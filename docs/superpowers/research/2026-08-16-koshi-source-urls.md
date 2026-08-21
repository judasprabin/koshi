# koshi — Source URL Catalog (23 sources, content-verified)

**Status:** Research artifact — exact URLs and verified retrieval methods for
every koshi source (`docs/superpowers/specs/2026-08-16-koshi-etl-architecture.md` §4).
**Date:** 2026-08-16 · **Revised 2026-08-18** after the three-agent source audit
**Author:** Prabin Karki (via subagent URL-verification task)

> ### 2026-08-18 revision
>
> The original catalog verified that URLs **respond**. The 2026-08-17 audit
> fetched and decoded what they **contain**, and nine of the sixteen entries
> were materially wrong: the wrong URL, the wrong content type, the wrong
> extraction tier, or the wrong authority entirely.
>
> The single largest correction: **no `immi.homeaffairs.gov.au` page serves an
> HTML `<table>`.** Every one ships its content as HTML-entity-encoded JSON
> inside a hidden input. Entries below that said "HTML table" described markup
> that does not exist, which is why both built parsers extract zero rows.
>
> Evidence: the three-agent audit's per-agent working notes (page-by-page
> fetch results, schema mapping, gap search) have been removed now that
> their findings are folded into this catalog and `2026-08-16-koshi-data-model.md`;
> the decision-ready summary survives at
> `docs/superpowers/research/source-audit/CONSOLIDATED-FINDINGS.md`.
>
> ### 2026-08-18 (later) — 6 of these sources are now built
>
> `VERIFIED` in this catalog means the page was fetched and decoded, not that
> koshi ingests it. Six now have running extraction code:
>
> | # | Source | Module | Live volume |
> |---|---|---|---|
> | 1 | ANZSCO occupations (JSA) | `extraction/anzsco_occupations.py` | 1,236 over 103 paged fetches |
> | 2 | EOI rounds (current) | `extraction/skillselect_rounds.py` | 140 rows |
> | 9/13 | LIN 19/051 | `extraction/lin19051.py` | 504 pairs, 38 bodies |
> | 16/21 | BP0068 | `extraction/bp0068.py` | 622,425 records → 432 rows |
> | 17 | EOI previous rounds | `extraction/skillselect_previous_rounds.py` | 646 rows over 4 rounds |
> | 18 | ABS ANZSCO workbook | `extraction/abs_anzsco.py` | 1,076 occupations + 1,425 titles |
>
> All nine Home Affairs sources share `extraction/homeaffairs.py`, so the
> remaining ones need a parser, not a decoder.
>
> The other 17 entries are researched and **not built**.

## Quick reference — all 23 sources at a glance

Full detail for each is below; this table exists so you don't have to scroll
through it to find the 6 that are built.

| # | Source | Status |
|---|---|---|
| 1 | ANZSCO occupations | ✅ BUILT — superseded by 18 as the code/title source |
| 2 | EOI invitation rounds (current) | ✅ BUILT |
| 3 | Migration program planning levels | VERIFIED |
| 3b | Occupation ceilings | ❌ 404 / not published |
| 4 | Visa fees | VERIFIED |
| 5 | Points test criteria | VERIFIED |
| 6 | Visa subclass static facts | ✅ BUILT (via BP0068) |
| 7 | Health/character requirements | VERIFIED |
| 8 | Processing times | VERIFIED |
| 9 | MLTSSL/STSOL/ROL | extractor exists, sync not built |
| 10 | Skills priority list | VERIFIED |
| 11 | State nomination status | VERIFIED — most columns NO SOURCE |
| 12 | State occupation list changes | VERIFIED |
| 13 | Assessing bodies + join | extractor exists, sync not built |
| 14 | Policy events | VERIFIED — primary URL soft-404 |
| 15 | Funnel — invited | VERIFIED — `submitted_count` permanently unpublished |
| 16 | Funnel — granted | ✅ BUILT (via BP0068) |
| 17 | SkillSelect previous rounds | ✅ BUILT |
| 18 | ABS ANZSCO structure | ✅ BUILT |
| 19 | ABS ANZSCO↔OSCA correspondence | VERIFIED |
| 20 | Name→code crosswalk | ✅ BUILT |
| 21 | BP0068 outcomes | ✅ BUILT |
| 22 | English test bands | VERIFIED |
| 23 | legislation.gov.au OData | VERIFIED |

## How to read this

One table per source. Each row records, for that source's live page(s):

- **URL** — the exact URL to point `SourceSpec.url` at. Where a page redirects,
  the *effective* (final) URL is shown and the redirect noted in Notes.
- **Content type** — what the page *actually serves*, so the extraction tier
  choice is honest. Values now include `hidden-field JSON` (Home Affairs' real
  delivery mechanism), `JSON API`, `XLSX pivot cache`, `epub HTML tables`,
  alongside `HTML table` / `PDF` / `prose` / `dataset`.
- **Retrieval** — the concrete mechanism. For hidden-field pages this includes
  the **JSON root key**, which is *not* uniform across the site: main pages use
  `content`, `previous-rounds` uses `criteria`. Storing this per resource is
  mandatory, not cosmetic.
- **Cadence** — how often the page changes (drives the §9 cadence groups).
- **Tier** — extraction tier (1 crawl, 2 deterministic, 3 PDF, 4 LLM, 5 manual).
- **Feeds** — the Postgres table(s) the source populates.
- **Status** — `BUILT` = koshi has running extraction code for it (see the
  build table below); `VERIFIED` = content fetched **and decoded**, structure
  confirmed, but no code yet;
  `CONFIRMED` = URL returns 2xx but content unverified; `PROPOSED` = could not be
  verified live (reason in Notes); `DEAD` = does not serve what the catalog
  claimed. No URL below is fabricated.

Verification method (2026-08-17 pass): live fetch, then hidden-input decode
(`html.unescape` → `json.loads`) or format-appropriate parse, with structure and
row counts recorded. The earlier pass used
`curl -sS -o /dev/null -w "%{http_code} %{url_effective}" -L` with a Chrome 124
desktop `User-Agent` and reported status only. Where a site 403s datacenter IPs,
that is reported honestly rather than guessed around.

### The Home Affairs decode recipe

Applies to sources 2, 3, 4, 5, 6, 7, 8, 15, 17. Raw HTML contains **zero
`<table>` tags**; the content is in:

```
<input id="ctl00_PlaceHolderMain_PageSchemaHiddenField_Input" value="...">
```

Decode: `html.unescape(value)` → `json.loads` → walk the root key, then the
per-item HTML key. **Both axes vary**: most pages are `content[].block`;
`previous-rounds` is `criteria[].description`. No JS rendering and no headless
browser is required for any of them.

Implemented once in `src/koshi/extraction/homeaffairs.py`, which takes both
keys as explicit arguments and raises rather than returning empty when either
is absent — a silent zero-row extraction is the failure this module exists to
end.

---

## 1. ANZSCO occupations

| Field | Value |
|---|---|
| URL | `https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco` |
| Content type | HTML browse surface — **not** a code/title table |
| Retrieval | Use the ABS structure workbook instead (source 18) for code+title |
| Cadence | Near-static (ANZSCO version changes every few years) |
| Tier | 2 (deterministic) |
| Feeds | `occupations` — code, name, unit_group |
| Status | ✅ **BUILT** (`extraction/anzsco_occupations.py`) — paginated; superseded by source 18 as the authoritative code/title source |

Notes: This is the already-built source (`pipeline.py:36` `ANZSCO_URL`).

**Three corrections from the audit:**

1. **ANZSCO is being retired.** JSA carries a sitewide banner announcing the
   move to **OSCA** (Occupation Standard Classification for Australia). OSCA has
   **1,577** entries vs ANZSCO's **1,236**; JSA already dual-publishes ratings
   under both. Recommendation is *not* to migrate: the binding instrument
   (LIN 19/051) and every state list remain ANZSCO-coded. Keep ANZSCO as the PK,
   add an `anzsco_edition` column, and carry the ABS crosswalk (source 19).
2. **Three ANZSCO editions are simultaneously live** — `F2024L01616` pins
   migration to **2013**; the CSOL in `F2024L01618` is coded on **2022**;
   LIN 19/051 is on **2013**, and 25 of its codes are absent from 2022. An
   edition column is therefore load-bearing, not bookkeeping.
3. **This page is not where code+title lives.** For the authoritative
   title→code mapping use source 18 (ABS structure workbook, Table 6) plus
   source 9's Table 5 — see source 20 for why the union is required.

---

## 2. EOI invitation rounds (SkillSelect)

| Field | Value |
|---|---|
| URL | `https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds` |
| Content type | **hidden-field JSON** — zero `<table>` tags in raw HTML |
| Retrieval | Hidden-input decode, root key **`content`** |
| Cadence | ~monthly (a new row per invitation round) |
| Tier | 2 (deterministic) |
| Feeds | `eoi_rounds` — threshold_points, round_date |
| Status | ✅ **BUILT** (`extraction/skillselect_rounds.py`) — 140 rows, 0 skipped |

Notes: Already built (`pipeline.py:37` `SKILLSELECT_ROUNDS_URL`), and **the
built parser extracts zero rows.** Two independent reasons:

1. **Content type was wrong.** The page has no HTML tables at all. Use the
   decode recipe above.
2. **Table B's shape was wrong.** After decoding, Table B
   (*"Invitations issued by occupation and minimum score invited"*) has
   **2 columns — `Occupation | minimum score`** — and 140 data rows. The parser
   at `extraction/skillselect_rounds.py:49` unpacks **3** cells per row, so every
   row raises `ValueError`, is caught, and is skipped. A 100% skip rate
   currently exits cleanly; it should be a hard failure.

**The join-key problem (blocker).** Table B publishes occupation **names**
("Actuary", "Agricultural Consultant", "Carpenter") and **never ANZSCO codes**,
but `eoi_rounds.occupation_code` is an FK to `occupations.code`. No selector fix
resolves this — it requires the crosswalk in source 20.

The four decoded tables: **A** round totals (`Visa type | EOIs Invited | Tie
break date`), **B** occupation × minimum score (140 rows), **C** monthly
invitation matrix by subclass, **D** state/territory nominations.

`invitations_issued` is **not** available at Table B's grain — it lives in
Tables A and C at coarser grain. See source 15.

---

## 3. Migration program planning levels

> **This entry previously conflated two different things.** Planning levels are
> real and extractable. Per-occupation ceilings are a *separate* dataset that is
> **no longer published** — split out as source 3b below.

| Field | Value |
|---|---|
| URL | `https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels` |
| Content type | **hidden-field JSON** — full 3-year table, **zero PDFs on the page** |
| Retrieval | Hidden-input decode, root key `content` |
| Cadence | Irregular (a few times per year, Budget + mid-year updates) |
| Tier | **2** (was catalogued as tier 5 / PDF — wrong) |
| Feeds | `program_allocation` — places, stream_name |
| Status | **VERIFIED** — decoded in full |

Notes: The catalog claimed the numbers live in linked PDFs requiring manual
curation. The audit found **no PDFs on this page at all**; the complete
three-year planning-levels table is in the hidden-field JSON and is
Tier-2 extractable. `program_allocation` is buildable from this today.

Grain is **visa category** (Skilled / Family / Special Eligibility and their
streams). There are **no per-occupation rows** — see 3b.

---

## 3b. Occupation ceilings — **NOT PUBLISHED**

| Field | Value |
|---|---|
| URL | ~~`https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/occupation-ceilings`~~ |
| Content type | — |
| Cadence | — |
| Tier | — |
| Feeds | `ceiling_usage` (currently unpopulated by design) |
| Status | **DEAD** — HTTP 404, independently re-verified 2026-08-18 |

Notes: Per-occupation invitation ceilings are **not routinely published
anywhere**. Established by three independent checks:

- `/skillselect/occupation-ceilings` returns **HTTP 404**.
- The live SkillSelect "Occupation ceilings" section is **599 bytes of prose**
  with zero tables.
- **data.gov.au has no SkillSelect/EOI dataset.**

The only PY2025-26 ceiling table found is inside an **FOI disclosure release**
(`homeaffairs.gov.au/foi/files/2026/fa-260100545-document-released.PDF`) as
**scanned page images**, at **4-digit unit-group grain** — not the 6-digit grain
`ceiling_usage` is defined at.

⚠ **Do not map the FOI's issued-looking column to `ceiling_usage.issued`** — it
is *prior-year grants in other subclasses*, a different quantity. A genuine
issued-to-date must be derived from BP0068 (source 21).

This page was the `source_url` on two seeded `ceiling_usage` rows whose values
it does not contain. Those rows were removed
(`fix: remove unsourced ceiling_usage seed rows`); the seed file is now
comment-only and documents the three conditions for repopulating it.

---

## 4. Visa fees

| Field | Value |
|---|---|
| URL | `https://immi.homeaffairs.gov.au/visas/getting-a-visa/fees-and-charges` |
| API | `POST https://immi.homeaffairs.gov.au/_layouts/15/api/data.aspx/GetPriceList` |
| Content type | **JSON API** (undocumented but live) |
| Retrieval | POST to the endpoint; returns **150 records** directly as JSON |
| Cadence | Annual indexation (1 July) |
| Tier | 2 (deterministic — no HTML parsing at all) |
| Feeds | `visa_subclasses.base_application_cost`; see F6 — promote to its own table |
| Status | **VERIFIED** — 150 records returned |

Notes: **`/visa-fees` (the URL the original catalog assumed) returns 404.**
Better than the catalog assumed: the page is backed by a hidden JSON API that
returns all 150 fee records without any HTML parsing. Prefer the API over the page.

Two schema consequences:

- 150 fee records vs `visa_subclasses`' 6 rows — the fee data is a **superset**
  of koshi's subclass table and supplies `visaSubclassCode`/`visaSubclassText`
  pairs useful for widening it (source 5 gap, F10).
- Fees vary by **stream**, which koshi has no dimension for, making
  `base_application_cost` ambiguous as a single scalar on `visa_subclasses`.

---

## 5. Points test criteria

| Field | Value |
|---|---|
| URL | `https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-independent-189/points-table` |
| Content type | **hidden-field JSON** (static — not JS-rendered) |
| Retrieval | Hidden-input decode, root key `content` |
| Cadence | Rare (points test changes only on major policy reform) |
| Tier | 2 (deterministic) |
| Feeds | `points_criteria_reference` — criterion_name, band_description, points_value |
| Status | **VERIFIED** — points table decoded |

Notes: **The catalogued URL was wrong.** `/points-tested` genuinely contains no
points table — but not because of JS rendering. The table lives at the **sibling
URL `/points-table`** shown above, as plain static content behind the standard
hidden-field decode.

**This refutes the "SharePoint SPA / may need Playwright" flag**, which was the
main justification for keeping a headless browser in the stack. No koshi source
requires JS rendering. `points_criteria_reference` is buildable today.

Scope note: points are a **single GSM test** specified in *Migration Regulations
1994* Schedule 6D — one table covering 189/190/491, not a per-subclass table.
There is no separate 190 or 491 points page to find.

---

## 6. Visa subclass static facts (189 / 190 / 491 / 485 / 500 / 482)

Six individual page URLs — one row each.

| Visa | URL | Content type | Status |
|---|---|---|---|
| 189 | `https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-independent-189` | HTML prose | **CONFIRMED** (200) |
| 190 | `https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-nominated-190` | HTML prose | **CONFIRMED** (200) |
| 491 | `https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-work-regional-provisional-491` | HTML prose | **CONFIRMED** (200) |
| 485 | `https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/temporary-graduate-485` | HTML prose | **CONFIRMED** (200) |
| 500 | `https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/student-500` | HTML prose | **CONFIRMED** (200) |
| 482 | `https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skills-in-demand-visa-subclass-482` | HTML prose | **CONFIRMED** (200) |

| Field | Value |
|---|---|
| Cadence | Rare (subclass definitions change only on reform) |
| Tier | 5 (manual YAML seed) — 6 rows, tier 4 skipped |
| Feeds | `visa_subclasses` — name, family, permanence, age_limit, work_rights_description, family_inclusion_rule, residency_requirement_description, occupation_list_required, onward_pathway_code, points_test_required |
| Status | **CONFIRMED** (all six) |

Notes: The 482 visa was renamed **"Skills in Demand"**; the legacy URL
`/visa-listing/temporary-skill-shortage-482` still 302-redirects to the
`skills-in-demand-visa-subclass-482` page above. Record the *effective* URL.

---

## 7. Health / character / English requirements

Three individual page URLs.

| Requirement | URL | Content type | Status |
|---|---|---|---|
| Health | `https://immi.homeaffairs.gov.au/help-support/meeting-our-requirements/health` | HTML prose | **CONFIRMED** (200) |
| Character | `https://immi.homeaffairs.gov.au/help-support/meeting-our-requirements/character` | HTML prose | **CONFIRMED** (200) |
| English language | `https://immi.homeaffairs.gov.au/help-support/meeting-our-requirements/english-language` | HTML prose | **CONFIRMED** (200) |

| Field | Value |
|---|---|
| Content type | **hidden-field JSON**, prose blocks — **zero tables on all three** |
| Retrieval | Hidden-input decode, root key `content` |
| Cadence | Rare (near-static reference prose) |
| Tier | 5 (manual YAML seed) — 3 rows |
| Feeds | `eligibility_requirements` — requirement_type, summary |
| Status | **VERIFIED** — live, prose only |

Notes: The template URL
`immi.homeaffairs.gov.au/help-support/meeting-our-requirements/{health,character,english-language}`
resolves exactly as written — all three live. `eligibility_requirements` is
buildable today from the decoded prose.

⚠ **The English page is prose only and cannot feed `english_test_bands`.** It
carries no test-score table. That table must come from legislation instead —
source 22.

---

## 8. Global visa processing times

| Field | Value |
|---|---|
| URL | `https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-processing-times/global-visa-processing-times` |
| API | `GetProcessGuideVisas` (subclass list) → `GetProcessGuideInfo` (per combo) |
| Content type | **JSON API** |
| Retrieval | Two-call API; **76 subclass × stream combinations** |
| Cadence | ~monthly |
| Tier | 2 (deterministic — no HTML parsing) |
| Feeds | `processing_times` |
| Status | **VERIFIED** — 76 combos enumerated |

Notes: Redirects from the older `/visas/getting-a-visa/visa-processing-times/...`
path — record the effective URL shown above.

**Two schema-breaking findings:**

1. **There is no median.** The API returns a **percentile distribution**, not a
   single figure. `processing_times.median_days` has no corresponding source
   field and must be re-modelled (F1).
2. **The stream dimension is missing.** Results are keyed by subclass **and
   stream** (76 combos across far fewer subclasses). `processing_times`' unique
   constraint has no stream column, so multi-stream subclasses — **485, 500,
   482, 186** — collide outright. This is a hard constraint violation, not a
   fidelity concern.

`as_of_date` is not in the API payload; the page states the calculation window
and update rule in prose only.

---

## 9. MLTSSL / STSOL / ROL — legislation.gov.au legislative instruments

The three occupation lists are specified together in a single current
legislative instrument, **LIN 19/051**. The instrument and the two closely
related instruments are:

| Instrument | URL | Content type | Status |
|---|---|---|---|
| **Migration (LIN 19/051: Specification of Occupations and Relevant Assessing Authorities) Instrument 2019** (MLTSSL / STSOL / ROL + assessing authorities) | `https://www.legislation.gov.au/F2019L00278/latest` | HTML (compiled instrument; schedules list occupations) | **CONFIRMED** (200) |
| Migration (Specification of Occupations and Relevant Assessing Authorities—Subclass 186 Visa) Instrument 2024 | `https://www.legislation.gov.au/F2024L01618` | HTML | **CONFIRMED** (200) |
| Migration (ANZSCO Definition) Specification 2024 | `https://www.legislation.gov.au/F2024L01616/latest` | HTML | **CONFIRMED** (200) |

| Field | Value |
|---|---|
| Content type | **epub HTML tables**, one iframe-hop from the register page |
| Retrieval | Follow the iframe to the static epub doc → **12 tables, no id/class — positional access only** |
| Cadence | A few times per year (amendments re-specify list membership) |
| Tier | 2 (deterministic) |
| Feeds | `occupation_assessing_bodies`, `assessing_bodies`, list membership, `list_change_log` |
| Status | ✅ **BUILT** (`extraction/lin19051.py`) — positional tables with row-count assertions |

Notes: **Research method** — searched the Federal Register of Legislation for
"Specification of Occupations and Assessing Authorities". The only currently
**"In force"** general-purpose occupation-list instrument is LIN 19/051
(F2019L00278, current compilation 2026-03-28); IMMI 17/072, IMMI 18/007,
IMMI 18/051 etc. are all "No longer in force".

**The real content is one iframe-hop away.** The register page is a shell; the
instrument body is a static epub HTML document containing **12 tables with no
`id` or `class` attributes** — they must be addressed **positionally**, which
makes table order a breaking-change risk worth asserting on.

Verified table contents:

| Table | Rows | Content |
|---|---|---|
| **5** | **504** | occupation → assessing-authority join |
| **6** | **38** | assessing-body name key |
| 7–11 | — | amendment history (**not opened** — may supply `effective_date`) |

This is the correct authority for `assessing_bodies` — **not MARA** (source 13).

Companion instruments:

- **`F2024L01618`** (Subclass 186 / CSOL) — coded on ANZSCO **2022**, 100% match.
- **`F2024L01616`** (ANZSCO Definition) — **contains zero tables.** It is purely
  definitional and pins migration to the ANZSCO **2013** edition. Useful as the
  edition pin; useless as a data source. LIN 19/051 is likewise on 2013, and
  **25 of its codes are absent from ANZSCO 2022**.

For version history, prefer the **OData API** (source 23) over scraping.

---

## 10. Jobs & Skills Australia — skills priority list

| Field | Value |
|---|---|
| URL | `https://www.jobsandskills.gov.au/data/occupation-shortage/occupation-shortage-list` |
| Content type | JSON (`splData` / `splSearch`) embedded in the page |
| Retrieval | Parse the embedded JSON payload |
| Cadence | Annual (refreshed each year) |
| Tier | 2 (deterministic) |
| Feeds | `skills_priority_ratings` — shortage_rating, as_of_date |
| Status | **VERIFIED** — payload and vocabulary confirmed |

Notes: **Redirects** from `/skills-priority-list` (the "Skills Priority List"
was rebranded "Occupation Shortage List"). Record the effective URL above.

**Rating vocabulary resolved** (§13 open question #2 — closed). From JSA's own
methodology PDF, there are exactly **four** classifications:

| Code | Meaning |
|---|---|
| `S` | Shortage |
| `M` | Metropolitan shortage |
| `R` | Regional shortage |
| `NS` | No shortage |

`Ns` seen in the payload is a **casing bug**, not a fifth value. The CHECK
constraint should be exactly these four, compared case-insensitively.

**`future_demand_rating` has no source** — the `d` field in `splData` is null
throughout. Ship NULL or drop the column.

JSA publishes ratings against **both ANZSCO and OSCA**, and mixes 4-digit and
6-digit codes — so this source alone requires the edition and grain columns from
source 1's note.

---

## 11. State nomination status (NSW / VIC / QLD / WA / SA)

Five per-state page URLs.

| State | URL (nomination / program landing page) | Status |
|---|---|---|
| NSW | `https://www.nsw.gov.au/visas-and-migration/skilled-visas` | **CONFIRMED** (200) |
| VIC | `https://liveinmelbourne.vic.gov.au/migrate` | **PROPOSED** (403 — Cloudflare bot challenge) |
| QLD | `https://migration.qld.gov.au/visa-options/skilled-visas` | **CONFIRMED** (200) |
| WA | `https://migration.wa.gov.au/our-services-support/state-nominated-migration-program` | **CONFIRMED** (200) |
| SA | `https://migration.sa.gov.au/before-applying/work-in-sa/occupation-lists` | **CONFIRMED** (200) |

| Field | Value |
|---|---|
| Content type | HTML prose landing pages (general "how to apply", not per-occupation tables) |
| Cadence | Irregular (each state re-opens/closes its program independently) |
| Tier | 5 (manual YAML seed — highest per-row curation effort) |
| Feeds | `state_nomination_status` — status, fee, points_minimum, job_offer_required, residency_commitment_description, decision_time_estimate, documents_required, approval_pattern_note |
| Status | **CONFIRMED** (4 of 5); **VIC PROPOSED** |

Notes: **VIC** is served behind Cloudflare bot detection —
`liveinmelbourne.vic.gov.au` returns 403 to both curl (datacenter IP) and a
headless browser ("Performing security verification" challenge). The page
exists but its content could not be confirmed; treat as PROPOSED and re-verify
from a residential IP or a human browser. NSW's precise sub-pages
(`/skilled-nominated-visa-subclass-190`, `/skilled-work-regional-visa-subclass-491`)
are also **CONFIRMED** (200) and are the correct per-subclass targets.

**Audit corrections:**

- **None of the columns this source is supposed to feed were found on any state
  page.** Fees, minimum points, job-offer requirement, decision-time estimates
  and document checklists are absent across NSW/VIC/QLD/WA/SA, and **no
  aggregated source exists**. Most of `state_nomination_status` therefore has no
  source at all — the table needs re-graining (F11) or most columns ship NULL.
- **NSW joins at 4-digit unit groups**, QLD at 6-digit. The FK to
  `occupations.code` cannot assume one width.
- **SA is legitimately empty** — the program is between intake rounds, not
  broken. koshi must distinguish "closed" from "scrape failed", or SA will look
  like a recurring pipeline error.
- **WA's list returns 0 by default** — the Views search form shows
  "Displaying 0 occupation(s)" until queried, and the catalogued
  `#2025-26-eligible-occupations` anchor **does not exist** on the page.

---

## 12. State occupation list changes

| Field | Value |
|---|---|
| URL | Same state pages as source 11, via `source_pages` hash-diff (no separate page) |
| Content type | HTML (state occupation-list pages) |
| Cadence | Irregular (state lists change throughout the program year) |
| Tier | 1 → 5 (`source_pages` hash-diff is the *trigger*; human review + YAML seed is the *write*) |
| Feeds | `list_change_log` — list_name = state code, change_type, effective_date |
| Status | **CONFIRMED** for the NSW/QLD/WA/SA list pages; **PROPOSED** for VIC (see source 11) |

Notes: Concrete state occupation-list URLs verified (200):

- NSW skills lists — `https://www.nsw.gov.au/visas-and-migration/skilled-visas/nsw-skills-lists`
- QLD offshore QSOL — `https://migration.qld.gov.au/occupation-lists/offshore-queensland-skilled-occupation-lists-(qsol)`
- WA program (occupations section) — `https://migration.wa.gov.au/our-services-support/state-nominated-migration-program#2025-26-eligible-occupations`
- SA occupation lists — `https://migration.sa.gov.au/before-applying/work-in-sa/occupation-lists` and `.../occupation-lists/occupations-list`

VIC's occupation list lives under the Cloudflare-blocked `liveinmelbourne.vic.gov.au`
— PROPOSED.

---

## 13. Assessing bodies (skills assessing authorities)

| Field | Value |
|---|---|
| URL | **`https://www.legislation.gov.au/F2019L00278/latest`** (epub Tables 5 & 6) |
| Content type | epub HTML tables — see source 9 |
| Retrieval | iframe-hop → positional table access: **Table 6** = 38 bodies, **Table 5** = 504-row join |
| Cadence | Rare (bodies change infrequently) |
| Tier | 2 (deterministic) — was catalogued tier 5 |
| Feeds | `assessing_bodies` — body_name; `occupation_assessing_bodies` — join |
| Status | ✅ **BUILT** (`extraction/lin19051.py` Table 6) — replaces MARA |

~~`https://portal.mara.gov.au/search-the-register-of-migration-agents/`~~ —
**wrong authority, do not use.**

Notes: **The correctness flag raised here is confirmed and now resolved.** MARA
(Office of the Migration Agents Registration Authority) registers **migration
agents**, not **skills assessing authorities** (Engineers Australia, ACS,
VETASSESS, CPA, ANMAC, …). The authoritative source is **LIN 19/051**, which
specifies "Relevant Assessing Authorities" alongside the occupation lists, and
it supplies the real data: 38 bodies and a 504-row occupation→authority join.

**Two mapping hazards found in that data:**

1. **Table 5 names bodies by abbreviation; Table 6 keys them by full name.** The
   FK between the join table and `assessing_bodies` does not match on a raw
   string compare — an explicit abbreviation↔name mapping is required.
2. **Some occupations list "either body"** — a disjunction. A plain
   `(occupation, body)` join row cannot express "either A or B", and silently
   flattening it would misstate the requirement.

**`turnaround_estimate` and `cost` have no source.** No aggregated publication
exists; the data lives on each of the ~38 bodies' own sites. Ship NULL rather
than curate 38 separate scrapers.

---

## 14. Policy events (budget / treasury / ministerial)

| Field | Value |
|---|---|
| URL | ~~`https://budget.gov.au/content/migration.htm`~~ → use **Budget Paper No. 3** |
| Content type | HTML / PDF budget papers (migration program) |
| Cadence | Ad hoc (Budget annually; ministerial releases on policy change) |
| Tier | 5 (manual YAML seed — explicitly editorial) |
| Feeds | `policy_events` — event_date, visa_code (nullable), description |
| Status | **DEAD (soft-404)** — replacement is partial |

⚠ **`budget.gov.au/content/migration.htm` is a soft-404**: it returns **HTTP 200**
with a "Page not found" body, after the 2026-27 budget site restructure. A
status-code-only health check passes it silently — koshi's fetcher must assert
on body content, not just status (see the architecture doc's fault-tolerance
section).

Budget migration numbers now live in **Budget Paper No. 3**. Ministerial media
releases have **no machine-readable index** — this source stays editorial.

Companion URLs:

| Domain | URL | Status |
|---|---|---|
| Treasury (root, policy context) | `https://treasury.gov.au/` | **CONFIRMED** (200) |
| Ministerial media releases | `https://minister.homeaffairs.gov.au/` | **CONFIRMED** (200) |
| Budget (root) | `https://budget.gov.au/` | **CONFIRMED** (200) |

Notes: `budget.gov.au/content/migration.htm` is the migration-program budget
paper index — the concrete page that announces annual planning levels (which
also feeds source 3). Ministerial press releases live under
`minister.homeaffairs.gov.au/` and change per-release; there is no single
stable "all events" URL to scrape — this source is editorial by design.

---

## 15. Application funnel — submitted / invited

| Field | Value |
|---|---|
| URL | `https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds` |
| Content type | HTML table (per-round invitations issued) |
| Cadence | ~monthly |
| Tier | 2 — **piggybacked on the existing SkillSelect fetch** (extend `parse_skillselect_rounds`, do not fetch the URL twice) |
| Feeds | `application_funnel` — submitted_count, invited_count |
| Status | **CONFIRMED** (200) |

Notes: Identical URL to source 2 — piggyback the same fetch and decode.

**`submitted_count` is not published anywhere.** Resolved, not merely
suspected: the entire decoded SkillSelect page was searched for `submitted`,
`lodged`, `EOIs on hand`, `EOIs in the system` and `pool` — **zero matches** —
and data.gov.au carries 12 Home Affairs datasets, none of them a SkillSelect/EOI
dataset. **Ship `submitted_count = NULL` permanently**, and record it as
unavailable rather than pending.

`invited_count` **is** available, from decoded Tables A and C — but at
round/subclass grain, not per occupation.

---

## 16. Application funnel — granted (Home Affairs annual report)

| Field | Value |
|---|---|
| URL | **`https://data.gov.au/data/dataset/permanent-migration-program-skilled-family`** (BP0068) |
| Content type | **XLSX pivot cache** — see source 21 for the full entry |
| Cadence | Annual |
| Tier | 2 (deterministic, structured file) — was tier 5 |
| Feeds | `application_funnel.granted_count` |
| Status | **VERIFIED** — 622,425 records parsed |

~~`https://www.homeaffairs.gov.au/reports-and-publications/reports/annual-reports`~~
— 44 report PDFs, none opened, and now unnecessary.

Notes: The canonical doc marked `granted_count` the **weakest-sourced field**,
to be shipped NULL if no pathway-level breakdown existed. **A far better source
exists**: Home Affairs publishes BP0068 on data.gov.au under CC-BY, with
per-subclass, per-occupation, per-program-year grant counts.

`granted_count` moves from "probably NULL" to **fully sourced**. Full retrieval
details in source 21 — note the data is in the workbook's **pivot cache**, not
its worksheets.

---

## New sources added by the 2026-08-17 audit

Sources 17–23 were not in the original catalog. All are content-verified.

---

## 17. SkillSelect previous rounds (invitation history)

| Field | Value |
|---|---|
| URL | `https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/previous-rounds` |
| Content type | **hidden-field JSON** |
| Retrieval | Hidden-input decode, root key **`criteria`**, item key **`description`** — *not* `content`/`block` |
| Cadence | ~monthly (appended per round) |
| Tier | 2 (deterministic) |
| Feeds | `eoi_rounds` — historical backfill |
| Status | ✅ **BUILT** (`extraction/skillselect_previous_rounds.py`) — see the correction below |

Notes: Supplies history where source 2 gives only the current round — the
difference between a point reading and a trend.

⚠ **Correction to the audit's figure.** The audit recorded "19 rounds, 1,419
rows". Building it showed only **4 of the 19 rounds carry an occupation
table** at all (144, 131, 161 and 149 rows = 585); the other 15 publish
summary figures only. The 1,419 count included those summary tables. koshi
extracts **646 rows** from the 4, because recent rounds publish one column
*per subclass* and a single occupation row yields up to two EOI rows.

⚠ **The table's shape varies by round**: recent rounds are
`Occupation | 189 | 491`, older ones a single score column with the subclass
named in the header or only in the round-summary table. A fixed column count
drops one era or the other. `N/A*` means not invited in that subclass.

⚠ **Two independent key differences, not one.** The root key is `criteria`
rather than `content`, *and* each item carries its HTML under `description`
rather than `block`. The audit found the first; building it found the second.
A parser hard-coding either raises. Both are configured per resource in
`extraction_strategies`, never sniffed.

The round date is on the item (`title`) and is authoritative: the HTML
heading's `id` is stale on the live page — `id="invitations-issued-13062024"`
sits above text reading "13 November 2025".

---

## 18. ABS ANZSCO structure workbook

| Field | Value |
|---|---|
| URL | ABS ANZSCO release — `anzsco 2022 structure 062023.xlsx` |
| Content type | XLSX |
| Retrieval | **Table 6** — 1,425 code/title pairs |
| Cadence | Per ANZSCO edition (rare) |
| Tier | 2 (deterministic, structured file) |
| Feeds | `occupations` — code, name; the crosswalk in source 20 |
| Status | ✅ **BUILT** (`extraction/abs_anzsco.py`) — Table 6 for titles, Table 5 for occupations |

Notes: The authoritative ANZSCO code↔title list. Resolves **132 of 140** live
SkillSelect occupation names on its own — see source 20 for why that is not
sufficient alone.

---

## 19. ABS ANZSCO ↔ OSCA correspondence

| Field | Value |
|---|---|
| URL | ABS — `OSCA correspondence tables v2.xlsx` |
| Content type | XLSX (10 tables) |
| Retrieval | Includes **ANZSCO v1.3 → OSCA** and **ANZSCO 2022 → OSCA**, with a `p` partial-match flag |
| Cadence | Per edition |
| Tier | 2 (deterministic, structured file) |
| Feeds | new `anzsco_osca_crosswalk` table |
| Status | **VERIFIED** |

Notes: The migration path for the ANZSCO→OSCA retirement (source 1). The `p`
flag marks partial matches — the mapping is **not** one-to-one, so a naive join
silently drops or duplicates occupations. Carrying this crosswalk is what makes
keeping ANZSCO as the PK viable.

---

## 20. Occupation name → code crosswalk (composite)

| Field | Value |
|---|---|
| URL | Union of source 18 (ABS Table 6) and source 9 (LIN 19/051 Table 5) |
| Content type | derived |
| Retrieval | **LIN-first**, then ABS fallback |
| Cadence | Per edition |
| Tier | derived |
| Feeds | `eoi_rounds.occupation_code` — unblocks the Occupation vertical |
| Status | **VERIFIED** — union resolves **140/140** |

Notes: This entry exists because **neither source alone is sufficient**, which
was established by measurement rather than assumption:

| Source | Pairs | Resolves |
|---|---|---|
| ABS Table 6 (source 18) | 1,425 | 132/140 |
| LIN 19/051 Table 5 (source 9) | 504 | 132/140 |
| **Union** | — | **140/140** |

Two hazards:

- **8 names are LIN-only** — an ABS-only implementation silently drops them.
- **3 titles resolve to *different codes* in the two sources**: **Management
  Consultant**, **Plumber (General)**, **Statistician**. Lookup order is
  therefore **LIN-first**, because LIN 19/051 is the binding instrument. An
  ABS-first implementation produces wrong codes for these three without erroring.

---

## 21. BP0068 — permanent migration program outcomes

| Field | Value |
|---|---|
| URL | `https://data.gov.au/data/dataset/permanent-migration-program-skilled-family` |
| API | `https://data.gov.au/data/api/3/action/package_show?id=permanent-migration-program-skilled-family` |
| Content type | **XLSX pivot cache** (5,237,461 bytes; ~119 MB uncompressed) |
| Retrieval | ⚠ **Data is in the pivot cache, not the worksheets** — pandas/openpyxl return nothing useful. A stdlib XML reader parses all records in ~4.8s |
| Cadence | Annual |
| Tier | 2 (deterministic, structured file) |
| Feeds | `application_funnel.granted_count`; `visa_subclasses` taxonomy; `ceiling_usage.issued` if re-sourced |
| Status | ✅ **BUILT** (`extraction/bp0068.py`) — 622,425 records parsed in ~4.7s; CC-BY 2.5 |

Notes: **The single largest addition this audit makes.** Home Affairs-published,
CC-BY, annually refreshed:

- **622,425 records** · **10 program years** · **62 visa subclasses** ·
  **764 ANZSCO-coded occupations** · 18 fields
- Skilled subclasses present: 186, 189, 190, 491, 494, 858, 888
- Carries a 5-level **Program → Category → Type → Sub-type → Subclass**
  hierarchy — the visa taxonomy `visa_subclasses` lacks

Found by following a citation inside the FOI ceilings PDF; three CKAN searches
had missed it. The dataset ships a "pivot table user guide" PDF, corroborating
the pivot-cache access route.

Caveat: its 62 subclasses are only those **with grants**, so it is not a
complete subclass registry.

---

## 22. English language test bands (legislative instruments)

| Field | Value |
|---|---|
| URL | `https://www.legislation.gov.au/F2025L00905` (LIN 25/016) · `https://www.legislation.gov.au/F2025L00904` |
| Content type | epub HTML tables |
| Retrieval | `F2025L00905` Schedule 2 — **4 bands × 9 tests × 4 skills**; `F2025L00904` — Functional English, 8 tests |
| Cadence | Rare (instrument amendment) |
| Tier | 2 (deterministic) |
| Feeds | `english_test_bands` — test_name, band_level, score_requirement |
| Status | **VERIFIED** — full matrix transcribed |

Notes: Replaces the Home Affairs English page (source 7), which has no tables.
Covers Vocational / Competent / Proficient / Superior in `F2025L00905`, with
Functional English specified separately in `F2025L00904`.

⚠ **Parser hazard:** Schedule 2's table uses **12 `rowspan` attributes**. Naive
`td`-indexing misaligns the Superior rows — the parser must track rowspan state
or it will silently attribute the wrong scores to the wrong band.

---

## 23. legislation.gov.au OData API (compilation history)

| Field | Value |
|---|---|
| URL | OData register-item API on `/F2019L00278/latest` |
| Content type | JSON |
| Retrieval | Register-item JSON enumerates every compilation with dates + amendment reasons |
| Cadence | Per amendment |
| Tier | 2 (deterministic) |
| Feeds | `list_change_log.effective_date`, `change_type` |
| Status | **VERIFIED** — 7-version history retrieved |

Notes: Closes the "register serves compilations, not diffs" gap. The API hands
over LIN 19/051's **full 7-version compilation history with effective dates and
amendment reasons**, so `list_change_log.effective_date` — which Agent 2 found
had **no source**, meaning a cold start produced zero rows — becomes sourceable.
Diff membership between successive compilations to synthesise change rows.

---

## GAPS — sources still missing a confirmed or sufficient URL

Most of the original gaps are **closed**. What remains is recorded honestly as
either *unpublished* (stop looking), *inaccessible* (a network problem, not a
data problem), or *unreached* (real work left).

### Closed by the audit

| # | Original gap | Resolution |
|---|---|---|
| 5 | Points table "may be JS-rendered" | **Closed.** Wrong URL, not JS. Real table at `/points-table`, static. No Playwright needed anywhere. |
| 9 | Register serves compilations, not diffs | **Closed.** OData API (source 23) supplies the 7-version history with effective dates. |
| 10 | JSA vocabulary unconfirmed | **Closed.** Exactly 4 values: `S`/`M`/`R`/`NS`. `Ns` is a casing bug. |
| 13 | MARA is the wrong authority | **Closed.** Re-sourced to LIN 19/051 Tables 5 & 6. |
| 15 | Is `submitted_count` published? | **Closed — it is not.** Ship NULL permanently. |
| 16 | Which annual-report PDF? | **Closed.** Superseded by BP0068 (source 21) — better data, no PDF parsing. |

### Genuinely unpublished — stop looking, ship NULL

| Field / table | Finding |
|---|---|
| `ceiling_usage` (6-digit) | Not published. FOI-only, scanned images, 4-digit grain. |
| `application_funnel.submitted_count` | Not published in any form. |
| `assessing_bodies.turnaround_estimate`, `.cost` | No aggregated source; ~38 separate sites. |
| `skills_priority_ratings.future_demand_rating` | JSA's `d` field is null throughout. |
| `visa_subclasses.permanence` | Not published as structured data anywhere found. |
| `state_nomination_status` — fees, points, job-offer, decision time, documents | Absent from every state page; no aggregated source. |

### Inaccessible — a network problem, not a data problem

| # | Source | Obstacle |
|---|---|---|
| 11/12 | **VIC** | `liveinmelbourne.vic.gov.au` 403s (Cloudflare) to curl **and** headless browser. Re-verify from a residential IP or curate from a human-checked snapshot. |
| 11/12 | **WA** | Views form returns "Displaying 0 occupation(s)" until queried; catalogued anchor does not exist. Needs a documented query parameter or a downloadable list. |
| 11/12 | **SA** | Not blocked — legitimately between intake rounds. Model as "closed", not "failed". |

### Not reached — real work remaining

- BP1 / BP2 datasets (siblings of BP0068).
- `minister.homeaffairs.gov.au` — no machine-readable index found; still editorial.
- ABS **EQ08** internals (Labour Force Detailed) — identified as the bulk
  labour-market dataset and the Department's own stated ceiling input, but its
  structure was not opened.
- LIN 19/051 epub **tables 7–11** (amendment history) — may supply
  `effective_date` directly, superseding the diff approach.
- FOI release `fa-260100545` pages 3–5.

### Summary counts

| Metric | Count |
|---|---|
| Sources catalogued | **23** (was 16) |
| **BUILT** (running extraction code) | **6** |
| **VERIFIED** (content fetched and decoded, not built) | 13 |
| **PROPOSED** (blocked at the network edge) | 1 — VIC |
| **DEAD** (does not serve what was claimed) | 2 — occupation-ceilings (404), budget migration page (soft-404) |
| Entries materially corrected | **9 of the original 16** |
| Sources needing JS rendering / Playwright | **0** |

**Correctness flags remaining:** LIN 19/051 tables are positional (no `id`/`class`)
— assert on table order; `F2025L00905`'s rowspans break naive `td`-indexing;
BP0068 needs pivot-cache access, not a worksheet read; and the Home Affairs JSON
root key varies per page (`content` vs `criteria`).
