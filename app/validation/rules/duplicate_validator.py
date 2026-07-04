"""
DuplicateValidator — detects duplicate rows and duplicate business keys.

Checks:
  DUP_001 — exact duplicate rows (all columns identical)
  DUP_002 — duplicate values in a declared primary/business key field
  DUP_003 — duplicate composite keys (multiple fields together form the key)
"""

from __future__ import annotations

import pandas as pd

from app.validation.models import RuleViolation, Severity
from app.validation.rules.base_rule import BaseValidationRule


class DuplicateValidator(BaseValidationRule):
    """Detects duplicate rows and duplicate key violations."""

    rule_code = "DUP"
    rule_category = "duplicate"
    description = "Duplicate detection"
    priority = 25

    def __init__(
        self,
        key_fields: list[str] | None = None,        # single-column keys
        composite_keys: list[list[str]] | None = None,  # multi-column keys
        check_full_row_duplicates: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.key_fields = [f.lower() for f in (key_fields or [])]
        self.composite_keys = [
            [c.lower() for c in key] for key in (composite_keys or [])
        ]
        self.check_full_row_duplicates = check_full_row_duplicates

    def validate(self, df: pd.DataFrame, dataset_type: str) -> list[RuleViolation]:
        violations: list[RuleViolation] = []
        if df.empty:
            return violations

        col_map = {c.lower(): c for c in df.columns}

        # DUP_001 — exact duplicate rows
        if self.check_full_row_duplicates:
            dup_mask = df.duplicated(keep="first")
            dup_count = dup_mask.sum()
            if dup_count > 0:
                dup_indices = df.index[dup_mask].tolist()
                for idx in dup_indices[:100]:  # cap to avoid huge violation lists
                    violations.append(self._violation(
                        field_name=None,
                        row_index=int(idx),
                        actual_value="<exact duplicate>",
                        expected="Each row should be unique",
                        message=f"Row {idx} is an exact duplicate of an earlier row.",
                        suggested_fix="Remove duplicate rows during the cleaning stage.",
                        severity=Severity.WARNING,
                    ))
                if dup_count > 100:
                    violations.append(self._violation(
                        field_name=None,
                        row_index=None,
                        actual_value=f"{dup_count} duplicate rows",
                        expected="All rows unique",
                        message=(
                            f"{dup_count} exact duplicate rows detected "
                            f"({dup_count / len(df) * 100:.1f}% of dataset)."
                        ),
                        suggested_fix="Deduplicate source data or apply deduplication in cleaning.",
                        severity=Severity.WARNING,
                    ))

        # DUP_002 — duplicate single-column keys
        for field_lower in self.key_fields:
            orig_col = col_map.get(field_lower)
            if orig_col is None:
                continue
            series = df[orig_col].dropna()
            dup_mask = series.duplicated(keep="first")
            for idx in series.index[dup_mask][:50]:
                val = series[idx]
                violations.append(self._violation(
                    field_name=orig_col,
                    row_index=int(idx),
                    actual_value=val,
                    expected=f"'{orig_col}' values must be unique",
                    message=f"Duplicate key value '{val}' in column '{orig_col}' at row {idx}.",
                    suggested_fix=f"Ensure '{orig_col}' contains only unique values.",
                    severity=Severity.ERROR,
                ))
            total_dups = dup_mask.sum()
            if total_dups > 50:
                violations.append(self._violation(
                    field_name=orig_col,
                    row_index=None,
                    actual_value=f"{total_dups} duplicate keys",
                    expected=f"'{orig_col}' must be unique across all rows",
                    message=f"Column '{orig_col}' has {total_dups} duplicate values.",
                    suggested_fix=f"Investigate duplicate {orig_col} values in source system.",
                    severity=Severity.ERROR,
                ))

        # DUP_003 — composite key duplicates
        for key_group in self.composite_keys:
            orig_cols = [col_map[c] for c in key_group if c in col_map]
            if len(orig_cols) < 2:
                continue
            existing = df[orig_cols].dropna()
            dup_mask = existing.duplicated(keep="first")
            total_dups = dup_mask.sum()
            if total_dups > 0:
                violations.append(self._violation(
                    field_name="+".join(orig_cols),
                    row_index=None,
                    actual_value=f"{total_dups} duplicate composite keys",
                    expected=f"Composite key ({', '.join(orig_cols)}) must be unique",
                    message=(
                        f"Composite key ({', '.join(orig_cols)}) has "
                        f"{total_dups} duplicate combinations."
                    ),
                    suggested_fix="Ensure the combination of these key fields is unique.",
                    severity=Severity.ERROR,
                ))

        return violations
