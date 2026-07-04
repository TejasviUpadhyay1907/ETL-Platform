# Ingestion Engine
## Enterprise ETL & Data Quality Platform — Phase 4

**Version:** 1.0.0
**Status:** Implemented

---

## Table of Contents

1. Ingestion Architecture
2. Component Sequence Diagram
3. Reader Factory Design
4. Supported File Formats
5. Dataset Type Detection
6. Duplicate Detection
7. Metadata Flow
8. Configuration Guide
9. Error Handling Strategy
10. Future Connector Strategy
11. API Reference

---

## 1. Ingestion Architecture

The ingestion engine is the first stage of the ETL pipeline. It accepts raw files from two sources — HTTP upload and directory polling — and produces a standardised `Dataset` object that all downstream stages consume.

```
┌────────────────────────────────────────────────────────────┐
│                     INGESTION ENGINE                        │
│                                                             │
│  FileReceiver / BatchFileReceiver                          │
│         │                                                   │
│         ▼                                                   │
│  IngestionService.ingest()                                 │
│         │                                                   │
│  ┌──────▼──────────────────────────────────────────────┐  │
│  │ Step 1  FileTypeDetector.validate()                  │  │
│  │         • Extension  • MIME type  • Size             │  │
│  │         • Encoding   • Delimiter  • Sheet names      │  │
│  └──────────────────────────────┬───────────────────────┘  │
│  ┌───────────────────────────── ▼───────────────────────┐  │
│  │ Step 2  HashGenerator.generate()  →  SHA-256          │  │
│  └──────────────────────────────┬───────────────────────┘  │
│  ┌───────────────────────────── ▼───────────────────────┐  │
│  │ Step 3  IngestionTracker.check_duplicate()            │  │
│  │         → reject OR reprocess  (configurable)         │  │
│  └──────────────────────────────┬───────────────────────┘  │
│  ┌───────────────────────────── ▼───────────────────────┐  │
│  │ Step 4  DatasetTypeResolver.resolve()                 │  │
│  │         filename → schema → explicit override         │  │
│  └──────────────────────────────┬───────────────────────┘  │
│  ┌───────────────────────────── ▼───────────────────────┐  │
│  │ Step 5  RawFileStore.store()                          │  │
│  │         data/raw/{type}/{date}/{id}/filename           │  │
│  └──────────────────────────────┬───────────────────────┘  │
│  ┌───────────────────────────── ▼───────────────────────┐  │
│  │ Step 6  ReaderFactory.get_reader() → Reader.read()   │  │
│  │         CSVReader  /  ExcelReader  /  FutureReader    │  │
│  └──────────────────────────────┬───────────────────────┘  │
│  ┌───────────────────────────── ▼───────────────────────┐  │
│  │ Step 7  DatasetTypeResolver (schema refinement)       │  │
│  └──────────────────────────────┬───────────────────────┘  │
│  ┌───────────────────────────── ▼───────────────────────┐  │
│  │ Step 8  MetadataExtractor.extract()                   │  │
│  │         Assembles FileMetadata from all prior steps   │  │
│  └──────────────────────────────┬───────────────────────┘  │
│  ┌───────────────────────────── ▼───────────────────────┐  │
│  │ Step 9  IngestionTracker.create_event()               │  │
│  │         Writes IngestionEvent to PostgreSQL           │  │
│  └──────────────────────────────┬───────────────────────┘  │
│  ┌───────────────────────────── ▼───────────────────────┐  │
│  │ Step 10 Build Dataset object                          │  │
│  │         Dataset(metadata, dataframe, schema)          │  │
│  └──────────────────────────────┬───────────────────────┘  │
│                                  │                          │
└──────────────────────────────────┼──────────────────────────┘
                                   │
                                   ▼
                     Dataset → Validation Stage
```

### Design Principles

- **Single Responsibility**: each component owns exactly one concern
- **No business logic in ingestion**: the ingestion stage is a faithful transcription of source files — no type coercion, no business rules, no cleaning
- **All values preserved as strings**: `dtype=str` on all reads prevents silent coercion (`'00123'` stays `'00123'`, `'2025-01-15'` stays `'2025-01-15'`)
- **Never raises to the caller**: `IngestionService.ingest()` always returns an `IngestionResult` — exceptions are caught internally and translated to failure results
- **Database-only in tracker**: `IngestionTracker` is the only ingestion component that touches the database

---

## 2. Component Sequence Diagram

```
Client          FileReceiver     IngestionService    FileTypeDetector
  │                  │                  │                    │
  │ upload(bytes)    │                  │                    │
  │─────────────────►│                  │                    │
  │                  │ ingest_bytes()   │                    │
  │                  │─────────────────►│                    │
  │                  │                  │ validate(path)     │
  │                  │                  │───────────────────►│
  │                  │                  │◄───────────────────│
  │                  │                  │ FileValidationResult
  │
  │           HashGenerator       DatasetTypeResolver    RawFileStore
  │                  │                  │                    │
  │                  │ generate(path)   │                    │
  │                  │◄─────────────────│                    │
  │                  │  sha256_hex      │                    │
  │                  │                  │ check_duplicate()  │
  │                  │                  │  (IngestionTracker)│
  │                  │                  │                    │
  │                  │                  │ resolve(filename)  │
  │                  │                  │───────────────────►│
  │                  │                  │◄───────────────────│
  │                  │                  │ DatasetType enum   │
  │                  │                  │                    │
  │                  │                  │ store(path)        │
  │                  │                  │───────────────────►│
  │                  │                  │◄───────────────────│
  │                  │                  │ stored_path        │
  │
  │           ReaderFactory         CSVReader/ExcelReader
  │                  │                  │
  │                  │ get_reader(ext)  │
  │                  │◄─────────────────│
  │                  │                  │ read(stored_path)  │
  │                  │                  │───────────────────►│
  │                  │                  │◄───────────────────│
  │                  │                  │ (DataFrame, Schema)│
  │
  │           MetadataExtractor   IngestionTracker      DB
  │                  │                  │                │
  │                  │ extract(...)     │                │
  │                  │◄─────────────────│                │
  │                  │ FileMetadata     │                │
  │                  │                  │ create_event() │
  │                  │                  │───────────────►│
  │                  │                  │◄───────────────│
  │                  │                  │ event_id       │
  │
  │    IngestionResult(success=True, dataset=Dataset)
  │◄──────────────────────────────────────────────────
```

---

## 3. Reader Factory Design

The `ReaderFactory` implements the **Factory Pattern** with a class-level registry. The rest of the system never imports `CSVReader` or `ExcelReader` directly.

```python
# How the pipeline uses readers
reader = ReaderFactory.get_reader("csv")       # returns CSVReader
reader = ReaderFactory.get_reader("xlsx")      # returns ExcelReader
df, schema = reader.read(file_path, encoding="utf-8", delimiter=",")
```

### Class Hierarchy

```
BaseReader  (abstract)
├── CSVReader
│   ├── read(path, encoding, delimiter) → (DataFrame, DatasetSchema)
│   └── read_chunked(path, chunk_size, encoding, delimiter) → Generator
└── ExcelReader
    ├── read(path, sheet_name) → (DataFrame, DatasetSchema)
    ├── read_chunked(path, chunk_size, sheet_name) → Generator
    └── get_sheet_names(path) → list[str]
```

### Adding a New Reader

```python
# 1. Create the reader
class ParquetReader(BaseReader):
    @property
    def reader_name(self) -> str:
        return "ParquetReader"

    def can_read(self, ext: str) -> bool:
        return ext == "parquet"

    def read(self, file_path, **kwargs):
        df = pd.read_parquet(file_path)
        return df, self._build_schema(df)

    def read_chunked(self, file_path, chunk_size=10_000, **kwargs):
        ...

# 2. Register it — no existing code changes needed
ReaderFactory.register(ParquetReader())
```

---

## 4. Supported File Formats

| Format | Extension | Engine | Chunked | Notes |
|---|---|---|---|---|
| CSV | `.csv` | pandas `read_csv` | ✅ Native | Encoding and delimiter auto-detected |
| Excel 2007+ | `.xlsx` | openpyxl | ✅ (slice) | Sheet selection supported |
| Excel 97–2003 | `.xls` | xlrd | ✅ (slice) | Password-protected files rejected |

### CSV Encoding Detection Priority

1. UTF-8 with BOM (Excel CSV exports)
2. UTF-8
3. Latin-1 (Western European)
4. CP1252 (Windows Western European)
5. UTF-16
6. Fallback: `latin-1` (never raises UnicodeDecodeError)

### CSV Delimiter Detection

Uses Python's `csv.Sniffer` with a fallback to comma. Supports: `,` `\t` `;` `|`

### Excel Sheet Selection

The active sheet defaults to the **first sheet** in the workbook. Override with the `sheet_name` parameter. Sheet names are detected without loading cell data.

---

## 5. Dataset Type Detection

Three-level detection strategy, tried in priority order:

| Priority | Method | Example |
|---|---|---|
| 1 | Explicit override | `dataset_type="orders"` API parameter |
| 2 | Filename keyword | `orders_2025_01.csv` → `ORDERS` |
| 3 | Schema matching | Column overlap ≥ 50% via Jaccard similarity |

### Filename Keywords

| Keyword | Dataset Type |
|---|---|
| `order` | ORDERS |
| `customer` | CUSTOMERS |
| `product` | PRODUCTS |
| `inventory` | INVENTORY |
| `supplier` | SUPPLIERS |
| `payment` | PAYMENTS |

### Schema Matching

Compares actual column names from the file against expected columns from each dataset's `schema.yaml`. Returns the type with the highest Jaccard similarity score above 50%.

**Adding new keywords:** Edit `DATASET_FILENAME_PATTERNS` in `app/utils/constants.py`.
**Extending schema rules:** Edit `config/datasets/{type}/schema.yaml`.

---

## 6. Duplicate Detection

Every file receives a SHA-256 hash before processing. The hash is checked against `ingestion_events.file_hash` in the database.

### Duplicate Handling Policy

Configured via the `IngestionService` constructor parameter `duplicate_policy`:

| Policy | Behaviour | Use case |
|---|---|---|
| `reject` (default) | Second upload returns `status=duplicate`, not processed | Production — prevent accidental double-processing |
| `reprocess` | Second upload is processed normally but flagged | Development — re-test the pipeline on the same file |

### Duplicate Response

```json
{
  "success": false,
  "error": {
    "code": "DUPLICATE_FILE",
    "message": "File 'orders_2025_01.csv' is a duplicate of a previously ingested file (event abc-123)."
  }
}
```

---

## 7. Metadata Flow

Every ingestion event records the following in `ingestion_events`:

| Field | Source | Description |
|---|---|---|
| `id` | UUID generated | Unique event identifier |
| `original_filename` | API/caller | As uploaded by the user |
| `stored_filename` | RawFileStore | Filename on disk |
| `file_path` | RawFileStore | Full path under `data/raw/` |
| `file_extension` | FileTypeDetector | Lowercase, no dot |
| `file_size_bytes` | File stat | Bytes |
| `file_hash` | HashGenerator | SHA-256 hex |
| `dataset_type` | DatasetTypeResolver | One of 6 types |
| `encoding` | FileTypeDetector | e.g. `utf-8`, `latin-1` |
| `delimiter` | FileTypeDetector | CSV delimiter character |
| `row_count_raw` | Schema | Total lines including header |
| `row_count_data` | Schema | Data rows only |
| `source_type` | Caller | `upload`, `directory_watch`, `api_push` |
| `uploaded_by` | API header | API key or user identifier |
| `status` | IngestionTracker | `received → processed / rejected / duplicate` |

### Stored File Path Structure

```
data/raw/{dataset_type}/{YYYY-MM-DD}/{ingestion_id}/{original_filename}

Example:
data/raw/orders/2025-01-15/a3f7b2c1-…/orders_2025_01.csv
```

---

## 8. Configuration Guide

All ingestion settings load from environment variables (via `AppConfig`) or `config/app.yaml`.

| Setting | Env Var | Default | Description |
|---|---|---|---|
| Upload directory | `UPLOAD_DIRECTORY` | `data/raw` | Root for raw file storage |
| Max file size | `MAX_UPLOAD_SIZE_MB` | `500` | Maximum upload in MB |
| Allowed extensions | `ALLOWED_FILE_TYPES` | `csv,xlsx,xls` | Comma-separated list |
| Chunk size | `PIPELINE_CHUNK_SIZE` | `10000` | Rows per chunk in chunked reads |

### Dataset Type Mapping

Edit `config/datasets/{type}/schema.yaml` to update expected column names for schema-based type resolution. No code changes required.

---

## 9. Error Handling Strategy

All errors are caught inside `IngestionService._run_ingestion_pipeline()` and returned as `IngestionResult(success=False, error_code=..., error_message=...)`. The service never raises.

| Scenario | Exception Class | Error Code | HTTP Status |
|---|---|---|---|
| File not found | `FileNotFoundException` | `FILE_NOT_FOUND` | 422 |
| Unsupported extension | `InvalidFileTypeException` | `INVALID_FILE_TYPE` | 422 |
| File too large | `FileTooLargeException` | `FILE_TOO_LARGE` | 413 |
| Empty file | `FileReadException` | `FILE_READ_ERROR` | 422 |
| Password-protected Excel | `FileReadException` | `FILE_READ_ERROR` | 422 |
| Unknown dataset type | `ValueError` (caught) | `UNKNOWN_DATASET_TYPE` | 422 |
| Duplicate file (reject) | Internal check | `DUPLICATE_FILE` | 409 |
| Corrupt file | `FileReadException` | `FILE_READ_ERROR` | 422 |
| Encoding error | `FileReadException` | `FILE_READ_ERROR` | 422 |

---

## 10. Future Connector Strategy

The ingestion engine is designed for connector extensibility. Adding a new source type requires implementing two interfaces:

### New Reader (new file format)

```python
class ParquetReader(BaseReader):
    def can_read(self, ext): return ext == "parquet"
    def read(self, path, **kw): ...
    def read_chunked(self, path, chunk_size, **kw): ...

ReaderFactory.register(ParquetReader())
```

### New Source Connector (new storage location)

Create a connector that downloads the file to a temp path and calls `IngestionService.ingest()`:

```python
class S3Connector:
    def fetch_and_ingest(self, s3_uri: str, session) -> IngestionResult:
        tmp_path = self._download_from_s3(s3_uri)
        svc = IngestionService(session)
        return svc.ingest(tmp_path, source_type="s3")
```

Planned connectors:

| Connector | Trigger | Notes |
|---|---|---|
| S3 | S3 event notification | boto3 download → temp file → ingest |
| Azure Blob | Event Grid trigger | azure-storage-blob → temp file → ingest |
| GCS | Pub/Sub notification | google-cloud-storage → temp file → ingest |
| SFTP | Scheduler | paramiko → temp file → ingest |
| REST API | Scheduler | httpx → bytes → `ingest_bytes()` |

All connectors feed into the same `IngestionService` entry point. No changes to downstream stages required.

---

## 11. API Reference

### POST /api/v1/ingest/upload

Upload a single CSV or Excel file.

**Request:** `multipart/form-data`
- `file`: the file (required)
- `dataset_type`: override detection (optional): `orders|customers|products|inventory|suppliers|payments`

**Response 201:**
```json
{
  "success": true,
  "data": {
    "ingestion_event_id": "a3f7b2c1-...",
    "processing_id": "b4e8c3d2-...",
    "original_filename": "orders_2025_01.csv",
    "dataset_type": "orders",
    "file_size_bytes": 45312,
    "row_count": 5000,
    "column_count": 9,
    "column_names": ["order_id", "customer_id", ...],
    "encoding": "utf-8",
    "delimiter": ",",
    "status": "processed",
    "is_duplicate": false
  }
}
```

**Response 409 (duplicate):**
```json
{
  "success": false,
  "error": { "code": "DUPLICATE_FILE", "message": "..." }
}
```

### POST /api/v1/ingest/upload/batch

Upload up to 10 files in one request. Returns per-file results.

### GET /api/v1/ingest/events

List ingestion events. Supports `?dataset_type=orders&status=processed` filters.

### GET /api/v1/ingest/events/{event_id}

Retrieve a specific ingestion event by UUID.
