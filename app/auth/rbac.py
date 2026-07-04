"""
RBAC (Role-Based Access Control) — seed data and permission registry.

Built-in roles and their permissions are defined here as constants.
On startup / migration, these are seeded into the database.

Permission naming: resource:action
  resource: pipelines, users, roles, api_keys, data, quality, admin
  action:   read, write, run, cancel, delete, create, revoke, rotate

Role hierarchy (most to least privileged):
  administrator > data_engineer > operator > analyst > viewer
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Permission constants — single source of truth
# ---------------------------------------------------------------------------


class Perm:
    """All permission strings defined as class attributes."""

    # Pipelines
    PIPELINES_READ   = "pipelines:read"
    PIPELINES_RUN    = "pipelines:run"
    PIPELINES_CANCEL = "pipelines:cancel"

    # Data (ingest, quality, transform results)
    DATA_READ  = "data:read"
    DATA_WRITE = "data:write"

    # Quality reports
    QUALITY_READ = "quality:read"

    # Users
    USERS_READ   = "users:read"
    USERS_WRITE  = "users:write"
    USERS_DELETE = "users:delete"

    # Roles
    ROLES_READ  = "roles:read"
    ROLES_WRITE = "roles:write"

    # API Keys
    API_KEYS_CREATE = "api_keys:create"
    API_KEYS_REVOKE = "api_keys:revoke"
    API_KEYS_ROTATE = "api_keys:rotate"
    API_KEYS_READ   = "api_keys:read"

    # Admin
    ADMIN_ALL = "admin:all"


@dataclass
class PermissionDef:
    name: str
    resource: str
    action: str
    description: str


@dataclass
class RoleDef:
    name: str
    display_name: str
    description: str
    permissions: list[str] = field(default_factory=list)
    is_system_role: bool = True


# ---------------------------------------------------------------------------
# All permissions
# ---------------------------------------------------------------------------

ALL_PERMISSIONS: list[PermissionDef] = [
    PermissionDef(Perm.PIPELINES_READ,   "pipelines", "read",   "View pipeline runs and history"),
    PermissionDef(Perm.PIPELINES_RUN,    "pipelines", "run",    "Trigger new pipeline runs"),
    PermissionDef(Perm.PIPELINES_CANCEL, "pipelines", "cancel", "Cancel running pipelines"),
    PermissionDef(Perm.DATA_READ,        "data",      "read",   "Read data and reports"),
    PermissionDef(Perm.DATA_WRITE,       "data",      "write",  "Write / ingest data"),
    PermissionDef(Perm.QUALITY_READ,     "quality",   "read",   "Read quality reports"),
    PermissionDef(Perm.USERS_READ,       "users",     "read",   "View user accounts"),
    PermissionDef(Perm.USERS_WRITE,      "users",     "write",  "Create and update users"),
    PermissionDef(Perm.USERS_DELETE,     "users",     "delete", "Delete user accounts"),
    PermissionDef(Perm.ROLES_READ,       "roles",     "read",   "View roles and permissions"),
    PermissionDef(Perm.ROLES_WRITE,      "roles",     "write",  "Manage roles and assignments"),
    PermissionDef(Perm.API_KEYS_CREATE,  "api_keys",  "create", "Create new API keys"),
    PermissionDef(Perm.API_KEYS_REVOKE,  "api_keys",  "revoke", "Revoke API keys"),
    PermissionDef(Perm.API_KEYS_ROTATE,  "api_keys",  "rotate", "Rotate API keys"),
    PermissionDef(Perm.API_KEYS_READ,    "api_keys",  "read",   "View own API keys"),
    PermissionDef(Perm.ADMIN_ALL,        "admin",     "all",    "Full administrative access"),
]


# ---------------------------------------------------------------------------
# Built-in roles
# ---------------------------------------------------------------------------

BUILT_IN_ROLES: list[RoleDef] = [
    RoleDef(
        name="administrator",
        display_name="Administrator",
        description="Full platform access — all operations on all resources.",
        permissions=[p.name for p in ALL_PERMISSIONS],
    ),
    RoleDef(
        name="data_engineer",
        display_name="Data Engineer",
        description="Run pipelines, manage data, create API keys.",
        permissions=[
            Perm.PIPELINES_READ, Perm.PIPELINES_RUN, Perm.PIPELINES_CANCEL,
            Perm.DATA_READ, Perm.DATA_WRITE,
            Perm.QUALITY_READ,
            Perm.API_KEYS_CREATE, Perm.API_KEYS_READ, Perm.API_KEYS_REVOKE, Perm.API_KEYS_ROTATE,
        ],
    ),
    RoleDef(
        name="operator",
        display_name="Operator",
        description="Trigger and cancel pipelines, read data.",
        permissions=[
            Perm.PIPELINES_READ, Perm.PIPELINES_RUN, Perm.PIPELINES_CANCEL,
            Perm.DATA_READ,
            Perm.QUALITY_READ,
        ],
    ),
    RoleDef(
        name="analyst",
        display_name="Analyst",
        description="Read-only access to data and quality reports.",
        permissions=[
            Perm.PIPELINES_READ,
            Perm.DATA_READ,
            Perm.QUALITY_READ,
        ],
    ),
    RoleDef(
        name="viewer",
        display_name="Viewer",
        description="Read-only access to pipelines and data.",
        permissions=[
            Perm.PIPELINES_READ,
            Perm.DATA_READ,
        ],
    ),
]


# ---------------------------------------------------------------------------
# Scope → permissions mapping (for API keys)
# ---------------------------------------------------------------------------

API_KEY_SCOPE_PERMISSIONS: dict[str, list[str]] = {
    "admin": [p.name for p in ALL_PERMISSIONS],
    "pipeline": [
        Perm.PIPELINES_READ, Perm.PIPELINES_RUN, Perm.PIPELINES_CANCEL,
        Perm.DATA_READ, Perm.DATA_WRITE,
        Perm.QUALITY_READ,
    ],
    "readonly": [
        Perm.PIPELINES_READ,
        Perm.DATA_READ,
        Perm.QUALITY_READ,
    ],
}


def get_api_key_permissions(scope: str) -> set[str]:
    """Return the permission set for a given API key scope."""
    return set(API_KEY_SCOPE_PERMISSIONS.get(scope, API_KEY_SCOPE_PERMISSIONS["readonly"]))


# ---------------------------------------------------------------------------
# Seeding helper
# ---------------------------------------------------------------------------

def seed_roles_and_permissions(session) -> None:
    """
    Seed all built-in roles and permissions into the database.

    Idempotent — safe to call multiple times (uses get-or-create).
    Called at application startup or via a management script.
    """
    from sqlalchemy import select
    from app.database.models.auth.permission import Permission
    from app.database.models.auth.role import Role
    from app.logging.logger import get_logger as _get_logger

    log = _get_logger(__name__)

    # 1. Create / update all permissions
    perm_map: dict[str, Permission] = {}
    for pdef in ALL_PERMISSIONS:
        existing = session.execute(
            select(Permission).where(Permission.name == pdef.name)
        ).scalar_one_or_none()
        if existing is None:
            existing = Permission(
                name=pdef.name,
                resource=pdef.resource,
                action=pdef.action,
                description=pdef.description,
            )
            session.add(existing)
            session.flush()
            log.info(f"Created permission: {pdef.name}")
        perm_map[pdef.name] = existing

    # 2. Create / update all roles
    for rdef in BUILT_IN_ROLES:
        role = session.execute(
            select(Role).where(Role.name == rdef.name)
        ).scalar_one_or_none()
        if role is None:
            role = Role(
                name=rdef.name,
                display_name=rdef.display_name,
                description=rdef.description,
                is_system_role=rdef.is_system_role,
            )
            session.add(role)
            session.flush()
            log.info(f"Created role: {rdef.name}")

        # Sync permissions
        desired = {perm_map[p] for p in rdef.permissions if p in perm_map}
        current = set(role.permissions)
        to_add = desired - current
        for p in to_add:
            role.permissions.append(p)
        if to_add:
            session.flush()

    log.info("RBAC seed complete")
