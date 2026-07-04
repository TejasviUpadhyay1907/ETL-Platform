"""
Unit tests for utility modules.

Tests string utilities, date utilities, hash utilities, and file utilities.
These are pure unit tests — no external dependencies required.
"""

import pytest

from app.utils.date_utils import is_valid_date_string, parse_date, to_iso_date_string
from app.utils.hash_utils import compute_row_hash, generate_api_key, hash_api_key, verify_api_key
from app.utils.string_utils import (
    is_valid_email,
    is_valid_phone,
    normalize_whitespace,
    strip_currency_symbols,
    to_snake_case,
    truncate,
)


class TestStringUtils:
    """Tests for app.utils.string_utils"""

    def test_normalize_whitespace_trims(self):
        assert normalize_whitespace("  hello  ") == "hello"

    def test_normalize_whitespace_collapses_internal(self):
        assert normalize_whitespace("hello   world") == "hello world"

    def test_to_snake_case_from_spaces(self):
        assert to_snake_case("Order Total") == "order_total"

    def test_to_snake_case_from_camel(self):
        assert to_snake_case("orderTotal") == "order_total"

    def test_to_snake_case_from_hyphens(self):
        assert to_snake_case("order-total") == "order_total"

    def test_strip_currency_usd(self):
        assert strip_currency_symbols("$1,234.56") == "1234.56"

    def test_strip_currency_gbp(self):
        assert strip_currency_symbols("£99.99") == "99.99"

    def test_strip_currency_eur(self):
        assert strip_currency_symbols("€1.234,56") == "1.234,56"

    def test_valid_email(self):
        assert is_valid_email("user@example.com") is True

    def test_invalid_email_no_at(self):
        assert is_valid_email("userexample.com") is False

    def test_invalid_email_no_domain(self):
        assert is_valid_email("user@") is False

    def test_valid_phone(self):
        assert is_valid_phone("+1-555-555-5555") is True

    def test_invalid_phone_too_short(self):
        assert is_valid_phone("123") is False

    def test_truncate_short_string(self):
        result = truncate("hello", max_length=10)
        assert result == "hello"

    def test_truncate_long_string(self):
        result = truncate("hello world", max_length=8)
        assert len(result) <= 8
        assert result.endswith("...")


class TestDateUtils:
    """Tests for app.utils.date_utils"""

    def test_parse_iso_date(self):
        from datetime import date

        result = parse_date("2025-01-15")
        assert result == date(2025, 1, 15)

    def test_parse_us_date(self):
        from datetime import date

        result = parse_date("01/15/2025")
        assert result == date(2025, 1, 15)

    def test_parse_european_date(self):
        from datetime import date

        result = parse_date("15/01/2025")
        assert result == date(2025, 1, 15)

    def test_parse_date_returns_none_for_invalid(self):
        result = parse_date("not-a-date")
        assert result is None

    def test_parse_date_returns_none_for_none(self):
        result = parse_date(None)
        assert result is None

    def test_parse_date_from_datetime(self):
        from datetime import date, datetime

        dt = datetime(2025, 6, 15, 10, 30, 0)
        result = parse_date(dt)
        assert result == date(2025, 6, 15)

    def test_to_iso_date_string(self):
        from datetime import date

        result = to_iso_date_string(date(2025, 1, 15))
        assert result == "2025-01-15"

    def test_to_iso_date_string_none(self):
        assert to_iso_date_string(None) is None

    def test_is_valid_date_string_true(self):
        assert is_valid_date_string("2025-01-15") is True

    def test_is_valid_date_string_false(self):
        assert is_valid_date_string("32/13/2025") is False


class TestHashUtils:
    """Tests for app.utils.hash_utils"""

    def test_generate_api_key_has_prefix(self):
        key = generate_api_key("etl")
        assert key.startswith("etl_")

    def test_generate_api_key_is_unique(self):
        key1 = generate_api_key()
        key2 = generate_api_key()
        assert key1 != key2

    def test_hash_api_key_produces_string(self):
        result = hash_api_key("my-api-key", "my-salt")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex = 64 chars

    def test_verify_api_key_correct(self):
        key = "test-key-12345"
        salt = "test-salt"
        hashed = hash_api_key(key, salt)
        assert verify_api_key(key, hashed, salt) is True

    def test_verify_api_key_incorrect(self):
        key = "test-key-12345"
        salt = "test-salt"
        hashed = hash_api_key(key, salt)
        assert verify_api_key("wrong-key", hashed, salt) is False

    def test_compute_row_hash_deterministic(self):
        values = ["order123", "customer456", "2025-01-15"]
        hash1 = compute_row_hash(values)
        hash2 = compute_row_hash(values)
        assert hash1 == hash2

    def test_compute_row_hash_different_values(self):
        hash1 = compute_row_hash(["a", "b"])
        hash2 = compute_row_hash(["a", "c"])
        assert hash1 != hash2
