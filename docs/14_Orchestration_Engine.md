# Pipeline Orchestration Engine
## Enterprise ETL & Data Quality Platform — Phase 8

**Version:** 1.0.0  
**Status:** Implemented  
**Coverage:** 67.96% (pipeline package)  
**Tests:** 93 pipeline tests, 883 total

---

## Table of Contents

1. Orchestration Architecture
2. Pipeline Execution Lifecycle
3. State Machine
4. Retry Strategy
5. Checkpoint Mechanism
6. Failure Recovery
7. Event System
8. Pipeline Definitions & Registry
9. Phase 9 (Warehouse Loader) Contract
10. Configuration Guide
11. Extension Guide
12. API Reference

---

## 1. Orchestration Architecture

The Pipeline Orchestration Engine coordinates all previously implemented ETL stages without duplicating their logic. It acts as a lightweight workflow engine similar to Apache Airflow or AWS Step Functions.

```
PipelineTriggerService (API-facing entry point)
        ↓
PipelineExecutor._run_with_retry()
        │
        ├── PipelineExecutor._run_pipeline()
        │       │
        │       ├── PipelineRegistry    → resolve pipeline definition
        │       ├── EventEmitter        → emit PIPELINE_STARTED
        │       │
        │       ├── [Stage Loop]
        │       │   ├── StageExecutor.run_ingestion()    → IngestionEngine (Phase 4)
        │       │   ├── StageExecutor.run_validation()   → ValidationEngine (Phase 5)
        │       │   ├── StageExecutor.run_cleaning()     → CleaningEngine (Phase 6)
        │       │   ├── StageExecutor.run_transformation() → TransformationEngine (Phase 7)
        │       │   └── StageExecutor.run_load()         → PLACEHOLDER (Phase 9)
        │       │
        │       ├── CheckpointManager.save()  → after each stage
        │       ├── EventEmitter              → per-stage events
        │       └── PipelineRunRepository    → DB updates
        │
        └── RetryManager               → decides retry on failure
        
→ PipelineResult (input to Phase 9 Warehouse Loader)
```

### Design Principles

- **Zero logic duplication** — the orchestrator calls existing engines; it adds no business logic
- **Fault-tolerant DB writes** — DB failures are logged and non-fatal; the pipeline continues
- **Always returns** — `PipelineExecutor.execute()` always returns a `PipelineResult`, never raises
- **Stateless executor** — all state lives in `PipelineResult` and the database
- **Configuration-driven** — pipeline definitions in `PipelineRegistry`; retry policy via API

---

## 2. Pipeline Execution Lifecycle

```
1. PipelineTriggerService.trigger(dataset_type, source_file_path, ...)
2. Validate dataset_type against DatasetType enum
3. Build RetryPolicy (from request or default)
4. PipelineExecutor.execute() called
5. Generate pipeline_run_id (UUID4)
6. Build PipelineContext (immutable, passed to all stages)
7. Create PipelineRun DB record
8. Emit PIPELINE_STARTED event
9. Execute stages in order:
   ├── ingestion   → IngestionService.ingest()
   ├── validation  → ValidationEngine.validate()
   ├── cleaning    → CleaningEngine.clean()
   ├── transformation → TransformationEngine.transform()
   └── load        → Placeholder (Phase 9)
10. After EACH stage:
    ├── Emit STAGE_COMPLETED or STAGE_FAILED
    ├── Save checkpoint to audit_log
    └── Create StageResult DB record
11. Build PipelineMetrics from stage results
12. Finalize PipelineRun DB record
13. Emit PIPELINE_COMPLETED or PIPELINE_FAILED
14. Return PipelineResult
```

---

## 3. State Machine

```
         ┌─────────┐
         │ CREATED │
         └────┬────┘
              │ trigger()
         ┌────▼────┐
         │ QUEUED  │
         └────┬────┘
              │ execute()
         ┌────▼────┐
         │ RUNNING │◄────────────────────────┐
         └────┬────┘                         │
    ┌─────────┼──────────┬─────────┐         │
    ▼         ▼          ▼         ▼         │
COMPLETED  FAILED    PARTIAL  CANCELLED   RETRYING
                        │         │           │
                        ▼         │           │
                     FAILED       │      RUNNING
                                  │
                               (terminal)
```

**Terminal states:** `completed`, `failed`, `cancelled`

**Illegal transitions are rejected:**
```python
PipelineState.is_valid_transition("completed", "running")  # False
PipelineState.is_valid_transition("running", "completed")  # True
```

---

## 4. Retry Strategy

Configured via `RetryPolicy` — passed at trigger time or using the default:

```python
RetryPolicy(
    max_retries=3,
    retry_delay_seconds=5.0,
    backoff_strategy="exponential",  # immediate | linear | exponential
    backoff_multiplier=2.0,
    max_delay_seconds=300.0,
    retry_on_stages=[],              # [] = retry any failed stage
)
```

| Strategy | Delay formula | Example (5s base, ×2) |
|---|---|---|
| `immediate` | 0 | 0s, 0s, 0s |
| `linear` | `delay × attempt` | 5s, 10s, 15s |
| `exponential` | `delay × multiplier^attempt` | 5s, 10s, 20s |

**API override:**
```json
{
  "dataset_type": "orders",
  "retry_policy": {
    "max_retries": 5,
    "retry_delay_seconds": 10,
    "backoff_strategy": "linear"
  }
}
```

**Prevent retries (testing/debugging):**
```python
RetryPolicy.no_retry()  # max_retries=0
```

---

## 5. Checkpoint Mechanism

A checkpoint is saved to `audit_logs` (with `is_checkpoint=True` in `context_data`) after each stage completes. The checkpoint records:

```json
{
  "checkpoint_id": "uuid",
  "pipeline_run_id": "uuid",
  "pipeline_name": "orders_pipeline",
  "dataset_type": "orders",
  "last_completed_stage": "cleaning",
  "last_completed_stage_order": 2,
  "completed_stages": ["ingestion", "validation", "cleaning"],
  "retry_count": 0,
  "is_checkpoint": true
}
```

### Resume from checkpoint

```bash
POST /api/v1/pipelines/{run_id}/resume
```

```python
svc = PipelineTriggerService(session)
result = svc.resume(pipeline_run_id="abc-123", source_file_path="/data/orders.csv")
```

The executor loads the latest checkpoint, determines `last_completed_stage_order`, and starts execution from `last_completed_stage_order + 1`. Stages before the checkpoint are skipped.

**DataFrames are NOT checkpointed** — only metadata is stored. On resume, the pipeline re-reads the source file and re-runs skipped stages instantly up to the checkpoint point.

---

## 6. Failure Recovery

### Stage failure
```
Stage fails → STAGE_FAILED event emitted → PipelineRun.failed_stage set
→ RetryManager.should_retry() checked
→ If retry: sleep(backoff) → re-run entire pipeline
→ If no retry: PIPELINE_FAILED event → PipelineResult(success=False)
```

### Graceful shutdown
All DB writes are wrapped in try/except with `session.rollback()` — a DB failure never crashes the pipeline. The `PipelineResult` is always returned.

### Cancellation
```bash
POST /api/v1/pipelines/{run_id}/cancel
```
Sets `PipelineRun.status = "cancelled"` in the DB. Running pipelines check for cancellation signals between stages (future enhancement: per-stage cancellation check).

---

## 7. Event System

Every pipeline lifecycle transition emits an event to the `audit_logs` table:

| Event | When | DB event_type |
|---|---|---|
| Pipeline started | Execution begins | `PIPELINE_STARTED` |
| Stage started | Before each stage | `STAGE_STARTED` |
| Stage completed | After successful stage | `STAGE_COMPLETED` |
| Stage failed | After failed stage | `STAGE_FAILED` |
| Pipeline completed | All stages done | `PIPELINE_COMPLETED` |
| Pipeline failed | Any stage failed (no retry left) | `PIPELINE_FAILED` |
| Pipeline cancelled | cancel() called | `PIPELINE_CANCELLED` |
| Checkpoint saved | After each stage | `STAGE_COMPLETED` (tagged) |

Query events for a run:
```bash
GET /api/v1/pipelines/{run_id}/events
GET /api/v1/pipelines/{run_id}/events?event_type=STAGE_FAILED
```

---

## 8. Pipeline Definitions & Registry

Six default pipelines are registered automatically (one per dataset type):

```python
from app.pipeline.pipeline_registry import get_registry
reg = get_registry()
defn = reg.get_by_dataset_type("orders")
# PipelineDefinition(name="orders_pipeline", dataset_type="orders", enabled=True)
```

### Adding a custom pipeline

```python
from app.pipeline.pipeline_registry import PipelineDefinition, get_registry

custom = PipelineDefinition(
    name="orders_express_pipeline",
    dataset_type="orders",
    stage_order=["ingestion", "cleaning", "load"],  # skip validation
    max_runtime_seconds=600,
    description="Express pipeline — no validation",
)
get_registry().register(custom)
```

### Disable a pipeline

```bash
GET /api/v1/pipelines/definitions          # list all
# Then via code:
get_registry().disable("orders_pipeline")
```

---

## 9. Phase 9 (Warehouse Loader) Contract

The `PipelineResult` is the direct input to the Warehouse Loader (Phase 9):

```python
# Phase 9 will call exactly this:
loader = WarehouseLoader(session=db)
load_result = loader.load(
    transformed_df=pipeline_result.transformed_df,   # pd.DataFrame
    dataset_type=pipeline_result.dataset_type,       # str
    pipeline_run_id=pipeline_result.pipeline_run_id, # str
)
```

### PipelineResult fields consumed by Phase 9

| Field | Type | Description |
|---|---|---|
| `transformed_df` | `pd.DataFrame` | Analytics-ready data from TransformationEngine |
| `dataset_type` | `str` | Target table selection |
| `pipeline_run_id` | `str` | For FK relationships in warehouse tables |
| `metrics` | `PipelineMetrics` | Record counts for loader statistics |
| `stage_results` | `list[PipelineStageResult]` | Full lineage from all stages |
| `ingestion_event_id` | `str \| None` | Link back to source file |

### Current Load Stage (Placeholder)

The load stage currently marks all transformed records as `ready_for_loading` without writing to the warehouse. Phase 9 replaces this with:

```python
class WarehouseLoader:
    def load(self, transformed_df, dataset_type, pipeline_run_id) -> LoadResult:
        # Actual upsert to operational tables
        ...
```

---

## 10. Configuration Guide

All pipeline settings come from environment variables / `AppConfig`:

| Setting | Default | Description |
|---|---|---|
| `PIPELINE_ENABLE_SCHEDULER` | `False` | Enable APScheduler for directory polling |
| `PIPELINE_CHUNK_SIZE` | `10000` | Rows per chunk in processing stages |
| `PIPELINE_MAX_CONCURRENT_RUNS` | `5` | Max simultaneous pipeline runs |
| `PIPELINE_STAGE_TIMEOUT_SECONDS` | `3600` | Timeout per stage (future) |

Retry policy defaults (no env var — passed via API):
- `max_retries`: 3
- `retry_delay_seconds`: 5.0
- `backoff_strategy`: exponential
- `max_delay_seconds`: 300.0

---

## 11. Extension Guide

### Adding a new stage

1. Add the stage name to `StageName.ALL` in `models.py`
2. Add a `run_{stage}()` method to `StageExecutor`
3. Add the dispatch case in `PipelineExecutor._execute_stage()`
4. No other changes needed

### Adding a new trigger type

```python
class S3TriggerService:
    def trigger_from_s3(self, bucket: str, key: str, dataset_type: str) -> PipelineResult:
        local_path = self._download_from_s3(bucket, key)
        svc = PipelineTriggerService(self._session)
        return svc.trigger(
            dataset_type=dataset_type,
            source_file_path=str(local_path),
            trigger_type="s3_event",
            triggered_by=f"s3://{bucket}/{key}",
        )
```

### Custom retry policy per dataset type

Register per-dataset policies in the `PipelineRegistry`:

```python
defn = PipelineDefinition(
    name="payments_pipeline",
    dataset_type="payments",
    retry_policy=RetryPolicy(max_retries=5, retry_delay_seconds=30.0),
)
get_registry().register(defn)
```

---

## 12. API Reference

### POST /api/v1/pipelines/run

Trigger a new pipeline run.

**Request:**
```json
{
  "dataset_type": "orders",
  "source_file_path": "/data/raw/orders/2025-01-15/run-001/orders.csv",
  "original_filename": "orders_2025_01_15.csv",
  "triggered_by": "data_engineer_01",
  "retry_policy": {
    "max_retries": 3,
    "retry_delay_seconds": 5.0,
    "backoff_strategy": "exponential"
  }
}
```

**Response 200:**
```json
{
  "success": true,
  "data": {
    "pipeline_run_id": "abc-123",
    "pipeline_name": "orders_pipeline",
    "status": "completed",
    "completed_stages": ["ingestion","validation","cleaning","transformation","load"],
    "duration_seconds": 4.782,
    "metrics": {
      "total_records_ingested": 5000,
      "total_records_transformed": 4975,
      "quality_score": 94.5
    }
  }
}
```

### POST /api/v1/pipelines/{run_id}/resume
Resume from last checkpoint.

### POST /api/v1/pipelines/{run_id}/retry
Retry from scratch.

### POST /api/v1/pipelines/{run_id}/cancel
Cancel a running pipeline.

### GET /api/v1/pipelines
List runs with filters: `?status=failed&dataset_type=orders`

### GET /api/v1/pipelines/{run_id}
Full run details with stage results.

### GET /api/v1/pipelines/{run_id}/events
Lifecycle events (paginated). Filter: `?event_type=STAGE_FAILED`

### GET /api/v1/pipelines/{run_id}/metrics
Execution metrics: durations, record counts, throughput.

### GET /api/v1/pipelines/{run_id}/checkpoints
Checkpoint history for resume/audit.

### GET /api/v1/pipelines/history
Paginated execution history with filters.

### GET /api/v1/pipelines/definitions
All registered pipeline definitions.
