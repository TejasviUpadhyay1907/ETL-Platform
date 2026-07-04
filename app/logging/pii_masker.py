"""
PII Masker — field-level value masking for sensitive data in logs.

Ensures that personally identifiable information (PII) is never written
to log files in plain text. Fields configured as sensitive have their
values replaced with masked representations before logging.

This is a compliance requirement — logs may be shipped to external aggregation
systems, and raw PII must never appear in those systems.
"""

import re
from typing import Any

# Fields that should NEVER appear in logs as plain text
DEFAULT_SENSITIVE_FIELDS: frozenset[str] = frozenset(
    {
        "password",
        "secret",
        "token",
        "api_key",
        "api_secret",
        "credit_card",
        "card_number",
        "cvv",
        "ssn",
        "social_security",
        "bank_account",
        "routing_number",
        "email",
        "phone",
        "phone_number",
        "date_of_birth",
        "dob",
        "passport",
        "license_number",
        "private_key",
        "secret_key",
    }
)

MASK_CHARACTER = "***"
EMAIL_PATTERN = re.compile(r"([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})")
CREDIT_CARD_PATTERN = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")
PHONE_PATTERN = re.compile(r"\b(\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")


class PIIMasker:
    """
    Masks sensitive field values before they are written to logs.

    Usage:
        masker = PIIMasker()
        safe_data = masker.mask_dict({"email": "user@example.com", "name": "John"})
        # safe_data = {"email": "***", "name": "John"}
    """

    def __init__(self, additional_sensitive_fields: set[str] | None = None) -> None:
        """
        Initialize the masker with the default + any additional sensitive fields.

        Args:
            additional_sensitive_fields: Extra field names to mask beyond defaults.
        """
        self.sensitive_fields = DEFAULT_SENSITIVE_FIELDS.copy()
        if additional_sensitive_fields:
            self.sensitive_fields = self.sensitive_fields | additional_sensitive_fields

    def mask_value(self, field_name: str, value: Any) -> Any:
        """
        Mask a single field value if it is sensitive.

        Args:
            field_name: Name of the field (checked against sensitive list).
            value: Original value.

        Returns:
            Masked value if field is sensitive, original value otherwise.
        """
        if field_name.lower() in self.sensitive_fields:
            return self._apply_mask(value)
        return value

    def mask_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Mask all sensitive fields in a dictionary.

        Args:
            data: Dictionary potentially containing sensitive fields.

        Returns:
            New dictionary with sensitive values replaced by masks.
        """
        return {key: self.mask_value(key, value) for key, value in data.items()}

    def mask_string(self, text: str) -> str:
        """
        Mask PII patterns found anywhere in a free-form string.

        Applies regex-based detection for emails, credit card numbers, and
        phone numbers that might appear in log messages.

        Args:
            text: Free-form text to scan and mask.

        Returns:
            Text with detected PII patterns replaced by masks.
        """
        # Mask email addresses
        text = EMAIL_PATTERN.sub(lambda m: f"{MASK_CHARACTER}@{m.group(2)}", text)

        # Mask credit card numbers
        text = CREDIT_CARD_PATTERN.sub(MASK_CHARACTER, text)

        # Mask phone numbers
        text = PHONE_PATTERN.sub(MASK_CHARACTER, text)

        return text

    @staticmethod
    def _apply_mask(value: Any) -> str:
        """Replace a value with the mask character."""
        if value is None:
            return MASK_CHARACTER
        # For short values, just mask completely
        # For longer strings, reveal partial to aid debugging (e.g., last 4 of card)
        if isinstance(value, str) and len(value) > 8:
            return f"{MASK_CHARACTER}"
        return MASK_CHARACTER


# Module-level singleton
_masker: PIIMasker | None = None


def get_masker() -> PIIMasker:
    """Get the singleton PIIMasker instance."""
    global _masker
    if _masker is None:
        _masker = PIIMasker()
    return _masker
