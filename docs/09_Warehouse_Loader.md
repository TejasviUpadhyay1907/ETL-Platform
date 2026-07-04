# Phase 9 — Enterprise Warehouse Loader

## Overview

The Warehouse Loader is the final stage of the ETL pipeline. It receives an analytics-ready DataFrame from the Transformation Engine and writes it to the target warehouse tables using a configurable load strategy. Every load is transactional, idempotent, and fully audited.

```
Pipeline Engine
     │
     ▼
WarehouseLoader.load(df, dataset_type, pipeline_run_id)
     │
     ├─ Idempotency Check (audit_log lookup)
     │
     ├─ LoadRegistry → resolve strategy + target table
     │
     ├─ LoadStrategy.execute(df, target_table, ...)
     │       ├── BulkInsertStrategy
     │       ├── UpsertStrategy          ← default
     │       ├── AppendStrategy
     │       ├── ReplaceStrategy
     │       └── IncrementalStrategy
     │
     ├─ LoadReport (metrics, batch results, audit trail)
     │
     ├─ AuditLog persist (RECORD_LOADED event)
     │
     └─ LoadResult → PipelineResult
```

---

## Architecture

### WarehouseLoader (`app/loading/loader.py`)

The primary entry point. Stateless between calls.

```python
loader = WarehouseLoader(session=db)
result = loader.load(
    transformed_df=df,
    dataset_type="orders",
    pipeline_run_id="abc-123",
)
```

**Internal pipeline:**

1. Idempotency check — look up `audit_log` for a prior `RECORD_LOADED` event for this `pipeline_run_id`
2. Resolve strategy and target table via `LoadRegistry`
3. Execute the strategy (returns `LoadMetrics` + `list[LoadBatchResult]`)
4. Build `LoadReport` with full audit trail
5. Persist audit record to `audit_log`
6. Update `pipeline_runs.loaded_records`
7. Return `LoadResult` — never raises

---

### LoadRegistry (`app/loading/load_registry.py`)

Maps `dataset_type → (LoadStrategy, target_table)`. Built-in defaults:

| Dataset Type | Strategy      | Target Table |
|-------------|---------------|-------------|
| orders      | upsert        | orders      |
| customers   | upsert        | customers   |
| products    | upsert        | products    |
| inventory   | incremental   | inventory   |
| suppliers   | upsert        | suppliers   |
| payments    | append        | payments    |

Overrides can be registered at runtime:

```python
registry.register_override("orders", {
    "strategy_type": "replace",
    "target_table": "orders_staging",
    "batch_size": 500,
})
```

---

## Load Strategies

All strategies inherit from `BaseLoadStrategy` and implement:

```python
def execute(
    self,
    df: pd.DataFrame,
    target_table: str,
    dataset_type: str,
    pipeline_run_id: str | None = None,
) -> tuple[LoadMetrics, list[LoadBatchResult]]:
    ...
```

### 1. BulkInsertStrategy

Inserts all records in configurable batches using `pandas.DataFrame.to_sql`. Fails on constraint violations unless `allow_partial=True`.

- **Use for:** Initial loads, staging tables, append-only datasets
- **Batch size:** configurable (default 1000)

### 2. UpsertStrategy *(default)*

Insert new records, update existing ones on conflict. Uses domain repository `bulk_upsert()` methods on PostgreSQL; falls back to `pandas.to_sql` on SQLite (tests).

- **Conflict columns:** per-dataset (e.g., `email` for customers, `order_number` for orders)
- **Idempotent:** yes — safe to re-run
- **Use for:** incremental file-based loads

### 3. AppendStrategy

Always appends records. Ignores primary-key conflicts. Best for event-sourced datasets.

- **Use for:** payments, audit events, log tables
- **Idempotent:** no — duplicate records possible without idempotency check

### 4. ReplaceStrategy

Truncates the target table then reloads with the full DataFrame in a single transaction. Fails atomically — either full replacement or no change.

- **Use for:** dimension tables, full refreshes
- **Idempotent:** yes

### 5. IncrementalStrategy

Filters the DataFrame to only rows newer than a configurable watermark before inserting. Supports timestamp, numeric ID, or hash watermarks.

```python
LoadStrategy(
    strategy_type="incremental",
    watermark_column="updated_at",
    watermark_value="2024-01-01T00:00:00",
)
```

- **Use for:** large tables where only recent deltas need loading
- **Idempotent:** yes (same watermark = same filter)

---

## Domain Models (`app/loading/models.py`)

### LoadStrategyType

```python
class LoadStrategyType:
    BULK_INSERT  = "bulk_insert"
    UPSERT       = "upsert"
    APPEND       = "append"
    INCREMENTAL  = "incremental"
    REPLACE      = "replace"
```

### LoadStrategy

Configuration passed to the strategy:

```python
@dataclass
class LoadStrategy:
    strategy_type:    str = "upsert"
    batch_size:       int = 1000
    conflict_columns: list[str] = []
    watermark_column: str | None = None
    watermark_value:  Any = None
    allow_partial:    bool = True
    validate_counts:  bool = True
```

### LoadMetrics

Aggregated statistics for the load operation:

```python
@dataclass
class LoadMetrics:
    total_rows_input:   int
    rows_inserted:      int
    rows_updated:       int
    rows_skipped:       int
    rows_failed:        int
    batch_count:        int
    total_duration_ms:  float
    avg_batch_ms:       float       # computed
    throughput_rows_sec: float      # computed
    rows_loaded:        int         # property: inserted + updated
```

### LoadReport

Full audit trail for one load operation, including all batch results:

```python
@dataclass
class LoadReport:
    report_id:        str          # UUID
    pipeline_run_id:  str | None
    dataset_type:     str
    target_table:     str
    strategy_used:    str
    loaded_at:        datetime
    duration_seconds: float
    metrics:          LoadMetrics
    batch_results:    list[LoadBatchResult]
    success:          bool
    idempotency_key:  str | None
```

### LoadResult

Top-level output returned to the pipeline engine:

```python
@dataclass
class LoadResult:
    success:          bool
    dataset_type:     str
    rows_inserted:    int = 0
    rows_updated:     int = 0
    rows_skipped:     int = 0
    rows_failed:      int = 0
    rows_loaded:      int          # property: inserted + updated
    target_table:     str = ""
    strategy_used:    str = ""
    report:           LoadReport
    error_message:    str | None
    duration_seconds: float
    idempotent_skip:  bool = False  # True = this run was already loaded
```

> **Important:** `rows_loaded` is a computed `@property`. Never pass it as a constructor argument.

---

## Idempotency

Every load is keyed by `pipeline_run_id`. Before executing, the loader queries `audit_log` for an existing `RECORD_LOADED` event with the same `run_id` and `stage="load"`. If found, it returns immediately with `idempotent_skip=True`.

This makes all load operations safe to re-run — whether from a retry, a resume, or a replay. No duplicate data is written.

To bypass idempotency (e.g. force re-load):

```python
loader = WarehouseLoader(session=db, check_idempotency=False)
```

---

## Batching

All strategies split the DataFrame into chunks of `batch_size` rows before writing. Each chunk produces one `LoadBatchResult` capturing rows attempted, inserted, updated, failed, and duration.

If `allow_partial=True` (default), successful batches are committed even when later batches fail. This maximises data availability for large files. Set `allow_partial=False` to make the entire load atomic.

---

## Error Handling

- Constraint violations, connection failures, and unexpected exceptions are caught per-batch
- Failed batches are recorded in `LoadBatchResult.error_message`
- The session is rolled back after each batch failure to avoid `PendingRollbackError`
- `WarehouseLoader.load()` never raises — it always returns a `LoadResult`
- Audit persistence and `pipeline_runs` updates are non-fatal — a DB write failure does not abort the load

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/load/run` | Trigger a load for a dataset |
| `GET`  | `/api/v1/load/report/{pipeline_run_id}` | Full load report |
| `GET`  | `/api/v1/load/summary/{pipeline_run_id}` | Summary metrics |
| `GET`  | `/api/v1/load/history` | Load history (paginated) |
| `GET`  | `/api/v1/load/metrics/{pipeline_run_id}` | Performance metrics |

---

## Database / Audit

Each successful load writes one `AuditLog` record:

```python
AuditLog(
    event_type = "RECORD_LOADED",
    severity   = "INFO",
    run_id     = pipeline_run_id,
    stage      = "load",
    message    = "Load succeeded: orders → orders, strategy=upsert, rows=1000",
    context_data = report.to_summary_dict(),
)
```

`pipeline_runs.loaded_records` is updated after each successful load.

---

## Performance Considerations

- Default batch size is 1000 rows — tune based on row width and network latency
- `BulkInsertStrategy` uses `pandas.to_sql(method="multi")` for multi-row inserts
- `UpsertStrategy` uses dialect-aware paths: PostgreSQL uses repository `bulk_upsert()`, SQLite falls back to `to_sql(if_exists="append")`
- Connection pooling is handled by SQLAlchemy at the `engine` layer (Phase 3)
- For very large files (>1M rows), set `batch_size=5000` and `allow_partial=True` to pipeline batches without holding a single large transaction

---

## Extending the Loader

### Add a new strategy

1. Create `app/loading/strategies/my_strategy.py` subclassing `BaseLoadStrategy`
2. Set `strategy_name = "my_strategy"`
3. Implement `execute(df, target_table, dataset_type, pipeline_run_id) -> tuple[LoadMetrics, list[LoadBatchResult]]`
4. Register in `LoadRegistry._STRATEGY_MAP`

### Add a new dataset mapping

```python
registry.register_override("new_table", {
    "strategy_type": "upsert",
    "target_table":  "new_table",
    "batch_size":    500,
})
```

---

## Test Coverage

| File | Coverage |
|------|---------|
| `app/loading/models.py` | 97.94% |
| `app/loading/loader.py` | 75.56% |
| `app/loading/load_registry.py` | 100.00% |
| `app/loading/strategies/base_strategy.py` | 100.00% |
| `app/loading/strategies/upsert_strategy.py` | 76.32% |
| `app/loading/strategies/bulk_insert_strategy.py` | 70.59% |
| `app/loading/strategies/append_strategy.py` | 79.45% |
| `app/loading/strategies/replace_strategy.py` | 85.00% |
| `app/loading/strategies/incremental_strategy.py` | 82.54% |

Test file: `tests/unit/test_core/test_warehouse_loader.py` (47 tests)

---

## Phase 9 Contract

The Pipeline Engine calls the loader via `StageExecutor.run_load()`:

```python
loader = WarehouseLoader(session=self._session)
load_result = loader.load(
    transformed_df=transformation_result.transformed_df,
    dataset_type=transformation_result.dataset_type,
    pipeline_run_id=ctx.pipeline_run_id,
)
```

The full ETL flow is now complete:

```
Ingestion → Validation → Cleaning → Transformation → Warehouse Loading → Pipeline Complete
```
