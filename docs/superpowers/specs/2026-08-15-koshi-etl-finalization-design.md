# koshi — ETL Finalization Design

**Status:** Design complete — awaiting review before any implementation plan is written.
**Date:** 2026-08-15
**Author:** Prabin Karki, via Claude (native Plan Mode: Explore → Plan → Review)

---

## 1. Why this exists

The occupation vertical slice (merged to `main`) proved the ETL shape works
end to end — crawl → parse → validate → persist → serve — but it only
covers 4 of the design spec's 16 cataloged data sources, and a full
codebase audit found the pipeline has **zero exception handling and zero
logging anywhere** (`grep -rn "except" src/koshi/` and
`grep -rn "import logging\|logger" src/koshi/` both return no matches).
That's fine for a first slice proving the pattern; it's not fine as the
foundation for 12 more sources.

This doc finalizes three things together, because they're genuinely
coupled: the **complete data model** (every remaining table), the
**complete source catalog** (every remaining source's extraction method and
tooling), and a **fault-tolerance retrofit** (the pipeline needs to survive
a bad row, a network blip, or a malformed page without silently corrupting
data or crashing the whole run). Presentation/application logic — new API
endpoints, derived views, national/state aggregations — is **explicitly
out of scope**, per direction: that's a separate, later planning round.

This is a design document, not a task-by-task implementation plan. Once
reviewed and approved, it feeds a `superpowers:writing-plans` pass (or
several, per the sequencing in §7) the same way every other design in this
project has.

## 2. What's already built (unchanged by this doc)

5 tables (`occupations`, `eoi_rounds`, `ceiling_usage`,
`occupation_momentum`, `source_pages`), 2 real sources (ANZSCO occupations,
SkillSelect EOI rounds), 1 manual-curation seed (`ceiling_usage`), the
extraction-watermark pattern (`source_pages.last_extracted_at`), and the
provenance gate (`provenance.py`). See `docs/ARCHITECTURE.md` for the full
account — nothing here changes what's already merged, only what's added
around it.

## 3. The fault-tolerance gap, confirmed precisely

Every claim below is a verified file:line, not a general impression.

- **`__main__.py`'s 3-step sync has no isolation.** A bare `try/finally`
  (no `except`) means if `sync_anzsco_occupations` (line 34) raises,
  `sync_skillselect_rounds` and `seed_ceiling_usage` (lines 37, 40) never
  run — even though the ceiling seed has zero dependency on either
  scraping step succeeding.
- **`crawler/fetch.py` has no retry, no backoff, no rate limiting, a flat
  15s timeout with no connect/read split**, and `response.raise_for_status()`
  (line 42) propagates any 4xx/5xx unhandled straight up through the whole
  call stack.
- **Both parsers crash the entire page on one bad row.** Fixed-column
  tuple-unpacking (`anzsco_occupations.py:22`, `skillselect_rounds.py:30-32`)
  raises on any row with an unexpected cell count; `int(threshold)` /
  `int(invitations)` (`skillselect_rounds.py:38-39`) will crash on
  real-world formatting like `"1,234"` or placeholder text like `"N/A"`/`"-"`
  for a zero-invitation row — discarding every other already-parsed good
  row on that page.
- **`seeds/loader.py` has no per-entry isolation** — one bad row anywhere
  in a hand-curated YAML file blocks every other valid row in that file.
- **No rollback anywhere.** A failed `session.commit()` (present in
  `fetch.py`, `pipeline.py` ×2, `momentum.py`, `loader.py`) has no recovery
  path.
- **No observability beyond three `print()` calls on the happy path only.**

A proven fix for most of this already exists, unported, in a sibling repo:
`research/au-visa-sources` (the crawler koshi's own crawler was originally
rebuilt from) has real `tenacity`-based exponential backoff
(`notion_registry.py:130-140`), rate-limiting (`crawler.py:223-227`), split
connect/read timeouts (`crawler.py:266-267`), a sentinel-return pattern so
one bad URL doesn't crash a batch (`crawler.py:275-277`), per-record
try/except with a tally (`notion_registry.py:306-322`), dual stdout +
rotating-file logging (`main.py:38-57`), a JSON run-summary per run
(`main.py:246-273`), and meaningful process exit codes
(`main.py:210-211`). This design ports the pattern, not the code verbatim —
`fetch.py`'s recovery semantics differ (see §6).

`karki-labs-infra` has **nothing** to reuse for production-level
fault-tolerance (no Cloud Scheduler Terraform resource, no Pub/Sub
dead-letter topic, no Cloud Run Job resource, zero retry-policy mentions
anywhere in the repo) — confirmed, not assumed. That's fine: local-first is
still the deliberate current phase (design spec §11); this doc's
fault-tolerance work is entirely application-level, and the deployment-level
story stays an explicitly named future gap, not something faked here.

## 4. The complete data model

Convention, matching the 5 already-built tables exactly: SQLAlchemy 2.0
`Mapped[...]`, one model file per table under `src/koshi/models/`, the
provenance trio (`source_url`, `retrieved_at`, `reliability_tier`) as the
last three columns except on derived tables, constraints declared via
`__table_args__` on the model (not just the migration, so
`tests/test_alembic_migrations.py` keeps catching drift), one Alembic
migration per table continuing the numbering from `0006`.

### 4.1 New reference tables

- **`visa_subclasses`** (migration `0007`) — `code` PK, `name`, `family`,
  `permanence`, `age_limit`, `work_rights_description`,
  `family_inclusion_rule`, `residency_requirement_description`,
  `occupation_list_required` (bool), `onward_pathway_code` (FK to itself,
  nullable — **seed in two passes**: all rows with `NULL` first, then a
  second pass setting pathways, since a curated file can't guarantee
  insertion order otherwise), `base_application_cost` (Numeric),
  `points_test_required` (bool), provenance trio (default
  `official_curated`).
- **`english_test_bands`** (migration `0008`) — surrogate `id` PK +
  `UniqueConstraint(test_name, band_level)` (not a true composite PK —
  matches this codebase's existing idiom and is simpler for the loader to
  upsert against), `score_requirement` (text — varies per test/skill, not
  one int), `points_awarded`, `cost`, `validity_period`, provenance trio
  (default `official_scraped`).
- **`assessing_bodies`** (migration `0009`) — `body_name` PK,
  `turnaround_estimate`, `cost`, provenance trio (default `official_curated`).
- **`occupation_assessing_bodies`** (migration `0010`) — composite PK
  `(occupation_code, body_name)`, both FKs, provenance trio (default
  `official_curated`) — genuinely many-to-many per the original spec.
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
  membership" derived view over this table is query/presentation logic —
  explicitly out of scope here; only the raw log lands in this phase.
- **`processing_times`** (migration `0015`) — `id` PK, `visa_code` (FK),
  `as_of_date`, `median_days`, `UniqueConstraint(visa_code, as_of_date)`,
  provenance trio (default `official_scraped`).
- **`program_allocation`** (migration `0016`) — `id` PK, `program_year`,
  `stream_name`, `places`, `UniqueConstraint(program_year, stream_name)`,
  provenance trio (default `official_curated` — same PDF source as
  `ceiling_usage`).
- **`application_funnel`** (migration `0017`) — `id` PK, `visa_code` (FK),
  `program_year`, `as_of_date`, `submitted_count` (nullable),
  `invited_count` (nullable), `granted_count` (nullable — launches `NULL`
  where unconfirmed, per the original spec's own honesty rule),
  `UniqueConstraint(visa_code, program_year, as_of_date)`,
  `CheckConstraint` enforcing `invited_count <= submitted_count` and
  `granted_count <= invited_count` where both sides are non-null.
  **Design decision, not unilaterally silent:** `submitted_count`/
  `invited_count` come from a monthly `official_scraped` SkillSelect page;
  `granted_count` comes from an annual `official_curated` PDF — two
  different sources on one row. Resolution: a **second, nullable
  provenance triple** scoped to `granted_count` alone
  (`granted_source_url`, `granted_retrieved_at`, `granted_reliability_tier`),
  leaving the row-level triple describing `submitted_count`/
  `invited_count`. Flagged here explicitly since it extends the spec's
  single-triple-per-table convention — reasonable given the alternative is
  silently misattributing `granted_count`'s real source.

### 4.3 The two previously-unassigned-table gaps — resolved

1. **Health/character/English requirement reference pages** — 3 near-static
   prose pages, not tabular data, so `english_test_bands` is genuinely the
   wrong fit. New table: **`eligibility_requirements`** (migration `0018`)
   — `id` PK, `requirement_type` (`health`/`character`/`english_language`,
   unique), `summary`, provenance trio (default `official_curated`). Named
   to avoid colliding semantically with `source_pages`.
2. **Skills priority list** — Jobs and Skills Australia's shortage/demand
   *rating* per occupation, conceptually distinct from the MLTSSL/STSOL/ROL
   eligibility lists (doesn't fit `list_change_log`'s added/removed shape).
   New table: **`skills_priority_ratings`** (migration `0019`) — `id` PK,
   `occupation_code` (FK), `shortage_rating`, `future_demand_rating`
   (nullable), `as_of_date`, `UniqueConstraint(occupation_code, as_of_date)`,
   provenance trio (default `official_scraped`). **Flag for
   implementation:** the exact rating vocabulary needs confirming against
   the live page when this source is actually built — not guessable from
   this planning pass.

`points_distribution` stays deferred — no table, no code, per the original
spec. Reaffirmed, not silently dropped: no confirmed source exists for it
anywhere in the crawl target list.

**Migrations land just-in-time, one per source slice** — matching the
existing `0002`→`0006` pattern — not all 13 upfront as an empty,
unexercised schema.

## 5. The complete source catalog

Every not-yet-built source, assigned a concrete tier and tooling. Per the
confirmed decision in §1 of this planning round: **no PDF (tier 3) or
Claude-fallback (tier 4) extraction gets built in this pass** — every
remaining source resolves to tier 2 (deterministic HTML) or tier 5 (manual
YAML curation). This is a deliberate deviation from the original design
spec, which had tentatively named a couple of small-row-count sources as
tier-4 candidates — recorded here as a conscious choice, not an oversight.

| Source | Tier | Tooling | Note |
|---|---|---|---|
| Visa fees → `visa_subclasses.base_application_cost` | 2 | httpx + BS4/lxml | Update-by-PK, not insert |
| Points test criteria | 2 | httpx + BS4/lxml | Standalone |
| Processing times | 2 | httpx + BS4/lxml | Same shape as `skillselect_rounds.py` |
| MLTSSL/STSOL/ROL → `list_change_log` | 2 | httpx + BS4/lxml | Confirm legislation.gov.au's real HTML structure at build time before committing to pure-tier-2 |
| Skills priority list → `skills_priority_ratings` | 2 | BS4/lxml, or `pandas`/`openpyxl` if JSA publishes a downloadable dataset | Confirm format at build time |
| Application funnel — submitted/invited | 2 | **Piggybacked on the existing SkillSelect fetch** — extend `parse_skillselect_rounds` to also emit `ApplicationFunnel` rows from the page already fetched | Avoids a redundant fetch of the same URL |
| Visa subclass static facts (189/190/491/485/500/482) | 5 | YAML seed + loader | 6 rows, rare cadence — tier 4 skipped per §1 decision |
| Health/character/English reference (`eligibility_requirements`) | 5 | YAML seed + loader | 3 rows, rare cadence |
| State nomination status/criteria | 5 | YAML seed + loader | Original spec's own explicit call |
| State occupation list changes | 1→5 | `source_pages` hash-diff triggers a human review, written via YAML seed | Tier 1 is the trigger, tier 5 is the write path |
| Assessing bodies + join table | 5 | Two YAML seeds | New crawl domain: `mara.gov.au` |
| Policy events | 5 | YAML seed | New crawl domains: `budget.gov.au`, `treasury.gov.au`, ministerial press releases |
| Occupation ceilings / `program_allocation` | 5 | YAML seed | Same proven pattern as the existing `ceiling_usage` seed |
| Application funnel — granted, by pathway | 5, or launches `NULL` | YAML seed only once a human confirms a real number | Weakest-sourced field in the whole catalog |

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

A generalized orchestration function replaces the copy-pasted skeleton:

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
around `run_source_sync` with a `persist_merge_by_pk`/
`persist_dedup_by_natural_key` strategy each — **their existing public
signatures don't change**, so `tests/test_pipeline.py` (which imports them
directly) needs no changes for this refactor alone. Every new source
registers against `run_source_sync` directly.

**Domain config**: a new `src/koshi/sources/domains.yaml`, porting
`research/au-visa-sources/config.yaml`'s domain list and crawler settings
(`max_pages_per_run: 300`, `max_pages_per_domain: 15`, `request_delay: 1.0s`,
`timeout: 15s` — already named in the original design spec), plus the two
flagged-missing domains (`mara.gov.au`; `budget.gov.au`/`treasury.gov.au`).
**Scoping call:** this documents domain-level politeness limits — it is
**not** an autonomous link-following crawler like
`research/au-visa-sources/crawler.py`'s sitemap discovery. koshi's whole
catalog is specific, already-known URLs, each an explicit `SourceSpec`.
Autonomous discovery of new, unlisted pages is a materially heavier
capability, not needed to finish this catalog — flagged as a possible
future capability only if that need arises, not scheduled work.

`__main__.py` becomes `for spec in SOURCE_REGISTRY.values(): ...` once this
lands (Phase 1, §7).

## 7. Fault-tolerance retrofit

New dependency: `tenacity>=8.2.0` (proven choice, already used in
`research/au-visa-sources`).

### New modules

- **`src/koshi/logging_config.py`** — dual stdout + `RotatingFileHandler`
  (5MB, 3 backups) to `logs/koshi.log`, ported from
  `research/au-visa-sources/main.py:38-57`. Called once at the top of
  `__main__.main()`. Every module gets `logger = logging.getLogger(__name__)`,
  replacing the three bare `print()` calls in `__main__.py`.
- **`src/koshi/resilience.py`**:
  - `isolated_item(session, description)` — a context manager using
    `session.begin_nested()` (a Postgres SAVEPOINT), logging and
    swallowing exceptions so one bad item doesn't poison the *entire*
    enclosing transaction. This is the specific mechanism a bare
    `try/except` around `session.add()` does **not** provide — Postgres
    aborts a whole transaction on a failed statement unless a savepoint is
    used to scope the failure.
  - `Throttler` — ports `research/au-visa-sources/crawler.py:223-227`'s
    min-interval sleep pattern. Wired in once a single run fetches
    multiple URLs (Phase 1+) — not needed today (one fetch per sync call).
  - `parse_int_loose(text) -> int | None` — strips thousands separators,
    maps placeholder tokens (`"N/A"`, `"-"`, `""`) to `None`, raises a
    clear `ValueError` on genuine garbage.
- **`src/koshi/run_summary.py`** — JSON run summary per invocation (counts,
  per-step status) to `logs/summaries/run_<timestamp>.json`, ported from
  `research/au-visa-sources/main.py:246-273`. (`.gitignore` needs a `logs/`
  entry — not currently present.)

### `crawler/fetch.py`

- Split timeout: `httpx.Timeout(connect=10.0, read=15.0, write=10.0, pool=10.0)`
  replacing the flat `timeout=15.0`.
- `_get_with_retry(client, url)` wraps the GET with `tenacity`
  (`stop_after_attempt(5)`, `wait_exponential(multiplier=1, min=1, max=30)`,
  `before_sleep=logger.warning(...)`), retrying on a transport error or an
  HTTP status in `(429, 500, 502, 503, 504)`.
- A typed `FetchError` (carrying url/domain/category) wraps the
  exhausted-retry case, so callers catch one clear exception instead of a
  raw `httpx.HTTPStatusError` propagating unhandled.

### Both parsers

Wrap each row's parse+construct inside the row loop in
`try/except (AttributeError, ValueError, IndexError)`, using
`parse_int_loose` for numeric fields, logging a warning per skipped row
(row index + raw cell text) and continuing rather than aborting the page.
`threshold_points` stays non-nullable — a row that fails to parse it is
skipped entirely; `invitations_issued` is already nullable, so a
placeholder token maps cleanly to `None`.

**Flagged, deliberate small API change:** parsers return
`ParseResult(rows, skipped)` instead of a bare `list[...]`, so skip counts
reach the run summary without log-scraping. This touches
`parse_anzsco_occupations`/`parse_skillselect_rounds`'s return type —
`tests/test_extraction_anzsco.py`/`tests/test_extraction_skillselect.py`
need a trivial `result.rows` update. Named explicitly rather than treated
as free.

### `seeds/loader.py`

Per-entry isolation in the seed-loading loop (porting
`research/au-visa-sources/notion_registry.py:306-322`'s per-record
try/except + tally pattern), plus generalization: `load_seed_rows(path, *,
row_builder, extra_validators)`, since ~7 of the remaining sources are
tier-5 manual curation and need this exact pattern.
`load_ceiling_usage_seed`/`seed_ceiling_usage` become thin wrappers,
preserving existing behavior so `tests/test_ceiling_seed_loader.py` stays
green.

### `pipeline.py`

The momentum-refresh loop gets a try/except per occupation code — since
`refresh_momentum` already commits per call, this alone is sufficient
isolation (no savepoint needed there specifically):

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

This is the direct fix for §3's headline finding: today, a failure in step
1 means steps 2 and 3 never run at all, even though the ceiling seed has
zero dependency on either scraping step.

### Resolving the hard-fail-vs-soft-fail open question

A single global switch is the wrong shape. Layered answer instead:

- **Per-row/per-entry** (a malformed round, a bad YAML seed entry):
  soft-fail — skip, log, continue. This is what the row/entry isolation
  work above *is*.
- **Per-source** (a whole page fails to fetch/parse): soft-fail at the
  `__main__` orchestration level — mark that step failed in the run
  summary, move to the next source.
- **Whole-run signaling**: the **exit code is the alerting mechanism** —
  `0` clean, `2` partial failure (some sources succeeded, some failed —
  the *expected common state* once there are 16 sources, not a rare edge
  case, hence its own code rather than folding into `3`), `3` total
  failure, `1` reserved for fatal init failures (DB unreachable before any
  step runs — fail fast rather than limping through 3 steps that would
  each fail identically). A cron wrapper — and later, Cloud Scheduler +
  Cloud Monitoring, once deployed — can act on `2`/`3` without koshi
  needing any notification integration built. This pragmatically resolves
  "no alerting channel decided yet" without inventing one.

### Foundational vs. deferred

**Foundational (lands before any new source is added — Phase 0):**
structured logging, `__main__.py` per-step isolation + exit codes, per-row
isolation + `parse_int_loose` in both existing parsers, `resilience.py`'s
`isolated_item()`, retry/backoff + split timeout in `crawler/fetch.py`
(every source, both tiers, goes through this at least once), seed-loader
per-entry isolation + generalization, the source-registry pattern.

**Deferred:** `Throttler` wiring (matters once a run fetches multiple URLs
— not true yet), Cloud Scheduler/Cloud Run Job/Pub/Sub dead-letter design
(confirmed nothing exists to build on in `karki-labs-infra`; correctly out
of scope until deployment), a bato-style batch-level validation gate
(`bato/ingest/build.py` + `validate.py`'s expected-count-range check) —
worth revisiting once row volumes are non-trivial, not with 6 tables — the
CDN/UA-fallback retry trick from `research/au-visa-sources/crawler.py` —
solves a problem (Akamai blocks) koshi hasn't hit against its actual
target domains.

## 8. Sequencing (confirmed: curation-effort order)

**Phase 0 — Fault-tolerance retrofit on the 2 existing sources.**
Everything in §7's foundational list, applied to `pipeline.py`,
`crawler/fetch.py`, both parsers, `seeds/loader.py`, `__main__.py`, plus
new tests (malformed-row fixtures proving one bad row doesn't kill a page;
a bad-YAML-entry test; a retry test via `httpx.MockTransport` failing N
times then succeeding). Cheapest, highest-leverage — every source added
afterward inherits this for free.

**Phase 1 — Source-registry refactor.** `source_registry.py`,
`run_source_sync()`, `seeds/loader.py` generalization,
`sources/domains.yaml`, `__main__.py` switched to iterate the registry.

**Phase 2 — New sources, in this order:**
1. `visa_subclasses` (tier 5, 6 rows) — unblocks the FK every later table needs.
2. Visa fees → `visa_subclasses.base_application_cost` (tier 2) — first update-by-PK strategy.
3. Processing times (tier 2) — cheapest pure-insert table, proves the registry end-to-end.
4. Points test criteria (tier 2).
5. English test bands (tier 2).
6. Assessing bodies + join table (tier 5) — first join-table curation, first new crawl domain.
7. Policy events (tier 5) — second new crawl domain.
8. Eligibility requirements (tier 5, gap 1).
9. Skills priority ratings (tier 2).
10. MLTSSL/STSOL/ROL + state list changes → `list_change_log`.
11. State nomination status (tier 5) — deliberately last: highest per-row curation effort of any source, attempted once the curation pattern is well-worn.
12. `program_allocation` + `application_funnel` (submitted/invited piggybacked on the existing SkillSelect fetch; `granted_count` ships `NULL` or tier-5-curated).
13. `points_distribution` — stays deferred, not scheduled.

Tiers 3/4 stay unbuilt for this whole pass per §5 — revisit only if step
10 or step 12's curation cadence genuinely proves unsustainable.

## 9. Explicitly out of scope

New API endpoints beyond the 2 already built, derived views (e.g. "current
MLTSSL membership" computed from `list_change_log`), and national/state/
visa aggregation logic. Every table above is designed to be queried by
that logic later — the query/serialization layer is a separate, later
planning round.

## 10. Open items for whoever picks up implementation

- `list_change_log`'s legislation.gov.au source needs its real HTML
  structure confirmed before committing to pure tier-2 (§5 note).
- `skills_priority_ratings`' rating vocabulary needs confirming against
  the live JSA page (§4.3, gap 2).
- The `application_funnel` dual-provenance design (§4.2) is a genuine
  schema extension beyond the original spec's single-triple convention —
  flagged, not hidden.
- The parser return-type change (`ParseResult(rows, skipped)`) touches two
  existing, already-reviewed test files (§7) — small, named explicitly.

## 11. Success criteria

Faithful to this doc if: every new table carries the provenance trio (or
is explicitly `derived`); no source needs a crawl domain that isn't in
`sources/domains.yaml`; a malformed row in any parser or seed file is
skipped and logged, never crashes the whole run; `__main__.py`'s three
(eventually sixteen) steps run independently, with a failure in one never
preventing an unrelated step from running; every network call goes through
retry/backoff with a split timeout; the run summary and exit code
correctly reflect partial vs. total vs. clean success; and — unchanged
from the existing design — no row ships without a source, no generated
string states or implies a personalized outcome, and koshi has zero
end-user-identity code anywhere.
