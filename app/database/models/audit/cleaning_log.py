"""
CleaningLog ORM model.

Records every individual cleaning transformation applied during the Cleaning stage.
"""

import uuid

from sqlalchemy import CheckConstraint, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDMixin


class CleaningLog(UUIDMixin, TimestampMixin, Base):
    """Per-record, per-field cleaning action log."""

    __tablename__ = "cleaning_logs"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ("
            "'duplicate_removed','null_filled','null_dropped','null_flagged',"
            "'string_trimmed','case_normalized','date_standardized',"
            "'numeric_cleaned','regex_applied'"
            ")",
            name="ck_cleaning_logs_action_type",
        ),
        Index("ix_cleaning_logs_run_id", "pipeline_run_id"),
        Index("ix_cleaning_logs_action_type", "action_type"),
        {"comment": "Per-record cleaning transformation audit log"},
    )

    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="The pipeline run this cleaning action was part of",
    )
    row_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="0-based row index in the source file",
    )
    dataset_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Dataset type",
    )
    action_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type of cleaning applied",
    )
    field_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Name of the field that was cleaned",
    )
    original_value: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="Value before cleaning",
    )
    cleaned_value: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="Value after cleaning",
    )

    def __repr__(self) -> str:
        return (
            f"CleaningLog(run_id={self.pipeline_run_id}, "
            f"row={self.row_index}, action={self.action_type!r}, "
            f"field={self.field_name!r})"
        )
