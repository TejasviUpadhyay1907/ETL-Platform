"""
Authentication router.

POST /api/v1/auth/login           — login, returns JWT access + refresh tokens
POST /api/v1/auth/logout          — revoke session
POST /api/v1/auth/refresh         — exchange refresh token for new access token
POST /api/v1/auth/change-password — change authenticated user's password
GET  /api/v1/auth/me              — return current user profile

These endpoints are public (exempt from JWTAuthMiddleware) except
/me and /change-password which require a valid access token.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.dependencies import DbSession, CurrentUser
from app.api.schemas.auth_schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    RefreshResponse,
    UserResponse,
)
from app.api.schemas.base_schemas import APIResponse
from app.logging.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── POST /api/v1/auth/login ────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=APIResponse[LoginResponse],
    summary="Login and obtain JWT tokens",
    description=(
        "Authenticate with username/password. Returns an access token (short-lived) "
        "and a refresh token (7 days). Pass the access token as "
        "`Authorization: Bearer <token>` on subsequent requests."
    ),
)
def login(
    request: Request,
    payload: LoginRequest,
    db: DbSession,
) -> APIResponse[LoginResponse]:
    from app.auth.auth_service import AuthService

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    svc = AuthService(db)
    result = svc.login(
        username=payload.username,
        password=payload.password,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    return APIResponse[LoginResponse].ok(data=LoginResponse(**result))


# ── POST /api/v1/auth/logout ───────────────────────────────────────────────

@router.post(
    "/logout",
    response_model=APIResponse[dict],
    summary="Logout and revoke refresh token",
)
def logout(
    payload: LogoutRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> APIResponse[dict]:
    from app.auth.auth_service import AuthService

    svc = AuthService(db)
    svc.logout(payload.refresh_token, current_user["user_id"])
    return APIResponse[dict].ok(data={"logged_out": True})


# ── POST /api/v1/auth/refresh ─────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=APIResponse[RefreshResponse],
    summary="Refresh access token",
    description="Exchange a valid refresh token for a new access + refresh token pair.",
)
def refresh_token(
    payload: RefreshRequest,
    db: DbSession,
) -> APIResponse[RefreshResponse]:
    from app.auth.auth_service import AuthService

    svc = AuthService(db)
    result = svc.refresh(payload.refresh_token)
    return APIResponse[RefreshResponse].ok(data=RefreshResponse(**result))


# ── POST /api/v1/auth/change-password ─────────────────────────────────────

@router.post(
    "/change-password",
    response_model=APIResponse[dict],
    summary="Change current user password",
)
def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> APIResponse[dict]:
    from app.auth.auth_service import AuthService

    svc = AuthService(db)
    svc.change_password(
        user_id=current_user["user_id"],
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return APIResponse[dict].ok(data={"password_changed": True})


# ── GET /api/v1/auth/me ───────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=APIResponse[UserResponse],
    summary="Get current authenticated user",
)
def get_me(
    current_user: CurrentUser,
    db: DbSession,
) -> APIResponse[UserResponse]:
    from app.auth.user_service import UserService
    import uuid as _uuid

    svc = UserService(db)
    user = svc.get_user_by_id(_uuid.UUID(current_user["user_id"]))
    return APIResponse[UserResponse].ok(data=UserResponse.from_user(user))
