"""
Display formatting helpers — numbers, durations, status badges, exports.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

def fmt_number(n: int | float | None) -> str:
    if n is None:
        return "—"
    return f"{int(n):,}"


def fmt_pct(v: float | None, decimals: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimals}f}%"


def fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f}m"
    return f"{minutes / 60:.1f}h"


def fmt_bytes(n: int | None) -> str:
    if n is None:
        return "—"
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n/1024:.1f} KB"
    return f"{n/1024**2:.1f} MB"


# ---------------------------------------------------------------------------
# Status badge (HTML)
# ---------------------------------------------------------------------------

_STATUS_STYLE = {
    "completed":  ("✅", "#22C55E"),
    "succeeded":  ("✅", "#22C55E"),
    "running":    ("🔄", "#3B82F6"),
    "failed":     ("❌", "#EF4444"),
    "cancelled":  ("⛔", "#6B7280"),
    "retrying":   ("🔁", "#F59E0B"),
    "queued":     ("⏳", "#60A5FA"),
    "pending":    ("⏳", "#60A5FA"),
    "active":     ("🟢", "#22C55E"),
    "inactive":   ("⚪", "#6B7280"),
}


def status_badge(status: str) -> str:
    """Return an emoji + colored text string for a status."""
    icon, _ = _STATUS_STYLE.get(status.lower() if status else "", ("❓", "#94A3B8"))
    return f"{icon} {status.title()}"


def grade_badge(grade: str) -> str:
    _g = {"A+": "🏆", "A": "🌟", "B": "✅", "C": "⚠️", "D": "🔶", "F": "❌"}
    return f"{_g.get(grade, '—')} {grade}"


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------

def fmt_dt(dt_str: str | None) -> str:
    if not dt_str:
        return "—"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return dt_str


def fmt_dt_relative(dt_str: str | None) -> str:
    """Return 'X minutes ago' style string."""
    if not dt_str:
        return "—"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo)
        diff = int((now - dt).total_seconds())
        if diff < 60:
            return f"{diff}s ago"
        if diff < 3600:
            return f"{diff // 60}m ago"
        if diff < 86400:
            return f"{diff // 3600}h ago"
        return f"{diff // 86400}d ago"
    except Exception:
        return dt_str


# ---------------------------------------------------------------------------
# DataFrame helpers
# ---------------------------------------------------------------------------

def safe_df(data: list[dict] | None) -> pd.DataFrame:
    """Convert a list of dicts to a DataFrame, returning empty DF on None."""
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)


def truncate_str(s: str | None, max_len: int = 40) -> str:
    if not s:
        return ""
    return s if len(s) <= max_len else s[:max_len] + "…"


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def df_to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Data")
    return buf.getvalue()


def extract_data(response: dict[str, Any]) -> list[dict] | dict | None:
    """Extract the 'data' field from an APIResponse envelope."""
    if response.get("error"):
        return None
    return response.get("data")


def extract_list(response: dict[str, Any]) -> list[dict]:
    """Extract a list from an APIResponse or PaginatedResponse envelope."""
    if response.get("error"):
        return []
    data = response.get("data", [])
    return data if isinstance(data, list) else []


def extract_pagination(response: dict[str, Any]) -> dict[str, Any]:
    """Extract pagination metadata."""
    return response.get("pagination", {"total_items": 0, "total_pages": 1})
