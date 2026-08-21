# koshi — API Reference

**Status:** Reflects the endpoints actually implemented (occupation slice).
**Base URL (local):** `http://localhost:8000` · **Base URL (prod):** not deployed yet.
**Auth:** None locally. Production design (not deployed) is Cloud Run IAM
invoker only — no end-user token, ever (see `docs/ARCHITECTURE.md` §6).

All routes are versioned under `/v1`. Full machine-readable schema is
always available at `/v1/openapi.json`; interactive docs (Swagger UI) at
`/v1/docs` while the server is running.

## Reading every response: `SourcedFact` and `DerivedFact`

Every fact in every response carries its own provenance — not just a value.
There are two shapes, and knowing which one you're looking at tells you how
the number was obtained:

```jsonc
// SourcedFact — scraped or hand-curated from a real external page
{
  "value": 3200,
  "reliability_tier": "official_curated",   // or "official_scraped"
  "retrieved_at": "2026-08-01T00:00:00+00:00",
  "source_url": "https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels"
}
```

```jsonc
// DerivedFact — computed by koshi itself from its own stored rows
{
  "value": "rising",
  "reliability_tier": "derived",
  "computed_at": "2026-08-15T09:12:03+00:00"
  // no source_url — there isn't one, it's not scraped from anywhere
}
```

`reliability_tier` is always one of `official_scraped` (deterministic
parser against a live page), `official_curated` (hand-entered against a
cited source, because the real page resists clean parsing), or `derived`
(computed from koshi's own data). Treat `official_curated` and `derived`
facts as real but lower-confidence than `official_scraped` — that's the
whole point of shipping the tier, so a frontend can render them
differently rather than presenting every number with equal confidence.

## `GET /v1/healthz`

Liveness check. No parameters, no auth.

```bash
curl http://localhost:8000/v1/healthz
```

```json
{"status": "ok"}
```

## `GET /v1/occupations`

List every occupation koshi knows about, with its current momentum.

**Query parameters**

| Param | Values | Default | Behavior |
|---|---|---|---|
| `sort` | `code`, `momentum` | `code` | `momentum` orders rising → steady → falling → unknown. Any other value returns `422` (it's a typed `Literal`, not a free string). |

```bash
curl "http://localhost:8000/v1/occupations?sort=momentum"
```

```json
[
  {"code": "261313", "name": "Software Engineer", "momentum": "rising"},
  {"code": "254499", "name": "Registered Nurse (Aged Care)", "momentum": "falling"}
]
```

Note: `momentum` here is a bare string, not a full `DerivedFact` — the list
view trades full provenance detail for compactness. Use the detail endpoint
below for the fully-sourced version of the same fact.

## `GET /v1/occupations/{code}`

The full profile for one occupation, `code` being its ANZSCO code (e.g.
`261313`).

```bash
curl http://localhost:8000/v1/occupations/261313
```

```json
{
  "code": "261313",
  "name": "Software Engineer",
  "unit_group": "2613 Software and Applications Programmers",
  "ceiling_issued": {
    "value": 3200,
    "reliability_tier": "official_curated",
    "retrieved_at": "2026-08-01T00:00:00+00:00",
    "source_url": "https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels"
  },
  "ceiling_cap": {
    "value": 5000,
    "reliability_tier": "official_curated",
    "retrieved_at": "2026-08-01T00:00:00+00:00",
    "source_url": "https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels"
  },
  "places_left": 1800,
  "latest_threshold": {
    "value": 85,
    "reliability_tier": "official_scraped",
    "retrieved_at": "2026-07-25T00:00:00+00:00",
    "source_url": "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds"
  },
  "momentum": {
    "value": "rising",
    "reliability_tier": "derived",
    "computed_at": "2026-08-15T09:12:03+00:00"
  },
  "insight": "64% of this occupation's ceiling has been issued this program year (3200 of 5000), leaving 1800 places. The points threshold has been rising over the last three rounds."
}
```

**Every field except `code`/`name`/`unit_group` can be `null`** — this is
intentional, not a bug to work around on the frontend:

| Field is `null` when… | Because… |
|---|---|
| `ceiling_issued`, `ceiling_cap`, `places_left`, `insight` | No `ceiling_usage` row exists yet for this occupation (data gap, not an error — the occupation itself was found). |
| `latest_threshold` | No `eoi_rounds` row exists yet for this occupation. |
| `momentum` | Fewer than 3 `eoi_rounds` rows exist for this occupation — momentum needs a real trailing-3-round trend, and koshi will never fabricate one. |

**Right now, `ceiling_issued`/`ceiling_cap`/`places_left`/`insight` are
`null` for every occupation.** The example above shows the shape the fields
take when populated, but the seed file that would populate them
(`seeds/ceiling_usage_manual.yaml`) is currently empty by design — per-occupation
ceilings aren't published anywhere at koshi's grain (an earlier seed cited a
page that didn't actually contain the numbers; it was removed rather than
left mis-sourced). Don't build a frontend that assumes these fields are
routinely populated.

**Error response — unknown occupation code:**

```bash
curl -i http://localhost:8000/v1/occupations/999999
```

```
HTTP/1.1 404 Not Found
{"detail": "unknown occupation code '999999'"}
```

404 is reserved strictly for "this code doesn't exist at all." A known
occupation with missing ceiling/threshold/momentum data is a `200` with
nulls, never a 404 — see `docs/ARCHITECTURE.md` for why that distinction
matters.

## What's not here yet

State nomination status, visa comparison, national summary/funnel/trend,
and the English-test/assessing-body reference tables are all specified in
the design spec but not built — separate future plans, each its own
vertical slice (design spec §10). Don't expect `/v1/states/*`, `/v1/visas/*`,
or `/v1/national/*` to exist yet.

## Populating data to query against

The endpoints above only return something once ingestion has actually run.
Locally: `alembic upgrade head` then `python -m koshi` (see `README.md`).
There is no seed data shipped pre-loaded into a fresh database — koshi
crawls and parses the real government pages, plus loads the one manually
curated seed file, every time you run it.
