# Complete ETL Workflow
## Enterprise ETL & Data Quality Platform

**Version:** 1.0.0  

---

## Overview

The ETL workflow is a sequential, staged pipeline. Each stage has a clear purpose, well-defined inputs and outputs, and produces artifacts that feed into the next stage. No stage is skipped. Every stage produces a result that is persisted to the database before the next stage begins.

The complete workflow progresses through ten stages:

```
Data Source
    ↓
Ingestion
    ↓
Validation
    ↓
Cleaning
    ↓
Transformation
    ↓
Loading
    ↓
Reporting
    ↓
Analytics
    ↓
Dashboard
    ↓
Archive
```

---

## Stage 1: Data Source

### What It Is
The originating source of raw business data. In this platform, data sources are flat files — CSV or Excel — submitted by vendors, internal systems, or manual uploads.

### Why It Exists
The system must accommodate data arriving from multiple heterogeneous sources that have no common format or delivery mechanism. The data source stage represents the boundary between external data providers and the internal platform.

### Data Sources Supported
- **Manual Upload**: a user uploads a file via the web dashboard or REST API
- **Directory Poll**: an automated watcher scans a designated directory at a configured interval for new files
- **Future**: S3 bucket notifications, SFTP polling, API callbacks from partner systems

### Source Dataset Types
The platform handles six dataset types, each arriving as a separate file:
- `orders.csv` — daily transactional order data
- `customers.csv` — customer master data
- `products.csv` — product catalog data
- `inventory.csv` — stock level data per warehouse
- `suppliers.csv` — vendor and supplier master data
- `payments.csv` — payment transaction data

### Accepted Formats
- `.csv` (comma-separated, UTF-8 or Latin-1 encoded)
- `.xlsx` (Excel 2007+)

---

## Stage 2: Ingestion

### What It Is
The act of accepting a raw file, verifying it is structurally processable, assigning it an identity, and making it available to the pipeline.

### Why It Exists
Before any business logic is applied, the system must confirm the file is a real, readable file of a known type. Ingestion is the controlled entry point. It prevents unreadable files from entering the pipeline and establishes an audit trail from the very first moment a file touches the system.

### What Happens
1. The file is received (upload or directory detection)
2. MIME type and extension are verified
3. File size is checked against the configured maximum
4. The dataset type is resolved from the filename pattern
5. A unique `ingestion_id` (UUID) is generated
6. The raw file is copied to: `data/raw/{dataset_type}/{YYYY-MM-DD}/{ingestion_id}/original_filename`
7. An `ingestion_event` record is written to the database with: ingestion_id, filename, dataset_type, file_size, row_count, status=RECEIVED, timestamp
8. A pipeline trigger is emitted: `{ ingestion_id, dataset_type, file_path }`

### Artifacts Produced
- Raw file persisted to versioned storage
- `ingestion_event` database record
- Pipeline trigger event

### Failure Handling
If the file fails format or size validation, it is rejected immediately. The `ingestion_event` record is written with `status=REJECTED` and a rejection reason. No pipeline run is created.

---

## Stage 3: Validation

### What It Is
The process of checking every record in the ingested dataset against schema definitions and business rules to determine which records are fit for further processing.

### Why It Exists
Raw data from external sources is untrustworthy. Vendors use inconsistent formats. Manual uploads contain human errors. Without a validation gate, bad data silently propagates into the database and corrupts analytics. Validation is the quality control checkpoint.

### What Happens
1. The raw file is read into a pandas DataFrame
2. **Schema Validation**: columns are checked for presence, naming, and data type conformance
3. **Business Rule Validation**: each rule in the dataset's rule set is applied to each record
4. Records that pass all rules are placed in `valid_df`
5. Records that fail any rule are placed in `rejected_df` with annotations:
   - `_validation_status`: INVALID or WARNING
   - `_failed_rules`: list of rule codes that failed
   - `_failure_messages`: human-readable descriptions
6. A `ValidationReport` is produced: total records, valid count, invalid count, quality score
7. `validation_failures` records are written to the database (one per failed record per rule)
8. The `StageResult` for validation is persisted: status, counts, quality score

### Quality Score Formula
`quality_score = (valid_records / total_records) × 100`

A configurable quality threshold (default: 80%) determines whether the pipeline proceeds or halts with a warning.

### Artifacts Produced
- `valid_df`: DataFrame of passing records
- `rejected_df`: DataFrame of failing records with annotations
- `ValidationReport`: summary metrics
- `validation_failures` database records
- `stage_results` record (Validation stage)

---

## Stage 4: Cleaning

### What It Is
The systematic application of data repair and normalization transformations to validated records, producing a dataset that is internally consistent and structurally correct.

### Why It Exists
Validation identifies bad records and removes them. Cleaning fixes fixable problems in the records that passed validation. A record can be structurally valid but still contain formatting inconsistencies (mixed case names, extra whitespace, date format variations) that would cause downstream failures or analytics errors. Cleaning standardizes all data before it enters the database.

### What Happens
1. `valid_df` is received from the validation stage
2. **Deduplication**: records sharing the same deduplication key (configured per dataset) are reduced to one record; a count of removed duplicates is recorded
3. **Null Handling**: each field's null strategy is applied (drop row, fill with default, flag with sentinel)
4. **String Normalization**: all string fields are trimmed; case normalization is applied per field definition
5. **Date Standardization**: all date fields are parsed (multiple format attempts) and converted to ISO 8601
6. **Numeric Cleaning**: currency symbols, commas, and spaces are stripped from numeric fields
7. **Custom Patterns**: field-level regex transformations defined in configuration are applied
8. Every cleaning action generates a `CleaningLog` entry: { row_id, field, action, old_value, new_value }
9. `CleaningSummary` is produced
10. `StageResult` for Cleaning is persisted

### Artifacts Produced
- `clean_df`: cleaned and standardized DataFrame
- `CleaningLog`: per-action record of every transformation
- `CleaningSummary`: aggregate cleaning statistics
- `stage_results` record (Cleaning stage)

---

## Stage 5: Transformation

### What It Is
The application of business-specific logic to convert clean operational data into analytics-ready, semantically rich records that match the target database schema.

### Why It Exists
Clean data is correct but not yet meaningful at the business level. Transformation adds business value: calculating derived metrics, enriching records with contextual information, mapping technical identifiers to human-readable names, and structuring data to support downstream analytics and reporting. This is the "T" in ETL — the stage where data becomes information.

### What Happens
1. `clean_df` is received
2. The dataset-specific `Transformer` is loaded from the `TransformerRegistry`
3. **Field Mapping**: columns are renamed and reordered to match the target schema
4. **Derived Field Calculation**: computed fields are calculated (e.g., `order_age_days`, `stock_value`, `days_to_payment`)
5. **Enrichment Lookup**: foreign keys are resolved against reference tables in the database to add descriptive fields
6. **Aggregation**: summary records are computed where required
7. The output DataFrame is validated against the target schema structure
8. `TransformationSummary` is produced
9. `StageResult` for Transformation is persisted

### Artifacts Produced
- `transformed_df`: schema-compatible, business-enriched DataFrame
- `TransformationSummary`
- `stage_results` record (Transformation stage)

---

## Stage 6: Loading

### What It Is
The act of writing the transformed, clean records into the PostgreSQL database using safe, idempotent upsert logic.

### Why It Exists
All previous stages produce DataFrames in memory. Loading is the stage that makes the data permanent and queryable by downstream consumers. It must be reliable, transactional, and idempotent so that re-running a pipeline for the same file does not create duplicate records.

### What Happens
1. `transformed_df` is received
2. A database transaction is opened
3. Records are written using `INSERT ... ON CONFLICT (primary_key) DO UPDATE` (upsert)
4. The transaction is committed if all records write successfully
5. On any failure, the transaction is rolled back — no partial writes
6. Load statistics are collected: rows_inserted, rows_updated, rows_failed
7. `StageResult` for Loading is persisted with load statistics
8. The `pipeline_run` record is updated to `status=COMPLETED`

### Artifacts Produced
- Persisted records in the target operational table
- `stage_results` record (Loading stage)
- Updated `pipeline_run` record

### Failure Handling
If the load fails, the transaction rolls back completely. The `pipeline_run` is marked `FAILED` at the Loading stage. Previously completed stages are unaffected. The run can be retried from the Loading stage without re-running ingestion, validation, cleaning, or transformation.

---

## Stage 7: Reporting

### What It Is
The automated generation of structured reports summarizing the pipeline run outcome and business metrics from the newly loaded data.

### Why It Exists
Raw pipeline results (record counts, quality scores) need to be packaged into formats that business stakeholders can understand and act on. Reports close the feedback loop — they tell data engineers whether the pipeline was healthy and tell business managers what the data says.

### What Happens
1. The `ReportOrchestrator` is triggered with the completed `run_id`
2. **Data Quality Report** is generated: record funnel, quality score, validation failure breakdown by rule, cleaning action summary, records loaded vs rejected
3. **Business Summary Report** is generated per dataset type with domain KPIs
4. Reports are exported to CSV and Excel format
5. Report files are written to: `data/reports/{run_id}/`
6. Report metadata records are written to the `reports` database table
7. Reports are immediately available via the API for download

### Artifacts Produced
- Report files (CSV and Excel) on the file system
- `reports` database records with file paths and metadata

---

## Stage 8: Analytics

### What It Is
The availability of clean, structured data in PostgreSQL for querying by business analysts and data engineers via the REST API or direct database tools.

### Why It Exists
The ultimate purpose of the ETL pipeline is to make data useful. Once data is loaded into the database, it must be queryable. The analytics stage represents the availability window — the point at which processed data can be consumed by downstream BI tools, dashboards, or custom queries.

### What Provides This
- REST API data endpoints (`/api/v1/data/{dataset_type}`)
- Indexed database tables optimized for analytical queries
- Aggregated summary tables populated during transformation
- The `data_quality_scores` table providing a historical quality trend

---

## Stage 9: Dashboard

### What It Is
The real-time operational visibility layer — a web interface that surfaces pipeline health, quality metrics, and business KPIs to non-technical stakeholders.

### Why It Exists
Not all stakeholders can query a database or call an API. The dashboard democratizes access to pipeline results. It provides at-a-glance operational awareness for operations teams and business managers without requiring technical knowledge.

### What Is Displayed
- Pipeline run list with status, dataset type, start/end time, quality score
- Per-run record funnel: ingested → validated → cleaned → loaded
- Quality score trend chart per dataset type over time
- Recent validation failures and alerts
- Report download links
- System health indicators

---

## Stage 10: Archive

### What It Is
The long-term storage and cleanup of pipeline artifacts that are no longer needed in active storage.

### Why It Exists
Without archiving, the `data/raw/` directory grows unbounded. Processed files and old reports consume disk space unnecessarily. Archiving moves completed pipeline artifacts to a cold storage location while keeping the system lean and performant.

### What Happens
1. After a configurable retention period (default: 30 days), pipeline run artifacts are eligible for archiving
2. Raw input files are moved from `data/raw/` to `data/archive/`
3. Old report files are moved to `data/archive/reports/`
4. The database records for archived runs are updated with `archived=true` and `archive_path`
5. Archive operations are logged in the audit log

### Archive Policy (Configurable)
- Raw files: archived after 30 days
- Report files: archived after 90 days
- Database records: retained indefinitely (soft archive flag only)
- Audit logs: retained per compliance policy (default: 365 days)
