"""
Tests for dashboard/utils/formatting.py
"""
from __future__ import annotations

import pandas as pd
import pytest

# We must set a dummy streamlit state before importing formatting
# since formatting itself doesn't import streamlit, this is fine.
from dashboard.utils.formatting import (
    fmt_number, fmt_pct, fmt_duration, fmt_bytes,
    fmt_dt, fmt_dt_relative, status_badge, grade_badge,
    safe_df, truncate_str,
    df_to_csv_bytes, df_to_excel_bytes,
    extract_data, extract_list, extract_pagination,
)


class TestFmtNumber:
    def test_integer(self):
        assert fmt_number(1000) == "1,000"

    def test_zero(self):
        assert fmt_number(0) == "0"

    def test_none_returns_dash(self):
        assert fmt_number(None) == "—"

    def test_large(self):
        assert fmt_number(1_000_000) == "1,000,000"


class TestFmtPct:
    def test_basic(self):
        assert fmt_pct(95.5) == "95.5%"

    def test_zero(self):
        assert fmt_pct(0.0) == "0.0%"

    def test_none(self):
        assert fmt_pct(None) == "—"

    def test_custom_decimals(self):
        assert fmt_pct(99.999, decimals=0) == "100%"


class TestFmtDuration:
    def test_seconds(self):
        assert "s" in fmt_duration(45.0)

    def test_minutes(self):
        assert "m" in fmt_duration(90.0)

    def test_hours(self):
        assert "h" in fmt_duration(7200.0)

    def test_none(self):
        assert fmt_duration(None) == "—"


class TestFmtBytes:
    def test_bytes(self):
        assert "B" in fmt_bytes(500)

    def test_kilobytes(self):
        assert "KB" in fmt_bytes(2048)

    def test_megabytes(self):
        assert "MB" in fmt_bytes(2 * 1024 * 1024)

    def test_none(self):
        assert fmt_bytes(None) == "—"


class TestFmtDt:
    def test_valid_iso(self):
        result = fmt_dt("2024-01-15T10:30:00")
        assert "2024" in result

    def test_none(self):
        assert fmt_dt(None) == "—"

    def test_empty(self):
        assert fmt_dt("") == "—"


class TestFmtDtRelative:
    def test_recent(self):
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc).isoformat()
        result = fmt_dt_relative(now)
        assert "ago" in result or "s ago" in result

    def test_none(self):
        assert fmt_dt_relative(None) == "—"


class TestStatusBadge:
    def test_completed(self):
        badge = status_badge("completed")
        assert "✅" in badge

    def test_failed(self):
        badge = status_badge("failed")
        assert "❌" in badge

    def test_running(self):
        badge = status_badge("running")
        assert "🔄" in badge

    def test_unknown(self):
        # Should not raise, returns something
        badge = status_badge("unknown_status")
        assert isinstance(badge, str)


class TestGradeBadge:
    def test_a_plus(self):
        assert "A+" in grade_badge("A+")

    def test_f(self):
        assert "F" in grade_badge("F")


class TestSafeDf:
    def test_none_returns_empty(self):
        df = safe_df(None)
        assert df.empty

    def test_list_of_dicts(self):
        df = safe_df([{"a": 1, "b": 2}, {"a": 3, "b": 4}])
        assert len(df) == 2
        assert "a" in df.columns

    def test_empty_list(self):
        df = safe_df([])
        assert df.empty


class TestTruncateStr:
    def test_short_string(self):
        assert truncate_str("hello", 10) == "hello"

    def test_long_string(self):
        result = truncate_str("a" * 50, 10)
        assert result.endswith("…")
        assert len(result) == 11

    def test_none(self):
        assert truncate_str(None) == ""


class TestExport:
    def test_csv_bytes_not_empty(self):
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        b = df_to_csv_bytes(df)
        assert isinstance(b, bytes)
        assert len(b) > 0
        assert b"a" in b

    def test_excel_bytes_not_empty(self):
        df = pd.DataFrame({"x": [10, 20], "y": [30, 40]})
        b = df_to_excel_bytes(df)
        assert isinstance(b, bytes)
        assert len(b) > 0


class TestExtractHelpers:
    def test_extract_data_success(self):
        resp = {"success": True, "data": {"id": "123"}}
        assert extract_data(resp) == {"id": "123"}

    def test_extract_data_error(self):
        resp = {"error": "not found"}
        assert extract_data(resp) is None

    def test_extract_list_success(self):
        resp = {"data": [{"a": 1}, {"a": 2}]}
        result = extract_list(resp)
        assert len(result) == 2

    def test_extract_list_error(self):
        resp = {"error": "bad request"}
        assert extract_list(resp) == []

    def test_extract_list_non_list_data(self):
        resp = {"data": {"key": "val"}}
        # data is not a list — returns empty
        assert extract_list(resp) == []

    def test_extract_pagination(self):
        resp = {
            "pagination": {"total_items": 100, "total_pages": 5, "has_next": True}
        }
        pag = extract_pagination(resp)
        assert pag["total_items"] == 100

    def test_extract_pagination_missing(self):
        pag = extract_pagination({})
        assert pag["total_items"] == 0
