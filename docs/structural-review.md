# koshi — Structural Review & Improvement Plan

**Date:** 2026-08-21  
**Author:** Prabin Karki (via Hermes review of the full codebase)

> This document is a companion to `docs/ARCHITECTURE.md` and
> `docs/superpowers/specs/2026-08-16-koshi-etl-architecture.md`. It covers
> only the **filesystem structure and organization** of the repo — not the
> system architecture, which those docs already handle.

---

## Current State: What's Good

Before listing problems, here's what should stay exactly as-is:

| Area | Why it works |
|---|---|
| **`src/koshi/` with `pyproject.toml`** | Proper Python packaging. Every subpackage has `__init__.py`. Installable with `pip install -e .` |
| **One model per file in `models/`** | Clean, scalable. Each file = one SQLAlchemy model. Easy to find, easy to test. |
| **`extraction/` — one module per source shape** | 7 extractors, each independently understandable. Adding a new source means a new file, not a patch. |
| **`tests/conftest.py` using real Postgres** | No SQLite, no mocks. Every new test copies the pattern. `test_alembic_migrations.py` additionally runs the real migration chain. |
| **Model registration via `models/__init__.py`** | Explicit import list, not magical `__subclasses__()` discovery. Alembic, conftest, and every caller uses one import. |
| **`alembic/` layout** | Standard, correct. Nothing to change. |

---

## Problem 1: `pipeline.py` at 619 lines — a god module (🔴 HIGH)

**Current state:** One file contains:
- 7 sync step functions (`sync_anzsco_occupations`, `sync_abs_occupations`, etc.)
- 6 URL constants (`ANZSCO_URL`, `SKILLSELECT_ROUNDS_URL`, etc.)
- A helper class (`_RowsWithSkipCount`)
- Watermark logic (`_needs_extraction`)
- Throttling parameters
- All orchestration dependencies

Every new source requires touching this file. At 17 more sources, it will be a ~1,500-line module where every change risks a merge conflict.

### Proposed fix: One sync module per source

```
src/koshi/
  pipeline.py              → ~80 lines (thin orchestration only)
  syncs/                    ← NEW directory
    __init__.py
    anzsco.py              ← sync_anzsco_occupations + JSA URL + pagination logic
    abs.py                 ← sync_abs_occupations + ABS URL + merge logic
    occupation_titles.py   ← sync_occupation_titles
    skillselect.py         ← sync_skillselect_rounds + current-round URL
    previous_rounds.py     ← sync_skillselect_previous_rounds
    bp0068.py              ← sync_bp0068_grants + BP0068 URL + visa subclass seeding
    backfill.py            ← backfill_unresolved_round_codes
```

Each sync module:
1. Owns its URL constant
2. Implements exactly one sync function
3. Calls `pipeline.py`'s shared helpers (`_needs_extraction`, `Throttler`, etc.)
4. Returns `list[Model]` — the same contract the current functions hold

`pipeline.py` becomes thin orchestration: it imports each sync module and calls it.
Adding a source is one new file, not a patch to a 619-line file.

**Why not the full control plane yet?** See [§Why the deferred architecture stays deferred](#why-the-deferred-architecture-stays-deferred) below.

---

## Problem 2: URL constants embedded in pipeline.py (🟡 MEDIUM)

6 URLs + throttling params + page caps are module-level strings inside `pipeline.py`. When the source registry grows to 23, this becomes unmanageable — URLs, domains, and politeness settings are scattered across sync modules.

### Proposed fix: Lightweight `sources.py` module

```python
# src/koshi/sources.py
import dataclasses

@dataclasses.dataclass(frozen=True)
class Source:
    key: str
    url: str
    domain: str
    category: str
    tier: str           # "hidden_field_json" | "json_api" | "xlsx_pivot_cache" | ...
    feeds: list[str]    # table names populated by this source
    cadence: str        # "nightly" | "weekly" | "monthly" | "annual"

ANZSCO = Source(
    key="anzsco",
    url="https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco",
    domain="jobsandskills.gov.au",
    category="occupations",
    tier="html_grid",
    feeds=["occupations"],
    cadence="nightly",
)

SKILLSELECT_ROUNDS = Source(
    key="skillselect-rounds",
    url="https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds",
    domain="homeaffairs.gov.au",
    category="eoi_rounds",
    tier="hidden_field_json",
    feeds=["eoi_rounds", "occupation_momentum"],
    cadence="nightly",
)

# ... 4 more built, 17 verified

ALL = [ANZSCO, SKILLSELECT_ROUNDS, ...]
```

This is a ~50-line dataclass registry — **not** the deferred control plane with 6 Postgres tables, extraction strategies, and schedules. It's a single source of truth for URL constants. The sync modules import from here instead of each defining their own strings.

---

## Problem 3: `docs/superpowers/` hierarchy is unnecessarily deep (🟡 LOW)

```
docs/superpowers/specs/2026-08-16-koshi-etl-architecture.md
docs/superpowers/research/2026-08-16-koshi-source-urls.md
docs/superpowers/research/2026-08-16-koshi-data-model.md
docs/superpowers/plans/2026-08-14-koshi-occupation-slice-v2.md
docs/superpowers/specs/feedback.md
```

`superpowers/` is a saathi carryover. In koshi, it adds zero signal — there's only one domain, and the folder name says nothing about its contents. The date prefixes help ordering but make filenames noisy and hard to reference ("the 2026-08-16 doc" vs "the data model doc").

### Proposed fix: flatten and rename

```
docs/
  API.md                                    (unchanged)
  ARCHITECTURE.md                           (unchanged)
  structural-review.md                      ← this file
  specs/
    design.md                               ← was 2026-08-14-koshi-design.md
    etl-architecture.md                     ← was 2026-08-16-koshi-etl-architecture.md
    etl-finalization.md                     ← was 2026-08-15-koshi-etl-finalization-design.md
    feedback.md                             (unchanged path, moved up one level)
  research/
    data-model.md                           ← was 2026-08-16-koshi-data-model.md
    source-urls.md                          ← was 2026-08-16-koshi-source-urls.md
    source-audit.md                         ← was source-audit/CONSOLIDATED-FINDINGS.md
  plans/
    occupation-slice-v2.md
    fault-tolerance-phase0.md
```

Dates stay in git history where they belong. Filenames describe what the doc *is*, not when it was written. All cross-references update once. Every link in `README.md`, `ARCHITECTURE.md`, `API.md`, and each spec that points to another doc gets updated.

---

## Problem 4: no `Dockerfile` for the application (🟡 LOW)

`docker-compose.yml` runs Postgres only. The API and ETL pipeline have no container definitions — they run bare-metal. Every new contributor sets up Python, venv, and deps manually.

### Proposed fix: Add Dockerfile + docker-compose services

```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .
COPY src/koshi/seeds/ src/koshi/seeds/
CMD ["uvicorn", "koshi.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Then `docker-compose.yml` adds `koshi-api` and `koshi-etl` services:

```yaml
services:
  postgres:
    # ... unchanged ...

  koshi-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+psycopg://koshi:koshi@postgres:5432/koshi
    depends_on:
      - postgres

  koshi-etl:
    build: .
    command: python -m koshi
    environment:
      - DATABASE_URL=postgresql+psycopg://koshi:koshi@postgres:5432/koshi
    depends_on:
      - postgres
```

This makes onboarding `docker compose up -d` and also pre-positions koshi for the Cloud Run (Job + Service) deployment model.

---

## Problem 5: API N+1 query in `GET /v1/occupations` (🟡 LOW)

```python
# api/occupations.py — current code
for occupation in occupations:          # 1,485 rows
    latest_momentum = session.scalar(   # 1,485 individual queries
        select(OccupationMomentum)...
    )
```

1,485 separate database round-trips when one batch load would do it.

### Proposed fix: Preload into a dict

```python
@router.get("", response_model=list[OccupationListItem])
def list_occupations(
    sort: Literal["code", "momentum"] = "code",
    session: Session = Depends(get_session),
) -> list[OccupationListItem]:
    occupations = session.scalars(
        select(Occupation).order_by(Occupation.code)
    ).all()

    # One query instead of 1,485
    momentums = session.execute(
        select(OccupationMomentum.occupation_code, OccupationMomentum.direction)
        .distinct(OccupationMomentum.occupation_code)
        .order_by(
            OccupationMomentum.occupation_code,
            OccupationMomentum.computed_at.desc(),
        )
    ).all()
    momentum_by_code = {row.occupation_code: row.direction for row in momentums}

    items = [
        OccupationListItem(
            code=occ.code,
            name=occ.name,
            momentum=momentum_by_code.get(occ.code),
        )
        for occ in occupations
    ]

    if sort == "momentum":
        items.sort(key=lambda item: _MOMENTUM_SORT_ORDER.get(item.momentum, 3))
    return items
```

Same result. 1 query instead of 1,486.

---

## Problem 6: Flat utility modules at package root (🟢 LOW — defer)

`crosswalk.py`, `momentum.py`, `insights.py`, `provenance.py`, `resilience.py`, `logging_config.py`, `run_summary.py` — 7 modules at `koshi/` top level, spanning three categories:

| Category | Modules |
|---|---|
| **Domain logic** | `crosswalk.py`, `momentum.py`, `insights.py` |
| **Infrastructure** | `logging_config.py`, `resilience.py`, `run_summary.py` |
| **Validation** | `provenance.py` |

**Verdict: defer.** 7 modules is manageable. The clean split would be `domain/`, `infra/` subpackages, but this is cosmetic at this scale. Revisit when the module count hits ~15.

---

## Problem 7: Tests are flat while source has subdirectories (🟢 LOW — defer)

25 test files all in `tests/`. Source has `api/`, `extraction/`, `models/`, `crawler/`, `seeds/`.

**Verdict: defer.** The flat test layout works and every file's name maps cleanly to its target (`test_extraction_skillselect.py` → `extraction/skillselect_rounds.py`). Mirroring the source tree (`tests/extraction/`, `tests/models/`) would be cleaner but is low-priority.

---

## Priority Order

| # | Change | Impact | Effort | Blocks anything? |
|---|---|---|---|---|
| **1** | Break up `pipeline.py` into `syncs/` | Prevents a 1,500-line monster at 17 more sources | Medium (~1 hr refactor) | Every new source |
| **2** | Extract URL constants into `sources.py` | Single place to find/add URLs; feeds the sync modules | Small (15 min) | Problem 1 |
| **3** | Flatten `docs/superpowers/` → `docs/` | Cleaner, shorter cross-reference paths | Small (30 min: move + grep replace links) | Nothing |
| **4** | Add `Dockerfile` + update `docker-compose.yml` | One-command onboarding; pre-positions for Cloud Run | Small (20 min) | Nothing |
| **5** | Fix N+1 query | 1,485 queries → 1 query | Small (5 min) | Nothing (only noticeable at scale) |
| **6** | Group flat utility modules | Cosmetic | Small (20 min) | Nothing |
| **7** | Organize tests into subdirectories | Cosmetic | Small (20 min) | Nothing |

**Start with 1–3.** The pipeline breakup and sources module are the changes that pay off immediately as more sources are added. The rest can be done incrementally without blocking any work.

---

## Why the Deferred Architecture Stays Deferred

The `docs/superpowers/specs/2026-08-16-koshi-etl-architecture.md` Part II documents a full medallion pipeline (Bronze → Silver → Gold), control plane (6 Postgres tables: sources, resources, extraction_strategies, contracts, quality_policies, schedules), data plane (snapshots, pipeline_runs, quarantine, dataset_releases), and a Source → Resource → Snapshot model. None of it is built. Here's why that's the correct decision, not a shortcut:

### The current (simpler) architecture

```
                   ┌──────────────────────────────────────┐
                   │         python -m koshi                │
                   │  (8 isolated sync steps, in order)     │
                   │                                        │
  Government       │  fetch_and_register(url)               │
  pages ──────────►│    → content_hash + source_pages row    │
 (immigov, ABS,    │    → _needs_extraction() check         │
  JSA, legislation │    → extraction/*.py deterministic parse│
  data.gov.au)     │    → require_provenance() gate          │
                   │    → session.add() + commit             │
                   │                                        │
                   │  logs/summaries/run_<ts>.json           │
                   │  logs/koshi.log                         │
                   └──────────────┬───────────────────────┘
                                  │ persisted rows
                   ┌──────────────▼───────────────────────┐
                   │         uvicorn koshi.main:app         │
                   │  GET /v1/occupations                   │
                   │  GET /v1/occupations/{code}            │
                   │  (read-only, never fetches or parses)  │
                   └──────────────────────────────────────┘
```

Every fact row carries `source_url` + `retrieved_at` + `reliability_tier`. The two-watermark design (`last_changed_at` vs `last_extracted_at`) prevents parse failures from freezing a page permanently. Run summaries are flat JSON files per invocation. This is simple, it works, and it handles 6 sources running end-to-end.

### Why each deferred piece stays deferred

| Deferred piece | Trigger to build it | Why it's not needed now |
|---|---|---|
| **Medallion pipeline** (Bronze → Silver → Gold) | At least one of: (a) managed-provider costs become worth amortizing via snapshot replay, (b) "what changed since last time" is a recurring question across sources | koshi's deterministic parsers are free per-run. Re-fetching a page costs nothing. There's no managed provider to pay for, so there's no snapshot to replay to save money. |
| **Source → Resource → Snapshot model** | Same trigger as the medallion pipeline — snapshots need to exist before the hierarchy matters | Currently, `source_pages` tracks content hashes per URL. That's sufficient for change detection. Adding per-resource snapshots with request/response/manifest storage is legitimate design for a future where a bad row silently reaching the API is a real risk — but with 6 sources, a human can verify the output. |
| **Control plane** (6 tables: sources, resources, extraction_strategies, contracts, quality_policies, schedules) | Source count is well past today's 6, or adding a source means touching more than one file | Today, adding a source means writing a new sync function + a new extractor module. This is two files. It becomes painful at ~15 sources. The lightweight `sources.py` dataclass registry proposed above (§Problem 2) is the right intermediate step — it centralizes URLs and metadata without the 6-table database migration. |
| **Data plane** (pipeline_runs, quarantine, dataset_releases) | Scheduling stops being manual, or a bad row reaches the API unnoticed and there's no quarantine to catch the next one | `logs/summaries/run_<ts>.json` and `logs/koshi.log` provide sufficient observability for hand-run syncs. Dataset releases with rollback are valuable when the API serves stale or corrupt data to a live frontend — but koshi isn't deployed yet, and lukla isn't consuming it in production. Building releases before deployment is premature. |
| **Provider ladder** (Firecrawl, Apify, Zyte, Playwright) | A catalogued source genuinely resists deterministic parsing | The 2026-08-17 audit fetched all 23 catalogued sources and found **zero** that need JS rendering, managed extraction, LLM extraction, or PDF extraction. The ladder's premise — "when does httpx + BS4 stop being enough?" — was answered: it doesn't. VIC's Cloudflare block is the sole exception and is a residential-IP problem, not an extraction-capability one. |
| **Scheduling** (Cloud Scheduler on cadence groups) | Moving off hand-running `python -m koshi` | The cadence groups are documented (nightly: EOI rounds, processing times; weekly: visa fees; monthly: ceilings; annual: funnel). When deployment happens, a `cronjob` on this machine or a Cloud Scheduler job will trigger the pipeline. The cadence-group design is ready; implementing it before deployment is premature. |

### The principle: "build the simpler thing first, defer the larger thing until its trigger fires"

Every deferred section in the spec document carries an explicit `⚠ DEFERRED` banner naming the trigger that would justify building it. None of the deferred pieces are wrong to have designed — they are legitimate reference architecture for koshi at a scale it has not reached. The current architecture (deterministic parsers, two-watermark change detection, per-row isolation, provenance trio, flat run summaries, hand-run pipeline) handles the 6 built sources correctly and will scale to the next several sources without architectural change.

When any of the triggers above fires, the reference design is ready — nothing needs to be redesigned, only built. Until then, the simpler architecture is the right architecture.