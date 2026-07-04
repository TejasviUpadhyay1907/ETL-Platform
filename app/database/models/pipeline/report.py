"""
Report ORM model.

Stores metadata about every generated report file. The actual file lives
on the file system; this table stores its path, type, and attributes so the
API can list and serve downloads without reading the file system directly.

Design decisions:
- One row per generated file (a single run can produce multiple reports:
  quality + business summary, each in CSV and Excel = up to 4 records per run)
- file_path is the authoritative location — the API reads this to serve the file
- is_archived flag tracks when reports are moved to cold storage
"""

import uuid

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDMixin


class Report(UUIDMixin, TimestampMixin, Base):
    """
    Generated report file metadata record.

    One row per report file. References the pipeline run that produced it.
    """

    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(
            "report_type IN ('data_quality','business_summary')",
            name="ck_reports_type",
        ),
        CheckConstraint(
            "file_format IN ('csv','xlsx')",
            name="ck_reports_format",
        ),
        Index("ix_reports_pipeline_run_id", "pipeline_run_id"),
        Index("ix_reports_report_type", "report_type"),
        {"comment": "Generated report file metadata — one row per report file"},
    )

    # ------------------------------------------------------------------
    # Parent run (no FK — avoids cascade issues on run cleanup)
    # ------------------------------------------------------------------
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Pipeline run this report was generated for",
    )

    # ------------------------------------------------------------------
    # Report classification
    # ------------------------------------------------------------------
    report_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Report type: data_quality, business_summary",
    )
    file_format: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default="csv",
        comment="File format: csv, xlsx",
    )
    dataset_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Dataset type covered by this report (if applicable)",
    )

    # ------------------------------------------------------------------
    # File location
    # ------------------------------------------------------------------
    file_path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        comment="Full file system path to the report file",
    )
    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="File name used for the Content-Disposition download header",
    )
    file_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="File size in bytes",
    )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="True when the file has been moved to archive storage",
    )

    def __repr__(self) -> str:
        return (
            f"Report(id={self.id}, run_id={self.pipeline_run_id}, "
            f"type={self.report_type!r}, format={self.file_format!r})"
        )
