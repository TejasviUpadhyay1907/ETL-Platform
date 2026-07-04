"""
Role ORM model.

Roles aggregate Permissions and are assigned to Users.
Built-in roles: administrator, data_engineer, analyst, viewer, operator.

Design: Role → Permissions (many-to-many via role_permissions join table)
        User → Roles (many-to-many via user_roles join table)
"""
from __future__ import annotations

import uuid
from sqlalchemy import Column, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


# ---------------------------------------------------------------------------
# Join table: Role ↔ Permission
# ---------------------------------------------------------------------------
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True),
    Column(
        "permission_id",
        UUID(as_uuid=True),
        ForeignKey("permissions.id"),
        primary_key=True,
    ),
)


class Role(UUIDMixin, TimestampMixin, Base):
    """
    A named collection of permissions.

    Built-in roles and their typical scopes:
      administrator  — all permissions
      data_engineer  — pipelines:*, data:*, api_keys:create
      analyst        — data:read, pipelines:read, quality:read
      viewer         — *:read only
      operator       — pipelines:run, pipelines:cancel
    """

    __tablename__ = "roles"
    __table_args__ = {"comment": "User roles that aggregate permissions"}

    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="Unique role name, e.g. 'administrator'",
    )
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable role name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Description of the role's purpose and scope",
    )
    is_system_role: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        server_default="true",
        comment="True = built-in role that cannot be deleted",
    )

    # Many-to-many: Role → Permission
    permissions: Mapped[list["Permission"]] = relationship(  # type: ignore[name-defined]
        "Permission",
        secondary=role_permissions,
        back_populates="roles",
        lazy="selectin",
    )

    # Many-to-many back-reference from User
    users: Mapped[list["User"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        secondary="user_roles",
        back_populates="roles",
    )

    @property
    def permission_names(self) -> set[str]:
        """Return the set of permission name strings for this role."""
        return {p.name for p in self.permissions}

    def has_permission(self, permission_name: str) -> bool:
        """Check if this role grants a specific permission."""
        return permission_name in self.permission_names

    def __repr__(self) -> str:
        return f"Role(name={self.name!r})"
