# koshi — Agent 2: Schema ↔ Source Mapping, Coverage & Integrity Audit

**Purpose:** map koshi's 18 planned domain fact tables onto the sources Agent 1
actually fetched, at **column** level, and enumerate every place where the data
model and the live sources disagree.
**Date:** 2026-08-17
**Inputs:** `agent1-page-audit.md` (ground truth — pages were really fetched),
`2026-08-16-koshi-data-model.md` (design), `2026-08-16-koshi-source-urls.md`
(catalog, superseded by Agent 1 where they conflict),
`2026-08-16-koshi-etl-architecture.md` (target architecture),
`docs/ARCHITECTURE.md` + `src/koshi/` (what exists today).

**Citation convention used throughout:**
- **[A1 §n]** = Agent 1 verified this against a live page/API response.
- **[DM Cn]** = the data model document *claims* this (design assumption, unverified).
- **[CAT n]** = the source-URL catalog claims this (design assumption, unverified).
- **[CODE]** = read directly from the repository.
- `UNVERIFIED — reason` where neither Agent 1 nor the repo establishes a fact.
  I did **not** fetch any live page; every source fact below is Agent 1's.

---

## Executive summary — the eight things that actually matter

1. **The single hardest blocker is a join key, not a parser.** SkillSelect's
   per-occupation table (Table B, 140 rows) publishes **`Occupation | minimum
   score`** — occupation *names*, never ANZSCO codes [A1 §2]. But
   `eoi_rounds.occupation_code` is an FK to `occupations.code` [DM C2], and the
   built parser reads a 3-cell row as `(occupation_code, threshold, invitations)`
   [CODE `extraction/skillselect_rounds.py`]. There is **no code column to read**.
   Every round row therefore needs a name→ANZSCO-code resolution step that has no
   source in this audit. This silently breaks `eoi_rounds`,
   `occupation_momentum` (derived from it) and the whole Occupation vertical.
   **BLOCKER.**

2. **`ceiling_usage` — a built, seeded table — has no verified source anywhere in
   the audit.** Agent 1 found the "Occupation ceilings" section of SkillSelect is
   *prose*, explicitly "not a ceiling number table" [A1 §2], and the
   planning-levels page carries a **visa-category** table (Skilled Independent,
   Employer-Sponsored, …), not an occupation-level one [A1 §3]. The two rows in
   `seeds/ceiling_usage_manual.yaml` (261313: 3200/5000; 254499: 1800/4000) cite
   `migration-program-planning-levels` [CODE], a page Agent 1 fully decoded and
   which contains no such numbers. Those rows are, on current evidence,
   **unsupported by their own citation** — which is exactly the failure koshi's
   provenance rule exists to prevent. **BLOCKER.**

3. **Occupation codes are not one key space.** Agent 1 found 4-digit unit groups
   and 6-digit occupations mixed in the same JSA listing [A1 §1]; NSW's lists are
   **4-digit unit groups** (79 + 78 rows) [A1 §12]; QLD's is **6-digit** (120 rows)
   [A1 §12]; LIN 19/051 is 6-digit [A1 §9]; JSA's shortage dataset publishes both
   levels *and* two classification editions (ANZSCO 2022 / OSCA 2024) [A1 §10].
   `occupations.code` is a single-width PK anchoring **seven** FKs [DM C1].
   **BLOCKER for NSW state rows; MAJOR globally.**

4. **`visa_subclasses` is a 6-row parent table for child tables carrying 76 and 150
   rows.** Processing times return **76 subclass × stream combinations** [A1 §8];
   the fee API returns **150 records** [A1 §4]; `visa_subclasses` is specced as
   "6 rows" [CAT 6]. Both `processing_times.visa_code` and
   `application_funnel.visa_code` are FKs to it [DM C14/C16]. Either 70+ subclasses
   are dropped or the FK fails. Additionally the design's own example self-FK
   (`491 → 191`) points at a subclass **not among the six** [DM C6]. **MAJOR.**

5. **The stream dimension is missing everywhere and it breaks two unique
   constraints.** Real data is keyed by *subclass × stream*: 189/Points-Tested,
   485 (3 sub-streams at 5,750/5,750/2,265), 500 (6 categories), 482 (3 streams),
   186 (Direct Entry / Agreement) [A1 §4, §8]. `processing_times` is unique on
   `(visa_code, as_of_date)` [DM C14] and `visa_subclasses.base_application_cost`
   is a single scalar [DM C6]. Both are violated by the real payloads. **MAJOR.**

6. **`processing_times.median_days` does not exist as a source field.** The API
   returns `Percent25/50/75/90` (+ text forms) and `ProcessGuideMaxDays`, and **no
   as-of date at all** [A1 §8]. Storing one median discards 4 of 5 published
   numbers and invents an `as_of_date` the source never states. **MAJOR** (see
   Forced change F1).

7. **`assessing_bodies` was catalogued against the wrong site and the right source
   only covers 1 of its 3 columns.** MARA is conclusively wrong — zero occurrences
   of "assessing authority" or "skills assessment" on the page [A1 §13]. LIN
   19/051 Table 6 supplies 38 bodies (abbreviation + full name) and Table 5 the
   504-row occupation→authority join [A1 §9/§13] — but `turnaround_estimate` and
   `cost` appear in neither, and Table 5's authority strings mix bare abbreviations
   (`VETASSESS`) with full names inside disjunctions (`(a) Engineers Australia; or
   (b) IML`), so the FK to `assessing_bodies.body_name` will not match without a
   normalization layer. **MAJOR** (see F2).

8. **The most valuable dataset in the whole audit has no table to land in.**
   LIN 19/051 supplies MLTSSL (212), STSOL (215) and ROL (77) *membership*
   [A1 §9]. The data model has `list_change_log` (a diff log) but **no
   list-membership table at all** [DM C13, full table inventory]. Meanwhile
   `change_type`/`effective_date` — the two columns that make `list_change_log` a
   log — have no source; legislation.gov.au serves compiled snapshots, not diffs
   [A1 §9, CAT 9]. **MAJOR** (see F4).

**Cross-cutting:** ANZSCO is being retired by JSA in favour of OSCA (sitewide
banner on koshi's own scrape target; 1,236 ANZSCO vs 1,577 OSCA results)
[A1 §1], while LIN 19/051 — the *legal* instrument — is still ANZSCO-coded
[A1 §9]. `occupations` is the FK anchor for seven tables, so this is a
schema-strategy decision, not a parser detail (see F3).

**Finding counts** (each series counted once, no cross-series deduplication):

| Series | BLOCKER | MAJOR | MINOR | Total |
|---|---|---|---|---|
| Integrity findings **I1–I24** | 3 (I1, I2, I3) | 13 | 8 | 24 |
| Forced schema changes **F1–F12** | 3 (F2, F5, F9) | 9 | 0 | 12 |
| Table verdicts **C1–C18** | 4 (C2, C3, C4, C7) | 11 | 0 | 18 (+3 OK) |
| Gaps for Agent 3 **G1–G16** | 3 (P1: G1, G2, G3) | 8 (P2) | 5 (P3) | 16 |

I2 is a BLOCKER for NSW state rows specifically and a MAJOR globally; it is
counted once, as a BLOCKER. F2 is a BLOCKER on source correctness that becomes
MAJOR once re-sourced; counted once, as a BLOCKER. C4 is blocked only by
inheritance from C2. Orphan sources **O1–O18** carry take/consider/drop verdicts
rather than severities.

---

## Coverage scoreboard — 18 domain fact tables

**Counting rule for "columns sourced":** denominator = all columns *except* the
surrogate `id` PK and the provenance trio (`source_url`/`retrieved_at`/
`reliability_tier`), which the pipeline always supplies. A column counts as
sourced only if Agent 1 saw a concrete field/cell/heading that carries it.
`½` = partially sourced (derivable, contextual, or present for only some rows).

| # | Table | Verified source (Agent 1) | Tier: design → revised | Columns sourced | Verdict |
|---|---|---|---|---|---|
| C1 | `occupations` | JSA ANZSCO card list, 1,236 results, 103 pages [A1 §1] | 2 → 2 (card scrape, not table) | 2 / 3 (67%) | **MAJOR** — `unit_group` has no source field; grain mixes 4- and 6-digit |
| C2 | `eoi_rounds` | SkillSelect hidden-field JSON, Table B 140 rows [A1 §2] | 2 → 2 (decode-then-parse) | 2½ / 5 (50%) | **BLOCKER** — occupation is a name, not a code |
| C3 | `ceiling_usage` | **none found** [A1 §2, §3] | 5 → n/a | 0 / 5 (0%) | **BLOCKER** — no occupation-level ceiling source exists in the audit |
| C4 | `occupation_momentum` | derived from C2 [CODE `momentum.py`] | derived | n/a (derived) | **BLOCKER (inherited)** — blocked by C2; also only ~3 rounds/yr [A1 §2 Table C] |
| C5 | `source_pages` | pipeline metadata [CODE] | n/a | n/a | **MAJOR** — cannot key POST-API resources; status enum can't express 403/soft-404/closed-program |
| C6 | `visa_subclasses` | 6 visa pages [A1 §6] + `GetPriceList` [A1 §4] | 5 → 5 (+2 for cost) | 2½ / 12 (21%) | **MAJOR** — 4 of 6 pages carry stub eligibility only |
| C7 | `english_test_bands` | **partial only** — points-table English band→points [A1 §5]; catalogued english-language page has 0 tables [A1 §7] | 2 → n/a | 2 / 6 (33%) | **BLOCKER** — `test_name` (half the unique key) has no source |
| C8 | `assessing_bodies` | LIN 19/051 epub Table 6, 38 rows [A1 §9/§13] | 5 → 2 (static epub HTML) | 1 / 3 (33%) | **MAJOR** — turnaround/cost unsourced |
| C9 | `occupation_assessing_bodies` | LIN 19/051 epub Table 5, 504 rows [A1 §9/§13] | 5 → 2 | 2 / 2 (100%) | **MAJOR** — needs disjunction parsing + body-name normalization |
| C10 | `points_criteria_reference` | **`/points-table`**, 11 sections/11 tables [A1 §5] | 2 → 2 (URL corrected) | 3 / 3 (100%) | **OK** — but 189-only; no visa dimension |
| C11 | `policy_events` | **none structured** — budget URL is a soft-404 [A1 §14] | 5 → 5 (editorial) | 0 / 4 (0%) | **MAJOR** — purely manual; primary URL dead |
| C12 | `state_nomination_status` | NSW 157 rows, QLD 120 rows [A1 §12]; WA gated, SA closed, VIC 403 [A1 §11/§12] | 5 → 5 | 2 / 11 (18%) | **MAJOR** — grain mismatch; 3 of 5 states unavailable |
| C13 | `list_change_log` | LIN tables 1–3 (212/215/77) [A1 §9]; NSW/QLD lists [A1 §12] | 2 → 2 | 2½ / 4 (63%) | **MAJOR** — no change events published; membership has no home table |
| C14 | `processing_times` | `GetProcessGuideVisas` + `GetProcessGuideInfo`, 76 combos [A1 §8] | 2 → 1/2 (direct JSON API) | 1½ / 3 (50%) | **MAJOR** — no median field, no as-of date, stream key missing |
| C15 | `program_allocation` | Planning-levels table, ~15 rows × 3 years [A1 §3] | **5 → 2** (catalog corrected) | 3 / 3 (100%) | **OK** — best-covered target table |
| C16 | `application_funnel` | SkillSelect Tables A/C [A1 §2/§15]; annual-report PDFs [A1 §16] | 2 + 5 | 3 / 6 (50%) | **MAJOR** — `submitted_count` verified absent; `granted_count` unverified |
| C17 | `eligibility_requirements` | health/character/english pages, 3 recipes [A1 §7] | 5 → 5 | 2 / 2 (100%) | **OK** — health page 22 months stale |
| C18 | `skills_priority_ratings` | JSA `spl_data` JSON, 1.47 MB, 916 + 311 codes [A1 §10] | 2 → 1/2 (direct JSON file) | 2 / 4 (50%) | **MAJOR** — no jurisdiction/edition dimension; `future_demand` is null in source |

**Roll-up:** 3 tables at 100% column coverage (C10, C15, C17 — plus C9 at 100%
with a normalization caveat). 4 tables at or below 33%. 2 tables (C3, C7) cannot
be built at all from any source in this audit.

---

## Per-table column-level mapping

### C1. `occupations` — MAJOR

**Source:** `jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco`,
Drupal Views **card list** (not a table), 1,236 results across 103 pages via
`?page=0..102` [A1 §1]. Tier 2, but per-card CSS selectors, not table parsing.

| Column | Source field | Status |
|---|---|---|
| `code` (PK) | `div.card_anzsco` → `"ANZSCO 422111"` [A1 §1] | ✅ verified — needs the `ANZSCO ` prefix stripped; **mixes 4-digit unit groups (`2211`) and 6-digit occupations (`422111`) in one result set** [A1 §1] |
| `name` | `h4.card_title` [A1 §1] | ✅ verified |
| `unit_group` (NOT NULL) | — | ❌ **no source field.** Derivable as `code[:4]` for 6-digit rows; **undefined for the 4-digit rows**, where it would equal `code` itself. [DM C1] asserts it is scraped |

**Design-vs-reality notes.**
- [DM C1]'s "Source reference" names the **ABS ANZSCO search page**
  (`abs.gov.au/ausstats/...`); [CAT 1] and the running code both use
  jobsandskills.gov.au [CODE `pipeline.py:36`]. The data model doc is
  internally wrong about its own built table. **MINOR** (I23).
- The built parser looks for `<table id="occupation-list">` — Agent 1 confirms
  **zero `<table>` tags and no such id anywhere in the raw HTML** [A1 §1],
  matching the known production failure [CODE `extraction/anzsco_occupations.py`].
- Orphan fields on the card with no column: "Employed" count and "Median weekly
  earnings" (the latter was `N/A` on the sampled card) [A1 §1].

---

### C2. `eoi_rounds` — BLOCKER

**Source:** SkillSelect invitation-rounds page, hidden-field JSON, section
"Current round" [A1 §2]. Decode `#ctl00_PlaceHolderMain_PageSchemaHiddenField_Input`
→ `html.unescape` → `json.loads` → `content[].block`.

Agent 1 verified four tables on this page:
- **Table A** — "Invitations issued on 4 June 2026": `Visa subclass | Total EOIs Invited | Tie break date – month and year`, 1 row (189 | 10,000 | 24/04/2026).
- **Table B** — "Invitations issued by occupation and minimum score invited": `Occupation | minimum score`, **140 rows**.
- **Table C** — "Total invitations issued during 2025-26 program year": `Visa subclass | Jul…Jun`, 2 rows.
- **Table D** — state/territory nominations: `Visa subclass | ACT | NSW | NT | Qld | SA | Tas | Vic | WA`, 2 rows.

| Column | Source field | Status |
|---|---|---|
| `visa_code` (NOT NULL) | Table A/C "Visa subclass"; **Table B has no visa column** [A1 §2] | ½ — contextual inference for all 140 threshold rows. The built parser takes `visa_code` as a caller argument [CODE], which is an assumption, not an extraction |
| `occupation_code` (FK) | Table B column 1 is **`Occupation`** — names: "Actuary", "Agricultural Consultant", "Architect", "Barrister", "Carpenter" [A1 §2] | ❌ **BLOCKER — no code is published.** FK to `occupations.code` [DM C2] cannot be satisfied without a name→code crosswalk that this audit did not find |
| `round_date` (NOT NULL) | Table A heading text "Invitations issued on **4 June 2026**" [A1 §2] | ✅ — but it lives in a *heading*, not a cell. The built parser regexes for `"Round date:"` [CODE], a string Agent 1's decoded content does not show |
| `threshold_points` (NOT NULL) | Table B "minimum score" (Actuary/90, Carpenter/65) [A1 §2] | ✅ verified |
| `invitations_issued` | — | ❌ **not published per occupation.** Table B has only 2 columns; Tables A/C are per-subclass totals [A1 §2]. Will be `NULL` for all 140 rows/round |

**Additional findings.** The built parser expects a 3-cell row
`(occupation_code, threshold_text, invitations_text)` [CODE
`extraction/skillselect_rounds.py`] against a **2-column** real table — so even
after the hidden-field decode is fixed, every row would hit the
`ValueError` skip path. Table C shows the 189 row as
`0,6887,0,0,10000,0,0,0,0,0,0,10000` — **3 non-zero months in the program year**
[A1 §2], contradicting [CAT 2]'s "~monthly (a new row per invitation round)"
cadence claim (I15).

---

### C3. `ceiling_usage` — BLOCKER

**Source:** none found in this audit.

| Column | Source field | Status |
|---|---|---|
| `occupation_code` (FK, NOT NULL) | — | ❌ no occupation-level ceiling table found |
| `program_year` | — | ❌ (the planning-levels table's year columns are program-level, not per occupation [A1 §3]) |
| `issued` (NOT NULL) | — | ❌ |
| `ceiling` (NOT NULL) | — | ❌ |
| `as_of_date` (NOT NULL) | — | ❌ |

**Evidence.** [A1 §2] on SkillSelect: *"'Occupation ceilings' is a **prose**
section here (limits explanation), not a ceiling number table — do not confuse it
with source 3's ceiling table."* [A1 §3] on the planning-levels page: the one
real table is `Visa Category | 2024–25 | 2025–26 | 2026–27`, broken out by
program line (Skilled Independent, Employer-Sponsored, …), **not by occupation**.
Agent 1 enumerated that page's four sections and reported exactly one table.

`UNVERIFIED — whether some other section of the planning-levels page, or another
page entirely, still publishes per-occupation ceilings; Agent 1 reported only the
one visa-category table and did not assert the absence of an occupation table
elsewhere on the site.`

**Consequence.** The two seeded rows in `seeds/ceiling_usage_manual.yaml` cite
`migration-program-planning-levels` as `source_url` [CODE] for numbers Agent 1
could not find on that page. This is the one place in koshi where a shipped row's
citation does not currently support its value. Escalated as I3 and G2.

---

### C4. `occupation_momentum` — BLOCKER (inherited)

Derived table; no external source by design [DM C4]. Columns
`occupation_code` / `computed_at` / `direction` are computed from
`eoi_rounds.threshold_points` history [CODE `momentum.py`].

**Blocked by C2** — every momentum row is keyed on an `occupation_code` that C2
cannot currently produce. Second, independent problem: `compute_momentum` uses a
trailing 3-round window [CODE], and Agent 1's Table C shows only **3 invitation
rounds for 189 in the whole 2025-26 program year** [A1 §2]. The window therefore
spans ~12 months, so "rising/falling" is an annual signal being presented as a
current one, and any occupation not invited in 3 separate rounds gets no momentum
row at all (I16).

---

### C5. `source_pages` — MAJOR

Metadata table, no provenance trio by design [DM C5]. All columns are
pipeline-generated [CODE `models/source_pages.py`], so there is no column-level
source mapping — but Agent 1's findings break three of its assumptions:

| Assumption [DM C5 / CODE] | Agent 1's contradicting finding | Severity |
|---|---|---|
| `url` is UNIQUE and identifies a resource | Two of the best sources are **POST endpoints with a JSON body**: `GetPriceList` (one call) and `GetProcessGuideInfo` (**76 distinct calls, same URL**, differing only by `{"VisaSubclassCode","StreamCode"}`) [A1 §4, §8]. 76 resources collapse to 1 registry row | **MAJOR** (I17) |
| `status IN ('active','dead','redirected')` | `budget.gov.au/content/migration.htm` returns **HTTP 200 with a "Page not found" body** (soft-404) [A1 §14] → registers as `active`; `liveinmelbourne.vic.gov.au` returns **403 Cloudflare** [A1 §11] → no enum value fits; SA's list page is **legitimately empty because the program is closed**, not broken [A1 §12] | **MAJOR** (I18) |
| `content_hash` is the change signal | Nearly every immi/homeaffairs page carries `<span id="pageModified">` with a real timestamp (e.g. `4/08/2026 17:03`, `1/07/2026 12:27 AM`) [A1 §2, §3, §4, §5, §7, §8] — a far better freshness signal than a whole-page byte hash. **No column exists to store it** | **MINOR** (I19) |

---

### C6. `visa_subclasses` — MAJOR

**Sources:** six visa-listing pages [A1 §6] + `POST /_layouts/15/api/data.aspx/GetPriceList`
[A1 §4]. Agent 1 verified the six pages split into two Angular templates:
190 and 500 carry **real eligibility prose** in `applicant.eligibility.criteria[]`;
189, 491, 485 and 482 carry the **literal stub `"See the relevant stream"`** [A1 §6].

| Column | Source field | Status |
|---|---|---|
| `code` (PK) | `visaSubclassCode` in `GetPriceList` [A1 §4]; page URLs | ✅ verified |
| `name` | `visaSubclassText`, e.g. `"Partner (Provisional and Migrant) visa (subclass 309/100)"` [A1 §4] | ✅ verified |
| `family` (NOT NULL) | — | ❌ curator classification. The API's only category parameter is `"category":"Visa"` [A1 §4] |
| `permanence` (NOT NULL, CHECK) | — | ❌ curator inference from prose |
| `age_limit` | — | `UNVERIFIED — Agent 1 decoded 190/500 criteria prose but did not report an age criterion; 189/491/485/482 are stubs [A1 §6]` |
| `work_rights_description` | 190/500 criteria prose [A1 §6] | ½ — 2 of 6 pages only |
| `family_inclusion_rule` | — | `UNVERIFIED — not reported in the decoded criteria [A1 §6]` |
| `residency_requirement_description` | — | `UNVERIFIED — same` |
| `occupation_list_required` (NOT NULL) | — | ❌ curator inference |
| `onward_pathway_code` (self-FK) | — | ❌ not a published field; **and [DM C6]'s own example target `191` is not one of the six rows** (I8) |
| `base_application_cost` | `basePrice`, e.g. `"AUD6,135.00"` for 189-63, `"AUD6,140.00"` for 190 and 491 [A1 §4] | ½ — **verified but ambiguous**: 485 has 3 sub-streams at 5,750/5,750/**2,265** and 500 has 6 categories at 2,500/2,500/**0/0**/2,050/2,050 [A1 §4]. One scalar per subclass cannot represent this (I6) |
| `points_test_required` (NOT NULL) | — | ❌ curator inference |

**Notes.** Values arrive as strings with an `AUD` prefix and literal `"N/A"`
[A1 §4] — needs parsing to `NUMERIC(10,2)`. The API also returns an `onShore`
flag (`"No"` on the sampled 309/100 record) [A1 §4], a dimension the schema has
no column for. 485's page has not been touched since **14/12/2024** (~20 months)
[A1 §6] — a staleness signal for a Tier-5 curated row.

---

### C7. `english_test_bands` — BLOCKER

**Catalogued source fails.** [CAT 7]/[DM C7] point at the Home Affairs
english-language page. Agent 1: hidden field **empty**, content is a plain
`RichHtmlField` div, **zero `<table>` elements**, and the verified content is
prose about the 7 August 2025 English-test-provider change [A1 §7].

**Partial substitute found in a different source.** The `/points-table` page's
English section is a real 2-column table: `Competent English | 0`,
`Proficient English | 10`, `Superior English | 20` [A1 §5].

| Column | Source field | Status |
|---|---|---|
| `test_name` (NOT NULL, half the unique key) | — | ❌ **BLOCKER.** No source in this audit names IELTS / PTE / TOEFL / Cambridge / OET with scores |
| `band_level` (NOT NULL) | points-table English table col 1 [A1 §5] | ✅ — but only the 3 points-bearing bands; `Functional` and `Vocational` [DM C7 examples] are **not** among them |
| `score_requirement` (NOT NULL) | — | ❌ no source found |
| `points_awarded` (NOT NULL) | points-table English table col 2 (0/10/20) [A1 §5] | ✅ verified |
| `cost` | — | ❌ no source found (would be per-test-provider) |
| `validity_period` | — | ❌ no source found |

**Verdict.** As designed the table is unbuildable: its unique constraint is
`(test_name, band_level)` [DM C7] and `test_name` has no source. The 3 rows that
*are* sourced duplicate `points_criteria_reference` exactly (same table, same
page). See F5 and G3.

---

### C8. `assessing_bodies` — MAJOR

**Catalogued source is conclusively wrong.** `portal.mara.gov.au` — zero
`<table>` elements, search-only, *"migration agent(s)" appears 12 times;
"assessing authority" and "skills assessment" appear **zero** times* [A1 §13].

**Correct source:** LIN 19/051 epub, **Table 6, 39 rows / 38 bodies**:
`Item | Abbreviation | Full authority name`, e.g. `1 | AACA | Architects
Accreditation Council of Australia` [A1 §9/§13]. Reached by a two-hop
resolution: `/latest` Angular shell → `<iframe id="epubFrame">` →
`.../F2019L00278/2026-03-28/2026-03-28/text/original/epub/OEBPS/document_1/document_1.html`
(834 KB static HTML, 12 tables, **no id/class selectors** — positional/heading-anchored
selection only) [A1 §9].

| Column | Source field | Status |
|---|---|---|
| `body_name` (PK) | Table 6 col 2 (`Abbreviation`) **and** col 3 (`Full authority name`) [A1 §9] | ✅ verified — but **which one is the PK is ambiguous**, and Table 5's join column uses a mix of both (I9) |
| `turnaround_estimate` | — | ❌ not in LIN 19/051. Would come from each body's own site [CAT 13] — unverified, 38 separate sites |
| `cost` | — | ❌ same |

**Tier correction:** [CAT 13]/[DM C8] say Tier 5 manual YAML. The real data is a
**static HTML table of 38 rows** — Tier 2 is achievable for `body_name`; only
`turnaround_estimate`/`cost` remain Tier 5.

---

### C9. `occupation_assessing_bodies` — MAJOR

**Source:** LIN 19/051 epub **Table 5, 505 rows / 504 occupations**:
`Item | Occupation | ANZSCO code | Relevant assessing authority` [A1 §9/§13].

| Column | Source field | Status |
|---|---|---|
| `occupation_code` (composite PK, FK) | Table 5 col 3, 6-digit ANZSCO (`133111`, `133211`) [A1 §9] | ✅ verified |
| `body_name` (composite PK, FK) | Table 5 col 4 [A1 §9] | ✅ verified **but not directly usable** — see below |

**The join column needs real work, verified from Agent 1's own sample rows:**
- `1 | construction project manager | 133111 | VETASSESS` — a bare abbreviation.
- `2 | engineering manager | 133211 | (a) Engineers Australia; or (b) IML` — a
  **disjunction of two bodies**, one written as a full name (`Engineers
  Australia`) and one as an abbreviation (`IML`).

Consequences: (a) the cell must be split into 1..n bodies — the composite PK
[DM C9] does support one-to-many, so Agent 1's "not a single FK" caution is
already satisfied structurally; (b) values must be normalized against Table 6's
**two** key columns before the FK to `assessing_bodies.body_name` resolves;
(c) the schema **cannot express that the bodies are alternatives** ("either
Engineers Australia *or* IML") rather than both being required — there is no
`alternative_group` or `is_alternative` column (I10).

Table 5's `Occupation` name column is unused by the schema, but is a useful
independent cross-check for the ANZSCO name→code crosswalk gap in C2 (see G1).

---

### C10. `points_criteria_reference` — OK (with caveats)

**Catalogued URL is wrong; the correct one is verified.** [CAT 5]/[DM C10] point
at `/points-tested`, which Agent 1 confirms has **no numeric points table
anywhere in static HTML or hidden JSON** — only prose linking onward [A1 §5].
The real table set is at the sibling URL **`/points-table`**, plain static
hidden-field JSON, **11 sections / 11 real `<table>` elements** [A1 §5].
No browser automation needed — this refutes [CAT GAPS 5]'s Playwright
recommendation.

| Column | Source field | Status |
|---|---|---|
| `criterion_name` (NOT NULL) | Section heading (Age, English language skills, Skilled employment experience, Educational qualifications, Specialist education qualification, Australian study requirement, Professional Year in Australia, Credentialled community language, Study in regional Australia, Partner skills, + Overview) [A1 §5] | ✅ verified |
| `band_description` (NOT NULL) | Table col 1, e.g. `"at least 25 but less than 33 years"`, `"Proficient English"` [A1 §5] | ✅ verified |
| `points_value` (NOT NULL) | Table col 2, e.g. `30`, `10` [A1 §5] | ✅ verified |

**Caveats.**
- Agent 1 verified **2 of 11 tables in full** (age: 4 rows; English: 3 rows) and
  reports the rest as "similarly small", est. 30–50 rows total [A1 §5].
  `UNVERIFIED — whether the other 9 tables are all 2-column; a 3-column table
  (e.g. a partner-skills matrix) would not fit this schema.`
- **No visa dimension.** This is the *subclass 189* points table. The
  state-nomination points (190/491) are **not among the 11 section headings Agent
  1 enumerated** [A1 §5], so a "points for 491" query cannot be answered from this
  table (I20, G12).
- Unique constraint `(criterion_name, band_description)` [DM C10] is plausible
  but `UNVERIFIED — the 9 unchecked tables could repeat a band string`.

---

### C11. `policy_events` — MAJOR

**Primary catalogued URL is dead.** `budget.gov.au/content/migration.htm` returns
**HTTP 200 with `<title>Page not found | Budget 2026–27</title>` and
`og:url = /page-not-found.htm`** — a soft-404 [A1 §14]. The 2026–27 budget site
is restructured into thematic sections (`01-fuel-supply-and-security` …
`06-security-and-investment`, plus `bp1`–`bp4`) with **no migration page anywhere
in the structure** [A1 §14]. `treasury.gov.au` and `minister.homeaffairs.gov.au`
are live but are generic indexes with **0 tables** [A1 §14].

| Column | Source field | Status |
|---|---|---|
| `event_date` (NOT NULL) | — | ❌ no structured source; per-release editorial |
| `visa_code` (FK, nullable) | — | ❌ editorial classification |
| `title` (NOT NULL) | — | ❌ editorial |
| `description` (NOT NULL) | — | ❌ editorial |

This is Tier 5 editorial **by design** [DM C11], so 0% column coverage is not by
itself a defect — but the catalog's claim that
`budget.gov.au/content/migration.htm` is "the concrete page that announces annual
planning levels" [CAT 14] is now false, and Agent 1's suggestion is worth taking:
since C15's numbers come straight off the planning-levels page [A1 §3], the
budget.gov.au dependency may be droppable entirely rather than replaced (I21, G13).

---

### C12. `state_nomination_status` — MAJOR

**Sources verified per state** [A1 §11/§12]:

| State | Occupation data available? | Detail |
|---|---|---|
| NSW | ✅ | `nsw-skills-lists`: 2 static tables, **79 rows (190) + 78 rows (491)**, columns `ANZSCO Code | Unit Group Name` — **4-digit unit groups** (e.g. `1325 Research and Development Managers`) |
| QLD | ✅ | offshore QSOL: 1 table, **120 rows**, `ANZSCO Code | Occupation | 491 [Yes/blank] | 190 [Yes/blank] | Additional information` — **6-digit codes**. Table carries `id="isPasted"` and Word-paste CSS classes → **markup is fragile between refreshes** |
| WA | ❌ | Views search form shows **"Displaying 0 occupation(s)"** by default; the catalog's `#2025-26-eligible-occupations` anchor **does not exist** on the page. `UNVERIFIED — how to bulk-extract; Agent 1 did not reverse-engineer the form contract` |
| SA | ❌ | **0 tables, 0 ANZSCO mentions.** Page states the skilled program is paused until 2026-27 — genuinely no list to scrape, not a parser bug |
| VIC | ❌ | **403 Cloudflare** ("Just a moment..." interstitial) — unchanged from the catalog |

| Column | Source field | Status |
|---|---|---|
| `state_code` (NOT NULL) | implicit from the page fetched | ✅ |
| `occupation_code` (FK, NOT NULL) | NSW col 1 (4-digit), QLD col 1 (6-digit) [A1 §12] | ½ — **2 of 5 states**, at two different code widths |
| `status` (NOT NULL, CHECK open/limited/closed) | — | ❌ **grain mismatch**: SA's closure is a *program-level* prose statement [A1 §12]; the lists carry membership, not per-occupation status |
| `fee` | — | `UNVERIFIED — Agent 1 reported the landing pages as static prose with 0 tables (NSW, QLD, SA) and did not report fee figures [A1 §11]` |
| `points_minimum` | — | `UNVERIFIED — same` |
| `job_offer_required` (NOT NULL) | — | `UNVERIFIED — same` |
| `residency_commitment_description` | — | `UNVERIFIED — same` |
| `decision_time_estimate` | — | `UNVERIFIED — same` |
| `documents_required` (JSONB) | — | `UNVERIFIED — same` |
| `approval_pattern_note` | — | ❌ editorial by design |
| `as_of_date` (NOT NULL, part of unique key) | — | ❌ **no state page exposes a last-updated date in static HTML** — Agent 1 grep-checked all four reachable states and confirmed genuine absence [A1 §11]. Only the fetch date is available |

**Structural gap:** QLD's table encodes the **visa dimension** (separate 190 and
491 Yes/blank columns) and NSW publishes **two per-visa lists** [A1 §12], but
`state_nomination_status` has **no `visa_code` column** [DM C12]. NSW's 79+78 rows
and QLD's 120 rows cannot be stored without either losing the visa distinction or
colliding on the unique key `(state_code, occupation_code, as_of_date)` (I11).

---

### C13. `list_change_log` — MAJOR

**Sources:** LIN 19/051 epub tables 1–3 [A1 §9] and the NSW/QLD state lists
[A1 §12].

Agent 1's verified table inventory for the LIN 19/051 epub document:

| epub table # | Rows | Section heading | Columns | Destination |
|---|---|---|---|---|
| 0 | 6 | "8 Specification of occupations — Application" | — | **orphan** (defines which visa classes the lists apply to) |
| 1 | 213 (212 occ.) | Medium and Long-term Strategic Skills List | `Item \| Occupation \| ANZSCO code` | **no membership table exists** |
| 2 | 216 (215 occ.) | Short-term Skilled Occupation List | same | **no membership table exists** |
| 3 | 78 (77 occ.) | Regional Occupation List | same | **no membership table exists** |
| 4 | 4 | transitional note (retail buyer) | — | **orphan** |
| 5 | 505 (504 occ.) | relevant assessing authority | `Item \| Occupation \| ANZSCO code \| Authority` | → C9 |
| 6 | 39 (38 bodies) | 11 Relevant assessing authorities | `Item \| Abbreviation \| Full name` | → C8 |
| 7–11 | 13/24/7/22 + amendment history | transitional provisions / endnotes | — | **orphan — but the amendment history is a candidate source for `effective_date`** |

| Column | Source field | Status |
|---|---|---|
| `list_name` (NOT NULL) | Section headings "Medium and Long-term Strategic Skills List" / "Short-term Skilled Occupation List" / "Regional Occupation List" [A1 §9]; state codes for NSW/QLD | ✅ verified |
| `occupation_code` (FK, NOT NULL) | epub tables 1–3 col 3 (6-digit ANZSCO) [A1 §9]; NSW 4-digit / QLD 6-digit [A1 §12] | ✅ verified (mixed widths — see I2) |
| `change_type` (NOT NULL, CHECK added/removed) | — | ❌ **not published.** legislation.gov.au serves versioned *compilations*, not diffs [A1 §9, CAT 9]. Must be derived by diffing two compilations |
| `effective_date` (NOT NULL) | Compilation date `2026-03-28` is present in the epub URL path [A1 §9]; the `/latest` metadata blob shows `asMadeRegisteredAt: 2019-03-10`, `status: InForce` | ½ — a compilation date is not a per-occupation change date. epub table 11 contains an **amendment history** whose content is `UNVERIFIED — Agent 1 did not open tables 7–11` |

**Two structural problems.**
1. **No membership table.** 212 + 215 + 77 occupation-list memberships — arguably
   the single most product-relevant dataset in the audit — have **nowhere to
   land**. `list_change_log` records transitions only [DM C13; full 18-table
   inventory confirms no membership table]. On a cold start with no prior
   compilation, koshi can produce **zero** rows from this source (F4).
2. **Change detection needs history koshi doesn't have.** Producing any
   `added`/`removed` row requires two compilations of the same instrument.
   `UNVERIFIED — whether legislation.gov.au exposes an enumerable list of prior
   compilation dates/epub URLs; Agent 1 resolved only the current one` (G7).

---

### C14. `processing_times` — MAJOR

**Source is an API, not a table.** [CAT 8]/[DM C14] describe "HTML table (visa ×
median processing days)". Agent 1: it is a **per-visa lookup search tool**, zero
`<table>` tags, backed by two directly-callable POST endpoints [A1 §8]:
- `POST /_layouts/15/api/GPT.aspx/GetProcessGuideVisas` body `{}` → **76 rows**
  of `{VisaSubclassText, VisaSubclassCode, StreamCode, StreamText}`.
- `POST /_layouts/15/api/GPT.aspx/GetProcessGuideInfo` body
  `{"gptRequest":{"VisaSubclassCode":"189","StreamCode":"63"}}` → one record.

Verified live response for 189/Points-Tested [A1 §8]:
`{"VisaSubclassText":"Skilled - Independent visa (subclass 189)","StreamText":"Points-Tested","VisaUrl":"...","Percent25":"191","Percent50":"202","Percent75":"245","Percent90":"271","Percent25Text":"6 Months","Percent50Text":"7 Months","Percent75Text":"8 Months","Percent90Text":"9 Months","ProcessGuideMaxDays":"282","ProcessGuideInfo":"<p></p>"}`

| Column | Source field | Status |
|---|---|---|
| `visa_code` (FK, NOT NULL) | `VisaSubclassCode` [A1 §8] | ✅ verified — but the record's identity is `(VisaSubclassCode, StreamCode)`; **`StreamCode` has no column** |
| `as_of_date` (NOT NULL, part of unique key) | — | ❌ **the API returns no date field.** The intro page's `pageModified` is `4/08/2026 8:32 AM` [A1 §8], but that is the *page*, not the data. `UNVERIFIED — Agent 1 could not confirm the data-refresh cadence ("plausibly monthly per catalog, not verified")` |
| `median_days` (NOT NULL) | closest is `Percent50` = `"202"` [A1 §8] | ½ — **there is no "median" field.** Picking `Percent50` discards `Percent25`, `Percent75`, `Percent90`, all four text forms, and `ProcessGuideMaxDays` |

**Unique-constraint violation is certain, not hypothetical.** `(visa_code,
as_of_date)` [DM C14] collapses every multi-stream subclass into one row. Agent 1
verified multi-stream subclasses exist in this very dataset: 186 has separate
Direct Entry and Agreement Pathway rows [A1 §8]; 485/500/482 have 3/6/3 streams
in the fee dataset [A1 §4]. 76 combinations cannot fit a 1-row-per-subclass key
(I5, F1).

---

### C15. `program_allocation` — OK

**Best-covered target table, and the catalog was wrong in koshi's favour.**
[CAT 3]/[DM C15] say the numbers "live in linked PDFs that change URL each
release" and mark it Tier 5. Agent 1 searched the whole raw HTML for
`href="...pdf"` and found **zero PDF links**; the full 3-year planning-level
table is statically present via the same hidden-field decode [A1 §3].
**Reclassify Tier 5 → Tier 2.**

Verified table shape: `Visa Category | 2024–25 Planning level | 2025–26 Planning
level | 2026–27 Planning level`, ~15 program-line rows, with real numbers
(Skilled Independent 16,900 / 16,900 / 21,090; Total Permanent Program 185,000 /
185,000 / 185,000) [A1 §3]. `pageModified` = 12/08/2026 5:28 PM.

| Column | Source field | Status |
|---|---|---|
| `program_year` (NOT NULL) | column headers `2024–25` / `2025–26` / `2026–27` — **unpivot** the 3 year columns [A1 §3] | ✅ verified (note the source uses en-dashes; `program_year` examples in [DM C15] use hyphens — normalize) |
| `stream_name` (NOT NULL) | "Visa Category" row label (Skilled Independent, Talent and Innovation, Employer-Sponsored, Regional, State/Territory Nominated, …) [A1 §3] | ✅ verified |
| `places` (NOT NULL) | cell value [A1 §3] | ✅ verified |

**Caveats.** The table also contains **subtotal and total rows** (Total Skilled
Migration Program, Australian Family Program subtotal, Total Permanent Program)
and non-skilled program lines (Partner, Child, Parent, Other Family, Special
Eligibility) [A1 §3]. Loading them verbatim into a flat
`(program_year, stream_name, places)` table means totals sit alongside their own
components and any `SUM(places)` double-counts (I13).

---

### C16. `application_funnel` — MAJOR

**Sources:** SkillSelect Tables A and C for invited [A1 §2/§15]; Home Affairs
annual-report PDF index for granted [A1 §16].

| Column | Source field | Status |
|---|---|---|
| `visa_code` (FK, NOT NULL) | Table A/C "Visa subclass" (189, 491) [A1 §2] | ✅ verified |
| `program_year` (NOT NULL) | Table C title "Total invitations issued during **2025-26 program year**" [A1 §2] | ✅ verified |
| `as_of_date` (NOT NULL) | derivable from the round heading date (4 June 2026) or Table C's month columns [A1 §2] | ½ — derived, not a source field |
| `submitted_count` | — | ❌ **verified absent.** Agent 1 searched the fully decoded page JSON for `submitted`, `lodged`, `EOIs on hand`, `EOIs in the system`, `pool` — **zero matches** [A1 §2/§15]. Ship `NULL`, per the design's own fallback |
| `invited_count` | Table A "Total EOIs Invited" (189 = 10,000); Table C monthly totals [A1 §2] | ✅ verified |
| `granted_count` | — | `UNVERIFIED — Agent 1 enumerated 44 annual-report PDF URLs from the static HTML but opened none; whether any contains a pathway-level (per-subclass) grant breakdown is untested [A1 §16]` |
| `granted_source_url` / `granted_retrieved_at` / `granted_reliability_tier` | the PDF URL pattern `home-affairs-annual-report-{YYYY}-{YY}.pdf` is deterministic and verified [A1 §16] | ✅ URL available even though the value behind it is not |

**Notes.** The annual-reports index page's `pageModified` span is **present but
empty** — uniquely among every immi/homeaffairs page Agent 1 checked [A1 §16], so
there is no freshness signal for this source at all. The funnel-order CHECK
`submitted >= invited >= granted` [DM C16] will be vacuous while `submitted` is
NULL, and risks false violations when it isn't, because `invited` is a
*round/monthly* figure and `granted` an *annual* one (I14).

---

### C17. `eligibility_requirements` — OK

**Three sibling URLs, three different extraction recipes** — none anticipated by
the catalog, all static and JS-free once identified [A1 §7]:

| `requirement_type` | Extraction recipe (verified) | `pageModified` |
|---|---|---|
| `health` | 4th schema variant: `{"components":[{"html": "..."}]}` — real content in `components[1].html` | **16/10/2024** (~22 months stale) |
| `character` | familiar `content[].block` sections (8 sections) | 19/02/2026 |
| `english_language` | hidden field **empty**; read `<div id="ctl00_PlaceHolderMain_ctl03__ControlWrapper_RichHtmlField">` directly | 02/02/2026 |

| Column | Source field | Status |
|---|---|---|
| `requirement_type` (UNIQUE, CHECK) | one row per verified page; enum values match the three pages exactly | ✅ verified |
| `summary` (NOT NULL) | real prose confirmed present on all three pages [A1 §7] | ✅ verified (curated summary of verified prose — Tier 5 by design) |

Only caveat: the health page's 22-month staleness [A1 §7] should be surfaced, not
hidden, given koshi's provenance posture (I22).

---

### C18. `skills_priority_ratings` — MAJOR

**Source is a downloadable JSON file, not a scrape.** The page's `splTable` is an
**empty DataTables shell**; the real data is named in the page's own
`drupalSettings` blob and fetched directly: `/system/files/applet_data/25-10-10 -
splData (1).json`, **200, valid JSON, 1.47 MB** [A1 §10]. **Reclassify Tier 2 →
Tier 1/2 (direct file GET, no HTML parsing).**

Verified structure [A1 §10]:
```
{ "4": {"2022": {code: {c, t, l, v: {year: {rnat,rnsw,rvic,rqld,rsa,rwa,rtas,rnt,ract,d}}}},
        "2024": {...}},
  "6": {"2022": {...}, "2024": {...}} }
```
`"4"`/`"6"` = ANZSCO digit level; `"2022"`/`"2024"` = **classification edition**
(ANZSCO 2022 / OSCA 2024, confirmed against the page's own UI toggle);
`c`=code, `t`=title, `l`=level, `v`=per-year (2021–2025) per-jurisdiction ratings.
Volume: **916 six-digit occupations, 311 four-digit unit groups** per edition.

| Column | Source field | Status |
|---|---|---|
| `occupation_code` (FK, NOT NULL) | `c` [A1 §10] | ✅ verified — but exists at **two code widths × two classification schemes** |
| `shortage_rating` (NOT NULL) | `rnat` (or a state field) [A1 §10] | ✅ verified — vocabulary is `{NS, S, R, M, Ns}`; `NS`=Not in Shortage and `S`=Shortage are clear from context, **`R`, `M` and lowercase `Ns` are `UNVERIFIED — the glossary modal is JS-populated and was not in the static HTML`**. `NS` vs `Ns` coexisting looks like a casing inconsistency, not two intentional codes [A1 §10] |
| `future_demand_rating` | `d` [A1 §10] | ❌ **`null` for every record Agent 1 checked** — the dimension is not currently populated by JSA. Launch `NULL` |
| `as_of_date` (NOT NULL, part of unique key) | per-year keys 2021–2025 inside `v`; filename encodes `25-10-10` (`UNVERIFIED — date format not confirmed`) [A1 §10] | ½ — the source grain is a **year**, not a date |

**Three dimensions the schema cannot hold** (I7): the dataset is keyed by
`(code, digit-level, classification edition, rating year, jurisdiction)` —
9 jurisdictions (`rnat` + 8 states/territories) × 5 years × 2 editions × 2 code
levels. The unique constraint `(occupation_code, as_of_date)` [DM C18] admits
**one** rating per occupation per date, so ~90% of the dataset is either dropped
or collides. `l` (level) also has no column.

---

## Orphan sources — verified data with no destination table

Everything below was **confirmed present by Agent 1** and has no column or table
in the data model. Each is either a missed opportunity or scope to drop
explicitly. Ordered by value.

| # | Orphan data | Verified detail [A1 §] | Verdict |
|---|---|---|---|
| **O1** | **MLTSSL / STSOL / ROL membership** | epub tables 1–3: **212 / 215 / 77** occupations with ANZSCO codes [§9] | **Take.** Highest-value orphan in the audit. Needs a new `occupation_list_membership` table (F4) |
| **O2** | **OSCA occupation list** | `occupations-osca`, 200, same card template, **1,577 results**, `OSCA 432931`-style codes [§1] | **Decide now.** Either a scheme column on `occupations` or an explicit "ANZSCO-only, will rot" decision (F3) |
| **O3** | **Processing-time percentile distribution** | `Percent25/75/90`, all four `*Text` forms, `ProcessGuideMaxDays`, `StreamCode/StreamText`, `VisaUrl` — 76 combos [§8] | **Take.** Free richness on an API koshi already calls (F1) |
| **O4** | **Per-jurisdiction / per-year shortage ratings** | `rnsw, rvic, rqld, rsa, rwa, rtas, rnt, ract` × years 2021–2025 × 2 editions × 2 code levels [§10] | **Take.** State-by-state shortage is directly product-relevant (F7) |
| **O5** | **State/territory nomination allocations** | SkillSelect **Table D**: `Visa subclass \| ACT \| NSW \| NT \| Qld \| SA \| Tas \| Vic \| WA`, 2 rows (190, 491), e.g. 190 = 800/2100/850/1850/1350/1200/2700/2000 [§2] | **Take.** No table has a state × visa × places grain; `program_allocation` has no state dimension (F8) |
| **O6** | **Full fee matrix** | `over18Price`, `under18Price`, `nonInternetPrice`, `subsequentPrice`, `onShore`, `streamCode/streamText`, `note` — across **150 records** [§4] | **Take (partially).** `visa_subclasses.base_application_cost` keeps 1 of 6 published prices (F6) |
| **O7** | **JSA labour-market fields** | per card: "Employed" count, "Median weekly earnings" (`N/A` on the sampled card) [§1] | **Consider.** Cheap — already on the page koshi scrapes for `occupations` |
| **O8** | **LIN 19/051 amendment history** | epub tables 7–11, incl. an amendment history block [§9] | **Investigate.** The most likely real source for `list_change_log.effective_date` (G7). Content `UNVERIFIED` |
| **O9** | **Companion legislative instruments** | `F2024L01618` (subclass 186 occupations + authorities) and `F2024L01616` (**Migration (ANZSCO Definition) Specification 2024**), both 200, both confirmed to use the same iframe→epub pattern; epub URLs resolved [§9] | **Investigate.** F2024L01616 is the strongest candidate for a *legally authoritative* occupation name↔code list — which is exactly what C2's blocker needs (G1). Table content `UNVERIFIED` |
| **O10** | **QLD per-visa flags + "Additional information"** | 190/491 Yes-blank columns and a free-text column on the 120-row QSOL table [§12] | **Take.** Needed anyway to fix C12's missing visa dimension (I11) |
| **O11** | **Tie-break date** | SkillSelect Table A col 3: `24/04/2026` for the 4 June 2026 round [§2] | **Consider.** A real invitation-pressure signal; no column anywhere |
| **O12** | **`pageModified` timestamps** | present on nearly every immi/homeaffairs page, e.g. `4/08/2026 17:03`, `1/07/2026 12:27 AM`, `11/06/2026 13:38` [§2,§3,§4,§5,§7,§8] | **Take.** Better freshness signal than a byte hash; no column on `source_pages` (I19) |
| **O13** | **LIN 19/051 application + transitional tables** | epub table 0 (6 rows: which visa classes the lists apply to), table 4 (retail-buyer transitional) [§9] | **Drop explicitly.** Legal scoping, not product data |
| **O14** | **WA accredited institutions** | largest of WA's 22 tables: **72 rows** of CRICOS-numbered educational institutions [§11] | **Drop explicitly.** Out of koshi's stated scope |
| **O15** | **Regulator Performance self-assessment PDFs** | 8 PDFs under `/commitments/files/rpf-self-assessment-{YYYY}-{YY}.pdf` on the annual-reports page [§16] | **Drop explicitly.** Agent 1 already flags them as not relevant to `application_funnel` |
| **O16** | **43 historical annual-report PDFs** | `home-affairs-annual-report-{YYYY}-{YY}.pdf`, 1 current + 43 prior, all enumerable from static HTML [§16] | **Consider.** A back-fill path for `granted_count` history if any year proves to carry a pathway breakdown |
| **O17** | **`spl_search` companion JSON** | `/system/files/applet_data/splSearch (2).json`, 316 KB, URL found, `UNVERIFIED — not downloaded` [§10] | **Drop unless needed.** Agent 1 judged it a lighter autocomplete index |
| **O18** | **190/500 eligibility criteria prose** | real per-criterion prose in `applicant.eligibility.criteria[]` (e.g. 190's bridging-visa scenarios) [§6] | **Consider.** Richer than the 4 free-text columns on `visa_subclasses` can hold; no criterion-grain table exists |

---

## Integrity & relationship findings

Walking the FK graph, the join keys, the cardinality assumptions, the unique
constraints, and the enum/domain assumptions against Agent 1's verified data.

### FK graph — parent-table health

`occupations.code` anchors **7** FKs and `visa_subclasses.code` anchors **3**
(+1 self-FK) [DM ERD]. Both parents are compromised:

| Parent | Child FKs | Parent's own source health |
|---|---|---|
| `occupations.code` | `eoi_rounds`, `ceiling_usage`, `occupation_momentum`, `state_nomination_status`, `skills_priority_ratings`, `occupation_assessing_bodies`, `list_change_log` | ⚠ Sourced (1,236 rows [A1 §1]) but **mixed-width**, **frozen scheme** (ANZSCO retired [A1 §1]), and `unit_group` unsourced |
| `visa_subclasses.code` | `processing_times`, `application_funnel`, `policy_events`, **self** (`onward_pathway_code`) | ⚠ **6 rows** [CAT 6] against children carrying 76 [A1 §8] and 150 [A1 §4] records |
| `assessing_bodies.body_name` | `occupation_assessing_bodies` | ⚠ Sourced (38 rows [A1 §9]) but key format doesn't match the child's values |

---

**I1 — `eoi_rounds.occupation_code` FK cannot be populated. BLOCKER.**
Table B publishes `Occupation | minimum score` — names only, no code column
[A1 §2, verified sample: Actuary/90, Carpenter/65]. The FK targets
`occupations.code` [DM C2]. Every one of ~140 rows per round needs a
name→ANZSCO-code resolution with no verified source. Cascades to
`occupation_momentum` (I16) and every occupation-level API response.
→ G1.

**I2 — Occupation code width is not consistent across sources. BLOCKER (NSW), MAJOR (global).**
Verified widths: JSA listing **mixes 4- and 6-digit in one result set** [A1 §1];
NSW skills lists are **4-digit unit groups** (`1325 Research and Development
Managers`, 79+78 rows) [A1 §12]; QLD QSOL is **6-digit** (120 rows) [A1 §12];
LIN 19/051 tables 1–3 and 5 are **6-digit** [A1 §9]; JSA `spl_data` publishes
**both levels as separate top-level keys** (`"4"`: 311 rows, `"6"`: 916 rows)
[A1 §10]. A single-width `occupations.code` PK [DM C1] means NSW's rows either
fail the FK or silently join at the wrong grain (a 4-digit unit group matching
nothing, or being treated as an occupation). → F9.

**I3 — `ceiling_usage` rows cite a page that does not contain their values. BLOCKER.**
`seeds/ceiling_usage_manual.yaml` [CODE] asserts `261313: issued 3200, ceiling
5000` sourced from `migration-program-planning-levels`. Agent 1 decoded that page
in full and found one visa-category table with no occupation dimension [A1 §3],
and separately confirmed SkillSelect's "Occupation ceilings" section is prose
[A1 §2]. koshi's own invariant is "no row ships without a source"
[docs/ARCHITECTURE.md §3]; these two rows technically satisfy the
`require_provenance` check (a non-empty URL) while failing its intent. → G2.

**I4 — `visa_subclasses` (6 rows) is too small to be the FK parent for its children. MAJOR.**
`processing_times.visa_code` [DM C14] must accept the **76** subclass×stream
combinations the API enumerates [A1 §8], which span far more than 6 subclasses
(186, 189, 190, 482, 485, 491, 500, …). The fee API covers **150 records**
"all AU visa subclasses × streams, not just the 6 skilled ones" [A1 §4]. Loading
either dataset whole violates the FK; loading only 6 discards ~90% of two
already-clean JSON sources. → F10.

**I5 — `processing_times` unique constraint is violated by real data. MAJOR.**
`UNIQUE(visa_code, as_of_date)` [DM C14] vs. a source keyed on
`(VisaSubclassCode, StreamCode)` — Agent 1 verified 186 returns separate Direct
Entry and Agreement Pathway rows [A1 §8], and the fee dataset confirms 485 (3
sub-streams), 500 (6 categories) and 482 (3 streams) [A1 §4]. Any full load
raises a duplicate-key error or silently keeps one arbitrary stream. → F1.

**I6 — `visa_subclasses.base_application_cost` is ambiguous for multi-stream subclasses. MAJOR.**
Verified prices [A1 §4]: 485's three sub-streams are **5,750 / 5,750 / 2,265**
and 500's six categories are **2,500 / 2,500 / 0 / 0 / 2,050 / 2,050**. A single
scalar per subclass cannot represent these without picking one arbitrarily. This
also compounds open design question #5 [ETL §16]: a Tier-2 scraped fee written
onto an `official_curated` row erases the fee's true provenance. → F6.

**I7 — `skills_priority_ratings` unique constraint drops most of the dataset. MAJOR.**
`UNIQUE(occupation_code, as_of_date)` [DM C18] vs. a source keyed on
`(code, digit-level, edition, year, jurisdiction)` — 9 jurisdiction fields
(`rnat`+8) × 5 years × 2 editions × 2 code levels [A1 §10]. Either ~90% of the
data is discarded or the load collides. → F7.

**I8 — `visa_subclasses.onward_pathway_code` self-FK has no valid target. MAJOR.**
[DM C6] gives the canonical example `491 → 191`, but the catalogued source set is
six pages: 189/190/491/485/500/482 [CAT 6, all verified 200 by A1 §6]. **191 is
not among them**, so the self-FK is unsatisfiable for the one example the design
names. The same applies to any 482→186 pathway. The two-pass seed [DM C6] solves
insert ordering, not a missing parent row.

**I9 — `occupation_assessing_bodies.body_name` FK will not resolve without normalization. MAJOR.**
Verified Table 5 values [A1 §9]: `VETASSESS` (bare abbreviation) and
`(a) Engineers Australia; or (b) IML` (a disjunction mixing a full name and an
abbreviation). Table 6 supplies **both** an `Abbreviation` and a `Full authority
name` column [A1 §9], so the parent has two candidate keys and the child has
values drawn from both. `assessing_bodies.body_name` as PK [DM C8] must pick one
and map the other. → F2.

**I10 — The schema cannot express "either body". MAJOR.**
`(a) Engineers Australia; **or** (b) IML` [A1 §9] is an alternative, not a
requirement to use both. The composite PK `(occupation_code, body_name)`
[DM C9] stores two independent rows, which reads as "both apply" — a materially
wrong answer to "who assesses engineering managers". Needs an
alternative-group/ordinal column. → F2.

**I11 — `state_nomination_status` has no visa dimension, and its grain doesn't match the sources. MAJOR.**
QLD's table encodes 190 and 491 as **separate Yes/blank columns** and NSW
publishes **two separate per-visa lists** (79 rows for 190, 78 for 491)
[A1 §12]. With no `visa_code` column [DM C12], NSW's two lists collide on
`UNIQUE(state_code, occupation_code, as_of_date)` for any occupation on both
lists. Separately, 9 of the table's 11 data columns (`fee`, `points_minimum`,
`job_offer_required`, …) are **program-level or unsourced**, while the only
verified data is list *membership* — a grain the table doesn't model. → F11, G6.

**I12 — `state_nomination_status.as_of_date` is NOT NULL with no source. MAJOR.**
Agent 1 grep-checked NSW, QLD, WA and SA for last-updated phrasing and confirmed
**genuine absence from the markup on all four** [A1 §11]. The column is part of
the unique key [DM C12], so its value determines dedup behaviour — and it can
only be the fetch date, which makes every re-crawl a new "status snapshot" even
when nothing changed.

**I13 — `program_allocation` will mix totals with their components. MINOR.**
The verified table includes `Total Skilled Migration Program`, the Family Program
subtotal and `Total Permanent Program` (185,000) alongside the line items
[A1 §3]. A flat `(program_year, stream_name, places)` table [DM C15] with no
row-type flag makes `SUM(places)` double-count. Needs a filter or a
`row_type`/`parent_stream` column.

**I14 — `application_funnel` funnel-order CHECK compares incompatible periods. MINOR.**
`submitted >= invited >= granted` [DM C16]. `submitted` is verified absent
(always NULL) [A1 §2/§15], so the left comparison never fires. The right one
compares a **round/monthly** invited figure [A1 §2, Table A/C] against an
**annual** granted figure [A1 §16] — for the same `as_of_date` row, `granted`
can legitimately exceed `invited` without any data error.

**I15 — Cadence assumption contradicted by row counts. MAJOR.**
[CAT 2] says "~monthly (a new row per invitation round)". Agent 1's Table C shows
189's monthly series as `0,6887,0,0,10000,0,0,0,0,0,0,10000` — **3 non-zero
months in the 2025-26 program year** [A1 §2]. This changes the expected volume
(~140 rows × ~3 rounds ≈ 420 `eoi_rounds` rows/year, not ~1,700), which directly
sets `quality_policies.expected_min_records` / `max_change_percent` [DM A5] and
the `schedules.cadence` group [DM A6].

**I16 — `occupation_momentum`'s 3-round window spans ~a year. MAJOR.**
`compute_momentum` uses a trailing 3-round threshold delta [CODE `momentum.py`].
At ~3 rounds/year (I15), "rising" describes a 12-month trend while the API
presents it as current. Additionally, only ~140 occupations appear per round
[A1 §2] out of 1,236 [A1 §1], and membership varies by round, so most occupations
will never accumulate 3 rounds → momentum is sparse by construction.

**I17 — `source_pages.url` UNIQUE cannot key POST-parameterised resources. MAJOR.**
`GetProcessGuideInfo` is **one URL called 76 times with different JSON bodies**
[A1 §8]; `GetPriceList` is a POST with a body [A1 §4]. The registry's unique key
is `url` alone [CODE `models/source_pages.py`], so 76 resources collapse into 1
row with one content hash and one extraction watermark. The control-plane
`resources.locator` JSONB [DM A2] models method/headers correctly — the built
`source_pages` table does not.

**I18 — `source_pages.status` enum cannot express three real observed states. MAJOR.**
`CHECK (status IN ('active','dead','redirected'))` [DM C5] vs. verified reality:
a **soft-404** returning HTTP 200 with a "Page not found" body [A1 §14] records
as `active`; a **403 Cloudflare challenge** [A1 §11] has no value at all; and
SA's **legitimately empty** list page (program paused between intake rounds)
[A1 §12] is indistinguishable from a broken parser. Agent 1 explicitly asks for
the last distinction: *"a quality-policy design should distinguish 'source
temporarily has no data because the program is closed' from 'parser broke.'"*

**I19 — No column for the `pageModified` freshness signal. MINOR.**
Verified present on nearly every immi/homeaffairs page [A1 §2,§3,§4,§5,§7,§8].
`source_pages` has `last_changed_at` (when *koshi* noticed a hash change) but no
`source_last_modified` (when the *publisher* says it changed) [CODE].

**I20 — `points_criteria_reference` has no visa dimension. MINOR.**
The 11 verified sections are the **subclass 189** points table [A1 §5]. State
nomination points (190/491) are not among the enumerated headings, so the table
silently answers "the points test" with "the 189 points test". → G12.

**I21 — `policy_events`' primary catalogued URL is dead. MINOR.**
Soft-404 confirmed [A1 §14]; no migration page exists in the 2026–27 budget
structure. Since C15's numbers come directly off the planning-levels page
[A1 §3], the budget.gov.au dependency may be removable rather than replaceable.

**I22 — Stale sources need to be visible, not silent. MINOR.**
Verified staleness: health page **16/10/2024** (~22 months) [A1 §7]; 485 visa
page **14/12/2024** (~20 months) [A1 §6]; annual-reports index has an **empty**
`pageModified` [A1 §16]. `retrieved_at` records when koshi fetched, not how old
the content is — a curated row can look fresh while restating 2-year-old prose.

**I23 — Doc-vs-code drift. MINOR.**
(a) [DM C1] names the **ABS** ANZSCO page as `occupations`' source; the catalog
and the running code use **jobsandskills.gov.au** [CAT 1, CODE `pipeline.py:36`].
(b) Migration numbers disagree: [DM Table Index] says `occupations`=0001,
`source_pages`=0005; the repo has `0001_create_source_pages`,
`0002_create_occupations`, `0003_create_eoi_rounds`, `0004_create_ceiling_usage`,
`0005_create_occupation_momentum`, `0006_eoi_rounds_dedup_and_data_integrity`
[CODE `alembic/versions/`]. Worth fixing during consolidation so Agent 3 and
future builders aren't misled.

**I24 — `reliability_tier` has no value for "official JSON API". MINOR.**
The enum is `official_scraped | official_curated | derived | community_sourced`
[DM Provenance]. Two of the best sources are authenticated-free official JSON
APIs [A1 §4, §8] — materially more reliable than HTML scraping. Calling them
`official_scraped` is defensible but loses a real reliability distinction that
koshi's whole provenance design exists to express.

---

## Forced schema changes

Each item: what the design says → what Agent 1 verified → recommended change.
The three the brief named are F1, F2, F3; F4–F12 are the ones I found.

### F1 — `processing_times`: percentile distribution + stream key. MAJOR

- **Design:** `median_days INTEGER NOT NULL`, `UNIQUE(visa_code, as_of_date)`,
  Tier 2 HTML table [DM C14].
- **Agent 1 verified:** no `median` field exists. `GetProcessGuideInfo` returns
  `Percent25:"191"`, `Percent50:"202"`, `Percent75:"245"`, `Percent90:"271"`,
  four matching `*Text` fields, and `ProcessGuideMaxDays:"282"` — plus
  `StreamCode`/`StreamText` as part of the record's identity across **76
  combinations**. No date field of any kind [A1 §8].
- **Change:**
  1. Add `stream_code TEXT` (nullable for single-stream subclasses) and put it in
     the unique key: `UNIQUE(visa_code, stream_code, as_of_date)`.
  2. Replace `median_days` with `p25_days`, `p50_days`, `p75_days`, `p90_days`,
     `max_days` (all INTEGER, nullable). If a single headline number is needed for
     the API, expose `p50_days` under an explicit alias and document the choice —
     do not name a source field "median" that the source never calls median.
  3. `as_of_date`: since the API publishes no date, either source it from the
     page's `pageModified` [A1 §8] or rename to `retrieved_on` so the column
     doesn't imply publisher-asserted currency it doesn't have.
  4. Retier: Tier 2 HTML → **direct JSON API** (2 calls + 76 calls, no parsing).

### F2 — `assessing_bodies` / `occupation_assessing_bodies`: re-source to LIN 19/051. BLOCKER→MAJOR

- **Design:** sourced from `portal.mara.gov.au`, Tier 5 manual YAML [DM C8/C9,
  CAT 13].
- **Agent 1 verified:** MARA is conclusively wrong — 0 tables, search-only,
  "assessing authority" and "skills assessment" appear **zero** times, while
  "migration agent(s)" appears 12 times [A1 §13]. The correct data is LIN
  19/051's epub: **Table 6 = 38 bodies** (`Abbreviation | Full authority name`),
  **Table 5 = 504-row occupation→authority join** [A1 §9/§13].
- **Change:**
  1. Repoint provenance for both tables at the LIN 19/051 epub URL; **delete
     mara.gov.au from the source catalog** (not "deprioritise" — it has zero
     usable content for this purpose).
  2. Retier 5 → **2**, but note the two-hop resolution (`/latest` → iframe →
     epub) and that the 12 tables have **no id/class attributes** — selection
     must be heading-anchored/positional [A1 §9].
  3. Change `assessing_bodies` PK from a single `body_name` to an explicit
     `body_code` (Table 6's `Abbreviation`) + `body_full_name` (Table 6 col 3),
     so the child's mixed-format values (I9) have both keys to normalize against.
  4. Add an alternatives model to the join — e.g.
     `alternative_group SMALLINT` — so `(a) Engineers Australia; or (b) IML`
     stores as two rows in one group rather than two independent requirements (I10).
  5. `turnaround_estimate` and `cost` have **no source**: mark them explicitly
     nullable/Tier-5-pending rather than implying LIN 19/051 supplies them (G8).

### F3 — `occupations`: ANZSCO→OSCA blast radius. MAJOR

- **Design:** `occupations.code` is the ANZSCO-anchored PK and the FK parent for
  **7** tables [DM C1].
- **Agent 1 verified:** a sitewide banner on koshi's own scrape target reads
  *"ANZSCO has been superseded and is no longer updated. Replacement OSCA content
  is now available and will expand as new data is released."* The OSCA listing is
  live with **1,577 results** vs ANZSCO's **1,236**; "OSCA Code A to Z" already
  appears as a sort option **on the ANZSCO page itself**; and JSA's shortage
  dataset already **dual-publishes under both ANZSCO 2022 and OSCA 2024**
  [A1 §1, §10].
- **Blast radius:** `eoi_rounds`, `ceiling_usage`, `occupation_momentum`,
  `state_nomination_status`, `skills_priority_ratings`,
  `occupation_assessing_bodies`, `list_change_log` — 7 FKs, i.e. every
  occupation-grain fact koshi holds.
- **Recommendation — keep ANZSCO as the PK, but stop pretending it's the only
  scheme.** Rationale from verified evidence, not preference: the *legally
  binding* instrument (LIN 19/051, compiled 2026-03-28, `status: InForce`) is
  ANZSCO-coded [A1 §9], and the state lists koshi must join to are ANZSCO-coded
  [A1 §12]. Migrating the PK to OSCA today would break the join to the law itself.
  Concretely:
  1. Add `code_scheme TEXT NOT NULL DEFAULT 'ANZSCO'` and
     `scheme_edition TEXT` (e.g. `2022`) to `occupations`; move the PK to
     `(code_scheme, code)` or keep `code` PK with a CHECK while only ANZSCO rows
     exist.
  2. Add `code_level SMALLINT` (4 or 6) — see F9.
  3. Add a **crosswalk table** `occupation_code_map(from_scheme, from_code,
     to_scheme, to_code, relationship)`. **The crosswalk source is
     `UNVERIFIED`** — Agent 1 found no correspondence file, only that JSA
     publishes both schemes side by side [A1 §10]. → G4.
  4. Record the decision in the data model doc with the ANZSCO-retirement banner
     as its cited evidence, so it is a deliberate choice with a known expiry
     rather than an unexamined default.

### F4 — Add an occupation-list membership table. MAJOR

- **Design:** `list_change_log` (a diff log) is the only home for MLTSSL/STSOL/ROL
  data [DM C13]; the 18-table inventory contains no membership table.
- **Agent 1 verified:** LIN 19/051 serves **current membership** —
  MLTSSL 212, STSOL 215, ROL 77 occupations with codes [A1 §9] — and
  **no change log**; the register publishes versioned compilations only
  [A1 §9, CAT 9].
- **Change:** add `occupation_list_membership(list_name, occupation_code,
  instrument_id, compilation_date, …)` with `UNIQUE(list_name, occupation_code,
  compilation_date)`. Keep `list_change_log` as a **derived** table computed by
  diffing two membership snapshots — which also means its `reliability_tier`
  should arguably be `derived`, not `official_scraped` as [DM C13] specifies,
  because no page ever states "added" or "removed". On a cold start
  `list_change_log` is legitimately empty; only membership has data.

### F5 — `english_test_bands`: rebuild or drop. BLOCKER

- **Design:** 6 columns keyed `(test_name, band_level)`, scraped Tier 2 from the
  Home Affairs English page [DM C7].
- **Agent 1 verified:** that page has **zero tables** and its content is prose
  about the 7 Aug 2025 test-provider change [A1 §7]. The only verified
  band→points data is 3 rows on `/points-table` (Competent 0 / Proficient 10 /
  Superior 20) [A1 §5] — which is already `points_criteria_reference` data.
- **Change:** either (a) **drop the table** and let
  `points_criteria_reference` carry the English bands, or (b) keep it but reduce
  the unique key to `band_level` alone and mark `test_name`,
  `score_requirement`, `cost`, `validity_period` as pending a source Agent 3 must
  find (G3). Do **not** ship the table populated with hand-entered IELTS/PTE
  score thresholds citing a page that doesn't contain them — that is I3's failure
  repeated.

### F6 — Fees: promote to a real table. MAJOR

- **Design:** one scalar `visa_subclasses.base_application_cost`, updated by PK
  [DM C6], flagged as open question #5 [ETL §16].
- **Agent 1 verified:** `GetPriceList` returns **150 records** with **6 price
  fields** each (`basePrice`, `over18Price`, `under18Price`, `nonInternetPrice`,
  `subsequentPrice`, plus `note`), an `onShore` flag, and `streamCode`/
  `streamText` [A1 §4]; multi-stream subclasses have genuinely different prices
  (485: 5,750/5,750/2,265) [A1 §4].
- **Change:** add `visa_fees(visa_code, stream_code, onshore, base_price,
  additional_applicant_over_18, additional_applicant_under_18,
  non_internet_price, subsequent_temporary_price, effective_date, + provenance)`,
  and either drop `base_application_cost` or define it as a documented derived
  view over `visa_fees`. This also resolves open question #5 cleanly: the fee
  keeps its own `official_scraped` provenance instead of being written onto an
  `official_curated` row.

### F7 — `skills_priority_ratings`: add jurisdiction, edition and level. MAJOR

- **Design:** `(occupation_code, shortage_rating, future_demand_rating,
  as_of_date)` with `UNIQUE(occupation_code, as_of_date)` [DM C18].
- **Agent 1 verified:** the source is keyed by digit-level (`"4"`/`"6"`),
  classification edition (`"2022"`/`"2024"`), year (2021–2025) and **9
  jurisdiction fields** (`rnat, rnsw, rvic, rqld, rsa, rwa, rtas, rnt, ract`);
  `d` (future demand) is **null for every record checked** [A1 §10].
- **Change:**
  1. Add `jurisdiction TEXT NOT NULL` (`NAT`/`NSW`/…), `code_scheme` +
     `scheme_edition`, and `rating_year`.
  2. New unique key: `(occupation_code, code_scheme, jurisdiction, rating_year)`.
  3. Ship `future_demand_rating` **NULL** and document that JSA does not
     currently populate it — don't build features on it.
  4. Do **not** hard-code a CHECK on the rating vocabulary yet: the observed set
     is `{NS, S, R, M, Ns}` with `R`, `M` and the lowercase `Ns` **unverified**,
     and `NS`/`Ns` are probably a casing bug in the source [A1 §10]. Store raw +
     a normalized column, and add the CHECK once G11 resolves.

### F8 — Add a state dimension for nomination allocations. MAJOR

- **Design:** `program_allocation(program_year, stream_name, places)`, no state
  dimension [DM C15]; `state_nomination_status` is per-occupation [DM C12].
- **Agent 1 verified:** SkillSelect Table D publishes
  `Visa subclass | ACT | NSW | NT | Qld | SA | Tas | Vic | WA` with real
  per-state counts (190: 800/2100/850/1850/1350/1200/2700/2000) [A1 §2] —
  a **state × visa × places** grain that neither table can hold.
- **Change:** add `state_allocation(program_year, state_code, visa_code, places,
  + provenance)`, or add nullable `state_code`/`visa_code` to
  `program_allocation` with a row-type discriminator (see also I13).

### F9 — Make occupation code grain explicit. BLOCKER

- **Design:** `occupations.code` is a single TEXT PK; `unit_group` NOT NULL
  [DM C1].
- **Agent 1 verified:** 4- and 6-digit codes coexist in the JSA listing [A1 §1];
  NSW joins at 4-digit, QLD/LIN at 6-digit [A1 §9, §12]; `spl_data` separates
  the two levels structurally [A1 §10].
- **Change:** add `code_level SMALLINT NOT NULL CHECK (code_level IN (4,6))`;
  make `unit_group` **nullable** (it has no source field at all — it is
  `code[:4]` for 6-digit rows and undefined for 4-digit rows), or drop it in
  favour of a self-referencing `parent_code`. Any FK join must then be
  level-aware, or NSW's unit-group rows will match nothing.

### F10 — Widen `visa_subclasses` or narrow its children. MAJOR

- **Design:** 6 curated rows [CAT 6] parenting `processing_times`,
  `application_funnel`, `policy_events` and itself.
- **Agent 1 verified:** 76 subclass×stream processing-time combinations [A1 §8],
  150 fee records [A1 §4], and a self-FK example (`491→191`) whose target isn't
  among the six [DM C6].
- **Change:** seed `visa_subclasses` from the **fee API's own
  `visaSubclassCode`/`visaSubclassText` pairs** (150 records — verified to carry
  both code and name [A1 §4]) as a thin registry, then enrich only the ~6 skilled
  subclasses with curated `family`/`permanence`/etc. This satisfies every child
  FK without hand-curating 150 rows. Add the pathway targets (191, 186) even if
  their descriptive columns stay NULL.

### F11 — Re-grain `state_nomination_status`. MAJOR

- **Design:** one row per `(state_code, occupation_code, as_of_date)` carrying
  program-level attributes (`status`, `fee`, `points_minimum`,
  `job_offer_required`, `decision_time_estimate`, `documents_required`)
  [DM C12].
- **Agent 1 verified:** the only per-occupation data published is **list
  membership** (NSW 79+78 at 4-digit, QLD 120 at 6-digit); WA is search-gated, SA
  is closed, VIC is 403 [A1 §11, §12]. No fee/points/decision-time figures were
  found on any state page.
- **Change:** split into (a) `state_program_status(state_code, visa_code, status,
  fee, points_minimum, …, as_of_date)` at **program** grain — where those columns
  actually live — and (b) `state_occupation_list(state_code, visa_code,
  occupation_code, code_level, as_of_date)` at **occupation** grain, which is what
  the sources actually serve. Add `visa_code` to both (I11).

### F12 — Control-plane fixes forced by the API-shaped sources. MAJOR

- **Design:** `source_pages.url` UNIQUE; `status IN
  ('active','dead','redirected')` [DM C5, CODE].
- **Agent 1 verified:** POST-body-parameterised APIs (76 calls on one URL)
  [A1 §8]; a soft-404 returning 200 [A1 §14]; a 403 Cloudflare challenge
  [A1 §11]; a legitimately empty page from a paused program [A1 §12];
  `pageModified` present on nearly every immi page [A1 §2–§8].
- **Change:** key the registry on `(url, request_fingerprint)` where the
  fingerprint hashes method+body (matching `resources.locator` [DM A2]); extend
  the status enum with `blocked` and `no_data`/`empty` (Agent 1 explicitly asks
  for the "program closed" vs "parser broke" distinction); add
  `source_last_modified TIMESTAMPTZ` for `pageModified`; and consider an
  `official_api` reliability tier (I24).

---

## Prioritised gap list for Agent 3

Each item is a specific, searchable question with the grain and coverage koshi
needs. **P1** = blocks a table entirely, **P2** = table buildable but materially
wrong/incomplete, **P3** = enrichment. Where I have a candidate lead it is marked
as a **lead to verify**, never as a fact — neither I nor Agent 1 fetched these.

### P1 — Blockers

**G1. ANZSCO occupation *name* → 6-digit *code* crosswalk.**
Where can we get an authoritative mapping from occupation **title** to ANZSCO
6-digit code, covering at minimum the ~140 occupation names SkillSelect publishes
per invitation round (verified examples: "Actuary", "Agricultural Consultant",
"Architect", "Barrister", "Carpenter") [A1 §2]? Needs: full coverage of the
ANZSCO title set, machine-readable, with a stated ANZSCO edition.
**Leads to verify:** (a) `legislation.gov.au/F2024L01616` — *Migration (ANZSCO
Definition) Specification 2024* — Agent 1 confirmed it is live and uses the same
iframe→epub pattern but **did not open its tables** [A1 §9]; (b) LIN 19/051's own
Table 5, which pairs 504 occupation **names** with codes [A1 §9] — good coverage
but not necessarily all 140 round names; (c) an ABS ANZSCO code list.
**Without this, `eoi_rounds`, `occupation_momentum` and the Occupation API are
blocked (I1).**

**G2. Per-occupation invitation ceilings and issued-to-date.**
Does Home Affairs still publish **occupation ceilings** (per ANZSCO occupation,
per program year, with invitations issued against them), and if so at what URL
and in what format? Agent 1 verified they are **not** on the SkillSelect page
(prose only) or the planning-levels page (visa-category grain only) [A1 §2, §3].
Needs: `(occupation_code, program_year, ceiling, issued, as_of_date)`.
**Leads to verify:** a SkillSelect "occupation ceilings" sub-page or PDF;
data.gov.au SkillSelect/EOI datasets; the Migration Program Report series.
**If it genuinely no longer exists, say so explicitly** — then `ceiling_usage`
must be retired or its two seeded rows removed, because they currently cite a
page that does not contain them (I3).

**G3. English test score → band → points mapping.**
Where is the official table mapping each accepted English test (IELTS, PTE
Academic, TOEFL iBT, Cambridge C1 Advanced, OET) to the bands *Functional /
Vocational / Competent / Proficient / Superior* with **per-skill score
thresholds**? The catalogued Home Affairs english-language page has zero tables
[A1 §7]; `/points-table` gives only band→points for 3 bands [A1 §5]. Needs
`(test_name, band_level, score_requirement, points_awarded)` plus, ideally,
validity period.
**Leads to verify:** a Home Affairs "English language requirement" page listing
test scores per visa; a legislative instrument specifying English language tests
and scores (search legislation.gov.au for "specification of English language
tests"). **Blocks `english_test_bands` (F5).**

### P2 — Material incompleteness

**G4. ANZSCO ↔ OSCA correspondence file.**
Is there an official ABS/JSA correspondence table mapping **ANZSCO 2022 6-digit →
OSCA 2024 6-digit** (and 4-digit unit groups), including one-to-many and
many-to-one relationships? Needs a downloadable file (CSV/XLSX) with both code
sets and a relationship type. Verified context: OSCA has **1,577** entries vs
ANZSCO's **1,236** [A1 §1], and JSA already dual-publishes ratings under both
[A1 §10] — but no crosswalk was found. **Required before F3 can be executed
safely.**

**G5. Complete visa-subclass registry with permanence/family classification.**
Is there a machine-readable list of all Australian visa subclasses with
**name, permanence (permanent/provisional/temporary) and family/category**?
The fee API already yields 150 `visaSubclassCode`/`visaSubclassText` pairs
[A1 §4] — that solves code+name; the gap is the classification attributes and a
confirmation that the fee list is a *complete* subclass registry rather than a
priced subset. Needed to make `visa_subclasses` a viable FK parent for 76
processing-time rows (I4, F10).

**G6. State nomination program attributes and the three unreachable states.**
Four sub-questions, all at `(state, visa_code)` grain unless noted:
(a) **Fees, minimum points, job-offer requirement, decision-time estimates and
document checklists** for NSW/VIC/QLD/WA/SA — Agent 1 found none of these on any
state page [A1 §11].
(b) **WA's full eligible-occupation list** — the Views search form returns
"Displaying 0 occupation(s)" by default and the catalog's
`#2025-26-eligible-occupations` anchor does not exist; is there a downloadable
PDF/CSV of WA's list, or a documented query parameter? [A1 §11, §12]
(c) **VIC's occupation list without Cloudflare** — `liveinmelbourne.vic.gov.au`
403s [A1 §11]; is the Victorian skilled occupation list published anywhere else
(a PDF, a vic.gov.au mirror, an official media release)?
(d) **SA** — confirm the program is paused and find the date/trigger for the
2026-27 reopening, so koshi can distinguish "closed" from "broken" [A1 §12].

**G7. Historical compilations of LIN 19/051 (for change detection).**
How do we enumerate **all prior compilations** of `F2019L00278` with their
compilation dates and epub URLs, so membership can be diffed into
`list_change_log`? Agent 1 resolved only the current compilation (`2026-03-28`)
and confirmed the register serves compilations, not diffs [A1 §9].
Sub-question: does the instrument's own **amendment history** (epub tables 7–11,
content unopened [A1 §9]) give per-amendment effective dates that would supply
`effective_date` directly? Needed for F4/I12.

**G8. Assessing body turnaround times and costs.**
For the **38 bodies** in LIN 19/051 Table 6 [A1 §9] — where are per-body
**assessment turnaround estimates and fees** published? These exist on each
body's own site (ACS, Engineers Australia, VETASSESS, ANMAC, CPA, …), so the
question is whether any single aggregated source exists, or whether this is
irreducibly 38 separate curation targets. Determines whether
`assessing_bodies.turnaround_estimate`/`cost` ship NULL (F2).

**G9. Visa grants by subclass and program year (`granted_count`).**
Does any Home Affairs annual report contain a **pathway-level (per-subclass)
grant breakdown**? Agent 1 enumerated 44 report PDFs but opened none [A1 §16].
If not, where else are per-subclass grant counts published? Needs
`(visa_code, program_year, granted_count)`.
**Leads to verify:** the 2024–25 annual report PDF itself; Home Affairs
migration-program statistics pages; data.gov.au migration datasets; Budget
Paper 3. **If nothing exists, confirm the design's fallback (ship NULL).**

**G10. EOI submitted / pool-on-hand counts (`submitted_count`).**
Where, if anywhere, are **EOIs submitted or EOIs on hand** published? Agent 1
searched the entire decoded SkillSelect page for `submitted`, `lodged`, `EOIs on
hand`, `EOIs in the system`, `pool` — **zero matches** [A1 §2/§15]. Needs
`(visa_code, points_range or occupation, as_of_date, count)`.
**Lead to verify:** data.gov.au has historically carried SkillSelect EOI
datasets — confirm whether a current one exists.

**G11. JSA rating vocabulary definitions.**
What do the shortage rating codes **`R`, `M`** and the lowercase **`Ns`** mean in
JSA's `splData` JSON? `NS`=Not in Shortage and `S`=Shortage are clear from
context; the glossary modal is JS-populated and was not in the static HTML
[A1 §10]. Also: is `NS` vs `Ns` a genuine distinction or a casing bug? And is
**future demand** (the null `d` field) published in a separate JSA dataset —
e.g. an employment-projections release? Determines the CHECK constraint in F7.

### P3 — Enrichment / lower priority

**G12. Points tables for visas other than 189.**
Is there an equivalent `/points-table` page for **190 and 491** (state-nomination
and family-sponsored points), or a single instrument specifying the whole GSM
points test? The 11 sections Agent 1 enumerated on the 189 points table do not
include state nomination [A1 §5]. Needed to give `points_criteria_reference` a
visa dimension (I20).

**G13. Replacement anchors for `policy_events`.**
(a) Which 2026–27 Budget Paper (BP1–BP4) actually carries migration planning
levels, now that `budget.gov.au/content/migration.htm` is a soft-404 [A1 §14]?
(b) Is there a stable, machine-readable index (RSS/JSON/paginated list) of
**ministerial media releases** under `minister.homeaffairs.gov.au` that could
drive `policy_events` semi-automatically instead of pure manual curation?
Note: C15's numbers no longer depend on budget.gov.au at all [A1 §3], so the
honest answer may be "drop this source" (I21).

**G14. Companion instrument contents.**
Fetch and characterise the tables inside `F2024L01618` (subclass 186 occupations
+ assessing authorities) and `F2024L01616` (ANZSCO Definition). Agent 1 confirmed
both are reachable and resolved their epub URLs but explicitly left their
row/column content **UNVERIFIED** [A1 §9]. F2024L01616 overlaps directly with G1.

**G15. Processing-times data cadence and as-of date.**
Does Home Affairs state anywhere **when** the processing-time percentiles were
last recalculated, or over what application window they are computed? Agent 1
could not confirm the refresh cadence ("plausibly monthly per catalog, not
verified") and the API returns no date [A1 §8]. Determines whether F1's
`as_of_date` can be honest.

**G16. Per-occupation labour-market detail.**
The JSA occupation cards expose "Employed" and "Median weekly earnings", and each
card links to a **per-occupation detail sub-page that Agent 1 did not fetch**
[A1 §1]. If koshi wants employment/earnings/outlook per occupation, what does
that sub-page serve, and is there a bulk dataset rather than 1,236 sub-page
fetches? (O7.)

---

## Appendix — what exists today vs. what this document maps

For separating "planned" from "real" [docs/ARCHITECTURE.md, CODE]:

| Reality | Detail |
|---|---|
| Tables built | **5** of 29: `source_pages`, `occupations`, `eoi_rounds`, `ceiling_usage`, `occupation_momentum` (migrations `0001`–`0006`) |
| Parsers built | **2**, both broken against the live pages — `anzsco_occupations.py` expects `<table id="occupation-list">`, `skillselect_rounds.py` expects `<table id="round-results">` plus a `"Round date:"` string; Agent 1 confirms none of these exist in the raw HTML [A1 §1, §2] |
| Control plane | **0** of 6 tables built |
| Data plane | **0** of 5 tables built (no `snapshots`, no `pipeline_runs`, no `quarantine`) |
| Seeds | 1 file, 2 rows (`ceiling_usage_manual.yaml`) — provenance disputed (I3) |
| Target tables with a fully-covered source today | `program_allocation`, `points_criteria_reference`, `eligibility_requirements` (+ `occupation_assessing_bodies` with normalization) — **none of which are built** |

**Suggested build-order revision (evidence-based).** The tables with full,
verified, static column coverage — `program_allocation` [A1 §3],
`points_criteria_reference` [A1 §5], `eligibility_requirements` [A1 §7] and
`assessing_bodies`/`occupation_assessing_bodies` [A1 §9] — plus the two clean
JSON APIs (`visa_fees` F6, `processing_times` F1) are all buildable **now**
without waiting on Agent 3. Everything gated on G1/G2/G3 (`eoi_rounds`,
`occupation_momentum`, `ceiling_usage`, `english_test_bands`) should not be
scheduled until those gaps resolve.

---

## Document history

| Date | Change |
|---|---|
| 2026-08-17 | Initial — Agent 2 schema↔source mapping: column-level coverage for all 18 domain tables, 18 orphan sources (O1–O18), 24 integrity findings (I1–I24), 12 forced schema changes (F1–F12), 16 prioritised gaps for Agent 3 (G1–G16). |
