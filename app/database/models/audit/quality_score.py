"""
DataQualityScore ORM model.

Stores the aggregated data quality score per pipeline run per dataset.
This table is the source for quality trend charts in the dashboard and
enables threshold-based alerting.

Design decisions:
- One row per pipeline run (unique on pipeline_run_id)
- All counts are stored explicitly (not computed from validation_failures)
  to ensure the score can be retrieved without re-aggregating millions of rows
- threshold_breached boolean allows a simple indexed query for alerting
- A separate row per dataset type ensures multi-dataset runs have independent scores
"""

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDMixin


class DataQualityScore(UUIDMixin, TimestampMixin, Base):
    """
    Aggregated data quality score for a pipeline run.

    One record per pipeline run, summarizing validation and loading outcomes
    into a single quality metric for trending and alerting.
    """

    __tablename__ = "data_quality_scores"
    __table_args__ = (
        UniqueConstraint("pipeline_run_id", name="uq_quality_scores_run_id"),
        CheckConstraint(
            "quality_score >= 0 AND quality_score <= 100",
            name="ck_quality_scores_range",
        ),
        CheckConstraint(
            "total_records >= 0",
            name="ck_quality_scores_total_non_negative",
        ),
        CheckConstraint(
            "dataset_type IN ('orders','customers','products','inventory','suppliers','payments')",
            name="ck_quality_scores_dataset_type",
        ),
        # Index for trend queries: quality over time per dataset
        Index("ix_quality_scores_dataset_created", "dataset_type", "created_at"),
        # Index for alerting: find runs below threshold
        Index(
            "ix_quality_scores_threshold_breached",
            "threshold_breached",
            postgresql_where="threshold_breached = true",
        ),
        {"comment": "Aggregated data quality scores per pipeline run"},
    )

    # ------------------------------------------------------------------
    # Parent run
    # ------------------------------------------------------------------
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="The pipeline run this score belongs to",
    )
    dataset_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Dataset type that was processed",
    )

    # ------------------------------------------------------------------
    # Record counts (source for score calculation)
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
        comment="Records that passed all validation rules",
    )
    invalid_records: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Records rejected by validation",
    )
    warning_records: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Records that passed with warnings",
    )
    duplicate_records: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Duplicate records removed during cleaning",
    )
    loaded_records: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Records successfully written to the database",
    )

    # ------------------------------------------------------------------
    # Quality score
    # ------------------------------------------------------------------
    quality_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Quality score: (valid_records / total_records) × 100",
    )
    warning_threshold: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        server_default="80.00",
        comment="Threshold below which a WARNING alert is triggered",
    )
    failure_threshold: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        server_default="50.00",
        comment="Threshold below which a FAILURE alert is triggered",
    )
    threshold_breached: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="True when quality_score < failure_threshold",
    )
    threshold_warning: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="True when quality_score < warning_threshold",
    )

    def __repr__(self) -> str:
        return (
            f"DataQualityScore(run_id={self.pipeline_run_id}, "
            f"dataset={self.dataset_type!r}, score={self.quality_score})"
        )
