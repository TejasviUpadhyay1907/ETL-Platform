"""
BusinessRuleValidator — evaluates configurable business rules from YAML.

Supported check types (mirrors rules.yaml):
  not_null             — field must not be null/empty
  greater_than         — numeric field > value
  greater_than_or_equal — numeric field >= value
  less_than            — numeric field < value
  less_than_or_equal   — numeric field <= value
  between              — value <= field <= max_value
  in_list              — field value must be in allowed list
  not_in_list          — field value must NOT be in list
  valid_date           — value can be parsed as a date
  valid_email          — value matches email format
  valid_phone          — value matches phone format
  min_length           — string length >= value
  max_length           — string length <= value
  regex_match          — value matches regex pattern
  unique               — all values in field must be unique

Rules are loaded from config/datasets/{dataset_type}/rules.yaml.
No business logic is hardcoded — all rules are data-driven.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from app.validation.models import RuleViolation, Severity
from app.validation.rules.base_rule import BaseValidationRule


class BusinessRuleValidator(BaseValidationRule):
    """
    Evaluates dataset-specific business rules loaded from YAML configuration.

    Each rule in the YAML produces violations for every row that fails it.
    """

    rule_code = "BR"
    rule_category = "business"
    description = "Business rule validation"
    priority = 50

    def __init__(self, rules: list[dict[str, Any]], **kwargs) -> None:
        """
        Args:
            rules: List of rule definition dicts loaded from rules.yaml.
                   Each dict must have: rule_code, check, field (most rules),
                   and optionally: value, values, severity, description.
        """
        super().__init__(**kwargs)
        self.rules = rules

    def validate(self, df: pd.DataFrame, dataset_type: str) -> list[RuleViolation]:
        violations: list[RuleViolation] = []
        if df.empty:
            return violations

        col_map = {c.lower(): c for c in df.columns}

        for rule_def in self.rules:
            rule_violations = self._apply_rule(df, col_map, rule_def)
            violations.extend(rule_violations)

        return violations

    def _apply_rule(
        self,
        df: pd.DataFrame,
        col_map: dict[str, str],
        rule: dict[str, Any],
    ) -> list[RuleViolation]:
        """Apply one rule definition and return violations."""
        violations: list[RuleViolation] = []

        code = rule.get("rule_code", "BR_UNKNOWN")
        check = rule.get("check", "").lower()
        field_lower = str(rule.get("field", "")).lower()
        severity = rule.get("severity", Severity.ERROR)
        description = rule.get("description", "")
        required = rule.get("required", True)
        threshold = rule.get("value")
        allowed_values = rule.get("values", [])

        orig_col = col_map.get(field_lower)
        if orig_col is None:
            return violations  # column missing — SchemaValidator handles this

        series = df[orig_col]
        non_null = series.dropna()
        non_null = non_null[non_null.astype(str).str.strip() != ""]

        # ── not_null ───────────────────────────────────────────────────────
        if check == "not_null":
            null_mask = series.isna() | (series.astype(str).str.strip() == "")
            for idx in df.index[null_mask]:
                violations.append(self._br_violation(
                    code, description, orig_col, idx,
                    None, "Not null/empty", severity,
                    f"Required field '{orig_col}' is null or empty.",
                    f"Provide a valid value for '{orig_col}'.",
                ))

        # ── numeric comparisons ────────────────────────────────────────────
        elif check in ("greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal"):
            if threshold is None:
                return violations
            for idx, val in non_null.items():
                num = self._to_numeric(val)
                if num is None:
                    continue
                failed = False
                if check == "greater_than"          and not (num > threshold):    failed = True
                elif check == "greater_than_or_equal" and not (num >= threshold): failed = True
                elif check == "less_than"            and not (num < threshold):    failed = True
                elif check == "less_than_or_equal"   and not (num <= threshold):  failed = True
                if failed:
                    op = {"greater_than": ">", "greater_than_or_equal": ">=",
                          "less_than": "<", "less_than_or_equal": "<="}[check]
                    violations.append(self._br_violation(
                        code, description, orig_col, int(idx),
                        val, f"{orig_col} {op} {threshold}", severity,
                        f"'{orig_col}' value {val} fails check: {op} {threshold}.",
                        f"Correct '{orig_col}' to satisfy the constraint {op} {threshold}.",
                    ))

        # ── between ────────────────────────────────────────────────────────
        elif check == "between":
            min_val = rule.get("min", threshold)
            max_val = rule.get("max")
            if min_val is None or max_val is None:
                return violations
            for idx, val in non_null.items():
                num = self._to_numeric(val)
                if num is None:
                    continue
                if not (min_val <= num <= max_val):
                    violations.append(self._br_violation(
                        code, description, orig_col, int(idx),
                        val, f"{min_val} <= {orig_col} <= {max_val}", severity,
                        f"'{orig_col}' value {val} is outside [{min_val}, {max_val}].",
                        f"Correct '{orig_col}' to be between {min_val} and {max_val}.",
                    ))

        # ── in_list ────────────────────────────────────────────────────────
        elif check == "in_list":
            allowed = {str(v).lower().strip() for v in allowed_values}
            for idx, val in non_null.items():
                if str(val).lower().strip() not in allowed:
                    violations.append(self._br_violation(
                        code, description, orig_col, int(idx),
                        val, f"One of {allowed_values}", severity,
                        f"'{orig_col}' value '{val}' is not in the allowed list.",
                        f"Use one of the allowed values: {allowed_values}.",
                    ))

        # ── not_in_list ────────────────────────────────────────────────────
        elif check == "not_in_list":
            forbidden = {str(v).lower().strip() for v in allowed_values}
            for idx, val in non_null.items():
                if str(val).lower().strip() in forbidden:
                    violations.append(self._br_violation(
                        code, description, orig_col, int(idx),
                        val, f"Not one of {allowed_values}", severity,
                        f"'{orig_col}' value '{val}' is in the forbidden list.",
                        f"Remove or replace forbidden value '{val}'.",
                    ))

        # ── valid_date ─────────────────────────────────────────────────────
        elif check == "valid_date":
            from app.utils.date_utils import parse_date
            for idx, val in non_null.items():
                if parse_date(val) is None:
                    violations.append(self._br_violation(
                        code, description, orig_col, int(idx),
                        val, "Parseable date", severity,
                        f"'{orig_col}' value '{val}' is not a valid date.",
                        f"Format '{orig_col}' as YYYY-MM-DD.",
                    ))

        # ── valid_email ────────────────────────────────────────────────────
        elif check == "valid_email":
            from app.utils.string_utils import is_valid_email
            for idx, val in non_null.items():
                if not is_valid_email(str(val)):
                    violations.append(self._br_violation(
                        code, description, orig_col, int(idx),
                        val, "Valid email address", severity,
                        f"'{orig_col}' value '{val}' is not a valid email.",
                        f"Correct the email address format in '{orig_col}'.",
                    ))

        # ── valid_phone ────────────────────────────────────────────────────
        elif check == "valid_phone":
            from app.utils.string_utils import is_valid_phone
            for idx, val in non_null.items():
                if not is_valid_phone(str(val)):
                    violations.append(self._br_violation(
                        code, description, orig_col, int(idx),
                        val, "Valid phone number", severity,
                        f"'{orig_col}' value '{val}' is not a valid phone number.",
                        f"Format '{orig_col}' as an international phone number.",
                    ))

        # ── min_length / max_length ────────────────────────────────────────
        elif check in ("min_length", "max_length"):
            if threshold is None:
                return violations
            for idx, val in non_null.items():
                length = len(str(val).strip())
                if check == "min_length" and length < threshold:
                    violations.append(self._br_violation(
                        code, description, orig_col, int(idx),
                        val, f"Length >= {threshold}", severity,
                        f"'{orig_col}' value '{val}' is too short (length {length} < {threshold}).",
                        f"Ensure '{orig_col}' has at least {threshold} characters.",
                    ))
                elif check == "max_length" and length > threshold:
                    violations.append(self._br_violation(
                        code, description, orig_col, int(idx),
                        val, f"Length <= {threshold}", severity,
                        f"'{orig_col}' value '{val}' is too long (length {length} > {threshold}).",
                        f"Truncate '{orig_col}' to {threshold} characters.",
                    ))

        # ── regex_match ────────────────────────────────────────────────────
        elif check == "regex_match":
            pattern = rule.get("pattern", "")
            try:
                compiled = re.compile(pattern)
            except re.error:
                return violations
            for idx, val in non_null.items():
                if not compiled.match(str(val)):
                    violations.append(self._br_violation(
                        code, description, orig_col, int(idx),
                        val, f"Matches pattern: {pattern}", severity,
                        f"'{orig_col}' value '{val}' does not match required pattern.",
                        f"Format '{orig_col}' to match: {pattern}",
                    ))

        # ── unique ─────────────────────────────────────────────────────────
        elif check == "unique":
            dup_mask = non_null.duplicated(keep="first")
            for idx in non_null.index[dup_mask][:50]:
                violations.append(self._br_violation(
                    code, description, orig_col, int(idx),
                    non_null[idx], f"'{orig_col}' must be unique", severity,
                    f"Duplicate value '{non_null[idx]}' in column '{orig_col}'.",
                    f"Ensure all values in '{orig_col}' are unique.",
                ))

        return violations

    def _br_violation(
        self,
        rule_code: str,
        rule_description: str,
        field: str,
        row_index: int,
        actual_value: Any,
        expected: str,
        severity: str,
        message: str,
        suggested_fix: str,
    ) -> RuleViolation:
        v = self._violation(field, row_index, actual_value, expected, message, suggested_fix, severity)
        v.rule_code = rule_code
        v.rule_description = rule_description
        return v

    @staticmethod
    def _to_numeric(val: Any) -> float | None:
        try:
            clean = str(val).strip().replace(",", "").replace("$", "").replace("£", "").replace("€", "")
            return float(clean)
        except (ValueError, TypeError):
            return None
