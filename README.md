# koshi — Australian visa landscape data service

**A headless backend service.** koshi extracts, stores, and serves structured,
sourced facts about the Australian skilled-migration system — occupation
ceilings, EOI invitation thresholds, state nomination status, processing
times. No UI, no end-user identity: this is a public-data API, not a
personalization service.

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

## Architecture

| Layer | Choice |
|-------|--------|
| Extraction | Tiered: deterministic HTML/table parsers first, Claude fallback for non-templated pages |
| Data source signal | Consumes change-detection from `research/au-visa-sources`' crawler — koshi parses, the crawler discovers |
| Backend | FastAPI, Python 3.11+ |
| Data | Cloud SQL Postgres (shares an instance with saathi/manaslu, separate database) |
| Auth | Cloud Run IAM invoker only — no end-user identity |
| Deploy | Cloud Run · GitHub Actions (WIF) · Terraform in `karki-labs-infra` |

## Related repos

- `lukla` — the one Saathi frontend; calls this API for the Landscape Navigator (and calls `thamel` for everything else).
- `thamel` — sibling headless service, different domain (personal data: tracker/calculator/checklist/explainer, resource-server auth) — not called by koshi, both called by lukla.
- `manaslu` — sibling headless service, different domain (personal document scan/fill) — reached only via thamel's BFF, not by koshi.
- `saathi` — docs/specs/research only, no code; the original Landscape Navigator design and mockup this service implements.
- `research/au-visa-sources` — the crawler koshi's extraction pipeline reacts to.
- `karki-labs-infra` — Terraform, GCP projects.
