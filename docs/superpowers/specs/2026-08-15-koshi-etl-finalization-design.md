# koshi — ETL Pipeline: Complete Design

**Status:** Design complete — awaiting review before any implementation plan is written.
**Date:** 2026-08-15
**Author:** Prabin Karki, via Claude (native Plan Mode: Explore → Plan → Review; reconciled
with a second, independently-produced ETL design that landed on `main` from a
concurrent session — see §0)

---

## 0. This doc supersedes two prior drafts — read this first

Two comprehensive ETL designs were produced independently around the same
time: this doc's earlier draft (grounded in a live codebase audit run in
this session) and `docs/ETL-PIPELINE-ARCHITECTURE.md` (broader — industry
survey, scheduling groups, deployment costing, a full serving-layer
section). Rather than pick one wholesale, this revision merges them,
resolving the places they genuinely disagreed:

| Disagreement | Resolution | Why |
|---|---|---|
| Build Claude/PDF extraction (tiers 3/4) now, or skip for this pass? | **Skip.** All 12 remaining sources resolve to deterministic HTML or manual curation. | Explicitly confirmed in this session — see §5. |
| Include "how to present this data" logic in this doc? | **No — stays out of scope.** | Explicitly requested as a separate, later round. |
| Design the production deployment (Cloud Run Jobs, Cloud SQL, GCS DLQ) now? | **Document as target reference only, not scheduled work.** | This project's standing rule: local-first, don't pull Cloud SQL/Terraform forward until local setup is solid (design spec §11) — that rule doesn't change just because a second draft assumed otherwise. |
| Tier numbering (5-tier vs. a renumbered 4-tier scheme) | **Keep the original 5-tier scheme** (1 crawl, 2 HTML, 3 PDF, 4 Claude, 5 manual). | Matches what the existing codebase, the original design spec, and `docs/data-sources.md` already use — introducing a second numbering would be a pure new source of confusion. |
| `eligibility_requirements` vs. folding health/character content into `english_test_bands` | **`eligibility_requirements`, a new table.** | Health/character reference content isn't a test-score band table — the other draft's mapping was a mismatch, not a considered alternative. |

Everything else — the industry framing, the ERD-style diagrams, the
scheduling-cadence grouping idea, the DLQ design, the appendix tooling
comparisons — was genuinely additive and is folded in below, credited to
where it came from. `docs/ETL-PIPELINE-ARCHITECTURE.md` is marked
superseded (not deleted — the research in it, especially the appendix, is
worth keeping as reference) and points here.

---

## 1. Executive summary

koshi is a headless ETL pipeline feeding a read-only REST API: it extracts
structured, sourced facts about the Australian skilled-migration system
from government pages, and serves them with no end-user identity anywhere
(public data, identical for every caller).

| Layer | Today | Target (this doc) |
|---|---|---|
| Sources extracted | 2 (ANZSCO, SkillSelect rounds) | 16 cataloged sources |
| Tables populated | 5 | 19 (14 new — see §4) |
| Extraction tiers in use | 1 (deterministic HTML) | 2 (+ manual curation) — tiers 3/4 deliberately unbuilt this pass, see §5 |
| Fault tolerance | None (zero exception handling, zero logging anywhere — grep-verified) | Retry/backoff, per-item isolation, structured logging, run summaries — see §8 |
| Scheduling | Manual (`python -m koshi`) | Still manual this pass; cadence-group design documented for later (§10) |
| Deployment | Local only | Still local only this pass; target GCP architecture documented for later (§11) |

**Architecture principles** (unchanged from the existing design, restated
because every decision below has to hold these):

1. Every row carries provenance (`source_url`, `retrieved_at`,
   `reliability_tier`) except `derived` rows, which cite the koshi rows
   they were computed from instead.
2. Honesty over completeness — when a source doesn't exist or resists
   automation, say so; never ship a fabricated number.
3. Deterministic where possible. No LLM extraction is scheduled in this
   pass at all (§5) — everything either parses cleanly or gets curated.
4. The fetcher doesn't know about the parser — content hash and
   `last_changed_at` commit before parsing is attempted, so a failed parse
   is retried automatically on the next run (`source_pages.last_extracted_at`).
5. Derived ≠ scraped — computed facts (currently just momentum) cite the
   rows they were computed from, never an external URL.
6. koshi calls nothing else in the Saathi family, and nothing else calls
   into it except `lukla`.

## 2. What's already built (unchanged by this doc)

5 tables (`occupations`, `eoi_rounds`, `ceiling_usage`,
`occupation_momentum`, `source_pages`), 2 real sources, 1 manual-curation
seed, the extraction-watermark pattern, the provenance gate. Full account:
`docs/ARCHITECTURE.md`.

## 3. The fault-tolerance gap, confirmed precisely

Verified by direct audit, not impression: `grep -rn "except" src/koshi/`
and `grep -rn "import logging\|logger" src/koshi/` **both return zero
matches**. Specifically:

- **`__main__.py`'s 3-step sync has no isolation.** A bare `try/finally`
  (no `except`) means a failure in step 1 prevents steps 2 and 3 from
  running at all — even though the ceiling seed has zero dependency on
  either scraping step succeeding.
- **`crawler/fetch.py`** has no retry, no backoff, no rate limiting, a flat
  15s timeout with no connect/read split, and `response.raise_for_status()`
  propagates any 4xx/5xx unhandled straight up the whole call stack.
- **Both parsers crash the entire page on one bad row** — fixed-column
  tuple-unpacking raises on an unexpected cell count; `int(threshold)` /
  `int(invitations)` will crash on real-world formatting like `"1,234"` or
  placeholder text like `"N/A"`/`"-"`, discarding every other
  already-parsed good row on that page.
- **`seeds/loader.py`** has no per-entry isolation — one bad row anywhere
  in a curated YAML file blocks every other valid row in that file.
- **No rollback anywhere** on a failed `session.commit()`.
- **No observability beyond three `print()` calls** on the happy path only.

A proven, unported fix for most of this exists in
`research/au-visa-sources` (the crawler koshi's own crawler was rebuilt
from): real `tenacity`-based exponential backoff
(`notion_registry.py:130-140`), rate-limiting (`crawler.py:223-227`), split
timeouts (`crawler.py:266-267`), a sentinel-return pattern so one bad URL
doesn't crash a batch (`crawler.py:275-277`), per-record try/except with a
tally (`notion_registry.py:306-322`), dual stdout + rotating-file logging
(`main.py:38-57`), a JSON run-summary per run (`main.py:246-273`), and
meaningful process exit codes (`main.py:210-211`). §8 ports the *pattern*,
adapted — not the code verbatim.

`karki-labs-infra` has **nothing** to reuse for production fault-tolerance
— confirmed, not assumed: no Cloud Scheduler Terraform resource anywhere,
no Pub/Sub dead-letter topic, no Cloud Run Job resource, zero retry-policy
mentions in any `.tf` or `.md` file. That's fine — local-first is still
the deliberate current phase; §11 documents a target for later without
pretending any of it exists today.

## 4. The complete data model

Convention, matching the 5 already-built tables: SQLAlchemy 2.0
`Mapped[...]`, one model file per table, the provenance trio as the last
three columns except on derived tables, constraints declared via
`__table_args__` on the model (so `tests/test_alembic_migrations.py` keeps
catching drift), one Alembic migration per table continuing from `0006`.

```
occupations (built)
  │ 1
  ├──< eoi_rounds (built)
  ├──< ceiling_usage (built)
  ├──< occupation_momentum (built, derived)
  ├──< state_nomination_status (new)
  ├──< skills_priority_ratings (new)
  └──< occupation_assessing_bodies (new, join → assessing_bodies)

visa_subclasses (new, self-referential FK for onward_pathway_code)
  │ 1
  ├──< processing_times (new)
  └──< application_funnel (new)

assessing_bodies (new) ── points_criteria_reference (new) ── english_test_bands (new)
eligibility_requirements (new) ── list_change_log (new) ── program_allocation (new)
policy_events (new)
```
(ERD layout style borrowed from the superseded draft — content reconciled below.)

### 4.1 New reference tables

- **`visa_subclasses`** (migration `0007`) — `code` PK, `name`, `family`,
  `permanence`, `age_limit`, `work_rights_description`,
  `family_inclusion_rule`, `residency_requirement_description`,
  `occupation_list_required` (bool), `onward_pathway_code` (FK to itself,
  nullable — **seed in two passes**: all rows `NULL` first, then a second
  pass setting pathways, since a curated file can't guarantee insertion
  order), `base_application_cost` (Numeric), `points_test_required` (bool),
  provenance trio (default `official_curated`).
- **`english_test_bands`** (migration `0008`) — surrogate `id` PK +
  `UniqueConstraint(test_name, band_level)`, `score_requirement` (text —
  varies per test/skill, not one int), `points_awarded`, `cost`,
  `validity_period`, provenance trio (default `official_scraped`).
- **`assessing_bodies`** (migration `0009`) — `body_name` PK,
  `turnaround_estimate`, `cost`, provenance trio (default `official_curated`).
- **`occupation_assessing_bodies`** (migration `0010`) — composite PK
  `(occupation_code, body_name)`, both FKs, provenance trio (default
  `official_curated`) — genuinely many-to-many.
- **`points_criteria_reference`** (migration `0011`) — `id` PK,
  `criterion_name`, `band_description`, `points_value`,
  `UniqueConstraint(criterion_name, band_description)`, provenance trio
  (default `official_scraped`).

### 4.2 New time-series/fact tables

- **`policy_events`** (migration `0012`) — `id` PK, `event_date`,
  `visa_code` (FK, nullable — national events), `description`, provenance
  trio (default `official_curated`). Explicitly editorial.
- **`state_nomination_status`** (migration `0013`) — `id` PK, `state_code`,
  `occupation_code` (FK), `status` (`CheckConstraint` restricting to
  `open`/`limited`/`closed`), `fee`, `points_minimum`,
  `job_offer_required` (bool), `residency_commitment_description`,
  `decision_time_estimate`, `documents_required` (JSONB),
  `approval_pattern_note`, `as_of_date`, `UniqueConstraint(state_code,
  occupation_code, as_of_date)`, provenance trio (default `official_curated`).
- **`list_change_log`** (migration `0014`) — `id` PK, `list_name`
  (MLTSSL/STSOL/ROL or a state code), `occupation_code` (FK), `change_type`
  (`CheckConstraint` restricting to `added`/`removed`), `effective_date`,
  `UniqueConstraint(list_name, occupation_code, change_type,
  effective_date)` (mirrors `eoi_rounds`'s existing dedup precedent),
  provenance trio (default `official_scraped`). The "current MLTSSL
  membership" derived view over this table is presentation logic — out of
  scope here, only the raw log lands.
- **`processing_times`** (migration `0015`) — `id` PK, `visa_code` (FK),
  `as_of_date`, `median_days`, `UniqueConstraint(visa_code, as_of_date)`,
  provenance trio (default `official_scraped`).
- **`program_allocation`** (migration `0016`) — `id` PK, `program_year`,
  `stream_name`, `places`, `UniqueConstraint(program_year, stream_name)`,
  provenance trio (default `official_curated` — same PDF source as
  `ceiling_usage`).
- **`application_funnel`** (migration `0017`) — `id` PK, `visa_code` (FK),
  `program_year`, `as_of_date`, `submitted_count`/`invited_count`/
  `granted_count` (all nullable — `granted_count` launches `NULL` where
  unconfirmed), `UniqueConstraint(visa_code, program_year, as_of_date)`,
  `CheckConstraint` enforcing the funnel order where both sides are
  non-null. **Resolved design tension the superseded draft left open**:
  `submitted_count`/`invited_count` come from a monthly `official_scraped`
  page; `granted_count` comes from an annual `official_curated` PDF — two
  sources on one row. This table gets a **second, nullable provenance
  triple** scoped to `granted_count` alone (`granted_source_url`,
  `granted_retrieved_at`, `granted_reliability_tier`), rather than one
  triple papering over two different sources.

### 4.3 The two previously-unassigned-table gaps — resolved

1. **Health/character/English requirement reference pages** — 3
   near-static prose pages, not tabular data. New table:
   **`eligibility_requirements`** (migration `0018`) — `id` PK,
   `requirement_type` (`health`/`character`/`english_language`, unique),
   `summary`, provenance trio (default `official_curated`).
2. **Skills priority list** — Jobs and Skills Australia's shortage/demand
   rating, conceptually distinct from MLTSSL/STSOL/ROL. New table:
   **`skills_priority_ratings`** (migration `0019`) — `id` PK,
   `occupation_code` (FK), `shortage_rating`, `future_demand_rating`
   (nullable), `as_of_date`, `UniqueConstraint(occupation_code, as_of_date)`,
   provenance trio (default `official_scraped`). Flag: exact rating
   vocabulary needs confirming against the live page at implementation
   time.

`points_distribution` stays deferred — no confirmed source exists
anywhere in the crawl target list. Reaffirmed, not dropped.

Migrations land **just-in-time, one per source slice** (§9's build order),
not all upfront as an unexercised empty schema.

## 5. The complete source catalog

**Confirmed decision: no PDF (tier 3) or Claude-fallback (tier 4)
extraction gets built in this pass.** Every remaining source resolves to
tier 2 (deterministic HTML) or tier 5 (manual YAML curation). This
deliberately deviates from the original design spec's tentative tier-4
assignment for a couple of small-row-count sources.

| Source | Tier | Tooling | Note |
|---|---|---|---|
| Visa fees → `visa_subclasses.base_application_cost` | 2 | httpx + BS4/lxml | Update-by-PK, not insert |
| Points test criteria | 2 | httpx + BS4/lxml | Standalone |
| Processing times | 2 | httpx + BS4/lxml | Same shape as `skillselect_rounds.py` |
| MLTSSL/STSOL/ROL → `list_change_log` | 2 | httpx + BS4/lxml | Confirm legislation.gov.au's real HTML structure at build time |
| Skills priority list → `skills_priority_ratings` | 2 | BS4/lxml, or `pandas`/`openpyxl` if a downloadable dataset exists | Confirm format at build time |
| Application funnel — submitted/invited | 2 | **Piggybacked on the existing SkillSelect fetch** — extend `parse_skillselect_rounds` rather than fetch the same URL twice | Politeness + fault-tolerance win |
| Visa subclass static facts (189/190/491/485/500/482) | **5** | YAML seed + loader | 6 rows, rare cadence — tier 4 skipped |
| Health/character/English (`eligibility_requirements`) | **5** | YAML seed + loader | 3 rows, rare cadence |
| State nomination status/criteria | 5 | YAML seed + loader | Original spec's own explicit call |
| State occupation list changes | 1→5 | `source_pages` hash-diff triggers human review, written via YAML seed | Tier 1 is the trigger, tier 5 is the write path |
| Assessing bodies + join table | 5 | Two YAML seeds | New crawl domain: `mara.gov.au` |
| Policy events | 5 | YAML seed | New crawl domains: `budget.gov.au`, `treasury.gov.au` |
| Occupation ceilings / `program_allocation` | 5 | YAML seed | Same proven pattern as `ceiling_usage` |
| Application funnel — granted, by pathway | 5, or launches `NULL` | YAML seed only once a human confirms a real number | Weakest-sourced field in the catalog |

**Tiers 3/4 stay tooling-pre-researched, not built.** If a future source
genuinely needs them: PDF → `pdfplumber` first, `marker-pdf` (free, local)
or Claude vision as a second attempt if layout resists it; Claude fallback
→ Haiku (not Sonnet/Opus — extraction from prose is a Haiku-class task,
~$0.001/page vs. Sonnet's $0.015), structured-output JSON-schema mode,
`max_retries=1` not the SDK default of 2 (bato's own documented lesson:
`bato/api/llm.py:38-40` — the caller's own timeout budget is tighter than
the SDK assumes). This tooling research is real and worth keeping even
though nothing in this pass schedules building it.

## 6. Source-registry pattern

Today, adding a source means a new hardcoded URL constant in `pipeline.py`
plus a hand-written `sync_*` function copying the same
fetch→needs-extraction→parse→persist→watermark→commit shape. New module,
`src/koshi/source_registry.py`:

```python
class ExtractionTier(enum.IntEnum):
    CRAWL = 1
    HTML = 2
    PDF = 3
    LLM_FALLBACK = 4
    MANUAL_CURATION = 5

@dataclass(frozen=True)
class SourceSpec:
    key: str
    url: str
    domain: str
    category: str            # ports the category vocabulary from
                              # research/au-visa-sources/config.yaml
    tables: tuple[str, ...]  # one page can feed more than one table
    tier: ExtractionTier
    reliability_tier: str
    cadence: str = ""
    notes: str = ""

SOURCE_REGISTRY: dict[str, SourceSpec] = {}
```

Generalized orchestration replaces the copy-pasted skeleton:

```python
def run_source_sync(session, spec, *, parser, persist, client=None) -> list[Base]:
    page, _changed, text = fetch_and_register(
        session, url=spec.url, domain=spec.domain, category=spec.category, client=client
    )
    if not _needs_extraction(page):
        return []
    retrieved_at = dt.datetime.now(dt.timezone.utc)
    rows = parser(text, source_url=spec.url, retrieved_at=retrieved_at)
    new_rows = persist(session, rows)
    page.last_extracted_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    return new_rows
```

`sync_anzsco_occupations`/`sync_skillselect_rounds` become thin wrappers
with a `persist_merge_by_pk`/`persist_dedup_by_natural_key` strategy each
— **existing public signatures don't change**, so `tests/test_pipeline.py`
needs no changes for this refactor alone. Every new source registers
against `run_source_sync` directly.

**Domain config**: `src/koshi/sources/domains.yaml`, porting
`research/au-visa-sources/config.yaml`'s domain list and crawler settings
(`max_pages_per_run: 300`, `max_pages_per_domain: 15`, `request_delay: 1.0s`,
`timeout: 15s`), plus the two flagged-missing domains (`mara.gov.au`;
`budget.gov.au`/`treasury.gov.au`). **Scoping call:** this documents
politeness limits — it is **not** an autonomous link-following crawler.
koshi's whole catalog is specific, already-known URLs, each an explicit
`SourceSpec`. Autonomous discovery of new, unlisted pages is a materially
heavier capability, not needed to finish this catalog.

`__main__.py` becomes `for spec in SOURCE_REGISTRY.values(): ...` once
this lands (Phase 1, §9).

## 7. Pipeline stages — the full flow

Diagram style and stage-naming borrowed from the superseded draft (it's a
clear way to show this); the specifics are what's actually built +
designed here.

```
fetch_and_register()          →  1. EXTRACT   (crawler/fetch.py)
commit content_hash            →  2. HASH + WATERMARK (source_pages.last_changed_at)
_needs_extraction()?           →  3. DECIDE    (pipeline.py)
    NO  → skip
    YES → parser(text)         →  4. TRANSFORM (extraction/*.py, tier-dispatched)
          require_provenance() →  5. VALIDATE  (provenance.py)
          persist + dedup      →  6. LOAD      (pipeline.py, session.add/merge + commit)
          refresh_momentum()   →  7. DERIVE    (momentum.py — only where a source affects it)
          last_extracted_at    →  8. ADVANCE   (only after 4–6 all succeed)
```

Stage 2 and stage 8 are deliberately two different watermarks
(`last_changed_at` vs. `last_extracted_at`) — this is the mechanism that
lets a failed parse retry automatically on the next run without needing to
know it failed. Already built (`pipeline.py`'s `_needs_extraction`); every
new source inherits it for free via `run_source_sync` (§6).

**Contract every `sync_*`/registry entry holds:** returns `list[Model]`
(the rows persisted); empty is never an error (means "nothing new"); a
parse failure propagates and `last_extracted_at` is *not* advanced; each
source is independently runnable.

## 8. Fault-tolerance retrofit

New dependency: `tenacity>=8.2.0`.

### New modules

- **`src/koshi/logging_config.py`** — dual stdout + `RotatingFileHandler`
  (5MB, 3 backups) to `logs/koshi.log`, ported from
  `research/au-visa-sources/main.py:38-57`. Called once at the top of
  `__main__.main()`. Every module gets `logger = logging.getLogger(__name__)`,
  replacing the three bare `print()` calls.
- **`src/koshi/resilience.py`**:
  - `isolated_item(session, description)` — a context manager using
    `session.begin_nested()` (a Postgres SAVEPOINT), logging and
    swallowing exceptions so one bad item doesn't poison the *entire*
    enclosing transaction. A bare `try/except` around `session.add()`
    alone does **not** provide this — Postgres aborts a whole transaction
    on a failed statement unless a savepoint scopes the failure.
  - `Throttler` — ports `research/au-visa-sources/crawler.py:223-227`'s
    min-interval sleep. Wired in once a single run fetches multiple URLs
    (Phase 1+) — not needed today.
  - `parse_int_loose(text) -> int | None` — strips thousands separators,
    maps placeholder tokens (`"N/A"`, `"-"`, `""`) to `None`, raises a
    clear `ValueError` on genuine garbage.
- **`src/koshi/run_summary.py`** — JSON run summary per invocation to
  `logs/summaries/run_<timestamp>.json`, ported from
  `research/au-visa-sources/main.py:246-273`. (`.gitignore` needs a
  `logs/` entry.)

### `crawler/fetch.py`

- Split timeout: `httpx.Timeout(connect=10.0, read=15.0, write=10.0, pool=10.0)`.
- `_get_with_retry(client, url)` wraps the GET with `tenacity`
  (`stop_after_attempt(5)`, `wait_exponential(multiplier=1, min=1, max=30)`,
  `before_sleep=logger.warning(...)`), retrying on a transport error or an
  HTTP status in `(429, 500, 502, 503, 504)`. **Retry only transient
  failures** — never retry a 404/400 or a parse error that will fail
  identically next time; the watermark already handles retry-on-next-run
  for those.
- A typed `FetchError` (url/domain/category attached) wraps the
  exhausted-retry case, so callers catch one clear exception instead of a
  raw `httpx.HTTPStatusError` propagating unhandled.

### Both parsers

Wrap each row's parse+construct inside the row loop in
`try/except (AttributeError, ValueError, IndexError)`, using
`parse_int_loose` for numeric fields, logging a warning per skipped row
(row index + raw cell text) and continuing rather than aborting the page.
`threshold_points` stays non-nullable — a row that fails to parse it is
skipped entirely; `invitations_issued` is already nullable.

**Flagged, deliberate small API change:** parsers return
`ParseResult(rows, skipped)` instead of a bare `list[...]`, so skip counts
reach the run summary without log-scraping. Touches
`parse_anzsco_occupations`/`parse_skillselect_rounds`'s return type —
`tests/test_extraction_anzsco.py`/`tests/test_extraction_skillselect.py`
need a trivial `result.rows` update.

### `seeds/loader.py`

Per-entry isolation (porting `notion_registry.py:306-322`'s per-record
try/except + tally pattern), generalized into
`load_seed_rows(path, *, row_builder, extra_validators)` since ~7 of the
remaining sources are tier-5 manual curation. `load_ceiling_usage_seed`/
`seed_ceiling_usage` become thin wrappers, preserving behavior.

### `pipeline.py`

Momentum-refresh loop gets a try/except per occupation code (sufficient
isolation on its own since `refresh_momentum` already commits per call):

```python
for code in new_codes:
    try:
        refresh_momentum(session, code)
    except Exception:
        logger.exception("momentum refresh failed for occupation_code=%s", code)
```

### `__main__.py` — the core isolation fix

```python
def main() -> int:
    setup_logging()
    logger = logging.getLogger(__name__)
    session = SessionLocal()
    summary = {"started_at": ..., "steps": []}
    try:
        for name, step in [
            ("anzsco_occupations", lambda: sync_anzsco_occupations(session)),
            ("skillselect_rounds", lambda: sync_skillselect_rounds(session)),
            ("ceiling_usage_seed", lambda: seed_ceiling_usage(session, CEILING_USAGE_SEED_PATH)),
        ]:
            try:
                result = step()
                summary["steps"].append({"name": name, "status": "ok", "count": len(result)})
                logger.info("%s: %d new/updated", name, len(result))
            except Exception:
                session.rollback()
                logger.exception("%s failed — continuing with remaining steps", name)
                summary["steps"].append({"name": name, "status": "failed"})
    finally:
        session.close()

    write_run_summary(summary)
    ok = sum(s["status"] == "ok" for s in summary["steps"])
    failed = sum(s["status"] == "failed" for s in summary["steps"])
    if failed and ok == 0:
        return 3
    if failed:
        return 2
    return 0
```

### Failure modes — reference table (format borrowed from the superseded draft)

| Failure mode | Current behavior | Target behavior |
|---|---|---|
| Network timeout / transient 5xx | Unhandled, crashes the sync | Retry w/ backoff (tenacity), then `FetchError` |
| 404/410 | Unhandled | Mark `source_pages.status='dead'`, skip, continue |
| Malformed row | Whole page/file aborts | Skip + log that row, keep the rest |
| DB commit failure | No rollback, propagates | `session.rollback()` in `__main__`'s per-step catch; `isolated_item()` for per-row DB isolation |
| One step fails | Later steps never run | Per-step try/except — every step attempts, run summary + exit code report which |

### Resolving the hard-fail-vs-soft-fail open question

Layered, not a single switch:

- **Per-row/per-entry**: soft-fail — skip, log, continue.
- **Per-source**: soft-fail at orchestration level — mark the step failed
  in the run summary, move to the next source.
- **Whole-run signaling**: the **exit code is the alerting mechanism** for
  now — `0` clean, `2` partial failure (the *expected common state* once
  there are 16 sources, not an edge case — hence its own code), `3` total
  failure, `1` reserved for fatal init failures (DB unreachable before any
  step runs). A cron wrapper — and later, Cloud Scheduler + Cloud
  Monitoring, once deployed — can act on `2`/`3` without koshi needing any
  notification integration built. If a lightweight channel is wanted
  sooner, a Discord webhook (the superseded draft's suggestion) is a
  reasonable default — not built in this pass, just not a bad idea for later.

### Dead-letter design — documented, not built

The superseded draft's DLQ design is worth keeping as a *documented
target*, not built now (nothing in `karki-labs-infra` exists to host it
yet — §3): on exhausted-retry parse failure, the raw page content would
save to a GCS bucket (`koshi-dlq/<date>/<page>.html` + a `manifest.json`
failure record: url, error, retry_count, content_hash), replayable later
via a manual `python -m koshi replay --manifest ...` command once a fix
ships. Deferred alongside the rest of §11's production infra.

### Foundational vs. deferred

**Foundational (Phase 0):** structured logging, `__main__.py` per-step
isolation + exit codes, per-row isolation + `parse_int_loose` in both
parsers, `resilience.py`'s `isolated_item()`, retry/backoff + split
timeout in `crawler/fetch.py`, seed-loader per-entry isolation +
generalization, the source-registry pattern.

**Deferred:** `Throttler` wiring (matters once a run fetches multiple URLs
— not yet), the GCS DLQ, Cloud Scheduler/Cloud Run Job/Pub/Sub design
(§11), a bato-style batch-level validation gate (worth it once row volumes
are non-trivial, not with 6 tables), the CDN/UA-fallback retry trick
(solves an Akamai-block problem koshi hasn't hit against its actual
targets).

## 9. Sequencing (confirmed: curation-effort order)

**Phase 0 — Fault-tolerance retrofit on the 2 existing sources.** Everything
in §8's foundational list, plus new tests (malformed-row fixtures, a
bad-YAML-entry test, a retry test via `httpx.MockTransport`). Cheapest,
highest-leverage — every source added afterward inherits this for free.

**Phase 1 — Source-registry refactor** (§6).

**Phase 2 — New sources, in this order:**
1. `visa_subclasses` (tier 5, 6 rows) — unblocks the FK every later table needs.
2. Visa fees → `visa_subclasses.base_application_cost` (tier 2).
3. Processing times (tier 2) — cheapest pure-insert table, proves the registry end-to-end.
4. Points test criteria (tier 2).
5. English test bands (tier 2).
6. Assessing bodies + join table (tier 5) — first join-table curation, first new crawl domain.
7. Policy events (tier 5) — second new crawl domain.
8. Eligibility requirements (tier 5, gap 1).
9. Skills priority ratings (tier 2).
10. MLTSSL/STSOL/ROL + state list changes → `list_change_log`.
11. **State nomination status (tier 5) — deliberately last**: highest per-row curation effort of any source (5 states × many occupations × many fields), attempted once the curation pattern is well-worn on cheaper sources first. (Confirmed: curation-effort order over presentation-priority order, even though this is probably the most visually prominent panel in the Landscape Navigator mockup.)
12. `program_allocation` + `application_funnel` (submitted/invited piggybacked on the existing SkillSelect fetch; `granted_count` ships `NULL` or tier-5-curated).
13. `points_distribution` — stays deferred, not scheduled.

Tiers 3/4 stay unbuilt for this whole pass. Revisit only if step 10 or
step 12's curation cadence genuinely proves unsustainable.

## 10. Scheduling model — documented for later, not active now

Borrowed from the superseded draft: once koshi has 16 sources, running
everything on one daily cron is wasteful — most sources change monthly or
less. A cadence-grouped model is the right target:

| Cadence | Sources | Trigger (once deployed) |
|---|---|---|
| Nightly | EOI rounds, processing times, momentum | Cloud Scheduler, 03:00 AEST |
| Weekly | Visa fees, visa subclass facts, state list changes | Monday 03:00 |
| Monthly | Ceilings, points test, English/health refs, funnel | 1st of month |
| Quarterly | Legislation lists, skills priority | Jan/Apr/Jul/Oct 1st |
| Annual | Funnel granted, assessing bodies | 1 July (program year start) |
| On-demand | Policy events | Manual trigger |

`__main__.py` would take an optional `--group` argument once this
matters. **Not built in this pass** — today's `python -m koshi` runs
everything, every time, manually, which is correct at 2-16 sources and
zero deployment.

## 11. Target deployment architecture — documented for later, not scheduled

Kept from the superseded draft as reference, explicitly **not** work this
design schedules (§3, §8: nothing in `karki-labs-infra` exists to build
this on yet, and the project's standing rule is local-first until local
setup is solid):

```
Cloud Scheduler (cron) → Cloud Run Job (ETL, python -m koshi --group ...)
                              ↓
                        Cloud SQL Postgres (shared instance, own database)
                              ↓
Cloud Run Service (API, uvicorn) ← lukla (Cloud Run IAM invoker only)
                              ↓
                        GCS (koshi-dlq) — dead-letter bucket
```

Rough estimated marginal cost once deployed: under $10/month (Cloud SQL
cost is shared across the other Saathi services, not koshi-specific).
Deploy mechanism matches the rest of this project family: Cloud Run (never
GKE), GitHub Actions + WIF (never Cloud Build), Terraform in
`karki-labs-infra` only once local setup has proven the pipeline end to
end.

## 12. Explicitly out of scope

- **New API endpoints, derived views, national/state/visa aggregation, or
  any "how to present this data" logic.** Requested as a separate, later
  planning round — not folded in here even though a prior draft did.
- **Any actual deployment work** — Cloud Run, Cloud SQL, Cloud Scheduler,
  GCS, Terraform. §10 and §11 are documentation of a target, not tasks.

## 13. Appendix — tooling comparisons (condensed reference)

Kept from the superseded draft's research, useful when tiers 3/4 or
production deployment actually get scheduled:

| Need | Options considered | Verdict |
|---|---|---|
| HTML parsing | BS4+lxml vs. Scrapy vs. Playwright | BS4+lxml — koshi targets ~16 known pages, not thousands of unknown ones; no JS rendering needed |
| PDF extraction | pdfplumber vs. marker-pdf vs. LlamaParse vs. Claude vision | pdfplumber first (already the project's stated default); marker-pdf as a free local fallback; Claude vision last resort |
| LLM fallback model | Haiku vs. Sonnet vs. Opus vs. GPT-4o(-mini) | Haiku — extraction from prose is a Haiku-class task; Opus is never justified for this |
| Orchestration | Cloud Run Jobs vs. Airflow/Prefect vs. Kafka | Cloud Run Jobs — 16 independent, batch-cadence sources don't justify an always-on scheduler or streaming infra |
| Transform layer | Custom Python vs. dbt | Custom — koshi's hard part is extraction from HTML/PDF, not SQL transforms on already-loaded data |
| Storage | Postgres vs. BigQuery vs. MongoDB | Postgres — koshi's data is relational with FK constraints, at a scale (<1M rows) BigQuery doesn't justify |

## 14. Open items for whoever picks up implementation

- `list_change_log`'s legislation.gov.au source needs its real HTML
  structure confirmed before committing to pure tier-2.
- `skills_priority_ratings`' rating vocabulary needs confirming against
  the live JSA page.
- The `application_funnel` dual-provenance design (§4.2) is a genuine
  schema extension beyond the original spec's single-triple convention.
- The parser return-type change (`ParseResult(rows, skipped)`) touches two
  existing, already-reviewed test files.

## 15. Success criteria

Faithful to this doc if: every new table carries the provenance trio (or
is explicitly `derived`); no source needs a crawl domain that isn't in
`sources/domains.yaml`; a malformed row in any parser or seed file is
skipped and logged, never crashes the whole run; `__main__.py`'s steps run
independently, with a failure in one never preventing an unrelated step
from running; every network call goes through retry/backoff with a split
timeout; the run summary and exit code correctly reflect partial vs.
total vs. clean success; no PDF or Claude-fallback extraction code exists
yet; no deployment/Terraform work happened as a side effect of this pass;
and — unchanged from the existing design — no row ships without a source,
no generated string states or implies a personalized outcome, and koshi
has zero end-user-identity code anywhere.
