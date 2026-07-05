"""
Password hashing and verification using passlib/bcrypt.
"""
from __future__ import annotations

import warnings

# Suppress passlib's bcrypt version detection warning (cosmetic only, hashing works fine)
warnings.filterwarnings("ignore", message=".*error reading bcrypt version.*")
warnings.filterwarnings("ignore", category=UserWarning, module="passlib")

from passlib.context import CryptContext

# ---------------------------------------------------------------------------
# CryptContext — single source of truth for hashing algorithm and config
# ---------------------------------------------------------------------------
# Using bcrypt as the primary scheme. deprecated="auto" means older hash
# schemes are transparently upgraded on next verify().
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """
    Hash a plaintext password using bcrypt.

    Args:
        plain_password: The plaintext password to hash.

    Returns:
        bcrypt hash string suitable for DB storage.
    """
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.

    Args:
        plain_password:   The password provided by the user.
        hashed_password:  The bcrypt hash stored in the database.

    Returns:
        True if the password matches, False otherwise.
        Never raises — invalid hashes return False.
    """
    try:
        return _pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def needs_rehash(hashed_password: str) -> bool:
    """
    Check if a stored hash should be rehashed (e.g., after bcrypt rounds upgrade).

    Returns True if the hash is outdated and should be updated on next login.
    """
    try:
        return _pwd_context.needs_update(hashed_password)
    except Exception:
        return False
