"""
ReferentialIntegrityValidator — detects orphan records and FK violations.

Cross-dataset validation: checks that values in a FK column exist in a
reference set (either a passed-in set or loaded from the database).

Checks:
  REF_001 — FK value not found in reference set (orphan record)
  REF_002 — FK column has a high orphan rate (dataset-level summary)
"""

from __future__ import annotations

import pandas as pd

from app.validation.models import RuleViolation, Severity
from app.validation.rules.base_rule import BaseValidationRule


class ReferentialIntegrityValidator(BaseValidationRule):
    """Validates foreign-key relationships against reference value sets."""

    rule_code = "REF"
    rule_category = "referential"
    description = "Referential integrity validation"
    priority = 70

    def __init__(
        self,
        # {fk_column: reference_values_set}
        references: dict[str, set[str]] | None = None,
        orphan_rate_threshold_pct: float = 5.0,
        max_violations_per_fk: int = 50,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.references: dict[str, set[str]] = {
            k.lower(): {str(v) for v in vs}
            for k, vs in (references or {}).items()
        }
        self.orphan_threshold = orphan_rate_threshold_pct
        self.max_v = max_violations_per_fk

    def validate(self, df: pd.DataFrame, dataset_type: str) -> list[RuleViolation]:
        violations: list[RuleViolation] = []
        if df.empty or not self.references:
            return violations

        col_map = {c.lower(): c for c in df.columns}

        for fk_lower, ref_set in self.references.items():
            orig_col = col_map.get(fk_lower)
            if orig_col is None:
                continue

            series = df[orig_col].dropna().astype(str)
            total = len(series)
            if total == 0:
                continue

            orphan_mask = ~series.isin(ref_set)
            orphan_count = int(orphan_mask.sum())
            orphan_pct = orphan_count / total * 100

            # REF_001 — per-row orphan violations (capped)
            for idx in series.index[orphan_mask][:self.max_v]:
                val = series[idx]
                violations.append(self._violation(
                    field_name=orig_col,
                    row_index=int(idx),
                    actual_value=val,
                    expected=f"'{orig_col}' value must exist in reference dataset",
                    message=(
                        f"Orphan record: '{orig_col}' value '{val}' "
                        f"does not exist in the reference dataset."
                    ),
                    suggested_fix=(
                        f"Ensure '{orig_col}' references a valid existing record. "
                        "Remove or correct orphan records."
                    ),
                    severity=Severity.ERROR,
                ))

            # REF_002 — dataset-level summary if orphan rate is high
            if orphan_count > 0:
                sev = Severity.ERROR if orphan_pct > self.orphan_threshold else Severity.WARNING
                violations.append(self._violation(
                    field_name=orig_col,
                    row_index=None,
                    actual_value=f"{orphan_count}/{total} ({orphan_pct:.1f}%) orphan values",
                    expected=f"Orphan rate < {self.orphan_threshold}%",
                    message=(
                        f"Column '{orig_col}' has {orphan_count} orphan values "
                        f"({orphan_pct:.1f}% of non-null values lack a matching reference)."
                    ),
                    suggested_fix=(
                        f"Load reference data for '{orig_col}' first, "
                        "then re-ingest this dataset."
                    ),
                    severity=sev,
                ))

        return violations
