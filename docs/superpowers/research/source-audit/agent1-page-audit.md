# koshi — Agent 1 Page Audit (ground-truth reconnaissance)

**Purpose:** verify, by actually fetching and inspecting raw HTML/JSON, what each of
the 16 catalogued sources really serves — not what the catalog or a URL name implies.
**Date:** 2026-08-17
**Method:** `curl -sL` with a Chrome 124 desktop UA (`--` no special headers beyond
UA), sequential (one host at a time, politely spaced), raw HTML saved to a scratch
dir and inspected with `grep`/`python3` (no `bs4` available in this environment, so
table extraction was done with regex + manual verification of row/column content).
Where a page's real content was hidden behind JS or an escaped JSON blob, the
underlying static payload was located, decoded, and its *actual* HTML tables printed
and eyeballed — not inferred.

**Headline result:** `immi.homeaffairs.gov.au` (the domain behind sources 2, 3, 4, 5,
6, 7, 8, 16) is **not one consistent template**. It is a classic ASP.NET
WebForms/SharePoint-publishing site that renders each page through one of **at least
five different patterns**, and a generic "find `<table>`" scraper will find **zero**
`<table>` elements in the raw response on almost every one of these pages even when
the real content is, in fact, present server-side. This is the root cause of both
proven production failures (source 1 and source 2) and is likely to break any new
parser built on a "just find the table" assumption. The five patterns, all confirmed
live on real pages below:

1. **Hidden "content sections" JSON** — `<input type="hidden" id="ctl00_PlaceHolderMain_PageSchemaHiddenField_Input" value="{&quot;content&quot;:[{&quot;text&quot;:...,&quot;block&quot;:&quot;<table>...&quot;}]}" />`. HTML-entity-unescape the `value`, `json.loads()` it, iterate `content[]`, each item's `block` is a real, fully-formed HTML fragment (with real `<table>` tags) keyed by a human section heading. **Confirmed on sources 2, 3, 5 (points-table page only), 7 (character), 16.**
2. **Hidden "visa details" JSON (Angular)** — same hidden input, different schema (`applicant.eligibility.criteria[]`, `subClass`, etc.), rendered client-side by `<ha-visa-details-root>` or `<ha-streams-root>`. Text content is present in the JSON but there is **no numeric table** — only prose. **Confirmed on source 5 (points-tested page) and all 6 pages of source 6.**
3. **Plain classic SharePoint `RichHtmlField` div** — content sits directly, unescaped, in `<div class="ms-rtestate-field">…real HTML…</div>`. No JSON, no JS needed at all. **Confirmed on source 4 (fees index page) and source 7 (english-language page).**
4. **Angular widget backed by a directly-callable internal REST API** — an empty custom element (`<ha-table-search>`) plus an inline `<script>` that declares `endpointUrl`/`endpointParm`. Calling that endpoint directly with `curl -X POST` returns clean JSON with the *entire* dataset, no scraping needed at all. **Confirmed and exploited for source 4 (`current-visa-pricing`) and source 8.**
5. **Form-builder JSON schema** — `{"components":[{"html": "..."}], "display":..., "page":...}`. **Confirmed on source 7 (health).**

Similarly, `jobsandskills.gov.au` (sources 1, 10) is Drupal, and its "table" pages are
either Drupal-Views card/search listings (source 1: zero `<table>` tags at all,
paginated via `?page=N`) or a jQuery-DataTables shell (`<table id="splTable"></table>`,
empty) whose real data is a directly downloadable JSON file referenced in the page's
own `drupalSettings` blob (source 10).

---

## 1. ANZSCO occupations

**URL:** `https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco`
**HTTP status:** 200, no redirect.
**Page type:** Static server-rendered HTML — but a **Drupal Views card/search
listing**, not a table. `grep -c '<table'` on the raw response = **0**.
**What's actually on the page:** a paginated grid of occupation "cards". Verified
markup:
```html
<div class="container view-of-cards view view-occupation-index view-id-occupation_index view-display-id-block_occupations" id="block-views-block-occupation-index-block-occupations">
  <div class="view-header"><div class="resultsCount">Showing 1 - 12 of 1236 results</div></div>
  <div class="view-content row">
    <div class="rowc"><a href="/data/occupation-and-industry-profiles/occupations-anzsco/422111-aboriginal-and-torres-strait-islander-education-workers">
      <div class="card_inner">
        <div class="card_anzsco">ANZSCO 422111</div>
        <h4 class="card_title">Aboriginal and Torres Strait Islander Education Workers</h4>
        <div class="card_stats">
          <div class="stats employment"><div class="stat_title">Employed</div><div class="stat_value stat_percent">2,200</div></div>
          <div class="stats weeklyEarnings"><div class="stat_title">Median weekly earnings</div><div class="stat_value stat_currency">N/A</div></div>
        </div>
      </div></a></div>
    ...
```
Fields per card: ANZSCO code (mix of 4-digit unit-group codes like `2211` and
6-digit occupation codes like `422111` — both appear in the same result set),
occupation title, "Employed" count, "Median weekly earnings". Each card links to a
per-occupation detail sub-page (not fetched).
**Retrieval method:** `div#block-views-block-occupation-index-block-occupations div.rowc` per card; `div.card_anzsco`, `h4.card_title`, `div.stat_value.stat_percent`, `div.stat_value.stat_currency` for fields. Pagination is a plain `?page=0..102` query-string GET (confirmed via `href="?page=1"` … `href="?page=102"` pager links) — **no JS required to page through it**, but it does require 103 sequential fetches. **There is no `<table>` anywhere on this page and no `id="occupation-list"` anywhere in the raw HTML** — confirms exactly why the existing parser (`pipeline.py:36`, expects `id="occupation-list"` table) is broken.
**Volume:** **1,236 results**, 12 per page, 103 pages.
**Cadence signal:** no per-page "last updated" field found. However, a **sitewide alert banner** on the page reads: *"ANZSCO has been superseded and is no longer updated. Replacement OSCA content is now available and will expand as new data is released."* with a link to `/data/occupation-and-industry-profiles/occupations-osca`.
**Notes/caveats — important:**
- **ANZSCO is being retired by JSA itself.** I fetched `https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-osca` as a sanity check: 200, same card-list template, **1,577 results**, coded under a new `OSCA` code scheme (e.g. `OSCA 432931`) instead of ANZSCO codes. This is a genuine, dated policy fact from the live site, not a guess — koshi should decide now whether `occupations` should anchor on ANZSCO (frozen, will visibly rot) or start tracking OSCA (the string "OSCA Code A to Z" also already appears as a sort option on the *ANZSCO* listing page itself, meaning JSA is cross-referencing the two schemes today).
- The result set mixes 4-digit and 6-digit codes in the same listing — a naive "occupation code" column needs to handle both widths.
- "Median weekly earnings" was `N/A` for the sampled card — expect nulls in this field regularly.

---

## 2. EOI invitation rounds (SkillSelect)

**URL:** `https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds`
**HTTP status:** 200, no redirect.
**Page type:** ASP.NET WebForms / classic SharePoint publishing page
(`Sys.WebForms.PageRequestManager`, `_spPageContextInfo` both present in source).
Raw DOM has **zero `<table>` tags**. The real content is server-rendered but shipped
as **HTML-entity-encoded JSON inside a hidden `<input>`'s `value` attribute**:
```html
<input type="hidden" name="ctl00$PlaceHolderMain$PageSchemaHiddenField$Input"
  id="ctl00_PlaceHolderMain_PageSchemaHiddenField_Input"
  value="{&quot;content&quot;:[{&quot;text&quot;:&quot;Overview&quot;,&quot;block&quot;:&quot;<p>...&quot;}, ...]}" />
```
Decoding recipe (verified working): `html.unescape(attr_value)` → `json.loads(...)` →
`data["content"]` is a list of `{"text": <section heading>, "block": <real HTML
string, already table-and-all>}`. Five sections found: **Overview, Occupation
ceilings, Invitation process, Current round, State and Territory nominations.**
**What's actually on the page (inside "Current round" and "State and Territory
nominations" blocks, decoded and printed in full):**
- Table A — *"Invitations issued on 4 June 2026"*: columns **Visa subclass | Total
  EOIs Invited | Tie break date – month and year**. 1 data row in the round checked
  (Skilled Independent 189 | 10,000 | 24/04/2026).
- Table B — *"Invitations issued by occupation and minimum score invited"*: columns
  **Occupation | minimum score**. **140 data rows** (Actuary/90, Agricultural
  Consultant/80, Architect/85, Barrister/80, Carpenter/65, … verified full list
  present).
- Table C — *"Total invitations issued during 2025-26 program year"*: matrix,
  columns **Visa subclass | Jul…Jun** (12 month columns). 2 rows: 189 and 491
  (Family Sponsored), monthly invite counts (e.g. 189: 0,6887,0,0,10000,0,0,0,0,0,0,10000).
- Table D — *"2025-26 program year"* (under "State and Territory nominations"):
  columns **Visa subclass | ACT | NSW | NT | Qld | SA | Tas | Vic | WA**. 2 rows: 190
  and 491 (State/Territory Nominated), with real per-state nomination counts (e.g.
  190: 800/2100/850/1850/1350/1200/2700/2000).
**Retrieval method:** extract-and-decode the hidden-input JSON as above, then run a
normal HTML table parser (BeautifulSoup/lxml) over each `block` string. **Not** a
DOM/CSS-selector problem on the fetched page — it's a decode-then-parse problem.
**Volume:** ~140 occupation-threshold rows per round + a handful of summary/state
rows.
**Cadence:** `<span id="pageModified" class="hide">4/08/2026 17:03</span>` — a real,
present, static last-updated timestamp, hidden via CSS but not via markup.
**Notes/caveats:**
- Confirms the production failure directly: the existing parser expects
  `id="round-results"`, which **does not exist anywhere in the raw HTML**, escaped
  or not.
- I searched the fully-decoded page JSON for `submitted`, `lodged`, `EOIs on hand`,
  `EOIs in the system`, `pool` — **zero matches**. `submitted_count` genuinely is
  not published on this page; per the canonical doc's own fallback, it should ship
  `NULL`, not be guessed at.
- "Occupation ceilings" is a *prose* section here (limits explanation), not a
  ceiling number table — do not confuse it with source 3's ceiling table.

---

## 3. Occupation ceilings / migration program planning levels

**URL:** `https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels`
**HTTP status:** 200, no redirect.
**Page type:** Same ASP.NET/SharePoint hidden-field JSON pattern as source 2.
Sections: **"Permanent Migration Program planning levels", "Skilled Migration
Program", "Australian Family Program", "Net overseas migration – relationship with
the Permanent Program."**
**What's actually on the page:** the *first* section contains one real table with a
full 3-year planning-level comparison, columns **Visa Category | 2024–25 Planning
level | 2025–26 Planning level | 2026–27 Planning level**, broken out by:
Commonwealth Program (Skilled Independent, Talent and Innovation), Employer Program
(Employer-Sponsored), State and Territory Program (Regional, State/Territory
Nominated), Total Skilled Migration Program; then Australian Family Program
(Partner, Child, Parent, Other Family, subtotal), Special Eligibility, Total
Permanent Program. Verified real numbers, e.g. Skilled Independent: 16,900 /
16,900 / 21,090; Total Permanent Program: 185,000 / 185,000 / 185,000.
**Retrieval method:** same hidden-field decode as source 2, then parse the single
table in the first section.
**Volume:** ~15 program-line rows × 3 year columns.
**Cadence:** `pageModified` = **12/08/2026 5:28 PM**.
**Notes/caveats — CORRECTS THE CATALOG:** the catalog states *"the actual numbers
live in linked PDFs that change URL each release... curate from the page + its
latest PDF rather than scraping"* and marks this source Tier 5. **This is wrong.**
I searched the entire raw HTML for `href="..."pdf"` — **zero PDF links anywhere on
this page.** The numeric planning-level table is fully present, static, and
deterministically extractable via the same hidden-field technique as source 2/5/16.
This source should be reclassified **Tier 2**, not Tier 5/manual — a real, concrete
build-plan-changing finding.

---

## 4. Visa fees

**Catalog URL:** `https://immi.homeaffairs.gov.au/visas/getting-a-visa/fees-and-charges`
**HTTP status:** 200, no redirect. **But this is a landing/index page, not a fee
table.** Its `PageSchemaHiddenField_Input` is present but **empty** (different,
simpler template: content sits in a plain `<div class="ms-rtestate-field">`
RichHtmlField). Verified content: three tiles — "Visa pricing estimator" (interactive
tool, `/visas/visa-pricing-estimator`), "Surcharges" (prose link), and **"Current
visa pricing table"** (`/visas/getting-a-visa/fees-and-charges/current-visa-pricing`
— this is the real target, and the catalog does not name it).
**Real fee-table page:** `https://immi.homeaffairs.gov.au/visas/getting-a-visa/fees-and-charges/current-visa-pricing` — 200. Also **zero static `<table>` tags**. Instead there is an empty custom Angular element `<ha-table-search id="ha-visaprices-tseacrh" configJson="">` populated at runtime by `/AssetLibrary/dist/angular/table-search.js`, configured via an inline `<script>`:
```js
var configJson = { "title": "Visa Prices", "columns": [
  {"name":"visaSubclassText","heading":"Visa subclass"},
  {"name":"basePrice","heading":"Base application charge"},
  {"name":"over18Price","heading":"Additional applicant charge 18 and over"},
  {"name":"under18Price","heading":"Additional applicant charge under 18"},
  {"name":"nonInternetPrice","heading":"Non-internet application charge"},
  {"name":"subsequentPrice","heading":"Subsequent temporary application charge"},
  {"name":"note", "display": false}
], "endpointUrl": "/_layouts/15/api/data.aspx/GetPriceList",
   "endpointParm": "{\"onshore\": \"All\",\"category\": \"Visa\"}", "pageSize": 50};
```
**This endpoint is directly callable and I confirmed it live:**
```
curl -X POST -H "Content-Type: application/json" \
  -d '{"onshore":"All","category":"Visa"}' \
  https://immi.homeaffairs.gov.au/_layouts/15/api/data.aspx/GetPriceList
```
returns real JSON: `{"d":{"__type":"Internet.Domain.JsonResponse","success":true,"data":[{"visaSubclassCode":"100","visaSubclassText":"Partner (Provisional and Migrant) visa (subclass 309/100)","streamCode":"","streamText":"","onShore":"No","basePrice":"AUD11,710.00","over18Price":"AUD5,860.00","under18Price":"AUD2,935.00","nonInternetPrice":"N/A","subsequentPrice":"N/A","note":"<html note with a link to the visa page>"}, ...]}}`
Verified all target subclasses present with per-stream breakdown, e.g.:
`189-63 Points tested stream = AUD6,135.00`, `190 = AUD6,140.00`, `491 =
AUD6,140.00`, `482 Core Skills/Specialist Skills/Labour agreement streams =
AUD4,015.00` each, `485 (3 sub-streams) = AUD5,750/5,750/2,265`, `500 (6
categories) = AUD2,500/2,500/0/0/2,050/2,050`.
**Retrieval method:** direct JSON API call (POST, no auth, no cookies needed) —
**no HTML parsing at all required.** This is better than "Tier 2 deterministic
HTML"; it's closer to Tier 1.
**Volume:** **150 fee records** (all AU visa subclasses × streams, not just the 6
skilled ones).
**Cadence:** `current-visa-pricing` pageModified = **1/07/2026 12:27 AM** (matches
catalog's claimed 1 July annual indexation cadence). `fees-and-charges` index page
pageModified = **4/05/2026 2:59 PM**.
**Notes/caveats:**
- Catalog's characterization ("HTML fee tables / fee-calculator surface... may be
  JS-augmented, confirm at build time") **undersells this** — the real situation is
  better: a stable, versioned, directly-callable internal JSON API exists. Point
  `SourceSpec.url` (or a dedicated fetch step) at the `GetPriceList` endpoint, not
  at HTML.
- The catalog's named URL is only the index; the real page (`current-visa-pricing`)
  isn't named in the catalog at all.

---

## 5. Points test criteria

**Catalog URL:** `https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-independent-189/points-tested`
**HTTP status:** 200, no redirect.
**Page type at this exact URL:** JS-rendered Angular app. `<ha-visa-details-root></ha-visa-details-root>` is a genuinely **empty** custom element, populated client-side by `/AssetLibrary/dist/angular/visa-details.js`. `PageSchemaHiddenField_Input` *does* have a value here, but its schema is the "visa details" shape (`recommended`, `visaSubclassHeading`, `applicant.tabs/overview/eligibility/stepGuide`, etc.) — I decoded it fully and searched for numeric points content: the eligibility criterion text says only *"Be able to score 65 points or more... To calculate how many points you may score use the points calculator... Use the points table to check the documents you need"* with a link to a **different page**: `/visas/getting-a-visa/visa-listing/skilled-independent-189/points-table`.
**CATALOG'S FLAG IS CONFIRMED TRUE for this exact URL: there is no numeric points table anywhere in the static HTML or the hidden JSON — only prose referencing the concept and linking elsewhere.** Zero `<table>` tags (direct or escaped) anywhere on the page.
**But the real table exists at a different, correct URL, which I found and verified:**
`https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-independent-189/points-table` — **200**. This page uses the *same* "content sections" hidden-field JSON pattern as source 2/3 (i.e. it is fully static/Tier-2, not JS-rendered). Sections found: **Overview, Age, English language skills, Skilled employment experience, Educational qualifications, Specialist education qualification, Australian study requirement, Professional Year in Australia, Credentialled community language, Study in regional Australia, Partner skills** — 11 sections, 11 real `<table>` elements. Verified two in full:
```html
<table summary="The table shows the points you can claim based on your age">
<thead><tr><th>Age</th><th>Points</th></tr></thead>
<tbody>
<tr><td>at least 18 but less than 25 years</td><td>25</td></tr>
<tr><td>at least 25 but less than 33 years</td><td>30</td></tr>
<tr><td>at least 33 but less than 40 years</td><td>25</td></tr>
<tr><td>at least 40 but less than 45 years</td><td>15</td></tr>
</tbody></table>
```
```html
<table summary="The points you can claim based on your English language skills">
<thead><tr><th>English</th><th>Points</th></tr></thead>
<tbody>
<tr><td>Competent English</td><td>0</td></tr>
<tr><td>Proficient English</td><td>10</td></tr>
<tr><td>Superior English</td><td>20</td></tr>
</tbody></table>
```
**Retrieval method:** hidden-field decode (as source 2) on the **`/points-table`**
URL, not `/points-tested`.
**Volume:** 11 small tables, roughly 30–50 criterion rows total across all bands
(age: 4 rows; English: 3 rows; others not individually counted but similarly small).
**Cadence:** `/points-table` pageModified = **11/06/2026 13:38**. `/points-tested`
pageModified = **1/07/2026 12:35 AM**.
**Notes/caveats — the single highest-value correction in this audit:** the catalog
points `SourceSpec.url` at `/points-tested`, which genuinely has no numeric table
(confirming the JS-SPA flag) — but the fix is not "switch to Playwright", it's
**"point the URL at `/points-table` instead"**, which is plain static HTML requiring
no browser automation at all.

---

## 6. Visa subclass static facts (189 / 190 / 491 / 485 / 500 / 482)

All six URLs: **200**. Legacy 482 URL
(`/visa-listing/temporary-skill-shortage-482`) does redirect — verified via
`curl -w %{url_effective}` — final URL is
`skills-in-demand-visa-subclass-482`, confirming the catalog.

| Visa | `ha-` root element | Hidden-field schema | Eligibility content present in JSON? | `pageModified` |
|---|---|---|---|---|
| 189 | `ha-streams-root` | `subClass/eligibility/description` | No — `eligibility` = literal stub `"See the relevant stream"` | 1/07/2026 11:58 AM |
| 190 | `ha-visa-details-root` | `applicant.eligibility.criteria[]` | **Yes** — real prose per criterion (verified) | 17/08/2026 10:42 AM |
| 491 | `ha-streams-root` | same stub pattern as 189 | No — stub | 17/08/2026 10:42 AM |
| 485 | `ha-streams-root` | same stub pattern as 189 | No — stub | **14/12/2024 12:00 AM** (stale, ~20 months) |
| 500 | `ha-visa-details-root` | `applicant.eligibility.criteria[]` | **Yes** — real prose per criterion (verified) | 1/07/2026 10:00 AM |
| 482 | `ha-streams-root` | same stub pattern as 189 | No — stub | 9/05/2025 1:05 PM |

**Page type:** all six are Angular-driven (`ha-streams-root` = a stream-router page
for multi-stream visas; `ha-visa-details-root` = same component family as source 5).
**Zero `<table>` tags on any of the six pages.**
**What's actually usable:** for 189/491/485/482 (the "streams" template), the
top-level page's own eligibility content is a placeholder — real eligibility detail
lives on a per-stream sub-page (e.g. `/189/points-tested`, itself thin, see source
5). For 190/500 (the "details" template), real, rich eligibility criteria prose
**is** present in the hidden-field JSON — e.g. 190's "Have this visa" criterion
includes full text about acceptable bridging-visa holder scenarios.
**Retrieval method:** hidden-field decode as source 2/3/5, same technique — but be
aware which of the two schema shapes a given page uses, and that the "streams" shape
requires an extra hop to the real sub-page for real content.
**Volume:** low (these are single-record "facts" pages per visa, tier-5-appropriate
as the catalog already assumes) — no correction to tier needed.
**Notes/caveats:** the 485 page not being touched since Dec 2024 is worth flagging
if 485 rules have changed since (I did not independently verify against current
Temporary Graduate rules — flagging only the staleness signal, not asserting an
error).

---

## 7. Health / character / English requirements

All three URLs: **200**, resolve exactly as the catalog's template predicts.
**Three different page templates on three adjacent URLs** (all static/extractable,
none requires JS execution, but a generic scraper needs to detect the difference):

- **Health** (`/health`): hidden field present, but with a **fourth, distinct
  schema** — `{"components":[{"type":"contentLink"|..., "html": "<real HTML>"}],
  "display":..., "page":...}`. Verified real content in `components[1].html`:
  `<h2>Why we have a health requirement</h2><p>Making sure visa applicants meet the
  health requirement:</p><ul>...</ul>`. `pageModified` = **16/10/2024 9:59** (stale,
  ~22 months).
- **Character** (`/character`): the familiar "content sections" pattern (source
  2/3/5/16 shape). 8 sections: Character considerations, When you apply, Other
  considerations, Mandatory cancellation, Other supporting documents, Requirements
  for ship workers, Consequences of visa refusal or cancellation, Character caseload
  prioritisation and processing times. `pageModified` = **19/02/2026 3:55 PM**.
- **English language** (`/english-language`): hidden field is **empty** — content
  lives directly, unescaped, in a plain `<div id="ctl00_PlaceHolderMain_ctl03__ControlWrapper_RichHtmlField">`. No JSON decode step needed at all — just read the div. Verified real content: prose about the 7 August 2025 English-test-provider change. `pageModified` = **2/02/2026 12:00**.
**Page type:** all three: static HTML prose (as catalog says), **zero `<table>`
elements** on any of the three.
**Retrieval method:** three different extraction recipes needed for what the
catalog treats as one uniform "HTML prose, Tier 5" bucket — health needs the
`components[].html` schema, character needs the `content[].block` schema, english
needs a plain div read. All are static and JS-free once you know which recipe
applies.
**Notes/caveats:** none of the "3 different templates on 3 sibling URLs" behavior
is mentioned or anticipated by the catalog — worth flagging generally for whoever
writes a generic immi.homeaffairs.gov.au fetcher.

---

## 8. Global visa processing times

**URL:** `https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-processing-times/global-visa-processing-times` — **200**, no redirect observed on the way in. I separately checked the older path the catalog implies redirects here — `https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-processing-times` — and it returns its **own 200 page**, not a redirect to `global-visa-processing-times`. **Minor correction:** the catalog's "redirects from the older path" note appears inaccurate — both paths are live, independent pages.
**Page type:** plain RichHtmlField intro prose ("Visa processing times guide...")
**plus a JS-driven single-visa lookup tool**, not a bulk table. Zero `<table>`
tags, zero `ha-` custom elements; instead a `<select>` dropdown
("Please select a visa type") inside a `div.gpt-visualtracker-search` block, backed
by `/AssetLibrary/dist/js/app.gpt-visualtracker.js`.
**CORRECTS THE CATALOG:** catalog describes this as *"HTML table (visa × median
processing days, updated monthly)"* — **wrong shape.** It is a per-visa **search
tool**, not a browsable table.
**Underlying API (found in the JS bundle, confirmed live):**
- `POST /_layouts/15/api/GPT.aspx/GetProcessGuideVisas` with body `{}` → returns the
  full dropdown list as JSON: **76 rows**, each `{VisaSubclassText,
  VisaSubclassCode, StreamCode, StreamText}` (subclass × stream combinations, e.g.
  186 has separate rows for "Direct Entry Pathway" and "Agreement Pathway").
- `POST /_layouts/15/api/GPT.aspx/GetProcessGuideInfo` with body
  `{"gptRequest":{"VisaSubclassCode":"189","StreamCode":"63"}}` → returns one
  record. **Verified live for 189/Points-Tested:**
  `{"VisaSubclassText":"Skilled - Independent visa (subclass 189)","StreamText":"Points-Tested","VisaUrl":"/visas/getting-a-visa/visa-listing/skilled-independent-189/points-tested","Percent25":"191","Percent50":"202","Percent75":"245","Percent90":"271","Percent25Text":"6 Months","Percent50Text":"7 Months","Percent75Text":"8 Months","Percent90Text":"9 Months","ProcessGuideMaxDays":"282","ProcessGuideInfo":"<p></p>"}`
**Retrieval method:** call `GetProcessGuideVisas` once to enumerate the 76
subclass/stream combinations, then call `GetProcessGuideInfo` once per combination
(76 calls) — same internal REST convention as source 4
(`/_layouts/15/api/{Controller}.aspx/{Method}`, POST + JSON body). No HTML parsing
needed anywhere in this flow.
**Volume:** **76 subclass × stream combinations.**
**Cadence:** intro-page `pageModified` = **4/08/2026 8:32 AM**. Data-refresh cadence
for the API itself not independently confirmed (plausible monthly per catalog, not
verified).
**Notes/caveats:** there is **no single "median_days"** field — the API returns a
**4-point percentile distribution** (25th/50th/75th/90th, in both raw days and
human text like "7 Months") plus a `ProcessGuideMaxDays`. `processing_times` schema
should probably capture the distribution, not one median number, or explicitly pick
`Percent50` and document the choice.

---

## 9. MLTSSL / STSOL / ROL — legislation.gov.au

**LIN 19/051** (`https://www.legislation.gov.au/F2019L00278/latest`) — **200**. The
`/latest` landing page is an **Angular app** (`ng-app`) showing register metadata
only — **zero `<table>` tags**. The real instrument text is loaded via an
`<iframe id="epubFrame">` pointing to a **separate, genuinely static** document URL:
```
https://www.legislation.gov.au/F2019L00278/2026-03-28/2026-03-28/text/original/epub/OEBPS/document_1/document_1.html
```
I fetched that URL directly — **200**, 834 KB, plain static HTML (no JS framework
markers), and it contains **12 `<table>` elements**, none with an `id` or `class`
attribute distinguishing content (only inline CSS) — selection must be by preceding
heading text, not by selector. Verified table-by-table (heading text immediately
preceding each, and row/column content):

| # | Rows | Preceding section heading | Columns | What it is |
|---|---|---|---|---|
| 0 | 6 | "8 Specification of occupations — Application" | n/a | defines which visa classes the lists apply to — not occupation data |
| 1 | 213 (212 occ.) | "Medium and Long-term Strategic Skills List" | Item \| Occupation \| ANZSCO code | **MLTSSL** |
| 2 | 216 (215 occ.) | "Short-term Skilled Occupation List" | Item \| Occupation \| ANZSCO code | **STSOL** |
| 3 | 78 (77 occ.) | "Regional Occupation List" | Item \| Occupation \| ANZSCO code | **ROL** |
| 4 | 4 | transitional note re: retail buyer | — | pre-16 Nov 2019 transitional provision |
| 5 | 505 (504 occ.) | "...is specified as the relevant assessing authority for: (a) the occupation..." | **Item \| Occupation \| ANZSCO code \| Relevant assessing authority** | full occupation→authority join |
| 6 | 39 (38 bodies) | "11 Relevant assessing authorities" | Item \| Abbreviation \| Full authority name | **assessing-body abbreviation key** |
| 7–11 | 13/24/7/22 + amendment history | transitional provisions / endnotes | — | not occupation data |

Verified sample rows (table 5): `1 | construction project manager | 133111 |
VETASSESS`; `2 | engineering manager | 133211 | (a) Engineers Australia; or (b)
IML` (note: some occupations map to **multiple alternative bodies**, not a single
FK). Verified sample rows (table 6): `1 | AACA | Architects Accreditation Council
of Australia`.
**Retrieval method:** **two-hop.** (1) resolve the real epub document URL — the
path pattern is `/{register-id}/{compilation-date}/{compilation-date}/text/original/epub/OEBPS/document_1/document_1.html` (the compilation date is visible in the iframe `src` on the `/latest` page, so this is a deterministic, not guessed, resolution step); (2) parse the resulting static HTML's 12 tables positionally, anchored on the preceding heading text.
**Volume:** MLTSSL 212 + STSOL 215 + ROL 77 occupations (lists likely overlap);
**504 occupations** in the assessing-authority join table; **38 distinct assessing
bodies**.
**Cadence:** compiled version dated **2026-03-28** in the URL (matches the
catalog's claimed effective date). A separate embedded metadata blob on the
`/latest` landing page (also JSON, Angular app state) shows
`"asMadeRegisteredAt":"2019-03-10T09:25:22.723"`, `"status":"InForce"`.
**Companion instruments** (`F2024L01618` subclass-186, `F2024L01616` ANZSCO
Definition): both **confirmed 200**, both confirmed to expose the **same
iframe→epub pattern** (epub URLs resolved: `.../F2024L01618/2026-03-28/2026-03-28/text/original/epub/OEBPS/document_1/document_1.html` and `.../F2024L01616/asmade/2024-12-06/text/original/epub/OEBPS/document_1/document_1.html`). **I did not fetch and fully parse their table contents** (time-boxed) — pattern is confirmed, row/column content of these two companion instruments is **UNVERIFIED**.
**Notes/caveats — resolves the catalog's open question #1 directly:** the real HTML
structure requires resolving the iframe target first; a scraper that just fetches
`/latest` and looks for tables will find none. **Also directly and concretely
confirms source 13's proposed fix** (see below) — this document already contains
both the assessing-body key and the occupation→body join.

---

## 10. Jobs & Skills Australia — skills priority / occupation shortage list

**URL:** `https://www.jobsandskills.gov.au/skills-priority-list` → redirects (200)
to `https://www.jobsandskills.gov.au/data/occupation-shortage/occupation-shortage-list` — confirmed, matches catalog.
**Page type:** Drupal + jQuery DataTables. Raw HTML has exactly **one** table:
`<table id="splTable"></table>` — a genuinely **empty shell**, populated at runtime.
**Real data source found (not guessed — traced through the page's own Drupal JS
bundles):** the page's `drupalSettings` JSON (embedded in the page itself) contains:
```json
"applets":{"applet_data":{
  "spl_search":["spl_search","json","/system/files/applet_data/splSearch (2).json",316671,0],
  "spl_data":["spl_data","json","/system/files/applet_data/25-10-10 - splData (1).json",1466812,0]
}}
```
I fetched `spl_data`'s URL directly — **200**, valid JSON, 1.47 MB. Structure
(verified by walking the JSON):
```
{ "4": {"2022": {code: {c, t, l, v: {year: {rnat, rnsw, rvic, rqld, rsa, rwa, rtas, rnt, ract, d}}}}, "2024": {...}},
  "6": {"2022": {...}, "2024": {...}} }
```
The `"4"`/`"6"` top level = ANZSCO digit-level (unit group vs occupation); the
`"2022"`/`"2024"` second level = **classification edition** — confirmed against the
page's own UI toggle text ("ANZSCO 2022" / "OSCA 2024") — i.e. **JSA already
dual-publishes this dataset under both ANZSCO 2022 and OSCA 2024 codes**, echoing
the ANZSCO→OSCA transition found on source 1. Per record: `c`=code, `t`=title,
`l`=level, `v`=a per-year (2021–2025) object of per-jurisdiction ratings.
**Rating vocabulary — partially confirmed:** distinct values found across
`rnat`/`rnsw`/.../`ract` fields: **`{NS, S, R, M, Ns}`**. `NS` = Not in Shortage and
`S` = Shortage are self-evident from context; **`R`, `M`, and the separate lowercase
`Ns` value are UNVERIFIED** — the page has a "What do the ratings mean" glossary
link/modal, but its content is populated by JS and was not present in the static
HTML I fetched (could not decode it). The coexistence of `NS` and `Ns` as distinct
values looks like a data-entry/casing inconsistency worth flagging to whoever
designs the enum, not treating as two intentionally distinct codes without
confirming with JSA.
**The `d` field** (plausibly "future demand," matching the catalog's
`future_demand_rating` schema column) was **`null` for every record checked** — this
dimension does not appear to be currently populated in the dataset.
**Retrieval method:** direct JSON file download, no HTML parsing, no JS execution.
Better than the catalog's speculative "BS4/lxml, or pandas/openpyxl if offered" —
it's a plain JSON GET.
**Volume:** **916 six-digit occupations, 311 four-digit unit groups** (per
classification edition; ×2 editions ×2 possible "4"/"6" digit levels).
**Cadence:** filename encodes `25-10-10` (plausibly 10 Oct 2025, format unconfirmed)
— a real, if informally expressed, snapshot date.
**Notes/caveats:** confirms catalog's flagged open question #2 partially (shortage
vocabulary has 2 clear values + 3 unclear ones) and reveals the `future_demand`
dimension is not currently populated at all — `skills_priority_ratings.future_demand_rating` should probably launch `NULL` rather than be built against, until JSA actually populates `d`.

---

## 11. State nomination status (NSW / VIC / QLD / WA / SA)

| State | URL | Status | Page type / real finding |
|---|---|---|---|
| NSW | `nsw.gov.au/visas-and-migration/skilled-visas` | **200** | Static prose landing page, 0 tables. |
| VIC | `liveinmelbourne.vic.gov.au/migrate` | **403** | Re-verified: **still Cloudflare-blocked.** Response body is literally the Cloudflare "Just a moment..." interstitial (`<title>Just a moment...</title>`, CSP referencing `challenges.cloudflare.com`). No change from the catalog's prior finding. |
| QLD | `migration.qld.gov.au/visa-options/skilled-visas` | **200** | Small (36 KB) static prose landing page, 0 tables, title "MQ - Skilled visas". |
| WA | `migration.wa.gov.au/.../state-nominated-migration-program` | **200** | Large (320 KB) page with **22 real `<table>` elements** — but the largest one (72 rows) is a list of **accredited educational institutions (CRICOS numbers)**, not occupations. The page also embeds a **Drupal Views exposed search form** for eligible occupations (`id="views-exposed-form-v2-occupation-search-v2-occupations-search"`) that shows **"Displaying 0 occupation(s)"** by default — the real occupation list is gated behind a search/filter submission, not directly browsable. The catalog's `#2025-26-eligible-occupations` anchor does not correspond to any actual element `id` on the page (dead fragment; page still loads). |
| SA | `migration.sa.gov.au/before-applying/work-in-sa/occupation-lists` | **200** | Static prose landing page, 0 tables, title "Occupation Lists \| Move to South Australia". |

**Notes/caveats:** none of NSW/QLD/WA/SA expose a page-level "last updated" date in
static HTML (checked, not found on any of the four). No genuine tier/URL corrections
here beyond WA's search-gating and dead anchor — see source 12 for the concrete
occupation-list URLs and their real table content.

---

## 12. State occupation list changes

| Source page | URL | Status | Real finding |
|---|---|---|---|
| NSW skills lists | `nsw.gov.au/.../nsw-skills-lists` | **200** | **2 real static `<table>` elements, no id/class.** Table 0 (79 data rows) = NSW Skilled Nominated (190) occupation list, columns **ANZSCO Code \| Unit Group Name** (4-digit unit-group codes, e.g. `1325 Research and Development Managers`). Table 1 (78 data rows) = NSW Skilled Work Regional (491) occupation list, same 2-column shape. |
| QLD offshore QSOL | `migration.qld.gov.au/occupation-lists/offshore-queensland-skilled-occupation-lists-(qsol)` | **200** | **1 table, 120 data rows**, columns **ANZSCO Code \| Occupation \| Skilled Work Regional visa (491) [Yes/blank] \| Skilled Nominated visa (190) [Yes/blank] \| Additional information**. 6-digit occupation-level codes (not unit groups). **Caveat:** the table carries `id="isPasted"` and Microsoft-Word-paste CSS classes (`Table Ltr TableWordWrap SCXW33046690 BCX8`) — a clear sign this table is manually pasted from a Word doc into the CMS on each update, meaning its exact markup (row/cell structure, whitespace, `&nbsp;` padding cells) is fragile and can shift unpredictably between refreshes. |
| WA eligible occupations | (see source 11) | 200 (page), but **0 occupations shown by default** | Search-form-gated; I did not reverse-engineer the Views AJAX/query-string parameters needed to retrieve the full list — **UNVERIFIED how to bulk-extract WA's occupation list** without either a keyword or filter submission per request. |
| SA occupations-list | `migration.sa.gov.au/.../occupation-lists/occupations-list` | **200** | **0 tables, 0 ANZSCO code mentions anywhere.** The page currently reads: *"Skilled ROI and GSM applications are currently unavailable. Skilled and Business Migration (SBM) will resume accepting ROIs from all eligible candidates when the 2026-27 program commences."* — **SA's skilled program is presently closed/paused**; there is no occupation list to scrape right now, not because of a parser bug but because the state genuinely isn't publishing one between intake rounds. |
| VIC | — | **403** | Same Cloudflare block as source 11; occupation list unreachable. |

**Volume:** NSW 157 total occupation-code rows across its 2 visa-specific lists;
QLD 120 occupations; WA unknown (gated); SA 0 (program closed); VIC unknown
(blocked).
**Notes/caveats:** SA's "0 tables" finding is time-sensitive and state-driven, not a
scraper bug — a quality-policy design should distinguish "source temporarily has no
data because the program is closed" from "parser broke."

---

## 13. Assessing bodies (skills assessing authorities)

**URL:** `https://portal.mara.gov.au/search-the-register-of-migration-agents/` —
**200**. `<title>Search for registered migration agents · OMARA Self-Service
Portal</title>`. **Zero `<table>` elements** — it is a search-only interface
requiring user input, no bulk listing. Text-mined the whole page: **"migration
agent(s)" appears 12 times; "assessing authority" and "skills assessment" appear
zero times.**
**Confirms the catalog's flagged semantic mismatch conclusively:** this page has no
relationship whatsoever to skills assessing bodies (Engineers Australia, VETASSESS,
ACS, etc.) — it is purely a migration-agent registration search tool.
**Confirms the catalog's proposed fix, with concrete verified detail (see source
9):** LIN 19/051's epub document already contains everything needed —
- **Table 6** (38 data rows): the assessing-body master list — `Item | Abbreviation
  | Full authority name` (e.g. `VETASSESS`, `AACA → Architects Accreditation
  Council of Australia`).
- **Table 5** (504 data rows): the occupation→assessing-authority join — `Item |
  Occupation | ANZSCO code | Relevant assessing authority` — noting some occupations
  map to **multiple alternative bodies** (e.g. "(a) Engineers Australia; or (b)
  IML"), which the `occupation_assessing_bodies` join-table schema needs to support
  as a one-to-many relationship, not a single FK.
Both tables already verified live and parseable under source 9 — **no separate
fetch is needed for this source; its real content lives at source 9's URL.**
**Retrieval method:** point `assessing_bodies`/`occupation_assessing_bodies`
provenance at LIN 19/051 (source 9) exactly as the catalog recommends; drop
`mara.gov.au` from consideration entirely (it has zero usable content for this
purpose, confirmed, not just suspected).

---

## 14. Policy events (budget / treasury / ministerial)

| URL | Status | Real finding |
|---|---|---|
| `budget.gov.au/content/migration.htm` | **HTTP 200, but soft-404** | Body is `<title>Page not found \| Budget 2026–27</title>`, and `<meta property="og:url" content="https://budget.gov.au/page-not-found.htm">` confirms this is the site's not-found page being served with a 200 status. **CORRECTS THE CATALOG:** this URL is dead for the current budget cycle, not "the migration-program budget paper index." |
| `budget.gov.au/` (root) | **200** | `<title>Budget.gov.au \| Budget 2026–27</title>`. Confirmed live nav structure is **thematic**, not migration-specific: `content/01-fuel-supply-and-security.htm`, `02-cost-of-living.htm`, `03-productivity.htm`, `04-tax-reform.htm`, `05-care-and-opportunity.htm`, `06-security-and-investment.htm`, plus `bp1/index.htm`…`bp4/index.htm`, `myefo/`, `overview/`, `pbs/`, `womens-statement/`. **No "migration" page exists anywhere in the 2026–27 site structure** — the budget site is restructured every year, so any fixed migration-specific URL is inherently fragile. I did not chase down which Budget Paper (BP1–4) currently contains migration planning-level figures — **UNVERIFIED**, out of time budget. |
| `treasury.gov.au/` | **200** | Generic homepage, 0 tables — fine as a stable anchor, exactly as the catalog intends (no scraping expected here). |
| `minister.homeaffairs.gov.au/` | **200** | `<title>Ministers for the Department of Home Affairs</title>`, 0 tables — a browsing index of per-release ministerial pages, exactly as the catalog describes; no single "all events" table, confirmed. |

**Notes/caveats:** the specific `content/migration.htm` URL the catalog cites as
"CONFIRMED (200)... the concrete page that announces annual planning levels" needs
correcting — it is dead. Since source 3 (see above) already contains the real
planning-level numbers directly and without any PDF dependency, this may reduce how
much budget.gov.au scraping is actually needed for `policy_events`/`ceiling_usage`
provenance — worth reconsidering the design rather than chasing a replacement URL.

---

## 15. Application funnel — submitted / invited

Same URL/page as source 2 — reused those findings in full (piggyback confirmed
correct, per catalog).
**`invited_count`:** available — via Table A ("Invitations issued on [date]": total
EOIs invited per round) and Table C (12-month invitation totals per subclass), both
decoded and verified under source 2.
**`submitted_count`:** I searched the fully-decoded page content (all 5 sections'
JSON) for `submitted`, `lodged`, `EOIs on hand`, `EOIs in the system`, `pool` —
**zero matches anywhere.** This is not a parser gap; the figure genuinely is not
published on this page. Confirms the catalog's own stated fallback: ship
`submitted_count = NULL`.

---

## 16. Application funnel — granted (Home Affairs annual report)

**URL:** `https://www.homeaffairs.gov.au/reports-and-publications/reports/annual-reports` — **200**.
**Page type:** same "content sections" hidden-field JSON pattern as sources
2/3/5(points-table)/7(character). Sections: **Overview, "Department of Home Affairs
2024–25 Annual Report", "Previous annual reports", "Home Affairs portfolio agencies
annual reports", "Regulator Performance Self-assessment Reports."**
**What's actually on the page:** direct PDF links, fully present in the static
decoded HTML (no separate fetch/JS needed to find them):
- Current year: `/reports-and-pubs/Annualreports/home-affairs-annual-report-2024-25.pdf`
- Previous years (43 links found): `/reports-and-pubs/Annualreports/home-affairs-annual-report-2023-24.pdf`, `-2022-23.pdf`, `-2021-22.pdf`, `-2020-21.pdf`, `-2019-20.pdf`, … all following the same `home-affairs-annual-report-{YYYY}-{YY}.pdf` naming pattern.
- Also 8 "Regulator Performance Self-assessment Report" PDFs under a different path
  (`/commitments/files/rpf-self-assessment-{YYYY}-{YY}.pdf`) — not relevant to
  `application_funnel` but present on the same page.
**Retrieval method:** hidden-field decode (as source 2/3) to enumerate the 44
annual-report PDF URLs deterministically; the specific pathway-level grant
breakdown inside any given PDF was **not opened or verified** (out of scope —
correctly Tier 3/5 per the catalog).
**Volume:** 44 total annual-report PDF links directly extractable from static HTML
(1 current + 43 previous years).
**Cadence:** `pageModified` element is present but **empty** (`<span
id="pageModified" class="hide"></span>` with no date text) — unusual compared to
every other immi/homeaffairs page checked in this audit; genuinely no date signal
available here.
**Notes/caveats:** whether the 2024–25 PDF (or any prior year) actually contains a
pathway-level (189/190/491/etc.) grant breakdown remains **UNVERIFIED** — I did not
open the PDF. The catalog's own fallback (ship `granted_count = NULL` if no
breakdown exists) still stands as untested.

---

## Summary table

| # | URL(s) | Page type | Extractable via | Confidence | Blocker |
|---|---|---|---|---|---|
| 1 | jobsandskills.gov.au ANZSCO occupations | Drupal Views card list (static) | `div.rowc` cards, `?page=N` pagination (103 pages) | **HIGH** | None — but ANZSCO is deprecated by JSA (see notes) |
| 2 | immi SkillSelect invitation-rounds | Hidden-field JSON (content sections) | Decode `#ctl00_PlaceHolderMain_PageSchemaHiddenField_Input` → parse `block` HTML | **HIGH** | None |
| 3 | immi migration-program-planning-levels | Hidden-field JSON (content sections) | Same decode technique | **HIGH** | None (contradicts catalog's PDF claim) |
| 4 | immi fees-and-charges → current-visa-pricing | Angular widget w/ internal REST API | Direct `POST /_layouts/15/api/data.aspx/GetPriceList` | **HIGH** | None |
| 5 | immi .../189/points-table (NOT points-tested) | Hidden-field JSON (content sections) | Same decode technique, on the correct URL | **HIGH** | Catalog names the wrong URL |
| 6 | immi 6× visa-listing pages | Angular (`ha-streams-root` / `ha-visa-details-root`) | Hidden-field JSON, 2 schema variants; "streams" pages need a sub-page hop | **MED** | Real per-visa numeric facts not in one clean spot |
| 7 | immi health/character/english | 3 different static templates | 3 different decode recipes (see §7) | **MED** | Inconsistent template per page |
| 8 | immi global-visa-processing-times | JS search tool w/ internal REST API | `POST /_layouts/15/api/GPT.aspx/GetProcessGuideVisas` then `GetProcessGuideInfo` × 76 | **HIGH** | 76 sequential calls required |
| 9 | legislation.gov.au LIN 19/051 (+2 companions) | Angular landing page → iframe → static epub HTML | Resolve epub URL, then parse 12 positional tables | **HIGH** (LIN 19/051); **MED** (2 companions, pattern only) | Two-hop resolution; no id/class selectors |
| 10 | jobsandskills.gov.au occupation-shortage-list | Drupal DataTables shell + JSON dataset | Direct JSON file download (`applet_data.spl_data`) | **HIGH** | Full rating vocabulary (R/M/Ns) unconfirmed |
| 11 | NSW/VIC/QLD/WA/SA nomination landing pages | Static prose (VIC excepted) | n/a — Tier 5 manual, as catalog says | **HIGH** (4/5); **N/A** (VIC blocked) | VIC still 403 Cloudflare |
| 12 | NSW/QLD/WA/SA occupation-list pages | Static tables (NSW, QLD) / search-gated (WA) / closed program (SA) | NSW/QLD: parse static tables; WA: unresolved; SA: nothing to parse right now | **HIGH** (NSW, QLD); **LOW** (WA); **N/A** (SA, VIC) | WA needs form params reverse-engineered; SA program closed |
| 13 | portal.mara.gov.au | Search-only interface, no usable data | n/a — redirect provenance to source 9 instead | **HIGH** (confirms mismatch) | Correct source is source 9, not this URL |
| 14 | budget.gov.au / treasury.gov.au / minister.homeaffairs.gov.au | Mixed: 1 dead soft-404, 3 live indexes | n/a — Tier 5 editorial, as catalog says | **MED** | `content/migration.htm` is dead; no replacement identified |
| 15 | (= source 2) | Hidden-field JSON | Same as source 2 | **HIGH** | `submitted_count` genuinely absent |
| 16 | homeaffairs.gov.au annual-reports index | Hidden-field JSON (content sections) | Decode → enumerate 44 PDF links | **HIGH** (index); **UNVERIFIED** (PDF content) | PDF pathway breakdown existence unchecked |

---

## CORRECTIONS TO THE CATALOG

1. **Source 3** — catalog says the planning-level numbers "live in linked PDFs that
   change URL each release" and marks it Tier 5. **False.** Zero PDF links on the
   page; the full 3-year planning-level table is directly, statically extractable.
   Should be Tier 2.
2. **Source 4** — catalog names `fees-and-charges` as the fee-table page. It is
   actually a 3-tile **index** page; the real table lives at
   `.../fees-and-charges/current-visa-pricing`, and that page is not a static table
   either — it is an Angular widget backed by a directly-callable JSON API
   (`/_layouts/15/api/data.aspx/GetPriceList`, 150 records). Catalog's "may be
   JS-augmented, confirm at build time" undersells what's actually a clean win (a
   public JSON API), but also doesn't name the correct sub-page.
3. **Source 5** — catalog's URL (`/points-tested`) genuinely has no numeric points
   table (flag confirmed true), but the fix isn't Playwright/tier-5 fallback as the
   GAPS section suggests — the real table is at a **different, sibling URL**
   (`/points-table`), which is fully static and Tier-2-extractable via the same
   hidden-field technique used elsewhere on the site.
4. **Source 8** — catalog says "HTML table (visa × median processing days)". It is
   actually a **per-visa lookup search tool**, not a browsable table, backed by a
   directly-callable JSON API (`GetProcessGuideVisas` / `GetProcessGuideInfo`, same
   internal REST convention as source 4) returning a **percentile distribution**
   (25th/50th/75th/90th), not a single median.
5. **Source 9** — catalog flags the real HTML structure as unverified (open
   question #1). Resolved: the `/latest` URL is an Angular shell with no tables;
   real content is a separate static document reached via an `<iframe>`, at a
   deterministic but two-hop URL. Once there, 12 tables exist with no id/class
   selectors (positional/heading-anchored selection required). This document (Table
   5 and Table 6) **also directly satisfies source 13's data need** — no need for a
   second/different citation for `assessing_bodies`.
6. **Source 10** — catalog speculates a "downloadable dataset... if offered." One
   is directly offered and confirmed: a 1.47 MB JSON file referenced in the page's
   own `drupalSettings` blob, no scraping needed. Also: the `future_demand_rating`
   dimension the catalog's schema wants (`d` field in the source JSON) is `null`
   for every record checked — it does not currently appear to be populated by JSA
   at all.
7. **Source 14** — catalog marks `budget.gov.au/content/migration.htm` CONFIRMED
   (200) and describes it as the migration planning-level index page. It returns
   HTTP 200 but is a **soft-404** ("Page not found") — the URL is dead for the
   current (2026–27) budget site, which has been restructured to thematic sections
   with no dedicated migration page. No replacement URL was identified in the time
   available.
8. **Source 8 (minor)** — catalog implies `.../visa-processing-times` (without
   `/global-`) redirects to the URL it names. It does not; both paths return
   independent 200 pages.
9. **Source 1 (new finding, not a catalog error but a material omission)** — the
   catalog doesn't mention that ANZSCO itself is being retired by JSA in favour of
   a new "OSCA" classification, actively promoted via a sitewide banner on the very
   page being scraped. This is a real, dated fact from the live site that affects
   the long-term viability of an ANZSCO-anchored `occupations` schema.

---

## CANNOT VERIFY

- **Source 9 companion instruments** (F2024L01618, F2024L01616): confirmed the
  same iframe→epub resolution pattern applies (URLs resolved and reachable), but I
  did **not** fetch and parse their table content — row/column shape for the
  subclass-186 and ANZSCO-definition instruments is unconfirmed. *Reason: time-boxed
  against the 16-source scope; the pattern is established and lower-risk to repeat.*
- **Source 10 rating codes `R`, `M`, and lowercase `Ns`**: found in the raw dataset
  but their precise definitions were not locatable in static HTML (the page's "What
  do the ratings mean" explainer is JS-populated). *Reason: definitions live behind
  client-side rendering I did not execute (no headless browser available in this
  environment).*
- **Source 10 `spl_search` companion JSON** (`splSearch (2).json`, 316 KB): its URL
  was found and is presumably fetchable the same way as `spl_data`, but its content
  was not downloaded or inspected. *Reason: judged lower-priority than `spl_data`
  given time budget; likely a lighter autocomplete/search index, not core rating
  data.*
- **Source 12 WA eligible-occupations full list**: the Views search form returns 0
  results with no filter applied; I did not reverse-engineer its query-string or
  AJAX contract to retrieve the full occupation set. *Reason: would require either
  trial-and-error against a live government form (judged impolite/wasteful without
  a clearer target) or a headless browser; out of scope for a read-only curl-based
  audit.*
- **Source 14 replacement for `budget.gov.au/content/migration.htm`**: confirmed
  the old URL is dead and enumerated the current site's top-level sections
  (BP1–4, thematic pages), but did not open each to locate which one (if any)
  currently carries migration planning-level detail. *Reason: this source is
  already Tier 5/editorial per the catalog and source 3 already covers the
  numeric planning-level data without needing budget.gov.au at all — judged lower
  marginal value to chase further within the time budget.*
- **Source 16 PDF content**: whether any annual report PDF contains a
  pathway-level (per-visa-subclass) grant breakdown was not checked — no PDF was
  opened. *Reason: explicitly out of scope per the task brief (PDF content
  extraction belongs to a later tier/agent); only the index/link-enumeration layer
  was in scope for this page-structure audit.*
- **Cadence/"last updated" signal for source 1 (ANZSCO) and all of source 11/12's
  state pages (NSW, QLD, WA, SA)**: no explicit "last updated" date found in the
  static HTML of any of these pages. *Reason: genuinely absent from the markup, not
  a search failure — confirmed by targeted `grep` for common "last updated" /
  "reviewed" phrasings on each page individually.*
