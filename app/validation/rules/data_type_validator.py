"""
DataTypeValidator — validates field value types against expected types.

Supported type checks:
  integer, float, decimal, boolean, date, datetime, email, phone,
  postal_code, currency, uuid, url, string

Checks:
  DT_001 — field value cannot be coerced to expected type
  DT_002 — field contains mixed detectable types (e.g. mostly numeric with some strings)
"""

from __future__ import annotations

import re
import uuid as _uuid
from typing import Any

import pandas as pd

from app.validation.models import RuleViolation, Severity
from app.validation.rules.base_rule import BaseValidationRule

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------
_EMAIL_RE     = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_PHONE_RE     = re.compile(r"^\+?[\d\s\-\(\)\.]{7,20}$")
_POSTAL_US_RE = re.compile(r"^\d{5}(-\d{4})?$")
_URL_RE       = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
_CURRENCY_RE  = re.compile(r"^[£$€¥₹]?\s*\d+([,\d]*)?(\.\d{1,4})?$")
_UUID_RE      = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Type check functions: return True if value is valid for the type
_TYPE_CHECKS: dict[str, Any] = {
    "integer":     lambda v: _safe_int(v),
    "float":       lambda v: _safe_float(v),
    "decimal":     lambda v: _safe_float(v),
    "boolean":     lambda v: str(v).strip().lower() in ("true", "false", "1", "0", "yes", "no"),
    "email":       lambda v: bool(_EMAIL_RE.match(str(v).strip())),
    "phone":       lambda v: bool(_PHONE_RE.match(str(v).strip())),
    "postal_code": lambda v: bool(_POSTAL_US_RE.match(str(v).strip())),
    "url":         lambda v: bool(_URL_RE.match(str(v).strip())),
    "currency":    lambda v: bool(_CURRENCY_RE.match(str(v).strip().replace(",", ""))),
    "uuid":        lambda v: bool(_UUID_RE.match(str(v).strip())),
    "date":        lambda v: _safe_date(v),
    "datetime":    lambda v: _safe_date(v),
    "string":      lambda v: True,   # every value is a valid string
}


def _safe_int(v: Any) -> bool:
    try:
        int(str(v).strip().replace(",", ""))
        return True
    except (ValueError, TypeError):
        return False


def _safe_float(v: Any) -> bool:
    try:
        float(str(v).strip().replace(",", "").replace("$", "").replace("£", "").replace("€", ""))
        return True
    except (ValueError, TypeError):
        return False


def _safe_date(v: Any) -> bool:
    from app.utils.date_utils import parse_date
    return parse_date(v) is not None


class DataTypeValidator(BaseValidationRule):
    """
    Validates that field values conform to their declared data types.

    field_types: dict mapping column_name → expected_type_string
    """

    rule_code = "DT"
    rule_category = "dtype"
    description = "Data type validation"
    priority = 30

    def __init__(
        self,
        field_types: dict[str, str] | None = None,
        max_violations_per_field: int = 100,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.field_types: dict[str, str] = {
            k.lower(): v.lower() for k, v in (field_types or {}).items()
        }
        self.max_violations_per_field = max_violations_per_field

    def validate(self, df: pd.DataFrame, dataset_type: str) -> list[RuleViolation]:
        violations: list[RuleViolation] = []
        if df.empty or not self.field_types:
            return violations

        col_map = {c.lower(): c for c in df.columns}

        for field_lower, expected_type in self.field_types.items():
            orig_col = col_map.get(field_lower)
            if orig_col is None:
                continue

            checker = _TYPE_CHECKS.get(expected_type)
            if checker is None:
                continue  # unknown type — skip

            series = df[orig_col].dropna()
            violation_count = 0

            for idx, val in series.items():
                val_str = str(val).strip()
                if val_str == "" or val_str in ("nan", "None", "null", "NULL"):
                    continue  # nulls handled by MissingValueValidator
                if not checker(val):
                    if violation_count < self.max_violations_per_field:
                        violations.append(self._violation(
                            field_name=orig_col,
                            row_index=int(idx),
                            actual_value=val,
                            expected=f"Valid {expected_type}",
                            message=(
                                f"Field '{orig_col}' value '{val}' is not a valid {expected_type}."
                            ),
                            suggested_fix=(
                                f"Convert '{orig_col}' values to {expected_type} "
                                "or mark invalid rows for cleaning."
                            ),
                            severity=Severity.ERROR,
                        ))
                    violation_count += 1

            # DT_002 — mixed types warning (if some violations but not all)
            non_null_count = len(series)
            if 0 < violation_count < non_null_count:
                pct = violation_count / non_null_count * 100
                violations.append(self._violation(
                    field_name=orig_col,
                    row_index=None,
                    actual_value=f"{violation_count}/{non_null_count} invalid ({pct:.1f}%)",
                    expected=f"All values to be valid {expected_type}",
                    message=(
                        f"Column '{orig_col}' has mixed types: "
                        f"{violation_count} of {non_null_count} non-null values "
                        f"are not valid {expected_type} ({pct:.1f}%)."
                    ),
                    suggested_fix=(
                        f"Standardise '{orig_col}' to {expected_type} in the source system."
                    ),
                    severity=Severity.WARNING,
                ))

        return violations
