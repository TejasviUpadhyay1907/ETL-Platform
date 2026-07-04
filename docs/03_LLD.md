# Low-Level Design (LLD)
## Enterprise ETL & Data Quality Platform

**Version:** 1.0.0  
**Status:** Approved for Architecture Review  

---

## Table of Contents

1. File Ingestion Module
2. Validation Module
3. Cleaning Module
4. Transformation Module
5. Pipeline Engine
6. Database Layer
7. API Layer
8. Reporting Module
9. Dashboard Module
10. Configuration Module
11. Logging & Audit Module
12. Authentication Module (Future)

---

## 1. File Ingestion Module

### Purpose
Accept raw data files from external sources (web upload or directory polling), verify file integrity, persist the raw file, and emit an ingestion event to trigger the pipeline.

### Responsibilities
- Accept file via multipart HTTP upload or detect file in watched directory
- Validate file format (CSV, XLSX only)
- Validate file size against configured maximum
- Detect dataset type from filename pattern or manifest
- Generate a unique ingestion_id (UUID)
- Persist the raw file to the ingestion storage directory with versioned path
- Create an ingestion_event record in the database
- Emit a pipeline trigger event with the ingestion_id

### Inputs
- Raw file (binary stream or file path from directory watcher)
- Ingestion source metadata (origin: upload/poll, timestamp, submitter)

### Outputs
- Persisted raw file at path: `data/raw/{dataset_type}/{date}/{ingestion_id}/filename`
- Ingestion event record written to database
- IngestionResult object: { ingestion_id, dataset_type, file_path, row_count, file_size, status }

### Internal Design
- `FileTypeDetector`: determines MIME type and extension validity
- `DatasetTypeResolver`: maps filename patterns to dataset type enum (Orders, Customers, Products, etc.)
- `RawFileStore`: handles file persistence with versioned directory creation
- `IngestionEventRepository`: database write for ingestion_events table
- `DirectoryWatcher`: polls a configured directory at a configurable interval for new files

### Dependencies
- Configuration Module (max file size, allowed extensions, watch directory path)
- Database Layer (ingestion_events table)
- Logging Module

### Possible Future Enhancements
- Support cloud storage sources (S3, Azure Blob, GCS)
- Support FTP/SFTP ingestion
- Support API-pushed files with metadata manifests
- Virus/malware scanning of uploaded files

---

## 2. Validation Module

### Purpose
Enforce schema correctness and business rule compliance on the ingested dataset. Separate valid records from invalid records with detailed failure annotations.

### Responsibilities
- Load schema definition for the detected dataset type from configuration
- Validate presence and order of required columns
- Validate data types per column (string, integer, float, date, boolean)
- Enforce business rules per dataset type (configurable rule set)
- Annotate each record with: validation_status, failed_rule_codes, failure_messages
- Produce a valid DataFrame (passing records only)
- Produce a rejected DataFrame (failing records with annotations)
- Produce a ValidationReport: total_records, valid_count, invalid_count, warning_count, rules_applied, quality_score

### Inputs
- Raw DataFrame (from Ingestion Module)
- Dataset type identifier
- Schema definition (from Configuration Module)
- Business rule set (from Configuration Module)

### Outputs
- valid_df: DataFrame of records that passed all rules
- rejected_df: DataFrame of records that failed at least one rule, with failure annotations
- ValidationReport object

### Internal Design
- `SchemaValidator`: checks column presence, ordering, and data types
- `BusinessRuleEngine`: iterates over configured rule definitions and applies each rule; rules are objects with a `validate(record)` method
- `RuleRegistry`: maps dataset type to its list of registered Rule objects
- `ValidationAnnotator`: appends validation metadata columns to the DataFrame
- `QualityScoreCalculator`: computes quality score as (valid_records / total_records) * 100

### Business Rules Examples by Dataset
- **Orders**: order_id not null, order_total > 0, order_date is valid date, customer_id not null
- **Customers**: customer_id not null, email matches RFC format, phone is numeric, country is valid ISO code
- **Products**: product_id not null, price > 0, category not null
- **Inventory**: quantity >= 0, warehouse_id not null
- **Payments**: amount > 0, payment_method in allowed list, transaction_date is valid date
- **Suppliers**: supplier_id not null, contact_email valid format

### Dependencies
- Configuration Module (schema definitions, rule configurations)
- Logging Module

### Possible Future Enhancements
- Rule versioning: track which rule version was applied per run
- Dynamic rule creation via admin UI
- Cross-dataset referential validation (e.g., customer_id in Orders must exist in Customers)
- ML-based anomaly flagging as a warning-level rule

---

## 3. Cleaning Module

### Purpose
Remove data quality defects from validated records and produce a standardized, consistent dataset ready for transformation.

### Responsibilities
- Remove exact duplicate rows based on configurable deduplication key fields per dataset
- Apply null handling strategy per field (drop row / fill with default / flag with sentinel value)
- Trim leading and trailing whitespace from all string fields
- Normalize string casing per field (upper, lower, title — configurable)
- Parse and standardize date fields to ISO 8601 format (YYYY-MM-DD)
- Strip non-numeric characters from numeric fields (currency symbols, commas, spaces)
- Apply field-level regex replacement patterns defined in configuration
- Produce a CleaningLog: one record per cleaning action applied per row
- Produce a clean DataFrame and a cleaning_summary report

### Inputs
- valid_df (from Validation Module)
- Dataset type identifier
- Cleaning rules configuration (from Configuration Module)

### Outputs
- clean_df: DataFrame with all cleaning transformations applied
- CleaningLog: list of { row_index, field_name, action_type, original_value, cleaned_value }
- CleaningSummary: { duplicates_removed, nulls_filled, nulls_dropped, formats_corrected, total_actions }

### Internal Design
- `DeduplicationHandler`: uses configurable key fields to identify and remove duplicate rows; retains the first occurrence by default (configurable)
- `NullHandler`: reads per-field null strategies from config and applies them
- `StringNormalizer`: applies trim, case normalization per field definition
- `DateStandardizer`: attempts multiple date format parsers; records successful parse format
- `NumericCleaner`: strips non-numeric characters, handles locale-specific formats
- `CleaningActionLogger`: records each transformation to the CleaningLog

### Dependencies
- Configuration Module (cleaning rules per dataset type)
- Logging Module

### Possible Future Enhancements
- Address standardization using postal APIs
- Phone number normalization using E.164 format
- Name deduplication using fuzzy matching (Levenshtein distance)
- Configurable outlier detection and flagging

---

## 4. Transformation Module

### Purpose
Apply dataset-specific business logic to produce a DataFrame that is semantically correct, enriched with derived fields, and structurally compatible with the target database schema.

### Responsibilities
- Apply dataset-specific transformation rules (derived fields, calculations, mappings)
- Enrich records with lookup values from the database or reference tables
- Rename and restructure columns to match the target schema
- Calculate aggregated summary fields where required
- Produce a transformed DataFrame ready for database loading
- Produce a TransformationSummary report

### Inputs
- clean_df (from Cleaning Module)
- Dataset type identifier
- Transformation rules configuration
- Reference/lookup data (from database or static configuration)

### Outputs
- transformed_df: DataFrame conforming to target database schema
- TransformationSummary: { dataset_type, rows_transformed, derived_fields_added, enrichment_lookups_performed }

### Internal Design
- `TransformerRegistry`: maps dataset type to its registered Transformer class
- `BaseTransformer`: abstract base class defining the transform(df) interface
- Per-dataset transformers (e.g., `OrderTransformer`, `CustomerTransformer`, `ProductTransformer`, etc.)
- `FieldMapper`: handles column renaming and reordering to match target schema
- `DerivedFieldCalculator`: applies computed field expressions (e.g., total_with_tax = order_total * 1.1)
- `LookupEnricher`: queries reference tables to resolve foreign key descriptions
- `AggregationBuilder`: produces summary records appended or written to summary tables

### Transformation Examples by Dataset
- **Orders**: calculate order_age_days from order_date, map status codes to descriptions, join to customer name
- **Customers**: derive full_name from first_name + last_name, derive customer_segment from order history
- **Products**: map category_id to category_name, calculate margin from price and cost
- **Inventory**: calculate stock_value = quantity * unit_cost, flag low_stock where quantity < reorder_point
- **Payments**: calculate days_to_payment from invoice_date to payment_date, classify payment_status

### Dependencies
- Configuration Module
- Database Layer (for enrichment lookups)
- Logging Module

### Possible Future Enhancements
- Support for user-defined transformation functions loaded at runtime
- DAG-based transformation chains for complex multi-step transforms
- Transformation versioning for reproducible historical runs

---

## 5. Pipeline Engine

### Purpose
Orchestrate the complete ETL lifecycle for a given ingestion event. Manage pipeline run state, sequence stage execution, handle failures, and persist run history.

### Responsibilities
- Create a new PipelineRun record with a unique run_id on every execution
- Execute stages in sequence: Ingest → Validate → Clean → Transform → Load
- Pass the output of each stage as the input to the next
- Persist a StageResult record to the database after each stage completes
- Capture exceptions at the stage level without crashing the engine
- Mark the PipelineRun as COMPLETED, FAILED, or PARTIAL based on stage outcomes
- Support scheduled execution via the job scheduler
- Support manual trigger via API
- Support per-stage re-execution for failed runs

### Inputs
- Trigger event: { ingestion_id, dataset_type, file_path } — from API or scheduler

### Outputs
- PipelineRunResult: { run_id, status, stage_results[], start_time, end_time, summary }
- PipelineRun record persisted in the database

### Internal Design
- `PipelineRunner`: main orchestrator class with a `run(trigger_event)` method
- `StageExecutor`: wraps each stage call with timing, exception handling, and result capture
- `PipelineRunRepository`: reads and writes pipeline_runs and stage_results tables
- `PipelineContext`: immutable context object passed through all stages containing run_id, dataset_type, config
- `PipelineScheduler`: uses APScheduler to register and manage cron-based triggers
- `PipelineTriggerService`: API-facing service that validates trigger requests and invokes PipelineRunner

### Run States
- `PENDING`: created, not yet started
- `RUNNING`: currently executing
- `COMPLETED`: all stages succeeded
- `FAILED`: a stage raised an unrecoverable error
- `PARTIAL`: some stages succeeded; run stopped at failure point

### Stage Result States
- `SUCCESS`: stage completed without errors
- `WARNING`: stage completed with non-fatal issues (e.g., high invalid record rate)
- `FAILED`: stage raised an exception or exceeded failure threshold

### Dependencies
- All processing modules (Ingestion, Validation, Cleaning, Transformation, Loader)
- Database Layer (pipeline_runs, stage_results tables)
- Configuration Module
- Logging Module

### Possible Future Enhancements
- DAG-based pipeline graph for parallel stage execution
- Retry policies per stage with backoff strategies
- Pipeline versioning (run against a specific pipeline version)
- Cross-file pipeline runs (join multiple ingestion events in one run)

---

## 6. Database Layer

### Purpose
Provide a clean, abstracted interface between the application and PostgreSQL. Enforce data integrity, manage schema migrations, and expose domain-specific repository classes to the rest of the application.

### Responsibilities
- Define the complete relational schema for all operational, pipeline, and audit tables
- Manage schema versioning and migrations via Alembic
- Provide repository classes per domain with typed query methods
- Manage connection pooling and session lifecycle
- Enforce upsert logic to prevent duplicate records on load
- Provide transaction management utilities

### Schema Groups

**Operational Tables** (business data):
- `orders`: processed order records
- `customers`: processed customer records
- `products`: processed product records
- `inventory`: processed inventory records
- `suppliers`: processed supplier records
- `payments`: processed payment records

**Pipeline Metadata Tables**:
- `ingestion_events`: record of every file ingestion
- `pipeline_runs`: record of every pipeline execution
- `stage_results`: per-stage outcome per run
- `reports`: metadata for generated report files

**Audit and Quality Tables**:
- `audit_log`: every significant system event
- `validation_failures`: per-record validation failure details
- `cleaning_log`: per-record cleaning actions applied
- `data_quality_scores`: aggregated quality scores per run per dataset

### Internal Design
- `DatabaseEngine`: manages the SQLAlchemy engine and session factory
- `BaseRepository`: abstract base with common CRUD and query methods
- Per-domain repositories: `OrderRepository`, `CustomerRepository`, `PipelineRunRepository`, `AuditLogRepository`, etc.
- `UpsertManager`: encapsulates PostgreSQL INSERT ... ON CONFLICT logic
- `TransactionManager`: context manager for wrapping multi-step operations in a transaction
- All ORM models defined using SQLAlchemy declarative base with type annotations

### Dependencies
- Configuration Module (database connection settings)
- Alembic (migration management)

### Possible Future Enhancements
- Read replica routing for query separation
- Table partitioning for audit_log and pipeline_runs by date
- Full-text search index on audit log for compliance queries
- Database-level row security for multi-tenant support

---

## 7. API Layer

### Purpose
Provide a well-structured, authenticated, and documented HTTP interface for all external interactions with the platform.

### Responsibilities
- Expose REST endpoints for all platform capabilities
- Validate all incoming request parameters and body payloads using Pydantic models
- Enforce API key authentication on all endpoints
- Apply rate limiting per API key and per IP
- Return standardized JSON response envelopes
- Generate automatic OpenAPI documentation
- Handle all expected error conditions with appropriate HTTP status codes and error codes

### Endpoint Groups

| Group | Base Path | Purpose |
|---|---|---|
| Ingestion | `/api/v1/ingest` | File upload and ingestion event management |
| Pipeline | `/api/v1/pipelines` | Trigger, monitor, and manage pipeline runs |
| Data | `/api/v1/data` | Query processed business data per domain |
| Quality | `/api/v1/quality` | Retrieve data quality scores and reports |
| Reports | `/api/v1/reports` | List and download generated reports |
| Health | `/api/v1/health` | System health and readiness checks |

### Response Envelope
Every API response follows a standard structure:
```
{
  "success": true/false,
  "data": { ... },
  "error": null / { "code": "...", "message": "...", "details": [...] },
  "meta": { "request_id": "...", "timestamp": "...", "version": "1.0" }
}
```

### Internal Design
- `APIRouter` instances per endpoint group, registered on the main FastAPI application
- `AuthMiddleware`: validates API key on every request; attaches key metadata to request context
- `RateLimitMiddleware`: enforces per-key and per-IP request rate limits using an in-memory sliding window
- `RequestValidator`: Pydantic models for all request bodies
- `ResponseBuilder`: utility for constructing standardized response envelopes
- `ErrorHandler`: global exception handler mapping exception types to HTTP status codes

### Dependencies
- Pipeline Engine (trigger and status)
- Database Layer (data queries, report metadata)
- Reporting Module (report generation and download)
- Configuration Module (rate limits, API key settings)
- Logging Module

### Possible Future Enhancements
- OAuth 2.0 / JWT token-based authentication
- GraphQL endpoint for flexible data queries
- Webhook callbacks for pipeline completion events
- API versioning strategy (v2 routes)

---

## 8. Reporting Module

### Purpose
Generate structured, downloadable reports that summarize data quality outcomes and business metrics for each pipeline run.

### Responsibilities
- Generate a Data Quality Report per pipeline run: record funnel, validation failures by rule, quality score, rejected records summary
- Generate a Business Summary Report per dataset per run: domain KPIs (e.g., total order value, new customers, low-stock products)
- Export reports in CSV and Excel formats
- Store generated report files on the file system under a versioned path
- Record report metadata in the `reports` database table
- Provide a report retrieval interface for the API layer

### Inputs
- Pipeline run_id
- Stage results from the pipeline run
- Aggregated quality scores from the database
- Transformed DataFrames (accessed via database queries)

### Outputs
- Report file at path: `data/reports/{run_id}/{report_type}.{format}`
- Report metadata record in the `reports` table

### Internal Design
- `ReportOrchestrator`: coordinates report generation for a given run_id
- `DataQualityReportBuilder`: assembles quality metrics from stage results and quality scores table
- `BusinessSummaryReportBuilder`: runs domain-specific aggregation queries and formats results
- `ReportExporter`: handles serialization to CSV (via pandas) and Excel (via openpyxl)
- `ReportFileStore`: manages file system paths and writes report files
- `ReportRepository`: database reads/writes for the reports table

### Dependencies
- Database Layer (stage results, quality scores, business data queries)
- Configuration Module (report output directory, enabled report types)
- Logging Module

### Possible Future Enhancements
- PDF report generation for executive distribution
- Scheduled email delivery of reports
- Report comparison view (run N vs run N-1)
- Interactive drill-down reports via the dashboard

---

## 9. Dashboard Module

### Purpose
Provide a web-based operational interface for data engineers, analysts, and business managers to monitor pipeline health, review data quality, and access reports.

### Responsibilities
- Display the list of recent pipeline runs with status, dataset type, and timestamps
- Display a record funnel per run: ingested → validated → cleaned → loaded
- Display quality score trend over time per dataset type
- Display recent validation failures and cleaning actions
- Provide file upload interface for manual ingestion triggering
- Provide report download links per run
- Display system health status

### Internal Design
The dashboard is served as a set of server-rendered HTML templates using Jinja2, backed entirely by the REST API. No direct database access from the dashboard layer.

- `DashboardRouter`: FastAPI router serving HTML views
- `TemplateEngine`: Jinja2-based template renderer
- Template pages: `runs_list.html`, `run_detail.html`, `upload.html`, `quality.html`, `reports.html`
- JavaScript (minimal, vanilla or HTMX): handles file upload form submission, polling for run status updates, and dynamic table loading

### Dependencies
- REST API Layer (all data fetched via API calls)
- Configuration Module (dashboard title, branding)

### Possible Future Enhancements
- React or Vue.js SPA for richer interactivity
- Real-time pipeline progress via WebSockets
- Custom KPI dashboard builder for business managers
- Role-based view filtering

---

## 10. Configuration Module

### Purpose
Centralize all runtime configuration and provide a validated, typed configuration object accessible to all system components.

### Responsibilities
- Load configuration from environment variables and YAML files
- Validate all required configuration values on application startup
- Provide per-dataset schema definitions
- Provide per-dataset business rule definitions
- Provide per-dataset cleaning rule definitions
- Provide per-dataset transformation rule definitions
- Fail fast with descriptive errors if configuration is invalid

### Configuration Categories
- **Application**: environment name, debug mode, log level
- **Database**: host, port, name, user, password, pool size
- **File System**: raw file directory, archive directory, report directory
- **Ingestion**: max file size, allowed extensions, watch directory, poll interval
- **Pipeline**: default chunk size, max concurrent runs, stage timeout
- **API**: rate limit thresholds, API key header name, CORS origins
- **Datasets**: per-dataset schema, rules, and transformation definitions (loaded from YAML files in `config/datasets/`)
- **Logging**: log file path, retention days, log format

### Internal Design
- `AppConfig`: Pydantic BaseSettings model for application-level configuration
- `DatasetConfig`: Pydantic model per dataset type loaded from YAML
- `ConfigLoader`: reads environment variables and merges with YAML configuration
- `ConfigValidator`: runs at startup to check all required values and dataset configs are present
- `ConfigRegistry`: singleton providing access to the loaded config throughout the application

### Dependencies
- None (this module has no upstream dependencies within the application)

### Possible Future Enhancements
- Remote configuration via a config server (HashiCorp Vault, AWS SSM)
- Configuration hot-reload without application restart
- Configuration audit log tracking who changed what

---

## 11. Logging & Audit Module

### Purpose
Provide a unified, structured logging interface for all system components and maintain a queryable audit trail of all significant events.

### Responsibilities
- Provide a structured logger that every module uses for all log output
- Write logs in JSON format to both file and stdout
- Write significant audit events to the `audit_log` database table
- Categorize log events: INFO, WARNING, ERROR, CRITICAL, AUDIT
- Include standard context fields on every log entry: timestamp, run_id, stage, component, event_type
- Support configurable log retention and rotation
- Mask PII fields defined in configuration before writing to logs

### Audit Event Types
- PIPELINE_STARTED, PIPELINE_COMPLETED, PIPELINE_FAILED
- STAGE_STARTED, STAGE_COMPLETED, STAGE_FAILED
- VALIDATION_FAILURE (per record)
- CLEANING_ACTION (per record action)
- RECORD_LOADED, RECORD_REJECTED
- API_REQUEST, API_ERROR
- FILE_INGESTED, FILE_REJECTED
- CONFIG_LOADED, SYSTEM_STARTUP, SYSTEM_SHUTDOWN

### Internal Design
- `StructuredLogger`: wrapper around structlog providing a consistent logging interface
- `AuditEventEmitter`: writes audit events to the database `audit_log` table
- `PIIMasker`: intercepts log records and replaces configured sensitive field values with masked representations
- `LogRotationHandler`: manages log file rotation and cleanup based on retention policy

### Dependencies
- Configuration Module (log level, retention, PII field list)
- Database Layer (audit_log table writes)

### Possible Future Enhancements
- Integration with centralized log aggregation (ELK Stack, Datadog, CloudWatch)
- Real-time alerting on ERROR and CRITICAL log events
- Audit log export for compliance reporting

---

## 12. Authentication Module (Future)

### Purpose
Provide identity verification and authorization for all platform users and API consumers. This module is planned for a future phase and is described here to ensure the architecture accounts for it.

### Planned Responsibilities
- User registration, login, and session management
- API key issuance, rotation, and revocation
- Role-based access control (RBAC) with roles: Admin, Data Engineer, Analyst, Viewer
- JWT token generation and validation
- Integration with enterprise SSO (SAML, OIDC)

### Planned Design Approach
- Separate authentication service or integrated module within the API layer
- Roles stored in database with permission mappings per endpoint group
- All existing API endpoints extended with role-based permission checks
- API key management UI in the dashboard

### Impact on Existing Modules
- API Layer: replace simple API key middleware with full JWT validation
- Dashboard: add login page and session management
- Audit Log: associate all events with authenticated user identity
