"""
Warehouse Loading domain models.

Pure Python dataclasses — the contract between the loading components
and the Pipeline Orchestration Engine.

LoadStrategy    — which strategy to use for this dataset
LoadBatchResult — outcome of one batch write
LoadReport      — complete audit trail for one load operation
LoadResult      — top-level output returned to the pipeline engine

The Pipeline Engine updates pipeline_runs.loaded_records from
LoadResult.rows_loaded after this stage completes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# Strategy constants
# ---------------------------------------------------------------------------

class LoadStrategyType:
    BULK_INSERT  = "bulk_insert"    # batch insert, fail on conflict
    UPSERT       = "upsert"         # insert or update on conflict
    APPEND       = "append"         # always insert, ignore conflicts
    INCREMENTAL  = "incremental"    # only new records (watermark-based)
    REPLACE      = "replace"        # truncate + reload target table


# ---------------------------------------------------------------------------
# LoadStrategy — configuration for one load operation
# ---------------------------------------------------------------------------

@dataclass
class LoadStrategy:
    """
    Configuration that controls how a dataset is written to the database.

    Strategy is resolved per dataset_type from config. Callers can override
    via the API request or pipeline definition.
    """

    strategy_type:    str = LoadStrategyType.UPSERT
    batch_size:       int = 1000
    conflict_columns: list[str] = field(default_factory=list)   # for upsert
    watermark_column: str | None = None                          # for incremental
    watermark_value:  Any = None                                 # last loaded value
    allow_partial:    bool = True    # True = commit successful batches even if some fail
    validate_counts:  bool = True    # True = verify row counts after load

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_type":    self.strategy_type,
            "batch_size":       self.batch_size,
            "conflict_columns": self.conflict_columns,
            "watermark_column": self.watermark_column,
            "allow_partial":    self.allow_partial,
        }


# ---------------------------------------------------------------------------
# LoadBatchResult — outcome of one batch
# ---------------------------------------------------------------------------

@dataclass
class LoadBatchResult:
    """Outcome of writing one batch of records."""

    batch_number:   int
    batch_size:     int
    rows_attempted: int = 0
    rows_inserted:  int = 0
    rows_updated:   int = 0
    rows_skipped:   int = 0
    rows_failed:    int = 0
    duration_ms:    float = 0.0
    error_message:  str | None = None

    @property
    def success(self) -> bool:
        return self.rows_failed == 0


# ---------------------------------------------------------------------------
# LoadMetrics — load-level statistics
# ---------------------------------------------------------------------------

@dataclass
class LoadMetrics:
    """Aggregated metrics for one complete load operation."""

    total_rows_input:   int = 0
    rows_inserted:      int = 0
    rows_updated:       int = 0
    rows_skipped:       int = 0
    rows_failed:        int = 0
    batch_count:        int = 0
    total_duration_ms:  float = 0.0
    avg_batch_ms:       float = 0.0
    throughput_rows_sec: float = 0.0
    strategy_used:      str = ""
    target_table:       str = ""

    @property
    def rows_loaded(self) -> int:
        return self.rows_inserted + self.rows_updated

    def compute_derived(self) -> None:
        if self.batch_count > 0:
            self.avg_batch_ms = round(self.total_duration_ms / self.batch_count, 2)
        if self.total_duration_ms > 0:
            self.throughput_rows_sec = round(
                self.rows_loaded / (self.total_duration_ms / 1000), 2
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows_input":   self.total_rows_input,
            "rows_inserted":      self.rows_inserted,
            "rows_updated":       self.rows_updated,
            "rows_skipped":       self.rows_skipped,
            "rows_failed":        self.rows_failed,
            "rows_loaded":        self.rows_loaded,
            "batch_count":        self.batch_count,
            "total_duration_ms":  round(self.total_duration_ms, 2),
            "avg_batch_ms":       self.avg_batch_ms,
            "throughput_rows_sec": self.throughput_rows_sec,
            "strategy_used":      self.strategy_used,
            "target_table":       self.target_table,
        }


# ---------------------------------------------------------------------------
# LoadReport — full audit trail
# ---------------------------------------------------------------------------

@dataclass
class LoadReport:
    """Complete audit record for one warehouse load operation."""

    report_id:       str = field(default_factory=lambda: str(uuid.uuid4()))
    pipeline_run_id: str | None = None
    dataset_type:    str = ""
    target_table:    str = ""
    strategy_used:   str = ""
    loaded_at:       datetime = field(default_factory=datetime.utcnow)
    duration_seconds: float = 0.0
    metrics:         LoadMetrics = field(default_factory=LoadMetrics)
    batch_results:   list[LoadBatchResult] = field(default_factory=list)
    success:         bool = False
    error_message:   str | None = None
    idempotency_key: str | None = None   # pipeline_run_id used for dedup

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "report_id":       self.report_id,
            "pipeline_run_id": self.pipeline_run_id,
            "dataset_type":    self.dataset_type,
            "target_table":    self.target_table,
            "strategy_used":   self.strategy_used,
            "loaded_at":       self.loaded_at.isoformat(),
            "duration_seconds": round(self.duration_seconds, 3),
            "success":         self.success,
            "error_message":   self.error_message,
            "metrics":         self.metrics.to_dict(),
        }


# ---------------------------------------------------------------------------
# LoadResult — top-level output (returned to pipeline engine)
# ---------------------------------------------------------------------------

@dataclass
class LoadResult:
    """
    Top-level output of the Warehouse Loader.

    Returned by WarehouseLoader.load() to the pipeline engine which uses it to:
    - Update pipeline_runs.loaded_records
    - Determine whether to mark the pipeline COMPLETED or FAILED
    - Persist the load report to the audit trail

    Phase 9 contract (called by StageExecutor.run_load()):
        loader = WarehouseLoader(session=db)
        result = loader.load(transformed_df, dataset_type, pipeline_run_id)

    Note: rows_loaded is a computed property (rows_inserted + rows_updated).
    Do NOT pass rows_loaded as a constructor argument.
    """

    success:          bool
    dataset_type:     str
    rows_inserted:    int = 0
    rows_updated:     int = 0
    rows_skipped:     int = 0
    rows_failed:      int = 0
    target_table:     str = ""
    strategy_used:    str = ""
    report:           LoadReport = field(default_factory=LoadReport)
    error_message:    str | None = None
    error_code:       str | None = None
    duration_seconds: float = 0.0
    idempotent_skip:  bool = False    # True = run was already loaded (idempotency)

    @property
    def rows_loaded(self) -> int:
        """Total rows written = inserted + updated."""
        return self.rows_inserted + self.rows_updated

    def __repr__(self) -> str:
        return (
            f"LoadResult(success={self.success}, "
            f"dataset={self.dataset_type!r}, "
            f"loaded={self.rows_loaded}, "
            f"inserted={self.rows_inserted}, "
            f"updated={self.rows_updated}, "
            f"failed={self.rows_failed})"
        )
