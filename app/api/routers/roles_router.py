"""
Roles and permissions router.

GET /api/v1/roles                       — list all roles (roles:read)
GET /api/v1/roles/{role_name}           — get role details (roles:read)
GET /api/v1/permissions                 — list all permissions (roles:read)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import DbSession, require_permission
from app.api.schemas.auth_schemas import RoleResponse
from app.api.schemas.base_schemas import APIResponse
from app.auth.rbac import ALL_PERMISSIONS, Perm
from app.logging.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["Roles & Permissions"])


@router.get("/roles", response_model=APIResponse[list[RoleResponse]], summary="List all roles")
def list_roles(
    db: DbSession,
    current_user: dict = Depends(require_permission(Perm.ROLES_READ)),
) -> APIResponse[list[RoleResponse]]:
    from sqlalchemy import select
    from app.database.models.auth.role import Role

    roles = list(db.execute(select(Role).order_by(Role.name)).scalars().all())
    return APIResponse[list[RoleResponse]].ok(data=[RoleResponse.from_role(r) for r in roles])


@router.get("/roles/{role_name}", response_model=APIResponse[RoleResponse], summary="Get role details")
def get_role(
    role_name: str,
    db: DbSession,
    current_user: dict = Depends(require_permission(Perm.ROLES_READ)),
) -> APIResponse[RoleResponse]:
    from sqlalchemy import select
    from app.database.models.auth.role import Role
    from app.core.exceptions import NotFoundException

    role = db.execute(select(Role).where(Role.name == role_name)).scalar_one_or_none()
    if role is None:
        raise NotFoundException(message=f"Role '{role_name}' not found.")
    return APIResponse[RoleResponse].ok(data=RoleResponse.from_role(role))


@router.get("/permissions", response_model=APIResponse[list[dict]], summary="List all defined permissions")
def list_permissions(
    current_user: dict = Depends(require_permission(Perm.ROLES_READ)),
) -> APIResponse[list[dict]]:
    return APIResponse[list[dict]].ok(
        data=[{"name": p.name, "resource": p.resource, "action": p.action,
               "description": p.description} for p in ALL_PERMISSIONS]
    )
