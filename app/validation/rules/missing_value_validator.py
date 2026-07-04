"""
MissingValueValidator — detects null, empty, and blank values.

Checks:
  MV_001 — required field is null/empty
  MV_002 — field null rate exceeds configured threshold
  MV_003 — column is completely empty (100% null)
  MV_004 — row is completely empty (all values null/empty)
"""

from __future__ import annotations

import pandas as pd

from app.validation.models import RuleViolation, Severity
from app.validation.rules.base_rule import BaseValidationRule


class MissingValueValidator(BaseValidationRule):
    """Detects missing, null, and blank values across all fields."""

    rule_code = "MV"
    rule_category = "missing"
    description = "Missing value detection"
    priority = 20

    def __init__(
        self,
        required_fields: list[str] | None = None,
        null_threshold_pct: float = 50.0,   # warn when null% > this
        check_empty_rows: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.required_fields = [f.lower() for f in (required_fields or [])]
        self.null_threshold_pct = null_threshold_pct
        self.check_empty_rows = check_empty_rows

    def validate(self, df: pd.DataFrame, dataset_type: str) -> list[RuleViolation]:
        violations: list[RuleViolation] = []
        if df.empty:
            return violations

        col_map = {c.lower(): c for c in df.columns}

        # MV_001 — required fields null per row
        for field_lower in self.required_fields:
            orig_col = col_map.get(field_lower)
            if orig_col is None:
                continue  # SchemaValidator handles missing columns
            series = df[orig_col]
            null_mask = series.isna() | (series.astype(str).str.strip() == "")
            for idx in df.index[null_mask]:
                violations.append(self._violation(
                    field_name=orig_col,
                    row_index=int(idx),
                    actual_value=None,
                    expected=f"'{orig_col}' must not be null or empty",
                    message=f"Required field '{orig_col}' is null or empty at row {idx}.",
                    suggested_fix=f"Provide a valid value for '{orig_col}'.",
                    severity=Severity.ERROR,
                ))

        # MV_002 — high null rate columns
        total = len(df)
        for col in df.columns:
            null_pct = df[col].isna().sum() / total * 100
            if null_pct >= 100.0:
                # MV_003 — completely empty column
                violations.append(self._violation(
                    field_name=col,
                    row_index=None,
                    actual_value=f"100% null ({total} rows)",
                    expected=f"Column '{col}' should contain data",
                    message=f"Column '{col}' is completely empty (all {total} rows are null).",
                    suggested_fix=f"Investigate why '{col}' has no values; consider removing it.",
                    severity=Severity.WARNING,
                ))
            elif null_pct > self.null_threshold_pct:
                violations.append(self._violation(
                    field_name=col,
                    row_index=None,
                    actual_value=f"{null_pct:.1f}% null",
                    expected=f"Null rate below {self.null_threshold_pct}%",
                    message=(
                        f"Column '{col}' has {null_pct:.1f}% null values "
                        f"(threshold: {self.null_threshold_pct}%)."
                    ),
                    suggested_fix=f"Review the data source; '{col}' may need a default value strategy.",
                    severity=Severity.WARNING,
                ))

        # MV_004 — completely empty rows
        if self.check_empty_rows:
            all_null = df.isna().all(axis=1) | (df.astype(str).apply(
                lambda row: row.str.strip().eq(""), axis=1
            ).all(axis=1))
            for idx in df.index[all_null]:
                violations.append(self._violation(
                    field_name=None,
                    row_index=int(idx),
                    actual_value="<all empty>",
                    expected="Row should contain at least one non-empty value",
                    message=f"Row {idx} is completely empty.",
                    suggested_fix="Remove empty rows from the source file.",
                    severity=Severity.WARNING,
                ))

        return violations
