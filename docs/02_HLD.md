# High-Level Design (HLD)
## Enterprise ETL & Data Quality Platform

**Version:** 1.0.0  
**Status:** Approved for Architecture Review  

---

## Table of Contents

1. Overall System Architecture
2. Major Components
3. Component Responsibilities
4. Inter-Component Communication
5. Technology Choices and Rationale
6. Scalability Considerations
7. Reliability Considerations
8. Security Considerations
9. Performance Considerations

---

## 1. Overall System Architecture

The system follows a **layered, modular pipeline architecture** with clear separation between ingestion, processing, storage, serving, and presentation concerns.

The architecture is organized into five horizontal tiers:

```
┌─────────────────────────────────────────────────────────────────┐
│                        PRESENTATION TIER                         │
│              Web Dashboard  |  REST API Consumers                │
├─────────────────────────────────────────────────────────────────┤
│                         SERVICE TIER                             │
│              REST API Layer  |  Report Service                   │
├─────────────────────────────────────────────────────────────────┤
│                        PROCESSING TIER                           │
│  Pipeline Engine → Ingestion → Validation → Cleaning →           │
│                  Transformation → Loading                        │
├─────────────────────────────────────────────────────────────────┤
│                         STORAGE TIER                             │
│        PostgreSQL Database  |  File System (Raw / Archive)       │
├─────────────────────────────────────────────────────────────────┤
│                     INFRASTRUCTURE TIER                          │
│         Docker Compose  |  Configuration  |  Logging             │
└─────────────────────────────────────────────────────────────────┘
```

The platform uses a **event-driven pipeline model** internally, where each pipeline stage emits a stage result object that drives the next stage. The pipeline engine acts as the orchestrator, invoking stages sequentially while capturing state at each transition.

All external interactions flow through the REST API or the web dashboard. Direct database access from consumers is not permitted.

---

## 2. Major Components

The platform consists of twelve major components:

| Component | Layer | Role |
|---|---|---|
| File Ingestion Module | Processing | Accept, validate format, and store raw files |
| Pipeline Engine | Processing | Orchestrate all stages of ETL execution |
| Validation Engine | Processing | Enforce schema and business rule validation |
| Cleaning Engine | Processing | Remove errors, normalize formats, deduplicate |
| Transformation Engine | Processing | Apply business logic and produce target schema |
| Data Loader | Processing | Write clean records to PostgreSQL |
| Database Layer | Storage | Relational storage with full schema management |
| REST API Layer | Service | HTTP interface for all external interactions |
| Reporting Module | Service | Generate quality and business reports |
| Dashboard | Presentation | Web interface for operational visibility |
| Audit & Logging Module | Cross-Cutting | Structured logging across all stages |
| Configuration Module | Cross-Cutting | Centralized, environment-aware configuration |

---

## 3. Component Responsibilities

### 3.1 File Ingestion Module

Accepts raw files from two sources: web upload through the API, and automated directory polling. Responsible for format detection, basic structural validation (is this a valid CSV/Excel file?), persisting the raw file to a versioned storage location, and emitting an ingestion event that triggers the pipeline. Does not perform business validation — that belongs to the Validation Engine.

### 3.2 Pipeline Engine

The central orchestrator. Responsible for creating and managing pipeline run records, sequencing stage execution in the correct order, capturing stage outputs and passing them to the next stage, handling stage failures with appropriate error isolation, and persisting run state to the database so runs are resumable and auditable. The pipeline engine is stateless — all state lives in the database.

### 3.3 Validation Engine

Receives a raw DataFrame from the Ingestion Module. Applies two types of checks: structural validation (required columns present, correct data types) and business rule validation (order total must be positive, customer email must be valid format, etc.). Produces a validated DataFrame containing only passing records, a rejected DataFrame containing failing records with failure reason codes, and a validation summary report.

### 3.4 Cleaning Engine

Receives the validated DataFrame. Applies cleaning transformations: duplicate removal, null handling per field-level strategy (drop row / fill default / flag), string normalization (trim, case standardization), date format parsing and standardization, numeric format cleaning (strip currency symbols, commas). Produces a clean DataFrame and a cleaning action log per record.

### 3.5 Transformation Engine

Receives the clean DataFrame. Applies dataset-specific business transformations: derived field calculations, cross-dataset enrichment lookups, structural mapping to the target database schema. Produces a transformed DataFrame that is schema-compatible with the database target tables and a transformation summary.

### 3.6 Data Loader

Receives the transformed DataFrame and performs database writes using upsert logic to prevent duplicates. Operates within a database transaction. On failure, rolls back. Records the load result (rows inserted, rows updated, rows failed) in the pipeline run record.

### 3.7 Database Layer

PostgreSQL-backed relational storage. Organized into three schema groups: operational tables (orders, customers, products, inventory, suppliers, payments), pipeline metadata tables (pipeline runs, stage results, ingestion events), and audit tables (audit log, cleaning log, validation log). All access goes through a repository layer — no raw SQL in business logic.

### 3.8 REST API Layer

FastAPI-based HTTP service. Exposes endpoints for: file upload, pipeline triggering, pipeline run history, per-run quality metrics, data retrieval per domain, and report download. Handles authentication via API keys, input validation, error formatting, and rate limiting. Returns standardized JSON envelopes on all responses.

### 3.9 Reporting Module

Generates two report types per pipeline run: a data quality report (record counts by stage, validation failures, quality score) and a business summary report (domain-specific KPIs per dataset). Supports export to CSV and Excel. Stores report files on the file system and records metadata in the database.

### 3.10 Dashboard

A server-rendered or SPA-based web interface backed by the REST API. Displays pipeline run history, quality scores per run, record funnel (ingested → valid → clean → loaded), downloadable reports, and recent alerts. Does not have its own data layer — all data comes from the API.

### 3.11 Audit & Logging Module

A cross-cutting concern. Provides a structured logger used by every component. Writes to both file-based logs and a database audit table. Every significant event (stage start/end, validation failure, cleaning action, load result, API call) is logged with a consistent schema: timestamp, run_id, stage, event_type, details.

### 3.12 Configuration Module

Centralizes all runtime configuration. Reads from environment variables, YAML config files, and per-dataset rule files. Provides a typed configuration object injected into all modules. Validates configuration on startup and fails fast if required values are missing or invalid.

---

## 4. Inter-Component Communication

All communication is in-process (within the same Python application) except for:

- **Database access:** All components access PostgreSQL via the SQLAlchemy ORM through the repository layer
- **File system:** Ingestion, Reporting, and Archiving read and write to a mounted file system directory structure
- **External API consumers:** All external traffic enters through the FastAPI REST layer

Internal data flow between pipeline stages uses **Python DataFrames** (pandas) as the standard data contract. Stage outputs are immutable — each stage receives a DataFrame, produces a new DataFrame, and returns it to the pipeline engine.

Stage results (not the DataFrames themselves) are persisted to the database after each stage completes, enabling pipeline resumption and auditing.

```
External Consumer
       │
       ▼
  REST API Layer
       │
       ▼
  Pipeline Engine ──────────────────────────────────────────────┐
       │                                                         │
       ▼                                                         │
  Ingestion Module → raw_df                                      │
       │                                                         │
       ▼                                                         │
  Validation Engine → valid_df + rejected_df + report           │
       │                                                         │
       ▼                                                         ▼
  Cleaning Engine → clean_df + cleaning_log              Audit & Logging
       │                                                         ▲
       ▼                                                         │
  Transformation Engine → transformed_df                        │
       │                                                         │
       ▼                                                         │
  Data Loader → load_result ──────────────────────────────────── │
       │
       ▼
  PostgreSQL Database
       │
       ▼
  Reporting Module → report_files
       │
       ▼
  File System / Download
```

---

## 5. Technology Choices and Rationale

| Technology | Role | Rationale |
|---|---|---|
| **Python 3.11+** | Application runtime | Dominant language in data engineering; rich ecosystem for data processing |
| **FastAPI** | REST API framework | High performance, async support, automatic OpenAPI docs, strong type validation via Pydantic |
| **pandas** | DataFrame processing | Industry standard for tabular data manipulation; well-understood by data engineers |
| **SQLAlchemy 2.x** | ORM and database access | Mature ORM with full PostgreSQL support; enables clean repository pattern |
| **Alembic** | Database migrations | Version-controlled schema evolution; pairs natively with SQLAlchemy |
| **PostgreSQL 15+** | Relational database | ACID-compliant, proven at scale, excellent JSON support, strong window function support |
| **Pydantic v2** | Data validation and config | Type-safe configuration and request/response modeling |
| **APScheduler** | Scheduled pipeline execution | Lightweight in-process job scheduler suitable for this scale |
| **openpyxl / xlrd** | Excel file reading | Standard Python Excel libraries |
| **Jinja2** | Report templating | Clean template-based HTML/text report generation |
| **Structlog** | Structured logging | JSON-formatted logs compatible with log aggregation systems |
| **pytest** | Testing framework | Industry standard; excellent fixture and parameterization support |
| **Docker + Docker Compose** | Containerization | Standard for local and production deployment; eliminates environment drift |
| **Nginx** | Reverse proxy | Handles static files, TLS termination, and load balancing in production |

### Why FastAPI over Flask or Django?

FastAPI provides native async support, automatic OpenAPI specification generation, and Pydantic-based validation out of the box. For a data platform where API contracts matter and request validation is frequent, these features significantly reduce boilerplate.

### Why pandas over Polars or Spark?

For datasets up to 500MB, pandas provides the best balance of developer familiarity, ecosystem compatibility, and processing speed. Polars is a strong future candidate for performance-critical paths. Spark would introduce significant operational overhead that is not justified at this scale.

### Why PostgreSQL over other databases?

PostgreSQL provides ACID guarantees, excellent support for complex queries needed by reporting, native JSONB for flexible audit log storage, and proven performance at the data volumes expected in this platform.

---

## 6. Scalability Considerations

### Horizontal Scaling

The pipeline processing layer is stateless — all pipeline state is stored in the database. This means multiple pipeline worker instances can run concurrently, processing different files in parallel, as long as they do not conflict on the same target tables. In a scaled deployment, a task queue (e.g., Celery + Redis) would replace the in-process scheduler, allowing workers to be distributed across multiple machines.

### Database Scaling

The PostgreSQL instance can be vertically scaled for increased throughput. For read-heavy workloads (reporting, API queries), read replicas can be added with no application changes, as the repository layer supports connection routing.

### File Processing Scaling

Large files are processed in configurable chunks to avoid loading entire datasets into memory. This ensures that even very large files do not cause memory exhaustion and that processing time scales linearly with file size.

### Configuration-Driven Dataset Support

New dataset types are registered via configuration files — not code changes. The validation engine, cleaning engine, and transformation engine all read dataset-specific rules from configuration, allowing the platform to scale to new domains without new deployments.

---

## 7. Reliability Considerations

### Transactional Writes

All database writes during the loading stage are wrapped in a transaction. If any part of the load fails, the entire transaction is rolled back. The pipeline run is marked as failed at the specific stage, preserving data integrity.

### Idempotent Operations

Pipeline stages are designed to be idempotent. Re-running a pipeline for the same file produces the same result. Upsert logic at the loader level ensures re-runs do not create duplicates.

### Failure Isolation

A failure in one pipeline stage does not affect other pipeline runs. The pipeline engine captures stage exceptions, logs them, updates the run status, and returns a controlled failure result without crashing the application.

### Health Monitoring

A dedicated health check endpoint exposes the application status, database connectivity, file system accessibility, and scheduler status. This endpoint is suitable for container orchestration health probes.

### Pipeline Run State

Every pipeline run is fully described in the database. If the application restarts mid-run, the incomplete run is detectable and can be retried. Stage results are written after each stage completes, not in bulk at the end.

---

## 8. Security Considerations

### API Authentication

All API endpoints require a valid API key passed via the `X-API-Key` header. Keys are stored as hashed values in the database. Plain-text keys are never stored.

### Input Validation

File uploads are validated before processing: MIME type checking, file extension validation, maximum file size enforcement, and malformed file detection. No file content is executed or interpreted as code.

### Database Credentials

All database connection parameters are read from environment variables. No credentials appear in source code or configuration files committed to version control.

### Sensitive Data in Logs

The logging module applies field-level masking for fields defined as sensitive in the configuration (e.g., payment card numbers, customer emails). Raw PII is never written to log files.

### Rate Limiting

The API layer enforces per-key and per-IP rate limits to prevent abuse and protect the processing backend from being overwhelmed by concurrent upload requests.

### Container Security

Docker containers run as non-root users. No unnecessary ports are exposed. Internal services (database, scheduler) are not exposed outside the Docker network.

---

## 9. Performance Considerations

### Chunked File Processing

Files are read and processed in configurable chunks (default: 10,000 rows per chunk). This bounds memory usage regardless of file size and allows the system to report intermediate progress on long-running pipelines.

### Database Connection Pooling

SQLAlchemy's connection pool is configured with appropriate pool size, max overflow, and connection timeout values. Connections are not held open during non-database pipeline stages.

### Indexed Database Tables

All tables used in API queries and reporting are indexed on their primary access patterns (run_id, dataset_type, created_at, status). This ensures query response times remain within the 500ms SLA as data volumes grow.

### Reporting Async Generation

Large reports are generated asynchronously — the API returns a report job ID immediately and the report is available for download once generation completes. This prevents long-running requests from blocking the API worker.

### Lazy Data Loading in Dashboard

The dashboard uses paginated API endpoints. It does not load full datasets into the browser. This ensures the dashboard remains responsive regardless of the number of pipeline runs or records in the system.
