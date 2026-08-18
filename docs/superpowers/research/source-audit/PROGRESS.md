# Source-audit pipeline — progress tracker

**Purpose:** survives context compaction. If you're picking this up cold,
read this file first, then `agent1-page-audit.md`.

**Goal (user's request, 2026-08-17):** run 3 agents in sequence to find all
reliable data sources, map them to koshi's schema, and find missing
data/sources.

1. **Agent 1** — browse every source URL; for each page determine data
   served, page type, retrieval method, volume, cadence signals.
2. **Agent 2** — read koshi's design/data model, link each schema table to a
   page/URL, flag incomplete/missing data, run integrity + relationship checks.
3. **Agent 3** — search online for anything still missing; for anything
   found, repeat steps 1 and 2 on it.

## Status

| Agent | Status | Output |
|---|---|---|
| 1 — page audit | ✅ **COMPLETE** | `agent1-page-audit.md` (708 lines, 16/16 sources, ~30 URLs) |
| 2 — schema mapping + integrity | ✅ **COMPLETE** | `agent2-schema-mapping.md` (1292 lines, 18 tables, I1–I24, F1–F12, G1–G16) |
| 3 — gap-filling search | ✅ **COMPLETE** | `agent3-gap-search.md` (1452 lines; 9 FOUND / 5 PARTIAL / 2 NOT PUBLISHED / 0 unreached) |
| Consolidation | ✅ **COMPLETE** | **`CONSOLIDATED-FINDINGS.md` — read this first** |

**Pipeline finished 2026-08-17.** Start at `CONSOLIDATED-FINDINGS.md`; the three
agent files are the evidence of record behind it. Still pending as *code*
changes (not yet applied): D1 delete the fabricated `ceiling_usage` seed rows,
the two parser fixes, and the D2/D5 schema migrations.

## Agent 1's headline findings (detail in `agent1-page-audit.md`)

1. **Root cause of the two proven-broken parsers found.**
   `immi.homeaffairs.gov.au` pages (sources 2,3,4,5,6,7,8,16) contain **zero
   `<table>` tags** in raw HTML. Content is server-rendered but shipped as
   HTML-entity-encoded JSON inside a hidden input:
   `<input id="ctl00_PlaceHolderMain_PageSchemaHiddenField_Input">`.
   Verified decode recipe: `html.unescape` → `json.loads` → `content[].block`.
   This directly unblocks fixing sources 1 and 2.
2. **Source 5's catalogued URL is wrong.** `/points-tested` genuinely has no
   points table; the real table is at sibling URL **`/points-table`**, plain
   static HTML via the same decode technique. **No Playwright needed** —
   refutes the earlier "JS-rendered SPA" assumption.
3. **Two live hidden JSON APIs found** (better than catalog assumed — direct
   JSON, no HTML parsing):
   - Visa fees: `POST /_layouts/15/api/data.aspx/GetPriceList` (150 records)
   - Processing times: `GetProcessGuideVisas` / `GetProcessGuideInfo`
     (76 subclass×stream combos). **Returns a percentile distribution, not a
     single "median"** — schema implication for `processing_times.median_days`.
4. **Source 3 correction:** catalog claims planning levels are PDF-only
   (Tier 5). False — zero PDFs on the page; full 3-year table is static and
   Tier-2 extractable.
5. **Sources 9 + 13 resolved together.** LIN 19/051's real content is one
   iframe-hop away at a static epub HTML doc with 12 tables (no id/class —
   positional access only): **Table 5 (504 rows)** = occupation→assessing-
   authority join; **Table 6 (38 rows)** = body-name key. Confirms
   **MARA is the wrong source** for `assessing_bodies` and supplies the
   correct replacement data.

Also: **`budget.gov.au/content/migration.htm` is now a soft-404** (HTTP 200
with "Page not found" body) after the 2026-27 budget site restructure — dead
link in the catalog. **ANZSCO is being actively retired by JSA in favour of
"OSCA"** (sitewide banner on source 1's own page) — a strategic issue for the
`occupations` table, not just a parser detail. **SA's state occupation list is
legitimately empty** (program between intake rounds, not a scraper bug).
**VIC (`liveinmelbourne.vic.gov.au`) remains Cloudflare-blocked** — still
unverified.

## Key input documents

- `docs/superpowers/research/2026-08-16-koshi-source-urls.md` — 16-source URL catalog (Agent 1 corrects several entries)
- `docs/superpowers/research/2026-08-16-koshi-data-model.md` — 29 entities (6 control-plane, 5 data-plane, 18 domain-fact)
- `docs/superpowers/specs/2026-08-16-koshi-etl-architecture.md` — canonical target architecture
- `docs/ARCHITECTURE.md` — what is *actually built* today (5 tables, 2 broken parsers)

## Standing constraints for all agents in this pipeline

- Read-only on the repo except each agent's own output file under
  `docs/superpowers/research/source-audit/`.
- Never invent a selector, table structure, URL, or field. Unverifiable →
  write `UNVERIFIED — [specific reason]`. Honest gaps are the deliverable.
- No Skill tool, no sub-agent spawning.
- Government sites: sequential fetches, back off on 429/block rather than
  retrying aggressively.
