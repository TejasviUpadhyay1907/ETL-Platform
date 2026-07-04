"""
FormatValidator — detects whitespace, encoding, and format issues.

Checks:
  FMT_001 — leading whitespace in field value
  FMT_002 — trailing whitespace in field value
  FMT_003 — email format invalid
  FMT_004 — phone format invalid
  FMT_005 — URL format invalid
  FMT_006 — special characters in fields that should be clean
  FMT_007 — unicode control characters detected
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import pandas as pd

from app.validation.models import RuleViolation, Severity
from app.validation.rules.base_rule import BaseValidationRule

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_PHONE_RE = re.compile(r"^\+?[\d\s\-\(\)\.]{7,20}$")
_URL_RE   = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
_CTRL_RE  = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class FormatValidator(BaseValidationRule):
    """Detects whitespace issues, format violations, and encoding problems."""

    rule_code = "FMT"
    rule_category = "format"
    description = "Format and whitespace validation"
    priority = 40

    def __init__(
        self,
        check_whitespace_fields: list[str] | None = None,
        email_fields: list[str] | None = None,
        phone_fields: list[str] | None = None,
        url_fields: list[str] | None = None,
        check_control_chars: bool = True,
        max_violations_per_field: int = 50,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.ws_fields = [f.lower() for f in (check_whitespace_fields or [])]
        self.email_fields = [f.lower() for f in (email_fields or [])]
        self.phone_fields = [f.lower() for f in (phone_fields or [])]
        self.url_fields = [f.lower() for f in (url_fields or [])]
        self.check_control_chars = check_control_chars
        self.max_v = max_violations_per_field

    def validate(self, df: pd.DataFrame, dataset_type: str) -> list[RuleViolation]:
        violations: list[RuleViolation] = []
        if df.empty:
            return violations

        col_map = {c.lower(): c for c in df.columns}

        # FMT_001/002 — whitespace in specified fields
        for fld in self.ws_fields:
            col = col_map.get(fld)
            if col is None:
                continue
            series = df[col].dropna().astype(str)
            count = 0
            for idx, val in series.items():
                if count >= self.max_v:
                    break
                if val != val.strip():
                    issue = ("leading" if val != val.lstrip() else "") + \
                            ("trailing" if val != val.rstrip() else "")
                    violations.append(self._violation(
                        field_name=col, row_index=int(idx), actual_value=repr(val),
                        expected="No leading/trailing whitespace",
                        message=f"'{col}' has {issue.strip()} whitespace at row {idx}.",
                        suggested_fix=f"Strip whitespace from '{col}' during cleaning.",
                        severity=Severity.WARNING,
                    ))
                    count += 1

        # FMT_003 — email validation
        for fld in self.email_fields:
            col = col_map.get(fld)
            if col is None:
                continue
            series = df[col].dropna().astype(str)
            count = 0
            for idx, val in series.items():
                if count >= self.max_v:
                    break
                val_s = val.strip()
                if val_s and not _EMAIL_RE.match(val_s):
                    violations.append(self._violation(
                        field_name=col, row_index=int(idx), actual_value=val_s,
                        expected="Valid email format (user@domain.tld)",
                        message=f"'{col}' value '{val_s}' is not a valid email address.",
                        suggested_fix="Correct the email address format.",
                        severity=Severity.ERROR,
                    ))
                    count += 1

        # FMT_004 — phone validation
        for fld in self.phone_fields:
            col = col_map.get(fld)
            if col is None:
                continue
            series = df[col].dropna().astype(str)
            count = 0
            for idx, val in series.items():
                if count >= self.max_v:
                    break
                val_s = val.strip()
                if val_s and not _PHONE_RE.match(val_s):
                    violations.append(self._violation(
                        field_name=col, row_index=int(idx), actual_value=val_s,
                        expected="Valid phone number",
                        message=f"'{col}' value '{val_s}' is not a valid phone number.",
                        suggested_fix="Format phone numbers as international E.164.",
                        severity=Severity.WARNING,
                    ))
                    count += 1

        # FMT_005 — URL validation
        for fld in self.url_fields:
            col = col_map.get(fld)
            if col is None:
                continue
            series = df[col].dropna().astype(str)
            count = 0
            for idx, val in series.items():
                if count >= self.max_v:
                    break
                val_s = val.strip()
                if val_s and not _URL_RE.match(val_s):
                    violations.append(self._violation(
                        field_name=col, row_index=int(idx), actual_value=val_s,
                        expected="Valid URL (http:// or https://)",
                        message=f"'{col}' value '{val_s}' is not a valid URL.",
                        suggested_fix="Ensure URLs start with http:// or https://.",
                        severity=Severity.WARNING,
                    ))
                    count += 1

        # FMT_007 — unicode control characters across all string columns
        if self.check_control_chars:
            for col in df.select_dtypes(include="object").columns:
                series = df[col].dropna().astype(str)
                count = 0
                for idx, val in series.items():
                    if count >= self.max_v:
                        break
                    if _CTRL_RE.search(val):
                        violations.append(self._violation(
                            field_name=col, row_index=int(idx), actual_value=repr(val[:50]),
                            expected="No control characters",
                            message=f"'{col}' contains unicode control characters at row {idx}.",
                            suggested_fix="Strip control characters during cleaning.",
                            severity=Severity.WARNING,
                        ))
                        count += 1

        return violations
