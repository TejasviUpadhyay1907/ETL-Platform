"""
CategoricalValidator — validates categorical field values.

Checks:
  CAT_001 — value not in allowed list
  CAT_002 — case inconsistency (same value in different cases)
  CAT_003 — rare category (< configured frequency threshold)
  CAT_004 — unknown / unlisted category detected
"""

from __future__ import annotations

import pandas as pd

from app.validation.models import RuleViolation, Severity
from app.validation.rules.base_rule import BaseValidationRule


class CategoricalValidator(BaseValidationRule):
    """Validates categorical columns against configured allowed value sets."""

    rule_code = "CAT"
    rule_category = "categorical"
    description = "Categorical value validation"
    priority = 45

    def __init__(
        self,
        categorical_fields: dict[str, list[str]] | None = None,  # field → [allowed values]
        rare_threshold_pct: float = 1.0,
        check_case_consistency: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        # Normalise to lowercase for case-insensitive matching
        self.categorical_fields: dict[str, list[str]] = {
            k.lower(): [str(v).lower() for v in vs]
            for k, vs in (categorical_fields or {}).items()
        }
        self.rare_threshold_pct = rare_threshold_pct
        self.check_case_consistency = check_case_consistency

    def validate(self, df: pd.DataFrame, dataset_type: str) -> list[RuleViolation]:
        violations: list[RuleViolation] = []
        if df.empty:
            return violations

        col_map = {c.lower(): c for c in df.columns}

        for field_lower, allowed in self.categorical_fields.items():
            orig_col = col_map.get(field_lower)
            if orig_col is None:
                continue

            series = df[orig_col].dropna().astype(str).str.strip()
            total = len(series)
            if total == 0:
                continue

            allowed_set = set(allowed)
            val_counts = series.str.lower().value_counts()

            # CAT_001 — unknown values
            unknown_vals = set(series.str.lower().unique()) - allowed_set
            for unknown in sorted(unknown_vals)[:20]:
                count = int(val_counts.get(unknown, 0))
                violations.append(self._violation(
                    field_name=orig_col,
                    row_index=None,
                    actual_value=unknown,
                    expected=f"One of: {allowed[:10]}{'...' if len(allowed) > 10 else ''}",
                    message=(
                        f"Unknown category '{unknown}' in '{orig_col}' "
                        f"({count} occurrences, {count/total*100:.1f}%)."
                    ),
                    suggested_fix=(
                        f"Map '{unknown}' to one of the allowed values "
                        f"or add it to the approved list."
                    ),
                    severity=Severity.WARNING,
                ))

            # CAT_002 — case inconsistency
            if self.check_case_consistency:
                unique_raw = series.unique()
                unique_lower_map: dict[str, list[str]] = {}
                for v in unique_raw:
                    unique_lower_map.setdefault(v.lower(), []).append(v)
                for lower_val, variants in unique_lower_map.items():
                    if len(variants) > 1:
                        violations.append(self._violation(
                            field_name=orig_col,
                            row_index=None,
                            actual_value=f"Variants: {variants}",
                            expected="Consistent casing",
                            message=(
                                f"Column '{orig_col}' has case variants of '{lower_val}': "
                                f"{variants}."
                            ),
                            suggested_fix=f"Standardise casing of '{orig_col}' to lowercase.",
                            severity=Severity.WARNING,
                        ))

            # CAT_003 — rare categories
            for val, count in val_counts.items():
                pct = count / total * 100
                if pct < self.rare_threshold_pct and val in allowed_set:
                    violations.append(self._violation(
                        field_name=orig_col,
                        row_index=None,
                        actual_value=f"'{val}' ({count} rows, {pct:.2f}%)",
                        expected=f"Category frequency >= {self.rare_threshold_pct}%",
                        message=(
                            f"Rare category '{val}' in '{orig_col}': "
                            f"{count} occurrences ({pct:.2f}% — below {self.rare_threshold_pct}% threshold)."
                        ),
                        suggested_fix="Investigate whether rare categories should be merged.",
                        severity=Severity.INFO,
                    ))

        return violations
