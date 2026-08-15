# koshi — Australian visa landscape data service

**A headless backend service: an ETL pipeline feeding a read-only API.**
koshi extracts raw government pages, transforms them into structured rows,
validates and loads them into Postgres, then serves the result as sourced
facts about the Australian skilled-migration system — occupation ceilings,
EOI invitation thresholds, state nomination status, processing times. No
UI, no end-user identity: this is a public-data API, not a personalization
service. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#2-two-runtime-shapes-one-codebase)
for exactly how the ETL stages map onto the code.

**Product boundary:** koshi describes the published state of the system. It
never scores, ranks, or predicts a personal outcome — every response is a
sourced fact, never advice. Same regulatory discipline as Saathi and manaslu,
inherited, not reinvented.

## Consumers

```
lukla (separate repo, the one Saathi frontend) ─┐
future consumers ───────────────────────────────┼──► koshi /v1 (REST) ──► sourced JSON
service-to-service auth only (Cloud Run IAM) ───┘
```

lukla also calls a sibling backend, `thamel` (F1–F4a, personal data, resource-server auth) — koshi has no relationship to thamel beyond both being called by lukla; they don't call each other.

No end-user JWT anywhere in this service — the data isn't personal, so there's
no "whose data is this" question to answer. See
[docs/superpowers/specs/](docs/superpowers/specs/) for the full design.

## Documentation

| Doc | What's in it |
|-----|--------------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Component diagrams, data model (ER diagram), the extraction-watermark design, what's real vs. spec-only |
| [docs/API.md](docs/API.md) | Every endpoint, request/response examples, the `SourcedFact`/`DerivedFact` contract |
| [docs/data-sources.md](docs/data-sources.md) | Every data source koshi's design targets, which ones have real extraction code today, and which remain spec-only |
| [docs/superpowers/specs/](docs/superpowers/specs/) | The original design spec (full intended scope — broader than what's built) |

## Architecture

The design spec targets a larger system than what's built today (see
"What's real vs. what's specified but not built" in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#9-whats-real-vs-whats-specified-but-not-built)).
This table describes the design's full intended shape; ✅/⏳ marks what's
actually implemented right now.

| Layer | Design | Today |
|-------|--------|-------|
| Discovery & crawling | Owned by koshi — crawls its own source list, hashes pages for change-detection, stores the registry in Postgres (`source_pages`) | ✅ Built (`crawler/fetch.py`), pointed at 2 real pages so far |
| Extraction | Tiered: deterministic HTML/table parsers, PDF parsers, Claude fallback for non-templated pages, manual curation where a real source isn't cleanly scrapable | ✅ Deterministic parsers + manual curation. ⏳ PDF and Claude-fallback tiers not built (not yet needed) |
| Backend | FastAPI, Python 3.11+ | ✅ |
| Data | Cloud SQL Postgres (shares an instance with saathi/manaslu, separate database) | ⏳ Local Postgres only — Cloud SQL deliberately deferred, see the note just below the table |
| Auth | Cloud Run IAM invoker only — no end-user identity | ⏳ No auth at all locally (nothing to invoke yet); the "no end-user identity" part is already true and permanent |
| Deploy | Cloud Run · GitHub Actions (WIF) · Terraform in `karki-labs-infra` | ⏳ Not deployed anywhere yet — `python -m koshi` + `uvicorn` locally only |

## Local development

1. Install and start Postgres 16 — e.g. via Homebrew: `brew install postgresql@16 && brew services start postgresql@16`. (A `docker-compose.yml` is also provided if you prefer running Postgres in a container instead — either works, since both end up serving the same `postgresql+psycopg://koshi:koshi@localhost:5432/...` connection the app expects. Note `docker compose up -d` only auto-creates the `koshi` database via `POSTGRES_DB` — you still need to create `koshi_test` yourself: `docker compose exec postgres createdb -U koshi koshi_test`.)
2. Create the `koshi` role and the `koshi`/`koshi_test` databases, owned by that role, with password `koshi`.
3. `pip install -e ".[dev]"`
4. `DATABASE_URL=postgresql+psycopg://koshi:koshi@localhost:5432/koshi alembic upgrade head`
5. `DATABASE_URL=postgresql+psycopg://koshi:koshi@localhost:5432/koshi python -m koshi` — runs the full local sync end-to-end: crawls/parses ANZSCO occupations, crawls/parses SkillSelect EOI rounds (refreshing occupation momentum for every occupation a new round touches), then seeds the manually-curated `ceiling_usage` data. Without this step the API has no data to serve.
6. `pytest` — runs against `koshi_test` (see `tests/conftest.py`)
7. `uvicorn koshi.main:app --reload` — serves the API at `http://localhost:8000/v1`, docs at `/v1/docs`

No Cloud SQL, no Terraform, no Cloud Run needed for local development — see the design spec §9/§11 for why that's deliberate, not a shortcut.

### Try it

```bash
curl http://localhost:8000/v1/occupations
curl http://localhost:8000/v1/occupations/261313   # Software Engineer, if step 5 above has run
```

Full endpoint reference with example responses: [docs/API.md](docs/API.md).

## Related repos

- `lukla` — the one Saathi frontend; calls this API for the Landscape Navigator (and calls `thamel` for everything else).
- `thamel` — sibling headless service, different domain (personal data: tracker/calculator/checklist/explainer, resource-server auth) — not called by koshi, both called by lukla.
- `manaslu` — sibling headless service, different domain (personal document scan/fill) — reached only via thamel's BFF, not by koshi.
- `saathi` — docs/specs/research only, no code; the original Landscape Navigator design and mockup this service implements.
- `research/au-visa-sources` — the crawler koshi's own discovery/change-detection was rebuilt from (see design spec §5); its own ongoing role is an open question there, not yet decided.
- `karki-labs-infra` — Terraform, GCP projects (deliberately not needed until koshi's local setup is working — see design spec §11).
