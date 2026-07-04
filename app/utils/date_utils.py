"""
Date and time utility functions.

Provides reusable helpers for date parsing, formatting, and validation
used across the validation, cleaning, and transformation modules.
"""

from datetime import date, datetime, timezone
from typing import Any

# Common date formats encountered in retail datasets
COMMON_DATE_FORMATS: list[str] = [
    "%Y-%m-%d",        # ISO 8601 (target format)
    "%d/%m/%Y",        # European
    "%m/%d/%Y",        # US
    "%d-%m-%Y",        # European with dashes
    "%Y/%m/%d",        # ISO with slashes
    "%d.%m.%Y",        # European with dots
    "%m-%d-%Y",        # US with dashes
    "%Y%m%d",          # Compact ISO
    "%d %b %Y",        # e.g., 15 Jan 2025
    "%d %B %Y",        # e.g., 15 January 2025
    "%b %d, %Y",       # e.g., Jan 15, 2025
    "%B %d, %Y",       # e.g., January 15, 2025
    "%Y-%m-%dT%H:%M:%S",     # ISO 8601 with time
    "%Y-%m-%dT%H:%M:%SZ",    # ISO 8601 UTC
    "%Y-%m-%d %H:%M:%S",     # Common datetime
]

ISO_DATE_FORMAT = "%Y-%m-%d"
ISO_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def parse_date(value: Any, formats: list[str] | None = None) -> date | None:
    """
    Attempt to parse a value into a date using multiple common formats.

    Tries each format in order and returns the first successful parse.
    Returns None if all formats fail (instead of raising — caller decides).

    Args:
        value: Value to parse (string, date, datetime, or other).
        formats: List of date format strings to attempt. Defaults to COMMON_DATE_FORMATS.

    Returns:
        Parsed date object, or None if parsing fails.
    """
    if value is None:
        return None

    # Already a date object
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    # Extract date from datetime
    if isinstance(value, datetime):
        return value.date()

    # Convert to string for parsing
    str_value = str(value).strip()

    if not str_value:
        return None

    formats = formats or COMMON_DATE_FORMATS

    for fmt in formats:
        try:
            return datetime.strptime(str_value, fmt).date()
        except (ValueError, TypeError):
            continue

    return None


def parse_date_strict(value: Any, field_name: str = "date") -> date:
    """
    Parse a date value, raising ValueError if parsing fails.

    Args:
        value: Value to parse.
        field_name: Field name for error message context.

    Returns:
        Parsed date object.

    Raises:
        ValueError: If the value cannot be parsed as a date.
    """
    result = parse_date(value)
    if result is None:
        raise ValueError(
            f"Cannot parse '{value}' as a date for field '{field_name}'. "
            f"Supported formats include: YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY."
        )
    return result


def to_iso_date_string(value: date | datetime | None) -> str | None:
    """
    Convert a date or datetime to ISO 8601 date string (YYYY-MM-DD).

    Args:
        value: Date or datetime to format.

    Returns:
        ISO formatted date string, or None if value is None.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().strftime(ISO_DATE_FORMAT)
    return value.strftime(ISO_DATE_FORMAT)


def now_utc() -> datetime:
    """Return current UTC datetime with timezone info."""
    return datetime.now(tz=timezone.utc)


def today_utc() -> date:
    """Return today's date in UTC."""
    return datetime.now(tz=timezone.utc).date()


def is_valid_date_string(value: str) -> bool:
    """
    Check if a string can be parsed as a date.

    Args:
        value: String to validate.

    Returns:
        True if parseable as a date, False otherwise.
    """
    return parse_date(value) is not None
