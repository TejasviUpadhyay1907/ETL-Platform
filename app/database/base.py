"""
SQLAlchemy declarative base and reusable ORM mixins.

All ORM models inherit from Base (for table creation and migration support)
and relevant mixins (for common fields like timestamps, UUIDs, soft delete).

Design Principle: Mixins follow the Single Responsibility Principle.
Each mixin adds exactly one orthogonal concern to a model.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    SQLAlchemy declarative base for all ORM models.

    All models must inherit from this class to be discovered by Alembic
    and included in schema migrations.
    """

    # Allow models to define type annotations on columns
    type_annotation_map: dict[Any, Any] = {}

    def to_dict(self) -> dict[str, Any]:
        """
        Convert model instance to a dictionary.

        Returns all column values as a plain dict, useful for serialization.
        Does NOT include relationships (to avoid N+1 queries).
        """
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns  # type: ignore[attr-defined]
        }

    def __repr__(self) -> str:
        """Generic repr showing model name and primary key."""
        pk_cols = [col.name for col in self.__table__.primary_key.columns]  # type: ignore[attr-defined]
        pk_values = {col: getattr(self, col) for col in pk_cols}
        return f"{self.__class__.__name__}({pk_values})"


class TimestampMixin:
    """
    Adds created_at and updated_at timestamp columns to a model.

    - created_at: Set automatically on INSERT, never changes.
    - updated_at: Set automatically on INSERT and UPDATE.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Record creation timestamp (UTC)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Record last update timestamp (UTC)",
    )


class UUIDMixin:
    """
    Adds a UUID primary key to a model.

    Uses PostgreSQL's native UUID type for efficient storage and indexing.
    Default is generated server-side to avoid round-trips for ID retrieval.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
        nullable=False,
        comment="Unique record identifier",
    )


class SoftDeleteMixin:
    """
    Adds soft delete capability to a model.

    Records are NEVER physically deleted. Instead, is_deleted is set to True
    and deleted_at records when. All queries should filter is_deleted=False.

    Used for audit trail preservation — deleted records remain in the database
    for compliance and troubleshooting.
    """

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false",
        index=True,  # Frequently filtered — always indexed
        comment="Soft delete flag — True means the record is deleted",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Timestamp when the record was soft-deleted",
    )

    def soft_delete(self) -> None:
        """Mark the record as soft-deleted."""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()

    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None


class AuditMixin(TimestampMixin):
    """
    Combines timestamp tracking with user attribution.

    Extends TimestampMixin to also track which user created and last modified a record.
    Used on business-critical models where user accountability matters.
    """

    created_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="User ID or system identifier that created this record",
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="User ID or system identifier that last updated this record",
    )
