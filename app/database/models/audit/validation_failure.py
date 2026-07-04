"""
ValidationFailure ORM model.

Stores one record per validation rule failure per source row. When the
Validation Engine rejects a record, it writes one ValidationFailure row
for each rule that failed on that record.

Design decisions:
- row_index stores the 0-based source file row number for traceability
- rule_code matches the codes defined in the YAML rule config files
- severity mirrors RuleSeverity: error rejects the record; warning flags it
- original_value stores the raw field value that caused the failure
  (truncated to 1000 chars to avoid bloat from large text fields)
- field_name + rule_code together identify exactly what was wrong and where
- No FK to operational tables — validation failures reference the pipeline run
  and the ingestion event (the raw file), not the final stored record
"""

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDMixin


class ValidationFailure(UUIDMixin, TimestampMixin, Base):
    """
    Per-record, per-rule validation failure detail.

    Populated by the Validation Engine for every rule that fails on every row.
    Used to generate validation reports and identify recurring data quality issues.
    """

    __tablename__ = "validation_failures"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('error','warning','info')",
            name="ck_validation_failures_severity",
        ),
        # Query: failures grouped by rule code (most common in quality reports)
        Index("ix_validation_failures_rule_code", "rule_code"),
        # Composite: failures by run + rule for aggregation
        Index("ix_validation_failures_run_rule", "pipeline_run_id", "rule_code"),
        {"comment": "Per-record validation rule failure details"},
    )

    # ------------------------------------------------------------------
    # Parent run
    # ------------------------------------------------------------------
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="The pipeline run this failure occurred in",
    )
    ingestion_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="The ingestion event (source file) this failure came from",
    )

    # ------------------------------------------------------------------
    # Record identification
    # ------------------------------------------------------------------
    row_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="0-based row index in the source file",
    )
    dataset_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Dataset type the failure belongs to",
    )

    # ------------------------------------------------------------------
    # Failure details
    # ------------------------------------------------------------------
    rule_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Rule code that failed (e.g., ORD_001, CUST_002)",
    )
    rule_description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Human-readable description of the rule",
    )
    field_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Name of the field that failed the rule",
    )
    original_value: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="The raw field value that caused the failure (truncated to 1000 chars)",
    )
    failure_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Specific message describing why this record failed this rule",
    )
    severity: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default="error",
        comment="Rule severity: error (rejected), warning (flagged), info",
    )

    def __repr__(self) -> str:
        return (
            f"ValidationFailure(run_id={self.pipeline_run_id}, "
            f"row={self.row_index}, rule={self.rule_code!r})"
        )
