"""
API Key generation, validation, and lifecycle management.

Key format: etl_<32 random hex chars>  (e.g. etl_a3f9b2c1...)
Key prefix:  first 12 chars stored in plain (etl_xxxxxxxx) — safe to display
Key hash:    SHA-256 of the full key stored in api_keys.key_hash

This means:
- Raw key is returned ONCE at creation and never retrievable again
- DB stores only the hash — a stolen DB does not expose usable keys
- Key lookup: compute hash from incoming key, query by hash
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationException, NotFoundException
from app.database.models.auth.api_key import APIKey
from app.logging.logger import get_logger

logger = get_logger(__name__)

_KEY_PREFIX = "etl_"
_KEY_RANDOM_BYTES = 32


def generate_raw_key() -> str:
    """
    Generate a new random API key.

    Format: etl_<64 hex chars>
    """
    random_part = os.urandom(_KEY_RANDOM_BYTES).hex()
    return f"{_KEY_PREFIX}{random_part}"


def hash_key(raw_key: str) -> str:
    """Compute SHA-256 hex digest of a raw API key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def get_key_prefix(raw_key: str) -> str:
    """Return the first 12 characters of the raw key for display."""
    return raw_key[:12]


def create_api_key(
    session: Session,
    user_id: uuid.UUID,
    name: str,
    scope: str = "readonly",
    description: str | None = None,
    expires_at: datetime | None = None,
) -> tuple[APIKey, str]:
    """
    Generate a new API key for a user and persist it.

    Args:
        session:     SQLAlchemy session.
        user_id:     Owner user UUID.
        name:        Human-readable key name.
        scope:       Key scope: admin | pipeline | readonly.
        description: Optional description.
        expires_at:  Optional expiry. None = never expires.

    Returns:
        Tuple of (APIKey ORM instance, raw_key string).
        The raw_key is returned ONCE — it's not stored in the DB.
    """
    raw_key = generate_raw_key()
    key_hash = hash_key(raw_key)
    prefix = get_key_prefix(raw_key)

    api_key = APIKey(
        user_id=user_id,
        name=name,
        key_prefix=prefix,
        key_hash=key_hash,
        scope=scope,
        description=description,
        expires_at=expires_at,
    )
    session.add(api_key)
    session.flush()

    logger.info(
        "API key created",
        key_id=str(api_key.id),
        user_id=str(user_id),
        scope=scope,
        prefix=prefix,
    )
    return api_key, raw_key


def validate_api_key(session: Session, raw_key: str) -> APIKey:
    """
    Validate an incoming API key and return the APIKey record.

    Args:
        session: SQLAlchemy session.
        raw_key: Raw key from the X-API-Key header.

    Returns:
        The active APIKey ORM record.

    Raises:
        AuthenticationException: If key is invalid, revoked, or expired.
    """
    from sqlalchemy import select

    if not raw_key or not raw_key.startswith(_KEY_PREFIX):
        raise AuthenticationException(
            message="Invalid API key format.",
            error_code="API_KEY_INVALID_FORMAT",
        )

    key_hash = hash_key(raw_key)

    api_key = session.execute(
        select(APIKey).where(APIKey.key_hash == key_hash)
    ).scalar_one_or_none()

    if api_key is None:
        raise AuthenticationException(
            message="API key not found.",
            error_code="API_KEY_NOT_FOUND",
        )

    if not api_key.is_active:
        raise AuthenticationException(
            message="API key has been revoked.",
            error_code="API_KEY_REVOKED",
        )

    if api_key.is_expired():
        raise AuthenticationException(
            message="API key has expired.",
            error_code="API_KEY_EXPIRED",
        )

    # Check owning user is still active
    if not api_key.user or not api_key.user.can_login():
        raise AuthenticationException(
            message="API key owner account is not active.",
            error_code="API_KEY_OWNER_INACTIVE",
        )

    # Update usage stats (non-fatal)
    try:
        api_key.last_used_at = datetime.now(tz=timezone.utc)
        api_key.request_count = (api_key.request_count or 0) + 1
        session.flush()
    except Exception as exc:
        logger.warning(f"Could not update API key usage stats: {exc}")

    return api_key


def revoke_api_key(session: Session, key_id: uuid.UUID, user_id: uuid.UUID) -> APIKey:
    """
    Revoke an API key. Only the owning user (or admin) may revoke.

    Raises:
        NotFoundException: Key does not exist or doesn't belong to user.
    """
    from sqlalchemy import select

    api_key = session.execute(
        select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user_id)
    ).scalar_one_or_none()

    if api_key is None:
        raise NotFoundException(message=f"API key {key_id} not found.")

    api_key.is_active = False
    api_key.revoked_at = datetime.now(tz=timezone.utc)
    session.flush()

    logger.info("API key revoked", key_id=str(key_id), user_id=str(user_id))
    return api_key


def rotate_api_key(
    session: Session, key_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[APIKey, str]:
    """
    Revoke an existing API key and create a replacement with the same config.

    Returns the new APIKey and new raw key string.
    """
    old_key = revoke_api_key(session, key_id, user_id)
    new_key, raw = create_api_key(
        session=session,
        user_id=user_id,
        name=f"{old_key.name} (rotated)",
        scope=old_key.scope,
        description=old_key.description,
        expires_at=old_key.expires_at,
    )
    return new_key, raw
