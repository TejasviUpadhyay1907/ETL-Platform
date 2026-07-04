"""
Cryptographic hashing utilities.

Used for:
- API key hashing (never store plain-text API keys)
- File integrity checksums
- Deterministic ID generation for deduplication
"""

import hashlib
import hmac
import secrets
import uuid


def generate_api_key(prefix: str = "etl") -> str:
    """
    Generate a new random API key.

    Format: {prefix}_{random_urlsafe_token}
    Example: etl_Xk9mN2pQ8rL5vT1w...

    Args:
        prefix: Short prefix identifying the key type.

    Returns:
        A new random API key string (never stored as-is — hash it first).
    """
    token = secrets.token_urlsafe(32)
    return f"{prefix}_{token}"


def hash_api_key(api_key: str, salt: str) -> str:
    """
    Hash an API key for secure database storage.

    Uses HMAC-SHA256 with a salt to prevent rainbow table attacks.
    The plain-text key is never stored.

    Args:
        api_key: The plain-text API key to hash.
        salt: The application-level salt (from config.api_key_salt).

    Returns:
        Hex-encoded HMAC-SHA256 hash.
    """
    return hmac.new(
        salt.encode("utf-8"),
        api_key.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_api_key(plain_key: str, hashed_key: str, salt: str) -> bool:
    """
    Securely verify an API key against its stored hash.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        plain_key: The plain-text key provided by the client.
        hashed_key: The stored hash from the database.
        salt: The application-level salt.

    Returns:
        True if the key matches, False otherwise.
    """
    computed_hash = hash_api_key(plain_key, salt)
    return hmac.compare_digest(computed_hash, hashed_key)


def generate_run_id() -> str:
    """
    Generate a unique pipeline run ID.

    Returns:
        UUID4 string without hyphens for compact storage.
    """
    return str(uuid.uuid4())


def generate_ingestion_id() -> str:
    """
    Generate a unique ingestion event ID.

    Returns:
        UUID4 string.
    """
    return str(uuid.uuid4())


def compute_row_hash(values: list[str]) -> str:
    """
    Compute a deterministic hash for a set of field values.

    Used for detecting duplicate records across pipeline runs
    when a natural deduplication key is not available.

    Args:
        values: List of field values that together identify a unique record.

    Returns:
        SHA-256 hex hash of the concatenated values.
    """
    combined = "|".join(str(v) for v in values)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()
