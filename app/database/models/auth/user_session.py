"""
UserSession ORM model.

Tracks active JWT refresh token sessions. When a user logs out or a
refresh token is used, the session is revoked (is_active=False).

This enables:
- Forced logout of all sessions (revoke all for user_id)
- Refresh token rotation (one-time use)
- Session audit trail
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class UserSession(UUIDMixin, TimestampMixin, Base):
    """
    Active user session tied to a refresh token.

    One session per login. Revoked on logout or refresh token use.
    """

    __tablename__ = "user_sessions"
    __table_args__ = {"comment": "Active user sessions for refresh token tracking"}

    # ------------------------------------------------------------------
    # Ownership
    # ------------------------------------------------------------------
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment="User this session belongs to",
    )

    # ------------------------------------------------------------------
    # Token tracking
    # ------------------------------------------------------------------
    refresh_token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="SHA-256 hash of the refresh token",
    )
    access_token_jti: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
        comment="JTI (JWT ID) of the last access token issued in this session",
    )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default="true",
        comment="False = session has been revoked",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Refresh token expiry — session is invalid after this",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when the session was explicitly revoked",
    )

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="IP address at login time",
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Browser / client user-agent at login time",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User",
        back_populates="sessions",
    )

    def is_valid(self) -> bool:
        """Return True if session is active and not expired."""
        from datetime import timezone as _tz
        if not self.is_active:
            return False
        exp = self.expires_at
        now = datetime.now(tz=_tz.utc)
        # Handle both naive (SQLite) and aware (PostgreSQL) datetimes
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=_tz.utc)
        return now < exp

    def __repr__(self) -> str:
        return f"UserSession(user_id={self.user_id}, active={self.is_active})"
