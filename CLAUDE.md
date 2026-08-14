# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Repo state

Design-only as of 2026-08-14 — no application code yet. The source of truth is
`docs/superpowers/specs/2026-08-14-koshi-design.md`; read it before making
architectural decisions or writing code. An implementation plan
(`docs/superpowers/plans/`) follows once the spec is reviewed and approved —
check whether one exists before improvising.

## What koshi is

A headless backend service: extracts, stores, and serves structured, sourced
facts about the Australian skilled-migration system (occupation ceilings, EOI
thresholds, state nomination status, processing times). No UI. No end-user
identity — the data is public, so there's no per-user concept anywhere in this
service (contrast with `manaslu`, a sibling headless service that *does* need
end-user identity because it processes personal documents).

Origin: split out of Saathi's "Visa Landscape Navigator" feature
(`saathi/docs/superpowers/specs/2026-08-13-visa-landscape-navigator-design.md`)
into its own microservice, mirroring manaslu's proven headless-service pattern,
once the feature's scope was judged distinct enough from Saathi's other
backend work (F1–F3 CRUD, F4a RAG) to warrant its own bounded context. That
other backend work subsequently moved out too, into `thamel` — saathi itself
now holds no code at all, just docs/specs/research.

## Non-negotiable regulatory posture (inherited from Saathi)

Every response describes published facts only — never "you should/can/are
eligible/will." No scoring, no ranking as "best," no personalized prediction.
This is the same discipline manaslu and bato both hold; do not relax it here.

## Related repos

- `lukla` — the one Saathi frontend; consumes koshi's API for the Landscape Navigator (separate repo, separate deploy).
- `thamel` — sibling headless service, different domain (F1–F4a: personal tracker/calculator/checklist/explainer data, resource-server auth) — not called by koshi, both called by lukla.
- `manaslu` — sibling headless service, different domain (personal document scan/fill) — reached only via thamel's BFF.
- `saathi` — docs/specs/research only, no code; owns the original Landscape Navigator design and mockup this service implements.
- `research/au-visa-sources` — the crawler koshi's own discovery + change-detection pipeline was rebuilt from as of the 2026-08-14 spec revision (§5); koshi no longer has a runtime dependency on this repo or its Notion registry. That repo's ongoing purpose (archive / repurpose for thamel's F4a ingestion / historical reference) is an open question, not koshi's to decide alone.
- `karki-labs-infra` — Terraform, GCP projects, shared CI/CD pattern (GitHub Actions + WIF, Cloud Run — not GKE, not Cloud Build; see that repo's `infra/` docs if tempted to reach for either). Deliberately not touched until koshi's local setup is working end to end (spec §11) — don't reach for Terraform early.
