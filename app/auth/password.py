"""
Password hashing and verification.

Uses raw bcrypt directly to avoid passlib/bcrypt version compatibility issues
on Python 3.12+ (passlib 1.7.4 has a known __about__ attribute error with
newer bcrypt versions that breaks hash verification).
"""
from __future__ import annotations

import warnings
warnings.filterwarnings("ignore", message=".*error reading bcrypt version.*")
warnings.filterwarnings("ignore", category=UserWarning, module="passlib")

import bcrypt


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt (rounds=12)."""
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Check if a stored hash needs upgrading (always False for raw bcrypt)."""
    return False
