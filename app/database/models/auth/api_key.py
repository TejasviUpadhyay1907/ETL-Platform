"""
APIKey ORM model.

API keys provide programmatic access without user credentials.
Keys are stored as SHA-256 hashes — the plaintext key is only shown once
at creation time and never stored.

Key scopes: admin, pipeline, readonly
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class APIKey(UUIDMixin, TimestampMixin, Base):
    """
    Hashed API key for programmatic platform access.

    Lifecycle: created → active → revoked (soft delete)
    The raw key is returned once at creation; only the hash is stored.
    """

    __tablename__ = "api_keys"
    __table_args__ = {"comment": "Hashed API keys for programmatic access"}

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable key name, e.g. 'CI/CD Pipeline Key'",
    )
    key_prefix: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        index=True,
        comment="First 8 chars of the raw key for identification (safe to display)",
    )
    key_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="SHA-256 hash of the raw API key",
    )

    # ------------------------------------------------------------------
    # Ownership
    # ------------------------------------------------------------------
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment="User who owns this API key",
    )

    # ------------------------------------------------------------------
    # Scope / permissions
    # ------------------------------------------------------------------
    scope: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="readonly",
        server_default="readonly",
        comment="Key scope: admin | pipeline | readonly",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional description of this key's purpose",
    )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default="true",
        comment="False = key has been revoked",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Optional expiry timestamp — None means never expires",
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Most recent successful use of this key",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when the key was revoked",
    )

    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------
    request_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        server_default="0",
        comment="Total number of authenticated requests made with this key",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User",
        back_populates="api_keys",
    )

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------
    def is_expired(self) -> bool:
        """Return True if the key has passed its expiry date."""
        if self.expires_at is None:
            return False
        from datetime import timezone
        return datetime.now(tz=timezone.utc) > self.expires_at

    def is_valid(self) -> bool:
        """Return True if the key can be used to authenticate."""
        return self.is_active and not self.is_expired()

    def __repr__(self) -> str:
        return f"APIKey(name={self.name!r}, prefix={self.key_prefix!r}, scope={self.scope!r})"
