"""
User management router.

GET    /api/v1/users               — list users (users:read)
POST   /api/v1/users               — create user (users:write)
GET    /api/v1/users/{user_id}     — get user (users:read or self)
PUT    /api/v1/users/{user_id}     — update user (users:write)
DELETE /api/v1/users/{user_id}     — soft-delete user (users:delete)
POST   /api/v1/users/{user_id}/roles  — assign role (roles:write)
DELETE /api/v1/users/{user_id}/roles/{role_name} — revoke role (roles:write)
POST   /api/v1/users/{user_id}/unlock — unlock locked account (users:write)
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.dependencies import DbSession, CurrentUser, require_permission
from app.api.schemas.auth_schemas import (
    AssignRoleRequest,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.api.schemas.base_schemas import APIResponse, PaginatedResponse
from app.auth.rbac import Perm
from app.logging.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["User Management"])


@router.get("", response_model=PaginatedResponse[UserListResponse], summary="List all users")
def list_users(
    db: DbSession,
    page: int = 1,
    page_size: int = 20,
    is_active: bool | None = None,
    current_user: dict = Depends(require_permission(Perm.USERS_READ)),
) -> PaginatedResponse[UserListResponse]:
    from app.auth.user_service import UserService
    svc = UserService(db)
    users, total = svc.list_users(
        offset=(page - 1) * page_size, limit=page_size, is_active=is_active,
    )
    return PaginatedResponse[UserListResponse].ok(
        data=[UserListResponse(
            id=u.id, username=u.username, email=u.email,
            is_active=u.is_active, roles=u.role_names, last_login_at=u.last_login_at,
        ) for u in users],
        total_items=total, page=page, page_size=page_size,
    )


@router.post("", response_model=APIResponse[UserResponse], status_code=201, summary="Create a new user")
def create_user(
    payload: UserCreateRequest,
    db: DbSession,
    current_user: dict = Depends(require_permission(Perm.USERS_WRITE)),
) -> APIResponse[UserResponse]:
    from app.auth.user_service import UserService
    svc = UserService(db)
    user = svc.create_user(
        username=payload.username, email=payload.email, password=payload.password,
        full_name=payload.full_name, role_names=payload.role_names,
    )
    return APIResponse[UserResponse].ok(data=UserResponse.from_user(user))


@router.get("/{user_id}", response_model=APIResponse[UserResponse], summary="Get user by ID")
def get_user(
    user_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> APIResponse[UserResponse]:
    from app.auth.user_service import UserService
    from app.core.exceptions import AuthorizationException

    is_self = current_user["user_id"] == str(user_id)
    has_perm = Perm.USERS_READ in current_user.get("permissions", set())
    if not is_self and not has_perm:
        raise AuthorizationException(
            message="You may only view your own profile or require users:read permission.",
            error_code="INSUFFICIENT_PERMISSION",
        )
    svc = UserService(db)
    user = svc.get_user_by_id(user_id)
    return APIResponse[UserResponse].ok(data=UserResponse.from_user(user))


@router.put("/{user_id}", response_model=APIResponse[UserResponse], summary="Update user profile")
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    db: DbSession,
    current_user: dict = Depends(require_permission(Perm.USERS_WRITE)),
) -> APIResponse[UserResponse]:
    from app.auth.user_service import UserService
    svc = UserService(db)
    user = svc.update_user(
        user_id=user_id, full_name=payload.full_name,
        email=payload.email, is_active=payload.is_active,
    )
    return APIResponse[UserResponse].ok(data=UserResponse.from_user(user))


@router.delete("/{user_id}", response_model=APIResponse[dict], summary="Soft-delete a user")
def delete_user(
    user_id: uuid.UUID,
    db: DbSession,
    current_user: dict = Depends(require_permission(Perm.USERS_DELETE)),
) -> APIResponse[dict]:
    from app.auth.user_service import UserService
    svc = UserService(db)
    svc.delete_user(user_id)
    return APIResponse[dict].ok(data={"deleted": True, "user_id": str(user_id)})


@router.post("/{user_id}/roles", response_model=APIResponse[UserResponse], summary="Assign a role to a user")
def assign_role(
    user_id: uuid.UUID,
    payload: AssignRoleRequest,
    db: DbSession,
    current_user: dict = Depends(require_permission(Perm.ROLES_WRITE)),
) -> APIResponse[UserResponse]:
    from app.auth.user_service import UserService
    svc = UserService(db)
    user = svc.assign_role(user_id, payload.role_name)
    return APIResponse[UserResponse].ok(data=UserResponse.from_user(user))


@router.delete("/{user_id}/roles/{role_name}", response_model=APIResponse[UserResponse], summary="Revoke a role from a user")
def revoke_role(
    user_id: uuid.UUID,
    role_name: str,
    db: DbSession,
    current_user: dict = Depends(require_permission(Perm.ROLES_WRITE)),
) -> APIResponse[UserResponse]:
    from app.auth.user_service import UserService
    svc = UserService(db)
    user = svc.revoke_role(user_id, role_name)
    return APIResponse[UserResponse].ok(data=UserResponse.from_user(user))


@router.post("/{user_id}/unlock", response_model=APIResponse[UserResponse], summary="Unlock a locked user account")
def unlock_user(
    user_id: uuid.UUID,
    db: DbSession,
    current_user: dict = Depends(require_permission(Perm.USERS_WRITE)),
) -> APIResponse[UserResponse]:
    from app.auth.user_service import UserService
    svc = UserService(db)
    user = svc.unlock_user(user_id)
    return APIResponse[UserResponse].ok(data=UserResponse.from_user(user))
