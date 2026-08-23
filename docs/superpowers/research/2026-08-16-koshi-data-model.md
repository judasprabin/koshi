# koshi — Complete Data Model

**Status:** Canonical (single source of truth for every koshi table)
**Date:** 2026-08-16 · **Revised 2026-08-18** after the three-agent source audit
**Author:** Prabin Karki (assembled from `feedback.md` control/data-plane specs, `2026-08-16-koshi-etl-architecture.md` §6, and `2026-08-15-koshi-etl-finalization-design.md` §4)

> This document models **every entity** across the control plane, data/execution plane, and the 18 domain fact tables.
> Sources: `docs/superpowers/specs/feedback.md` (target architecture), `docs/superpowers/specs/2026-08-16-koshi-etl-architecture.md` §6 (domain tables), `docs/superpowers/specs/2026-08-15-koshi-etl-finalization-design.md` §4 (domain definitions).

> ### 2026-08-18 revision
>
> This model was designed against assumptions about what the source pages
> contain. The 2026-08-17 audit fetched them. Where the two disagree, **the
> pages win** — every change below is traceable to fetched content, cited in
> `docs/superpowers/research/source-audit/`.
>
> **Four findings change the shape of the model, not just its column list:**
>
> 1. **`occupations.code` is not one key space.** Sources disagree on both
>    *width* (4-digit unit group vs 6-digit occupation) and *edition* (ANZSCO
>    2013, ANZSCO 2022 and OSCA are all simultaneously live). It is the FK
>    anchor for 7 tables, so this propagates everywhere.
> 2. **The stream dimension is missing entirely.** Processing times and fees are
>    published per subclass **and stream**. `processing_times`' unique constraint
>    collides outright on 485/500/482/186.
> 3. **Provenance can be present and false.** Two `ceiling_usage` rows passed
>    `require_provenance` while citing a page that does not contain them —
>    the check tests non-null, not truth.
> 4. **Several columns have no source at all** and never will. They are marked
>    **NO SOURCE** below and should ship NULL or be dropped, not left looking
>    like pending work.
>
> Each affected table carries an **`⚠ Audit`** block. Findings are referenced as
> I*n* (integrity), F*n* (forced change) and G*n* (gap) per the agent files.
>
> ### 2026-08-18 (later) — reconciled with the implementation
>
> Steps 3–7 built part of this model, and this document has been brought back
> into line with the code. Sections marked **✅ Built** describe what exists;
> everything else is still specification.
>
> Where the implementation deliberately departs from what this doc specified,
> the departure is recorded **at the table**, with its reason. The most
> important is C22: an earlier revision specified a foreign key that must not
> exist, and building it would abort every crosswalk load. Undocumented
> deviations read as bugs to the next person, so they are written down where
> someone will actually hit them.
>
> **8 tables are live.** If you want the real schema, skip to
> [C1](#c1-occupations) — every table in §C carries its own Built/Target
> status. Sections **A** (Control Plane, 6 tables) and **B**
> (Data/Execution Plane, 5 tables) below are **0% built** — see each
> section's own banner for why, and the ETL architecture doc's
> [Part II](2026-08-16-koshi-etl-architecture.md#10-target-architecture-overview--the-medallion-pipeline)
> for the full reference design.

---

## Table of Contents

1. [Conventions](#conventions)
2. [Entity-Relationship Diagram](#entity-relationship-diagram)
3. [Medallion-Layer Map](#medallion-layer-map)
4. [A. Control Plane Entities](#a-control-plane-entities)
   - [A1. sources](#a1-sources)
   - [A2. resources](#a2-resources)
   - [A3. extraction_strategies](#a3-extraction_strategies)
   - [A4. contracts](#a4-contracts)
   - [A5. quality_policies](#a5-quality_policies)
   - [A6. schedules](#a6-schedules)
5. [B. Data / Execution Plane Entities](#b-data--execution-plane-entities)
   - [B1. snapshots (Bronze)](#b1-snapshots)
   - [B2. snapshot_manifests (Bronze)](#b2-snapshot_manifests)
   - [B3. pipeline_runs (lineage)](#b3-pipeline_runs)
   - [B4. quarantine](#b4-quarantine)
   - [B5. dataset_releases](#b5-dataset_releases)
6. [C. Domain Fact Tables (Silver / Gold)](#c-domain-fact-tables)
   - [C1. occupations (built)](#c1-occupations)
   - [C2. eoi_rounds (built)](#c2-eoi_rounds)
   - [C3. ceiling_usage (built)](#c3-ceiling_usage)
   - [C4. occupation_momentum (built, derived)](#c4-occupation_momentum)
   - [C5. source_pages (built)](#c5-source_pages)
   - [C6. visa_subclasses](#c6-visa_subclasses)
   - [C7. english_test_bands](#c7-english_test_bands)
   - [C8. assessing_bodies](#c8-assessing_bodies)
   - [C9. occupation_assessing_bodies](#c9-occupation_assessing_bodies)
   - [C10. points_criteria_reference](#c10-points_criteria_reference)
   - [C11. policy_events](#c11-policy_events)
   - [C12. state_nomination_status](#c12-state_nomination_status)
   - [C13. list_change_log](#c13-list_change_log)
   - [C14. processing_times](#c14-processing_times)
   - [C15. program_allocation](#c15-program_allocation)
   - [C16. application_funnel](#c16-application_funnel)
   - [C17. eligibility_requirements](#c17-eligibility_requirements)
   - [C18. skills_priority_ratings](#c18-skills_priority_ratings)
7. [C19–C22. Entities added by the 2026-08-17 audit](#c19c22-entities-added-by-the-2026-08-17-audit)
   - [C19. anzsco_osca_crosswalk](#c19-anzsco_osca_crosswalk)
   - [C20. occupation_list_membership](#c20-occupation_list_membership)
   - [C21. visa_fees](#c21-visa_fees)
   - [C22. occupation_titles](#c22-occupation_titles)
8. [Provenance & Derived Conventions](#provenance--derived-conventions)
   - [The verified-citation rule](#the-verified-citation-rule-added-2026-08-18)

---

## Conventions

| Convention | Rule |
|---|---|
| **Provenance trio** | `source_url` (TEXT), `retrieved_at` (TIMESTAMPTZ), `reliability_tier` (TEXT) — the last three columns on every fact table |
| **reliability_tier values** | `official_scraped`, `official_curated`, `derived`, `community_sourced` (reserved, unused) |
| **Derived tables** | Omit `source_url`; `reliability_tier` is always `derived` |
| **SQLAlchemy** | 2.0 `Mapped[...]`, one model file per table, constraints in `__table_args__` |
| **Migrations** | One Alembic migration per table; numbered `0007`–`0019` for new domain tables (continuing from `0006`) |
| **PK pattern** | `id` surrogate PK (INTEGER, autoincrement) on all except reference tables with a strong natural key (`occupations.code`, `visa_subclasses.code`, `assessing_bodies.body_name`, `eligibility_requirements.requirement_type`) |
| **`source_pages`** | Metadata, not a fact — carries **no** provenance trio (it *is* the source) |
| **JSONB** | Used for `documents_required` (state_nomination_status), `config` (extraction_strategies), `schema` (contracts), `metadata` (pipeline_runs/dataset_releases) |

---

## Entity-Relationship Diagram

```mermaid
erDiagram
    %% =========================================================================
    %% CONTROL PLANE
    %% =========================================================================
    sources ||--o{ resources : "source_id"
    sources ||--o{ schedules : "source_id"
    sources ||--o{ pipeline_runs : "source_id"
    sources ||--o{ snapshots : "source_id"
    resources ||--o{ extraction_strategies : "resource config links"
    resources ||--o{ snapshots : "resource_id"
    contracts ||--o{ quality_policies : "contract_id"
    contracts ||--o{ pipeline_runs : "contract_id"
    contracts ||--o{ dataset_releases : "contract_id"
    pipeline_runs ||--o{ pipeline_runs : "parent_run_id"
    pipeline_runs ||--o{ quarantine : "run_id"
    pipeline_runs ||--o{ snapshot_manifests : "run_id"
    snapshots ||--o{ snapshot_manifests : "snapshot_id"

    %% =========================================================================
    %% DOMAIN FACT TABLES
    %% =========================================================================
    occupations ||--o{ eoi_rounds : "occupation_code (nullable)"
    occupations ||--o{ ceiling_usage : "occupation_code"
    occupations ||--o{ occupation_momentum : "occupation_code"
    occupations ||--o{ state_nomination_status : "occupation_code"
    occupations ||--o{ skills_priority_ratings : "occupation_code"
    occupations ||--o{ occupation_assessing_bodies : "occupation_code"
    occupations ||--o{ list_change_log : "occupation_code"

    visa_subclasses ||--o| visa_subclasses : "onward_pathway_code (self-FK, nullable)"
    visa_subclasses ||--o{ processing_times : "visa_code"
    visa_subclasses ||--o{ application_funnel : "visa_code"
    visa_subclasses ||--o{ policy_events : "visa_code (nullable)"

    assessing_bodies ||--o{ occupation_assessing_bodies : "body_name"

    %% =========================================================================
    %% CONTROL PLANE — TABLE DEFINITIONS
    %% =========================================================================
    sources {
        string source_id PK "e.g., 'homeaffairs-visa-fees'"
        string name
        string description
        string domain "e.g., 'homeaffairs.gov.au'"
        timestamptz created_at
        timestamptz updated_at
    }

    resources {
        string resource_id PK "e.g., '/visa-fees'"
        string source_id FK
        string resource_type "url | pdf | api | file"
        jsonb locator "{url, method, headers}"
        string acquisition_strategy "http | browser | api_client | managed"
        timestamptz created_at
        timestamptz updated_at
    }

    extraction_strategies {
        string strategy_id PK
        string resource_id FK "(implicit — configures a resource)"
        string strategy_type "html_table | pdf_parser | semantic_extraction | api_parser"
        string provider "custom | firecrawl | apify | zyte | llm"
        int priority "fallback order, 1 = primary"
        jsonb config "schema, prompt, selectors"
        bool enabled
        timestamptz created_at
    }

    contracts {
        string contract_id PK
        string name "e.g., 'VisaFeeRecord'"
        string version "e.g., 'v1'"
        jsonb schema "Pydantic model as JSON schema"
        string domain "visa | occupation | state | reference"
        timestamptz created_at
        timestamptz updated_at
    }

    quality_policies {
        string policy_id PK
        string contract_id FK
        int expected_min_records
        int expected_max_records
        numeric max_change_percent
        text required_fields "Postgres ARRAY"
        text uniqueness_fields "Postgres ARRAY"
        text block_on "Postgres ARRAY: schema_error, required_field_missing, etc."
        timestamptz created_at
        timestamptz updated_at
    }

    schedules {
        string schedule_id PK
        string source_id FK
        string cadence "daily | weekly | monthly | quarterly | annual | on_demand"
        interval freshness_sla "max tolerable staleness"
        int priority "1–10"
        bool enabled
        timestamptz created_at
    }

    %% =========================================================================
    %% DATA / EXECUTION PLANE — TABLE DEFINITIONS
    %% =========================================================================
    snapshots {
        uuid snapshot_id PK
        string source_id FK
        string resource_id FK
        timestamptz retrieved_at
        string acquisition_strategy
        string content_hash "SHA-256"
        text storage_path "GCS or local path"
        int http_status
        string content_type
        jsonb request_headers
        jsonb response_headers
        string etag
        string last_modified
        int content_size_bytes
        int acquisition_duration_ms
    }

    snapshot_manifests {
        uuid manifest_id PK
        uuid snapshot_id FK
        uuid run_id FK
        jsonb payload "Full manifest JSON (as in §2.1)"
    }

    pipeline_runs {
        uuid run_id PK
        uuid parent_run_id FK "self, for nested tasks"
        string run_type "acquisition | extraction | validation | quality | publication"
        string source_id FK
        string resource_id
        string contract_id FK
        uuid snapshot_id FK "(optional — links to acquired snapshot)"
        string status "pending | running | success | failure | blocked | warning"
        timestamptz started_at
        timestamptz finished_at
        jsonb input "serialized inputs to this stage"
        jsonb output "serialized outputs (row counts, etc.)"
        text error "error message if failed"
        jsonb metadata
    }

    quarantine {
        uuid quarantine_id PK
        uuid run_id FK "the pipeline run that produced these rejects"
        string contract_id FK
        text record_payload "the rejected record as JSON"
        text rejection_reasons "comma-separated quality-check failures"
        string severity "INFO | WARNING | ERROR | BLOCKER"
        timestamptz quarantined_at
    }

    dataset_releases {
        uuid release_id PK
        timestamptz created_at
        string status "complete | partial | degraded"
        string contract_id FK
        uuid pipeline_run_ids "Postgres ARRAY of UUIDs"
        jsonb metadata
        bool is_current
        string previous_release_id "for rollback chain"
    }

    %% =========================================================================
    %% DOMAIN FACT TABLES — KEY TABLES
    %% =========================================================================
    occupations {
        string code PK "ANZSCO occupation code"
        string name
        string unit_group
        string source_url
        timestamptz retrieved_at
        string reliability_tier
    }

    eoi_rounds {
        int id PK
        string visa_code
        string occupation_code FK "nullable"
        date round_date
        int threshold_points
        int invitations_issued "nullable"
        string source_url
        timestamptz retrieved_at
        string reliability_tier
    }

    ceiling_usage {
        int id PK
        string occupation_code FK
        string program_year
        int issued
        int ceiling
        date as_of_date
        string source_url
        timestamptz retrieved_at
        string reliability_tier
    }

    occupation_momentum {
        int id PK
        string occupation_code FK
        timestamptz computed_at
        string direction "rising | falling | steady"
        string reliability_tier "always 'derived'"
    }

    source_pages {
        int id PK
        string url UK
        string domain
        string category
        string content_hash
        timestamptz first_seen_at
        timestamptz last_checked_at
        timestamptz last_changed_at
        string status "active | dead | redirected"
        timestamptz last_extracted_at "nullable"
    }

    visa_subclasses {
        string code PK
        string name
        string family
        string permanence
        string age_limit
        string work_rights_description
        string family_inclusion_rule
        string residency_requirement_description
        bool occupation_list_required
        string onward_pathway_code FK "self, nullable, 2-pass seed"
        numeric base_application_cost
        bool points_test_required
        string source_url
        timestamptz retrieved_at
        string reliability_tier
    }

    assessing_bodies {
        string body_name PK
        string turnaround_estimate
        string cost
        string source_url
        timestamptz retrieved_at
        string reliability_tier
    }
```

> **Not drawn above (for legibility):** the remaining domain tables — `english_test_bands`, `points_criteria_reference`, `policy_events`, `state_nomination_status`, `list_change_log`, `processing_times`, `program_allocation`, `application_funnel`, `eligibility_requirements`, `skills_priority_ratings`, and `occupation_assessing_bodies`. See §C7–C18 for their full column definitions and relationships.

---

## Medallion-Layer Map

```
┌──────────────────────────────────────────────────────────────────┐
│                        CONTROL PLANE                              │
│  sources   resources   extraction_strategies                     │
│  contracts   quality_policies   schedules                        │
│  (Metadata — not a medallion tier; defines what happens)         │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                          BRONZE (Raw)                             │
│  snapshots          — immutable raw source artifacts             │
│  snapshot_manifests  — acquisition metadata (manifest.json)       │
│  source_pages       — crawl registry + content hashes            │
│  (Immutability, content hash, replayable without re-acquisition)  │
└──────────────────────────┬───────────────────────────────────────┘
                           │ extraction + validation
┌──────────────────────────▼───────────────────────────────────────┐
│                         SILVER (Validated)                        │
│  pipeline_runs      — lineage across all ETL stages              │
│  quarantine         — rejected records (failed quality gates)    │
│  (Quality-checked, deduplicated, provenance-attached rows)       │
│                                                                   │
│  Domain tables — scraped/curated, one row = one sourced fact:     │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ occupations · eoi_rounds · ceiling_usage                    │ │
│  │ visa_subclasses · english_test_bands · assessing_bodies     │ │
│  │ occupation_assessing_bodies · points_criteria_reference     │ │
│  │ policy_events · state_nomination_status · list_change_log   │ │
│  │ processing_times · program_allocation · application_funnel  │ │
│  │ eligibility_requirements · skills_priority_ratings          │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────┬───────────────────────────────────────┘
                           │ normalization + derivation
┌──────────────────────────▼───────────────────────────────────────┐
│                          GOLD (Serving)                           │
│  dataset_releases    — versioned, rollback-able publication      │
│  occupation_momentum — derived fact (computed from Silver rows)  │
│  (API-ready, current-release-only views, derived computations)   │
└──────────────────────────────────────────────────────────────────┘
```

---

## A. Control Plane Entities

> ⚠ **DEFERRED — not on the near-term roadmap.** Build when: hardcoded
> source constants in `pipeline.py` become painful to maintain by hand —
> realistically, once source count is well past today's 6, or once adding a
> source means touching more than one file. See the ETL architecture doc's
> [§12](2026-08-16-koshi-etl-architecture.md#12-control-plane).

The control plane defines **what should happen** — configuration, policies, schedules, and the registry of sources/resources/contracts. It does not hold acquired data.

### A1. sources

**Purpose:** Registry of every external data source koshi acquires from. One source may have multiple resources (URLs, PDFs, APIs).

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `source_id` | `TEXT` | NOT NULL | **PK** |
| `name` | `TEXT` | NOT NULL | — |
| `description` | `TEXT` | NULL | — |
| `domain` | `TEXT` | NOT NULL | e.g. `homeaffairs.gov.au` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, `now()` | — |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, `now()` | — |

**Relationships:**
- `sources.source_id` ← `resources.source_id` (FK)
- `sources.source_id` ← `schedules.source_id` (FK)
- `sources.source_id` ← `pipeline_runs.source_id` (FK — optional, tracing)
- `sources.source_id` ← `snapshots.source_id` (FK)

**Source reference:** N/A — this is a control-plane registry. Populated at system-config time from `src/koshi/sources/domains.yaml` and explicit `SourceSpec` declarations.

---

### A2. resources

**Purpose:** Each physical resource belonging to a source — a specific URL, PDF file, API endpoint, or file location.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `resource_id` | `TEXT` | NOT NULL | **PK** |
| `source_id` | `TEXT` | NOT NULL | **FK** → `sources.source_id` |
| `resource_type` | `TEXT` | NOT NULL | `CHECK (resource_type IN ('url','pdf','api','file'))` |
| `locator` | `JSONB` | NOT NULL | `{url: "...", method: "GET", headers: {...}}` |
| `acquisition_strategy` | `TEXT` | NOT NULL | `CHECK (acquisition_strategy IN ('http','browser','api_client','managed'))` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, `now()` | — |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, `now()` | — |

**Relationships:**
- `resources.source_id` → `sources.source_id`
- `resources.resource_id` ← `extraction_strategies.resource_id` (FK)
- `resources.resource_id` ← `snapshots.resource_id` (FK)

**Source reference:** N/A — control-plane declaration. Derived from the source catalog in `2026-08-16-koshi-etl-architecture.md` §4 (16 sources, each with ≥1 resources).

---

### A3. extraction_strategies

**Purpose:** Defines how a resource gets extracted — which parser/provider/strategy to use, in priority (fallback) order.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `strategy_id` | `TEXT` | NOT NULL | **PK** |
| `resource_id` | `TEXT` | NOT NULL | **FK** → `resources.resource_id` |
| `strategy_type` | `TEXT` | NOT NULL | `CHECK (strategy_type IN ('hidden_field_json','json_api','html_table','xlsx_pivot_cache','epub_table_positional','pdf_parser','semantic_extraction','api_parser'))` |
| `provider` | `TEXT` | NOT NULL | `CHECK (provider IN ('custom','firecrawl','apify','zyte','llm'))` |
| `priority` | `INTEGER` | NOT NULL, `1` | Fallback order (1 = primary) |
| `config` | `JSONB` | NOT NULL, `'{}'` | Strategy-specific config — see the required keys below |
| `enabled` | `BOOLEAN` | NOT NULL, `true` | — |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, `now()` | — |

**Relationships:**
- `extraction_strategies.resource_id` → `resources.resource_id`

**Source reference:** N/A — control-plane configuration. Models the quality-aware fallback chain described in `feedback.md` §2.2.

> **⚠ Audit (F12) — the original `strategy_type` vocabulary described none of
> koshi's actual sources.**
>
> It offered `html_table | pdf_parser | semantic_extraction | api_parser`. In
> reality **no** `immi.homeaffairs.gov.au` page serves an HTML table, no koshi
> source is a PDF, and the two richest sources are a JSON API and an XLSX pivot
> cache. Every Home Affairs page would have been mis-typed as `html_table` and
> parsed for markup that does not exist.
>
> **Four values added**, each matching a real, verified delivery mechanism:
>
> | `strategy_type` | Used by | Required `config` keys |
> |---|---|---|
> | `hidden_field_json` | Sources 2, 3, 4, 5, 6, 7, 8, 15, 17 | **`json_root_key`**, `hidden_input_id` |
> | `json_api` | Fees (`GetPriceList`), processing times (`GetProcessGuide*`) | `method`, `endpoint`, `payload` |
> | `xlsx_pivot_cache` | BP0068 | `pivot_cache_index`, `field_map` |
> | `epub_table_positional` | LIN 19/051, `F2025L00905` | **`table_index`**, `iframe_hop`, `rowspan_aware` |
>
> **`json_root_key` is load-bearing, not cosmetic.** Home Affairs pages do not
> use one key: main pages use `content`, `previous-rounds` uses `criteria`. A
> parser hard-coding either raises `KeyError` on the other. Storing it per
> resource is the reason this column exists.
>
> **`table_index` is a breaking-change risk.** LIN 19/051's 12 epub tables carry
> no `id` or `class`, so they can only be addressed positionally. The strategy
> should also assert an expected row count (Table 5 = 504, Table 6 = 38) so a
> re-ordered document fails loudly instead of silently loading the wrong table.
>
> **`rowspan_aware` matters for `F2025L00905`**, whose Schedule 2 table uses 12
> `rowspan` attributes; naive `td`-indexing misaligns the Superior band rows.

---

### A4. contracts

**Purpose:** Canonical Pydantic schema for a domain record — decouples extraction from storage. Domain-specific, not domain-agnostic.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `contract_id` | `TEXT` | NOT NULL | **PK** |
| `name` | `TEXT` | NOT NULL | e.g. `VisaFeeRecord`, `OccupationRecord` |
| `version` | `TEXT` | NOT NULL | e.g. `v1` |
| `schema` | `JSONB` | NOT NULL | Pydantic model serialized as JSON Schema |
| `domain` | `TEXT` | NOT NULL | `CHECK (domain IN ('visa','occupation','state','reference','editorial','aggregate'))` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, `now()` | — |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, `now()` | — |

**Relationships:**
- `contracts.contract_id` ← `quality_policies.contract_id` (FK)
- `contracts.contract_id` ← `pipeline_runs.contract_id` (FK — optional)
- `contracts.contract_id` ← `dataset_releases.contract_id` (FK)

**Source reference:** One contract per domain table. Defined inline from the Pydantic model in `extraction/` and `schemas/`.

---

### A5. quality_policies

**Purpose:** Per-contract quality rules — row-count expectations, uniqueness constraints, severity-based blocking. Drives the quality engine gate.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `policy_id` | `TEXT` | NOT NULL | **PK** |
| `contract_id` | `TEXT` | NOT NULL | **FK** → `contracts.contract_id` |
| `expected_min_records` | `INTEGER` | NULL | — |
| `expected_max_records` | `INTEGER` | NULL | — |
| `max_change_percent` | `NUMERIC(5,2)` | NULL | e.g. 30.00 means 30% |
| `required_fields` | `TEXT[]` | NULL | Postgres array |
| `uniqueness_fields` | `TEXT[]` | NULL | Postgres array — natural key columns |
| `block_on` | `TEXT[]` | NOT NULL, `'{}'` | `schema_error`, `required_field_missing`, `duplicate_primary_key`, etc. |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, `now()` | — |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, `now()` | — |

**Relationships:**
- `quality_policies.contract_id` → `contracts.contract_id`

**Source reference:** N/A — control-plane policy. Defined per-contract (see `feedback.md` §2.4 YAML examples for `VisaFeeRecord` and `EOIRoundRecord`).

---

### A6. schedules

**Purpose:** Cadence and freshness SLA for each source — defines when acquisition should trigger.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `schedule_id` | `TEXT` | NOT NULL | **PK** |
| `source_id` | `TEXT` | NOT NULL | **FK** → `sources.source_id` |
| `cadence` | `TEXT` | NOT NULL | `CHECK (cadence IN ('daily','weekly','monthly','quarterly','annual','on_demand'))` |
| `freshness_sla` | `INTERVAL` | NULL | e.g. `'1 day'`, `'7 days'` |
| `priority` | `INTEGER` | NOT NULL, `5` | `CHECK (priority BETWEEN 1 AND 10)` |
| `enabled` | `BOOLEAN` | NOT NULL, `true` | — |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, `now()` | — |

**Relationships:**
- `schedules.source_id` → `sources.source_id`

**Source reference:** N/A — maps to cadence groups in `2026-08-16-koshi-etl-architecture.md` §9.1 (nightly/weekly/monthly/quarterly/annual/on-demand).

---

## B. Data / Execution Plane Entities

> ⚠ **DEFERRED — not on the near-term roadmap.** Build when: scheduling
> stops being manual, or a bad row reaches the API unnoticed and there's no
> quarantine to have caught the next one. See the ETL architecture doc's
> [§13](2026-08-16-koshi-etl-architecture.md#13-data-plane).

The data plane executes **what needs to happen** — acquisition, extraction, validation, quality gating, and publication.

### B1. snapshots

**Purpose:** Immutable raw source artifact — the Bronze layer. Stores the original response (HTML, JSON, PDF) before any processing, enabling replay without re-acquisition.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `snapshot_id` | `UUID` | NOT NULL, `gen_random_uuid()` | **PK** |
| `source_id` | `TEXT` | NOT NULL | **FK** → `sources.source_id` |
| `resource_id` | `TEXT` | NOT NULL | **FK** → `resources.resource_id` |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | When acquisition occurred |
| `acquisition_strategy` | `TEXT` | NOT NULL | `http`, `browser`, `api_client`, `managed` |
| `content_hash` | `TEXT` | NOT NULL | SHA-256 of raw response bytes |
| `storage_path` | `TEXT` | NOT NULL | GCS path or local filesystem path to raw artifact |
| `http_status` | `INTEGER` | NULL | HTTP response status code |
| `content_type` | `TEXT` | NULL | e.g. `text/html`, `application/pdf` |
| `request_headers` | `JSONB` | NULL | Request headers sent |
| `response_headers` | `JSONB` | NULL | Response headers received |
| `etag` | `TEXT` | NULL | HTTP ETag from response |
| `last_modified` | `TEXT` | NULL | HTTP Last-Modified from response |
| `content_size_bytes` | `INTEGER` | NULL | Raw response size |
| `acquisition_duration_ms` | `INTEGER` | NULL | Time spent fetching |

**Relationships:**
- `snapshots.source_id` → `sources.source_id`
- `snapshots.resource_id` → `resources.resource_id`
- `snapshots.snapshot_id` ← `snapshot_manifests.snapshot_id` (FK)
- `snapshots.snapshot_id` ← `pipeline_runs.snapshot_id` (FK — optional)

**Source reference:** Models the raw snapshot structure from `feedback.md` §2.1 (the `gs://koshi-raw/` bucket layout). Unique natural key: `(source_id, resource_id, retrieved_at, content_hash)`.

---

### B2. snapshot_manifests

**Purpose:** The `manifest.json` metadata from each acquisition — acquisition parameters, timing, request ID. Stored as a row for queryability alongside the raw file.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `manifest_id` | `UUID` | NOT NULL, `gen_random_uuid()` | **PK** |
| `snapshot_id` | `UUID` | NOT NULL | **FK** → `snapshots.snapshot_id` |
| `run_id` | `UUID` | NULL | **FK** → `pipeline_runs.run_id` |
| `payload` | `JSONB` | NOT NULL | Full manifest JSON (schema: see `feedback.md` §2.1) |

**Relationships:**
- `snapshot_manifests.snapshot_id` → `snapshots.snapshot_id` (one-to-one conceptually)
- `snapshot_manifests.run_id` → `pipeline_runs.run_id`

**Source reference:** Schema from `feedback.md` §2.1 manifest JSON: `{source_id, resource_id, retrieved_at, acquisition_strategy, http_status, content_type, content_hash, etag, last_modified, request_id, acquisition_duration_ms}`.

---

### B3. pipeline_runs

**Purpose:** Unified lineage table across all ETL stages. Every acquisition/extraction/validation/quality/publication step is one row. Supports nested tasks (parent/child), tracing, and replay.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `run_id` | `UUID` | NOT NULL, `gen_random_uuid()` | **PK** |
| `parent_run_id` | `UUID` | NULL | **FK** → `pipeline_runs.run_id` (self-referential, for nested tasks) |
| `run_type` | `TEXT` | NOT NULL | `CHECK (run_type IN ('acquisition','extraction','validation','quality','publication'))` |
| `source_id` | `TEXT` | NULL | **FK** → `sources.source_id` |
| `resource_id` | `TEXT` | NULL | — |
| `contract_id` | `TEXT` | NULL | **FK** → `contracts.contract_id` |
| `snapshot_id` | `UUID` | NULL | **FK** → `snapshots.snapshot_id` |
| `status` | `TEXT` | NOT NULL, `'pending'` | `CHECK (status IN ('pending','running','success','failure','blocked','warning'))` |
| `started_at` | `TIMESTAMPTZ` | NULL | — |
| `finished_at` | `TIMESTAMPTZ` | NULL | — |
| `input` | `JSONB` | NULL | Serialized inputs to this stage |
| `output` | `JSONB` | NULL | Serialized outputs (row counts, records produced, etc.) |
| `error` | `TEXT` | NULL | Error message if status = `failure` |
| `metadata` | `JSONB` | NULL | Provider used, retry count, duration breakdown |

**Relationships:**
- `pipeline_runs.parent_run_id` → `pipeline_runs.run_id` (self-FK, hierarchical lineage)
- `pipeline_runs.source_id` → `sources.source_id`
- `pipeline_runs.contract_id` → `contracts.contract_id`
- `pipeline_runs.snapshot_id` → `snapshots.snapshot_id`
- `pipeline_runs.run_id` ← `pipeline_runs.parent_run_id`
- `pipeline_runs.run_id` ← `quarantine.run_id`
- `pipeline_runs.run_id` ← `snapshot_manifests.run_id`
- `pipeline_runs.run_id` ← `dataset_releases.pipeline_run_ids` (array, not FK)

**Source reference:** Schema from `feedback.md` §2.5. Derived from the generic execution model design.

---

### B4. quarantine

**Purpose:** Stores records rejected by quality gates — schema violations, uniqueness failures, semantic drift, etc. Enables human review and replay after fixes.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `quarantine_id` | `UUID` | NOT NULL, `gen_random_uuid()` | **PK** |
| `run_id` | `UUID` | NOT NULL | **FK** → `pipeline_runs.run_id` |
| `contract_id` | `TEXT` | NOT NULL | **FK** → `contracts.contract_id` |
| `record_payload` | `JSONB` | NOT NULL | The rejected record as JSON |
| `rejection_reasons` | `TEXT` | NOT NULL | Comma-separated quality-check failure identifiers |
| `severity` | `TEXT` | NOT NULL | `CHECK (severity IN ('INFO','WARNING','ERROR','BLOCKER'))` |
| `quarantined_at` | `TIMESTAMPTZ` | NOT NULL, `now()` | — |

**Relationships:**
- `quarantine.run_id` → `pipeline_runs.run_id`
- `quarantine.contract_id` → `contracts.contract_id`

**Source reference:** Designed from `feedback.md` §2.4's publication gate logic: `quarantine(quality_result.rejected_records)` on BLOCKER. Phase 3 deliverable (`feedback.md` §Implementation Roadmap, Phase 3).

---

### B5. dataset_releases

**Purpose:** Versioned publication of a contract's data. Supports release lifecycle (candidate → published), the `is_current` flag for API serving, and rollback.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `release_id` | `UUID` | NOT NULL, `gen_random_uuid()` | **PK** |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, `now()` | — |
| `status` | `TEXT` | NOT NULL | `CHECK (status IN ('complete','partial','degraded'))` |
| `contract_id` | `TEXT` | NOT NULL | **FK** → `contracts.contract_id` |
| `pipeline_run_ids` | `UUID[]` | NULL | Postgres array of UUIDs — all runs contributing to this release |
| `metadata` | `JSONB` | NULL | Source freshness, partial flags, quality summary |
| `is_current` | `BOOLEAN` | NOT NULL, `false` | Only one row per `contract_id` should have `is_current = true` |
| `previous_release_id` | `UUID` | NULL | Self-referential for rollback chain |

**Relationships:**
- `dataset_releases.contract_id` → `contracts.contract_id`
- `dataset_releases.pipeline_run_ids` references `pipeline_runs.run_id` (logical, unenforced array)
- `dataset_releases.previous_release_id` → `dataset_releases.release_id` (self-FK, rollback chain)

**Source reference:** Schema from `feedback.md` §2.6. Rollback workflow: set old `is_current = false`, set target release `is_current = true`.

---

## C. Domain Fact Tables

These 18 tables are the Silver/Gold normalized output — the actual sourced facts about the Australian skilled-migration system. Five are already built; the remaining 13 are target.

### C1. occupations

**Purpose:** ANZSCO occupation master list — the canonical occupation dimension. Fed by **ABS Table 5** (the classification proper, 1,076 six-digit occupations), **JSA** (which adds 4-digit unit groups), and **LIN 19/051** (which adds ANZSCO-2013-only codes the 2022 edition dropped).

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `code` | `TEXT` | NOT NULL | **PK** — ANZSCO occupation code (e.g. `261312`) |
| `name` | `TEXT` | NOT NULL | — |
| `unit_group` | `TEXT` | NOT NULL | ANZSCO unit group code (e.g. `2613`) |
| `code_grain` | `TEXT` | NOT NULL, `'occupation'` | `CHECK IN ('unit_group','occupation')` — migration `0008` |
| `anzsco_edition` | `TEXT` | NOT NULL, `'2022'` | Which edition this code belongs to — migration `0010` |
| `source_url` | `TEXT` | NOT NULL | Provenance trio |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | Provenance trio |
| `reliability_tier` | `TEXT` | NOT NULL, `'official_scraped'` | Provenance trio |

**Live volume (2026-08-18):** 1,485 rows — 1,480 ANZSCO 2022 plus 5 carried
only by LIN 19/051 under 2013 (e.g. `394111 Cabinetmaker`, which live
invitation rounds invite and the 2022 classification does not contain).

**Relationships:**
- `occupations.code` ← `eoi_rounds.occupation_code` (FK, nullable)
- `occupations.code` ← `ceiling_usage.occupation_code` (FK)
- `occupations.code` ← `occupation_momentum.occupation_code` (FK)
- `occupations.code` ← `state_nomination_status.occupation_code` (FK)
- `occupations.code` ← `skills_priority_ratings.occupation_code` (FK)
- `occupations.code` ← `occupation_assessing_bodies.occupation_code` (FK)
- `occupations.code` ← `list_change_log.occupation_code` (FK)

**Source reference:** ANZSCO occupations → `occupations`. Scraped from `https://www.abs.gov.au/ausstats/abs@.nsf/Latestproducts/...` (ABS ANZSCO search page). Tier 2 (deterministic HTML).

**Status:** ✅ Built (migration `0001`).

> **⚠ Audit (F3, F9, I1) — this table's PK is doing three jobs at once and can
> only do one.** It anchors 7 FKs, so every problem here propagates.
>
> **1. Width.** Sources join at different grains: **NSW** and the FOI ceilings
> at **4-digit** unit groups; **QLD** and **LIN 19/051** at **6-digit**; **JSA**
> mixes both. A single-width PK silently fails to join roughly half of them.
>
> **2. Edition — three are simultaneously live.**
>
> | Instrument / source | ANZSCO edition |
> |---|---|
> | `F2024L01616` (ANZSCO Definition — pins migration) | **2013** |
> | LIN 19/051 (the binding occupation instrument) | **2013** |
> | `F2024L01618` (CSOL) | **2022** (100% match) |
> | JSA | dual-publishes ANZSCO **and OSCA** |
>
> **25 of LIN 19/051's codes are absent from ANZSCO 2022.** Without an edition
> column those rows look like bad data rather than a different vocabulary.
>
> **3. ANZSCO is being retired** in favour of **OSCA** (1,577 entries vs
> ANZSCO's 1,236).
>
> **Recommended changes:**
>
> | Change | Rationale |
> |---|---|
> | Add `anzsco_edition TEXT NOT NULL` | Three editions are live; without it the PK is ambiguous |
> | Add `code_grain TEXT` (`unit_group` \| `occupation`) | Makes the 4- vs 6-digit join explicit instead of implied |
> | **Keep ANZSCO as PK** — do *not* migrate to OSCA | The binding instrument and every state list are ANZSCO-coded; migrating would break the join to the authority that legally matters |
> | Add `anzsco_osca_crosswalk` table (see C19) | Carries the OSCA relationship without a destructive migration |
>
> **Source correction:** the JSA browse page is *not* where code+title lives.
> Use the **ABS structure workbook Table 6** (1,425 pairs) — catalog source 18.

---

### C2. eoi_rounds

**Purpose:** SkillSelect Expression of Interest invitation rounds — threshold points and invitations issued per visa/occupation/round date.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `visa_code` | `TEXT` | NOT NULL | e.g. `189`, `491` — read from the page, not passed in |
| `occupation_name_raw` | `TEXT` | NOT NULL | What the source published, verbatim — migration `0007` |
| `occupation_code` | `TEXT` | NULL | **FK** → `occupations.code`. *Derived* via the C22 crosswalk, never published by the source |
| `round_date` | `DATE` | NOT NULL | — |
| `threshold_points` | `INTEGER` | NOT NULL | Minimum points invited |
| `invitations_issued` | `INTEGER` | NULL | **NO SOURCE at this grain** — see audit block |
| `source_url` | `TEXT` | NOT NULL | Provenance trio |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | Provenance trio |
| `reliability_tier` | `TEXT` | NOT NULL, `'official_scraped'` | Provenance trio |

**Unique constraint:** `(visa_code, occupation_name_raw, round_date)` — migration `0007`.

⚠ **Keyed on the name, not the code.** `occupation_code` is NULL for any row
the crosswalk cannot resolve, and Postgres treats NULLs as distinct, so a
code-keyed constraint silently stops deduplicating exactly the rows most at
risk of duplication. The name is the stable natural key regardless of
resolution outcome.

**Live volume (2026-08-18):** 786 rows over 5 round dates — 140 from the
current-round page, 646 backfilled from the previous-rounds archive.
**0 unresolved.**

**Relationships:**
- `eoi_rounds.occupation_code` → `occupations.code`

**Source reference:** SkillSelect invitation rounds → `eoi_rounds` + `application_funnel` (submitted/invited counts). Scraped from `https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds`. Tier 2 (deterministic HTML).

**Status:** ✅ Built (migration `0002`) — **but the parser extracts zero rows.**

> **⚠ Audit (I1, BLOCKER) — the FK cannot be populated from the source.**
>
> The source table (decoded Table B) publishes occupation **names** —
> "Actuary", "Agricultural Consultant", "Carpenter" — and **never ANZSCO
> codes**. `occupation_code` is an FK to `occupations.code`. There is no
> selector fix for this; it needs a name→code crosswalk.
>
> **Resolution (G1, FOUND):** the union of ABS Table 6 (1,425 pairs) and
> LIN 19/051 Table 5 (504 pairs) resolves **140/140** live names. Neither alone
> suffices — each resolves only 132/140. Lookup must be **LIN-first**: three
> titles (**Management Consultant**, **Plumber (General)**, **Statistician**)
> resolve to *different codes* in the two sources, and LIN 19/051 is the binding
> instrument. An ABS-first implementation returns wrong codes without erroring.
>
> **Recommended changes:**
>
> | Change | Rationale |
> |---|---|
> | Add `occupation_name_raw TEXT NOT NULL` | Preserve what the source actually published; makes crosswalk failures visible and re-resolvable |
> | Keep `occupation_code` nullable | It is now a *derived* join, and 0 of 140 names carry a code natively |
> | **`invitations_issued` — NO SOURCE at this grain** | Table B has only 2 columns (`Occupation | minimum score`). Invitation counts live in decoded Tables A and C at round/subclass grain, not per occupation |
>
> **Parser bug:** `extraction/skillselect_rounds.py:49` unpacks **3** cells from
> a **2**-column table, so every row raises `ValueError`, is caught, and is
> skipped. The 100% skip rate currently exits cleanly — it should be a hard
> failure.
>
> **Backfill:** catalog source 17 (`previous-rounds`, root key `criteria`)
> supplies **19 rounds / 1,419 rows** of history.

---

### C3. ceiling_usage

**Purpose:** Annual occupation ceiling utilization — how many invitations have been issued against each occupation's ceiling for a program year.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `occupation_code` | `TEXT` | NOT NULL | **FK** → `occupations.code` |
| `program_year` | `TEXT` | NOT NULL | e.g. `2025-26` |
| `issued` | `INTEGER` | NOT NULL | Invitations issued to date |
| `ceiling` | `INTEGER` | NOT NULL | Annual ceiling |
| `as_of_date` | `DATE` | NOT NULL | The date this snapshot reflects |
| `source_url` | `TEXT` | NOT NULL | Provenance trio — URL of the PDF report |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | Provenance trio |
| `reliability_tier` | `TEXT` | NOT NULL, `'official_curated'` | Provenance trio |

**Check constraint:** `issued <= ceiling AND ceiling > 0`.

**Relationships:**
- `ceiling_usage.occupation_code` → `occupations.code`

**Source reference:** ~~Occupation ceilings PDF (planning-levels report)~~ — **the cited source does not contain this data.** See the audit block.

**Status:** ⚠ Built (migration `0003`) — **table exists, deliberately empty.**

> **⚠ Audit (I3, D1, BLOCKER) — this table has no source, and shipped
> fabricated data until 2026-08-18.**
>
> Two seeded rows (261313 → 3200/5000, 254499 → 1800/4000) cited the
> planning-levels page. That page was decoded in full: it contains a
> **visa-category table only, no per-occupation ceilings**, and — contrary to
> this entry's own "PDF report" description — **has no PDFs on it at all**.
>
> Per-occupation ceilings are **not routinely published anywhere**:
>
> | Check | Result |
> |---|---|
> | `/skillselect/occupation-ceilings` | **HTTP 404** (re-verified 2026-08-18) |
> | Live SkillSelect ceilings section | 599 bytes of prose, zero tables |
> | data.gov.au SkillSelect/EOI dataset | none exists |
> | FOI release `fa-260100545` | **the only** PY2025-26 table — scanned images, **4-digit** grain |
>
> **Why this matters beyond one table:** those rows passed `require_provenance`
> because `source_url` and `retrieved_at` were non-null. The check tests
> *presence*, not *truth*. The API served them as `official_curated`
> `SourcedFact`s, indistinguishable from verified government data. See the
> Provenance section's new **verified-citation rule**.
>
> The rows were removed in `fix: remove unsourced ceiling_usage seed rows`; the
> seed file is now comment-only and documents its own repopulation conditions.
>
> **Options, in preference order:**
>
> 1. **Retire the table.** The data does not exist at 6-digit grain.
> 2. **Re-grain to 4-digit** and source from the FOI release, accepting a
>    point-in-time disclosure with no update cadence.
> 3. **Derive `issued` from BP0068** (C16's source). ⚠ Do **not** map the FOI's
>    issued-looking column here — it is *prior-year grants in other subclasses*,
>    a different quantity entirely.

---

### C4. occupation_momentum

**Purpose:** Derived trend direction for an occupation — computed from `eoi_rounds` threshold-point history, never scraped.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `occupation_code` | `TEXT` | NOT NULL | **FK** → `occupations.code` |
| `computed_at` | `TIMESTAMPTZ` | NOT NULL | When this momentum was computed |
| `direction` | `TEXT` | NOT NULL | `CHECK (direction IN ('rising','falling','steady'))` |
| `reliability_tier` | `TEXT` | NOT NULL, `'derived'` | Always derived |

**Note:** No `source_url` — this is the only table that omits it (always `derived`). Cites the koshi rows it was computed from (the `eoi_rounds` that fed the computation).

**Relationships:**
- `occupation_momentum.occupation_code` → `occupations.code`

**Source reference:** Derived — computed from `eoi_rounds.threshold_points` history. No external source URL. Tier: N/A (derived).

**Status:** ✅ Built (migration `0004`).

---

### C5. source_pages

**Purpose:** Crawl registry — tracks every known source URL, its content hash, freshness, and extraction watermark. Metadata, not a fact table.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `url` | `TEXT` | NOT NULL | **UNIQUE** |
| `domain` | `TEXT` | NOT NULL | e.g. `homeaffairs.gov.au` |
| `category` | `TEXT` | NOT NULL | e.g. `visa_fees`, `occupations` |
| `content_hash` | `TEXT` | NOT NULL | SHA-256 of raw bytes |
| `first_seen_at` | `TIMESTAMPTZ` | NOT NULL, `now()` | — |
| `last_checked_at` | `TIMESTAMPTZ` | NOT NULL, `now()` | Last fetch attempt |
| `last_changed_at` | `TIMESTAMPTZ` | NOT NULL, `now()` | Last time content hash changed |
| `status` | `TEXT` | NOT NULL, `'active'` | `CHECK (status IN ('active','dead','redirected'))` |
| `last_extracted_at` | `TIMESTAMPTZ` | NULL | Watermark — only advanced after successful parse + persist |

**Note:** No provenance trio — this table *is* the source metadata.

**Relationship:** Referenced by `snapshots` via logical URL matching (not a direct FK).

**Source reference:** Every source in the catalog (16 sources, `2026-08-16-koshi-etl-architecture.md` §4).

**Status:** ✅ Built (migration `0005`).

---

### C6. visa_subclasses

**Purpose:** Static reference facts for each visa subclass — family, permanence, age limit, onward pathway, base application cost, and other near-unchanging attributes.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `code` | `TEXT` | NOT NULL | **PK** — visa subclass code (e.g. `189`, `491`) |
| `name` | `TEXT` | NOT NULL | e.g. `Skilled Independent visa (subclass 189)` |
| `family` | `TEXT` | NOT NULL | e.g. `skilled`, `student`, `family` |
| `permanence` | `TEXT` | NOT NULL | `CHECK (permanence IN ('permanent','provisional','temporary'))` |
| `age_limit` | `TEXT` | NULL | e.g. `Under 45`, `No limit` |
| `work_rights_description` | `TEXT` | NULL | Free-text description |
| `family_inclusion_rule` | `TEXT` | NULL | Free-text rule |
| `residency_requirement_description` | `TEXT` | NULL | Free-text description |
| `occupation_list_required` | `BOOLEAN` | NOT NULL | Whether the visa requires an occupation list |
| `onward_pathway_code` | `TEXT` | NULL | **FK** → `visa_subclasses.code` (self-referential — e.g. `491` → `191`) |
| `base_application_cost` | `NUMERIC(10,2)` | NULL | Main applicant fee (AUD) |
| `points_test_required` | `BOOLEAN` | NOT NULL | — |
| `source_url` | `TEXT` | NOT NULL | Provenance trio |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | Provenance trio |
| `reliability_tier` | `TEXT` | NOT NULL, `'official_curated'` | Provenance trio |

**Self-referential FK:** `onward_pathway_code → visa_subclasses.code` — requires **2-pass seed**: all rows inserted with `NULL` first, then a second pass sets pathway codes.

**Relationships:**
- `visa_subclasses.code` ← `visa_subclasses.onward_pathway_code` (self-FK)
- `visa_subclasses.code` ← `processing_times.visa_code` (FK)
- `visa_subclasses.code` ← `application_funnel.visa_code` (FK)
- `visa_subclasses.code` ← `policy_events.visa_code` (FK, nullable)

**Source reference:** Visa subclass static facts (189/190/491/485/500/482) → `visa_subclasses` (6 rows, rare cadence). Tier 5 (manual YAML curation). `base_application_cost` updated from visa-fees page (Tier 2, update-by-PK) — see open design question #5 in `2026-08-16-koshi-etl-architecture.md` §13.

> **⚠ Audit (I4, F10) — 6 rows cannot parent children carrying 76 and 150
> records.**
>
> | Source | Records | Child table |
> |---|---|---|
> | Processing-times API | **76** subclass × stream combos | `processing_times` |
> | Fee API | **150** fee records | `base_application_cost` |
> | BP0068 | **62** subclasses with grants | `application_funnel` |
> | **This table** | **6** | — |
>
> Every FK from those children into a 6-row parent fails for the majority of
> rows. Either widen this table or narrow the children — but the current shape
> cannot hold.
>
> **The self-FK example in this doc is itself broken:** the canonical
> `491 → 191` onward-pathway example targets a row that does not exist in a
> 6-row table.
>
> **Recommended changes:**
>
> | Change | Rationale |
> |---|---|
> | Widen to the BP0068 5-level taxonomy (Program → Category → Type → Sub-type → Subclass) | The only verified structured visa taxonomy found |
> | Add a **stream** dimension | Fees and processing times are both per-stream; without it `base_application_cost` is ambiguous |
> | `permanence` — **NO SOURCE** | Not published as structured data anywhere found (G5). Ship NULL or curate manually and mark `official_curated` |
>
> Caveat: BP0068's 62 subclasses are only those **with grants**, so it is a
> lower bound on a complete registry, not a registry.

### ✅ Built 2026-08-18 — migration `0011`, 62 rows

Populated from BP0068 rather than the 6-row tier-5 seed this section
originally described. Built columns are `code` (PK), `name`, `visa_category`
and the provenance trio.

**Not yet built** from the plan above: `permanence`, `family`, `age_limit`,
`work_rights_description`, `points_test_required` and the other static facts.
`permanence` in particular has **NO SOURCE** (G5) — it is not published as
structured data anywhere the audit found. The 5-level Program → Category →
Type → Sub-type → Subclass taxonomy is available in BP0068 and only
`visa_category` is currently taken from it.

**Status:** Target (migration `0007`).

---

### C7. english_test_bands

**Purpose:** English language test score bands and their migration points — IELTS, PTE, TOEFL, Cambridge, OET score mappings.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `test_name` | `TEXT` | NOT NULL | e.g. `IELTS`, `PTE Academic`, `TOEFL iBT`, `Cambridge C1`, `OET` |
| `band_level` | `TEXT` | NOT NULL | e.g. `Functional`, `Vocational`, `Competent`, `Proficient`, `Superior` |
| `score_requirement` | `TEXT` | NOT NULL | e.g. `IELTS 6.0 in each band`, `PTE 50 in each skill` |
| `points_awarded` | `INTEGER` | NOT NULL | Migration points (0, 10, or 20) |
| `cost` | `TEXT` | NULL | Approximate test cost (varies by country) |
| `validity_period` | `TEXT` | NULL | e.g. `3 years from test date` |
| `source_url` | `TEXT` | NOT NULL | Provenance trio |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | Provenance trio |
| `reliability_tier` | `TEXT` | NOT NULL, `'official_scraped'` | Provenance trio |

**Unique constraint:** `(test_name, band_level)`.

**Relationships:** None — standalone reference table.

**Source reference:** ~~Home Affairs English language requirements page~~ → **`F2025L00905` (LIN 25/016) Schedule 2 + `F2025L00904`**. Tier 2 (`epub_table_positional`, rowspan-aware).

> **⚠ Audit (F5, G3) — was BLOCKER, now resolved by re-sourcing.**
>
> The catalogued Home Affairs English page has **zero tables** — it is prose
> only and cannot feed this table. The data is in legislation instead:
>
> | Instrument | Supplies |
> |---|---|
> | **`F2025L00905`** Sch. 2 | **4 bands × 9 tests × 4 skills** — Vocational / Competent / Proficient / Superior |
> | **`F2025L00904`** | Functional English, 8 tests |
>
> This gives per-skill score thresholds per test, which is exactly the grain the
> table needs.
>
> ⚠ **Parser hazard:** Schedule 2's table uses **12 `rowspan` attributes**.
> Naive `td`-indexing misaligns the **Superior** rows — it will attribute wrong
> scores to the wrong band *silently*, producing plausible-looking bad data.
> The extraction strategy must set `rowspan_aware`.
>
> Note `/points-table` supplies only band→points for 3 bands, which is a
> different and much coarser thing than the per-test score matrix here.

**Status:** Target (migration `0008`).

---

### C8. assessing_bodies

**Purpose:** Skills assessing authorities — the bodies that assess qualifications/experience for each occupation.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `body_name` | `TEXT` | NOT NULL | **PK** — e.g. `ACS`, `Engineers Australia`, `VETASSESS` |
| `turnaround_estimate` | `TEXT` | NULL | e.g. `8–12 weeks` |
| `cost` | `TEXT` | NULL | e.g. `$500–$1,050 AUD` |
| `source_url` | `TEXT` | NOT NULL | Provenance trio |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | Provenance trio |
| `reliability_tier` | `TEXT` | NOT NULL, `'official_curated'` | Provenance trio |

**Relationships:**
- `assessing_bodies.body_name` ← `occupation_assessing_bodies.body_name` (FK)

**Source reference:** ~~MARA~~ → **LIN 19/051 (`F2019L00278`) epub Table 6** — 38 bodies. Tier 2 (`epub_table_positional`).

> **⚠ Audit (F2) — MARA is the wrong authority.**
>
> MARA registers **migration agents**, not **skills assessing authorities**
> (Engineers Australia, ACS, VETASSESS, CPA, ANMAC, …). The correct source is
> LIN 19/051, which specifies "Relevant Assessing Authorities": **Table 6** is
> the 38-row body key, **Table 5** the 504-row occupation join (C9).
>
> **`turnaround_estimate` and `cost` — NO SOURCE (G8).** No aggregated
> publication exists; the data lives on each of ~38 bodies' own sites. Ship
> NULL rather than commit to 38 separate scrapers.
>
> Since `body_name` is the PK, note the abbreviation-vs-full-name mismatch
> documented in C9 — it determines what this PK's values actually are.

**Status:** Target (migration `0009`).

---

### C9. occupation_assessing_bodies

**Purpose:** Many-to-many join — which assessing body/bodies serve each ANZSCO occupation.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `occupation_code` | `TEXT` | NOT NULL | **PK (composite)**, **FK** → `occupations.code` |
| `body_name` | `TEXT` | NOT NULL | **PK (composite)**, **FK** → `assessing_bodies.body_name` |
| `source_url` | `TEXT` | NOT NULL | Provenance trio |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | Provenance trio |
| `reliability_tier` | `TEXT` | NOT NULL, `'official_curated'` | Provenance trio |

**Composite PK:** `(occupation_code, body_name)`.

**Relationships:**
- `occupation_assessing_bodies.occupation_code` → `occupations.code`
- `occupation_assessing_bodies.body_name` → `assessing_bodies.body_name`

**Source reference:** ~~MARA~~ → **LIN 19/051 (`F2019L00278`) epub Table 5** — 504 rows. Tier 2 (`epub_table_positional`).

> **⚠ Audit (F2) — the join data exists, but two things break a naive load.**
>
> **1. The two tables key bodies differently.** Table 5 names bodies by
> **abbreviation**; Table 6 keys them by **full name**. A raw string compare
> between this table's FK and `assessing_bodies.body_name` will not match —
> an explicit abbreviation↔name mapping is required, and it is not published as
> a third table.
>
> **2. Some occupations specify "either body"** — a disjunction. A plain
> `(occupation_code, body_name)` row cannot express "either A or B". Flattening
> it into two independent rows asserts that *both* are valid, which misstates
> the requirement; dropping one loses information. This needs either a
> `requirement_group` column or an explicit `alternative_of` relationship.
>
> Table 5's 504 rows also serve as half of the name→code crosswalk (C2, G1).

**Status:** Target (migration `0010`).

---

### C10. points_criteria_reference

**Purpose:** The General Skilled Migration points test — what earns how many points (age bands, English, experience, qualifications, etc.).

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `criterion_name` | `TEXT` | NOT NULL | e.g. `Age`, `English Language Ability`, `Australian Work Experience` |
| `band_description` | `TEXT` | NOT NULL | e.g. `18–24 years`, `25–32 years`, `IELTS 8.0 in each band` |
| `points_value` | `INTEGER` | NOT NULL | Points awarded for this band |
| `source_url` | `TEXT` | NOT NULL | Provenance trio |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | Provenance trio |
| `reliability_tier` | `TEXT` | NOT NULL, `'official_scraped'` | Provenance trio |

**Unique constraint:** `(criterion_name, band_description)`.

**Relationships:** None — standalone reference table.

**Source reference:** Points test criteria page → `points_criteria_reference`. Scraped from `https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-independent-189/points-tested`. Tier 2 (deterministic HTML).

**Status:** Target (migration `0011`).

---

### C11. policy_events

**Purpose:** Editorial log of policy changes — budget announcements, legislative changes, program adjustments. Timestamped, linked to a visa subclass where applicable.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `event_date` | `DATE` | NOT NULL | When the policy event occurred |
| `visa_code` | `TEXT` | NULL | **FK** → `visa_subclasses.code` (nullable — national events don't target a specific visa) |
| `title` | `TEXT` | NOT NULL | Short headline |
| `description` | `TEXT` | NOT NULL | Full event description |
| `source_url` | `TEXT` | NOT NULL | Provenance trio |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | Provenance trio |
| `reliability_tier` | `TEXT` | NOT NULL, `'official_curated'` | Provenance trio |

**Relationships:**
- `policy_events.visa_code` → `visa_subclasses.code` (nullable)

**Source reference:** Budget / treasury announcements → `policy_events`. Tier 5 (manual YAML curation, editorial; domains: `budget.gov.au`, `treasury.gov.au`).

**Status:** Target (migration `0012`).

---

### C12. state_nomination_status

**Purpose:** Per-state, per-occupation nomination program status — open/limited/closed, with fees, requirements, and document checklists.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `state_code` | `TEXT` | NOT NULL | e.g. `NSW`, `VIC`, `QLD`, `WA`, `SA` |
| `occupation_code` | `TEXT` | NOT NULL | **FK** → `occupations.code` |
| `status` | `TEXT` | NOT NULL | `CHECK (status IN ('open','limited','closed'))` |
| `fee` | `TEXT` | NULL | Nomination application fee |
| `points_minimum` | `INTEGER` | NULL | Minimum points required |
| `job_offer_required` | `BOOLEAN` | NOT NULL, `false` | — |
| `residency_commitment_description` | `TEXT` | NULL | — |
| `decision_time_estimate` | `TEXT` | NULL | e.g. `6–8 weeks` |
| `documents_required` | `JSONB` | NULL | Display-only checklist (not a join table) |
| `approval_pattern_note` | `TEXT` | NULL | Free-text observation about pattern |
| `as_of_date` | `DATE` | NOT NULL | The date this status snapshot reflects |
| `source_url` | `TEXT` | NOT NULL | Provenance trio |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | Provenance trio |
| `reliability_tier` | `TEXT` | NOT NULL, `'official_curated'` | Provenance trio |

**Unique constraint:** `(state_code, occupation_code, as_of_date)`.

**Relationships:**
- `state_nomination_status.occupation_code` → `occupations.code`

**Source reference:** State government nomination pages (NSW/VIC/QLD/WA/SA) → `state_nomination_status`. Tier 5 (manual YAML curation — highest per-row curation effort; deliberately built last, per §11 build order).

**Status:** Target (migration `0013`).

---

### C13. list_change_log

**Purpose:** Change log of occupations being added to or removed from skilled occupation lists — MLTSSL, STSOL, ROL, and individual state lists.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `list_name` | `TEXT` | NOT NULL | e.g. `MLTSSL`, `STSOL`, `ROL`, or a state code like `NSW` |
| `occupation_code` | `TEXT` | NOT NULL | **FK** → `occupations.code` |
| `change_type` | `TEXT` | NOT NULL | `CHECK (change_type IN ('added','removed'))` |
| `effective_date` | `DATE` | NOT NULL | When the change took effect |
| `source_url` | `TEXT` | NOT NULL | Provenance trio |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | Provenance trio |
| `reliability_tier` | `TEXT` | NOT NULL, `'official_scraped'` | Provenance trio |

**Unique constraint:** `(list_name, occupation_code, change_type, effective_date)` — mirrors `eoi_rounds` dedup precedent.

**Relationships:**
- `list_change_log.occupation_code` → `occupations.code`

> **⚠ Audit (I12, F4, G7) — a change log with no source for `change_type` or
> `effective_date` produces zero rows on a cold start.**
>
> This table records *transitions*, but the register publishes *compilations* —
> point-in-time membership snapshots. With nothing to diff against, a first run
> has no changes to record, so the table starts empty and stays empty until a
> second compilation happens to land.
>
> **Resolved (G7, FOUND):** the **legislation.gov.au OData API** (catalog source
> 23) enumerates LIN 19/051's full **7-version compilation history** with
> effective dates and amendment reasons. Diff successive compilations to
> synthesise change rows, and take `effective_date` from the API directly rather
> than inferring it.
>
> **Still unopened:** LIN 19/051 epub **tables 7–11** are the instrument's own
> amendment history and may supply per-amendment effective dates without any
> diffing at all. Worth checking before building the diff machinery.
>
> **Missing companion table (F4):** current *membership* of MLTSSL (212), STSOL
> (215) and ROL (77) has **nowhere to land** — this change log is the only
> occupation-list table in the model. See C20.

**Source reference:** 
- Legislation.gov.au (MLTSSL/STSOL/ROL changes) → `list_change_log`. Tier 2 (deterministic HTML — HTML structure must be confirmed at build time, open design question #1).
- State occupation list change pages → `list_change_log`. Tier 1→5 (`source_pages` hash-diff triggers human review, YAML seed writes). 

**Status:** Target (migration `0014`).

---

### C14. processing_times

**Purpose:** Current visa processing time estimates — percentile-based days-to-decision per visa subclass and stream, as regularly published by Home Affairs.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `visa_code` | `TEXT` | NOT NULL | **FK** → `visa_subclasses.code` |
| `stream` | `TEXT` | NOT NULL | Multi-stream subclasses (485, 500, 482, 186) publish one estimate per stream — part of the identity, not a fidelity nicety |
| `as_of_date` | `DATE` | NOT NULL | Derived from fetch time, not the API payload — see decision note below |
| *(percentile fields)* | — | NOT NULL | Exact field set is pinned when #15 (the build ticket) inspects the live `GetProcessGuideInfo` payload — see decision note |
| `source_url` | `TEXT` | NOT NULL | Provenance trio |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | Provenance trio |
| `reliability_tier` | `TEXT` | NOT NULL, `'official_scraped'` | Provenance trio |

**Unique constraint:** `(visa_code, stream, as_of_date)`.

**Relationships:**
- `processing_times.visa_code` → `visa_subclasses.code`

**Source reference:** Processing times → `processing_times`, via the **`GetProcessGuideVisas` / `GetProcessGuideInfo` JSON API**. Tier 2 (`json_api`) — no HTML parsing.

> **✅ Decided 2026-08-23 (issue #11) — resolves the audit's two schema
> breaks.** The original spec (`median_days`, unique on `(visa_code,
> as_of_date)`) cannot be populated: the API returns a percentile
> distribution, not a median, and 76 subclass×stream combinations collide
> under a stream-less unique key for 485/500/482/186.
>
> **Decided:**
>
> | Change | Rationale |
> |---|---|
> | Add `stream TEXT NOT NULL`, include it in the unique constraint | Without it 76 real rows cannot coexist |
> | Drop `median_days`; model percentile fields instead | The API doesn't publish a median — storing one percentile under that name would misrepresent the source |
> | `as_of_date` derived from fetch time, not the payload | Not present in the API response; the page states the calculation window in prose only |
>
> **Deliberately not decided here:** the exact percentile column names/count
> (e.g. `p50_days`/`p90_days` vs. some other shape). Discovering that
> requires fetching the live `GetProcessGuideInfo` response, which is
> `#15`'s job (Phase B build), not a schema-shape decision — pinning field
> names against a guess risks getting them wrong twice. `#15`'s
> implementer adds the real column names as part of that ticket's
> migration.

**Status:** Target (migration `0015`).

---

### C15. program_allocation

**Purpose:** Annual migration program planning levels — how many places are allocated per stream (skilled independent, state nominated, employer sponsored, etc.).

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `program_year` | `TEXT` | NOT NULL | e.g. `2025-26` |
| `stream_name` | `TEXT` | NOT NULL | e.g. `Skilled Independent (189)`, `State/Territory Nominated (190)`, `Employer Sponsored` |
| `places` | `INTEGER` | NOT NULL | Number of places allocated |
| `source_url` | `TEXT` | NOT NULL | Provenance trio |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | Provenance trio |
| `reliability_tier` | `TEXT` | NOT NULL, `'official_curated'` | Provenance trio |

**Unique constraint:** `(program_year, stream_name)`.

**Relationships:** None — standalone aggregate table.

**Source reference:** Planning-levels PDF → `program_allocation` + `ceiling_usage`. Tier 5 (manual YAML curation — same PDF source as `ceiling_usage`).

**Status:** Target (migration `0016`).

---

### C16. application_funnel

**Purpose:** Visa application volumes at each funnel stage — submitted, invited, granted — per visa subclass and program year.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `visa_code` | `TEXT` | NOT NULL | **FK** → `visa_subclasses.code` |
| `program_year` | `TEXT` | NOT NULL | e.g. `2025-26` |
| `as_of_date` | `DATE` | NOT NULL | The date this snapshot reflects |
| `submitted_count` | `INTEGER` | NULL | EOI/lodgement count |
| `invited_count` | `INTEGER` | NULL | Invitations issued this period |
| `granted_count` | `INTEGER` | NULL | Visas granted (weakest-sourced; may be NULL) |
| `source_url` | `TEXT` | NOT NULL | Provenance trio (for submitted/invited) |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | Provenance trio (for submitted/invited) |
| `reliability_tier` | `TEXT` | NOT NULL, `'official_scraped'` | Provenance trio (for submitted/invited) |
| `granted_source_url` | `TEXT` | NULL | **Second provenance trio** — scoped to `granted_count` |
| `granted_retrieved_at` | `TIMESTAMPTZ` | NULL | Second provenance trio |
| `granted_reliability_tier` | `TEXT` | NULL | Second provenance trio (typically `official_curated`) |

**Unique constraint:** `(visa_code, program_year, as_of_date)`.

**Funnel-order check:** Where both sides non-null: `submitted_count >= invited_count >= granted_count`.

**Second provenance trio:** `submitted_count`/`invited_count` come from a monthly `official_scraped` SkillSelect page; `granted_count` comes from an annual `official_curated` PDF — two sources on one row require a second, nullable provenance triple scoped to `granted_count` alone (open design question #3).

**Relationships:**
- `application_funnel.visa_code` → `visa_subclasses.code`

**Source reference:**
- SkillSelect rounds → `application_funnel.invited_count`. Tier 2 (piggybacked on existing SkillSelect fetch — don't fetch the same URL twice).
- **BP0068 (data.gov.au, CC-BY 2.5)** → `application_funnel.granted_count`. Tier 2 (`xlsx_pivot_cache`), replacing the annual PDF.

> **⚠ Audit (G9 FOUND, G10 NOT PUBLISHED) — one column got much better, one is
> gone for good.**
>
> **`granted_count` — from "weakest-sourced, probably NULL" to fully sourced.**
> Home Affairs publishes **BP0068** on data.gov.au under **CC-BY 2.5**:
> **622,425 records**, **10 program years**, **62 visa subclasses**, **764
> ANZSCO-coded occupations**. No PDF parsing required, and it is annually
> refreshed. Update `granted_reliability_tier` from `official_curated` to
> **`official_scraped`** — this is now a machine-readable official dataset.
>
> ⚠ **Retrieval:** the data lives in the workbook's **pivot cache**, not its
> worksheets. `pandas`/`openpyxl` return nothing useful; a stdlib XML reader
> parses all records in ~4.8s.
>
> **`submitted_count` — NO SOURCE, permanently.** Not published in any form:
> the decoded SkillSelect page was searched for `submitted`, `lodged`,
> `EOIs on hand`, `EOIs in the system` and `pool` with **zero matches**, and
> none of Home Affairs' 12 data.gov.au datasets is a SkillSelect/EOI dataset.
> Record it as unavailable, not pending.
>
> **Consequence for the funnel-order check:** with `submitted_count` always
> NULL, `submitted >= invited >= granted` degrades to `invited >= granted`. Keep
> the check null-tolerant rather than dropping it.
>
> **Grain mismatch to resolve:** `invited_count` is per round/subclass;
> BP0068's `granted_count` is per program year/subclass/occupation. The unique
> key `(visa_code, program_year, as_of_date)` fits neither cleanly.

### ✅ Built 2026-08-18 — migration `0011`, 432 rows

622,425 BP0068 records aggregated to **(visa_code, program_year)**:
10 program years × 62 subclasses, 1,710,097 grants.

**Three deliberate deviations from the specification above.** Each is a
decision, not an oversight:

| Deviation | Reason |
|---|---|
| **Unique key is `(visa_code, program_year)`**, with no `as_of_date` | BP0068 is an annual restatement, not a time series of snapshots. An `as_of_date` in the key would accumulate a new row set per run instead of updating. |
| **One provenance trio, not two** | The dual trio assumed submitted/invited and granted come from different sources on the same row. Only `granted_count` is sourced, so one trio describes the row honestly. A second is added when `invited_count` lands. |
| **No `granted_count >= 0` check** | BP0068 is confidentialised (`masked` in its own filename): small cells are perturbed and one real row — subclass 110 Interdependency, 2019-20 — reports **-2**. It is stored as published; clamping would fabricate data to satisfy an assumption the source does not share. The parser warns, so a *rise* in such rows reads as a parsing bug rather than a privacy artefact. |

`submitted_count` ships NULL **permanently** (G10, not published in any form).
`invited_count` ships NULL pending grain reconciliation with `eoi_rounds`.

**Status:** Target (migration `0017`).

---

### C17. eligibility_requirements

**Purpose:** Prose reference for the three near-static eligibility requirements — health, character, and English language — cited from government pages, not tabular data.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `requirement_type` | `TEXT` | NOT NULL | **UNIQUE**; `CHECK (requirement_type IN ('health','character','english_language'))` |
| `summary` | `TEXT` | NOT NULL | Curated prose summary of the requirement |
| `source_url` | `TEXT` | NOT NULL | Provenance trio |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | Provenance trio |
| `reliability_tier` | `TEXT` | NOT NULL, `'official_curated'` | Provenance trio |

**Relationships:** None — standalone reference table (3 rows, near-static).

**Source reference:** Health/character/English requirement pages → `eligibility_requirements`. Tier 5 (manual YAML curation — 3 near-static prose pages, not tabular data).

**Status:** Target (migration `0018`).

---

### C18. skills_priority_ratings

**Purpose:** Jobs and Skills Australia's occupation shortage and future-demand ratings — conceptually distinct from MLTSSL/STSOL/ROL list membership.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `occupation_code` | `TEXT` | NOT NULL | **FK** → `occupations.code` |
| `shortage_rating` | `TEXT` | NOT NULL | `CHECK (shortage_rating IN ('S','M','R','NS'))` — confirmed, see audit block |
| `future_demand_rating` | `TEXT` | NULL | **NO SOURCE** — JSA's `d` field is null throughout |
| `as_of_date` | `DATE` | NOT NULL | The date this rating reflects |
| `source_url` | `TEXT` | NOT NULL | Provenance trio |
| `retrieved_at` | `TIMESTAMPTZ` | NOT NULL | Provenance trio |
| `reliability_tier` | `TEXT` | NOT NULL, `'official_scraped'` | Provenance trio |

**Unique constraint:** `(occupation_code, as_of_date)`.

**Note:** ~~Exact rating vocabulary must be confirmed at implementation time~~ — **closed 2026-08-17**, see the audit block below (open design question #2 resolved).

**Relationships:**
- `skills_priority_ratings.occupation_code` → `occupations.code`

**Source reference:** JSA Occupation Shortage List → `skills_priority_ratings`, via the embedded `splData` / `splSearch` JSON. Tier 2 (deterministic).

> **⚠ Audit (F7, G11) — vocabulary resolved; one column has no source.**
>
> **`shortage_rating` has exactly four values**, confirmed from JSA's own
> methodology PDF — the earlier "confirm vocabulary at build time" flag is
> closed:
>
> | Code | Meaning |
> |---|---|
> | `S` | Shortage |
> | `M` | Metropolitan shortage |
> | `R` | Regional shortage |
> | `NS` | No shortage |
>
> `Ns` appearing in the payload is a **casing bug**, not a fifth value —
> normalise case before applying the CHECK constraint, or valid rows will be
> rejected as invalid.
>
> **`future_demand_rating` — NO SOURCE.** The `d` field in `splData` is null
> throughout. Ship NULL or drop the column.
>
> **Missing dimensions (F7):** JSA publishes ratings against **both ANZSCO and
> OSCA**, at **both 4- and 6-digit** grain, and per **edition** and
> **jurisdiction** (the `M`/`R` split is itself geographic). Add
> `jurisdiction`, `edition` and a code-grain marker, or rows from different
> vocabularies will silently collide on the same `occupation_code`.

**Status:** Target (migration `0019`).

---

## C19–C22. Entities added by the 2026-08-17 audit

Four tables the model lacked. Each exists because verified data has nowhere to
land, or because a join cannot be expressed without it.

---

### C19. anzsco_osca_crosswalk

**Purpose:** Carry the ANZSCO→OSCA relationship without a destructive migration
of `occupations` (F3).

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `anzsco_code` | `TEXT` | NOT NULL | **FK** → `occupations.code` |
| `anzsco_edition` | `TEXT` | NOT NULL | `2013` \| `2022` |
| `osca_code` | `TEXT` | NOT NULL | OSCA 2024 code |
| `is_partial_match` | `BOOLEAN` | NOT NULL, `false` | ABS's `p` flag |
| `source_url` / `retrieved_at` / `reliability_tier` | — | NOT NULL | Provenance trio |

**Source:** ABS `OSCA correspondence tables v2.xlsx` (catalog source 19), which
carries both **ANZSCO v1.3 → OSCA** and **ANZSCO 2022 → OSCA**.

⚠ **The mapping is not one-to-one** — OSCA has 1,577 entries vs ANZSCO's 1,236,
and ABS marks partial matches with `p`. A naive join silently drops or
duplicates occupations, so `is_partial_match` must be preserved and surfaced.

---

### C20. occupation_list_membership

**Purpose:** Current membership of MLTSSL / STSOL / ROL / CSOL (F4). The model
had only `list_change_log`, which records *transitions* — so a cold start
produced zero rows and there was nowhere to store present-day membership.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `list_name` | `TEXT` | NOT NULL | `CHECK (list_name IN ('MLTSSL','STSOL','ROL','CSOL'))` |
| `occupation_code` | `TEXT` | NOT NULL | **FK** → `occupations.code` |
| `anzsco_edition` | `TEXT` | NOT NULL | LIN 19/051 is **2013**; CSOL is **2022** |
| `compilation_date` | `DATE` | NOT NULL | Which compilation this reflects |
| `source_url` / `retrieved_at` / `reliability_tier` | — | NOT NULL | Provenance trio |

**Unique constraint:** `(list_name, occupation_code, compilation_date)`.

**Source:** LIN 19/051 epub tables; CSOL from `F2024L01618`.
**Verified volumes:** MLTSSL **212**, STSOL **215**, ROL **77**.

`list_change_log` becomes a *derivative* of this table — diff two
`compilation_date`s — rather than a separately-sourced table.

---

### C21. visa_fees

**Purpose:** Promote fees off `visa_subclasses` (F6). 150 fee records cannot
live as one scalar column on a 6-row table, and fees vary by stream.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `visa_code` | `TEXT` | NOT NULL | **FK** → `visa_subclasses.code` |
| `stream` | `TEXT` | NULL | Fees differ per stream |
| `applicant_type` | `TEXT` | NOT NULL | Primary / secondary / child |
| `amount_aud` | `NUMERIC(10,2)` | NOT NULL | — |
| `effective_date` | `DATE` | NOT NULL | Indexed annually on 1 July |
| `source_url` / `retrieved_at` / `reliability_tier` | — | NOT NULL | Provenance trio |

**Source:** `POST /_layouts/15/api/data.aspx/GetPriceList` — **150 records**,
`json_api` strategy.

---

### C22. occupation_titles

**Purpose:** The name→code crosswalk that unblocks `eoi_rounds` (G1). Kept as a
table, not inline logic, because two sources disagree and the resolution order
is load-bearing.

| Column | PostgreSQL Type | Nullable / Default | Constraints |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | **PK**, `auto_increment` |
| `title` | `TEXT` | NOT NULL | As published by the source, verbatim |
| `title_normalized` | `TEXT` | NOT NULL, indexed | Case/whitespace-folded, footnote markers stripped — what lookups match on |
| `occupation_code` | `TEXT` | NOT NULL | **No FK** — see below |
| `title_source` | `TEXT` | NOT NULL | `CHECK (title_source IN ('LIN_19_051','ABS_ANZSCO'))` |
| `anzsco_edition` | `TEXT` | NOT NULL | `2013` (LIN) or `2022` (ABS) |
| `source_url` / `retrieved_at` / `reliability_tier` | — | NOT NULL | Provenance trio |

**Unique constraint:** `(title_normalized, title_source)` — deliberately *not*
`(title)`, because the same title legitimately maps to different codes in the
two sources. Normalised rather than raw, so the constraint matches how lookups
actually compare.

> ### ⚠ Correction: this table has NO foreign key to `occupations.code`
>
> An earlier revision of this doc specified `occupation_code` as
> `FK → occupations.code`. **That is wrong and was not built.** The crosswalk
> is a *reference mapping* and legitimately names codes koshi's occupation
> table does not carry:
>
> - LIN 19/051 is coded against ANZSCO **2013**; 25 of its codes are absent
>   from 2022.
> - ABS Table 6 is the **coder list**, including non-occupations such as
>   `099960 Retired`.
>
> With an FK, loading the crosswalk aborts on those rows. The FK belongs on
> the *consumer* (`eoi_rounds.occupation_code`), and the pipeline checks
> `occupations` membership before writing a resolved code there — see the
> resolution note below.

**Live volume (2026-08-18):** 1,929 rows (1,425 ABS + 504 LIN).

**Resolution rule — LIN-first.** Three titles (**Management Consultant**,
**Plumber (General)**, **Statistician**) resolve to different codes in the two
sources. LIN 19/051 is the binding instrument, so it wins. An ABS-first
implementation returns wrong codes for these three **without erroring**, which
is why the rule is recorded in the schema rather than left to the parser.

Coverage: ABS alone 132/140, LIN alone 132/140, **union 140/140** — measured
against a live invitation round, not assumed.

**Resolution writes only codes that exist in `occupations`.** Because
`eoi_rounds.occupation_code` *is* an FK, a resolved-but-absent code would
abort the whole batch. Unresolved rows keep `occupation_name_raw` and are
retried by the `backfill_round_codes` pipeline step, since the crosswalk
grows independently of the source pages.

**Normalisation** strips trailing footnote markers (`*`, `+`, `†`, …):
SkillSelect annotates names against notes under the table
(`Medical Radiation Therapist+`), which is presentation, not part of the name.

---

## Provenance & Derived Conventions

### The Provenance Trio

Every fact table carries these last three columns:

| Column | Meaning |
|---|---|
| `source_url` | The exact URL the row was extracted from (or the PDF/manual source URL) |
| `retrieved_at` | UTC timestamp of acquisition |
| `reliability_tier` | One of four values (see below) |

### Reliability Tier Values

| Value | Meaning | Used By |
|---|---|---|
| `official_scraped` | Directly extracted from an official government HTML page | `occupations`, `eoi_rounds`, `english_test_bands`, `points_criteria_reference`, `processing_times`, `skills_priority_ratings`, `list_change_log` (legislation.gov.au), `application_funnel` (submitted/invited) |
| `official_curated` | Human-reviewed from an official source (PDF, complex page, or manual tracking) | `ceiling_usage`, `visa_subclasses`, `assessing_bodies`, `occupation_assessing_bodies`, `policy_events`, `state_nomination_status`, `program_allocation`, `eligibility_requirements`, `application_funnel.granted_count` |
| `derived` | Computed from other koshi rows — cites those rows, not an external URL | `occupation_momentum` (the only derived table today) |
| `community_sourced` | Reserved for a future non-official source | Nothing uses this yet |

### Derived Table Rules

1. **Only `occupation_momentum` is derived** — all other fact tables carry a genuine external source URL.
2. Derived tables **omit `source_url`** entirely — the `reliability_tier = 'derived'` signals that the source is koshi's own computation.
3. Derived computations cite the rows they were computed from (e.g., `occupation_momentum` is computed from `eoi_rounds.threshold_points` history — the `computed_at` timestamp and the `occupation_code` FK are the implicit citation).

### Special Provenance Cases

1. **`application_funnel` dual provenance** — two sources on one row (`submitted`/`invited` from scraped SkillSelect; `granted_count` from curated annual PDF) require a second nullable provenance triple (`granted_source_url`, `granted_retrieved_at`, `granted_reliability_tier`). This is a deliberate schema extension beyond the single-triple convention (open design question #3).

2. **`visa_subclasses.base_application_cost`** — a tier-2-scraped fee value written onto an `official_curated` row erases the fee's true source. Open question #5: consider a separate `visa_fees` time-series table or a second provenance triple scoped to `base_application_cost`.

3. **`source_pages` no provenance** — this is metadata, not a fact. It is the registry of *where* facts come from; it does not itself carry the trio.

### The verified-citation rule (added 2026-08-18)

**A `source_url` must point at a page that actually contains the fact.**

This sounds tautological. It was violated in production, and the existing checks
could not catch it.

Two `ceiling_usage` rows shipped citing the migration-program planning-levels
page. That page contains a visa-category table and no per-occupation ceilings —
the numbers were never on it. `require_provenance` passed, because it tests that
`source_url` and `retrieved_at` are **non-null**, not that the citation is
**true**. The API then served those values as `official_curated` `SourcedFact`s,
where a consumer could not distinguish them from verified government data.

Provenance that points somewhere plausible but wrong is **worse than a NULL**: a
NULL is honest about not knowing, while a false citation actively transfers the
government's credibility onto an invented number. For a product whose entire
regulatory posture rests on "we only report what official sources say", this is
the failure mode that matters most.

**Rules:**

| Rule | Applies to |
|---|---|
| Every manually-curated row must name the **specific table, section or page number** within the cited document — not just the document | Tier 5 seeds |
| A seed file whose source becomes unavailable must be **emptied**, not left in place | Tier 5 seeds |
| **NO SOURCE** columns ship NULL and are documented as unavailable, never as pending | All tables |
| A citation whose page no longer contains the fact is a **data incident**, not a stale link | All tables |

**Detection is a fetcher concern too.** `budget.gov.au/content/migration.htm`
returns **HTTP 200 with a "Page not found" body** — a soft-404 that a
status-code-only check passes silently. The fetcher must assert on body content.

**Columns currently marked NO SOURCE:** `ceiling_usage.*` (whole table),
`application_funnel.submitted_count`, `assessing_bodies.turnaround_estimate`
and `.cost`, `skills_priority_ratings.future_demand_rating`,
`visa_subclasses.permanence`, and most of `state_nomination_status`.

### Snapshot vs. Overwrite (Open Design Question #9)

Most reference tables do not specify whether a change **overwrites** (losing prior value + `retrieved_at`) or **appends** (keeping history). Per-table decision required at build time:

| Table | Strategy | Rationale |
|---|---|---|
| `occupations` | Upsert-by-PK (overwrite) | ANZSCO name changes are corrections, not history |
| `visa_subclasses` | Upsert-by-PK (overwrite) | Reference facts, not time-series |
| `ceiling_usage` | Append (new row per `as_of_date`) | Time-series — need history |
| `processing_times` | Append (new row per `as_of_date`) | Time-series — need history |
| `eoi_rounds` | Append (unique constraint on natural key) | Time-series — one row per round |
| `state_nomination_status` | Append (unique constraint includes `as_of_date`) | Time-series — status changes over time |
| `list_change_log` | Append-only (log) | It *is* a log |

---

## Table Index

| # | Table | Plane | Medallion | Status | Migration |
|---|---|---|---|---|---|
| A1 | `sources` | Control | — | Target | — |
| A2 | `resources` | Control | — | Target | — |
| A3 | `extraction_strategies` | Control | — | Target | — |
| A4 | `contracts` | Control | — | Target | — |
| A5 | `quality_policies` | Control | — | Target | — |
| A6 | `schedules` | Control | — | Target | — |
| B1 | `snapshots` | Data | Bronze | Target | — |
| B2 | `snapshot_manifests` | Data | Bronze | Target | — |
| B3 | `pipeline_runs` | Data | Silver | Target | — |
| B4 | `quarantine` | Data | Silver | Target | — |
| B5 | `dataset_releases` | Data | Gold | Target | — |
| C1 | `occupations` | Domain | Silver | ✅ Built | 0001 |
| C2 | `eoi_rounds` | Domain | Silver | ✅ Built | 0002 |
| C3 | `ceiling_usage` | Domain | Silver | ✅ Built | 0003 |
| C4 | `occupation_momentum` | Domain | Gold | ✅ Built | 0004 |
| C5 | `source_pages` | Domain | Bronze | ✅ Built | 0005 |
| C6 | `visa_subclasses` | Domain | Silver | ✅ Built | **0011** |
| C7 | `english_test_bands` | Domain | Silver | Target | — |
| C8 | `assessing_bodies` | Domain | Silver | Target | — |
| C9 | `occupation_assessing_bodies` | Domain | Silver | Target | — |
| C10 | `points_criteria_reference` | Domain | Silver | Target | — |
| C11 | `policy_events` | Domain | Silver | Target | — |
| C12 | `state_nomination_status` | Domain | Silver | Target | — |
| C13 | `list_change_log` | Domain | Silver | Target | — |
| C14 | `processing_times` | Domain | Silver | Target | — |
| C15 | `program_allocation` | Domain | Silver | Target | — |
| C16 | `application_funnel` | Domain | Silver | ✅ Built | **0011** |
| C17 | `eligibility_requirements` | Domain | Silver | Target | — |
| C18 | `skills_priority_ratings` | Domain | Silver | Target | — |
| C19 | `anzsco_osca_crosswalk` | Domain | Silver | Target | — |
| C20 | `occupation_list_membership` | Domain | Silver | Target | — |
| C21 | `visa_fees` | Domain | Silver | Target | — |
| C22 | `occupation_titles` | Domain | Silver | ✅ Built | **0009** |

**Migration numbers for unbuilt tables are now `—` rather than a planned
number.** The original 0007–0019 allocation assumed tables would land in
catalog order; they have not, and a stale planned number is worse than none.
Actual chain to date:

| Migration | What it did |
|---|---|
| `0001`–`0006` | Original occupation slice + fault-tolerance retrofit |
| `0007` | `eoi_rounds.occupation_name_raw`; unique key moved onto the name |
| `0008` | `occupations.code_grain` |
| `0009` | `occupation_titles` (C22) |
| `0010` | `occupations.anzsco_edition` |
| `0011` | `visa_subclasses` (C6) + `application_funnel` (C16) |

**Total: 33 entities** (6 control-plane, 5 data-plane, 22 domain-fact) —
C19–C22 were added by the 2026-08-17 audit.

**Built as of 2026-08-18: 8 tables** — C1–C6 (`source_pages` is C5, not a
separate ninth table), plus C16 and C22.
Every other row above is specification, not code.

---

## Document History

| Date | Change |
|---|---|
| 2026-08-16 | Initial: complete data model synthesized from `feedback.md` (control/data plane), `2026-08-16-koshi-etl-architecture.md` §6 (domain tables), and `2026-08-15-koshi-etl-finalization-design.md` §4 (domain definitions). |