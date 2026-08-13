# koshi — Design Spec

**Status:** Design approved — ready for implementation planning
**Date:** 2026-08-14
**Author:** Prabin Karki, via brainstorming session with Claude

---

## 1. Why this exists

koshi is the backend half of Saathi's Visa Landscape Navigator feature, split out into its own service. The feature was originally designed and spec'd inside Saathi itself (`saathi/docs/superpowers/specs/2026-08-13-visa-landscape-navigator-design.md`), with a first implementation plan already written (`saathi/docs/superpowers/plans/2026-08-14-visa-landscape-navigator-occupation-slice.md`). That plan's backend tasks (schema, seed loader, API endpoint, insight generation) are the direct ancestor of this spec — reused, not rewritten from scratch, except where the split itself changes something (auth model, deployment, data-sourcing detail).

**Why split it out:** the Landscape Navigator's data layer — occupation/visa schema, ceiling extraction, EOI thresholds, state nomination status — is conceptually closer to manaslu's shape (a self-contained data/extraction pipeline with a narrow bounded context) than to saathi-api's other work (simple CRUD for F1/F2/F3). Splitting it into its own service mirrors a pattern already proven in this project: manaslu is headless, no UI, consumed by Saathi's frontend over a versioned API. koshi is exactly that shape for landscape data.

## 2. What koshi is not

- Not a personal-data service. No end-user identity, no JWT verification, no per-user rows anywhere. Contrast with manaslu, which *is* a resource server because it processes personal documents.
- Not a UI. No rendering, no templates beyond the deterministic text fields it returns as data.
- Not the crawler. `research/au-visa-sources` still owns page discovery and change detection; koshi consumes that signal and does the structured extraction.
- Not an advice or eligibility service. Every response is a sourced, published fact — never a personalized judgment (inherited regulatory posture, non-negotiable — see §7).

## 3. Data model

Six tables, Cloud SQL Postgres, sharing an instance with saathi/manaslu (separate database — the cost lever already established during the earlier infra cleanup, not a new decision):

- **`occupations`** — `code` (ANZSCO, PK), `name`, `lists` (MLTSSL/STSOL/Regional membership).
- **`visa_subclasses`** — `code` (PK, e.g. "189"), `name`, `family`, `permanence` (temporary/provisional/permanent).
- **`ceiling_usage`** — occupation × program-year time-series: `issued`, `ceiling`, `as_of_date`.
- **`eoi_rounds`** — visa × round-date: `threshold` (points), optionally occupation-scoped.
- **`state_nomination_status`** — state × occupation: `status` (open/limited/closed), `fee`, `decision_time_estimate`.
- **`processing_times`** — visa × as-of-date: `median_days`.

Every row carries `source_url` + `retrieved_at` — provenance is enforced at the schema level (`NOT NULL`), matching manaslu's and bato's discipline. No row without a source ships.

## 4. Where the data comes from, and an honest freshness note

| Data | Source | Real-world update cadence |
|---|---|---|
| EOI thresholds | SkillSelect invitation round results | ~monthly, after each round |
| Occupation ceilings | Home Affairs Migration Program planning levels / SkillSelect ceiling reports | Irregular — a few times a year, not daily |
| State nomination lists/status | Individual state government sites (NSW/VIC/QLD/WA/SA — already in the crawler's 19-domain list) | Irregular, state-specific |
| Processing times | Home Affairs Global Visa Processing Times page | ~monthly |
| Occupation list membership (MLTSSL/STSOL/ROL) | Home Affairs published lists | A few times a year (legislative instrument updates) |
| ANZSCO codes/names | ABS classification | Near-static, multi-year cycle |

"Updated daily" describes the *check*, not most of the underlying *data* — the crawler polls daily, but most sources themselves change monthly or less. koshi's extraction job should trigger off "the crawler flagged this page as changed," not blindly re-parse everything on a fixed schedule.

## 5. Extraction pipeline

Tiered, matching manaslu's own extraction discipline (`manaslu/docs/architecture/02-scan-extraction.md`):

1. **Deterministic parsers, primary tier.** BeautifulSoup4 + lxml table/structure parsers, one per known page type (SkillSelect round-results page, occupation ceiling page, a given state's nomination list page). These are government data tables — usually consistently structured within a page type, which is exactly the condition deterministic parsing handles well and cheaply.
2. **Claude fallback, secondary tier.** Only for pages that don't fit a known template. Same Anthropic SDK pattern as the rest of this project family.
3. **Trigger:** a Cloud Run Job, invoked by Cloud Scheduler, that reads the crawler's change-detection output and re-parses only what changed. Same operational shape as `saathi-knowledge`'s planned ingestion job — not a new deployment pattern to invent.
4. **Validation gate:** before any row lands in the DB, it must have a non-empty `source_url`, a parseable `retrieved_at`, and pass basic sanity checks (e.g. `issued <= ceiling`, dates not in the future) — mirrors bato's build-time validation gate, applied at ingestion time here since koshi's data changes continuously rather than being a one-time build artifact.

## 6. API

REST, OpenAPI-first — the schema is the source of truth, same discipline as manaslu (`manaslu/docs/architecture/06-service-api.md`). CI publishes a generated TypeScript client for `lukla` to consume, so the frontend never hand-writes types against this API.

```
GET /v1/occupations/{code}
GET /v1/occupations/{code}/states           # per-state status for one occupation
GET /v1/visas/compare?codes=189,491
GET /v1/national/summary                    # funnel, 5-year trend, occupation ranking
GET /v1/openapi.json
GET /v1/healthz
```

Versioned (`/v1` path), additive-only changes within a version — same rule as manaslu's API contract.

## 7. Regulatory posture (inherited, non-negotiable)

Every field and every generated string describes a published fact — never "you should/can/are eligible/will." No scoring, no ranking pathways as "best," no personalized prediction. "What this means" insight text (design spec precedent: `saathi`'s §6.1/§9.5, bato's `ingest/cards.py`) is generated by deterministic templates keyed to data conditions, never an LLM call, and every template has a phrase-ban test asserting the banned phrases never appear.

## 8. Auth & security

- **No end-user identity.** The data is public and identical for every caller asking about the same occupation — there is no "whose data" question, so there is nothing to verify a JWT against.
- **Service-to-service only:** Cloud Run IAM. koshi is not publicly invokable; only `lukla`'s service account (and, later, any other legitimate consumer) is granted `roles/run.invoker`.
- **No secrets in the response path** — the only external API key in play is Anthropic's, used only by the extraction pipeline (offline job), never by the request-serving API.

## 9. Tech stack

Python 3.11+, FastAPI, SQLAlchemy 2.0 + Alembic, Cloud SQL Postgres, pytest. BeautifulSoup4 + lxml for deterministic extraction; Anthropic SDK for fallback extraction. Deploy: Cloud Run for the API, a Cloud Run Job (via Cloud Scheduler) for extraction, GitHub Actions + WIF for CI/CD, Terraform in `karki-labs-infra` — all matching the pattern already corrected and established for saathi/manaslu (not GKE, not Cloud Build; see `karki-labs-infra/infra/README.md`'s "Decision: Cloud Run, not GKE" if tempted to reconsider).

## 10. Relationship to the existing Saathi plan

The occupation-slice implementation plan already written in saathi
(`saathi/docs/superpowers/plans/2026-08-14-visa-landscape-navigator-occupation-slice.md`)
is the direct backend reference for this repo's first implementation plan — its Tasks 1–5 (project scaffold, schema, seed loader, API endpoint, insight generation) describe almost exactly what koshi's first plan should build, adjusted for: no `get_db`-style personal-session dependency (no end-user auth here), and deployment/CI targeting this repo instead of saathi's. Reuse that plan's code and test patterns rather than redesigning them.

## 11. Open questions

- Exact Cloud SQL instance-sharing mechanics (same instance as saathi/manaslu, separate DB — needs a `karki-labs-infra` Terraform task, not yet written).
- Which state government sites get parsers first — NSW/VIC likely first (largest occupation lists), the rest as a "growing the dataset" follow-on, matching bato's own README pattern for growing its seed set incrementally.
- Whether the extraction validation gate should hard-fail an ingestion run on a sanity-check violation (safer, but a bad government-side page format could silently stall an update) or soft-fail with an alert (needs an alerting channel decision, not made yet).

## 12. Success criteria

The build is faithful to this spec if: no row in any table lacks `source_url`/`retrieved_at`; every extraction has a working deterministic parser or an explicit, tested LLM-fallback path — never a silent guess; the API is fully described by its own OpenAPI schema; no response field or generated string states or implies a personalized outcome; and koshi has zero end-user-identity code anywhere, on purpose.
