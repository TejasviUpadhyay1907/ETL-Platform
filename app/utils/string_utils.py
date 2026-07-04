"""
String utility functions.

Provides reusable string manipulation helpers used in the cleaning
and transformation modules.
"""

import re
import unicodedata


def normalize_whitespace(value: str) -> str:
    """
    Trim leading/trailing whitespace and collapse internal multiple spaces.

    Args:
        value: Input string.

    Returns:
        String with normalized whitespace.
    """
    return re.sub(r"\s+", " ", value.strip())


def to_snake_case(value: str) -> str:
    """
    Convert a string to snake_case.

    Useful for normalizing column names from CSV headers.

    Args:
        value: Input string (e.g., "Order Total", "orderTotal", "Order-Total").

    Returns:
        snake_case string (e.g., "order_total").
    """
    # Insert underscore before uppercase letters preceded by lowercase
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    # Replace spaces and hyphens with underscores
    value = re.sub(r"[\s\-]+", "_", value)
    # Remove non-alphanumeric/underscore characters
    value = re.sub(r"[^\w]", "", value)
    return value.lower()


def to_title_case(value: str) -> str:
    """
    Convert a string to Title Case, handling edge cases.

    Args:
        value: Input string.

    Returns:
        Title case string.
    """
    return value.strip().title()


def strip_currency_symbols(value: str) -> str:
    """
    Remove common currency symbols and formatting from a numeric string.

    Handles: $, £, €, ¥, commas, spaces within numbers.

    Args:
        value: String that may contain currency formatting.

    Returns:
        Clean numeric string suitable for float() parsing.
    """
    # Remove currency symbols
    cleaned = re.sub(r"[£$€¥₹₩₺₽]", "", value)
    # Remove thousands separators (commas between digits)
    cleaned = re.sub(r"(\d),(\d{3})", r"\1\2", cleaned)
    # Remove spaces within number
    cleaned = cleaned.strip()
    return cleaned


def is_valid_email(value: str) -> bool:
    """
    Validate an email address format.

    Uses a practical regex that covers the vast majority of valid emails.
    For strict RFC 5322 compliance, use a dedicated library.

    Args:
        value: Email string to validate.

    Returns:
        True if the format is valid, False otherwise.
    """
    pattern = re.compile(
        r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    )
    return bool(pattern.match(value.strip()))


def is_valid_phone(value: str) -> bool:
    """
    Validate a phone number format (international or US format).

    Args:
        value: Phone number string.

    Returns:
        True if looks like a valid phone number, False otherwise.
    """
    # Strip common formatting characters
    digits_only = re.sub(r"[\s\-\(\)\+\.]", "", value)
    # Valid if 7-15 digits (international range)
    return bool(re.match(r"^\d{7,15}$", digits_only))


def truncate(value: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate a string to a maximum length with an optional suffix.

    Args:
        value: Input string.
        max_length: Maximum length including suffix.
        suffix: String to append when truncated.

    Returns:
        Truncated string.
    """
    if len(value) <= max_length:
        return value
    return value[: max_length - len(suffix)] + suffix


def normalize_unicode(value: str) -> str:
    """
    Normalize unicode characters to their ASCII equivalents where possible.

    Useful for normalizing names and addresses from international sources.

    Args:
        value: Input string possibly containing unicode characters.

    Returns:
        ASCII-normalized string.
    """
    # NFKD decomposition + encode to ASCII ignoring unmappable characters
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def slugify(value: str) -> str:
    """
    Convert a string to a URL-safe slug.

    Args:
        value: Input string.

    Returns:
        Lowercase hyphenated slug (e.g., "my-order-report").
    """
    value = normalize_unicode(value).lower()
    value = re.sub(r"[^\w\s\-]", "", value)
    value = re.sub(r"[\s_]+", "-", value)
    return value.strip("-")
