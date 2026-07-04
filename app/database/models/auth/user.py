"""
User ORM model.

Platform users with role-based access control. Passwords are stored as
bcrypt hashes — plaintext is never persisted.

Status lifecycle: active → suspended → deleted (soft)
Account locking: failed_login_count >= max_failed_attempts → locked
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer,
    String, Table, Text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


# ---------------------------------------------------------------------------
# Join table: User ↔ Role
# ---------------------------------------------------------------------------
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True),
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True),
)


class User(UUIDMixin, TimestampMixin, Base):
    """
    Platform user account.

    Authentication: username/password with JWT tokens.
    Authorization: role-based via User → Role → Permission chain.
    """

    __tablename__ = "users"
    __table_args__ = {"comment": "Platform user accounts with RBAC"}

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    username: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="Unique username for login",
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="User email address",
    )
    full_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Display name",
    )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="bcrypt-hashed password — never store plaintext",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default="true",
        comment="Account is active and can log in",
    )
    is_locked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false",
        comment="Account locked due to too many failed login attempts",
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false",
        comment="Superuser bypasses all permission checks",
    )

    # ------------------------------------------------------------------
    # Login tracking
    # ------------------------------------------------------------------
    failed_login_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        server_default="0",
        comment="Consecutive failed login attempts",
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of most recent successful login",
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when the account was locked",
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last password change",
    )

    # ------------------------------------------------------------------
    # Soft delete
    # ------------------------------------------------------------------
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false",
        comment="Soft-deleted user — cannot log in",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    roles: Mapped[list["Role"]] = relationship(  # type: ignore[name-defined]
        "Role",
        secondary=user_roles,
        back_populates="users",
        lazy="selectin",
    )
    api_keys: Mapped[list["APIKey"]] = relationship(  # type: ignore[name-defined]
        "APIKey",
        back_populates="user",
        lazy="select",
    )
    sessions: Mapped[list["UserSession"]] = relationship(  # type: ignore[name-defined]
        "UserSession",
        back_populates="user",
        lazy="select",
    )

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def permission_names(self) -> set[str]:
        """Aggregate all permission names from all assigned roles."""
        perms: set[str] = set()
        for role in self.roles:
            perms |= role.permission_names
        return perms

    def has_permission(self, permission_name: str) -> bool:
        """Check if user has a specific permission (superusers always do)."""
        if self.is_superuser:
            return True
        return permission_name in self.permission_names

    def has_role(self, role_name: str) -> bool:
        """Check if the user has a specific role by name."""
        return any(r.name == role_name for r in self.roles)

    @property
    def role_names(self) -> list[str]:
        """List of role names assigned to this user."""
        return [r.name for r in self.roles]

    def can_login(self) -> bool:
        """Return True if the user is allowed to authenticate."""
        return self.is_active and not self.is_locked and not self.is_deleted

    def __repr__(self) -> str:
        return f"User(username={self.username!r}, email={self.email!r})"
