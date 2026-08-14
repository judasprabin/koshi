# koshi — Design Spec

**Status:** Design approved — ready for implementation planning
**Date:** 2026-08-14 (v2 — deepened data model, sourcing, and API surface)
**Author:** Prabin Karki, via brainstorming session with Claude

---

## Why this revision exists

The first version of this spec (v1, same date) named 6 tables, 5 generic source
*categories*, and 5 API endpoints. That was enough to describe the shape of
the service but not enough to build it: it didn't cover most of what the
approved mockup (`saathi/diagrams/saathi-landscape-navigator-mockup.html`)
actually renders, it cited source categories instead of real pages, and it
didn't say how the data gets saved beyond "Postgres." This revision replaces
§3–§6 with a version grounded directly in two things: every data point the
mockup's working code actually reads, and the real 19-domain page list
already defined in `research/au-visa-sources/config.yaml` (not a paraphrase
of it). Sections 1, 2, 7, 8 are unchanged from v1 — still correct, not
rewritten for the sake of it.

## 1. Why this exists

koshi is the backend half of Saathi's Visa Landscape Navigator feature, split
out into its own service. The feature was originally designed and spec'd
inside Saathi itself
(`saathi/docs/superpowers/specs/2026-08-13-visa-landscape-navigator-design.md`),
with a first implementation plan already written
(`saathi/docs/superpowers/plans/2026-08-14-visa-landscape-navigator-occupation-slice.md`).
That plan's backend tasks are the direct ancestor of this spec, reused where
they still fit.

**Why split it out:** the Landscape Navigator's data layer — occupation/visa
schema, ceiling extraction, EOI thresholds, state nomination status — is
conceptually closer to manaslu's shape (a self-contained data/extraction
pipeline with a narrow bounded context) than to thamel's other work (simple
CRUD for F1/F2/F3). Splitting it into its own service mirrors a pattern
already proven in this project: manaslu is headless, no UI, consumed over a
versioned API. koshi is exactly that shape for landscape data.

## 2. What koshi is not

- Not a personal-data service. No end-user identity, no JWT verification, no
  per-user rows anywhere. Contrast with manaslu and thamel, which *are*
  resource servers.
- Not a UI. No rendering, no templates beyond the deterministic text fields
  it returns as data.
- Not dependent on a separate crawler repo anymore. Discovery and
  change-detection (previously `research/au-visa-sources`, feeding a Notion
  registry) are absorbed into koshi as of this revision — see §5. koshi owns
  the full pipeline end to end: discover → detect change → extract →
  validate → store.
- Not an advice or eligibility service. Every response is a sourced,
  published fact — never a personalized judgment (§7).
- **Not a service that pretends every fact is equally solid.** Some of what
  the mockup shows does not have a confirmed, cleanly-scrapable public
  source. §4 says which, explicitly, rather than quietly shipping an
  approximation labeled as fact.

## 3. Data model

Cloud SQL Postgres, sharing an instance with saathi/manaslu/thamel (separate
database — the existing cost lever). SQLAlchemy 2.0 models, Alembic
migrations, snake_case tables, `_code` suffix for foreign keys into
reference tables.

**Cross-cutting provenance rule (unchanged from v1, now applied uniformly):**
every row carries `source_url`, `retrieved_at`, and a new `reliability_tier`
enum — `official_scraped` (deterministic parser against an official page),
`official_curated` (official source, but the page isn't cleanly
machine-parseable, so a human reviews and enters the value on a cadence),
`community_sourced` (a non-government source, used only where no official
one exists, always visibly labeled as such to the frontend), or `derived`
(computed from other koshi rows, not sourced externally). A check constraint
enforces `source_url IS NOT NULL` for every tier except `derived` — a
computed row cites the koshi rows it was computed from instead. No row ships
without one of these being true.

### 3.1 Reference tables (static or near-static)

- **`occupations`** — `code` (ANZSCO, PK), `name`, `unit_group`. Current
  MLTSSL/STSOL/Regional membership is a *derived view* over
  `list_change_log` (3.2), not a column here — a column would silently go
  stale; a view can't.
- **`visa_subclasses`** — `code` (PK, e.g. "189"), `name`, `family`,
  `permanence`, plus the fields the mockup's visa-comparison table actually
  needs: `age_limit`, `work_rights_description`, `family_inclusion_rule`,
  `residency_requirement_description`, `occupation_list_required` (bool),
  `onward_pathway_code` (FK to another visa_subclasses row, nullable),
  `base_application_cost`, `points_test_required` (bool).
- **`english_test_bands`** — `test_name` (IELTS / PTE Academic / TOEFL iBT /
  OET), `band_level` (e.g. Competent/Proficient/Superior), `score_requirement`,
  `points_awarded`, `cost`, `validity_period`. PK `(test_name, band_level)`.
- **`assessing_bodies`** — `body_name` (e.g. ACS, ANMAC, VETASSESS, Engineers
  Australia), `turnaround_estimate`, `cost`.
- **`occupation_assessing_bodies`** — join table, `occupation_code` ×
  `body_name` — modeled many-to-many because a handful of occupations are
  validly assessed by more than one body depending on specialization; a
  1:1 FK on `occupations` would be wrong for those rows.
- **`points_criteria_reference`** — the 12-criterion points test itself
  (age, English, skilled employment on/offshore, education, partner skills,
  etc.) as *public reference content*: `criterion_name`, `band_description`,
  `points_value`. This is the same page thamel's F2 also implements as a
  computation — deliberately duplicated, not shared by API call. thamel's
  points engine must never depend on a network call to another service
  inside a deterministic computation path; koshi's copy exists only so the
  Navigator can show "how points work" as browsable public reference
  content, independent of thamel. Both copies cite the same source page and
  must be kept in sync by hand when Home Affairs revises the test — flagged
  in §11, not hidden.

### 3.2 Core time-series tables

- **`ceiling_usage`** — `occupation_code`, `program_year`, `issued`,
  `ceiling`, `as_of_date`. Multiple rows per program year, at different
  `as_of_date` snapshots (not just a year-end total) — this is what makes
  "pace vs. last year" answerable: compare this year's row at a given
  as_of_date to last year's row at the nearest matching as_of_date. The
  comparison is computed at query time in the API layer, not stored as its
  own column.
- **`eoi_rounds`** — `visa_code`, `round_date`, `occupation_code` (nullable —
  some rounds are visa-wide, not occupation-scoped), `threshold_points`,
  `invitations_issued`.
- **`policy_events`** — `event_date`, `visa_code` (nullable if national),
  `description`, `source_url`. Feeds the 5-year trend chart's annotations
  ("program cut announced"). Explicitly editorial — see §4's note on this
  table's sourcing.
- **`state_nomination_status`** — `state_code`, `occupation_code`, `status`
  (open/limited/closed), `fee`, `points_minimum`, `job_offer_required`
  (bool), `residency_commitment_description`, `decision_time_estimate`,
  `documents_required` (jsonb array of strings — a read-only display list,
  not independently queried, so a join table would be unjustified
  normalization), `approval_pattern_note` (text, nullable), `as_of_date`.
- **`list_change_log`** — `list_name` (MLTSSL / STSOL / ROL / a state code
  like NSW), `occupation_code`, `change_type` (added/removed),
  `effective_date`. One table drives both the national list-membership view
  (3.1's derived view) and the mockup's "recently added/removed" deltas per
  state — same shape, different `list_name` values, no need for two tables.
- **`processing_times`** — `visa_code`, `as_of_date`, `median_days`.
- **`program_allocation`** — `program_year`, `stream_name` (Skill/Family/
  Other), `places`. Normalized as year × stream rows rather than fixed
  columns, so a future stream split change doesn't require a migration.
- **`application_funnel`** — `visa_code`, `program_year`, `submitted_count`,
  `invited_count`, `granted_count`, `as_of_date`. See §4 — the `granted_count`
  column is the weakest-sourced field in this table and may need to launch
  null for some visa/year combinations rather than a fabricated number.

### 3.3 Derived tables (computed inside koshi, not sourced externally)

- **`occupation_momentum`** — `occupation_code`, `computed_at`, `direction`
  (rising/falling/steady), based on the trailing 3-round threshold delta in
  `eoi_rounds`. A nightly job recomputes this; it is never scraped.

### 3.4 Deferred, not built in v1

- **`points_distribution`** (`occupation_code`, `round_date`, `band_label`,
  `applicant_pct`, `median_points`) — the histogram the mockup shows per
  occupation. Sketched here so the shape is known, but **not built in v1**:
  see §4 for why. Building this table before a real source is confirmed
  would mean shipping fabricated numbers next to real ones with no visual
  distinction — worse than not having the panel at all.

## 4. Where the data actually comes from

Every row below is a real path from `research/au-visa-sources/config.yaml`'s
19-domain crawl list, not a paraphrased category. Where a mockup data point
has no confirmed source, that's stated plainly instead of assigned one.

| Data | Real source | Format | Cadence | Reliability tier |
|---|---|---|---|---|
| EOI thresholds, invitations issued | `immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds` | HTML table, per round | ~monthly | `official_scraped` |
| Occupation ceilings, program allocation | `immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels` | Periodic report, likely PDF | Irregular, few/yr | `official_curated` — see note below |
| Visa fees (feeds `visa_subclasses.base_application_cost`) | `immi.homeaffairs.gov.au/visa-fees` | HTML table | Irregular (annual indexation) | `official_scraped` |
| Points test criteria | `immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/points-test` | HTML | Rare | `official_scraped` |
| Visa subclass static facts (189/190/491/485/500/482 pages) | Individual Home Affairs visa subclass pages (in crawl list) | HTML prose, page-specific layout | Rare | `official_curated` |
| Health/character/English requirement reference | `immi.homeaffairs.gov.au/help-support/meeting-our-requirements/{health,character,english-language}` | HTML prose | Rare | `official_curated` |
| Processing times | Home Affairs Global Visa Processing Times page (in crawl list) | HTML table | ~monthly | `official_scraped` |
| MLTSSL / STSOL / ROL list membership | `legislation.gov.au` (legislative instruments) | HTML/gazette-style | A few/yr | `official_scraped` |
| ANZSCO codes/names | `jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco` | HTML | Near-static | `official_scraped` |
| Skills priority list | `jobsandskills.gov.au/skills-priority-list` | HTML/dataset | Annual | `official_scraped` |
| State nomination status/criteria (NSW/VIC/QLD/WA/SA) | State government pages already in the crawl list | HTML, general landing pages — **not** clean per-occupation tables | Irregular | `official_curated` — see note below |
| State occupation list changes | Same state pages, via the crawler's change-detection diff | HTML | Irregular | `official_curated` |
| Assessing bodies × occupations | mara.gov.au / individual assessing-body sites | HTML | Rare | `official_curated` — **not yet in the crawler's 19-domain config; needs adding** (see §11) |
| Policy events (trend annotations) | Ministerial press releases / budget.gov.au / treasury.gov.au | HTML | Ad hoc | `official_curated`, explicitly editorial — **not yet in the crawler's 19-domain config; needs adding** (see §11) |
| Application funnel — submitted/invited | SkillSelect round-results pages (same source as EOI thresholds) | HTML table | ~monthly | `official_scraped` |
| Application funnel — granted, by pathway | Home Affairs annual report | PDF, aggregate-level | Annual | `official_curated` — pathway-level breakdown may not be published at all; launch with `granted_count = NULL` where unconfirmed rather than approximate it |
| Points distribution among invitees | **No confirmed source in any of the 19 crawled domains** | — | — | **Deferred — see §3.4.** Not built until a real source (official or a clearly-labeled community tracker) is found. |
| Occupation momentum | Computed from koshi's own `eoi_rounds` | — | Nightly | `derived` |

**Two honest notes worth not glossing over:**

1. **Ceiling data is likely a synthesis, not a lookup.** The planning-levels
   page reads as a periodic report (PDF), not a live per-occupation table.
   Getting `ceiling_usage.ceiling` per occupation may mean cross-referencing
   a published cap against SkillSelect invitation counts rather than reading
   one number off one page. That's real extraction work, not a config value
   — flagged so the implementation plan doesn't underestimate this task.
2. **State pages are landing pages, not data tables.** NSW/VIC/QLD/WA/SA
   sites in the crawler's config are general "how to apply" pages. The rich
   per-occupation detail the mockup shows (fee, points minimum, job-offer
   requirement, decision time, documents, an approval-pattern note) will
   most likely need a **human-curated seed**, reviewed against the source
   page on a cadence — the same honest move `bato` already made for its own
   seed data — rather than a deterministic parser that looks automated but
   silently breaks the moment a state redesigns its page. `official_curated`
   still requires `source_url` + `retrieved_at`; it just means a person, not
   a parser, produced the value.

## 5. Discovery, change-detection & extraction pipeline

**Architecture decision (this revision): the crawler moves into koshi.**
`research/au-visa-sources` was a separate repo, with its own config and a
Notion-based registry of pages/change-status, built for human-readable
change tracking rather than feeding a structured-extraction pipeline. That
split made adding a new domain (e.g. assessing bodies) a cross-repo
coordination problem, and made "what triggers extraction" an unclear
hand-off between two codebases. Rebuilding it inside koshi, purpose-built
for koshi's own needs, removes both problems: one repo, one datastore, one
person (or one PR) can add a domain and ship the parser for it in the same
change.

**`source_pages`** — the new crawl registry, a koshi Postgres table, replacing
Notion: `url` (unique), `domain`, `category` (the crawler's existing 18
categories, ported as-is), `content_hash`, `first_seen_at`,
`last_checked_at`, `last_changed_at`, `status` (active/removed). This is
crawler metadata, not a fact table — it doesn't carry `reliability_tier`,
because it *is* the source, not a claim sourced from something else. The
extraction pipeline reads rows where `last_changed_at > last_extracted_at`
and, for each, writes rows into the §3 fact tables citing that page's `url`
as `source_url`.

**The 19-domain config** (`immi.homeaffairs.gov.au` paths, state government
sites, legislation.gov.au, jobsandskills.gov.au, etc.) ports into koshi
directly — same domains, same settings (max_pages_per_run 300,
max_pages_per_domain 15, 1s request delay, 15s timeout) — plus the two
domains §4 flagged as missing (assessing bodies, policy-event sources),
added now that adding a domain no longer requires touching a different repo.

Five tiers of getting a fact from a page into a table:

1. **Crawl & change-detection (new, formerly external).** httpx + BeautifulSoup4
   walk the configured domains, hash each page's content, and update
   `source_pages`. Cheap, runs on a schedule, produces no facts itself — only
   the signal that something may have changed.
2. **Deterministic HTML parsers (primary extraction tier).** BeautifulSoup4 +
   lxml, one parser per known page type: SkillSelect round-results, visa
   fees, processing times, ANZSCO/skills-priority-list pages, MLTSSL
   legislative HTML where structured.
3. **PDF extraction.** `pdfplumber` for the planning-levels and annual-report
   -style publications that ceilings and `program_allocation` come from.
   Claude reads pdfplumber's extracted text/tables as a fallback when a
   report's layout doesn't parse cleanly on the first pass.
4. **Claude fallback.** Anthropic SDK, for prose pages that don't fit a
   template: visa subclass pages, health/character/English requirement
   pages, gazette-style legislative PDFs with inconsistent layout.
5. **Manual curation — the general fallback whenever a page resists tiers
   2–4, not only the two cases already named.** State nomination detail and
   assessing-body data are the known cases today, but the rule is general:
   if a real source exists and it isn't cleanly scrapable, a person enters
   the value against that source, on a review cadence (monthly is the
   working assumption — see §11), in versioned YAML/JSON seed files reviewed
   in a PR before ingestion — `bato`'s pattern, reused rather than
   reinvented. `source_url` and `retrieved_at` are still required at
   ingestion; `reliability_tier` marks it `official_curated` so the API can
   distinguish it from an automated extraction without hiding that
   distinction.

**Trigger:** a Cloud Run Job, invoked by Cloud Scheduler, runs tier 1
(crawl), then tiers 2–4 against whatever `source_pages` rows just changed.
Tier 5 (manual curation) runs on its own cadence, independent of the crawl
schedule, since the underlying pages don't usefully change that often
anyway ("updated daily" describes the check, not most of the data — see §4).

**Local dev, before any of this touches Cloud Scheduler:** the crawl job,
extraction tiers, and `source_pages`/fact tables all run against a local
Postgres (Docker Compose) and are invoked manually or via a simple script —
no Cloud Run Job, no Scheduler, until the pipeline is proven locally. See §11.

**What happens to `research/au-visa-sources`:** its config and any working
parser logic are the starting point koshi ports from, not thrown away — but
the repo itself becomes either redundant or repurposed once koshi's own
crawler is live. That's a call worth making deliberately rather than by
default; flagged as an open decision in §11, not resolved here.

**Validation gate, before any row lands in the DB:** non-empty `source_url`
(unless `reliability_tier='derived'`), a parseable `retrieved_at`, and
data-shape sanity checks (`issued <= ceiling`, dates not in the future,
`invited_count <= submitted_count` where both are present). Mirrors bato's
build-time validation gate, applied at ingestion time here since koshi's
data changes continuously.

## 6. API

REST, OpenAPI-first — the schema is the source of truth. CI publishes a
generated TypeScript client for `lukla`. One endpoint per mockup panel,
grouped by the same four sections the mockup uses:

```
# Occupation
GET /v1/occupations                          # list, sortable by momentum — backs "All Occupations" ranking
GET /v1/occupations/{code}                   # profile: name, lists, ceiling gauge, pace-vs-last-year, momentum
GET /v1/occupations/{code}/states             # per-state status for one occupation
GET /v1/occupations/{code}/points-distribution  # 501 Not Implemented until §3.4 is unblocked — see §11

# State
GET /v1/states                                # all-states summary (status/fee/decision-time) — backs the map
GET /v1/states/{code}                         # one state's summary
GET /v1/states/{code}/occupations/{occ_code}  # full nomination detail: criteria, docs, approval note
GET /v1/states/{code}/list-changes            # recently added/removed occupations

# Visa
GET /v1/visas/{code}                          # single visa's static facts
GET /v1/visas/compare?codes=189,190,491,485,500  # full comparison table, all 5 visa types
GET /v1/visas/{code}/trend                    # 5-year threshold trend + policy_events annotations

# National
GET /v1/national/summary                      # total places, stream split, invited-so-far, avg threshold change, days-to-next-round
GET /v1/national/funnel                       # application funnel by pathway

# Reference
GET /v1/reference/english-tests               # 4 tests × bands
GET /v1/reference/assessing-bodies            # bodies × occupations × turnaround × cost
GET /v1/reference/points-criteria             # 12-criterion breakdown, public reference copy

GET /v1/openapi.json
GET /v1/healthz
```

Every response includes each fact's `reliability_tier` and `retrieved_at` —
not just as an internal column, but serialized in the response, so `lukla`
can render a visibly different treatment (e.g. a muted "community-sourced"
tag) rather than presenting a curated estimate with the same confidence as a
scraped official number. This is the API-level enforcement of §4's honesty
principle — it doesn't work if the distinction dies at the database layer.

Versioned (`/v1` path), additive-only changes within a version — unchanged
from v1.

## 7. Regulatory posture (inherited, non-negotiable)

Unchanged from v1: every field and every generated string describes a
published fact — never "you should/can/are eligible/will." No scoring, no
ranking pathways as "best," no personalized prediction. "What this means"
insight text is generated by deterministic templates keyed to data
conditions, never an LLM call, with a phrase-ban test per template.

## 8. Auth & security

Unchanged from v1: no end-user identity, no JWT anywhere in this service.
Service-to-service only via Cloud Run IAM (`lukla`'s service account granted
`roles/run.invoker`). The only external API key in play is Anthropic's, used
only by the offline extraction pipeline, never the request-serving API.

## 9. Tech stack

Python 3.11+, FastAPI, SQLAlchemy 2.0 + Alembic, Postgres, pytest.
`httpx` + BeautifulSoup4 + lxml for crawling and deterministic HTML
extraction (dual-purpose — same libraries, §5 tiers 1–2), **pdfplumber for
PDF/report extraction**, Anthropic SDK for fallback extraction. No Notion
dependency (superseded by `source_pages`, §5).

**Local dev:** Postgres via Docker Compose, crawl/extraction run as scripts
or a local scheduler (e.g. `cron` or a simple loop) — no cloud dependency to
get the pipeline working end to end.

**Deploy (later, see §11 on sequencing):** Cloud Run for the API, a Cloud
Run Job (via Cloud Scheduler) for crawl + extraction, GitHub Actions + WIF
for CI/CD, Terraform in `karki-labs-infra` (not GKE, not Cloud Build).

## 10. Relationship to the existing plan

The occupation-slice plan in saathi
(`saathi/docs/superpowers/plans/2026-08-14-visa-landscape-navigator-occupation-slice.md`)
remains the reference for koshi's *first* implementation plan's shape —
scaffold → schema → seed loader → API endpoint → insight generation — but
its scope was one table and one endpoint. This spec's data model and API
surface are substantially larger; the implementation plan built from this
spec should sequence tables/endpoints into multiple vertical slices (e.g.
occupation slice first, as already planned, then state, then visa
comparison, then national/reference) rather than attempt all of §3/§6 in one
plan.

## 11. Open questions

- **Fate of `research/au-visa-sources`:** now that koshi has its own
  crawler (§5), that repo becomes either redundant or needs a narrower
  reason to keep existing (e.g. `thamel`'s F4a RAG ingestion, which the
  original thamel spec assumed would share this crawler — see below).
  Options: archive it once koshi's crawler is proven; repurpose it as
  F4a-only (page text → chunking, a different extraction purpose than
  koshi's structured facts); or keep it as a read-only historical reference
  for the config koshi ported from. Not blocking koshi's own build — but
  worth a deliberate call, not a default.
- **Consequence for `thamel`'s F4a:** thamel's design spec
  (`thamel/docs/superpowers/specs/2026-08-14-thamel-design.md` §3, F4a)
  currently assumes it ingests "the same AU Visa Source Registry crawler
  koshi also consumes." That assumption no longer holds once koshi absorbs
  and rebuilds that crawler for its own structured-extraction purpose.
  thamel will need either its own independent page-fetching for F4a's
  chunking/embedding needs, or a narrow, deliberate read of koshi's
  `source_pages` (public page metadata, not personal data — plausibly a
  smaller exception to the "koshi and thamel don't call each other" rule,
  but that's a decision for thamel's spec, not this one). Flagged here so
  it isn't silently forgotten; not resolved in this pass since the current
  focus is koshi.
- **Points-distribution histogram (§3.4):** deferred until a real source is
  found. Worth a deliberate, separate research spike (does Home Affairs
  publish this anywhere, even in an annual report appendix; is a
  community-tracker source acceptable with a visible "community-sourced"
  label) rather than silently dropping the panel from `lukla`'s build.
- **`application_funnel.granted_count` granularity:** may not be available
  per-pathway from any official source — confirm during implementation
  before committing to the column; launch with nulls where unconfirmed
  rather than approximate.
- **Manual curation review cadence:** monthly is the working assumption for
  state nomination data and assessing-body data (and now, per §5 tier 5,
  any other data type scraping turns out not to reach); not yet validated
  against how often those pages actually change in practice.
- **Points criteria duplication (§3.1):** koshi and thamel both need the 12
  points-test criteria — koshi as browsable reference, thamel as
  computation. Kept as deliberate duplication for service isolation; if this
  proves error-prone to keep in sync by hand, revisit as a shared config
  package rather than a network dependency between the two services.
- **Cloud SQL / Terraform — deliberately deferred, not a blocker.** Local
  dev runs entirely on a local Postgres (§9); Cloud SQL instance-sharing and
  the corresponding `karki-labs-infra` Terraform work happen once the local
  setup is working end to end and the schema has settled, not before. This
  is a sequencing decision, not an unresolved question — don't pull it
  forward into the implementation plan's early tasks.
- Whether the extraction validation gate should hard-fail an ingestion run
  or soft-fail with an alert — unchanged open item, no alerting channel
  decided yet.

## 12. Success criteria

Faithful to this spec if: every table in §3 exists with the fields listed
(except §3.4, deliberately deferred); crawling and change-detection run
inside koshi against its own `source_pages` registry, with no runtime
dependency on `research/au-visa-sources` or Notion; no row lacks
`source_url`/`retrieved_at` unless `reliability_tier='derived'`; every API
response serializes `reliability_tier` and `retrieved_at` per fact, not just
per endpoint; every extraction path (crawl, HTML, PDF, Claude fallback,
manual curation) has a working implementation or an explicitly deferred
status — never a silent guess presented as fact; the whole pipeline runs
against local Postgres before any Cloud SQL/Terraform work is touched; the
API in §6 is fully described by its own OpenAPI schema; no response field or
generated string states or implies a personalized outcome; and koshi has
zero end-user-identity code anywhere, on purpose.
