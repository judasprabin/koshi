# koshi — ETL Pipeline Architecture

**Status:** Architecture research & technical review — August 2026
**Author:** Technical review of `judasprabin/koshi` + `research/au-visa-sources`
**Purpose:** Complete ETL pipeline design for Australian skilled-migration data extraction, transformation, and serving.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Industry Survey: How Modern ETL Pipelines Are Built](#2-industry-survey-how-modern-etl-pipelines-are-built)
3. [Source Inventory: Complete Data Landscape (19 Domains)](#3-source-inventory-complete-data-landscape-19-domains)
4. [Extraction Tier Strategy: Per-Source Methods](#4-extraction-tier-strategy-per-source-methods)
5. [Complete Data Model: Entities, Relations, Fields, Types](#5-complete-data-model-entities-relations-fields-types)
6. [Pipeline Architecture: Extract → Validate → Transform → Load](#6-pipeline-architecture-extract--validate--transform--load)
7. [Fault Tolerance & Resilience Design](#7-fault-tolerance--resilience-design)
8. [Ingestion Orchestration & Scheduling](#8-ingestion-orchestration--scheduling)
9. [Serving Layer: API Design & Caching](#9-serving-layer-api-design--caching)
10. [Infrastructure & Deployment](#10-infrastructure--deployment)
11. [Implementation Roadmap](#11-implementation-roadmap)
12. [Appendix: Technology Comparisons](#12-appendix-technology-comparisons)

---

## 1. Executive Summary

**koshi** is a headless backend service that extracts, stores, and serves structured, sourced facts about the Australian skilled-migration system. It is the data engine behind Saathi's Visa Landscape Navigator — a tool that helps skilled migrants understand occupation ceilings, EOI thresholds, state nomination status, and processing times.

### What koshi is

| Property | Value |
|---|---|
| **Type** | Headless ETL + Read API microservice |
| **Domain** | AU skilled migration public data |
| **Auth** | None — public data, no end-user identity |
| **Consumer** | `lukla` (Next.js frontend), called via Cloud Run IAM |
| **Stack** | Python 3.11, FastAPI, SQLAlchemy 2.0, Alembic, Postgres, BeautifulSoup4/lxml |
| **Infra** | Cloud Run Job (ETL) + Cloud Run Service (API) + Cloud SQL Postgres |
| **Scope** | 19 gov domains → 16 data sources → 15+ Postgres tables → 6+ API endpoints |

### Current State vs Target

| Layer | Today (occupation slice) | Target (full system) |
|---|---|---|
| **Sources extracted** | 2 (ANZSCO + SkillSelect rounds) | 16 (all cataloged sources) |
| **Tables populated** | 5 (occupations, eoi_rounds, ceiling_usage, occupation_momentum, source_pages) | 15+ (full data model) |
| **API endpoints** | 2 (list + detail) | 6+ (states, visas, national, reference) |
| **Extraction tiers** | 1 (deterministic BS4/lxml) | 4 (deterministic, PDF, Claude-fallback, curated) |
| **Scheduling** | Manual (`python -m koshi`) | Cloud Run Job on cron (per-source cadence) |
| **Deployment** | Local Docker | GCP Cloud Run + Cloud SQL |

### Architecture Principles

1. **Every row carries provenance.** `source_url`, `retrieved_at`, `reliability_tier` on every fact table. No fact ships without its origin.
2. **Honesty over completeness.** When a source doesn't exist or resists automation, say so explicitly rather than shipping fabricated data.
3. **Deterministic where possible, LLM where necessary.** Clean HTML tables → BS4 parsers. PDFs and prose → Claude extraction. Pages that resist both → human-curated seed.
4. **Fetcher doesn't know about parser.** Content hash and `last_changed_at` are committed before parsing is attempted. A failed parse is retried on every subsequent run.
5. **Derived ≠ scraped.** Computed facts (momentum, comparisons) cite the source rows they were computed from, not an external URL.
6. **One bounded context.** koshi never calls thamel, manaslu, or any other Saathi service. It's a pure data provider with zero outgoing dependencies.

---

## 2. Industry Survey: How Modern ETL Pipelines Are Built

Before designing koshi's pipeline, let's survey the state of the art — what tools, patterns, and frameworks the industry uses to build production ETL pipelines at scale.

### 2.1 The Three Generations of ETL

| Generation | Era | Paradigm | Examples | Best For |
|---|---|---|---|---|
| **Gen 1: Batch ETL** | 1990s–2010s | Scheduled bulk extraction, staging tables, SQL transforms | Informatica, Talend, SSIS | Enterprise data warehousing |
| **Gen 2: Stream Processing** | 2010s–present | Event-driven, real-time, append-only logs | Kafka, Flink, Spark Streaming | High-throughput event data |
| **Gen 3: ELT (Extract-Load-Transform)** | 2015s–present | Raw data lands first, transforms run in-warehouse | Fivetran, Airbyte, dbt | Cloud data warehouses (Snowflake, BigQuery) |
| **Gen 3.5: AI-Augmented ETL** | 2023–present | LLMs for unstructured extraction, schema inference, anomaly detection | Unstructured.io, LlamaParse, Claude | Semi-structured docs, PDFs, web scraping with changing layouts |

**koshi falls into Gen 3.5.** Most of its sources are unstructured government HTML pages and PDFs that resist traditional scraping. The extraction pipeline needs deterministic parsers for stable tables AND LLM fallback for everything else.

### 2.2 The Modern Web-Scraping Stack

```
┌─────────────────────────────────────────────────────────────────┐
│  ORCHESTRATION        │  EXTRACTION         │  STORAGE          │
│                       │                     │                   │
│  Airflow / Prefect    │  Scrapy / Playwright│  Postgres / S3    │
│  Dagster / Temporal   │  BeautifulSoup      │  MongoDB / Kafka   │
│  Cloud Run Jobs       │  lxml / parsel      │  BigQuery          │
│                       │  Unstructured.io    │                   │
│                       │  Claude / GPT-4     │                   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Framework Comparison: What Others Use

| Framework | Type | Strengths | Weaknesses | Verdict for koshi |
|---|---|---|---|---|
| **Scrapy** | Full scraping framework | Built-in middleware, spiders, item pipelines, auto-throttle | Heavy for simple HTML tables; async complexity | ❌ Overkill for ~16 known-page sources |
| **Playwright / Puppeteer** | Headless browser | Handles JS-rendered pages, SPAs | 10-20x slower, memory-heavy | ⚠️ Only if gov pages become JS-rendered |
| **BeautifulSoup4 + lxml** | HTML parser | Fast, simple, no browser overhead | No JS support | ✅ Primary tier — koshi already uses this |
| **Unstructured.io** | Document parsing | PDF, HTML, DOCX → structured text | Dependency heavy | ⚠️ Consider for PDF tier |
| **LlamaParse / Marker** | AI PDF parsing | Handles tables, complex layouts | API cost, latency | ⚠️ For planning-levels PDF reports |
| **Claude / GPT-4 with structured output** | LLM extraction | Handles prose, changing layouts, implicit data | Cost, latency, non-deterministic | ✅ Fallback tier — Claude with structured JSON mode |
| **dlt (data load tool)** | ELT framework | Schema inference, incremental loading, declarative | Python-only, younger ecosystem | ⚠️ Worth evaluating for pipeline orchestration |
| **Meltano** | ELT platform | Singer taps/targets, 300+ connectors | Heavy setup for simple HTTP sources | ❌ Overkill for direct HTTP fetches |

### 2.4 Proven Patterns from Production Pipelines

**Pattern 1: The Watermark Pattern (koshi already uses this)**

```
fetch → hash content → commit content_hash + last_changed_at
         ↓
        only if last_changed_at > last_extracted_at:
           parse → validate → persist → commit last_extracted_at
```

This is what koshi's `_needs_extraction()` does — the extraction watermark decouples "the page changed" from "we successfully parsed it." Industry standard in Airbyte, Fivetran, and every serious ETL tool.

**Pattern 2: Multi-Tier Extraction (Zillow, Airbnb, Stripe)**

Sources are classified by extraction difficulty:
- **Tier 1: Deterministic parser** — stable HTML tables, API endpoints, CSV exports. Fast, reliable, zero LLM cost.
- **Tier 2: Structured extraction with layout awareness** — PDFs with tables, semi-structured HTML. Use Unstructured.io or marker-pdf.
- **Tier 3: LLM fallback** — prose, changing layouts, implicit data. Claude/GPT-4 with structured output mode. Highest cost, lowest reliability.
- **Tier 4: Human-curated seed** — sources that resist all automation. Manually maintained YAML/JSON, versioned in git.

**koshi needs all four tiers.** We'll map every source to a tier below.

**Pattern 3: Idempotency by Natural Key (Stripe, GitHub)**

Every row has a natural key — `(visa_code, occupation_code, round_date)` for EOI rounds, `(state_code, occupation_code, as_of_date)` for state nominations. Re-running the pipeline with the same source data produces the same rows, no duplicates. This is what koshi's `eoi_rounds` unique constraint already enforces.

**Pattern 4: Dead Letter Queue for Unparseable Content (Netflix, Uber)**

When extraction fails, save the raw HTML/PDF to blob storage with metadata (URL, timestamp, error). An operator (or future LLM run) can replay it later. This is missing from koshi today and should be added.

**Pattern 5: Content Freshness Monitoring (GitHub Archive Program)**

Every fact table has `retrieved_at` + `source_url`. A background job checks "how stale is this data" and alerts when sources haven't been re-crawled within their expected cadence. The `source_pages` table already has `last_checked_at` — extend this with a freshness dashboard.

### 2.5 The Fastest Path to Production

Given koshi's constraints (16 sources, single developer, GCP-native), the fastest proven stack is:

```
Cloud Run Jobs (per-source, per-cadence)
    ↓
Python 3.11 + httpx (fetch) + BS4/lxml (deterministic) + Claude API (fallback)
    ↓
Postgres (source_pages → extraction → fact tables)
    ↓
FastAPI (Cloud Run Service) → lukla frontend
```

**Why this over alternatives:**

| Alternative | Rejection Reason |
|---|---|
| Airflow / Prefect | Operational overhead for 16 sources. Cloud Run Jobs + Cloud Scheduler gives scheduling without managing a scheduler. |
| Kafka / streaming | Sources update monthly/annually, not in real-time. Batch ETL is the right abstraction. |
| dbt | dbt excels at SQL transforms on already-loaded data. koshi's hard part is extraction from HTML/PDFs, not SQL transforms. |
| Scrapy | Scrapy's strength is crawling thousands of unknown pages. koshi targets ~30 known pages. BS4 + httpx is simpler. |
| BigQuery | Postgres is sufficient for koshi's scale (<1M rows). Cloud SQL is simpler and shares an instance with other Saathi services. |

---

## 3. Source Inventory: Complete Data Landscape (19 Domains)

This is the master catalog of every data source koshi needs — derived from `research/au-visa-sources/config.yaml`'s 19-domain crawl list and `docs/data-sources.md`'s 16-source catalog.

### 3.1 Domain Map

```
┌────────────────────────────────────────────────────────────┐
│                 AU Government Domains (19)                  │
├────────────────────────────────────────────────────────────┤
│ imni.homeaffairs.gov.au    ── visas, fees, rounds, forms   │
│ homeaffairs.gov.au         ── policy, media, reports       │
│ legislation.gov.au         ── Migration Act, instruments   │
│ aat.gov.au                 ── tribunal decisions           │
│ art.gov.au                 ── review tribunal decisions    │
│ mara.gov.au                ── migration agent registry     │
│ portal.mara.gov.au         ── agent search                 │
│ studyaustralia.gov.au      ── student visa info            │
│ jobsandskills.gov.au       ── ANZSCO, skills priority      │
│ treasury.gov.au            ── budget measures              │
│ budget.gov.au              ── budget content               │
│ abs.gov.au                 ── migration statistics         │
│ nsw.gov.au                 ── NSW nomination               │
│ liveinmelbourne.vic.gov.au ── VIC nomination               │
│ migration.qld.gov.au       ── QLD nomination               │
│ migration.wa.gov.au        ── WA nomination                │
│ migration.sa.gov.au        ── SA nomination                │
└────────────────────────────────────────────────────────────┘
```

### 3.2 Complete Source-to-Entity Mapping

| # | Source | URL | Format | Cadence | Extraction Tier | Feeds Table(s) | Status |
|---|---|---|---|---|---|---|---|
| 1 | **ANZSCO occupations** | `jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations-anzsco` | HTML table (`#occupation-list`) | Near-static | Tier 1 — Deterministic BS4 | `occupations` (code, name, unit_group) | ✅ Done |
| 2 | **EOI invitation rounds** | `immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds` | HTML table (`#round-results`) | ~Monthly | Tier 1 — Deterministic BS4 | `eoi_rounds` (visa_code, occupation_code, round_date, threshold_points, invitations_issued) | ✅ Done |
| 3 | **Occupation ceilings** | `immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels` | PDF report | Few/year | Tier 2 → Tier 4 hybrid | `ceiling_usage` (issued, ceiling, as_of_date) + `program_allocation` | ⚠️ Partial (curated seed for 2 occupations) |
| 4 | **Visa fees** | `immi.homeaffairs.gov.au/visa-fees` | HTML table | Annual (indexation) | Tier 1 — Deterministic BS4 | `visa_subclasses.base_application_cost` | ❌ |
| 5 | **Points test criteria** | `immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/points-test` | HTML structured | Rare | Tier 1 — Deterministic BS4 | `points_criteria_reference` (criterion_name, band_description, points_value) | ❌ |
| 6 | **Visa subclass static facts** (189/190/491/485/500/482) | Individual Home Affairs visa pages | HTML prose | Rare | Tier 3 — Claude extraction | `visa_subclasses` (name, family, permanence, age_limit, work_rights, family_inclusion, residency_requirement, onward_pathway, points_test_required) | ❌ |
| 7 | **Health/Character/English requirements** | `immi.homeaffairs.gov.au/help-support/meeting-our-requirements/{health,character,english-language}` | HTML prose | Rare | Tier 3 — Claude extraction | `english_test_bands` (test_name, band_name, points_value) | ❌ |
| 8 | **Processing times** | Home Affairs Global Visa Processing Times page | HTML table | ~Monthly | Tier 1 — Deterministic BS4 | `processing_times` (visa_code, as_of_date, median_days) | ❌ |
| 9 | **MLTSSL/STSOL/ROL lists** | `legislation.gov.au` legislative instruments | HTML/gazette | Few/year | Tier 1 — Deterministic BS4 | `list_change_log` (list_name, occupation_code, change_type, effective_date) | ❌ |
| 10 | **Skills priority list** | `jobsandskills.gov.au/skills-priority-list` | HTML/dataset | Annual | Tier 1 — Deterministic BS4 | `skills_priority` (occupation_code, priority_level, as_of_date) | ❌ |
| 11 | **State nomination status** (NSW/VIC/QLD/WA/SA) | State gov landing pages | HTML prose | Irregular | **Tier 4 — Human-curated seed** | `state_nomination_status` (state_code, occupation_code, status, fee, points_minimum, job_offer_required, residency_commitment, decision_time, documents_required, approval_pattern_note) | ❌ |
| 12 | **State occupation list changes** | State pages (via crawler diff) | HTML | Irregular | Tier 3 — Claude + diff | `list_change_log` (list_name=state code, change_type, effective_date) | ❌ |
| 13 | **Assessing bodies × occupations** | `mara.gov.au` + assessing-body sites | HTML | Rare | Tier 4 — Curated seed | `assessing_bodies` + `occupation_assessing_bodies` (join table) | ❌ |
| 14 | **Policy events** | Ministerial press releases, `budget.gov.au`, `treasury.gov.au` | HTML | Ad hoc | Tier 4 — Curated, explicitly editorial | `policy_events` (event_date, visa_code, description) | ❌ |
| 15 | **Application funnel (submitted/invited)** | SkillSelect round results pages | HTML table | ~Monthly | Tier 1 — Deterministic BS4 | `application_funnel` (visa_code, program_year, submitted_count, invited_count) | ❌ |
| 16 | **Application funnel (granted)** | Home Affairs annual report | PDF | Annual | Tier 2 — PDF extraction | `application_funnel.granted_count` (may be NULL where unconfirmed) | ❌ |
| — | **Points distribution** | **No confirmed source** | — | — | Deferred | `points_distribution` — NOT built until source confirmed | ❌ Deferred |
| — | **Occupation momentum** | Computed internally | — | After every EOI sync | Derived | `occupation_momentum` (direction) | ✅ Done |

### 3.3 Source Risk Assessment

| Risk Factor | Sources Affected | Mitigation |
|---|---|---|
| **Page redesign breaks parser** | #1, #2, #4, #5, #8, #9, #10, #15 (deterministic) | Extraction watermark ensures retry; dead letter queue for failures; alert on parse failures |
| **PDF format changes** | #3, #16 | Human-curated seed as permanent fallback; Claude PDF extraction for attempt |
| **No clean data table exists** | #11, #12, #13, #14 | Curated seed is the primary strategy, not a fallback |
| **Source disappears** | All | `source_pages.status = 'dead'` detection; frontend shows "last updated" timestamp |
| **Source never existed** | Points distribution | Deferred entirely — not built until confirmed |

---

## 4. Extraction Tier Strategy: Per-Source Methods

koshi needs a four-tier extraction strategy because its 16 sources span the full spectrum from "clean HTML table" to "PDF report" to "human-only prose page."

### 4.1 Tier 1: Deterministic BS4/lxml Parsers

**When:** The source page has a stable, identifiable HTML table with predictable column layout.

**Sources:** #1 (ANZSCO), #2 (EOI rounds), #4 (visa fees), #5 (points test), #8 (processing times), #9 (legislation lists), #10 (skills priority), #15 (application funnel).

**Architecture:**

```python
# Pattern: Each parser is a module in extraction/
# ── extraction/visa_fees.py
def parse_visa_fees(html: str, *, source_url: str, retrieved_at: datetime) -> list[VisaFee]:
    require_provenance(
        reliability_tier="official_scraped",
        source_url=source_url,
        retrieved_at=retrieved_at
    )
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="visa-fees-table")  # selector validated against fixture
    if table is None:
        raise ExtractionError("visa fees table not found — possible site redesign")

    fees = []
    for row in table.find("tbody").find_all("tr"):
        cells = row.find_all("td")
        fees.append(VisaFee(
            visa_code=normalize_visa_code(cells[0].get_text(strip=True)),
            base_application_cost=parse_currency(cells[1].get_text(strip=True)),
            source_url=source_url,
            retrieved_at=retrieved_at,
            reliability_tier="official_scraped",
        ))
    return fees
```

**Key design decisions:**
- Each parser has a fixture HTML file in `tests/fixtures/` — tests run against real saved HTML
- Selectors are explicit (CSS ID/class, XPath) — not heuristic "find any table"
- Parsers raise on missing expected structure → pipeline retries next run
- Currency/date parsing is centralized in a `parsing_helpers.py` module

### 4.2 Tier 2: PDF Extraction (LlamaParse + Marker)

**When:** The source is a PDF report with structured data that resists simple text extraction.

**Sources:** #3 (occupation ceilings/planning levels), #16 (application funnel granted counts).

**Architecture:**

```python
# ── extraction/pdf_extractor.py
def extract_from_pdf(
    pdf_bytes: bytes,
    *,
    source_url: str,
    extraction_schema: type[BaseModel],
) -> list[dict]:
    """
    Two-stage PDF extraction:
    1. Try marker-pdf (local, fast, free) for structured tables
    2. Fall back to Claude (API, slow, costly) if marker fails
    """
    # Stage 1: Structural extraction
    try:
        markdown_output = marker.convert(pdf_bytes)
        tables = extract_tables_from_markdown(markdown_output)
        if tables:
            return tables
    except Exception:
        pass

    # Stage 2: Claude vision extraction
    claude_response = claude.messages.create(
        model="claude-sonnet-4-20250514",
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64_pdf}},
                {"type": "text", "text": f"Extract the following data from this PDF into JSON matching this schema: {extraction_schema.model_json_schema()}"}
            ]
        }]
    )
    return parse_claude_json_response(claude_response)
```

**Key design decisions:**
- PDF extraction is wrapped in a single module, callable from multiple pipeline sync functions
- Results are `official_curated` tier — the PDF parser is not as deterministic as an HTML table parser
- Extraction failures fall back to the curated seed (Tier 4)
- PDF bytes are saved to GCS dead letter bucket for future replay

### 4.3 Tier 3: Claude Structured Extraction

**When:** The source is HTML prose — a page with the data embedded in paragraphs, not tables. Layout varies between pages.

**Sources:** #6 (visa subclass static facts), #7 (health/character/English requirements), #12 (state list changes via crawler diff).

**Architecture:**

```python
# ── extraction/claude_extractor.py
VISA_SUBCLASS_SCHEMA = {
    "type": "object",
    "properties": {
        "visa_code": {"type": "string", "description": "e.g., '189', '190'"},
        "name": {"type": "string"},
        "family": {"type": "string", "enum": ["skilled", "family", "student", "temporary", "humanitarian"]},
        "permanence": {"type": "string", "enum": ["permanent", "provisional", "temporary"]},
        "age_limit": {"type": "string", "nullable": True},
        "work_rights_description": {"type": "string"},
        "family_inclusion_rule": {"type": "string"},
        "residency_requirement_description": {"type": "string"},
        "occupation_list_required": {"type": "boolean"},
        "onward_pathway_code": {"type": "string", "nullable": True},
        "points_test_required": {"type": "boolean"},
        "processing_time_median_days": {"type": "integer", "nullable": True},
    },
    "required": ["visa_code", "name", "family", "permanence", "points_test_required"]
}

def extract_visa_subclass_facts(
    html: str,
    *,
    visa_code: str,
    source_url: str,
    retrieved_at: datetime,
) -> VisaSubclass:
    require_provenance(
        reliability_tier="official_curated",
        source_url=source_url,
        retrieved_at=retrieved_at
    )

    # Strip to text content only — remove nav, footer, scripts
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["nav", "footer", "script", "style", "header"]):
        tag.decompose()
    text_content = soup.get_text(" ", strip=True)[:30000]  # 30k char limit

    response = claude.messages.create(
        model="claude-haiku-4-20250514",  # Haiku is sufficient for extraction
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": text_content},
                {"type": "text", "text": f"Extract structured facts about subclass {visa_code} from the page content above. Return ONLY valid JSON matching this schema."}
            ]
        }],
        response_format={"type": "json_schema", "json_schema": VISA_SUBCLASS_SCHEMA}
    )

    data = json.loads(response.content[0].text)
    return VisaSubclass(
        visa_code=visa_code,
        source_url=source_url,
        retrieved_at=retrieved_at,
        reliability_tier="official_curated",
        **data
    )
```

**Key design decisions:**
- **Claude Haiku for extraction** — not Sonnet/Opus. Extraction from prose is a Haiku-class task. Cost: ~$0.001 per page extraction vs $0.015 for Sonnet.
- **Structured output mode** — JSON Schema enforcement eliminates hallucinated fields.
- **`official_curated` tier** — Claude extraction is less reliable than deterministic parsing. The tier reflects this.
- **HTML is stripped to text first** — no need to send full HTML to Claude. Strip nav/footer/scripts, send only body text.
- **Prompt caching for repeated extractions** — the schema + instruction prefix is identical across all pages. This gives ~90% cost reduction on the system prompt portion.

**Cost estimate:**
- 6 visa subclass pages × monthly re-extraction = 6 × $0.001 = $0.006/month
- Health/character/English pages: 3 × quarterly = $0.003/quarter
- Total Claude Tier 3 cost: <$0.10/month

### 4.4 Tier 4: Human-Curated Seed (YAML → Git)

**When:** The source resists all automation. State pages are landing pages, not data tables. The rich per-occupation detail the frontend needs must be hand-entered.

**Sources:** #11 (state nomination status), #13 (assessing bodies), #14 (policy events). Also the fallback for #3 and #12 when automation fails.

**Architecture (koshi already has this pattern — `seeds/ceiling_usage_manual.yaml`):**

```yaml
# seeds/state_nomination_seed.yaml
# Curated source — reviewed against state gov pages on a monthly cadence.
# Last review: 2026-08-15
# Reviewer: Prabin Karki
sources:
  state_nomination:
    - source_url: "https://www.nsw.gov.au/visas-and-migration/skilled-visas/nsw-skilled-occupation-lists"
      as_of_date: "2026-08-01"
      entries:
        - state_code: "NSW"
          occupation_code: "261313"
          status: "open"
          fee: 330
          points_minimum: 85
          job_offer_required: false
          residency_commitment_description: "Must live and work in NSW for at least 2 years"
          decision_time_estimate: "6-8 weeks"
          documents_required:
            - "Skills assessment"
            - "English test results"
            - "Employment references"
            - "CV/Resume"
          approval_pattern_note: "Priority given to applicants with 85+ points and NSW work experience"
```

**Loader pattern (mirrors existing `seeds/loader.py`):**

```python
def load_state_nomination_seed(session: Session, seed_path: Path) -> list[StateNominationStatus]:
    with open(seed_path) as f:
        data = yaml.safe_load(f)

    entries = []
    for source in data["sources"]["state_nomination"]:
        for entry in source["entries"]:
            row = StateNominationStatus(
                state_code=entry["state_code"],
                occupation_code=entry["occupation_code"],
                status=entry["status"],
                fee=entry["fee"],
                points_minimum=entry["points_minimum"],
                job_offer_required=entry["job_offer_required"],
                residency_commitment_description=entry["residency_commitment_description"],
                decision_time_estimate=entry["decision_time_estimate"],
                documents_required=json.dumps(entry["documents_required"]),
                approval_pattern_note=entry.get("approval_pattern_note"),
                as_of_date=date.fromisoformat(source["as_of_date"]),
                source_url=source["source_url"],
                retrieved_at=datetime.now(timezone.utc),
                reliability_tier="official_curated",
            )
            session.merge(row)
            entries.append(row)
    session.commit()
    return entries
```

**Key design decisions:**
- **Version-controlled in git** — seed files live in `src/koshi/seeds/`, reviewed via PR
- **`official_curated` tier** — honest about the data's origin
- **Review cadence documented in the seed file** — `last_review` field + human reviewer
- **Staleness alert** — a cron job checks "has this seed been reviewed in the last 30 days?"
- **This is bato's pattern** — `bato` already uses curated seeds for its own unparsable sources. Reuse the pattern, don't reinvent it.

### 4.5 Extraction Tier Decision Tree

```
Source page fetched
    │
    ├── HTML with stable table? (Sources #1, #2, #4, #5, #8, #9, #10, #15)
    │   └── Tier 1: Deterministic BS4/lxml parser
    │       └── reliability_tier = "official_scraped"
    │
    ├── PDF report with tables? (Sources #3, #16)
    │   └── Tier 2: marker-pdf → Claude fallback
    │       └── reliability_tier = "official_curated"
    │
    ├── HTML prose, data not in tables? (Sources #6, #7, #12)
    │   └── Tier 3: Claude structured extraction
    │       └── reliability_tier = "official_curated"
    │
    └── No clean parsable structure? (Sources #11, #13, #14)
        └── Tier 4: Human-curated seed (YAML → git → loader)
            └── reliability_tier = "official_curated"
```

---

## 5. Complete Data Model: Entities, Relations, Fields, Types

### 5.1 Full Entity-Relationship Diagram

```
┌─────────────────────┐
│    source_pages     │  ← Crawl registry (not a fact table)
│─────────────────────│
│ id (PK, int)        │
│ url (UNIQUE, text)  │
│ domain (text)       │
│ category (text)     │
│ content_hash (text) │
│ first_seen_at (ts)  │
│ last_checked_at (ts)│
│ last_changed_at (ts)│
│ last_extracted_at   │
│   (ts, nullable)    │
│ status (text)       │
└─────────────────────┘
         │ (no FK — metadata only)

┌─────────────────────────┐
│     occupations          │  ← Reference: ANZSCO codes
│─────────────────────────│
│ code (PK, text)          │  ANZSCO code, e.g. "261313"
│ name (text, NOT NULL)    │  "Software Engineer"
│ unit_group (text)        │  "2613 Software and Applications Programmers"
│ source_url (text)        │
│ retrieved_at (timestamptz)│
│ reliability_tier (text)  │  "official_scraped"
└─────────────────────────┘
    │ 1
    │
    ├───< eoi_rounds
    │    ┌──────────────────────────────────────┐
    │    │           eoi_rounds                  │
    │    │──────────────────────────────────────│
    │    │ id (PK, int)                         │
    │    │ visa_code (text, NOT NULL)            │  189, 190, 491
    │    │ occupation_code (FK→occupations.code, │
    │    │   nullable)                          │  NULL = visa-wide round
    │    │ round_date (date, NOT NULL)           │
    │    │ threshold_points (int, NOT NULL)      │
    │    │ invitations_issued (int, nullable)    │
    │    │ source_url (text)                    │
    │    │ retrieved_at (timestamptz)            │
    │    │ reliability_tier (text)              │  "official_scraped"
    │    │                                      │
    │    │ UNIQUE (visa_code, occupation_code,   │
    │    │         round_date)                  │
    │    └──────────────────────────────────────┘
    │
    ├───< ceiling_usage
    │    ┌──────────────────────────────────────┐
    │    │         ceiling_usage                 │
    │    │──────────────────────────────────────│
    │    │ id (PK, int)                         │
    │    │ occupation_code (FK, NOT NULL)       │
    │    │ program_year (text, NOT NULL)         │  "2025-26"
    │    │ issued (int, NOT NULL)               │
    │    │ ceiling (int, NOT NULL)              │
    │    │ as_of_date (date, NOT NULL)           │
    │    │ source_url (text)                    │
    │    │ retrieved_at (timestamptz)            │
    │    │ reliability_tier (text)              │  "official_curated"
    │    │                                      │
    │    │ CHECK (issued <= ceiling AND         │
    │    │        ceiling > 0)                  │
    │    └──────────────────────────────────────┘
    │
    ├───< occupation_momentum
    │    ┌──────────────────────────────────────┐
    │    │     occupation_momentum               │
    │    │──────────────────────────────────────│
    │    │ id (PK, int)                         │
    │    │ occupation_code (FK, NOT NULL)       │
    │    │ computed_at (timestamptz, NOT NULL)   │
    │    │ direction (text, NOT NULL)            │  rising | falling | steady
    │    │ reliability_tier (text)              │  "derived" (always)
    │    └──────────────────────────────────────┘
    │
    ├───< state_nomination_status (NEW)
    │    ┌──────────────────────────────────────┐
    │    │    state_nomination_status            │
    │    │──────────────────────────────────────│
    │    │ id (PK, int)                         │
    │    │ state_code (text, NOT NULL)           │  NSW, VIC, QLD, WA, SA
    │    │ occupation_code (FK, NOT NULL)       │
    │    │ status (text, NOT NULL)              │  open | limited | closed
    │    │ fee (int, nullable)                  │
    │    │ points_minimum (int, nullable)        │
    │    │ job_offer_required (bool)            │
    │    │ residency_commitment_description     │
    │    │   (text, nullable)                   │
    │    │ decision_time_estimate (text, null)   │
    │    │ documents_required (jsonb, nullable) │  Array of strings
    │    │ approval_pattern_note (text, null)    │
    │    │ as_of_date (date, NOT NULL)           │
    │    │ source_url (text)                    │
    │    │ retrieved_at (timestamptz)            │
    │    │ reliability_tier (text)              │  "official_curated"
    │    └──────────────────────────────────────┘
    │
    ├───< skills_priority (NEW)
    │    ┌──────────────────────────────────────┐
    │    │       skills_priority                 │
    │    │──────────────────────────────────────│
    │    │ id (PK, int)                         │
    │    │ occupation_code (FK, NOT NULL)       │
    │    │ priority_level (text, NOT NULL)       │  shortage | no_shortage | regional
    │    │ as_of_date (date, NOT NULL)           │
    │    │ source_url (text)                    │
    │    │ retrieved_at (timestamptz)            │
    │    │ reliability_tier (text)              │  "official_scraped"
    │    └──────────────────────────────────────┘
    │
    └───< occupation_assessing_bodies (NEW, join)
         ┌──────────────────────────────────────┐
         │  occupation_assessing_bodies          │
         │──────────────────────────────────────│
         │ id (PK, int)                         │
         │ occupation_code (FK, NOT NULL)       │
         │ body_name (FK→assessing_bodies,      │
         │   NOT NULL)                          │
         └──────────────────────────────────────┘


┌─────────────────────────┐
│    visa_subclasses       │  ← Reference: visa types (NEW)
│─────────────────────────│
│ code (PK, text)          │  189, 190, 491, 485, 500, 482
│ name (text, NOT NULL)    │  "Skilled Independent visa"
│ family (text, NOT NULL)  │  skilled | family | student | temporary | humanitarian
│ permanence (text)        │  permanent | provisional | temporary
│ age_limit (text, null)   │  "Must be under 45"
│ work_rights_description  │
│ family_inclusion_rule    │
│ residency_requirement    │
│ occupation_list_required │
│   (bool)                 │
│ onward_pathway_code      │
│   (text, nullable)       │
│ points_test_required     │
│   (bool)                 │
│ base_application_cost    │
│   (int, nullable)        │
│ source_url (text)        │
│ retrieved_at (timestamptz)│
│ reliability_tier (text)  │  "official_curated"
└─────────────────────────┘
    │ 1
    │
    ├───< processing_times
    │    ┌──────────────────────────────────────┐
    │    │       processing_times                │
    │    │──────────────────────────────────────│
    │    │ id (PK, int)                         │
    │    │ visa_code (FK, NOT NULL)             │
    │    │ as_of_date (date, NOT NULL)           │
    │    │ median_days (int, NOT NULL)           │
    │    │ source_url (text)                    │
    │    │ retrieved_at (timestamptz)            │
    │    │ reliability_tier (text)              │  "official_scraped"
    │    └──────────────────────────────────────┘
    │
    └───< application_funnel
         ┌──────────────────────────────────────┐
         │      application_funnel               │
         │──────────────────────────────────────│
         │ id (PK, int)                         │
         │ visa_code (FK, NOT NULL)             │
         │ program_year (text, NOT NULL)         │  "2025-26"
         │ submitted_count (int, nullable)       │
         │ invited_count (int, nullable)         │
         │ granted_count (int, nullable)         │  ← weakest-sourced, may be NULL
         │ as_of_date (date, NOT NULL)           │
         │ source_url (text)                    │
         │ retrieved_at (timestamptz)            │
         │ reliability_tier (text)              │  "official_scraped" or "official_curated"
         └──────────────────────────────────────┘


┌─────────────────────────┐
│   assessing_bodies       │  ← Reference (NEW, curated)
│─────────────────────────│
│ body_name (PK, text)     │  "ACS", "ANMAC", "VETASSESS", "Engineers Australia"
│ turnaround_estimate (text)│
│ cost (text, nullable)    │
│ source_url (text)        │
│ retrieved_at (timestamptz)│
│ reliability_tier (text)  │  "official_curated"
└─────────────────────────┘


┌─────────────────────────┐
│   points_criteria_ref    │  ← Reference: points test (NEW)
│─────────────────────────│
│ id (PK, int)             │
│ criterion_name (text)    │  "Age", "English language ability", "Skilled employment"
│ band_description (text)  │  "At least 18 but less than 25 years"
│ points_value (int)       │  25, 30, 0, 5, 10, 15, 20
│ source_url (text)        │
│ retrieved_at (timestamptz)│
│ reliability_tier (text)  │  "official_scraped"
└─────────────────────────┘


┌─────────────────────────┐
│   english_test_bands     │  ← Reference (NEW)
│─────────────────────────│
│ id (PK, int)             │
│ test_name (text)         │  "IELTS", "PTE Academic", "TOEFL iBT", "CAE"
│ band_name (text)         │  "Superior", "Proficient", "Competent"
│ points_value (int)       │  20, 10, 0
│ source_url (text)        │
│ retrieved_at (timestamptz)│
│ reliability_tier (text)  │  "official_curated"
└─────────────────────────┘


┌─────────────────────────┐
│    list_change_log       │  ← Multi-purpose (NEW)
│─────────────────────────│
│ id (PK, int)             │
│ list_name (text)         │  "MLTSSL" | "STSOL" | "ROL" | "NSW" | "VIC" | ...
│ occupation_code (FK→     │
│   occupations.code)      │
│ change_type (text)       │  "added" | "removed"
│ effective_date (date)    │
│ source_url (text)        │
│ retrieved_at (timestamptz)│
│ reliability_tier (text)  │  "official_scraped" or "official_curated"
└─────────────────────────┘


┌─────────────────────────┐
│    program_allocation    │  ← Aggregate (NEW)
│─────────────────────────│
│ id (PK, int)             │
│ program_year (text)      │  "2025-26"
│ stream_name (text)       │  "Skill", "Family", "Other"
│ places (int, NOT NULL)   │
│ source_url (text)        │
│ retrieved_at (timestamptz)│
│ reliability_tier (text)  │  "official_curated"
└─────────────────────────┘


┌─────────────────────────┐
│    policy_events         │  ← Editorial annotations (NEW)
│─────────────────────────│
│ id (PK, int)             │
│ event_date (date)        │
│ visa_code (text, null)   │  NULL = national-level event
│ description (text)       │
│ source_url (text)        │
│ retrieved_at (timestamptz)│
│ reliability_tier (text)  │  "official_curated"
└─────────────────────────┘
```

### 5.2 Complete Field Reference

| Table | Field | Type | Nullable | Constraint | Description |
|---|---|---|---|---|---|
| `occupations` | `code` | text | PK | — | ANZSCO code (e.g., "261313") |
| `occupations` | `name` | text | NOT NULL | — | "Software Engineer" |
| `occupations` | `unit_group` | text | NOT NULL | — | "2613 Software and Applications Programmers" |
| `eoi_rounds` | `visa_code` | text | NOT NULL | — | "189", "190", "491" |
| `eoi_rounds` | `occupation_code` | text | nullable FK | — | NULL = visa-wide round (not occupation-scoped) |
| `eoi_rounds` | `round_date` | date | NOT NULL | UNIQUE(visa, occ, date) | When the round was held |
| `eoi_rounds` | `threshold_points` | int | NOT NULL | — | Minimum points to receive invitation |
| `eoi_rounds` | `invitations_issued` | int | nullable | — | NULL when not published per-occupation |
| `ceiling_usage` | `program_year` | text | NOT NULL | — | "2025-26" |
| `ceiling_usage` | `issued` | int | NOT NULL | CHECK(issued ≤ ceiling) | Invitations issued so far |
| `ceiling_usage` | `ceiling` | int | NOT NULL | CHECK(ceiling > 0) | Annual occupation cap |
| `visa_subclasses` | `family` | text | NOT NULL | enum | skilled, family, student, temporary, humanitarian |
| `visa_subclasses` | `permanence` | text | NOT NULL | enum | permanent, provisional, temporary |
| `visa_subclasses` | `points_test_required` | bool | NOT NULL | — | Is this a points-tested visa? |
| `state_nomination_status` | `status` | text | NOT NULL | enum | open, limited, closed |
| `state_nomination_status` | `documents_required` | jsonb | nullable | — | Array of strings; jsonb avoids join table for a display-only list |
| `occupation_momentum` | `direction` | text | NOT NULL | enum | rising, falling, steady |
| `processing_times` | `median_days` | int | NOT NULL | — | Median processing time |
| `list_change_log` | `list_name` | text | NOT NULL | — | "MLTSSL", "NSW", "VIC", etc. |
| `list_change_log` | `change_type` | text | NOT NULL | enum | added, removed |
| `program_allocation` | `stream_name` | text | NOT NULL | — | "Skill", "Family", "Other" |
| `application_funnel` | `granted_count` | int | nullable | — | Weakest-sourced — NULL where unconfirmed |

**Provenance columns on EVERY fact table:**

| Column | Type | Required | Description |
|---|---|---|---|
| `source_url` | text | NOT NULL (except derived tables) | Canonical URL the fact was extracted from |
| `retrieved_at` | timestamptz | NOT NULL (except derived tables) | When the source was fetched |
| `reliability_tier` | text | NOT NULL | official_scraped, official_curated, derived |

`occupation_momentum` is the only table that omits `source_url` — its `reliability_tier` is always `"derived"`.

### 5.3 Schema Migrations Plan

Each new table gets its own numbered Alembic migration:

```
alembic/versions/
  0001_create_source_pages.py          ✅ Done
  0002_create_occupations.py            ✅ Done
  0003_create_eoi_rounds.py             ✅ Done
  0004_create_ceiling_usage.py          ✅ Done
  0005_create_occupation_momentum.py    ✅ Done
  0006_eoi_rounds_dedup.py              ✅ Done (constraints)
  0007_create_visa_subclasses.py        ← NEXT
  0008_create_processing_times.py
  0009_create_state_nomination_status.py
  0010_create_list_change_log.py
  0011_create_program_allocation.py
  0012_create_application_funnel.py
  0013_create_points_criteria_ref.py
  0014_create_assessing_bodies.py
  0015_create_english_test_bands.py
  0016_create_policy_events.py
  0017_create_skills_priority.py
```

---

## 6. Pipeline Architecture: Extract → Validate → Transform → Load

### 6.1 The Full Pipeline Flow

```
                        ┌─────────────────────────────────────────────────┐
                        │              CLOUD RUN JOB (ETL)                 │
                        │                                                 │
                        │  ┌─────────────┐    ┌───────────────────────┐  │
                        │  │  ORCHESTRATOR │───▶│  per-source sync fn  │  │
                        │  │  (main.py)   │    │  (pipeline.py)        │  │
                        │  └─────────────┘    └──────────┬────────────┘  │
                        │                                │               │
                        │                    ┌───────────▼────────────┐  │
                        │                    │  1. EXTRACT (fetch.py)  │  │
                        │                    │  fetch_and_register()   │  │
                        │                    └───────────┬────────────┘  │
                        │                                │               │
                        │                    ┌───────────▼────────────┐  │
                        │                    │  2. HASH + WATERMARK   │  │
                        │                    │  commit content_hash   │  │
                        │                    │  + last_changed_at     │  │
                        │                    └───────────┬────────────┘  │
                        │                                │               │
                        │                    ┌───────────▼────────────┐  │
                        │                    │  3. DECIDE (pipeline)  │  │
                        │                    │  _needs_extraction()?  │  │
                        │                    └─────┬──────────┬───────┘  │
                        │                          │ NO       │ YES      │
                        │                          ▼          ▼          │
                        │                     ┌────────┐ ┌────────────┐ │
                        │                     │  SKIP  │ │ 4. TRANSFORM│ │
                        │                     └────────┘ │ (tier-based)│ │
                        │                                └─────┬──────┘ │
                        │                                      │        │
                        │                          ┌───────────▼──────┐ │
                        │                          │ 5. VALIDATE      │ │
                        │                          │ require_provenance│ │
                        │                          └─────┬────────────┘ │
                        │                                │              │
                        │                          ┌───────────▼──────┐ │
                        │                          │ 6. LOAD (merge)  │ │
                        │                          │ + dedup by key   │ │
                        │                          │ + commit         │ │
                        │                          └─────┬────────────┘ │
                        │                                │              │
                        │                          ┌───────────▼──────┐ │
                        │                          │ 7. DERIVE        │ │
                        │                          │ refresh_momentum │ │
                        │                          └─────┬────────────┘ │
                        │                                │              │
                        │                          ┌───────────▼──────┐ │
                        │                          │ 8. ADVANCE       │ │
                        │                          │ last_extracted_at│ │
                        │                          └──────────────────┘ │
                        └─────────────────────────────────────────────────┘
```

### 6.2 Stage-by-Stage Detail

**Stage 1 — Extract (`crawler/fetch.py`)**

```python
def fetch_and_register(session, *, url, domain, category, client=None):
    # HTTP GET with httpx, 15s timeout
    # SHA-256 hash of raw content bytes
    # Upsert into source_pages: content_hash, last_checked_at, last_changed_at
    # Returns (page, changed, text) — text reused by parser to avoid double-fetch
```

**Design note:** koshi currently fetches a page only if its URL is known. The `research/au-visa-sources` crawler does *discovery* (sitemap + key-path + link-following). koshi should adopt a two-phase discovery:

1. **Discovery phase (rare):** crawl sitemaps + key paths to find new pages → register in `source_pages`
2. **Extraction phase (frequent):** fetch known pages → hash → parse if changed

This separates "find new sources" (expensive, rare) from "re-check known sources" (cheap, frequent). Today koshi only does phase 2 with hardcoded URLs.

**Stage 2 — Hash + Watermark**

```python
# Two watermarks, two different meanings:
# last_changed_at    — "the page content changed" (set by fetcher, before parse)
# last_extracted_at  — "we successfully parsed AND persisted it" (set by pipeline, after load)
```

This is the critical anti-freeze mechanism: a page that fails parsing retains a stale `last_extracted_at`, so `_needs_extraction()` returns True on every run, retrying until parse succeeds.

**Stage 3 — Decide**

```python
def _needs_extraction(page: SourcePage) -> bool:
    watermark = page.last_extracted_at or _NEVER_EXTRACTED
    return page.last_changed_at > watermark
```

**Stage 4 — Transform (tier-dispatch)**

```python
def sync_source(session, *, source_spec):
    page, changed, text = fetch_and_register(...)
    if not _needs_extraction(page):
        return []

    # Dispatch to the right tier based on source_spec.tier
    if source_spec.tier == "deterministic":
        rows = source_spec.parser(text, source_url=..., retrieved_at=...)
    elif source_spec.tier == "pdf":
        rows = extract_from_pdf(page_bytes, ...)
    elif source_spec.tier == "claude":
        rows = extract_with_claude(text, ...)
    else:  # curated
        rows = load_curated_seed(...)

    return rows
```

**Stage 5 — Validate (provenance gate)**

```python
def require_provenance(*, reliability_tier, source_url, retrieved_at):
    # Reject invalid tier values
    # Reject non-derived rows without source_url
    # Reject non-derived rows without retrieved_at
    # Reject future-dated retrieved_at
```

This is the invariant that makes "no row ships without a source" enforceable.

**Stage 6 — Load (dedup + merge)**

```python
# Dedup within the batch (critical for messy gov HTML tables):
staged_keys = set()
for row in rows:
    key = row.natural_key()
    if key in staged_keys:
        continue
    existing = session.scalar(select(Model).where(natural_key_match))
    if existing is not None:
        continue
    session.add(row)
    staged_keys.add(key)
session.commit()
```

**Stage 7 — Derive (computed facts)**

After loading new EOI rounds, recompute momentum for every touched occupation:

```python
new_codes = {r.occupation_code for r in new_rounds if r.occupation_code}
for code in new_codes:
    refresh_momentum(session, code)
```

**Stage 8 — Advance watermark**

Only after parse AND persist both succeed:

```python
page.last_extracted_at = datetime.now(timezone.utc)
session.commit()
```

### 6.3 The `pipeline.py` Orchestration Contract

Every source gets a `sync_<source>()` function in `pipeline.py` that follows the same contract:

| Contract | Rule |
|---|---|
| **Return type** | `list[Model]` — the rows persisted |
| **Empty return** | Never an error — means "no new data" or "no extraction needed" |
| **Raises on parse failure** | Propagates to caller; `last_extracted_at` NOT advanced |
| **Self-contained** | Each sync fn is independently runnable — a single source can be run alone |

---

## 7. Fault Tolerance & Resilience Design

### 7.1 Failure Modes and Recovery

| Failure Mode | Where | Current Behavior | Target Behavior |
|---|---|---|---|
| **Network timeout** | fetch.py | `httpx` raises; sync fn crashes | Retry with exponential backoff (2-3 attempts); log to DLQ |
| **HTTP 4xx/5xx** | fetch.py | `raise_for_status()` raises | Retry on 5xx; record `status='dead'` on 404/410; skip on other 4xx |
| **CDN block (403)** | fetch.py | No handling in koshi | UA rotation + retry (au-visa-sources already does this — port it) |
| **Parse failure** | extraction/*.py | Raises; `last_extracted_at` not advanced → auto-retry next run | Same + write raw HTML to GCS DLQ + send alert after N consecutive failures |
| **Malformed row** | pipeline.py | `require_provenance` raises; whole batch aborts | Per-row validation: log + skip bad row, persist good rows |
| **DB unavailable** | db.py | Connection error crashes | Retry with backoff; alert; job exits non-zero for Cloud Run to retry |
| **Duplicate rows** | pipeline.py | `staged_keys` + DB existence check + unique constraint | Already solid — keep as is |
| **Source deleted (404)** | fetch.py | `raise_for_status()` crashes | Mark `status='dead'`, log, continue other sources |

### 7.2 Dead Letter Queue (DLQ) Design

When extraction fails after retries, the raw content must be preserved for later replay:

```
GCS bucket: koshi-dlq/
  ├── 2026-08-15/
  │   ├── immi-invitation-rounds-14-32-05.html    ← raw HTML
  │   ├── planning-levels-report.html             ← raw PDF bytes
  │   └── manifest.json                          ← failure metadata
```

```json
// manifest.json — one entry per failure
{
  "url": "https://immi.homeaffairs.gov.au/...",
  "fetched_at": "2026-08-15T14:32:05Z",
  "error": "ExtractionError: round-results table not found",
  "tier": "deterministic",
  "retry_count": 3,
  "content_hash": "abc123...",
  "storage_path": "2026-08-15/immi-invitation-rounds-14-32-05.html"
}
```

**Replay:** a manual CLI command (`python -m koshi replay --manifest manifest.json`) re-runs extraction against the stored raw content, with a fresh LLM or updated parser.

### 7.3 Retry Policy

```python
# crawler/fetch.py — enhanced retry
def fetch_with_retry(url, *, max_attempts=3, backoff_base=2.0):
    for attempt in range(max_attempts):
        try:
            resp = httpx.get(url, timeout=15.0)
            if resp.status_code in (500, 502, 503, 504):
                raise TransientError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp
        except TransientError as e:
            if attempt == max_attempts - 1:
                raise
            time.sleep(backoff_base ** attempt)  # 2s, 4s
        except httpx.TimeoutException as e:
            if attempt == max_attempts - 1:
                raise
            time.sleep(backoff_base ** attempt)
    raise PermanentError(f"failed after {max_attempts} attempts")
```

**Key principle:** retry only transient failures (network, 5xx, timeout). Never retry permanent failures (404, 400, parse errors that will fail identically next time). For parse errors, the watermark already handles retry-on-next-run semantics — don't hammer a broken parser in a tight loop.

### 7.4 Alerting

| Signal | Threshold | Channel |
|---|---|---|
| Parse failure | 3 consecutive runs fail on same source | Discord (#job_market or a dedicated #koshi-alerts) |
| Source dead | `status='dead'` detected | Discord |
| Freshness breach | Source not re-crawled within expected cadence × 2 | Discord + dashboard |
| Job crash | Cloud Run Job exits non-zero | Cloud Monitoring → Discord |

### 7.5 Idempotency Guarantee

Every sync function is safe to run any number of times:

1. **Content hash** — unchanged page → `_needs_extraction` returns False → no-op
2. **Natural key unique constraint** — re-parsed same data → DB rejects duplicates
3. **`staged_keys`** — in-batch dedup prevents UniqueViolation rollback
4. **`merge()` for reference tables** — occupations upsert by primary key

This means the entire pipeline can be re-run from scratch safely, and a Cloud Run Job can be retried without side effects.

---

## 8. Ingestion Orchestration & Scheduling

### 8.1 Two-Phase Schedule Model

Different sources need different cadences. koshi should NOT run everything on one daily cron — it should group sources by cadence:

| Cadence | Sources | Trigger |
|---|---|---|
| **Nightly** | EOI rounds (#2), processing times (#8), momentum (derived) | Cloud Scheduler → Cloud Run Job, 03:00 AEST |
| **Weekly** | Visa fees (#4), visa subclass facts (#6), state lists (#12) | Every Monday 03:00 |
| **Monthly** | Ceilings (#3), points test (#5), health/English (#7), application funnel (#15) | 1st of month 03:00 |
| **Quarterly** | Legislation lists (#9), skills priority (#10) | 1st Jan/Apr/Jul/Oct |
| **Annual** | Application funnel granted (#16), assessing bodies (#13) | 1st July (program year start) |
| **On-demand** | Policy events (#14) — manually triggered when a policy change happens | Manual `python -m koshi --source policy_events` |

### 8.2 Cloud Run Jobs Architecture

```
Cloud Scheduler (cron)
    │
    ├── "nightly"   → Cloud Run Job "koshi-sync-nightly"
    ├── "weekly"    → Cloud Run Job "koshi-sync-weekly"
    ├── "monthly"   → Cloud Run Job "koshi-sync-monthly"
    └── "quarterly" → Cloud Run Job "koshi-sync-quarterly"
```

Each job runs `python -m koshi --group <group>` which syncs only that group's sources.

```python
# __main__.py — enhanced with group selection
GROUPS = {
    "nightly": ["skillselect_rounds", "processing_times"],
    "weekly": ["visa_fees", "visa_subclass_facts", "state_list_changes"],
    "monthly": ["ceiling_usage", "points_test", "english_bands", "application_funnel"],
    "quarterly": ["legislation_lists", "skills_priority"],
    "annual": ["funnel_granted", "assessing_bodies"],
}

def main(group: str | None = None):
    sources = GROUPS[group] if group else ALL_SOURCES
    for source in sources:
        sync_source(source)
        # momentum refresh is triggered inside sync_skillselect_rounds
```

### 8.3 Why Cloud Run Jobs, Not Airflow

| Concern | Cloud Run Jobs | Airflow/Prefect |
|---|---|---|
| **Setup** | `gcloud run jobs deploy` — 1 command | K8s/VM cluster, DB, web UI, workers |
| **Ops burden** | None (serverless) | Scheduler to monitor, upgrade, scale |
| **Cost** | Pay per job run (seconds) | Always-on scheduler node (~$50+/month) |
| **Scale** | 16 sources, <1M rows — trivial | Overkill |
| **Scheduling** | Cloud Scheduler (cron) | Built-in, more flexible |
| **Retries** | Native (max-retries on job) | Native |
| **Logging** | Cloud Logging | Web UI |

For koshi's scale, Cloud Run Jobs + Cloud Scheduler is dramatically simpler and cheaper. Airflow earns its complexity only when you have hundreds of interdependent DAGs — koshi has 16 independent sources.

---

## 9. Serving Layer: API Design & Caching

### 9.1 Endpoint Inventory (Target)

| Endpoint | Returns | Source Tables | Status |
|---|---|---|---|
| `GET /v1/healthz` | liveness | — | ✅ Done |
| `GET /v1/occupations` | list + momentum | occupations, occupation_momentum | ✅ Done |
| `GET /v1/occupations/{code}` | full profile | occupations, ceiling_usage, eoi_rounds, occupation_momentum | ✅ Done |
| `GET /v1/visas` | visa subclass list | visa_subclasses | ❌ |
| `GET /v1/visas/{code}` | visa detail + processing times | visa_subclasses, processing_times | ❌ |
| `GET /v1/states` | state nomination summary | state_nomination_status | ❌ |
| `GET /v1/states/{state}` | state detail + occupation list | state_nomination_status | ❌ |
| `GET /v1/national/summary` | program allocation, funnel | program_allocation, application_funnel | ❌ |
| `GET /v1/reference/points-test` | points criteria | points_criteria_reference | ❌ |
| `GET /v1/reference/english-tests` | English test bands | english_test_bands | ❌ |
| `GET /v1/reference/assessing-bodies` | assessing bodies | assessing_bodies | ❌ |

### 9.2 Response Contract (SourcedFact / DerivedFact)

Every response distinguishes fact confidence via two Pydantic shapes:

```jsonc
// SourcedFact — scraped or curated from a real page
{
  "value": 3200,
  "reliability_tier": "official_curated",   // or "official_scraped"
  "retrieved_at": "2026-08-01T00:00:00+00:00",
  "source_url": "https://immi.homeaffairs.gov.au/what-we-do/migration-program-planning-levels"
}

// DerivedFact — computed internally, no external source
{
  "value": "rising",
  "reliability_tier": "derived",
  "computed_at": "2026-08-15T09:12:03+00:00"
  // no source_url
}
```

This is the key design decision that lets the frontend render `official_curated` differently from `official_scraped` differently from `derived`. It's already implemented and should be extended to all new endpoints.

### 9.3 Caching Strategy

| Layer | What | TTL | Rationale |
|---|---|---|---|
| **API response cache** | Read endpoint responses | 5-10 min | Data changes monthly; 10-min cache serves >99% of reads without hitting DB |
| **DB connection pool** | SQLAlchemy pool | — | Default pooling; 10-20 connections for API |
| **CDN / edge cache** | Static reference data (points test, English bands) | 24h | Near-static reference tables change at most annually |
| **No application cache** | — | — | Don't add Redis yet — Postgres is fast enough at this scale |

**Implementation:** use `fastapi-cache2` (in-memory) or Cloud CDN for static reference endpoints. Don't over-engineer — a 5-minute in-process cache is sufficient at MVP scale.

### 9.4 The "Apply Logic to Best Present" Layer

The user asked "how to apply logic to this data to best present." This is where koshi's serving layer adds value beyond raw ETL:

**Deterministic insights (already implemented — `insights.py`):**

```python
def generate_ceiling_insight(*, issued, ceiling, direction):
    places_left = ceiling - issued
    pct_used = round(issued / ceiling * 100)
    base = f"{pct_used}% of this occupation's ceiling has been issued..."
    if direction:
        base += f" The points threshold has been {direction} over the last three rounds."
    return base
```

**Rules for the presentation layer:**

1. **Only state published facts** — never "you should/can/are eligible." Phrase-ban tests enforce this.
2. **Never fabricate a trend** — if <3 rounds exist, omit the trend sentence entirely, don't say "steady."
3. **Compare at query time, don't store comparisons** — "pace vs last year" is computed in the API from `ceiling_usage` rows at two `as_of_date` snapshots, not stored as a derived fact.
4. **Momentum is the only derived fact** — trailing-3-round threshold delta. Everything else is either sourced or computed-at-query-time.
5. **NULL is honest** — `granted_count = NULL` where unconfirmed, `momentum = null` when <3 rounds. The frontend renders "not published" rather than a fake number.

---

## 10. Infrastructure & Deployment

### 10.1 Target GCP Architecture

```
                        ┌─────────────────────────────────────────────┐
                        │              Google Cloud (GCP)              │
                        │                                             │
  Cloud Scheduler ──────▶│  Cloud Run Job (ETL)                       │
  (cron triggers)       │    python -m koshi --group nightly          │
                        │    python -m koshi --group weekly           │
                        │    python -m koshi --group monthly          │
                        │         │                                   │
                        │         ▼                                   │
                        │  Cloud SQL (Postgres)                       │
                        │    koshi database                           │
                        │         ▲                                   │
                        │         │                                   │
  lukla (Next.js) ──────▶│  Cloud Run Service (API)                  │
  (Cloud Run IAM)       │    uvicorn koshi.main:app                   │
                        │         │                                   │
                        │         ▼                                   │
                        │  GCS (koshi-dlq) — dead letter bucket       │
                        └─────────────────────────────────────────────┘
```

### 10.2 Resource Specs

| Resource | Type | Spec | Monthly Cost (est.) |
|---|---|---|---|
| **Cloud Run Job (ETL)** | serverless job | 1 vCPU, 2GB, timeout 30min | ~$0 (runs minutes/month) |
| **Cloud Run Service (API)** | serverless | 1 vCPU, 512MB, min-instances 0 | ~$0-5 (spiky traffic) |
| **Cloud SQL Postgres** | managed | shared instance with saathi/thamel/manaslu | ~$25-50 (shared) |
| **GCS DLQ bucket** | object storage | standard, ~1GB | ~$0.02 |
| **Cloud Scheduler** | cron | 5-6 schedules | Free tier |
| **Claude API** | extraction fallback | Haiku, ~10 calls/month | <$0.10 |

**Total marginal cost of koshi: <$10/month** (Cloud SQL is shared with the other Saathi services).

### 10.3 Deployment Model

| Env | Deploy Mechanism | Notes |
|---|---|---|
| **Local** | Docker Compose (Postgres) + `alembic upgrade head` + `python -m koshi` | Already working |
| **CI/CD** | GitHub Actions + Workload Identity Federation → Cloud Run | Same pattern as `karki-labs-infra` |
| **Staging** | Separate Cloud Run project | Before merging to main |
| **Prod** | Cloud Run with IAM invoker restriction | Only lukla's service account can call the API |

**Key rule (from karki-labs-infra):** Cloud Run, NOT GKE. GitHub Actions + WIF, NOT Cloud Build. Don't reach for Terraform until local setup is solid end-to-end.

### 10.4 Auth Model

koshi has NO end-user identity — the data is public. In production:

- **API auth:** Cloud Run IAM invoker — only `lukla`'s service account is granted `roles/run.invoker`
- **No JWT, no API key, no OAuth** — the service account identity IS the auth
- **This is deliberate** — koshi is a public-data read API, identical for every caller

---

## 11. Implementation Roadmap

### Phase 0: Foundation (Already Done ✅)

- Repo scaffold, SQLAlchemy models, Alembic migrations
- Provenance validation gate
- Extraction watermark pattern
- Occupation vertical slice (2 sources + momentum + 2 endpoints)
- Full test suite (18 test files, real Postgres, mocked HTTP)

### Phase 1: Tier-1 Parsers (Fastest Wins — deterministic tables)

| Task | Source | Table | Effort | Depends On |
|---|---|---|---|---|
| 1.1 | Visa fees | `visa_subclasses.base_application_cost` (partial) | 0.5d | visa_subclasses table |
| 1.2 | Processing times | `processing_times` | 0.5d | visa_subclasses table |
| 1.3 | Points test | `points_criteria_reference` | 0.5d | — |
| 1.4 | Application funnel | `application_funnel` | 0.5d | — |
| 1.5 | Skills priority | `skills_priority` | 0.5d | — |

**Exit criteria:** All Tier-1 sources have parsers + fixtures + tests. All populate `official_scraped` tier.

### Phase 2: Reference Tables + Curated Seeds (Tier 4)

| Task | Source | Table | Effort | Depends On |
|---|---|---|---|---|
| 2.1 | Visa subclass facts | `visa_subclasses` (full) | 1d | — |
| 2.2 | State nomination | `state_nomination_status` + seed | 2d | occupations table |
| 2.3 | Assessing bodies | `assessing_bodies` + join | 1d | occupations table |
| 2.4 | Policy events | `policy_events` + seed | 0.5d | — |
| 2.5 | English test bands | `english_test_bands` + seed | 0.5d | — |
| 2.6 | Legislation lists | `list_change_log` | 1d | — |

**Exit criteria:** All curated seeds ship with review cadence + staleness alert.

### Phase 3: LLM + PDF Extraction (Tiers 2-3)

| Task | Source | Table | Effort | Depends On |
|---|---|---|---|---|
| 3.1 | Claude extraction module | shared `claude_extractor.py` | 1d | Anthropic API key |
| 3.2 | Visa subclass facts via Claude | `visa_subclasses` | 0.5d | 3.1 |
| 3.3 | English requirements via Claude | `english_test_bands` | 0.5d | 3.1 |
| 3.4 | PDF extraction module | shared `pdf_extractor.py` | 1d | marker-pdf + Claude |
| 3.5 | Ceilings PDF extraction | `ceiling_usage` (full) | 1d | 3.4 |

**Exit criteria:** All Tier-2/3 sources extract with `official_curated` tier, with curated-seed fallback.

### Phase 4: Orchestration + Fault Tolerance

| Task | Component | Effort | Depends On |
|---|---|---|---|
| 4.1 | Group-based sync (`--group nightly`) | 0.5d | Phase 1-3 |
| 4.2 | Retry with backoff | 0.5d | — |
| 4.3 | CDN-block handling (UA rotation) | 0.5d | port from au-visa-sources |
| 4.4 | DLQ (GCS) + replay command | 1d | — |
| 4.5 | Freshness monitoring + alerts | 1d | — |

**Exit criteria:** Any source can fail independently without blocking others. Failures are visible and replayable.

### Phase 5: API Expansion + Caching

| Task | Endpoint | Effort | Depends On |
|---|---|---|---|
| 5.1 | `/v1/visas`, `/v1/visas/{code}` | 1d | Phase 2.1 |
| 5.2 | `/v1/states`, `/v1/states/{state}` | 1d | Phase 2.2 |
| 5.3 | `/v1/national/summary` | 0.5d | Phase 1.4, 2.4 |
| 5.4 | `/v1/reference/*` | 0.5d | Phase 1.3, 2.5, 2.3 |
| 5.5 | Response caching | 0.5d | — |

**Exit criteria:** All 6+ endpoint families live, with SourcedFact/DerivedFact contract everywhere.

### Phase 6: Deployment

| Task | Component | Effort | Depends On |
|---|---|---|---|
| 6.1 | Cloud Run Job deploy | 1d | Phase 4 |
| 6.2 | Cloud Run Service deploy + IAM | 0.5d | Phase 5 |
| 6.3 | Cloud Scheduler schedules | 0.5d | 6.1 |
| 6.4 | Cloud SQL provision + migration | 0.5d | — |
| 6.5 | GitHub Actions CI/CD + WIF | 1d | 6.1-6.4 |

**Total effort: ~20 developer-days** for the full system (excluding the already-done Phase 0).

---

## 12. Appendix: Technology Comparisons

### 12.1 LLM Extraction Cost Comparison

| Model | Per-1K input tokens | Per-1K output tokens | Suitability |
|---|---|---|---|
| **Claude Haiku 4** | $0.001 | $0.005 | ✅ Best for prose extraction (fast, cheap) |
| **Claude Sonnet 4** | $0.003 | $0.015 | PDF vision extraction, complex reasoning |
| **Claude Opus 4** | $0.015 | $0.075 | ❌ Overkill — never needed for extraction |
| **GPT-4o-mini** | $0.00015 | $0.0006 | ⚠️ Cheapest, but weaker structured output |
| **GPT-4o** | $0.0025 | $0.010 | ⚠️ Comparable to Sonnet, no vision advantage |

**Recommendation:** Haiku for Tier-3 prose extraction; Sonnet for Tier-2 PDF vision. Never Opus.

### 12.2 PDF Extraction Comparison

| Tool | Cost | Quality | Setup | Verdict |
|---|---|---|---|---|
| **marker-pdf** | Free (local) | Good for clean PDFs | `pip install marker-pdf` | ✅ First attempt |
| **LlamaParse** | ~$0.003/page | Excellent for tables | API key | ⚠️ If marker fails |
| **Claude vision** | ~$0.01/page | Excellent, handles complex layouts | Anthropic API | ✅ Fallback |
| **pypdf** | Free | Text only, loses tables | `pip install pypdf` | ❌ Not for tables |
| **Camelot** | Free | Good for bordered tables | `pip install camelot-py` | ⚠️ For specific table layouts |

### 12.3 Why Not These Tools

| Tool | Why Rejected |
|---|---|
| **Airbyte / Fivetran** | Built for SaaS API connectors, not bespoke gov HTML scraping. koshi's 16 sources are too custom. |
| **dbt** | Transform layer, not extraction. koshi's hard part is extraction. dbt could be added later for analytics, not needed now. |
| **Kafka** | Streaming, but koshi's data is batch (monthly/annual updates). Batch ETL is the right abstraction. |
| **MongoDB** | Document store, but koshi's data is relational (occupations → rounds → momentum). Postgres with FK constraints is the right fit. |
| **Redis** | Caching layer, but not needed at <1M rows. In-process caching suffices. |
| **Elasticsearch** | Search engine, but koshi's API is structured lookups, not full-text search. |

---

## Document History

| Date | Change |
|---|---|
| 2026-08-15 | Initial comprehensive ETL architecture written. Covers: industry survey, full 16-source catalog, 4-tier extraction strategy, complete data model (15+ tables), 8-stage pipeline flow, fault tolerance (DLQ, retry, alerting), group-based scheduling, serving layer with SourcedFact/DerivedFact contract, GCP deployment, and 6-phase roadmap. |

