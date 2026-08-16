# Koshi: Web Data Acquisition & Normalization Platform (Final Architecture)

## Executive Summary

Koshi is a **domain-agnostic ingestion and data-quality engine with domain-specific contracts and normalization**. It acquires structured data from web sources (APIs, HTML, PDFs, files), validates it against contracts, and serves it via a clean API. It uses managed extraction services (Firecrawl/Apify/Zyte) selectively for complex cases while prioritizing deterministic extraction for simple sources. [use-apify](https://use-apify.com/blog/firecrawl-comprehensive-guide)

### Key Design Decisions (Updated)

| Decision | Rationale |
|---|---|
| **Separate acquisition from extraction** | Raw snapshots must capture the original source artifact before any processing for true replayability |
| **Deterministic-first extraction** | Use cheapest mechanism (httpx + BS4) for simple HTML; managed providers only when needed |
| **Quality-aware provider fallback** | Don't accept extraction just because `success=True`; validate against quality gates before trying next provider |
| **Control plane + data plane** | Separate "what should happen" (control) from "what needs to happen" (execution) |
| **Source → Resource → Snapshot model** | One source may have multiple resources (URL, PDF, API); each resource has independent snapshots |
| **Generic execution model** | Unified `pipeline_run` with child tasks (acquisition, extraction, validation, quality, publication) for lineage |
| **Severity-based quality** | INFO, WARNING, ERROR, BLOCKER levels with configurable publication policies |
| **Dataset-specific quality rules** | Each source defines its own expected record counts, required fields, uniqueness constraints |
| **Semantic drift detection** | Use LLM to detect when source meaning changes, not just schema changes  [computer](https://www.computer.org/csdl/journal/oj/2026/01/11399888/2eePsqyP74A) |
| **Three vertical slices** | Build 3 representative slices (easy HTML, difficult JS/PDF, semantic LLM) instead of all 18 contracts upfront |

***

## Architecture Overview

```text
                         ┌─────────────────────┐
                         │    CONTROL PLANE    │
                         │                     │
                         │ Source Registry     │
                         │ Contracts           │
                         │ Schedules            │
                         │ Quality Policies    │
                         │ Provider Policies   │
                         │ Release Management  │
                         └──────────┬──────────┘
                                    │
                                    ▼
┌──────────────┐          ┌──────────────────┐
│    SOURCE    │─────────►│   ACQUISITION    │
│              │          │                  │
│ API          │          │ HTTP             │
│ HTML         │          │ Browser          │
│ PDF          │          │ API clients      │
│ Files        │          │ Managed fetch    │
└──────────────┘          └────────┬─────────┘
                                   │
                                   ▼
                         ┌──────────────────┐
                         │  BRONZE / RAW    │
                         │                  │
                         │ Immutable        │
                         │ Content hash     │
                         │ Headers          │
                         │ Request          │
                         │ Manifest         │
                         │ Screenshot       │
                         └────────┬─────────┘
                                  │
                                  ▼
                       ┌─────────────────────┐
                       │     EXTRACTION      │
                       │                     │
                       │ HTML parser         │
                       │ PDF parser          │
                       │ API parser          │
                       │ Firecrawl           │
                       │ Apify               │
                       │ LLM                 │
                       └─────────┬───────────┘
                                 │
                                 ▼
                       ┌─────────────────────┐
                       │ CANONICAL CONTRACT  │
                       │ Pydantic + version  │
                       └─────────┬───────────┘
                                 │
                                 ▼
                       ┌─────────────────────┐
                       │   QUALITY ENGINE    │
                       │                     │
                       │ Schema              │
                       │ Completeness        │
                       │ Business rules      │
                       │ Anomaly detection   │
                       │ Semantic drift      │
                       └─────────┬───────────┘
                                 │
                       ┌─────────┴─────────┐
                       ▼                   ▼
                    QUARANTINE            SILVER
                                          │
                                          ▼
                                    NORMALIZATION
                                          │
                                          ▼
                                        GOLD
                                          │
                              ┌───────────┴──────────┐
                              ▼                      ▼
                         PostgreSQL              Parquet
                              │                      │
                              ▼                      ▼
                           RELEASE              Analytics
                              │
                              ▼
                           FastAPI
```

***

## Component Breakdown

### 1. Control Plane

**Purpose**: Define what should happen (configuration, policies, schedules).

**Tables**:
```sql
CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    domain TEXT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

CREATE TABLE resources (
    resource_id TEXT PRIMARY KEY,
    source_id TEXT REFERENCES sources(source_id),
    resource_type TEXT,  -- "url" | "pdf" | "api" | "file"
    locator JSONB,       -- {url: "...", method: "GET", headers: {...}}
    acquisition_strategy TEXT,  -- "http" | "browser" | "api_client" | "managed"
    created_at TIMESTAMPTZ
);

CREATE TABLE extraction_strategies (
    strategy_id TEXT PRIMARY KEY,
    strategy_type TEXT,  -- "html_table" | "pdf_parser" | "semantic_extraction"
    provider TEXT,       -- "custom" | "firecrawl" | "apify" | "zyte"
    config JSONB,        -- schema, prompt, selector
    created_at TIMESTAMPTZ
);

CREATE TABLE contracts (
    contract_id TEXT PRIMARY KEY,
    name TEXT,  -- "VisaFeeRecord"
    version TEXT,  -- "v1"
    schema JSONB,  -- Pydantic schema as JSON
    domain TEXT,  -- "visa" | "nepal_earth"
    created_at TIMESTAMPTZ
);

CREATE TABLE quality_policies (
    policy_id TEXT PRIMARY KEY,
    contract_id TEXT REFERENCES contracts(contract_id),
    expected_min_records INT,
    expected_max_records INT,
    max_change_percent DECIMAL,
    required_fields TEXT[],
    uniqueness_fields TEXT[],
    block_on TEXT[],  -- ["schema_error", "required_field_missing", ...]
    created_at TIMESTAMPTZ
);

CREATE TABLE schedules (
    schedule_id TEXT PRIMARY KEY,
    source_id TEXT REFERENCES sources(source_id),
    cadence TEXT,  -- "daily" | "weekly" | "monthly"
    freshness_sla INTERVAL,
    priority INT,  -- 1-10
    enabled BOOLEAN DEFAULT true
);
```

### 2. Data Plane

**Purpose**: Execute what needs to happen (acquisition, extraction, validation, publication).

#### 2.1 Acquisition Layer

**Key insight**: Acquisition is separate from extraction. Capture the raw source artifact before any processing.

**Strategies**:
- **HTTP**: `httpx` for HTML, PDF, JSON APIs.
- **Browser**: Playwright for JS-rendered pages.
- **API client**: Specialized clients (e.g., government API SDKs).
- **Managed fetch**: Zyte API for blocked/anti-bot sites.

**Raw snapshot structure**:
```text
gs://koshi-raw/
  source_id=homeaffairs-visa-fees/
  resource_id=/visa-fees/
  retrieved_date=2026-08-16/
  content_hash=abc123/
    request.json          # {method, url, headers, body}
    response.html         # or response.json, response.pdf
    response.json         # parsed JSON if applicable
    headers.json          # HTTP response headers
    screenshot.png        # optional, for browser acquisition
    manifest.json         # metadata
    extraction_result.json  # populated after extraction
```

**Manifest schema**:
```json
{
  "source_id": "homeaffairs-visa-fees",
  "resource_id": "/visa-fees",
  "retrieved_at": "2026-08-16T03:00:00Z",
  "acquisition_strategy": "http",
  "http_status": 200,
  "content_type": "text/html",
  "content_hash": "sha256:abc123...",
  "etag": "\"xyz789\"",
  "last_modified": "2026-08-15T12:00:00Z",
  "request_id": "req_abc123",
  "acquisition_duration_ms": 1234
}
```

**Why this matters**:
- Replay any extraction without re-acquiring.
- Compare providers on the same input.
- Debug extraction failures with full context.
- Audit published facts back to original source.

#### 2.2 Extraction Layer

**Strategies**:
- **HTML table parser**: `lxml`/BeautifulSoup for deterministic tables.
- **PDF parser**: `pdfplumber` or `marker-pdf`.
- **API parser**: JSON response → Pydantic model.
- **Firecrawl**: LLM-powered schema extraction for complex pages. [use-apify](https://use-apify.com/blog/firecrawl-comprehensive-guide)
- **Apify**: Actor-based extraction with custom logic. 
- **LLM**: Custom prompt + schema for unstructured text.

**Quality-aware fallback**:
```python
async def extract_with_quality_aware_fallback(
    resource: Resource,
    strategy: ExtractionStrategy,
    contract: Contract,
    quality_policy: QualityPolicy,
) -> ExtractionResult:
    providers = get_providers_for_strategy(strategy)
    
    for provider in providers:
        # Try extraction
        result = await provider.extract(resource, strategy.config)
        
        # Validate against contract
        if not validate_schema(result.records, contract.schema):
            continue
        
        # Run quality checks
        quality = await run_quality_checks(
            result.records,
            quality_policy,
            previous_snapshot=resource.last_snapshot,
        )
        
        if quality.status == "PASS":
            return result
        elif quality.status == "WARNING":
            # Accept with warnings logged
            log_warnings(quality.warnings)
            return result
        # If BLOCKER, try next provider
    
    raise ExtractionFailedError("All providers failed quality gates")
```

**Provider selection**:
```yaml
extraction_strategies:
  - strategy_id: homeaffairs-visa-fees-extract
    strategy_type: html_table
    provider: custom  # Try custom first
    
  - strategy_id: homeaffairs-visa-fees-extract-fallback
    strategy_type: semantic_extraction
    provider: firecrawl  # Fallback to Firecrawl if custom fails
```

**Cost optimization**:
- Custom HTML parser: ~$0 (your infra).
- Firecrawl: $0.05/verified extraction or credits + token subscription. [use-apify](https://use-apify.com/blog/firecrawl-comprehensive-guide)
- Apify: $0.05–$0.50/1K pages depending on Actor. 

Use managed providers only when deterministic extraction fails or is impractical.

#### 2.3 Canonical Contracts

**Purpose**: Decouple extraction from storage. Domain-agnostic engine, domain-specific contracts.

**Example**:
```python
class VisaFeeRecord(BaseModel):
    visa_code: str
    base_application_cost: Decimal
    effective_date: date
    source_url: str
    retrieved_at: datetime
    reliability_tier: Literal["official_scraped", "official_curated", "derived"]
    provider: str
    extraction_timestamp: datetime
    schema_version: str = "v1"

class TrekkingRouteRecord(BaseModel):
    route_id: str
    name: str
    region: str
    difficulty: Literal["easy", "moderate", "hard", "expert"]
    max_elevation_m: int
    duration_days: int
    source_url: str
    retrieved_at: datetime
    reliability_tier: Literal["official_scraped", "community_sourced"]
```

**Benefits**:
- Parser tests are independent of database schema.
- Multiple storage projections (Postgres, Parquet, BigQuery).
- Schema evolution without breaking extraction.
- Validation at the boundary (Pydantic rejects invalid data).

#### 2.4 Quality Engine

**Severity levels**:
- **INFO**: Minor anomalies, logged but not blocking.
- **WARNING**: Notable changes, may require review.
- **ERROR**: Significant issues, blocks publication unless overridden.
- **BLOCKER**: Critical failures, always blocks publication.

**Checks**:
- **Schema validation**: Pydantic model validation (BLOCKER if fails).
- **Row-count drift**: Compare against expected range (WARNING if >30%, BLOCKER if >80%).
- **Duplicate detection**: Natural key uniqueness (BLOCKER).
- **Required fields**: Ensure required fields present (BLOCKER if missing).
- **Enumerated values**: Ensure values in known vocabulary (ERROR if invalid).
- **Date plausibility**: `effective_date` not in the future (WARNING if future).
- **Cross-field consistency**: e.g., `base_application_cost > 0` (ERROR if negative).
- **Semantic drift**: LLM-based detection of meaning changes (WARNING or ERROR). [computer](https://www.computer.org/csdl/journal/oj/2026/01/11399888/2eePsqyP74A)

**Dataset-specific rules**:
```yaml
quality_policies:
  - contract_id: VisaFeeRecord
    expected_min_records: 10
    expected_max_records: 50
    max_change_percent: 30
    required_fields:
      - visa_code
      - base_application_cost
    uniqueness_fields:
      - visa_code
    block_on:
      - schema_error
      - required_field_missing
      - duplicate_primary_key

  - contract_id: EOIRoundRecord
    expected_min_records: 1
    expected_max_records: 10
    max_change_percent: 100  # EOI rounds can vary widely
    required_fields:
      - visa_code
      - occupation_code
      - round_date
    uniqueness_fields:
      - visa_code
      - occupation_code
      - round_date
```

**Semantic drift detection**:
```python
async def detect_semantic_drift(
    current_snapshot: Snapshot,
    previous_snapshot: Snapshot,
) -> SemanticDriftResult:
    # Use LLM to compare source text
    prompt = f"""
    Compare these two versions of a government policy page.
    Has the meaning changed materially (not just formatting)?
    
    Previous version:
    {previous_snapshot.text[:5000]}
    
    Current version:
    {current_snapshot.text[:5000]}
    
    Respond with JSON:
    {{
      "semantic_drift_detected": true/false,
      "summary": "...",
      "confidence": 0.0-1.0
    }}
    """
    
    response = await llm.generate(prompt, response_format="json")
    return SemanticDriftResult(**response)
```

**Publication gate**:
```python
if quality_result.status == "PASS":
    publish(canonical_records)
elif quality_result.status == "WARNING":
    publish(canonical_records)
    alert_team(quality_result.warnings)
elif quality_result.status == "BLOCKER":
    quarantine(quality_result.rejected_records)
    alert_team(quality_result.errors)
    # Optionally: publish previous known-good version
```

#### 2.5 Generic Execution Model

**Table**: `pipeline_runs`

```sql
CREATE TABLE pipeline_runs (
    run_id UUID PRIMARY KEY,
    parent_run_id UUID REFERENCES pipeline_runs(run_id),  -- for nested tasks
    run_type TEXT,  -- "acquisition" | "extraction" | "validation" | "quality" | "publication"
    source_id TEXT,
    resource_id TEXT,
    status TEXT,  -- "pending" | "running" | "success" | "failure" | "blocked"
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    input JSONB,  -- serialized input
    output JSONB,  -- serialized output
    error TEXT,
    metadata JSONB
);
```

**Benefits**:
- Unified lineage across all stages.
- Easy to trace a record back to its acquisition and extraction.
- Supports nested tasks (e.g., extraction run has child validation runs).
- Enables replay of specific stages.

#### 2.6 Versioned Releases

**Table**: `dataset_releases`

```sql
CREATE TABLE dataset_releases (
    release_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ,
    status TEXT,  -- "complete" | "partial" | "degraded"
    contract_id TEXT,
    pipeline_run_ids UUID[],
    metadata JSONB,
    is_current BOOLEAN DEFAULT false
);
```

**Release workflow**:
```text
raw → validated → candidate release → quality gates → published release
```

**API response**:
```json
{
  "data": [...],
  "metadata": {
    "release_id": "2026-08-16T03:00:00Z",
    "status": "complete",
    "contract_id": "VisaFeeRecord",
    "source_last_updated": "2026-08-10T00:00:00Z",
    "freshness": "current",
    "partial": false
  }
}
```

**Rollback**:
```sql
UPDATE dataset_releases
SET is_current = false
WHERE contract_id = 'VisaFeeRecord' AND is_current = true;

UPDATE dataset_releases
SET is_current = true
WHERE release_id = 'previous_release_id';
```

***

## Implementation Roadmap (Updated)

### Phase 0: Provider Bake-Off (1 week)

**Goal**: Test Firecrawl, Apify, and custom extraction on 10 known URLs.

**Test criteria**:
- Accuracy (schema compliance, field correctness). [use-apify](https://use-apify.com/blog/firecrawl-comprehensive-guide)
- Cost per 1K pages.
- Latency (time to extract).
- Failure rate (timeouts, blocks).
- Schema consistency (same output across runs).

**Test plan**:
```python
urls = [
    "https://homeaffairs.gov.au/visa-fees",
    "https://jobsandskills.gov.au/occupation-list",
    # ... 8 more
]

schema = {
    "type": "object",
    "properties": {
        "visa_code": {"type": "string"},
        "base_application_cost": {"type": "number"},
    }
}

for provider in ["custom", "firecrawl", "apify"]:
    results = await provider.extract(urls, schema)
    log_accuracy(results)
    log_cost(results)
    log_latency(results)
    log_failure_rate(results)
```

**Decision**: Choose primary and fallback providers based on results.

### Phase 1: Control Plane + Raw Snapshots (1.5 weeks)

**Goal**: Build source registry, contracts, and immutable snapshot storage.

**Tasks**:
- Create GCS bucket `koshi-raw/`.
- Implement `acquire_and_store_snapshot()` function.
- Persist manifest metadata in Postgres.
- Add replay from local snapshot (no network call).
- Add conditional requests (ETag/Last-Modified).
- Build control plane tables (sources, resources, contracts, schedules).

**Deliverable**: Can acquire any source and store raw response immutably.

### Phase 2: Three Vertical Slices (2 weeks)

**Goal**: Build 3 representative end-to-end slices instead of all 18 contracts.

**Slice A — Easy (HTML table)**:
- Source: ANZSCO occupations.
- Acquisition: `httpx`.
- Extraction: `lxml`/BeautifulSoup.
- Contract: `OccupationRecord`.
- Quality: Schema validation, row-count checks.
- Storage: Postgres.

**Slice B — Difficult (JS/PDF)**:
- Source: Processing times (if JS-rendered) or PDF report.
- Acquisition: Playwright or PDF download.
- Extraction: Firecrawl or `pdfplumber`.
- Contract: `ProcessingTimeRecord`.
- Quality: Schema validation, provider comparison.
- Storage: Postgres.

**Slice C — Semantic (LLM extraction)**:
- Source: Unstructured policy page.
- Acquisition: `httpx`.
- Extraction: LLM with schema.
- Contract: `PolicyEventRecord`.
- Quality: Semantic drift detection, human review.
- Storage: Postgres.

**Deliverable**: Three complete vertical slices demonstrating the architecture.

### Phase 3: Quality Engine + Publication (1.5 weeks)

**Goal**: Build quality gates, quarantine, and versioned releases.

**Tasks**:
- Implement severity-based quality checks.
- Add dataset-specific quality policies.
- Build quarantine table for rejected records.
- Implement publication gate (PASS/WARNING/BLOCKER).
- Add `pipeline_runs` and `dataset_releases` tables.
- Implement release publication and rollback.

**Deliverable**: Can validate extracted data, block bad records, and publish versioned releases.

### Phase 4: API + Deployment (1 week)

**Goal**: Build FastAPI and deploy to Cloud Run.

**Tasks**:
- Implement FastAPI endpoints with pagination.
- Add release metadata to responses.
- Separate ETL Job and API Service containers.
- Add Cloud Scheduler for cron jobs.
- Add Cloud Monitoring alerts.

**Deliverable**: Production-ready API with versioned data.

### Phase 5: Add Remaining Sources (2-3 weeks)

**Goal**: Add remaining 15 sources as configuration + contracts.

**Tasks**:
- Define contracts for remaining tables.
- Configure extraction strategies.
- Add quality policies.
- Test end-to-end.

**Deliverable**: Full source catalog operational.

***

## Cost Model (Updated)

Instead of a fixed estimate, use a cost model:

```text
Total cost = 
  acquisition_cost/source +
  extraction_cost/record +
  storage_cost/GB +
  compute_cost/run
```

**After Phase 0**, calculate actual costs:

| Component | Cost Driver | Example |
|---|---|---|
| **Acquisition** | Per-source HTTP/browser calls | $0–50/mo (mostly free for simple HTTP) |
| **Extraction** | Per-record or per-page | Custom: $0; Firecrawl: $0.05/record; Apify: $0.05–0.50/1K pages  |
| **Storage** | GB/month | GCS: ~$0.02/GB; Postgres: shared ~$25–50/mo |
| **Compute** | Cloud Run Job minutes | ~$0 for minutes/month |
| **API** | Cloud Run Service | ~$0–5/mo (min-instances 0) |

**Total**: ~$50–150/mo depending on extraction provider usage.

***

## Reusability for NepalEarth

This architecture is **domain-agnostic for ingestion and quality, domain-specific for contracts**.

**To power NepalEarth**:
1. **Define new sources** (government datasets, tourism websites, conservation data).
2. **Define new contracts** (e.g., `TrekkingRouteRecord`, `ConservationAreaRecord`).
3. **Reuse the same engine** (acquisition, extraction, quality, storage, API).

**Example**:
```yaml
sources:
  - source_id: nepal-tourism-treks
    resources:
      - resource_id: /trekking-routes
        resource_type: url
        locator:
          url: https://ntb.gov.np/trekking-routes
        acquisition_strategy: http
    extraction_strategies:
      - strategy_type: html_table
        provider: custom
    contract_id: TrekkingRouteRecord
    quality_policy_id: TrekkingRoutePolicy
```

The engine doesn't care about the domain—it acquires, validates, and serves structured data.

***

## Next Steps

### Week 1: Provider Bake-Off
- Test Firecrawl, Apify, custom on 10 URLs.
- Measure accuracy, cost, latency, failure rate.
- Choose primary and fallback providers.

### Week 2-3: Control Plane + Raw Snapshots
- Implement GCS snapshot storage.
- Build control plane tables.
- Add replay capability.
- Test with existing sources.

### Week 4-5: Three Vertical Slices
- Build Slice A (easy HTML table).
- Build Slice B (difficult JS/PDF).
- Build Slice C (semantic LLM).
- Test end-to-end for each.

### Week 6-7: Quality Engine + Publication
- Implement severity-based quality checks.
- Add dataset-specific quality policies.
- Build quarantine and release tables.
- Test publication gate.

### Week 8: API + Deployment
- Build FastAPI endpoints.
- Deploy to Cloud Run.
- Add monitoring and alerts.

***

This architecture gives you **modern data platform properties** (immutability, contracts, quality gates, versioning, semantic drift detection) without the operational overhead of Airflow or building your own crawler. It's reusable across koshi, NepalEarth, and any future data product. [use-apify](https://use-apify.com/blog/firecrawl-comprehensive-guide)