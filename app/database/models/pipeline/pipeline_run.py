"""
PipelineRun ORM model.

The central tracking record for every ETL pipeline execution. Every time
a file is processed through the ETL system, one PipelineRun record is
created. It is the parent for all StageResult and IngestionEvent records
for that execution.

Design decisions:
- run_id is the UUID PK (from UUIDMixin) — also exposed as a human-readable
  run_number (YYYYMMDD-NNNN sequence) for operations team reference
- status uses a CHECK constraint matching the PipelineStatus enum exactly
- duration_seconds stored separately from timestamps to avoid timezone confusion
  in reporting queries
- metrics stored as JSONB for flexibility — different dataset types produce
  different counts, and we don't want 20 sparse nullable integer columns
- triggered_by distinguishes manual API triggers from scheduled runs
- execution_host supports future distributed execution monitoring
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class PipelineRun(UUIDMixin, TimestampMixin, Base):
    """
    Pipeline execution run record.

    Created once per file processing cycle. Tracks lifecycle from trigger
    through all ETL stages to completion or failure.
    """

    __tablename__ = "pipeline_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','failed','partial','cancelled')",
            name="ck_pipeline_runs_status",
        ),
        CheckConstraint(
            "dataset_type IN ('orders','customers','products','inventory','suppliers','payments')",
            name="ck_pipeline_runs_dataset_type",
        ),
        # Most common query pattern: runs by dataset type and date
        Index("ix_pipeline_runs_dataset_status", "dataset_type", "status"),
        Index("ix_pipeline_runs_started_at", "started_at"),
        Index("ix_pipeline_runs_status_started", "status", "started_at"),
        {"comment": "Pipeline execution history — one row per ETL run"},
    )

    # ------------------------------------------------------------------
    # Run identification
    # ------------------------------------------------------------------
    run_number: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
        comment="Human-readable run reference (e.g., 20250115-0042)",
    )
    pipeline_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Name of the pipeline (matches dataset_type for standard pipelines)",
    )
    dataset_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Dataset type: orders, customers, products, inventory, suppliers, payments",
    )

    # ------------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------------
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when execution began",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when execution finished (success or failure)",
    )
    duration_seconds: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 3),
        nullable=True,
        comment="Total wall-clock duration in seconds",
    )

    # ------------------------------------------------------------------
    # Status and outcome
    # ------------------------------------------------------------------
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending",
        index=True,
        comment="Run lifecycle status",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Top-level error message if the run failed",
    )
    error_stage: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Pipeline stage where the failure occurred",
    )

    # ------------------------------------------------------------------
    # Record counts (denormalized from stage results for fast dashboard queries)
    # ------------------------------------------------------------------
    total_records: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Total records in the source file",
    )
    valid_records: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Records that passed validation",
    )
    invalid_records: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Records rejected during validation",
    )
    cleaned_records: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Records that passed cleaning",
    )
    loaded_records: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Records successfully written to the database",
    )
    failed_records: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Records that failed at any stage",
    )
    warning_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Total non-fatal warnings across all stages",
    )

    # ------------------------------------------------------------------
    # Quality score
    # ------------------------------------------------------------------
    quality_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Data quality score 0.00–100.00 (valid_records / total_records × 100)",
    )

    # ------------------------------------------------------------------
    # Execution context
    # ------------------------------------------------------------------
    triggered_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        server_default="system",
        comment="Who/what triggered this run: api_key, scheduler, manual, system",
    )
    trigger_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="manual",
        comment="Trigger mechanism: manual, scheduled, api, directory_watch",
    )
    execution_host: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Hostname of the worker that executed this run",
    )

    # ------------------------------------------------------------------
    # Extended metrics (JSONB — flexible, avoids sparse nullable columns)
    # ------------------------------------------------------------------
    metrics: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Stage-level metrics as JSON: {stage: {records, duration_ms, ...}}",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    ingestion_events: Mapped[list["IngestionEvent"]] = relationship(  # type: ignore[name-defined]
        "IngestionEvent",
        back_populates="pipeline_run",
        lazy="select",
        cascade="save-update, merge",
    )
    stage_results: Mapped[list["StageResult"]] = relationship(  # type: ignore[name-defined]
        "StageResult",
        back_populates="pipeline_run",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="StageResult.stage_order",
    )

    def __repr__(self) -> str:
        return (
            f"PipelineRun(id={self.id}, run_number={self.run_number!r}, "
            f"dataset={self.dataset_type!r}, status={self.status!r})"
        )
