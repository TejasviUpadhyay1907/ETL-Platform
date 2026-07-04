"""
AuditLog ORM model.

The compliance and traceability backbone of the platform. Every significant
system event — pipeline start/stop, record loaded, file rejected, API access —
is written here with a consistent schema.

Design decisions:
- No soft-delete, no update — audit records are immutable (INSERT-only)
- event_type uses a CHECK constraint matching AuditEventType enum values
- entity_type + entity_id form a polymorphic reference: together they identify
  what object the event relates to without needing foreign keys to every table
- context_data as JSONB stores the event payload without a fixed schema —
  different event types carry different data
- Indexed on (event_type, created_at) for compliance period queries
- Indexed on (run_id, event_type) for per-run audit trail queries
- Partitioning strategy: this table should be RANGE partitioned by created_at
  in production (monthly partitions). Alembic migration includes the partition DDL.
"""

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDMixin


class AuditLog(UUIDMixin, TimestampMixin, Base):
    """
    Immutable audit event log.

    Never updated or deleted. Only INSERT operations are valid on this table.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ("
            "'PIPELINE_STARTED','PIPELINE_COMPLETED','PIPELINE_FAILED','PIPELINE_CANCELLED',"
            "'STAGE_STARTED','STAGE_COMPLETED','STAGE_FAILED',"
            "'FILE_INGESTED','FILE_REJECTED',"
            "'RECORD_LOADED','RECORD_REJECTED','VALIDATION_FAILURE','CLEANING_ACTION',"
            "'API_REQUEST','API_ERROR',"
            "'CONFIG_LOADED','SYSTEM_STARTUP','SYSTEM_SHUTDOWN'"
            ")",
            name="ck_audit_logs_event_type",
        ),
        # Primary compliance query: all events in a time window
        Index("ix_audit_logs_event_type_created", "event_type", "created_at"),
        # Per-run audit trail
        Index("ix_audit_logs_run_id_created", "run_id", "created_at"),
        # Entity lookup (e.g., all events for customer X)
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        # API access log queries by user
        Index("ix_audit_logs_user_created", "user_id", "created_at"),
        {"comment": "Immutable compliance and traceability event log"},
    )

    # ------------------------------------------------------------------
    # Event classification
    # ------------------------------------------------------------------
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Event category from the AuditEventType enum",
    )
    severity: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default="INFO",
        comment="Severity level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )

    # ------------------------------------------------------------------
    # Correlation identifiers
    # ------------------------------------------------------------------
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Pipeline run ID this event relates to (if applicable)",
    )
    stage: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Pipeline stage name (if event occurred within a stage)",
    )

    # ------------------------------------------------------------------
    # Actor
    # ------------------------------------------------------------------
    user_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="User or API key that triggered the event",
    )
    source_ip: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Client IP address for API events",
    )
    request_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="HTTP request ID for API-originated events",
    )

    # ------------------------------------------------------------------
    # Subject (what object does this event refer to?)
    # ------------------------------------------------------------------
    entity_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Type of the object this event relates to (e.g., 'order', 'customer')",
    )
    entity_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="ID of the object this event relates to",
    )

    # ------------------------------------------------------------------
    # Message and payload
    # ------------------------------------------------------------------
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Human-readable event description",
    )
    context_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Structured event payload as JSON — schema varies by event_type",
    )

    def __repr__(self) -> str:
        return (
            f"AuditLog(id={self.id}, event={self.event_type!r}, "
            f"run_id={self.run_id}, severity={self.severity!r})"
        )
