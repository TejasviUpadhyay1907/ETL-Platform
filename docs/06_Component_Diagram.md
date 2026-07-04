# Component Diagram
## Enterprise ETL & Data Quality Platform

**Version:** 1.0.0  

---

## Overview

This document describes every system component, its internal structure, its external interface, and how it interacts with other components. Components are grouped by system layer.

---

## Component Map

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                         PRESENTATION LAYER                                    ║
║                                                                               ║
║  ┌─────────────────────────────┐   ┌─────────────────────────────────────┐  ║
║  │        WEB DASHBOARD         │   │       EXTERNAL API CONSUMERS         │  ║
║  │  (Jinja2 / HTMX Templates)   │   │  (BI Tools, Scripts, Downstream      │  ║
║  │                               │   │   Systems)                           │  ║
║  └──────────────┬────────────────┘   └─────────────────┬───────────────────┘  ║
╚═════════════════╪═══════════════════════════════════════╪═════════════════════╝
                  │ HTTP                                   │ HTTP
╔═════════════════▼═══════════════════════════════════════▼═════════════════════╗
║                           SERVICE LAYER                                        ║
║                                                                               ║
║  ┌────────────────────────────────────────────────────────────────────────┐  ║
║  │                         REST API LAYER (FastAPI)                        │  ║
║  │                                                                         │  ║
║  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │  ║
║  │  │  /ingest     │  │  /pipelines  │  │  /data       │  │  /reports  │  │  ║
║  │  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘  │  ║
║  │  ┌───────────────────────────────────────────────────────────────────┐  │  ║
║  │  │  AuthMiddleware │ RateLimitMiddleware │ RequestValidator            │  │  ║
║  │  └───────────────────────────────────────────────────────────────────┘  │  ║
║  └──────────────────────────────────┬─────────────────────────────────────┘  ║
║                                     │                                         ║
║  ┌──────────────────────────────────▼─────────────────────────────────────┐  ║
║  │                        REPORTING MODULE                                  │  ║
║  │  DataQualityReportBuilder │ BusinessSummaryReportBuilder │ ReportExporter │  ║
║  └──────────────────────────────────┬─────────────────────────────────────┘  ║
╚═════════════════════════════════════╪═════════════════════════════════════════╝
                                      │
╔═════════════════════════════════════▼═════════════════════════════════════════╗
║                          PROCESSING LAYER                                      ║
║                                                                               ║
║  ┌────────────────────────────────────────────────────────────────────────┐  ║
║  │                        PIPELINE ENGINE                                   │  ║
║  │            PipelineRunner │ StageExecutor │ PipelineScheduler            │  ║
║  └──────┬─────────────┬────────────┬─────────────┬──────────────────────┘  ║
║         │             │            │             │                           ║
║         ▼             ▼            ▼             ▼                           ║
║  ┌────────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  ┌─────────────┐  ║
║  │ INGESTION  │ │VALIDATION│ │ CLEANING │ │TRANSFORMAT-│  │   DATA      │  ║
║  │  MODULE    │ │ ENGINE   │ │  ENGINE  │ │ION ENGINE  │  │   LOADER    │  ║
║  │            │ │          │ │          │ │            │  │             │  ║
║  │FileDetector│ │SchemaVal.│ │Dedup.    │ │Transformer │  │UpsertManager│  ║
║  │TypeResolver│ │RuleEngine│ │NullHandle│ │Registry    │  │TxManager    │  ║
║  │RawFileStore│ │Annotator │ │Normalizer│ │FieldMapper │  │             │  ║
║  └──────┬─────┘ └──────────┘ └──────────┘ └────────────┘  └─────────────┘  ║
╚══════════╪════════════════════════════════════════════════════════════════════╝
           │
╔══════════▼════════════════════════════════════════════════════════════════════╗
║                           STORAGE LAYER                                        ║
║                                                                               ║
║  ┌─────────────────────────────┐   ┌────────────────────────────────────┐   ║
║  │       FILE SYSTEM            │   │          POSTGRESQL DATABASE        │   ║
║  │                              │   │                                     │   ║
║  │  data/                       │   │  Operational Tables:                │   ║
║  │  ├── raw/                    │   │  orders, customers, products,       │   ║
║  │  ├── reports/                │   │  inventory, suppliers, payments     │   ║
║  │  └── archive/                │   │                                     │   ║
║  │                              │   │  Pipeline Tables:                   │   ║
║  │                              │   │  pipeline_runs, stage_results,      │   ║
║  │                              │   │  ingestion_events, reports          │   ║
║  │                              │   │                                     │   ║
║  │                              │   │  Audit Tables:                      │   ║
║  │                              │   │  audit_log, validation_failures,    │   ║
║  │                              │   │  cleaning_log, quality_scores       │   ║
║  └─────────────────────────────┘   └────────────────────────────────────┘   ║
╚═══════════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════════╗
║                        CROSS-CUTTING COMPONENTS                               ║
║                                                                               ║
║  ┌──────────────────────────┐   ┌─────────────────────────────────────────┐ ║
║  │   CONFIGURATION MODULE    │   │         AUDIT & LOGGING MODULE           │ ║
║  │  AppConfig │ DatasetConfig│   │  StructuredLogger │ AuditEventEmitter    │ ║
║  │  ConfigLoader │ Registry  │   │  PIIMasker │ LogRotationHandler          │ ║
║  └──────────────────────────┘   └─────────────────────────────────────────┘ ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

---

## Component Interaction Matrix

| Component | Interacts With | Nature of Interaction |
|---|---|---|
| Web Dashboard | REST API Layer | HTTP requests (all data via API) |
| External Consumers | REST API Layer | HTTP requests |
| REST API Layer | Pipeline Engine | Trigger pipeline runs, query run status |
| REST API Layer | Database Layer | Query operational and metadata tables |
| REST API Layer | Reporting Module | Trigger report generation, serve downloads |
| REST API Layer | Configuration Module | Read API settings |
| REST API Layer | Logging Module | Log all requests and errors |
| Pipeline Engine | Ingestion Module | Invoke ingestion stage |
| Pipeline Engine | Validation Engine | Invoke validation stage, receive stage result |
| Pipeline Engine | Cleaning Engine | Invoke cleaning stage, receive stage result |
| Pipeline Engine | Transformation Engine | Invoke transformation stage, receive stage result |
| Pipeline Engine | Data Loader | Invoke loading stage, receive stage result |
| Pipeline Engine | Database Layer | Write pipeline_runs and stage_results |
| Pipeline Engine | Reporting Module | Trigger report generation on run completion |
| Pipeline Engine | Logging Module | Log stage transitions and run events |
| Ingestion Module | File System | Write raw files |
| Ingestion Module | Database Layer | Write ingestion_events |
| Ingestion Module | Configuration Module | Read ingestion settings |
| Validation Engine | Configuration Module | Read schema and rule definitions |
| Validation Engine | Database Layer | Write validation_failures |
| Cleaning Engine | Configuration Module | Read cleaning rules |
| Cleaning Engine | Database Layer | Write cleaning_log |
| Transformation Engine | Database Layer | Read reference/lookup data |
| Transformation Engine | Configuration Module | Read transformation rules |
| Data Loader | Database Layer | Write to operational tables (upsert) |
| Reporting Module | Database Layer | Read stage results, quality scores, business data |
| Reporting Module | File System | Write report files |
| Audit & Logging Module | Database Layer | Write audit_log records |
| Configuration Module | File System | Read YAML config and dataset config files |

---

## Component Detail Cards

### REST API Layer

**Interface:** HTTP/JSON on port 8000 (configurable)  
**Technology:** FastAPI  
**Key Internal Classes:** `APIRouter` instances, `AuthMiddleware`, `RateLimitMiddleware`, `ResponseBuilder`, `ErrorHandler`  
**Exposes:**
- `POST /api/v1/ingest/upload` — file upload
- `POST /api/v1/pipelines/trigger` — trigger pipeline
- `GET /api/v1/pipelines/{run_id}` — run status
- `GET /api/v1/pipelines` — run history list
- `GET /api/v1/data/{dataset_type}` — paginated data query
- `GET /api/v1/quality/{run_id}` — quality metrics
- `GET /api/v1/reports` — report list
- `GET /api/v1/reports/{report_id}/download` — report download
- `GET /api/v1/health` — health check

---

### Pipeline Engine

**Interface:** Internal Python method calls + Scheduler  
**Technology:** Python, APScheduler  
**Key Internal Classes:** `PipelineRunner`, `StageExecutor`, `PipelineContext`, `PipelineScheduler`, `PipelineTriggerService`  
**Run Lifecycle:**
1. Receive trigger (manual API or scheduler)
2. Create PipelineRun record
3. Execute stages sequentially via StageExecutor
4. Capture StageResult after each stage
5. Handle exceptions per stage without cascading failure
6. Update PipelineRun to final status
7. Trigger Reporting Module

---

### Validation Engine

**Interface:** Internal Python — `validate(df, dataset_type) → ValidationResult`  
**Technology:** Python, pandas  
**Key Internal Classes:** `SchemaValidator`, `BusinessRuleEngine`, `RuleRegistry`, `ValidationAnnotator`, `QualityScoreCalculator`  
**Rule Loading:** Rules loaded from `config/datasets/{dataset_type}/rules.yaml` at startup  
**Rule Interface:** Each rule is an object with `rule_code`, `description`, `severity`, and `validate(row) → bool`

---

### Cleaning Engine

**Interface:** Internal Python — `clean(df, dataset_type) → CleaningResult`  
**Technology:** Python, pandas  
**Key Internal Classes:** `DeduplicationHandler`, `NullHandler`, `StringNormalizer`, `DateStandardizer`, `NumericCleaner`, `CleaningActionLogger`  
**Cleaning Config:** Per-field strategies loaded from `config/datasets/{dataset_type}/cleaning.yaml`

---

### Transformation Engine

**Interface:** Internal Python — `transform(df, dataset_type) → TransformationResult`  
**Technology:** Python, pandas  
**Key Internal Classes:** `TransformerRegistry`, `BaseTransformer` (abstract), dataset-specific transformers, `FieldMapper`, `DerivedFieldCalculator`, `LookupEnricher`  
**Extension Point:** New dataset transformers registered via the `TransformerRegistry` without modifying existing code

---

### Database Layer

**Interface:** Internal Python — Repository classes with typed methods  
**Technology:** SQLAlchemy 2.x, PostgreSQL 15+, Alembic  
**Key Internal Classes:** `DatabaseEngine`, `BaseRepository`, domain repositories, `UpsertManager`, `TransactionManager`  
**Access Pattern:** Only repository classes interact with the database. No raw SQL in business logic layers.

---

### Configuration Module

**Interface:** `ConfigRegistry.get() → AppConfig`  
**Technology:** Pydantic BaseSettings, PyYAML  
**Key Internal Classes:** `AppConfig`, `DatasetConfig`, `ConfigLoader`, `ConfigValidator`, `ConfigRegistry`  
**Config Sources (priority order, highest last):** YAML defaults → environment variables  
**Dataset configs:** `config/datasets/{dataset_type}/schema.yaml`, `rules.yaml`, `cleaning.yaml`, `transformations.yaml`

---

### Audit & Logging Module

**Interface:** `get_logger(component_name) → StructuredLogger`  
**Technology:** structlog, Python logging  
**Key Internal Classes:** `StructuredLogger`, `AuditEventEmitter`, `PIIMasker`, `LogRotationHandler`  
**Log Format:** JSON-structured log lines on stdout and to `logs/app.log`  
**Audit Events:** Written to both log file and `audit_log` database table
