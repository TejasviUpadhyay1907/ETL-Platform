"""
IngestionEvent ORM model.

Records every file ingestion event — the moment a raw file enters the system.
Each IngestionEvent is the root of a pipeline execution chain: one file arrives,
one IngestionEvent is created, one PipelineRun is spawned.

Design decisions:
- file_hash (SHA-256) enables idempotency detection: if the same file is
  uploaded twice, the system can detect and reject/skip it
- file_path stores the versioned path on the file system for archive retrieval
- row_count_raw vs row_count_after_header distinguishes blank/header lines
- rejection_reason is only populated when status='rejected'
- FK to pipeline_run is nullable: set after the run is created, not at ingestion time
"""

import uuid
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class IngestionEvent(UUIDMixin, TimestampMixin, Base):
    """
    File ingestion event record.

    Created the moment a raw file is received, before any processing begins.
    The audit anchor for the entire downstream pipeline execution.
    """

    __tablename__ = "ingestion_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('received','processing','processed','rejected','duplicate')",
            name="ck_ingestion_events_status",
        ),
        CheckConstraint(
            "dataset_type IN ('orders','customers','products','inventory','suppliers','payments')",
            name="ck_ingestion_events_dataset_type",
        ),
        CheckConstraint(
            "file_size_bytes > 0",
            name="ck_ingestion_events_file_size_positive",
        ),
        # Index for querying by dataset type and ingestion date
        Index("ix_ingestion_events_dataset_type", "dataset_type"),
        Index("ix_ingestion_events_status", "status"),
        Index("ix_ingestion_events_file_hash", "file_hash"),
        {"comment": "Raw file ingestion event log"},
    )

    # ------------------------------------------------------------------
    # File identification
    # ------------------------------------------------------------------
    original_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Original filename as uploaded by the user or detected from directory",
    )
    stored_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Filename as stored on the file system (may be renamed for uniqueness)",
    )
    file_path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Full file system path to the stored raw file",
    )
    file_extension: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="File extension (csv, xlsx, xls)",
    )

    # ------------------------------------------------------------------
    # File metrics
    # ------------------------------------------------------------------
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="File size in bytes",
    )
    file_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 hash of file contents for idempotency detection",
    )
    row_count_raw: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Total line count including header row",
    )
    row_count_data: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Data row count (excluding header)",
    )

    # ------------------------------------------------------------------
    # Dataset identification
    # ------------------------------------------------------------------
    dataset_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Detected dataset type",
    )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="received",
        comment="Processing status: received, processing, processed, rejected, duplicate",
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Reason for rejection (populated when status='rejected')",
    )

    # ------------------------------------------------------------------
    # Source tracking
    # ------------------------------------------------------------------
    source_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="upload",
        comment="How the file arrived: upload, directory_watch, api_push",
    )
    uploaded_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="User or API key that submitted the file",
    )
    source_ip: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Client IP address (IPv4 or IPv6)",
    )

    # ------------------------------------------------------------------
    # FK to pipeline run (set after run is created)
    # ------------------------------------------------------------------
    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "pipeline_runs.id",
            ondelete="SET NULL",
            name="fk_ingestion_events_pipeline_run",
        ),
        nullable=True,
        index=True,
        comment="Pipeline run spawned from this ingestion event",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    pipeline_run: Mapped["PipelineRun | None"] = relationship(  # type: ignore[name-defined]
        "PipelineRun",
        back_populates="ingestion_events",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"IngestionEvent(id={self.id}, file={self.original_filename!r}, "
            f"dataset={self.dataset_type!r}, status={self.status!r})"
        )
