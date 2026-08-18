# Source audit — consolidated findings

**Date:** 2026-08-17
**Inputs:** `agent1-page-audit.md` (708 lines) · `agent2-schema-mapping.md`
(1,292 lines) · `agent3-gap-search.md` (1,452 lines)

This is the decision-ready summary of the three-agent audit. The agent files
remain the evidence of record; this file states what changed and what to do.

---

## What the audit established

koshi's data model was designed against assumptions about what the source
pages contain. The audit fetched those pages. The two disagree in ways that
explain the failing live run and that require schema changes, not just
parser fixes.

| Agent | Scope | Result |
|---|---|---|
| 1 — page audit | 16/16 catalogued sources, ~30 URLs actually fetched | Root-caused both broken parsers; corrected 4 catalog entries; found 2 undocumented JSON APIs |
| 2 — schema mapping | 18 domain tables, column-level | 24 integrity findings (3 blocker / 13 major / 8 minor); 12 forced schema changes; 18 orphan sources |
| 3 — gap search | 16 gaps from Agent 2 | 9 FOUND · 5 PARTIAL · 2 NOT PUBLISHED · **0 unreached** |

---

## Independently verified

I re-checked the load-bearing claims rather than trusting the reports. All
held:

| Claim | Check | Result |
|---|---|---|
| Home Affairs pages carry no `<table>` markup | Fetched `previous-rounds` | **0** `<table>` tags; hidden input present |
| `previous-rounds` uses root key `criteria`, not `content` | Decoded the hidden input | Confirmed — `['criteria']` |
| SkillSelect parser unpacks 3 cells from a 2-column table | Read `skillselect_rounds.py:49` | Confirmed |
| `ceiling_usage` seed cites a page without ceilings | Read seed + Agent 1 decode | Confirmed |
| `/skillselect/occupation-ceilings` is dead | `curl -I` | **HTTP 404** |
| BP0068 exists, CC-BY, 5,237,461 bytes | CKAN `package_show` | Exact byte match; CC-BY 2.5 |

---

## Decisions needed

### D1. `ceiling_usage` — remove the fabricated rows *(urgent, independent of everything else)*

`src/koshi/seeds/ceiling_usage_manual.yaml` holds two rows with round-number
values (3200/5000, 1800/4000) citing
`immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels`. Agent 1
decoded that page in full: it contains a visa-category table only, no
occupation ceilings. The file's own header comment calls the page "a periodic
PDF"; Agent 1 found zero PDFs there. Agent 3 then confirmed ceilings are **not
routinely published at all** — `/skillselect/occupation-ceilings` is a 404 and
data.gov.au has no SkillSelect dataset.

These rows pass `require_provenance` because the fields are non-null, while the
citation is false. That is the exact failure mode koshi's provenance rules
exist to prevent, and it is currently shipping.

**Options:**
- **(a) Delete the rows and retire the table** — recommended for now. Ceilings
  are unavailable at koshi's 6-digit grain.
- **(b) Re-source at reduced fidelity** — the only real ceiling table Agent 3
  found is inside an FOI release (`fa-260100545`), as **scanned images** at
  **4-digit unit-group** grain. Tier 5, manual, low confidence.
- Note: the FOI's `issued`-looking column is *prior-year grants in other
  subclasses*, so it must **not** be mapped to `ceiling_usage.issued`. A genuine
  issued-to-date can be derived from BP0068 instead (D4).

### D2. Occupation codes are not one key space

`occupations.code` is a single-width PK anchoring 7 FKs, but the real sources
disagree on both **width** and **edition**:

- **Width:** NSW joins at 4-digit unit groups; QLD and LIN 19/051 at 6-digit;
  JSA mixes both; the FOI ceilings are 4-digit.
- **Edition — three are simultaneously live:** `F2024L01616` pins migration to
  ANZSCO **2013**; the CSOL in `F2024L01618` is coded on **2022**; LIN 19/051
  is on **2013** (25 of its codes are absent from 2022). Separately, JSA is
  retiring ANZSCO for **OSCA**.

**Recommendation:** keep ANZSCO as the PK (the binding instrument and state
lists are ANZSCO-coded), add an explicit `anzsco_edition` column, make the code
grain explicit, and carry the ABS ANZSCO↔OSCA correspondence table (found,
G4) as a crosswalk rather than migrating.

### D3. The name→code crosswalk (unblocks the Occupation vertical)

SkillSelect publishes occupation **names**, never codes. Agent 3 measured
coverage rather than assuming it: ABS ANZSCO Table 6 (1,425 pairs) resolves
132/140 live names; LIN 19/051 Table 5 (504 pairs) also resolves 132/140; the
**union resolves 140/140**.

Two hazards it found by measurement:
- 8 names are LIN-only.
- **3 titles — Management Consultant, Plumber (General), Statistician — map to
  *different codes* in the two sources.** Lookup must therefore be
  **LIN-first**, not ABS-first.

### D4. Adopt BP0068 as a source *(largest single addition)*

`data.gov.au/data/dataset/permanent-migration-program-skilled-family` —
Home Affairs-published, CC-BY 2.5, annual: **622,425 records, 10 program years,
62 subclasses, 764 ANZSCO-coded occupations**. Resolves `granted_count`
(which Agent 2 expected to ship NULL), supplies the honest `issued` column for
D1, and adds a 5-level visa taxonomy for `visa_subclasses`.

**Retrieval caveat:** the data is in the workbook's **pivot cache**, not its
worksheets — pandas/openpyxl return nothing useful. Agent 3 verified a stdlib
reader parses all records in ~4.8s.

Agent 3 found this by following a citation inside the FOI PDF; three CKAN
searches had missed it.

### D5. `processing_times` cannot keep its current shape

The live API returns a **percentile distribution**, not a median, and the
**stream dimension is missing everywhere** — which breaks the table's unique
constraint outright, since 485/500/482/186 are multi-stream. Stream also makes
`base_application_cost` ambiguous.

---

## Status — what has been actioned since this audit

| Item | State |
|---|---|
| **D1** delete fabricated `ceiling_usage` rows | ✅ done — seed file now comment-only |
| Three docs revised | ✅ done — source catalog, data model, ETL architecture |
| **Both parsers fixed** | ✅ done — SkillSelect **0 → 140 rows**; ANZSCO now reads the card grid and follows all 103 pages |
| Shared hidden-field decoder | ✅ done — `koshi.extraction.homeaffairs`, unblocks 9 sources |
| Structural assertions (§11.5) | ◐ partial — shape/row-floor/root-key assertions live in the parsers; soft-404 helper written but not yet wired into the fetcher |
| Migrations | ✅ `0007` `eoi_rounds.occupation_name_raw` · `0008` `occupations.code_grain` |
| **D3** name→code crosswalk | ✅ done — LIN-first, **139/140** rounds resolved live |
| `occupations` re-sourced to ABS | ✅ done — JSA's browse UI carried 878 of 1,076 occupations; ABS Table 5 is authoritative |
| **D2/D5** edition + stream migrations | ⬜ not started |
| **D4** BP0068 ingestion | ⬜ not started |

**Verified live 2026-08-18:** `python -m koshi` exits 0 with 1,480 occupations,
1,929 crosswalk entries and 140 rounds, and `GET /v1/occupations/253518`
returns a real 100-point threshold carrying `official_scraped` provenance —
koshi's first genuine end-to-end government data.

**Two known gaps at this state:**

1. **Momentum still shows null**, but no longer for a schema reason: it needs
   three rounds per occupation and only one round is published on the current
   page. Backfilling from the `previous-rounds` source (catalog source 17,
   19 rounds) is what closes it.
2. **One occupation does not resolve** — Cabinetmaker (394111), carried by
   LIN 19/051 under ANZSCO 2013 and absent from 2022. This is the genuine
   edition split (open question #14), now a single instance rather than 23.

---

## Fix the parsers (both root-caused) — ✅ done 2026-08-18

1. **All Home Affairs pages** — content is HTML-entity-encoded JSON in
   `<input id="ctl00_PlaceHolderMain_PageSchemaHiddenField_Input">`. Decode:
   `html.unescape` → `json.loads`. **Record the JSON root key per page**: main
   pages use `content`, `previous-rounds` uses `criteria`.
2. **SkillSelect rounds** — the live table has 2 columns
   (`Occupation | minimum score`); the parser unpacks 3. Then apply D3 to
   convert names to codes.
3. **Points table** — the catalogued `/points-tested` URL has no points table;
   the real one is at `/points-table`, static HTML, same decode. No Playwright
   needed.

**Also worth fixing:** every SkillSelect row currently fails its unpack, is
caught, and is skipped — so a 100% extraction failure exits cleanly. A 100%
skip rate should be a hard failure, not a clean run.

---

## Recommended sequence

1. **D1** — delete the fabricated ceiling rows. Independent, urgent, small.
2. Parser fixes (hidden-field decode + 2-column SkillSelect) — restores the
   two sources koshi already has.
3. **D3** crosswalk — unblocks `eoi_rounds`, `occupation_momentum`, Occupation API.
4. Schema migration for **D2** (edition + grain) and **D5** (stream + percentiles).
5. **D4** BP0068 ingestion.
6. Ship the three tables that are buildable *today* with no new research:
   `program_allocation`, `points_criteria_reference`, `eligibility_requirements`,
   plus both JSON APIs (fees: 150 records; processing times: 76 combos).

---

## Other findings worth carrying forward

- **New source, no gap asked for it:** SkillSelect **previous-rounds** — 19
  rounds, 1,419 rows of history.
- **legislation.gov.au OData API** hands over LIN 19/051's full 7-version
  compilation history with effective dates and amendment reasons — supplies
  `list_change_log.effective_date`, which had no source.
- **G11 resolved:** JSA's vocabulary is exactly 4 classifications —
  `S` / `M` (metropolitan) / `R` (regional) / `NS`. `Ns` is a casing bug.
- **`assessing_bodies` turnaround/cost:** no aggregated source exists;
  irreducibly ~38 separate sites. Ship NULL.
- **EOI submitted / on-hand counts:** not published anywhere. Ship NULL.
- **`budget.gov.au/content/migration.htm`** is a **soft-404** — HTTP 200 with a
  "Page not found" body. Status-code-only health checks pass it.
- **`F2024L01616` has zero tables** — definitional only; useful as the ANZSCO
  edition pin, not as a data source.
- **Access obstacles:** VIC (`liveinmelbourne.vic.gov.au`) is Cloudflare-blocked;
  WA's list returns 0 by default and the catalogued anchor doesn't exist; SA is
  legitimately between intake rounds, not broken.

## Explicitly not reached

BP1/BP2 datasets, the minister's media-release site, EQ08's internals, and FOI
pages 3–5. Listed rather than guessed at.
