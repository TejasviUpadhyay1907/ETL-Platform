"""
Pydantic schemas for authentication and user management endpoints.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    """POST /api/v1/auth/login"""
    username: str = Field(min_length=1, description="Username or email address")
    password: str = Field(min_length=1, description="Plaintext password")


class LoginResponse(BaseModel):
    """Successful login response payload."""
    access_token: str = Field(description="JWT access token")
    refresh_token: str = Field(description="JWT refresh token (7-day lifetime)")
    token_type: str = Field(default="bearer")
    expires_in: int = Field(description="Access token lifetime in seconds")
    user_id: str = Field(description="Authenticated user UUID")
    username: str
    roles: list[str] = Field(default_factory=list)


class RefreshRequest(BaseModel):
    """POST /api/v1/auth/refresh"""
    refresh_token: str = Field(description="Valid JWT refresh token")


class RefreshResponse(BaseModel):
    """Successful token refresh response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LogoutRequest(BaseModel):
    """POST /api/v1/auth/logout"""
    refresh_token: str = Field(description="Refresh token to invalidate")


class ChangePasswordRequest(BaseModel):
    """POST /api/v1/auth/change-password"""
    current_password: str = Field(min_length=1, description="Current password")
    new_password: str = Field(
        min_length=8,
        description="New password — minimum 8 characters",
    )

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class UserCreateRequest(BaseModel):
    """POST /api/v1/users"""
    username: str = Field(min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, description="Minimum 8 characters")
    full_name: str | None = Field(default=None, max_length=200)
    role_names: list[str] = Field(default_factory=list)


class UserUpdateRequest(BaseModel):
    """PUT /api/v1/users/{user_id}"""
    full_name: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    """User profile response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    full_name: str | None
    is_active: bool
    is_locked: bool
    is_superuser: bool
    roles: list[str] = Field(default_factory=list)
    last_login_at: datetime | None = None
    created_at: datetime | None = None

    @classmethod
    def from_user(cls, user) -> "UserResponse":
        return cls(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_locked=user.is_locked,
            is_superuser=user.is_superuser,
            roles=user.role_names,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
        )


class UserListResponse(BaseModel):
    """Minimal user info for list endpoints."""
    id: uuid.UUID
    username: str
    email: str
    is_active: bool
    roles: list[str]
    last_login_at: datetime | None = None


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

class RoleResponse(BaseModel):
    """Role detail response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    display_name: str
    description: str | None
    is_system_role: bool
    permissions: list[str] = Field(default_factory=list)
    created_at: datetime | None = None

    @classmethod
    def from_role(cls, role) -> "RoleResponse":
        return cls(
            id=role.id,
            name=role.name,
            display_name=role.display_name,
            description=role.description,
            is_system_role=role.is_system_role,
            permissions=list(role.permission_names),
            created_at=role.created_at,
        )


class AssignRoleRequest(BaseModel):
    """POST /api/v1/users/{user_id}/roles"""
    role_name: str = Field(description="Role name to assign, e.g. 'data_engineer'")


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

class APIKeyCreateRequest(BaseModel):
    """POST /api/v1/api-keys"""
    name: str = Field(min_length=1, max_length=100, description="Human-readable key name")
    scope: str = Field(
        default="readonly",
        description="Key scope: admin | pipeline | readonly",
        pattern="^(admin|pipeline|readonly)$",
    )
    description: str | None = Field(default=None, max_length=500)
    expires_at: datetime | None = Field(
        default=None,
        description="Optional expiry — None means never expires",
    )


class APIKeyResponse(BaseModel):
    """API key summary (no raw key — returned only at creation)."""
    id: uuid.UUID
    name: str
    key_prefix: str
    scope: str
    description: str | None
    is_active: bool
    expires_at: datetime | None
    last_used_at: datetime | None
    request_count: int
    created_at: datetime | None

    @classmethod
    def from_api_key(cls, key) -> "APIKeyResponse":
        return cls(
            id=key.id,
            name=key.name,
            key_prefix=key.key_prefix,
            scope=key.scope,
            description=key.description,
            is_active=key.is_active,
            expires_at=key.expires_at,
            last_used_at=key.last_used_at,
            request_count=key.request_count,
            created_at=key.created_at,
        )


class APIKeyCreatedResponse(APIKeyResponse):
    """API key creation response — includes the raw key (shown ONCE)."""
    raw_key: str = Field(
        description="The actual API key value — store it now, it will not be shown again."
    )


class APIKeyRotateResponse(BaseModel):
    """Response after rotating an API key."""
    old_key_id: uuid.UUID
    new_key: "APIKeyCreatedResponse"
