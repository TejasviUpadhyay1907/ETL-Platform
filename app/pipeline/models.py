"""
Pipeline orchestration domain models.

These are pure Python dataclasses — NOT ORM models.
They carry data between orchestration components and form the complete
PipelineResult contract that Phase 9 (Warehouse Loader) will consume.

Design:
  PipelineStageResult — outcome of one stage execution
  PipelineMetrics     — run-level execution statistics
  PipelineEvent       — one event in the lifecycle log
  CheckpointData      — serializable run state for resume/retry
  RetryPolicy         — retry configuration for a pipeline
  PipelineResult      — top-level output of the orchestration engine

The PipelineResult is the direct input for the Warehouse Loader (Phase 9).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Pipeline state machine values
# ---------------------------------------------------------------------------

class PipelineState:
    CREATED   = "created"
    QUEUED    = "queued"
    RUNNING   = "running"
    SUCCEEDED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"
    RETRYING  = "retrying"
    PARTIAL   = "partial"

    # Valid transitions: {from_state: {allowed_to_states}}
    TRANSITIONS: dict[str, set[str]] = {
        "created":   {"queued", "cancelled"},
        "queued":    {"running", "cancelled"},
        "running":   {"completed", "failed", "partial", "cancelled", "retrying"},
        "retrying":  {"running", "failed", "cancelled"},
        "partial":   {"completed", "failed"},
        "completed": set(),   # terminal
        "failed":    {"retrying", "cancelled"},
        "cancelled": set(),   # terminal
    }

    @classmethod
    def is_valid_transition(cls, from_state: str, to_state: str) -> bool:
        return to_state in cls.TRANSITIONS.get(from_state, set())

    @classmethod
    def is_terminal(cls, state: str) -> bool:
        return state in {"completed", "failed", "cancelled"}


# ---------------------------------------------------------------------------
# Stage names
# ---------------------------------------------------------------------------

class StageName:
    INGESTION       = "ingestion"
    VALIDATION      = "validation"
    CLEANING        = "cleaning"
    TRANSFORMATION  = "transformation"
    LOAD            = "load"

    ALL = [INGESTION, VALIDATION, CLEANING, TRANSFORMATION, LOAD]
    ORDER = {name: i for i, name in enumerate(ALL)}


# ---------------------------------------------------------------------------
# PipelineStageResult — outcome of one stage
# ---------------------------------------------------------------------------

@dataclass
class PipelineStageResult:
    """Result of executing one pipeline stage."""

    stage_name:    str
    stage_order:   int
    status:        str       # success | warning | failed | skipped
    started_at:    datetime  = field(default_factory=datetime.utcnow)
    completed_at:  datetime | None = None
    duration_ms:   float = 0.0
    input_records: int = 0
    output_records: int = 0
    rejected_records: int = 0
    warning_count: int = 0
    quality_score: float | None = None
    error_message: str | None = None
    # The actual stage output object (IngestionResult, ValidationResult, etc.)
    stage_output:  Any = None
    details:       dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_name":      self.stage_name,
            "stage_order":     self.stage_order,
            "status":          self.status,
            "duration_ms":     round(self.duration_ms, 2),
            "input_records":   self.input_records,
            "output_records":  self.output_records,
            "rejected_records": self.rejected_records,
            "warning_count":   self.warning_count,
            "quality_score":   self.quality_score,
            "error_message":   self.error_message,
        }


# ---------------------------------------------------------------------------
# PipelineMetrics — run-level statistics
# ---------------------------------------------------------------------------

@dataclass
class PipelineMetrics:
    """Aggregated execution metrics for one pipeline run."""

    total_duration_seconds: float = 0.0
    stage_durations: dict[str, float] = field(default_factory=dict)   # stage → ms
    total_records_ingested: int = 0
    total_records_valid:    int = 0
    total_records_cleaned:  int = 0
    total_records_transformed: int = 0
    total_records_loaded:   int = 0
    total_records_rejected: int = 0
    retry_count:            int = 0
    warning_count:          int = 0
    quality_score:          float | None = None
    throughput_rows_per_sec: float = 0.0

    def compute_throughput(self) -> None:
        if self.total_duration_seconds > 0:
            self.throughput_rows_per_sec = round(
                self.total_records_ingested / self.total_duration_seconds, 2
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_duration_seconds":  round(self.total_duration_seconds, 3),
            "stage_durations":         self.stage_durations,
            "total_records_ingested":  self.total_records_ingested,
            "total_records_valid":     self.total_records_valid,
            "total_records_cleaned":   self.total_records_cleaned,
            "total_records_transformed": self.total_records_transformed,
            "total_records_loaded":    self.total_records_loaded,
            "total_records_rejected":  self.total_records_rejected,
            "retry_count":             self.retry_count,
            "warning_count":           self.warning_count,
            "quality_score":           self.quality_score,
            "throughput_rows_per_sec": self.throughput_rows_per_sec,
        }


# ---------------------------------------------------------------------------
# PipelineEvent — lifecycle event
# ---------------------------------------------------------------------------

@dataclass
class PipelineEvent:
    """One event in the pipeline execution lifecycle."""

    event_type:     str
    pipeline_run_id: str
    stage_name:     str | None = None
    message:        str = ""
    details:        dict[str, Any] = field(default_factory=dict)
    timestamp:      datetime = field(default_factory=datetime.utcnow)
    severity:       str = "INFO"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type":      self.event_type,
            "pipeline_run_id": self.pipeline_run_id,
            "stage_name":      self.stage_name,
            "message":         self.message,
            "timestamp":       self.timestamp.isoformat(),
            "severity":        self.severity,
        }


# ---------------------------------------------------------------------------
# CheckpointData — serializable run state for resume/retry
# ---------------------------------------------------------------------------

@dataclass
class CheckpointData:
    """Snapshot of pipeline state after each stage completion."""

    checkpoint_id:   str = field(default_factory=lambda: str(uuid.uuid4()))
    pipeline_run_id: str = ""
    pipeline_name:   str = ""
    dataset_type:    str = ""
    last_completed_stage: str | None = None
    last_completed_stage_order: int = -1
    completed_stages: list[str] = field(default_factory=list)
    stage_results:   list[dict[str, Any]] = field(default_factory=list)
    # Serialized last stage output (key data only — not full DataFrames)
    last_output_summary: dict[str, Any] = field(default_factory=dict)
    created_at:      datetime = field(default_factory=datetime.utcnow)
    retry_count:     int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id":              self.checkpoint_id,
            "pipeline_run_id":            self.pipeline_run_id,
            "pipeline_name":              self.pipeline_name,
            "dataset_type":               self.dataset_type,
            "last_completed_stage":       self.last_completed_stage,
            "last_completed_stage_order": self.last_completed_stage_order,
            "completed_stages":           self.completed_stages,
            "stage_results":              self.stage_results,
            "last_output_summary":        self.last_output_summary,
            "created_at":                 self.created_at.isoformat(),
            "retry_count":                self.retry_count,
        }


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------

@dataclass
class RetryPolicy:
    """Configurable retry policy for a pipeline run."""

    max_retries:        int = 3
    retry_delay_seconds: float = 5.0
    backoff_strategy:   str = "exponential"   # immediate | linear | exponential
    backoff_multiplier: float = 2.0
    max_delay_seconds:  float = 300.0
    retry_on_stages:    list[str] = field(default_factory=list)  # [] = all stages

    def get_delay(self, attempt: int) -> float:
        """Compute delay in seconds for the given retry attempt (0-indexed)."""
        if self.backoff_strategy == "immediate":
            return 0.0
        if self.backoff_strategy == "linear":
            delay = self.retry_delay_seconds * (attempt + 1)
        else:  # exponential
            delay = self.retry_delay_seconds * (self.backoff_multiplier ** attempt)
        return min(delay, self.max_delay_seconds)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RetryPolicy":
        return cls(
            max_retries=d.get("max_retries", 3),
            retry_delay_seconds=d.get("retry_delay_seconds", 5.0),
            backoff_strategy=d.get("backoff_strategy", "exponential"),
            backoff_multiplier=d.get("backoff_multiplier", 2.0),
            max_delay_seconds=d.get("max_delay_seconds", 300.0),
            retry_on_stages=d.get("retry_on_stages", []),
        )

    @classmethod
    def default(cls) -> "RetryPolicy":
        return cls()

    @classmethod
    def no_retry(cls) -> "RetryPolicy":
        return cls(max_retries=0)


# ---------------------------------------------------------------------------
# PipelineResult — top-level output (Phase 9 Warehouse Loader contract)
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """
    The top-level output of the Pipeline Orchestration Engine.

    This is the direct input for the Warehouse Loader (Phase 9).
    It contains:
    - The final analytics-ready DataFrame (transformed_df)
    - Complete execution history
    - All stage results with lineage references
    - Metrics and quality scores
    - Checkpoint reference for recovery

    Phase 9 usage:
        loader = WarehouseLoader(session=db)
        load_result = loader.load(pipeline_result)
    """

    # ── Identity ──────────────────────────────────────────────────────
    pipeline_run_id:  str
    pipeline_name:    str
    dataset_type:     str
    run_number:       str = ""

    # ── Status ────────────────────────────────────────────────────────
    status:           str = PipelineState.CREATED
    current_stage:    str | None = None
    completed_stages: list[str] = field(default_factory=list)
    failed_stage:     str | None = None
    retry_count:      int = 0

    # ── Final output (consumed by Phase 9) ────────────────────────────
    transformed_df:   pd.DataFrame = field(default_factory=pd.DataFrame)
    original_filename: str = ""
    ingestion_event_id: str | None = None

    # ── Detailed stage results ─────────────────────────────────────────
    stage_results:    list[PipelineStageResult] = field(default_factory=list)

    # ── Metrics ───────────────────────────────────────────────────────
    metrics:          PipelineMetrics = field(default_factory=PipelineMetrics)

    # ── Error information ─────────────────────────────────────────────
    success:          bool = False
    error_message:    str | None = None
    error_code:       str | None = None
    warnings:         list[str] = field(default_factory=list)
    errors:           list[str] = field(default_factory=list)

    # ── Timing ────────────────────────────────────────────────────────
    started_at:       datetime = field(default_factory=datetime.utcnow)
    completed_at:     datetime | None = None
    duration_seconds: float = 0.0

    # ── Checkpoint reference for resume/retry ─────────────────────────
    checkpoint_id:    str | None = None
    triggered_by:     str = "manual"
    trigger_type:     str = "manual"

    @property
    def record_count(self) -> int:
        return len(self.transformed_df)

    def get_stage_result(self, stage_name: str) -> PipelineStageResult | None:
        return next((s for s in self.stage_results if s.stage_name == stage_name), None)

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "pipeline_run_id":  self.pipeline_run_id,
            "pipeline_name":    self.pipeline_name,
            "dataset_type":     self.dataset_type,
            "run_number":       self.run_number,
            "status":           self.status,
            "success":          self.success,
            "current_stage":    self.current_stage,
            "completed_stages": self.completed_stages,
            "failed_stage":     self.failed_stage,
            "retry_count":      self.retry_count,
            "duration_seconds": round(self.duration_seconds, 3),
            "metrics":          self.metrics.to_dict(),
            "record_count":     self.record_count,
            "error_message":    self.error_message,
            "warnings":         self.warnings[:10],
            "errors":           self.errors[:10],
        }

    def __repr__(self) -> str:
        return (
            f"PipelineResult("
            f"run_id={self.pipeline_run_id[:8]}, "
            f"pipeline={self.pipeline_name!r}, "
            f"status={self.status!r}, "
            f"records={self.record_count})"
        )
