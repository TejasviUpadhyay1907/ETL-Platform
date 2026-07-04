# Data Flow Diagram
## Enterprise ETL & Data Quality Platform

**Version:** 1.0.0  

---

## Overview

This document traces the complete movement of data through the platform, from the moment a raw file arrives at the system boundary to the point where processed records are available for reporting and analytics.

Data flows through three categories of storage:
- **In-Memory**: pandas DataFrames during active pipeline processing
- **File System**: raw files, archive files, and report files
- **Database**: pipeline metadata, processed records, audit events, and quality metrics

---

## Complete Data Flow — Narrative

### 1. File Arrives at System Boundary

A file (`orders.csv`) is submitted by a user via the REST API file upload endpoint, or detected in the watched ingestion directory by the directory watcher.

**Data at this point:** Raw binary file stream or file path

---

### 2. Ingestion Stage

The Ingestion Module receives the file. It reads the file header to confirm readability, determines the dataset type (`orders`), generates an `ingestion_id`, and writes the raw file to persistent storage.

**Data movement:**
```
[Binary File Stream]
        │
        ▼
[File System: data/raw/orders/2025-01-15/abc-uuid/orders.csv]
        │
        ▼
[Database: ingestion_events table]
  { ingestion_id, dataset_type, file_path, file_size, row_count, status=RECEIVED }
        │
        ▼
[Pipeline Trigger Event: { ingestion_id, dataset_type, file_path }]
```

---

### 3. Pipeline Engine Creates Run

The Pipeline Engine receives the trigger event, creates a new pipeline run record, and begins stage orchestration.

**Data movement:**
```
[Pipeline Trigger Event]
        │
        ▼
[Database: pipeline_runs table]
  { run_id, ingestion_id, dataset_type, status=RUNNING, start_time }
```

---

### 4. Validation Stage

The Ingestion Module reads the raw file from disk into a pandas DataFrame. The Validation Engine applies schema and business rule checks.

**Data movement:**
```
[File System: data/raw/orders/...]
        │
        ▼
[In-Memory: raw_df (full raw DataFrame)]
        │
        ├──► [In-Memory: valid_df (passing records only)]
        │
        └──► [In-Memory: rejected_df (failing records + annotations)]
                │
                ▼
        [Database: validation_failures table]
          { run_id, row_index, rule_code, failure_message }
        
[Database: stage_results table]
  { run_id, stage=VALIDATION, status, valid_count, invalid_count, quality_score }

[Database: data_quality_scores table]
  { run_id, dataset_type, quality_score, timestamp }
```

---

### 5. Cleaning Stage

The Cleaning Engine receives `valid_df` and applies all cleaning transformations.

**Data movement:**
```
[In-Memory: valid_df]
        │
        ▼
[In-Memory: clean_df (deduplicated, normalized, standardized)]
        │
[In-Memory: cleaning_log (list of per-record actions)]
        │
        ▼
[Database: cleaning_log table]
  { run_id, row_id, field_name, action_type, original_value, cleaned_value }

[Database: stage_results table]
  { run_id, stage=CLEANING, status, duplicates_removed, actions_applied }
```

---

### 6. Transformation Stage

The Transformation Engine receives `clean_df` and applies business transformations and schema mapping.

**Data movement:**
```
[In-Memory: clean_df]
        │
        ├──► [Database: reference tables (lookup queries for enrichment)]
        │
        ▼
[In-Memory: transformed_df (target-schema-compliant, enriched)]
        │
[Database: stage_results table]
  { run_id, stage=TRANSFORMATION, status, rows_transformed }
```

---

### 7. Loading Stage

The Data Loader writes the transformed DataFrame to the target operational table using upsert logic.

**Data movement:**
```
[In-Memory: transformed_df]
        │
        ▼  (within a database transaction)
[Database: orders table]
  → INSERT ... ON CONFLICT DO UPDATE
  → Rows inserted: N, Rows updated: M, Rows failed: 0
        │
[Database: stage_results table]
  { run_id, stage=LOADING, status=SUCCESS, rows_inserted, rows_updated }

[Database: pipeline_runs table]
  → status updated to COMPLETED
```

---

### 8. Reporting Stage

The Reporting Module generates reports from the pipeline run results and newly loaded data.

**Data movement:**
```
[Database: stage_results, data_quality_scores, orders table]
        │
        ▼
[In-Memory: Report DataFrames (quality metrics, business KPIs)]
        │
        ▼
[File System: data/reports/{run_id}/data_quality_report.xlsx]
[File System: data/reports/{run_id}/orders_summary_report.xlsx]
[File System: data/reports/{run_id}/data_quality_report.csv]
        │
[Database: reports table]
  { run_id, report_type, file_path, format, generated_at }
```

---

### 9. API Access

Downstream consumers (dashboard, business analysts, external systems) query data through the REST API.

**Data movement:**
```
[External Consumer → HTTP GET /api/v1/data/orders?date=2025-01-15]
        │
        ▼
[API Layer → Repository → Database: orders table]
        │
        ▼
[JSON Response Envelope → External Consumer]
```

---

### 10. Archive Stage (Scheduled)

After the configured retention period, the Archive service moves raw files and reports to cold storage.

**Data movement:**
```
[File System: data/raw/orders/2025-01-15/...]
        │
        ▼
[File System: data/archive/raw/orders/2025-01-15/...]

[File System: data/reports/{run_id}/...]
        │
        ▼
[File System: data/archive/reports/{run_id}/...]

[Database: ingestion_events, pipeline_runs]
  → archived flag set to true, archive_path recorded
```

---

## Complete Data Flow — Visual Summary

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            EXTERNAL SOURCES                                   │
│  [User Upload via API]          [Directory Watcher]          [Future: S3]    │
└──────────────────┬───────────────────────┬──────────────────────────────────┘
                   │                       │
                   └───────────┬───────────┘
                               │ Raw File
                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  INGESTION MODULE                                                             │
│  File → Validate Format → Detect Type → Assign ID → Persist Raw File        │
│                                                                               │
│  Writes to: [FS: data/raw/]  [DB: ingestion_events]                         │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │ Trigger Event
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  PIPELINE ENGINE                                                              │
│  Create Run → Orchestrate Stages → Capture Results → Update Run State       │
│                                                                               │
│  Writes to: [DB: pipeline_runs]                                              │
└──────┬─────────────────────────────────────────────────────────────────┬─────┘
       │                                                                   │
       ▼                                                                   │
┌──────────────────┐    valid_df     ┌──────────────────┐   clean_df      │
│  VALIDATION      │ ──────────────► │  CLEANING        │ ─────────────►  │
│  ENGINE          │                 │  ENGINE           │                 │
│                  │  rejected_df    │                   │                 │
│  Writes to:      │ ──► [DB: val.   │  Writes to:       │                 │
│  [DB: val_fail]  │      failures]  │  [DB: clean_log]  │                 │
└──────────────────┘                 └──────────────────┘                 │
                                                                           │
                              transformed_df                               │
┌──────────────────┐ ◄──────────────────────── ┌──────────────────┐       │
│  DATA LOADER     │                            │  TRANSFORMATION  │ ◄─────┘
│                  │                            │  ENGINE          │
│  Upsert to DB    │                            │                  │
│  Writes to:      │                            │  Reads: [DB:     │
│  [DB: orders,    │                            │  reference tbls] │
│   customers,     │                            └──────────────────┘
│   etc.]          │
└──────┬───────────┘
       │ Load Complete
       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  REPORTING MODULE                                                             │
│  Read Results → Build Reports → Export Files → Record Metadata               │
│                                                                               │
│  Writes to: [FS: data/reports/]  [DB: reports]                              │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │ Data Available
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  REST API LAYER                                                               │
│  Authenticated endpoints for data queries, pipeline status, report download  │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │ HTTP Responses
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  DASHBOARD  /  BUSINESS ANALYSTS  /  EXTERNAL SYSTEMS                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Data State Transitions Summary

| Stage | Input Data State | Output Data State |
|---|---|---|
| Data Source | External raw file | Unprocessed binary file |
| Ingestion | Binary file stream | Persisted raw file + DB event record |
| Validation | Raw DataFrame | Valid DF + Rejected DF + Quality score |
| Cleaning | Valid DataFrame | Clean DF (normalized, deduplicated) |
| Transformation | Clean DataFrame | Target-schema DF (enriched, derived fields) |
| Loading | Target-schema DF | Persisted database records |
| Reporting | DB records + stage results | Report files (CSV/Excel) |
| Analytics | DB records | Queryable via API |
| Dashboard | API responses | Visual operational data |
| Archive | Active files + DB records | Cold storage + archived flags |
