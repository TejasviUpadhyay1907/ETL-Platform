"""
JWT access and refresh token management.

Access tokens:   short-lived (configurable, default 60 min), carry user identity + roles
Refresh tokens:  long-lived (7 days), used to obtain new access tokens, stored hashed

Token structure (access token payload):
{
    "sub":   "user-uuid",          # subject — user ID
    "username": "john",
    "roles": ["data_engineer"],
    "scope": "access",             # distinguishes access vs refresh
    "jti":   "uuid4",              # JWT ID for revocation
    "iat":   1234567890,
    "exp":   1234567890,
}

Refresh token payload:
{
    "sub":   "user-uuid",
    "scope": "refresh",
    "jti":   "uuid4",
    "iat":   ...,
    "exp":   ...,
}
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.core.config import get_config
from app.core.exceptions import AuthenticationException
from app.logging.logger import get_logger

logger = get_logger(__name__)

# Refresh token lifetime in days
REFRESH_TOKEN_DAYS = 7


def _config():
    return get_config()


def create_access_token(
    user_id: str,
    username: str,
    roles: list[str],
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        user_id:       UUID string of the user.
        username:      Username (for human-readable token inspection).
        roles:         List of role names the user holds.
        extra_claims:  Additional claims to embed (e.g., email).
        expires_delta: Override default expiration.

    Returns:
        Encoded JWT string.
    """
    cfg = _config()
    now = datetime.now(tz=timezone.utc)
    exp = now + (expires_delta or timedelta(minutes=cfg.jwt_expiration_minutes))

    payload: dict[str, Any] = {
        "sub": user_id,
        "username": username,
        "roles": roles,
        "scope": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": exp,
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm)


def create_refresh_token(user_id: str) -> tuple[str, str]:
    """
    Create a signed JWT refresh token.

    Args:
        user_id: UUID string of the user.

    Returns:
        Tuple of (raw_refresh_token, token_hash).
        The hash should be stored in user_sessions; the raw token sent to client.
    """
    cfg = _config()
    now = datetime.now(tz=timezone.utc)
    jti = str(uuid.uuid4())
    exp = now + timedelta(days=REFRESH_TOKEN_DAYS)

    payload = {
        "sub": user_id,
        "scope": "refresh",
        "jti": jti,
        "iat": now,
        "exp": exp,
    }
    raw_token = jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm)
    token_hash = hash_token(raw_token)
    return raw_token, token_hash


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT access token.

    Args:
        token: Raw JWT string from Authorization header.

    Returns:
        Decoded payload dict.

    Raises:
        AuthenticationException: If the token is invalid, expired, or wrong scope.
    """
    cfg = _config()
    try:
        payload = jwt.decode(token, cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])
    except JWTError as exc:
        logger.warning(f"JWT decode failed: {exc}")
        raise AuthenticationException(
            message="Invalid or expired access token.",
            error_code="TOKEN_INVALID",
        ) from exc

    if payload.get("scope") != "access":
        raise AuthenticationException(
            message="Token is not an access token.",
            error_code="TOKEN_WRONG_SCOPE",
        )

    return payload


def decode_refresh_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT refresh token.

    Raises:
        AuthenticationException: If invalid, expired, or wrong scope.
    """
    cfg = _config()
    try:
        payload = jwt.decode(token, cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])
    except JWTError as exc:
        raise AuthenticationException(
            message="Invalid or expired refresh token.",
            error_code="REFRESH_TOKEN_INVALID",
        ) from exc

    if payload.get("scope") != "refresh":
        raise AuthenticationException(
            message="Token is not a refresh token.",
            error_code="TOKEN_WRONG_SCOPE",
        )

    return payload


def hash_token(raw_token: str) -> str:
    """
    Compute a SHA-256 hex digest of a token.

    Used to store refresh tokens and API keys without keeping the raw value.
    """
    return hashlib.sha256(raw_token.encode()).hexdigest()


def get_token_expiry(days: int = REFRESH_TOKEN_DAYS) -> datetime:
    """Compute a refresh token expiry datetime from now."""
    return datetime.now(tz=timezone.utc) + timedelta(days=days)
