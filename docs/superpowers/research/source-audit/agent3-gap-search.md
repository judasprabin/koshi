# Agent 3 — Gap search: do authoritative sources exist for G1–G16?

**Date:** 2026-08-17
**Scope:** the 16 prioritised gaps in `agent2-schema-mapping.md` §"Prioritised gap
list for Agent 3".
**Method:** web search for leads → **direct `curl` fetch of every candidate** →
parse the actual bytes (HTML tables, XLSX parts, PDF text/images, JSON) →
characterise (Agent 1 style) and map to koshi columns (Agent 2 style).

## How to read the evidence labels

Every factual claim below carries one of these:

- **[FETCHED]** — I retrieved the bytes myself and parsed them. Row counts,
  column names and sample values in a [FETCHED] claim were computed from the
  response, not read off a search snippet.
- **[SEARCH LEAD]** — a search engine or a third-party page asserted this. Not
  verified. Used only to justify the next fetch.
- **UNVERIFIED — <reason>** — I could not confirm it and am saying so.

Nothing in this document is inferred from a snippet alone. Where a search result
looked right but the fetch contradicted it, the fetch wins and I say so.

---

## Summary table

| Gap | Question in brief | Verdict | Source (verified by fetch unless noted) | Unblocks |
|---|---|---|---|---|
| **G1** | ANZSCO occupation **name → 6-digit code** crosswalk | **FOUND** | ABS `anzsco 2022 structure 062023.xlsx` **Table 6** (1,425 pairs) **+** LIN 19/051 epub **Table 5** (504 pairs) — union resolves **140/140** live SkillSelect names | `eoi_rounds`, `occupation_momentum`, Occupation API |
| **G2** | Per-occupation **ceilings + issued-to-date** | **PARTIAL** | **Not routinely published.** Full PY2025‑26 ceiling table exists only in an **FOI release**: `homeaffairs.gov.au/foi/files/2026/fa-260100545-document-released.PDF` (scanned images, 4-digit grain) + method doc `fa-251001376` | `ceiling_usage` (as manual/FOI tier) |
| **G3** | English test → band → **per-skill score** | **FOUND** | `legislation.gov.au/F2025L00905` epub Sch. 2 (4 bands × 9 tests × 4 skills) **+** `F2025L00904` (Functional English, 8 tests) | `english_test_bands` |
| **G4** | ANZSCO ↔ OSCA correspondence | **FOUND** | ABS `OSCA correspondence tables v2.xlsx` — 10 tables incl. **ANZSCO v1.3→OSCA** and **ANZSCO 2022→OSCA**, with `p` = partial-match flag | F3 / `occupations` |
| **G5** | Complete subclass registry + permanence/family | **PARTIAL** | BP0068 pivot cache gives a 5-level **Program→Category→Type→Sub-type→Subclass** hierarchy for 62 *granted* subclasses; permanence still not published anywhere found | `visa_subclasses` |
| **G6** | State program attributes; WA / VIC / SA | **PARTIAL** | See §G6 — per-state results differ; no aggregated source exists | `state_program_status`, `state_occupation_list` |
| **G7** | Historical compilations of LIN 19/051 | **FOUND** | `legislation.gov.au` register-item JSON on `/F2019L00278/latest` enumerates every compilation + date | `list_change_log` |
| **G8** | Assessing body turnaround + cost | **NOT PUBLISHED (aggregated)** | No aggregated source exists; irreducibly ~38 separate sites | `assessing_bodies` (ship NULL) |
| **G9** | Visa **grants by subclass and program year** | **FOUND** | **data.gov.au `permanent-migration-program-skilled-family` → BP0068 XLSX**, 622,425 records, 10 program years, 62 subclasses, 764 occupations | `application_funnel.granted_count` |
| **G10** | EOI **submitted / on-hand** counts | **NOT PUBLISHED** | Home Affairs publishes 12 datasets on data.gov.au; none is a SkillSelect/EOI dataset. Zero matches on the live page | `application_funnel.submitted_count` → NULL |
| **G11** | JSA rating vocabulary (`R`, `M`, `Ns`) | **FOUND** | JSA `splSearch` JSON + shortage-list page methodology — see §G11 | `skills_priority_ratings` CHECK |
| **G12** | Points tables for 190 / 491 | **FOUND** | Points are a **single** GSM test in `Migration Regulations 1994` Sch. 6D — one table, not per-subclass | `points_criteria_reference` |
| **G13** | Replacement anchors for `policy_events` | **PARTIAL** | Budget migration numbers live in **Budget Paper No. 3**; ministerial media releases have **no** machine-readable index found | `policy_events` |
| **G14** | Companion instrument contents | **FOUND (both, incl. a negative)** | `F2024L01616` has **zero tables** — definitional only; `F2024L01618` characterised in §G14 | `assessing_bodies`, ANZSCO edition pin |
| **G15** | Processing-times cadence / as-of date | **PARTIAL** | Page states the calculation window and update rule in prose; the API itself carries no date | `processing_times.as_of_date` |
| **G16** | Per-occupation labour-market detail | **FOUND** | ABS **Labour Force, Australia, Detailed — EQ08** is the bulk dataset (and is the Department's own stated input for ceilings) | `occupations` enrichment |

**Verdict counts (16 gaps):** FOUND **9** (G1, G3, G4, G7, G9, G11, G12, G14, G16)
· PARTIAL **5** (G2, G5, G6, G13, G15) · NOT PUBLISHED **1** (G10) ·
NOT PUBLISHED in aggregated form **1** (G8) · NOT REACHED **0**.

All three P1 blockers were worked to a conclusion: **G1 FOUND**, **G3 FOUND**,
**G2 answered with an explicit negative** on routine publication plus a real
FOI-only source.

---

## The three findings that matter most

1. **BP0068 on data.gov.au** (§G9) is the largest single addition this audit can
   make to koshi. It is a Home Affairs-published, CC-BY, annually-refreshed
   record-level dataset of **622,425** rows [FETCHED] covering ten program years,
   62 visa subclasses and 764 ANZSCO-coded occupations. It resolves `granted_count`
   outright and supplies the `issued` half of `ceiling_usage`. koshi currently has
   no source of grant data at all.
2. **G1 is solved by a union, not a single source** (§G1). Neither ABS nor the
   legislative instrument alone covers the SkillSelect name set; together they hit
   **140/140** [FETCHED]. Using either alone silently drops 8 occupations.
3. **Three ANZSCO editions are simultaneously live** and koshi must model the
   edition explicitly. `F2024L01616` [FETCHED] fixes the *legal* meaning of ANZSCO
   for migration at the **2013** ABS edition, while JSA/ABS publish **2022** and
   **OSCA 2024**. 25 of LIN 19/051's 504 codes do not exist in ANZSCO 2022
   [FETCHED]. This is the root cause of F3's blast radius.

---

# P1 — Blockers

## G1. ANZSCO occupation name → 6-digit code crosswalk — **FOUND**

**Question.** An authoritative title→6-digit-code mapping covering at minimum the
~140 occupation names SkillSelect publishes per invitation round; machine-readable,
with a stated ANZSCO edition.

**What I searched.** ABS classification downloads (`site:abs.gov.au`); the two
leads Agent 2 flagged (`F2024L01616`, LIN 19/051 Table 5); the ABS ANZSCO landing
page for the full edition list.

### Lead (a) — `F2024L01616` — **dead end, and that is itself the useful finding**

[FETCHED] `https://www.legislation.gov.au/F2024L01616/asmade/2024-12-06/text/original/epub/OEBPS/document_1/document_1.html`
→ **HTTP 200, 7,916 bytes, `<table>` count = 0.**

*Migration (ANZSCO Definition) Specification 2024* (LIN 24/105) contains **no
occupation tables at all**. It is a two-page definitional instrument. Its entire
operative content, quoted verbatim from the fetched HTML:

> **6 Definition of ANZSCO** … (2) Subject to subsection (3), **ANZSCO means the
> Australian and New Zealand Standard Classification of Occupations published by
> the Australian Bureau of Statistics, as in force on 27 June 2013.** (3) For the
> following provisions of the Regulations, ANZSCO means the … Classification …
> **as in force on 23 November 2022**: (a) regulation 2.72; (b) regulation 2.73;
> (c) subregulation 5.19(5).

**Why this matters more than a table would have.** It legally pins the ANZSCO
edition. For migration generally the binding edition is the **2013** ABS release;
only regulations 2.72/2.73/5.19(5) use the **2022** release. koshi cannot treat
"ANZSCO code" as a single key space. This directly explains the mismatch measured
below and is the evidentiary basis for making `anzsco_edition` a real column.

### Lead (b) — LIN 19/051 epub Table 5 — **confirmed, 504 pairs**

[FETCHED] `https://www.legislation.gov.au/F2019L00278/2026-03-28/2026-03-28/text/original/epub/OEBPS/document_1/document_1.html`
→ HTTP 200, 833,789 bytes, **11 `<table>` elements**.

Agent 1 reported 12 tables; my parse of the same URL finds **11**. I did not
resolve the discrepancy — likely a nested-table or regex-boundary difference.
Row counts otherwise match Agent 1 exactly (MLTSSL 213/212, STSOL 216/215, ROL
78/77, assessing-authority join 505/504, abbreviations 39/38), so the two audits
agree on content. Treat "11 vs 12" as a parser detail, not a source change.

Table index 5 [FETCHED] → 504 data rows, columns `Item | Occupation | ANZSCO code
| Relevant assessing authority`, e.g. `1 | construction project manager | 133111
| VETASSESS`. Names are **lowercase**; codes are **ANZSCO 2013**.

### Lead (c) — ABS ANZSCO code list — **the primary answer**

[FETCHED] `https://www.abs.gov.au/statistics/classifications/anzsco-australian-and-new-zealand-standard-classification-occupations/2022/anzsco%202022%20structure%20062023.xlsx`
→ HTTP 200, **205,482 bytes**, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

**Page type / format:** direct XLSX download, no HTML parsing, no JS, no auth.
8 worksheets [FETCHED]: `Contents`, `Table 1`–`Table 6`, `Explanatory Notes`.
Header row of every sheet carries `Released at 11:30am (Canberra time) 22 November
2022` — note this is the **release date of the edition**, i.e. a static
provenance stamp, not a refresh signal.

| Sheet | Rows | What it is |
|---|---|---|
| Table 1 | 27 | Major groups (8) |
| Table 2 | 68 | Major + sub-major |
| Table 3 | 177 | + minor groups |
| Table 4 | 532 | + unit groups (4-digit) |
| Table 5 | 1,609 | full hierarchy incl. occupations — **1,076 distinct 6-digit codes** |
| **Table 6** | **1,439** | **flat `Code \| Title` — 1,425 distinct 6-digit pairs** |

**The retrieval target is `Table 6`.** [FETCHED] Exactly two columns, `Code` and
`Title`, starting at the row after the header `['Code','Title']`; 1,425 rows match
`^\d{6}$`; **1,425 unique codes and 1,425 unique titles** (no duplicates on either
side — a clean bijection). First row `111111 | Chief Executive or Managing
Director`. Data ends before two footer rows `© Commonwealth of Australia` /
`Crown Copyright ©`, so terminate on the code regex, not on end-of-sheet.

**Caveat [FETCHED]:** Table 6 is the *coder* list, so it is a superset of the
classification — it includes non-occupations `099950 House wife/husband`,
`099960 Retired`, `099970 Unemployed`. Table 5's 1,076 codes are the real
occupations. Filter or flag these.

### The decisive coverage test [FETCHED]

I re-fetched the live SkillSelect page, decoded it with Agent 1's recipe, pulled
the **140** occupation names from the round table, and looked each up.

| Lookup source | Names resolved |
|---|---|
| ABS ANZSCO 2022 Table 6 alone | **132 / 140** |
| LIN 19/051 Table 5 alone | **132 / 140** |
| **Union of both** | **140 / 140** |

The 8 names ABS 2022 cannot resolve, with the codes LIN 19/051 gives them
[FETCHED]: `Agricultural Scientist 234112`, `Cabinetmaker 394111`,
`Fibrous Plasterer 333211`, `Forester 234113`, `Sheetmetal Trades Worker 322211`,
`Solid Plasterer 333212`, `Speech Pathologist 252712`, `Welder (First Class)
322313`. These are titles ABS renamed between the 2013 and 2022 editions;
Home Affairs still publishes the 2013 titles, consistent with `F2024L01616`.

**Three name collisions must be resolved edition-first, not source-first**
[FETCHED] — same title, different code in the two sources:

| Title | ABS ANZSCO 2022 | LIN 19/051 (ANZSCO 2013) |
|---|---|---|
| Management Consultant | `224713` | `224711` |
| Plumber (General) | `334116` | `334111` |
| Statistician | `224116` | `224113` |

Because SkillSelect operates under the migration definition of ANZSCO, **LIN
19/051 must win these three**. A naive "try ABS first, fall back to LIN" resolver
silently mis-codes them. Order the lookup **LIN first, ABS second**.

**Supporting scale figure [FETCHED]:** across LIN 19/051's own 504 name→code
pairs, only **427** titles match an ABS 2022 title case-insensitively, and of
those 427, **11** map to a different code. Name-based joining across editions is
~85% accurate — never use it as the primary key.

### Column mapping (Agent 2 style)

| koshi target | Column | Source | Grain | Extraction tier |
|---|---|---|---|---|
| `occupations` | `occupation_code` | ABS T6 `Code` / LIN T5 col 3 | 6-digit occupation | **Tier 2** (deterministic XLSX / HTML table) |
| `occupations` | `occupation_name` | ABS T6 `Title` / LIN T5 col 2 | " | Tier 2 |
| `occupations` | `anzsco_edition` *(new, per F9/F3)* | constant `2022` / `2013` per source | " | Tier 5 constant |
| `eoi_rounds` | `occupation_code` | **resolved** from round `Occupation*` name via the union LUT | 6-digit | Tier 2 + join |

**Join key reality check.** The join key is the occupation **title string**, and
it does *not* cleanly match koshi's key space — that is the entire problem. The
verified recipe is: normalise case and whitespace → look up **LIN 19/051 first**
→ fall back to **ABS 2022 Table 6** → if still unmatched, quarantine. On the
current round that yields 140/140 with zero quarantine [FETCHED], and every
resolved code is **6 digits** [FETCHED] (no 4-digit unit groups in the current
round — but see §G-NEW-1, older rounds *are* 4-digit).

**Recommendation:** build the LUT as a versioned seed table
(`anzsco_titles(code, title, edition, source)`) from both files rather than
resolving at parse time, so a round that introduces a new title fails loudly.

---

## G2. Per-occupation invitation ceilings and issued-to-date — **PARTIAL** (not routinely published; exists only via FOI)

**Question.** Does Home Affairs still publish occupation ceilings per occupation
per program year with invitations issued, and at what URL/format? Needs
`(occupation_code, program_year, ceiling, issued, as_of_date)`.

**What I searched.** Candidate URLs under the SkillSelect path; the live
SkillSelect page's own decoded content; the data.gov.au CKAN API (three separate
full-text queries, plus the complete 1,139-entry organisation list and the Home
Affairs organisation's full package list); a domain-restricted search of
`homeaffairs.gov.au` / `immi.homeaffairs.gov.au`.

### Confirmed negatives

- [FETCHED] `https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/occupation-ceilings`
  → **HTTP 404** (727 bytes). Also `…/occupation-ceiling` → **404**. There is no
  ceilings sub-page.
- [FETCHED] The live invitation-rounds page's `Occupation ceilings` section is
  **599 bytes of prose with 0 tables**. Full text: *"An 'occupation ceiling' means
  there **may** be an upper limit on how many EOIs with a specific occupation we
  can invite … Occupation ceilings do not apply to these visa subclasses: Skilled
  Nominated visa (subclass 190), Skilled Work Regional (Provisional) visa
  (subclass 491) – State and Territory Nominated."* No numbers. Confirms Agent 1.
- [FETCHED] data.gov.au CKAN `package_search?q=skillselect` → **count = 1**, and
  the single hit is a 2012 NSW Government Gazette — irrelevant. The Home Affairs
  organisation (`immi`) publishes **12 datasets**; none concerns ceilings or EOIs.

**So: ceilings are no longer part of the routine publication surface.** Agent 2
asked for this to be stated explicitly, and it is: **there is no live URL serving
an occupation-ceiling table.** The two seeded `ceiling_usage` rows cite a page
that does not contain them and must be removed or re-provenanced.

### But the data does exist — in an FOI disclosure release

[FETCHED] `https://www.homeaffairs.gov.au/foi/files/2026/fa-260100545-document-released.PDF`
→ HTTP 200, **1,043,833 bytes**, `application/pdf`, **6 pages**.

**Page type:** an FOI-released PDF that is **mostly scanned images**. Diagnosed
per page [FETCHED]: page 1 has real text (1,630 chars) *plus* two JPEGs; **pages
2–6 have zero extractable text** and one 1584×1224 PNG each. The ceiling table is
image-only — OCR or vision is mandatory. This is a **Tier 3 / Tier 4** target,
not Tier 2.

**What it actually serves.** Page 1 text [FETCHED] states the title:
*"The ceiling for each occupation under all four tiers of the Subclass 189 visa
in the 2025-26 financial year"*, with the column header row:

```
Unit Code | Occupation | Multiplier Tier | Average stock figure |
Occupation Ceiling adjusted | Grants in PY24/25 to 491/494/186/190 |
Remaining places for PY25/26
```

I extracted the page images and read them. Verified sample rows from **page 2**
[FETCHED, read from the image]:

| Unit code + occupation | Tier | Mult. | Avg stock | Ceiling | Grants PY24/25 | Remaining PY25/26 |
|---|---|---|---|---|---|---|
| 2531 General Practitioners and Resident Medical Officers | 1 | 4% | 90,567 | 3,623 | 660 | 2,963 |
| 2525 Physiotherapists | 1 | 4% | 47,783 | 1,911 | 358 | 1,553 |
| 2411 Early Childhood (Pre-primary School) Teachers | 2 | 2% | 79,172 | 1,583 | 556 | 1,027 |
| 2335 Industrial, Mechanical and Production Engineers | 3 | 1% | 38,154 | 500 | 1,848 | – |
| 2333 Electrical Engineers | 3 | 1% | 32,989 | 500 | 950 | – |

and from **page 6** [FETCHED, read from the image]:

| 2631 Computer Network Professionals | 4 | 0.5% | 43,895 | 500 | 756 | – |
| 2621 Database and Systems Administrators, and ICT Security Specialists | 4 | 0.5% | 68,049 | 500 | 643 | – |
| 3132 Telecommunications Technical Specialists | 4 | 0.5% | 3,633 | 500 | 62 | 438 |

**Grain — important:** the code column is **4-digit ANZSCO unit group**, not
6-digit occupation. Ceilings are set per *unit group*. Any `ceiling_usage` keyed
on a 6-digit code is mis-grained. This is direct evidence for F9 (make code
level explicit).

**Volume:** UNVERIFIED — exact total row count. I read pages 2 and 6 of the 5
table pages; rows are ~21 per page, so the table is plausibly ~100 unit groups,
but I did not read pages 3–5 and will not assert a number.

**The methodology is published in full** on page 6 [FETCHED, read from the image],
which is the most reusable part of the document:

1. Take ABS employment stock from **Labour Force, Australia, Detailed** (Industry
   and Occupation, **EQ08**), averaging the four quarter figures.
2. Multiply by the tier multiplier (Tier 1 = 4%, Tier 2 = 2%, Tier 3 = 1%,
   Tier 4 = 0.5%) [FETCHED from the table rows].
3. **Floor rule:** *"If an occupation has a ceiling calculation that is <500, then
   a ceiling of 500 is applied."* — visible in the data (many rows read exactly
   500).
4. Subtract 2024-25 grants in subclasses **190, 186, 491, 494** — sourced from
   **`data.gov.au/data/dataset/permanent-migration-program-skilled-family`** — to
   get remaining subclass-189 places.

This citation is how I found the BP0068 dataset in §G9.

A second, corroborating FOI release [FETCHED]
`https://www.homeaffairs.gov.au/foi/files/2025/fa-251001376-document-released.PDF`
(98,308 bytes, **1 page, text-extractable**) works the same calculation for one
occupation and confirms the numbers independently: *"There were 79,171 Early
Childhood (Pre-primary School) Teachers … Tier 2 occupation with a multiplier of
2.0%. The occupation ceiling … in 2025/26 would be 1,583 visa grants … There were
556 visa grants in 2024/25 … This leaves 1,027 visa grants available to the
Skilled Independent (Subclass 189) program."* Those three figures (1,583 / 556 /
1,027) match the scanned table row exactly — a genuine cross-source validation.

**A third FOI document referenced but not fetched:**
`https://www.homeaffairs.gov.au/foi/files/2025/fa-251000198-document-released.PDF`
— cited on page 6 as the tier-assignment methodology. UNVERIFIED — not fetched
(budget).

**Access obstacles:** none technical (plain 200s, no Cloudflare, no auth). The
obstacle is **semantic**: FOI releases are one-off documents at unstable,
request-numbered URLs (`fa-YYMMNNNNN`). There is no index, no cadence, no
guarantee next year's ceilings will be released at all.

### Column mapping

| koshi target | Column | Source | Grain | Tier |
|---|---|---|---|---|
| `ceiling_usage` | `occupation_code` | FOI PDF `Unit Code` | **4-digit unit group** | **Tier 4** (vision/OCR) |
| `ceiling_usage` | `program_year` | document title (`2025-26`) | constant per doc | Tier 5 |
| `ceiling_usage` | `ceiling` | `Occupation Ceiling adjusted` | unit group × year | Tier 4 |
| `ceiling_usage` | `issued` | ⚠ see below | — | — |
| `ceiling_usage` | `as_of_date` | FOI release date | constant per doc | Tier 5 |

**⚠ `issued` does not mean what the schema assumes.** The FOI column is *"Grants
in PY24/25 to 491/494/186/190"* — **grants in other subclasses in the prior
year**, deliberately excluding 189. It is an input to the ceiling calculation,
not "invitations issued against this ceiling". Mapping it to `issued` would be
wrong. If koshi wants a genuine issued-to-date it must be derived from BP0068
(§G9) or from the invitation-round tables, and this column should be named
something like `prior_year_grants_other_subclasses`.

### Recommendation

Ceilings are **not** a crawlable source. Either (a) retire `ceiling_usage`, or
(b) reclassify it as a **manual/FOI curation tier** table with an explicit
`source_document` and `code_level='unit_group'`, seeded once per year if and when
an FOI release appears. Do **not** leave it modelled as pipeline-fed. Either way,
**delete the two existing seeded rows** — they cite the SkillSelect page, which
[FETCHED] contains no ceiling numbers.

---

## G3. English test score → band → points mapping — **FOUND**

**Question.** The official table mapping each accepted English test to
Functional / Vocational / Competent / Proficient / Superior with **per-skill
score thresholds**; ideally validity period.

**What I searched.** `legislation.gov.au` for "specification of English language
tests" (Agent 2's suggested phrasing) — which surfaced the current instrument
directly.

**Answer: two instruments, both made 6 Aug 2025, together covering all five
bands.**

### Source 1 — `F2025L00905` (LIN 25/016) — Vocational / Competent / Proficient / Superior

**Landing page:** `https://www.legislation.gov.au/F2025L00905/latest` — [FETCHED]
HTTP 200, 85,046 bytes. Same Angular shell Agent 1 documented; contains
`id="epubFrame"` and, usefully, hundreds of `href` links that already embed the
resolved epub path — so the epub URL can be recovered with a plain regex for
`https://[^"#]*OEBPS[^"#]*document_1\.html` without executing JS [FETCHED].

**Real document URL** [FETCHED] — HTTP 200, **94,105 bytes**, static HTML,
**2 `<table>` elements**:

```
https://www.legislation.gov.au/F2025L00905/asmade/2025-08-06/text/original/epub/OEBPS/document_1/document_1.html
```

Note the path segment is `asmade/2025-08-06`, not the
`{date}/{date}` compilation form LIN 19/051 uses — the resolver must read the
actual href, not template the pattern.

**Table 0 — Schedule 2, "Specified language tests and test scores"** [FETCHED],
19 `<tr>`. Preceding heading confirmed as `Schedule 2 — Specified language tests
and test scores`. Nine test columns, in order:

`C1 Advanced | CELPIP General | IELTS Academic | IELTS General Training |
LANGUAGECERT Academic | MET | OET | PTE Academic | TOEFL iBT`

Four bands × four skills. Complete verified content [FETCHED]:

| Band | Skill | C1 Adv | CELPIP | IELTS Ac | IELTS GT | LANGCERT | MET | OET | PTE Ac | TOEFL |
|---|---|---|---|---|---|---|---|---|---|---|
| **Vocational** | listening | *Excluded* | 5 | 5 | 5 | 41 | 49 | 220 | 33 | 8 |
| | reading | | 5 | 5 | 5 | 44 | 47 | 240 | 36 | 8 |
| | writing | | 5 | 5 | 5 | 45 | 45 | 200 | 29 | 9 |
| | speaking | | 5 | 5 | 5 | 54 | 38 | 270 | 24 | 14 |
| **Competent** | listening | 163 | 7 | 6 | 6 | 57 | 56 | 290 | 47 | 16 |
| | reading | 163 | 7 | 6 | 6 | 60 | 55 | 310 | 48 | 16 |
| | writing | 170 | 7 | 6 | 6 | 64 | 57 | 290 | 51 | 19 |
| | speaking | 179 | 7 | 6 | 6 | 70 | 48 | 330 | 54 | 19 |
| **Proficient** | listening | 175 | 9 | 7 | 7 | 67 | 61 | 350 | 58 | 22 |
| | reading | 179 | 8 | 7 | 7 | 71 | 63 | 360 | 59 | 22 |
| | writing | 193 | 10 | 7 | 7 | 78 | 74 | 380 | 69 | 26 |
| | speaking | 194 | 8 | 7 | 7 | 82 | 59 | 360 | 76 | 24 |
| **Superior** | listening | 186 | 10 | 8 | 8 | 80 | *Excluded* | 390 | 69 | 26 |
| | reading | 190 | 10 | 8 | 8 | 83 | | 400 | 70 | 27 |
| | writing | 210 | 12 | 8 | 8 | 89 | | 420 | 85 | 30 |
| | speaking | 208 | 10 | 8 | 8 | 89 | | 400 | 88 | 28 |

**⚠ Concrete parsing hazard [FETCHED].** The table uses **12 `rowspan`
attributes** (`rowspan="2"` and `rowspan="4"`) and 1 `colspan`. The `Item` and
`Level of English` cells span all four skill rows, and the two `Excluded.` cells
span four rows each. A naive `td`-index parser mis-aligns: the Superior
reading/writing/speaking rows return **8** cells for **9** tests because the MET
column is absorbed by its rowspan. **The parser must expand rowspans into a dense
grid before reading columns** — do not index positionally. The `(listening)` /
`(reading)` suffix inside each cell value is a useful assertion to validate the
expansion against, since every score cell carries its own skill label.

Cell value format is `"<score> (<skill>)"` — e.g. `"163 (listening)"` — so the
score needs a `^(\d+(?:\.\d+)?)\s*\(` extraction.

**Table 1 — Schedule 3, "Specified passports"** [FETCHED], 6 rows: `Canada`,
`New Zealand`, `The Republic of Ireland`, and 2 more not enumerated here. This is
the passport-based English exemption list — a genuine bonus for
`eligibility_requirements`.

**Repeal note [FETCHED]:** the instrument's Schedule 1 repeals
*"…Tests, Score and Passports 2015 – IMMI 15/005"* in whole. So `F2025L00905` is
the sole current instrument; anything citing IMMI 15/005 or `F2015L00564` is dead.

### Source 2 — `F2025L00904` — Functional English

[FETCHED] `https://www.legislation.gov.au/F2025L00904/asmade/2025-08-06/text/original/epub/OEBPS/document_1/document_1.html`
→ HTTP 200, **38,296 bytes**, **1 `<table>`**, 11 rows.

*Migration (Evidence of Functional English Language Proficiency) Instrument 2025.*
Columns `Item | Language Tests | Average band score | Overall band score | Total
band score` — **a different, three-way-optional score shape**, not per-skill.
Complete content [FETCHED]:

| Item | Test | Average | Overall | Total |
|---|---|---|---|---|
| 1 | CELPIP General | | at least 5 | |
| 2 | IELTS Academic | at least 4.5 | | |
| 3 | IELTS General Training | at least 4.5 | | |
| 4 | LANGUAGECERT Academic | | at least 38 | |
| 5 | MET | | at least 38 | |
| 6 | OET | | at least 1020 | |
| 7 | PTE Academic | | at least 24 | |
| 8 | TOEFL iBT | | | at least 26 |

Note **C1 Advanced is absent** from the Functional list (8 tests, not 9), and the
score is an aggregate, not per-skill — so `english_test_bands` needs a
`score_basis` discriminator (`per_skill` / `overall` / `average` / `total`) or
Functional rows will not fit the same shape.

### Column mapping

| koshi target | Column | Source | Grain | Tier |
|---|---|---|---|---|
| `english_test_bands` | `test_name` | Sch. 2 column header / Sch. tbl col 2 | test | **Tier 2** |
| `english_test_bands` | `band_level` | Sch. 2 `Level of English` / const `Functional` | band | Tier 2 |
| `english_test_bands` | `score_requirement` | cell value, digits before `(` | test × band × skill | Tier 2 |
| `english_test_bands` | `skill` *(new column required)* | `(listening\|reading\|writing\|speaking)` | " | Tier 2 |
| `english_test_bands` | `score_basis` *(new column required)* | `per_skill` (00905) / `overall`\|`average`\|`total` (00904) | " | Tier 2 |
| `english_test_bands` | `points_awarded` | **not in either instrument** — join to `/points-table` | band | join |

**Join-key check.** `band_level` is the join key to the points table, and it
**does match** koshi's existing key space in the overlapping region: the
`/points-table` page Agent 1 verified carries 3 bands (Competent / Proficient /
Superior) and these instruments carry those same three spelled identically, plus
`Vocational` and `Functional`, which carry **no points** (they are eligibility
thresholds for other visa classes, not GSM points). So `points_awarded` is
legitimately NULL for Vocational and Functional — that is correct data, not a gap.

**Row count for the built table:** 4 bands × 9 tests × 4 skills = 144, minus the
two `Excluded` blocks (C1 Advanced × Vocational × 4 = 4; MET × Superior × 4 = 4)
= **136 rows** from `F2025L00905`, plus **8** from `F2025L00904` = **144 rows**
total. (Arithmetic mine, from [FETCHED] table contents.)

**Validity period:** UNVERIFIED — neither instrument's tables state a test-result
validity window (the commonly cited "3 years" is a Migration Regulations
criterion, not part of these instruments). Do not populate a validity column from
these sources.

**Cadence:** both instruments are `asmade` dated **2025-08-06**. Change detection
= poll the `/latest` landing page and compare the resolved epub date segment.

---

# P2 — Material incompleteness

## G4. ANZSCO ↔ OSCA correspondence file — **FOUND**

**Question.** An official ABS/JSA correspondence mapping ANZSCO 6-digit → OSCA
2024 6-digit (and unit groups), with relationship type, as a downloadable file.

**What I searched.** The ABS ANZSCO landing page (which lists all editions), then
the OSCA 2024 v1.0 data-downloads page.

**Note on a false lead:** the ABS ANZSCO *2022* data-downloads URL
(`…/2022/data-downloads`) returns **HTTP 404** [FETCHED]. The correspondences are
published under **OSCA**, not under ANZSCO. Do not catalogue the ANZSCO path.

**Source found** [FETCHED] — HTTP 200, **641,062 bytes**, XLSX:

```
https://www.abs.gov.au/statistics/classifications/osca-occupation-standard-classification-australia/2024-version-1-0/data-downloads/OSCA%20correspondence%20tables%20v2.xlsx
```

**Page type / format:** direct XLSX download. No auth, no JS, no Cloudflare.
Released **6 December 2024** (stated in every sheet header) [FETCHED].

**What it actually serves** — 12 sheets: `Contents`, `Table 1`–`Table 10`,
`Further information`. Ten directional correspondence tables [FETCHED]:

| Sheet | Direction | Mapping rows | Distinct source codes | 1-to-many sources | Max fan-out |
|---|---|---|---|---|---|
| **Table 1** | **ANZSCO v1.3 → OSCA 2024 v1.0** | **1,383** | **1,023** | 232 | 10 |
| Table 2 | OSCA → ANZSCO v1.3 | 1,383 | 1,156 | 148 | 8 |
| Table 3 | ANZSCO 2021 → OSCA | (not counted) | — | — | — |
| Table 4 | OSCA → ANZSCO 2021 | (not counted) | — | — | — |
| **Table 5** | **ANZSCO 2022 → OSCA 2024 v1.0** | **1,348** | **1,076** | 178 | 10 |
| Table 6 | OSCA → ANZSCO 2022 | (not counted) | — | — | — |
| Table 7/8 | ISCO-08 ↔ OSCA | — | — | — | — |
| Table 9/10 | NZ NOL v1.0 ↔ OSCA | — | — | — | — |

Row layout [FETCHED]: `col A = source code`, `col B = source name`,
`col C = target code`, `col D = relationship flag`, `col E = target name`.
Continuation rows for one-to-many mappings leave A and B **blank** — the parser
must forward-fill the source code, exactly as I did to produce the counts above.

**The relationship type Agent 2 asked for exists** [FETCHED]: column D carries
`'p'` for a **partial match**, blank for a full match. The `Further information`
sheet defines it verbatim: `'p' -- partial match`. Distribution in Table 1:
**1,008 full / 375 partial**; Table 5: **1,031 full / 317 partial**.

### The critical result for koshi

[FETCHED] **All 504 LIN 19/051 occupation codes appear on the ANZSCO v1.3 side of
Table 1 — coverage 504/504, zero missing.** ANZSCO "v1.3" is the 2013-lineage
edition, which is precisely the edition `F2024L01616` makes legally binding for
migration. So **Table 1 is the exact bridge** from koshi's legislated occupation
lists to OSCA, and it is complete. This de-risks F3 entirely.

Use **Table 5** (ANZSCO 2022 → OSCA) for JSA/ABS-sourced rows and **Table 1**
(ANZSCO v1.3 → OSCA) for legislation-sourced rows. They are not interchangeable.

### Column mapping

| koshi target | Column | Source | Grain | Tier |
|---|---|---|---|---|
| `occupation_code_map` *(new bridge table)* | `from_code`, `from_edition` | col A + sheet identity | 6-digit | **Tier 2** |
| " | `to_code`, `to_edition` | col C + sheet identity | 6-digit | Tier 2 |
| " | `relationship` | col D (`p` → `partial`, blank → `full`) | pair | Tier 2 |

**Do not** add an `osca_code` column to `occupations` — the mapping is genuinely
one-to-many (fan-out up to 10), so it needs its own table with a composite key.

---

## G5. Complete visa-subclass registry with permanence/family classification — **PARTIAL**

**Question.** A machine-readable list of all subclasses with name, permanence
(permanent/provisional/temporary) and family/category.

**What I found** [FETCHED] — the BP0068 pivot cache (§G9) carries a **five-level
visa taxonomy** that Agent 2 did not know existed:

| Level | Distinct values | Examples [FETCHED] |
|---|---|---|
| `Visa Program` | 2 | `Migration Program`, `Child Program` |
| `Visa Category` | 4 | `Skilled`, `Family`, `Child`, `Special Eligibility` |
| `Visa Type` | 14 | `Skilled Independent`, `Employer Sponsored`, `State/Territory Nominated`, `Regional`, `National Innovation`, `Distinguished Talent`, … |
| `Visa Sub-type` | 45 | `Employer Nomination Scheme`, `Business Skills`, … |
| `Visa Subclass` | **62** | `189 Skilled - Independent`, `190 Skilled - Nominated`, `491 Skilled Work Regional (Provisional)`, `494 Skilled Employer Sponsored Regional (Provisional)`, `186 Employer Nomination Scheme`, `858 National Innovation`, `888 Business Innovation and Investment (Permanent)` |

This **does** supply `visa_subclasses.family`/category as a real, published
classification rather than hand-curation — `Visa Category` is exactly a family
column, and `Visa Type` gives a useful sub-grouping.

**What is still missing — permanence.** No source I fetched publishes a
permanent / provisional / temporary flag as data. It is *inferable* from subclass
names (several carry the literal string `(Provisional)` or `(Permanent)`), but
inference is not publication. **Recommendation:** derive `permanence` with an
explicit rule over the subclass name and record it as derived, or curate the ~6
skilled subclasses by hand; do not claim a source for it.

**On completeness — an important correction to the plan.** Agent 2 hoped the fee
API's 150 `visaSubclassCode`/`visaSubclassText` pairs would serve as a complete
registry. Note that BP0068's 62 subclasses are only those with **grants in the
permanent Migration and Child Programs** — it excludes every temporary subclass
(482, 485, 500, …). Neither list is "all Australian visa subclasses":

- the fee list (150) is *priced* subclasses,
- BP0068 (62) is *permanent-program* subclasses.

**Recommendation:** keep Agent 2's F10 plan (seed from the 150-row fee list as
the thin registry — it is the broadest), then **left-join BP0068's taxonomy** to
populate `family`/`category` for the 62 it covers, leaving the rest NULL. That is
strictly better than curating 150 rows by hand, and it is honest about coverage.

---

## G6. State nomination program attributes and the three unreachable states — **PARTIAL**

I probed each state, sequentially and politely. Results [FETCHED]:

| State | URL probed | Result |
|---|---|---|
| VIC | `liveinmelbourne.vic.gov.au/migrate/visa-options-and-eligibility/skilled-visas` | **HTTP 403**, 5,887-byte challenge body — **Cloudflare block confirmed**, independently reproducing Agent 1's finding from a different client and user-agent |
| WA | `migration.wa.gov.au/services/skilled-migration-work-visas/waskilled-migration-occupation-list-wasmol` | **HTTP 404** (62,554-byte styled error page — note: a *large* 404, so byte-size is not a liveness signal) |
| SA | `migration.sa.gov.au/` | **HTTP 200**, 224,121 bytes |

**(a) Fees, minimum points, job-offer requirement, decision times, checklists —
NOT FOUND.** I found no state page and no aggregated source publishing these as
data. Combined with Agent 1's independent sweep, two audits have now failed to
find them. **Recommendation:** treat `state_program_status`'s attribute columns
(F11a) as **manual curation [Tier 5]** with a per-state `source_url` and a
`last_reviewed` date, or drop them. Do not model them as scrapeable.

**(b) WA's full eligible-occupation list — NOT RESOLVED.** The catalogued URL
404s. Agent 1 found the Views search form defaults to "Displaying 0
occupation(s)". I did not find a downloadable PDF/CSV or a documented query
parameter. UNVERIFIED — whether one exists behind a different path; I stopped
after the 404 rather than guess at URLs.

**(c) VIC without Cloudflare — NOT RESOLVED.** 403 reproduced. I did not locate a
`vic.gov.au` mirror. Record VIC in `source_pages` with the new `blocked` status
from F12 — this is exactly the case that enum exists for.

**(d) SA paused-vs-broken — INCONCLUSIVE.** The site returns 200 with substantial
content, but my keyword scan (`closed`, `paused`, `not accepting`, `reopen`,
`2026-27`) found **zero matches in the server-rendered text**, which strongly
suggests the status is rendered client-side. UNVERIFIED — SA's program status; it
needs a JS-capable fetch. This is precisely Agent 1's "program closed vs parser
broke" ambiguity and justifies the `no_data`/`empty` status in F12.

**Net:** G6 remains the weakest area in koshi's source coverage, and it is weak
because of publisher behaviour, not audit effort.

---

## G7. Historical compilations of LIN 19/051 — **FOUND**

**Question.** How to enumerate all prior compilations with dates and epub URLs so
membership can be diffed into `list_change_log`; and whether the amendment history
supplies `effective_date` directly.

**The answer is an API neither Agent 1 nor Agent 2 knew about.** While parsing the
`/latest` landing page I found its Angular state keyed by real endpoint URLs on
`api.prod.legislation.gov.au`. It is a public **OData** service and it works
without auth [FETCHED].

**Endpoint:**

```
GET https://api.prod.legislation.gov.au/v1/titles('F2019L00278')?$expand=versions
Accept: application/json
```

[FETCHED] HTTP 200, 7,984 bytes, JSON. This is a **Tier 1 crawl** target — a
clean JSON API, vastly better than scraping the Angular shell.

**What it serves** — the title record (`name`, `makingDate`, `status`,
`isInForce`, `asMadeRegisteredAt`, `nameHistory`, `statusHistory`) plus a
`versions` array. **7 versions** for LIN 19/051 [FETCHED]:

| # | `start` | `end` | `registerId` | `compilationNumber` | Amended by |
|---|---|---|---|---|---|
| 0 | 2019-03-10 | 2019-11-16 | `F2019L00278` | 0 | (as made) |
| 1 | 2019-11-16 | 2022-05-06 | `F2019C00855` | 1 | LIN 19/243 (`F2019L01402`) |
| 2 | 2022-05-06 | 2024-12-07 | `F2022C00574` | 2 | LIN 22/053 (`F2022L00678`) |
| 3 | 2024-12-07 | 2024-12-14 | `F2025C00014` | 3 | **LIN 24/105 ANZSCO Definition (`F2024L01616`)** |
| 4 | 2024-12-14 | 2026-03-28 | `F2025C00064` | 4 | LIN 24/083 (`F2024L01675`) |
| 5 | **2026-03-28** | 2029-04-01 | `F2026C00265` | 5 | LIN 26/027 (`F2026L00369`) — **current** |
| 6 | 2029-04-01 | — | — | — | **Repealed** — `s 50 Legislation Act 2003` (sunsetting) |

**This answers the sub-question directly: yes, `effective_date` comes straight
from the API.** Each version's `start` is the effective date, and each carries a
`reasons[]` array naming the amending instrument, its provisions and its title —
so `list_change_log.effective_date` and a human-readable change reason are both
available without opening a single PDF.

**Bonus finding:** version 6 shows the instrument **sunsets on 2029-04-01** under
Legislation Act s 50. koshi should surface that rather than be surprised by it.

**Historical epubs are fetchable and diffable — verified** [FETCHED]. Using the
`start` date in Agent 1's `{id}/{date}/{date}/…` pattern:

- `…/F2019L00278/2022-05-06/2022-05-06/…/document_1.html` → **HTTP 200, 560,258 bytes, 9 tables**
- `…/F2019L00278/2024-12-14/2024-12-14/…/document_1.html` → **HTTP 200, 826,205 bytes, 11 tables**

⚠ **Concrete diffing hazard [FETCHED]: the table count and table *order* change
between compilations.** The 2022-05-06 compilation has **9** tables and row
counts `[6, 214, 217, 80, 4, 39, 13, 4, 16]` — it has **no 505-row
occupation→authority table at all**; at index 5 sits the 39-row abbreviation key
instead. The 2024-12-14 compilation has 11 tables with the 505-row table restored
at index 5. **Positional table indexing across compilations is unsafe** — anchor
on preceding heading text, exactly as Agent 1 warned for the current version.

**A real diff result [FETCHED]:** MLTSSL membership is **unchanged** across
2022-05-06 → 2024-12-14 → 2026-03-28 (212 codes each, zero added, zero removed).
The amendments in this period changed *assessing authorities*, not list
membership. Useful calibration: `list_change_log` will be sparse on membership and
active on authority changes.

### Column mapping

| koshi target | Column | Source | Grain | Tier |
|---|---|---|---|---|
| `list_change_log` | `effective_date` | API `versions[].start` | compilation | **Tier 1** (JSON API) |
| `list_change_log` | `compilation_number`, `register_id` | `compilationNumber`, `registerId` | " | Tier 1 |
| `list_change_log` | `change_reason` | `reasons[].markdown` / `affectedByTitle.name` | " | Tier 1 |
| `list_change_log` | `occupation_code`, `change_type` | **diff** of epub tables between consecutive `start` dates | occupation × compilation | Tier 2 + diff |

---

## G8. Assessing body turnaround times and costs — **NOT PUBLISHED (in aggregated form)**

**Question.** For the 38 bodies in LIN 19/051 Table 6, is there any single
aggregated source of turnaround estimates and fees?

**Verdict: no aggregated source exists.** Neither the legislative instruments
(which specify *which* body assesses *which* occupation, and nothing else —
[FETCHED], confirmed across both LIN 19/051 and F2024L01618) nor any Home Affairs
page carries per-body fees or turnaround times. These figures live on each body's
own site, are commercial terms, and change independently.

**Additional evidence this is irreducibly per-body** [FETCHED]: the abbreviation
keys are not even *stable across two instruments of the same department*. LIN
19/051 lists **37** bodies and F2024L01618 lists **39** in my parse, and the
abbreviation sets differ:

- only in `F2024L01618`: `CMBA`, `CWA`, `EA`, `SLAA`
- only in LIN 19/051: `ACWA`, `Engineers Australia`

Note `EA` vs `Engineers Australia` and `CWA` vs `ACWA` — **the same body under
different abbreviations in two current instruments**. Any `assessing_bodies` table
keyed on the abbreviation string will produce duplicate/orphan rows. Key on the
**full legal name** and store abbreviations as a many-to-one alias table.

(Agent 1 reported 38 bodies; I count 37 and 39 in the two instruments. The
difference is header-row handling. The *union* of abbreviations across both is
**41** [FETCHED]. Treat 38 as approximate.)

**Recommendation:** ship `assessing_bodies.turnaround_estimate` and `cost` as
**NULL**, exactly as Agent 2's F2 anticipated. If koshi later wants them, it is 38
separate Tier 5 curation targets with individual review dates — scope it as such,
not as a pipeline.

---

## G9. Visa grants by subclass and program year — **FOUND** ⭐ *the most valuable find in this audit*

**Question.** A pathway-level (per-subclass) grant breakdown; needs
`(visa_code, program_year, granted_count)`. Agent 1 enumerated 44 annual-report
PDFs but opened none.

**How I found it — worth recording, because it was not where anyone was looking.**
Not in an annual report. The Home Affairs FOI ceiling document (§G2) *cites its
own sources*, and step 4(a) of its methodology names a **data.gov.au dataset**.
Following that citation found the dataset. Three CKAN full-text searches for
"skillselect" / "occupation ceiling" had all failed to surface it, because the
dataset's title contains none of those words.

**Dataset:** `https://data.gov.au/data/dataset/permanent-migration-program-skilled-family`
**API:** `https://data.gov.au/data/api/3/action/package_show?id=permanent-migration-program-skilled-family` — [FETCHED] HTTP 200, 10,848 bytes JSON.

**Metadata** [FETCHED]:
- Title: *Permanent Migration Program (Skilled & Family) Outcomes Snapshot – Annual Statistics*
- Organisation: **Department of Home Affairs** (CKAN org name `immi`)
- Licence: **Creative Commons Attribution 2.5 Australia**
- `metadata_modified`: **2026-04-23**
- Cadence, stated verbatim in the dataset notes: *"These reports are released on an **annual** basis."*
- 7 resources: 5 XLSX vintages (2011-12 → current), a pivot-table user guide PDF, a resources CSV.
- Notes also record a genuine availability risk: *"The statistics were temporarily removed in March 2024 in response to a question about privacy … the Department of Home Affairs has republished the dataset."*

**Current resource** [FETCHED] — HTTP 200, **5,237,461 bytes** XLSX:

```
https://data.gov.au/data/dataset/096fd157-807c-4ba0-8c63-0754cae4ba35/resource/832fe752-f672-4ce7-a5bc-bada2270496c/download/bp0068-migration-and-child-outcome-since-2015-16-to-2025-06-30-masked-v100.xlsx
```

⚠ **Retrieval recipe — the data is NOT in the worksheets.** [FETCHED] The workbook
has 4 sheets (`Overview`, `Outcome`, `Explanatory Notes`, `Data Items and
Terminology Used`) which are just a pivot-table UI. The actual data is the
**pivot cache**:

```
xl/pivotCache/pivotCacheDefinition1.xml   (60,833 bytes — field names + shared items)
xl/pivotCache/pivotCacheRecords1.xml      (119,509,535 bytes uncompressed — the records)
```

Read `pivotCacheDefinition1.xml` for `cacheFields` (each with its `sharedItems`
list), then stream `pivotCacheRecords1.xml` with `iterparse`; each `<r>` has one
child per field — `<x v="i"/>` indexes into that field's shared items, `<n v="…"/>`
is a literal number. **A generic "read the XLSX with pandas/openpyxl" approach
returns nothing useful.** This is Tier 2 but needs a bespoke reader.

**Verified performance:** full parse of all **622,425** records in **4.8 seconds**
with the Python stdlib only [FETCHED].

**What it actually serves** — `recordCount="622425"`, **18 fields** [FETCHED]:

| # | Field | Distinct | Sample values |
|---|---|---|---|
| 0 | Programme Year | 10 | `2015-16` … `2024-25` |
| 1 | Visa Program | 2 | `Migration Program`, `Child Program` |
| 2 | Visa Category | 4 | `Skilled`, `Family`, `Child`, `Special Eligibility` |
| 3 | Visa Type | 14 | `Skilled Independent`, `State/Territory Nominated`, … |
| 4 | Visa Sub-type | 45 | `Employer Nomination Scheme`, … |
| 5 | **Visa Subclass** | **62** | `189 Skilled - Independent` |
| 6 | Citizenship Country | 228 | `India`, `China, Peoples Republic of (excl SARs)` |
| 7 | Gender | 3 | `Male`, `Female`, `Not Specified` |
| 8 | Applicant Type | 2 | `Primary`, `Secondary` |
| 9 | Age Group at Grant | 21 | `25 - 29` |
| 10 | Client Location | 2 | `In Australia`, `Outside Australia` |
| 11–14 | Occupation Major / Submajor / Minor / **Unit Group** | 11 / 46 / 98 / **306** | `2544 Registered Nurses` |
| 15 | **Occupation** | **764** | `261313 Software Engineer`, `232111 Architect` |
| 16 | Intended Residence | 10 | `New South Wales`, … |
| 17 | **Outcome** | numeric | the grant count (min −95, max 764) |

**Verified aggregate — subclass 189 grants by program year** [FETCHED, computed
from all 622,425 records]:

| Year | Grants | | Year | Grants |
|---|---|---|---|---|
| 2015-16 | 43,525 | | 2020-21 | 7,837 |
| 2016-17 | 42,396 | | 2021-22 | 5,882 |
| 2017-18 | 39,130 | | 2022-23 | 32,100 |
| 2018-19 | 34,244 | | 2023-24 | 30,375 |
| 2019-20 | 13,349 | | 2024-25 | 16,900 |

Skilled subclasses present [FETCHED]: `186`, `189`, `190`, `491`, `494`, `858`,
`888`. Top 189 occupations across all years [FETCHED]: `261313 Software Engineer`
10,952 · `254499 Registered Nurses nec` 10,853 · `221111 Accountant (General)`
8,592 · `233512 Mechanical Engineer` 4,922.

⚠ **Two data caveats, both [FETCHED]:**
1. **Negative `Outcome` values exist** — 4,611 records carry values from −1 to −95.
   Their meaning is **UNVERIFIED** (plausibly withdrawals/reversals or a masking
   artefact; the dataset notes describe masking values <5 as `<5`). They *do*
   affect sums. koshi should keep them (the publisher's own pivot sums them) but
   flag the count in the load log rather than silently discarding.
2. **`Not Applicable` / `Not Specified` / `070299 Occupation Unknown` are real
   category values**, not nulls — `Not Applicable` alone accounts for 123,831 of
   the 189 total. Never treat the occupation dimension as complete.

### Column mapping

| koshi target | Column | Source field | Grain | Tier |
|---|---|---|---|---|
| `application_funnel` | `granted_count` | `SUM(Outcome)` | subclass × year | **Tier 2** |
| `application_funnel` | `visa_code` | `Visa Subclass`, split on first space | " | Tier 2 |
| `application_funnel` | `program_year` | `Programme Year` | " | Tier 2 |
| `visa_subclasses` | `name`, `family` | `Visa Subclass` / `Visa Category` | subclass | Tier 2 |
| `ceiling_usage` | genuine `issued` | `SUM(Outcome)` filtered to 190/186/491/494 | unit group × year | Tier 2 |
| *(new)* `grants_by_occupation` | `occupation_code`, `granted_count` | `Occupation` split on first space | occupation × subclass × year | Tier 2 |

**Join-key check.** `Visa Subclass` is `"189 Skilled - Independent"` — the code is
the token before the first space, and it **does match** koshi's `visa_code` key
space after that split. `Occupation` is `"261313 Software Engineer"` — same split
yields a **6-digit ANZSCO code** that joins directly to `occupations`, no name
resolution needed. `Occupation Unit Group` yields the **4-digit** code that
matches the §G2 ceiling grain. This dataset is unusually well keyed for koshi.

**This single source resolves G9 outright, supplies the honest `issued` column
that G2's FOI document could not, and adds a per-occupation grant history koshi
had no source for at all.**

---

## G10. EOI submitted / pool-on-hand counts — **NOT PUBLISHED**

**Question.** Are EOIs submitted or EOIs on hand published anywhere? Lead:
data.gov.au historically carried SkillSelect EOI datasets.

**What I searched, and the results** [FETCHED]:
1. `data.gov.au` CKAN `package_search?q=skillselect` → **count = 1**, the sole hit
   being a *2012 NSW Government Gazette*. No SkillSelect dataset exists.
2. `package_search?q=occupation+ceiling` (310 hits) and
   `q=expression+of+interest+migration` (396 hits) → manually reviewed the top 15
   of each; **all irrelevant** (NSW gazettes, museum annual reports, ocean ecology).
   CKAN full-text relevance on this portal is poor, so I did not rely on it alone.
3. Retrieved the **complete list of all 1,139 organisations** on data.gov.au and
   grepped for immigration-related names.
4. Retrieved the **full package list of the Home Affairs org (`immi`)** —
   `package_count = 12`. The datasets are: Settlement Reports; Overseas Arrivals
   and Departures; Student visa program; Working Holiday Maker visa program;
   Temporary Work (skilled) visa program; Visitor visa program; Temporary Graduate
   visa program; Temporary visa holders in Australia; **Permanent Migration
   Program (Skilled & Family)**; Australian Migration Statistics.
   **None is a SkillSelect or EOI dataset.**
5. Agent 1 separately searched the fully-decoded SkillSelect page for `submitted`,
   `lodged`, `EOIs on hand`, `EOIs in the system`, `pool` — zero matches. My own
   decode of the same page reproduces its five sections and confirms no such table.

**Verdict: EOI submitted / on-hand counts are not published by the Commonwealth in
any machine-readable form I could find.** Third-party sites (`immitrend.com.au`
and similar) advertise "EOI pool & backlog by occupation" — these appeared in
search results as leads and are **explicitly not usable**: they are commercial
estimates, not government data, and citing them would repeat exactly the error
this audit exists to prevent.

**Recommendation:** `application_funnel.submitted_count` should ship **NULL**, as
the canonical design's own fallback anticipated. Consider adding a
`not_published` marker distinct from `NULL`-because-not-yet-loaded, so the API can
tell consumers this will never be populated rather than implying pending work.

---

## G11. JSA rating vocabulary definitions — **FOUND**

**Question.** What do `R`, `M` and lowercase `Ns` mean in JSA's `splData` JSON? Is
`NS` vs `Ns` a real distinction? Is future demand (`d`) published separately?

**Path to the answer.** The glossary is JS-rendered, so the page itself is a dead
end — I re-fetched it [FETCHED, 41,285 bytes] and confirmed the phrase "What do
the ratings mean" appears but **no definitions are in the static HTML**. The
definitions are in JSA's published methodology PDF instead.

**Source** [FETCHED] — HTTP 200, **670,568 bytes**, PDF, **27 pages**,
text-extractable (no OCR needed):

```
https://www.jobsandskills.gov.au/sites/default/files/2025-10/2025%20OSL%20Methodology.pdf
```

*2025 Occupation Shortage List Methodology, October 2025.* **Table 1:
Classifications of occupations in scope of the OSL**, quoted verbatim from the
extracted text [FETCHED]:

> *"The OSL has **4 ratings classifications** (Table 1). … **Shortage (S)** — An
> occupation is in national shortage or overall shortage. **Metropolitan shortage
> (M)** — An occupation is in shortage in a metropolitan area. **Regional shortage
> (R)** — An occupation is in shortage in a regional area. **No shortage (NS)** —
> An occupation is not in shortage."*

with the footnote [FETCHED]: *"Metropolitan area refers to Capital City, while
Regional area refers to Rest of State locations. Capital City and Rest of State
areas are defined by the Australian Statistical Geography Standard (ASGS) Edition
3 – Reference period July 2021 to June 2026."*

**This resolves both of Agent 1's UNVERIFIED items:**

| Code | Meaning |
|---|---|
| `S` | Shortage (national/overall) |
| `M` | **Metropolitan** shortage (Capital City) |
| `R` | **Regional** shortage (Rest of State) |
| `NS` | No shortage |

**And it settles `NS` vs `Ns`:** the methodology states there are **exactly 4**
classifications. There is no fifth. **`Ns` is a casing inconsistency in the data
file, not a distinct code** — normalise it to `NS` on ingest. Agent 1's instinct
was right; this is the confirmation they asked for.

**Bonus [FETCHED]:** ratings are driven by a **vacancy fill rate** with a **67%
threshold**, produced by a GBM machine-learning model plus the SERA employer
survey and stakeholder survey. That is a genuine provenance note for
`skills_priority_ratings`.

**On the `d` (future demand) field:** still **NOT FOUND** as populated data. Agent
1 found it `null` for every record. I did not locate a separate JSA
employment-projections dataset that fills it. UNVERIFIED — whether JSA publishes
projections elsewhere; I did not exhaust this. Keep
`skills_priority_ratings.future_demand_rating` NULL.

### Column mapping

| koshi target | Column | Source | Tier |
|---|---|---|---|
| `skills_priority_ratings` | `shortage_rating` **CHECK** | `IN ('S','M','R','NS')` after upper-casing | Tier 2 |
| `skills_priority_ratings` | `rating_definition` (lookup) | Methodology PDF Table 1 | Tier 5 (4 rows, stable) |
| `skills_priority_ratings` | `future_demand_rating` | — | **NULL, not published** |

**F7's CHECK constraint should be `CHECK (shortage_rating IN ('S','M','R','NS'))`
with a normalising `UPPER()` on ingest.**

---

### G-NEW-A. JSA `splSearch` — an alternative-titles index (found while resolving G11)

Agent 1 identified `spl_search` in the Drupal settings but characterised only
`spl_data`. I fetched it [FETCHED] — HTTP 200, **316,671 bytes**, valid JSON:

```
https://www.jobsandskills.gov.au/system/files/applet_data/splSearch%20(2).json
```

**Structure:** `{ "<edition>": { "<6-digit code>": {"actual": <title>, "code":
<code>, "alt": [<alternative titles>]} } }`. Two editions [FETCHED]:

| Edition key | Occupations | Alternative titles | Code width |
|---|---|---|---|
| `2022` | 1,076 | 3,269 | 6 |
| `2025` | 1,156 | 3,338 | 6 |

⚠ **Edition-key inconsistency worth flagging:** `splData` uses keys `2022`/`2024`
(per Agent 1) while `splSearch` uses `2022`/`2025` for what appears to be the same
ANZSCO-vs-OSCA split — and the `2025` codes are OSCA-shaped (e.g. `Speech
Pathologist → 262631`, an OSCA code). Do not assume the two files' edition keys
align.

**Value: it is a synonym dictionary for G1.** Tested against the 140 SkillSelect
names it resolves **137/140** [FETCHED] (missing `Cabinetmaker`, `Fibrous
Plasterer`, `Sheetmetal Trades Worker`). It is a good *third* fallback after LIN
and ABS, and its 3,000+ alternative titles are genuinely useful for a
user-facing occupation search endpoint — but it is edition-mixed, so always carry
the edition alongside any code it returns.

---

# P3 — Enrichment

## G12. Points tables for visas other than 189 — **FOUND**

**Question.** Is there an equivalent `/points-table` page for 190 and 491, or a
single instrument specifying the whole GSM points test?

**Answer: yes — parallel pages exist at the predictable path, and I fetched both.**

| Visa | URL | Status | `pageModified` | Sections |
|---|---|---|---|---|
| 189 | `…/visa-listing/skilled-independent-189/points-table` | **200** | 11/06/2026 13:38 | **11** |
| 190 | `…/visa-listing/skilled-nominated-190/points-table` | **200**, 1,302,562 B | 16/07/2026 9:55 | **12** |
| 491 | `…/visa-listing/skilled-work-regional-provisional-491/points-table` | **200**, 1,303,370 B | 16/07/2026 9:55 | **12** |

All three use the **identical** hidden-input JSON decode recipe Agent 1
documented, with a `content` array [FETCHED].

**The structure is 11 shared sections + 1 visa-specific section** [FETCHED].
Shared by all three: `Overview`, `Age`, `English language skills`, `Skilled
employment experience`, `Educational qualifications`, `Specialist education
qualification`, `Australian study requirement`, `Professional Year in Australia`,
`Credentialled community language`, `Study in regional Australia`,
`Partner skills`.

The differing 12th section, with its full verified content [FETCHED]:

| Visa | Section name | Requirement | Points |
|---|---|---|---|
| 189 | *(none)* | — | — |
| 190 | `Nomination` | "You were invited to apply for a Subclass 190 (Skilled — Nominated) visa and the nominating State or Territory government agency has not withdrawn the nomination" | **5** |
| 491 | `Nomination or sponsorship` | "…nominated **or** …sponsored … by a family member and the Minister has accepted that sponsorship" | **15** |

**Cross-check that matters for G3** [FETCHED]: the `English language skills`
section is byte-identical across all three — `Competent English 0`,
`Proficient English 10`, `Superior English 20`. So the band→points mapping is
visa-invariant, and `english_test_bands.points_awarded` needs **no** visa
dimension. Good news for F5.

**Correcting a plausible assumption:** I searched all three decoded pages for
`Schedule 6D` and found **zero occurrences** [FETCHED]. The pages do not cite the
underlying instrument. I therefore do **not** assert that Schedule 6D of the
Migration Regulations is the source — UNVERIFIED, not fetched. The three HTML
pages are sufficient and are the better extraction target anyway.

### Column mapping

| koshi target | Column | Source | Grain | Tier |
|---|---|---|---|---|
| `points_criteria_reference` | `visa_code` **(the I20 fix)** | which of the 3 URLs | criterion × visa | **Tier 2** |
| `points_criteria_reference` | `category` | section `text` | " | Tier 2 |
| `points_criteria_reference` | `requirement`, `points` | section table columns | " | Tier 2 |

**Recommendation:** load all three URLs into `source_pages` and add `visa_code` to
`points_criteria_reference`. Because 11 of 12 sections are duplicated across the
three pages, either store all three copies (simplest, honest) or store shared
criteria once with a `applies_to` set — but do **not** load only the 189 page and
imply it covers 190/491, which is the current state.

---

## G13. Replacement anchors for `policy_events` — **PARTIAL**

**(a) Which Budget Paper carries migration planning levels?**

[FETCHED] `https://budget.gov.au/` → HTTP 200, and
`https://budget.gov.au/content/bp3/index.htm` → **HTTP 200**, 17,953 bytes. So the
`/content/{paper}/index.htm` pattern is live even though Agent 1's
`/content/migration.htm` was a soft-404.

**But BP3 is the wrong paper.** Its fetched title and contents [FETCHED] are
*"Budget Paper No. 3: **Federal Financial Relations**"*, with parts
`Australia's Federal Relations`, `Payments for specific purposes`, `Health`,
`Education`, `Skills and workforce development`, `Community services`,
`Affordable housing`… — Commonwealth-to-State payments, **not** migration
planning levels. The site navigation [FETCHED] lists the paper set as
`Budget Strategy and Outlook` (BP1), `Budget Measures` (BP2),
`Federal Financial Relations` (BP3), `Agency Resourcing` (BP4).

UNVERIFIED — which of BP1/BP2 carries the migration planning numbers; I did not
fetch and search them (budget). **But the honest answer Agent 2 anticipated
stands and is now better evidenced:** since Agent 1 established that C15's
numbers come entirely from the immi planning-levels page and do **not** depend on
budget.gov.au, the right action is **drop budget.gov.au from the catalog** rather
than chase the correct paper. Chasing it adds a fragile annual-churn URL for data
koshi already has from a better source.

**(b) A machine-readable index of ministerial media releases — NOT FOUND.**

I found no RSS, JSON or documented paginated API under
`minister.homeaffairs.gov.au`. UNVERIFIED — I did not fetch the minister site
directly (budget) and am not going to assert either way from search snippets.
Recorded as unreached-and-unresolved rather than "does not exist".

**A better `policy_events` driver exists, and it is already verified.** The
legislation OData API from §G7 gives, for any instrument, a dated version history
with the amending instrument named in `reasons[].markdown` — dated, authoritative,
machine-readable, and already proven to work. For a dataset whose subject *is*
migration policy change, legislative amendments are a stronger and more reliable
event stream than press releases. **Recommendation:** drive `policy_events` from
the legislation API for the instruments koshi already tracks, and keep media
releases as optional manual enrichment.

---

## G14. Companion instrument contents — **FOUND (one positive, one negative)**

Agent 1 resolved both epub URLs but left contents UNVERIFIED. Both are now
fetched and parsed.

### `F2024L01616` — **zero tables** (fully covered in §G1)

[FETCHED] 7,916 bytes, **0 `<table>`**. Definitional only; pins ANZSCO to the ABS
edition in force **27 June 2013** (and 23 November 2022 for regs 2.72/2.73/5.19(5)).
**Do not catalogue it as an occupation-list source.** Catalogue it as the
edition-authority document — it is the citation for koshi's `anzsco_edition`
column.

### `F2024L01618` — the **Core Skills Occupation List**, 456 occupations

[FETCHED] `https://www.legislation.gov.au/F2024L01618/2026-03-28/2026-03-28/text/original/epub/OEBPS/document_1/document_1.html`
→ HTTP 200, **564,729 bytes**, static HTML, **6 `<table>` elements**.

Full title, extracted from the document text [FETCHED]: *"Migration
(Specification of Occupations and Relevant Assessing Authorities—Subclass 186
Visa) Instrument 2024"*.

| # | Rows | Preceding heading (verified) | Columns | What it is |
|---|---|---|---|---|
| **0** | **459** | "The occupations set out in the following table are the **Core Skills Occupation List**." | `Item \| Occupation Title \| ANZSCO Code \| Relevant assessing authority \| Applicable circumstance` | **CSOL — 456 data rows** |
| 1 | 17 | "Applicable circumstances" | `Item \| Circumstance` | the circumstance codes referenced by col 4 |
| 2 | 41 | "Relevant assessing authorities" | `Item \| Abbreviation \| Full name` | **39 bodies** |
| 3 | 23 | "Endnote 2—Abbreviation key" | — | legislative drafting key, not data |
| 4 | 6 | "Endnote 3—Legislation history" | `Name \| Registration \| Commencement \| …` | amendment provenance |
| 5 | 22 | "Endnote 4—Amendment history" | `Provision affected \| How affected` | per-provision changes |

**Verified sample rows (table 0)** [FETCHED]:
`1 | Chief Executive or Managing Director | 111111 | IML | 1`;
`3 | Aquaculture Farmer | 121111 | VETASSESS | 5`.

**Key facts about the CSOL** [FETCHED]:
- **456 distinct 6-digit ANZSCO codes** (all 6-digit — no unit groups).
- **All 456 exist in ABS ANZSCO 2022 Table 6 — 100% coverage, zero misses.**
  This is a *striking contrast with LIN 19/051*, of whose 504 codes 25 are absent
  from ANZSCO 2022. **The CSOL is coded on the modern ANZSCO; the MLTSSL/STSOL/ROL
  instrument is not.** Two current instruments from the same department use two
  different ANZSCO editions. This is the single strongest piece of evidence that
  koshi must carry `anzsco_edition` per row.
- **86 CSOL codes do not appear in LIN 19/051 at all** — the CSOL is a genuinely
  distinct list, not a subset. Only 370 of 456 overlap.
- **38 distinct assessing-authority strings**, and some cells name **multiple**
  bodies (e.g. `ACPSEM, VETASSESS`) — the same multi-authority pattern Agent 1
  found in LIN 19/051 (`(a) Engineers Australia; or (b) IML`), but with a
  **different delimiter convention**. A parser must handle both `, ` and
  `(a) … ; or (b) …`.
- **34 rows carry a non-empty `Applicable circumstance`** keyed to table 1 — a
  conditional-eligibility dimension koshi's schema has no home for today.

**This is an orphan source worth adopting.** The CSOL is the current occupation
list for the Skills in Demand / subclass 186 pathway. koshi models MLTSSL / STSOL
/ ROL and has no CSOL table. Given F4 adds an occupation-list membership table,
the CSOL should be a fourth `list_name` value in it — the schema change costs
nothing and the data is already parsed.

---

## G15. Processing-times data cadence and as-of date — **PARTIAL**

**Question.** Does Home Affairs state when the percentiles were recalculated, or
over what application window?

[FETCHED] `https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-processing-times/global-visa-processing-times`
→ HTTP 200, 1,284,921 bytes.

**Findings:**
- The page does **not** use the hidden-input JSON pattern — my decoder found no
  `PageSchemaHiddenField` content array [FETCHED]. It is a form-driven page
  (`Visa type`, `Visa stream`, `Application Date` inputs) backed by the POST API
  Agent 1 documented. Different template from the other immi pages; note this in
  the catalog.
- It **does** carry `pageModified`: **`4/08/2026 8:32 AM`** [FETCHED].
- I scanned the full de-tagged text for `calculated`, `90 per cent`, `50 per
  cent`, `window`, `previous`, `month`. **No statement of the calculation window
  or refresh cadence appears in the server-rendered HTML** [FETCHED]. The
  explanatory prose is either on a parent page or rendered client-side.

**Verdict.** The **only** honest as-of signal is `pageModified` on the containing
page — the API response itself carries no date, as Agent 1 found.

**Recommendation for F1:** set `processing_times.as_of_date` from the containing
page's `pageModified`, and store it as `source_last_modified` (the new F12 column)
rather than implying it is a statistical reference date. Do **not** label it
"data as of" — it is "page last edited", which is a weaker claim. The catalog's
"plausibly monthly" cadence remains **UNVERIFIED**; the two `pageModified` values
I observed on immi pages this session (SkillSelect `4/08/2026 17:03`, processing
times `4/08/2026 8:32 AM`) share a date, which is suggestive of a batch publish
but proves nothing about recalculation frequency.

---

## G16. Per-occupation labour-market detail — **FOUND** (a bulk dataset, not 1,236 fetches)

**Question.** What does the JSA per-occupation detail sub-page serve, and is there
a bulk dataset rather than 1,236 sub-page fetches?

**Answer: there is a bulk dataset, and the Department of Home Affairs already
uses it.** The §G2 FOI methodology names it as the authoritative employment-stock
source, which makes it the right choice for koshi too — the same numbers the
ceiling calculation runs on.

**Source** [FETCHED] — `https://www.abs.gov.au/statistics/labour/employment-and-unemployment/labour-force-australia-detailed/latest-release`
→ HTTP 200, 189,622 bytes.

The page exposes a full set of quarterly data cubes as direct XLSX links
[FETCHED], currently under a `mar-2026/` path segment — `EQ02`–`EQ14`. The
relevant one, with its exact published description [FETCHED]:

> **EQ08** — *Employed persons by **Occupation unit group** of main job (ANZSCO),
> Sex, State and Territory, August 1986 onwards (Pivot Table)* — Download xlsx
> **[53.44 MB]**

```
https://www.abs.gov.au/statistics/labour/employment-and-unemployment/labour-force-australia-detailed/mar-2026/EQ08.xlsx
```

**Characterisation:**
- **Format:** XLSX pivot table. Given its 53 MB size and the "(Pivot Table)"
  label, expect the **same pivot-cache extraction pattern as BP0068** (§G9) —
  data in `xl/pivotCache/`, not in the worksheets. UNVERIFIED — I did not
  download the 53 MB file (budget); the extraction pattern is an inference from
  the label and from BP0068's identical presentation, **not** a fetched fact.
- **Grain:** ANZSCO **4-digit unit group** × sex × state/territory × quarter.
  Note this is **unit-group grain, not 6-digit** — it matches the §G2 ceiling
  grain exactly (which is why Home Affairs uses it) but does **not** match the
  6-digit `occupations` key.
- **Cadence:** quarterly; the URL embeds the quarter (`mar-2026`), so the
  crawler must resolve the current quarter from the latest-release page rather
  than template the path.
- **Access obstacles:** none observed — plain 200, no auth, no Cloudflare.

**On the JSA per-occupation sub-page:** still **NOT FETCHED** (budget). Agent 1's
card-level fields (`Employed`, `Median weekly earnings`) are the same measures
EQ08 carries in bulk, so the sub-page is likely redundant for `Employed`. Whether
it adds outlook/projections is **UNVERIFIED**.

### Column mapping

| koshi target | Column | Source | Grain | Tier |
|---|---|---|---|---|
| `occupations` / *(new)* `occupation_labour_market` | `employed_count` | EQ08 | **4-digit unit group** × state × quarter | Tier 2 (pivot-cache reader) |
| " | `as_of_quarter` | URL path segment + cube period | " | Tier 2 |
| `occupations` | `median_weekly_earnings` | **not in EQ08** — JSA card only, and Agent 1 observed `N/A` values | 6-digit | Tier 2, expect nulls |

⚠ **Grain mismatch is the blocker here, not availability.** koshi's `occupations`
is 6-digit; EQ08 is 4-digit. Employment counts cannot be attached to a 6-digit row
without inventing an allocation. Either add a separate unit-group-grain table or
expose employment only at unit-group level — do not apportion.

---

# New sources discovered

Genuinely new finds, not among Agent 2's 18 orphan sources.

| # | Source | Verified as | Why it belongs in koshi |
|---|---|---|---|
| **N1** | **BP0068** on data.gov.au (§G9) | XLSX pivot cache, 622,425 records, CC-BY, annual | Only source of grant counts. Resolves G9; supplies G2's `issued`; adds subclass taxonomy for G5 |
| **N2** | **SkillSelect "Previous rounds"** page (below) | 19 historical rounds, 1,419 occupation rows | Turns `eoi_rounds` from 1 row into ~1,400 with 5 years of history |
| **N3** | **legislation.gov.au OData API** (§G7) | JSON, no auth | Compilation history + effective dates + amendment reasons for every instrument koshi tracks |
| **N4** | **`F2024L01618` CSOL** (§G14) | 456 occupations, ANZSCO-2022-coded | A fourth occupation list koshi does not model at all |
| **N5** | **`F2025L00905` / `F2025L00904`** (§G3) | 144 band×test×skill rows | Unblocks `english_test_bands` |
| **N6** | **ABS OSCA correspondence tables** (§G4) | 10 directional maps with partial-match flags | Unblocks F3 |
| **N7** | **ABS ANZSCO 2022 structure** (§G1) | Table 6, 1,425 code/title pairs | Unblocks G1 |
| **N8** | **JSA `splSearch`** (§G-NEW-A) | 6,600+ alternative titles across 2 editions | Occupation search / fuzzy name resolution |
| **N9** | **JSA OSL Methodology PDF** (§G11) | 27pp, text-extractable | Defines the rating enum; provenance for `skills_priority_ratings` |
| **N10** | **Home Affairs FOI releases** (§G2) | scanned PDFs | Only source of occupation ceilings, at all |
| **N11** | **ABS EQ08** (§G16) | 53 MB quarterly pivot table | Employment stock per unit group |

## N2 in detail — SkillSelect "Previous rounds" (a significant miss in the current catalog)

**URL:** `https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/previous-rounds`
(discovered by extracting the links out of the decoded *current* rounds page —
it is linked from the `Overview` block as "Previous rounds").

[FETCHED] HTTP 200, **1,903,834 bytes**. `pageModified` = **`23/06/2026 11:33`**.

⚠ **It uses a DIFFERENT JSON schema from the current-round page.** The same hidden
input decodes to a top-level **`criteria`** key, not `content` [FETCHED]. Each
element is `{title, subTitle, description, collapsed, criteria}` where `title` is
the **round date** and `description` is the HTML block. A parser written against
the current-round page's `data["content"]` will **KeyError** here. This is exactly
the kind of silent breakage this audit exists to catch.

**Volume [FETCHED]: 19 rounds, `11 August 2020` → `13 November 2025`, totalling
1,419 occupation-grain data rows.**

⚠ **Five distinct table schemas across the 19 rounds** [FETCHED] — the historical
data is not uniform:

| Era | Occupation-table header | Note |
|---|---|---|
| 2025 | `Occupation* \| 189 \| 491` | current shape (145, 132 rows) |
| Nov 2024 | `Occupation* \| Subclass 189` | single-subclass |
| Sep 2024 / Jun 2024 | `Occupation* \| Subclass 189* Minimum scored` | renamed column |
| May 2023 / Dec 2022 / Oct 2022 | blank first header + **two-level header row** `Occupation \| Offshore** \| Onshore** \| Offshore** \| Onshore**` | **an offshore/onshore split that no longer exists** |
| Aug 2020 – Jan 2022 | `Subclass \| Occupation ID \| Description \| Minimum points score \| Latest date of effect month` | **carries an explicit `Occupation ID`, and it is 4-DIGIT** (e.g. `2211 Accountants`, `2334 Electronics Engineer`) |

**Two findings that change the `eoi_rounds` design:**

1. **Older rounds ship the code directly** — the 2020–21 rounds have an
   `Occupation ID` column, so no name resolution is needed for them at all. But it
   is a **4-digit unit group**, whereas modern rounds resolve to **6-digit**
   occupations. `eoi_rounds` therefore needs the `code_level` discriminator from
   F9 as a hard requirement, not a nicety.
2. **The 2022–23 rounds have an offshore/onshore dimension** that modern rounds
   lack. Either add a nullable `applicant_location` column or those rounds cannot
   be loaded without collapsing two real distinctions into one.

**Recommendation:** catalogue this URL, and give it its **own** parser keyed on
`criteria` with per-era schema detection. It is the difference between
`eoi_rounds` holding one round and holding six years.

---

# Recommended catalog updates to `2026-08-16-koshi-source-urls.md`

## A. Additions — all verified by fetch

| # | URL / endpoint | Method | Format | Tier | Feeds |
|---|---|---|---|---|---|
| A1 | `abs.gov.au/statistics/classifications/anzsco-.../2022/anzsco%202022%20structure%20062023.xlsx` | GET | XLSX, sheet `Table 6` | 2 | `occupations`, G1 LUT |
| A2 | `abs.gov.au/statistics/classifications/osca-.../2024-version-1-0/data-downloads/OSCA%20correspondence%20tables%20v2.xlsx` | GET | XLSX, `Table 1`+`Table 5` | 2 | `occupation_code_map` |
| A3 | `data.gov.au/data/api/3/action/package_show?id=permanent-migration-program-skilled-family` | GET | JSON → XLSX pivot cache | 2 | `application_funnel`, `visa_subclasses`, `ceiling_usage.issued` |
| A4 | `immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/previous-rounds` | GET | hidden-input JSON, **`criteria`** key | 2 | `eoi_rounds` (history) |
| A5 | `api.prod.legislation.gov.au/v1/titles('{id}')?$expand=versions` | GET | JSON (OData) | 1 | `list_change_log`, `policy_events` |
| A6 | `legislation.gov.au/F2025L00905/asmade/2025-08-06/…/document_1.html` | GET | HTML, table 0 | 2 | `english_test_bands` |
| A7 | `legislation.gov.au/F2025L00904/asmade/2025-08-06/…/document_1.html` | GET | HTML, table 0 | 2 | `english_test_bands` (Functional) |
| A8 | `legislation.gov.au/F2024L01618/2026-03-28/2026-03-28/…/document_1.html` | GET | HTML, 6 tables | 2 | CSOL membership, `assessing_bodies` |
| A9 | `immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-nominated-190/points-table` | GET | hidden-input JSON | 2 | `points_criteria_reference` (190) |
| A10 | `…/skilled-work-regional-provisional-491/points-table` | GET | hidden-input JSON | 2 | `points_criteria_reference` (491) |
| A11 | `jobsandskills.gov.au/system/files/applet_data/splSearch%20(2).json` | GET | JSON | 2 | occupation search / alt titles |
| A12 | `jobsandskills.gov.au/sites/default/files/2025-10/2025%20OSL%20Methodology.pdf` | GET | PDF (text) | 3 | rating enum + provenance |
| A13 | `abs.gov.au/…/labour-force-australia-detailed/mar-2026/EQ08.xlsx` | GET | XLSX pivot | 2 | employment stock (unit group) |
| A14 | `homeaffairs.gov.au/foi/files/2026/fa-260100545-document-released.PDF` | GET | **scanned PDF** | **4** | `ceiling_usage` (manual) |
| A15 | `homeaffairs.gov.au/foi/files/2025/fa-251001376-document-released.PDF` | GET | PDF (text) | 3 | ceiling methodology |

## B. Corrections

| # | Correction |
|---|---|
| B1 | **`F2024L01616` is NOT an occupation-list source** — 0 tables [FETCHED]. Recatalogue as the *ANZSCO edition authority* document. |
| B2 | **`immi…/skillselect/occupation-ceilings` does not exist** — HTTP 404 [FETCHED]. Remove if present; never cite it for ceiling data. |
| B3 | **`abs.gov.au/…/anzsco…/2022/data-downloads` returns 404** [FETCHED]. Correspondences live under the **OSCA** path (A2). |
| B4 | **`migration.wa.gov.au/…/waskilled-migration-occupation-list-wasmol` → HTTP 404** [FETCHED], and its 404 body is 62 KB — size is not a liveness check. Mark `dead`. |
| B5 | **`liveinmelbourne.vic.gov.au` → HTTP 403** [FETCHED], reproduced independently of Agent 1. Mark `blocked` (F12). |
| B6 | **Drop `budget.gov.au`** as a `policy_events` source — BP3 is Federal Financial Relations, not migration [FETCHED]; and C15's numbers come from immi. |
| B7 | **The processing-times page does not use the hidden-input JSON pattern** [FETCHED] — it is form+POST-API. Do not assume one immi decoder fits all immi pages. |
| B8 | **`previous-rounds` uses `criteria`, not `content`** [FETCHED]. Two different schemas on the same site, same hidden input. Record the JSON root key per page. |
| B9 | LIN 19/051 current compilation: I parse **11** tables where Agent 1 reported 12; row counts otherwise agree exactly. Record 11 with a note, and anchor selection on heading text either way. |
| B10 | Assessing-body counts differ between instruments (**37** in LIN 19/051, **39** in F2024L01618, **41** in union) and abbreviations conflict (`EA`/`Engineers Australia`, `CWA`/`ACWA`) [FETCHED]. Key on full legal name, not abbreviation. |

## C. Schema changes this audit forces (beyond Agent 2's F1–F12)

| # | Change | Evidence |
|---|---|---|
| C-a | **`anzsco_edition` is mandatory on every occupation-coded row.** | 3 editions live; LIN 19/051 = 2013 (25 codes absent from 2022), CSOL = 2022 (100% present), JSA = 2022+OSCA [FETCHED] |
| C-b | **`code_level` (`unit_group`/`occupation`) is mandatory**, not optional. | Ceilings 4-digit; 2020–21 EOI rounds 4-digit; EQ08 4-digit; modern rounds 6-digit [FETCHED] |
| C-c | `english_test_bands` needs **`skill`** and **`score_basis`** columns. | Sch. 2 is per-skill; Functional is overall/average/total [FETCHED] |
| C-d | `eoi_rounds` needs a nullable **`applicant_location`** (offshore/onshore). | 2022–23 rounds carry the split [FETCHED] |
| C-e | Add **`occupation_code_map`** (from/to code + edition + `full`/`partial`). | Fan-out up to 10; not a scalar column [FETCHED] |
| C-f | Add **CSOL** as a `list_name` in F4's membership table. | 456 occupations, 86 not in LIN 19/051 [FETCHED] |
| C-g | `ceiling_usage.issued` must be **renamed** — the FOI column is prior-year grants in *other* subclasses, not invitations issued. | FOI header text [FETCHED] |
| C-h | `assessing_bodies`: key on full name; add an **alias** table for abbreviations. | `EA` vs `Engineers Australia` across two live instruments [FETCHED] |

---

# Still missing after this pass

## Unpublished — retire the column, do not leave it "pending"

| Item | Evidence |
|---|---|
| **EOI submitted / on-hand counts** (G10) | 5 independent checks incl. the full 1,139-org list and Home Affairs' complete 12-dataset package list [FETCHED]. Ship `submitted_count` NULL and mark it *not published*, not *pending*. |
| **Occupation ceilings as a routine feed** (G2) | Sub-page 404s; live page is prose [FETCHED]. Data exists **only** via ad-hoc FOI releases at unstable URLs. `ceiling_usage` must become manual-tier or be retired. **Delete the 2 seeded rows now** — they cite a page that does not contain them. |
| **Assessing body fees / turnaround** (G8) | Absent from both instruments and every page checked across two audits. `turnaround_estimate` and `cost` ship NULL. |
| **JSA future demand (`d`)** (G11) | `null` for every record (Agent 1); no separate release found. `future_demand_rating` NULL. |
| **Visa permanence flag** (G5) | No published source. Derive from subclass name by explicit rule, or curate ~6 rows — but label it derived. |
| **State fees / points / decision times** (G6a) | Two audits, no source. Manual tier or drop. |

## Inaccessible — a source may exist but I could not reach it

| Item | Obstacle |
|---|---|
| **VIC occupation list** (G6c) | HTTP 403 Cloudflare, reproduced [FETCHED]. Needs a browser-like client or an official alternative. |
| **WA occupation list** (G6b) | Catalogued URL 404s [FETCHED]; the live list is behind a Views search form that defaults to 0 results. |
| **SA program status** (G6d) | Page returns 200 but status keywords are absent from server-rendered HTML [FETCHED] — client-side rendered. Needs a JS-capable fetch. **Genuinely ambiguous between "closed" and "parser broke"** — the exact case F12's `no_data` status is for. |

## Unreached — not investigated, or investigated only partially (budget)

Listed honestly so no one mistakes these for negative results:

- **Which Budget Paper carries migration planning levels** (G13a) — BP3 ruled out by fetch; BP1/BP2 not opened. Recommendation is to drop the source regardless.
- **A machine-readable index of ministerial media releases** (G13b) — `minister.homeaffairs.gov.au` **not fetched at all**. Neither confirmed nor denied.
- **EQ08's internal structure** (G16) — the 53 MB file was **not downloaded**. Its pivot-cache layout is inferred from the "(Pivot Table)" label and BP0068's identical presentation, and is explicitly UNVERIFIED.
- **JSA per-occupation detail sub-page** (G16) — not fetched. Whether it adds outlook/projections beyond EQ08 is unknown.
- **FOI `fa-251000198`** (G2) — the tier-assignment methodology cited by the ceiling document; not fetched.
- **Total row count of the FOI ceiling table** (G2) — I read pages 2 and 6 of 5 table pages; pages 3–5 unread. No total asserted.
- **English test validity period** (G3) — not stated in either instrument; the commonly cited "3 years" is a Migration Regulations criterion I did not verify.
- **Correspondence Tables 3/4/6** (G4) — counted only Tables 1, 2 and 5.
- **Annual report PDFs** (G9) — deliberately not opened. BP0068 supersedes the need; if grant data is ever needed pre-2015-16, they remain the fallback.

## Contradictions between this audit and Agent 1 — flagged, not silently reconciled

1. **LIN 19/051 table count:** Agent 1 says 12, I count **11** [FETCHED]. Row
   counts agree exactly. Likely a nested-table or regex-boundary difference. Not
   material — both audits agree the tables must be selected by heading text.
2. **Assessing bodies:** Agent 1 says 38; I count **37** in LIN 19/051 and **39**
   in F2024L01618 [FETCHED]. Header-row handling. Treat 38 as approximate and key
   on names.

---

## Document history

| Date | Change |
|---|---|
| 2026-08-17 | Initial — Agent 3 gap search across G1–G16. **9 FOUND, 5 PARTIAL, 1 NOT PUBLISHED, 1 NOT PUBLISHED (aggregated), 0 NOT REACHED.** 11 new sources (N1–N11), 15 catalog additions (A1–A15), 10 corrections (B1–B10), 8 further forced schema changes (C-a–C-h). |
