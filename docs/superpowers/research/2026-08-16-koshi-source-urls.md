# koshi — Source URL Catalog (16 sources, verified)

**Status:** Research artifact — exact, live-verified URLs for every source in
the canonical 16-source catalog (`docs/superpowers/specs/2026-08-16-koshi-etl-architecture.md` §4).
**Date:** 2026-08-16
**Author:** Prabin Karki (via subagent URL-verification task)

## How to read this

One table per source. Each row records, for that source's live page(s):

- **URL** — the exact URL to point `SourceSpec.url` at. Where a page redirects,
  the *effective* (final) URL is shown and the redirect noted in Notes.
- **Content type** — `HTML table` / `PDF` / `prose` / `dataset` — what the page
  actually serves, so the extraction tier choice is honest.
- **Cadence** — how often the page changes (drives the §9 cadence groups).
- **Tier** — extraction tier (1 crawl, 2 HTML, 3 PDF, 4 LLM, 5 manual) per the
  canonical doc.
- **Feeds** — the Postgres table(s) the source populates.
- **Status** — `CONFIRMED` = `curl -L` returned 2xx/3xx from this environment;
  `PROPOSED` = could not be verified live (reason in Notes). No URL below is
  fabricated; every `PROPOSED` entry is a real, researched URL that either
  returned a non-2xx or was blocked at the network edge, and is flagged as such.

Verification method: `curl -sS -o /dev/null -w "%{http_code} %{url_effective}" -L`
with a Chrome 124 desktop `User-Agent` (to avoid CDN blocking on `.gov.au`
sites), `--connect-timeout 15 --max-time 30`, run from a datacenter IP.
Where a site 403s datacenter IPs, that is reported honestly rather than guessed
around.

---

## 1. ANZSCO occupations

| Field | Value |
|---|---|
| URL | `https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco` |
| Content type | HTML (occupation/industry profile search + ANZSCO dataset) |
| Cadence | Near-static (ANZSCO version changes every few years) |
| Tier | 2 (deterministic HTML) |
| Feeds | `occupations` — code, name, unit_group |
| Status | **CONFIRMED** (200) |

Notes: This is the already-built source (`pipeline.py:36` `ANZSCO_URL`). It is
the occupation-and-industry-profile ANZSCO browse/search surface. The *legal*
ANZSCO definition (the new `Migration (ANZSCO Definition) Specification 2024`)
is a separate instrument — see source 9.

---

## 2. EOI invitation rounds (SkillSelect)

| Field | Value |
|---|---|
| URL | `https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds` |
| Content type | HTML table (per-round thresholds + invitations) |
| Cadence | ~monthly (a new row per invitation round) |
| Tier | 2 (deterministic HTML) |
| Feeds | `eoi_rounds` — threshold_points, invitations_issued, round_date |
| Status | **CONFIRMED** (200) |

Notes: Already built (`pipeline.py:37` `SKILLSELECT_ROUNDS_URL`). This exact
URL is also the source for the funnel's `submitted_count` / `invited_count`
(source 15) — piggyback, do not fetch twice.

---

## 3. Occupation ceilings / migration program planning levels

| Field | Value |
|---|---|
| URL | `https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels` |
| Content type | Prose page linking to the periodic planning-levels **PDF** report |
| Cadence | Irregular (a few times per year, aligned to the Federal Budget + mid-year updates) |
| Tier | 5 (manual YAML curation) — the PDF is tier 3, deliberately unbuilt |
| Feeds | `ceiling_usage` — ceiling; `program_allocation` — places, stream_name |
| Status | **CONFIRMED** (200) |

Notes: Already the `source_url` in `seeds/ceiling_usage_manual.yaml`. The page
is the stable index; the actual numbers live in linked PDFs that change URL
each release. Curate from the page + its latest PDF rather than scraping.

---

## 4. Visa fees

| Field | Value |
|---|---|
| URL | `https://immi.homeaffairs.gov.au/visas/getting-a-visa/fees-and-charges` |
| Content type | HTML (fee tables / fee-calculator surface) |
| Cadence | Irregular (annual indexation, 1 July) |
| Tier | 2 (deterministic HTML) |
| Feeds | `visa_subclasses.base_application_cost` (update-by-PK, not insert) |
| Status | **CONFIRMED** (200) |

Notes: **`/visa-fees` (the URL in `docs/data-sources.md`) returns 404.** The
live page is the one above. Confirm the exact fee-table markup at build time —
the page may be JS-augmented.

---

## 5. Points test criteria

| Field | Value |
|---|---|
| URL | `https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-independent-189/points-tested` |
| Content type | HTML prose + points table (SharePoint page; table may be JS-rendered) |
| Cadence | Rare (points test changes only on major policy reform) |
| Tier | 2 (deterministic HTML) — flagged: confirm table is in static HTML vs. JS |
| Feeds | `points_criteria_reference` — criterion_name, band_description, points_value |
| Status | **CONFIRMED** (200) |

Notes: **`/visas/working-in-australia/skillselect/points-test` (the URL in
`docs/data-sources.md`) returns 404.** The live points-tested stream page for
subclass 189 is the canonical points-criteria location. **Flag:** the page is a
SharePoint SPA and the raw HTML does not contain the numeric points table — it
may be loaded client-side. This contradicts the "clean deterministic HTML"
assumption and should be re-verified before committing to pure tier 2.

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
| Cadence | Rare (near-static reference prose) |
| Tier | 5 (manual YAML seed) — 3 rows |
| Feeds | `eligibility_requirements` — requirement_type (health/character/english_language), summary |
| Status | **CONFIRMED** (all three) |

Notes: The `docs/data-sources.md` template URL
`immi.homeaffairs.gov.au/help-support/meeting-our-requirements/{health,character,english-language}`
resolves exactly as written — all three live.

---

## 8. Global visa processing times

| Field | Value |
|---|---|
| URL | `https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-processing-times/global-visa-processing-times` |
| Content type | HTML table (visa × median processing days, updated monthly) |
| Cadence | ~monthly |
| Tier | 2 (deterministic HTML — same shape as SkillSelect parser) |
| Feeds | `processing_times` — median_days, as_of_date |
| Status | **CONFIRMED** (200) |

Notes: Redirects from the older `/visas/getting-a-visa/visa-processing-times/...`
path — record the effective URL shown above.

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
| Cadence | A few times per year (amendments re-specify list membership) |
| Tier | 2 (deterministic HTML) — **flag:** confirm legislation.gov.au's real HTML structure at build time (§13 open question #1) |
| Feeds | `list_change_log` — list_name (MLTSSL/STSOL/ROL), occupation_code, change_type, effective_date |
| Status | **CONFIRMED** (all three) |

Notes: **Research method** — searched the Federal Register of Legislation
(`legislation.gov.au/search`) for "Specification of Occupations and Assessing
Authorities". The only currently **"In force"** general-purpose occupation-list
instrument is LIN 19/051 (F2019L00278, effective 28/03/2026); the earlier
IMMI 17/072, IMMI 18/007, IMMI 18/051, etc. are all "No longer in force". The
Subclass 186 instrument (F2024L01618) and the ANZSCO Definition instrument
(F2024L01616) are the companion specifications. `list_change_log` membership
must be diffed between instrument versions — the register serves versioned
compilations, not a raw change log.

---

## 10. Jobs & Skills Australia — skills priority list

| Field | Value |
|---|---|
| URL | `https://www.jobsandskills.gov.au/skills-priority-list` |
| Content type | HTML + downloadable dataset (redirects to the Occupation Shortage List) |
| Cadence | Annual (refreshed each year) |
| Tier | 2 (BS4/lxml, or `pandas`/`openpyxl` if a downloadable dataset is offered) |
| Feeds | `skills_priority_ratings` — shortage_rating, future_demand_rating, as_of_date |
| Status | **CONFIRMED** (200 → redirect) |

Notes: **Redirects** to
`https://www.jobsandskills.gov.au/data/occupation-shortage/occupation-shortage-list`
(the "Skills Priority List" was rebranded "Occupation Shortage List"). Record
the effective URL. **Flag:** confirm JSA's exact rating vocabulary
(shortage rating / future demand) against the live page before committing to
`skills_priority_ratings` schema (§13 open question #2).

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
exists (it is Victoria's skilled-migration landing page) but its 200 status
could not be confirmed from this environment; treat as PROPOSED and re-verify
from a residential IP or a human browser. NSW's precise sub-pages
(`/skilled-nominated-visa-subclass-190`, `/skilled-work-regional-visa-subclass-491`)
are also **CONFIRMED** (200) and are the correct per-subclass targets.

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
| URL | `https://portal.mara.gov.au/search-the-register-of-migration-agents/` |
| Content type | HTML (searchable register) |
| Cadence | Rare (bodies change infrequently) |
| Tier | 5 (manual YAML seed) |
| Feeds | `assessing_bodies` — body_name, turnaround_estimate, cost; `occupation_assessing_bodies` — join |
| Status | **CONFIRMED** (200) |

Notes: **Correctness flag (important).** The docs (`docs/data-sources.md`,
canonical §4) name `mara.gov.au` as the assessing-bodies source, but MARA
(Office of the Migration Agents Registration Authority) registers **migration
agents**, *not* **skills assessing authorities** (Engineers Australia, ACS,
VETASSESS, CPA, ANMAC, etc.). The authoritative source for which body assesses
which occupation is **LIN 19/051 itself** (`F2019L00278` — it specifies the
"Relevant Assessing Authorities" alongside the occupation lists), plus each
body's own site. The MARA register URL above is the closest live `mara.gov.au`
page, but it is the wrong source for `assessing_bodies`; see GAPS.

---

## 14. Policy events (budget / treasury / ministerial)

| Field | Value |
|---|---|
| URL | `https://budget.gov.au/content/migration.htm` (primary) |
| Content type | HTML / PDF budget papers (migration program) |
| Cadence | Ad hoc (Budget annually; ministerial releases on policy change) |
| Tier | 5 (manual YAML seed — explicitly editorial) |
| Feeds | `policy_events` — event_date, visa_code (nullable), description |
| Status | **CONFIRMED** (200) |

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

Notes: Identical URL to source 2. `submitted_count` (EOIs lodged) may not be
published per-round on this page — verify whether it is derivable at all before
assuming it is; if absent, launch `submitted_count = NULL` rather than invent
it. The canonical doc's §7.3 open question #7 (multi-table `SourceSpec`) applies
here.

---

## 16. Application funnel — granted (Home Affairs annual report)

| Field | Value |
|---|---|
| URL | `https://www.homeaffairs.gov.au/reports-and-publications/reports/annual-reports` |
| Content type | HTML index linking to annual-report **PDFs** (aggregate visa grants) |
| Cadence | Annual |
| Tier | 5 (manual YAML seed — or launch `NULL` until a human confirms a real number) |
| Feeds | `application_funnel.granted_count` (second nullable provenance triple) |
| Status | **CONFIRMED** (200, index page) |

Notes: This is the annual-report *index* — the specific PDF and page containing
a pathway-level grant breakdown changes each year and must be located at
curation time. The canonical doc marks this the **weakest-sourced field**: if
no pathway-level breakdown is published, ship `NULL` rather than approximate.
`/reports-and-pubs/annual-reports` and the access-and-accountability path both
404 — the correct index is the URL above.

---

## GAPS — sources still missing a confirmed or sufficient URL

| # | Source | Gap | Recommendation |
|---|---|---|---|
| 5 | Points test criteria | URL is **confirmed live** but the points *table* is not in the static HTML — the page is a SharePoint SPA and the numeric points data appears JS-rendered. "Tier 2 deterministic HTML" may not hold. | Re-verify by inspecting the rendered DOM (Playwright or browser) before building the parser; if JS-rendered, either pin a Playwright fetch or fall back to tier 5 curation of `points_criteria_reference`. |
| 9 | MLTSSL/STSOL/ROL | `list_change_log` needs *change* events; legislation.gov.au serves versioned compilations, not a diff. The real HTML structure is unverified (§13 open question #1). | Inspect `F2019L00278/latest`'s DOM to confirm the schedule table is parseable; build a version-diff over successive instrument compilations (or curate the diff manually). |
| 10 | Skills priority list | JSA rating vocabulary unconfirmed; the page redirects to the rebranded "Occupation Shortage List". | Confirm `shortage_rating`/`future_demand_rating` vocabulary against the live page before finalising `skills_priority_ratings`. |
| 11/12 | **VIC** state nomination + occupation list | **PROPOSED only.** `liveinmelbourne.vic.gov.au` returns 403 (Cloudflare bot challenge) to both curl and headless browser from this environment. | Re-verify from a residential IP / human browser; add VIC's Cloudflare domain to any crawler allowlist, or curate VIC state data from a human-checked snapshot. Until then, VIC rows cannot carry a confirmed `source_url`. |
| 13 | Assessing bodies | **Source mismatch.** `mara.gov.au` registers *migration agents*, not *skills assessing authorities*. The MARA register URL is live but semantically wrong for `assessing_bodies`. | Point `assessing_bodies`/`occupation_assessing_bodies` provenance at **LIN 19/051 (F2019L00278)** — the instrument that actually specifies "Relevant Assessing Authorities" — plus each body's own site. Correct `docs/data-sources.md` accordingly. |
| 14 | Policy events | No single stable "events" URL exists; `budget.gov.au/content/migration.htm` is an annual index, ministerial releases are per-URL. | Treat as editorial (tier 5): curate per-event with a link to the specific press release / budget paper; the three index URLs (budget migration page, `treasury.gov.au`, `minister.homeaffairs.gov.au`) are the stable anchors. |
| 15 | Funnel submitted/invited | `submitted_count` may not be published per-round on the SkillSelect page. | Verify the round page's columns at build time; if EOI-lodgement counts aren't there, ship `submitted_count = NULL`. |
| 16 | Funnel granted | Only an index URL is confirmed; the specific annual-report PDF and the pathway-level grant table change each year. | Locate the current year's PDF at curation time; if no pathway breakdown is published, ship `granted_count = NULL` (canonical doc's explicit fallback). |

### Summary counts

- **CONFIRMED URLs:** 23 (all Home Affairs pages, legislation.gov.au instruments, JSA, budget/treasury/ministerial, MARA register, 4 of 5 states, annual-report index).
- **PROPOSED / unverifiable:** VIC (Cloudflare 403) — affects sources 11 and 12.
- **Correctness flags (URL live but source mismatched or insufficient):** 5 (JS-rendered table), 9 (diff not served), 13 (mara.gov.au is the wrong authority), 14/15/16 (no single stable URL — editorial or nullable).
