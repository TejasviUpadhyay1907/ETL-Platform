"""
StageResult ORM model.

Records the outcome of one pipeline stage within a pipeline run.
Each PipelineRun has up to six StageResults (one per ETL stage):
ingestion → validation → cleaning → transformation → loading → reporting.

Design decisions:
- stage_order INTEGER ensures results can be retrieved in execution order
  without relying on insertion timestamp ordering
- stage_name uses a CHECK constraint matching PipelineStage enum values
- status mirrors StageStatus enum: success, warning, failed, skipped
- input_records / output_records tracks the record count funnel through stages
- duration_ms stored as INTEGER milliseconds for sub-second precision
- details stored as JSONB for stage-specific structured output
  (e.g., validation failures count per rule, cleaning actions by type)
"""

import uuid
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


class StageResult(UUIDMixin, TimestampMixin, Base):
    """
    Pipeline stage execution result.

    One record per stage per pipeline run. Provides the granular breakdown
    used by the dashboard's record funnel visualization.
    """

    __tablename__ = "stage_results"
    __table_args__ = (
        CheckConstraint(
            "stage_name IN ('ingestion','validation','cleaning','transformation','loading','reporting')",
            name="ck_stage_results_stage_name",
        ),
        CheckConstraint(
            "status IN ('success','warning','failed','skipped')",
            name="ck_stage_results_status",
        ),
        CheckConstraint(
            "stage_order >= 0",
            name="ck_stage_results_order_non_negative",
        ),
        # Composite index for querying all stages of a specific run
        Index("ix_stage_results_run_order", "pipeline_run_id", "stage_order"),
        {"comment": "Per-stage execution results within a pipeline run"},
    )

    # ------------------------------------------------------------------
    # Parent run FK
    # ------------------------------------------------------------------
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "pipeline_runs.id",
            ondelete="CASCADE",
            name="fk_stage_results_pipeline_run",
        ),
        nullable=False,
        index=True,
        comment="Parent pipeline run",
    )

    # ------------------------------------------------------------------
    # Stage identity
    # ------------------------------------------------------------------
    stage_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Stage name: ingestion, validation, cleaning, transformation, loading, reporting",
    )
    stage_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Execution order (0=ingestion, 1=validation, 2=cleaning, …)",
    )

    # ------------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------------
    started_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when this stage began",
    )
    completed_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when this stage finished",
    )
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Stage wall-clock duration in milliseconds",
    )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="success",
        comment="Stage outcome: success, warning, failed, skipped",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if stage failed",
    )

    # ------------------------------------------------------------------
    # Record funnel counts
    # ------------------------------------------------------------------
    input_records: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Records received at the start of this stage",
    )
    output_records: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Records produced at the end of this stage (passed through)",
    )
    rejected_records: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Records rejected or dropped during this stage",
    )
    warning_records: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Records flagged with warnings (not rejected)",
    )

    # ------------------------------------------------------------------
    # Quality score for validation stage
    # ------------------------------------------------------------------
    quality_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Quality score for validation stage (0.00–100.00)",
    )

    # ------------------------------------------------------------------
    # Stage-specific details (JSONB)
    # ------------------------------------------------------------------
    details: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Stage-specific structured output (validation rule counts, cleaning actions, etc.)",
    )

    # ------------------------------------------------------------------
    # Relationship
    # ------------------------------------------------------------------
    pipeline_run: Mapped["PipelineRun"] = relationship(  # type: ignore[name-defined]
        "PipelineRun",
        back_populates="stage_results",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"StageResult(run_id={self.pipeline_run_id}, "
            f"stage={self.stage_name!r}, status={self.status!r}, "
            f"in={self.input_records}, out={self.output_records})"
        )
