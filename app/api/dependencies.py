"""
Shared FastAPI dependencies.

Injected into endpoints via FastAPI's Depends() mechanism.
Centralizing here ensures consistency and simplifies testing.

Dependency hierarchy:

  get_db          → raw Session
  get_current_user → validates JWT (from request.state set by JWTAuthMiddleware)
                    OR validates X-API-Key against DB
  require_role    → get_current_user + role check
  require_permission → get_current_user + permission check
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.schemas.base_schemas import PaginationParams
from app.core.config import AppConfig, get_config
from app.core.exceptions import AuthenticationException, AuthorizationException
from app.database.engine import get_db_session
from app.logging.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Database session
# ---------------------------------------------------------------------------

def get_db() -> "Session":
    """
    FastAPI dependency providing a database session per request.

    Session is automatically closed after the response is sent.
    """
    yield from get_db_session()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def get_config_dep() -> AppConfig:
    """FastAPI dependency returning the application configuration."""
    return get_config()


# ---------------------------------------------------------------------------
# Current user — reads from request.state set by JWTAuthMiddleware
# ---------------------------------------------------------------------------

def get_current_user(request: Request, db: "Session" = Depends(get_db)) -> dict:
    """
    Extract and validate the authenticated principal from request.state.

    For JWT paths: JWTAuthMiddleware has already decoded the token and set
    request.state.user_id, .username, .roles.

    For API key paths: JWTAuthMiddleware sets request.state.pending_api_key;
    we validate it here where a DB session is available.

    Returns:
        Dict with user_id, username, roles, is_api_key, permissions.

    Raises:
        AuthenticationException: Not authenticated.
    """
    is_api_key = getattr(request.state, "is_api_key", False)
    pending_api_key = getattr(request.state, "pending_api_key", None)

    if is_api_key and pending_api_key:
        # Validate API key against DB
        from app.auth.api_key_manager import validate_api_key
        from app.auth.rbac import get_api_key_permissions
        api_key = validate_api_key(db, pending_api_key)
        permissions = get_api_key_permissions(api_key.scope)
        return {
            "user_id": str(api_key.user_id),
            "username": api_key.user.username if api_key.user else "api_key",
            "roles": [api_key.scope],
            "is_api_key": True,
            "permissions": permissions,
            "api_key_id": str(api_key.id),
            "api_key_scope": api_key.scope,
        }

    # JWT path — attributes set by JWTAuthMiddleware
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise AuthenticationException(
            message="Authentication required.",
            error_code="AUTHENTICATION_REQUIRED",
        )

    # Load full user permissions from DB (lazy — only if needed by require_permission)
    from sqlalchemy import select
    from app.database.models.auth.user import User as UserModel

    user = db.execute(
        select(UserModel).where(UserModel.id == uuid.UUID(user_id))
    ).scalar_one_or_none()

    permissions: set[str] = set()
    if user:
        permissions = user.permission_names
        if user.is_superuser:
            from app.auth.rbac import ALL_PERMISSIONS
            permissions = {p.name for p in ALL_PERMISSIONS}

    return {
        "user_id": user_id,
        "username": getattr(request.state, "username", ""),
        "roles": getattr(request.state, "roles", []),
        "is_api_key": False,
        "permissions": permissions,
    }


# ---------------------------------------------------------------------------
# Role guard
# ---------------------------------------------------------------------------

def require_role(*role_names: str):
    """
    Dependency factory: require that the current user has at least one of the given roles.

    Usage:
        @router.get("/admin")
        def admin_endpoint(
            user=Depends(require_role("administrator", "data_engineer"))
        ):
            ...
    """
    def _guard(current_user: dict = Depends(get_current_user)) -> dict:
        user_roles = set(current_user.get("roles", []))
        if not user_roles.intersection(role_names):
            raise AuthorizationException(
                message=f"Requires one of roles: {', '.join(role_names)}.",
                error_code="INSUFFICIENT_ROLE",
            )
        return current_user
    return _guard


# ---------------------------------------------------------------------------
# Permission guard
# ---------------------------------------------------------------------------

def require_permission(*permission_names: str):
    """
    Dependency factory: require that the current user has all of the given permissions.

    Superusers always pass. Checks JWT user permissions OR API key scope permissions.

    Usage:
        @router.post("/pipelines/run")
        def run_pipeline(
            user=Depends(require_permission("pipelines:run"))
        ):
            ...
    """
    def _guard(current_user: dict = Depends(get_current_user)) -> dict:
        user_perms = set(current_user.get("permissions", []))
        # admin:all grants everything
        if "admin:all" in user_perms:
            return current_user
        for perm in permission_names:
            if perm not in user_perms:
                raise AuthorizationException(
                    message=f"Missing permission: {perm}.",
                    error_code="INSUFFICIENT_PERMISSION",
                )
        return current_user
    return _guard


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def get_pagination(
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> PaginationParams:
    """Dependency providing standardized pagination parameters."""
    return PaginationParams(page=page, page_size=page_size)


# ---------------------------------------------------------------------------
# Type aliases — clean endpoint signatures
# ---------------------------------------------------------------------------
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[dict, Depends(get_current_user)]
Pagination = Annotated[PaginationParams, Depends(get_pagination)]
ConfigDep = Annotated[AppConfig, Depends(get_config_dep)]

# Legacy alias — keeps existing routers working (they used CurrentApiKey)
CurrentApiKey = Annotated[dict, Depends(get_current_user)]
