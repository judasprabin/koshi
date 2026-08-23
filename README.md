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
| [docs/structural-review.md](docs/structural-review.md) | Filesystem/code-organization findings and fixes — sources.py, the syncs/ split, the N+1 fix, and what's still open (docs flatten, Dockerfile) |
| [docs/superpowers/research/2026-08-16-koshi-source-urls.md](docs/superpowers/research/2026-08-16-koshi-source-urls.md) | Every cataloged data source (23), its verified URL/extraction method, and a quick-reference table of which 6 are actually built |
| [docs/superpowers/research/2026-08-16-koshi-data-model.md](docs/superpowers/research/2026-08-16-koshi-data-model.md) | Full schema reference — the 8 live tables plus the researched-but-unbuilt ones |
| [docs/superpowers/specs/2026-08-16-koshi-etl-architecture.md](docs/superpowers/specs/2026-08-16-koshi-etl-architecture.md) | The deep-dive doc: Part I is what's built (more detail than ARCHITECTURE.md), Part II is deferred reference architecture, Part III is history |
| [docs/tracking/](docs/tracking/) | Spreadsheet-friendly CSVs (sources, tables, columns) for tracking what's built vs. target — see its README for provenance and how to regenerate |

**Live execution tracker:** the design docs above are the *what and why*; [koshi's GitHub Project board](https://github.com/users/judasprabin/projects/3/) is the *what's actually in flight right now* — epics, decisions, build tickets, and their dependencies. If the two ever disagree on current state, the board wins; file an issue to fix the doc.

## Architecture

The design spec targets a larger system than what's built today (see
"What's real vs. what's specified but not built" in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#9-whats-real-vs-whats-specified-but-not-built)).
This table describes the design's full intended shape; ✅/⏳ marks what's
actually implemented right now.

| Layer | Design | Today |
|-------|--------|-------|
| Discovery & crawling | Owned by koshi — crawls its own source list, hashes pages for change-detection, stores the registry in Postgres (`source_pages`) | ✅ Built (`crawler/fetch.py`), driving 6 live sources (ANZSCO, ABS, LIN 19/051, 2 SkillSelect pages, BP0068) |
| Extraction | Tiered: deterministic HTML/table parsers, PDF parsers, LLM fallback for non-templated pages, manual curation where a real source isn't cleanly scrapable | ✅ 7 deterministic parser modules, no PDF/LLM tier built — a 2026-08-17 audit of all 23 catalogued sources found none needs one |
| Backend | FastAPI, Python 3.11+ | ✅ |
| Data | Cloud SQL Postgres (shares an instance with saathi/manaslu, separate database) | ⏳ Local Postgres only — Cloud SQL deliberately deferred, see the note just below the table |
| Auth | Cloud Run IAM invoker only — no end-user identity | ⏳ No auth at all locally (nothing to invoke yet); the "no end-user identity" part is already true and permanent |
| Deploy | Cloud Run · GitHub Actions (WIF) · Terraform in `karki-labs-infra` | ⏳ Not deployed anywhere yet — `python -m koshi` + `uvicorn` locally only |

## Local development

1. Install and start Postgres 16 — e.g. via Homebrew: `brew install postgresql@16 && brew services start postgresql@16`. (A `docker-compose.yml` is also provided if you prefer running Postgres in a container instead — either works, since both end up serving the same `postgresql+psycopg://koshi:koshi@localhost:5432/...` connection the app expects. Note `docker compose up -d` only auto-creates the `koshi` database via `POSTGRES_DB` — you still need to create `koshi_test` yourself: `docker compose exec postgres createdb -U koshi koshi_test`.)
2. Create the `koshi` role and the `koshi`/`koshi_test` databases, owned by that role, with password `koshi`.
3. `pip install -e ".[dev]"`
4. `DATABASE_URL=postgresql+psycopg://koshi:koshi@localhost:5432/koshi alembic upgrade head`
5. `DATABASE_URL=postgresql+psycopg://koshi:koshi@localhost:5432/koshi python -m koshi` — runs the full local sync end-to-end, in order: ANZSCO occupations, ABS occupations (the authoritative 1,076-code set), the name→code crosswalk (LIN 19/051 + ABS), current SkillSelect EOI rounds, historical EOI rounds (momentum needs the trailing window), BP0068 grant statistics + visa subclasses, a backfill retry for any round the crosswalk couldn't resolve yet, and finally the manually-curated `ceiling_usage` seed (currently empty by design — see `docs/API.md`). Each step is isolated: one failing step doesn't stop the rest. Without this step the API has no data to serve. Full per-step detail: `docs/superpowers/specs/2026-08-16-koshi-etl-architecture.md` §2.
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
