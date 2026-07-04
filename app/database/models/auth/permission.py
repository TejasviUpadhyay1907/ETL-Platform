"""
Permission ORM model.

A permission is a named capability, e.g. "pipelines:run", "users:read".
Permissions are assigned to Roles, and Roles are assigned to Users.

Naming convention: resource:action (e.g. "pipelines:run", "users:write")
"""
from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class Permission(UUIDMixin, TimestampMixin, Base):
    """
    A granular permission that can be granted to a Role.

    Follows the resource:action naming pattern:
      pipelines:run, pipelines:read, pipelines:cancel
      users:read, users:write, users:delete
      api_keys:create, api_keys:revoke
      data:read, data:write
      admin:all
    """

    __tablename__ = "permissions"
    __table_args__ = {"comment": "Granular permissions assigned to roles"}

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="Permission identifier, e.g. 'pipelines:run'",
    )
    resource: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Resource this permission applies to, e.g. 'pipelines'",
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Action allowed, e.g. 'run', 'read', 'write', 'delete'",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable description of what this permission allows",
    )

    # Many-to-many back-reference from Role (populated by Role.permissions)
    roles: Mapped[list["Role"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Role",
        secondary="role_permissions",
        back_populates="permissions",
    )

    def __repr__(self) -> str:
        return f"Permission(name={self.name!r})"
