"""
SchemaValidator — validates column presence, naming, and structure.

Checks:
  SV_001 — required columns are present
  SV_002 — no unexpected columns (columns not in schema)
  SV_003 — no duplicate column names
  SV_004 — dataset is not completely empty (zero rows)

This validator is the first to run because schema issues invalidate all other checks.
"""

from __future__ import annotations

import pandas as pd

from app.validation.models import RuleViolation, Severity
from app.validation.rules.base_rule import BaseValidationRule


class SchemaValidator(BaseValidationRule):
    """Validates the structural schema of the dataset against the expected schema."""

    rule_code = "SV"
    rule_category = "schema"
    description = "Schema structure validation"
    priority = 10  # always runs first

    def __init__(
        self,
        expected_columns: list[str],
        required_columns: list[str] | None = None,
        allow_extra_columns: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.expected_columns = [c.lower().strip() for c in expected_columns]
        self.required_columns = (
            [c.lower().strip() for c in required_columns]
            if required_columns
            else self.expected_columns
        )
        self.allow_extra_columns = allow_extra_columns

    def validate(self, df: pd.DataFrame, dataset_type: str) -> list[RuleViolation]:
        violations: list[RuleViolation] = []
        actual_cols = [c.lower().strip() for c in df.columns]

        # SV_001 — required columns missing
        for col in self.required_columns:
            if col not in actual_cols:
                violations.append(self._violation(
                    field_name=col,
                    row_index=None,
                    actual_value="<missing>",
                    expected=f"Column '{col}' to be present",
                    message=f"Required column '{col}' is missing from the dataset.",
                    suggested_fix=f"Ensure the source file contains a column named '{col}'.",
                    severity=Severity.ERROR,
                ))

        # SV_002 — unexpected columns
        if not self.allow_extra_columns:
            for col in actual_cols:
                if col not in self.expected_columns:
                    violations.append(self._violation(
                        field_name=col,
                        row_index=None,
                        actual_value=col,
                        expected="Column not in approved schema",
                        message=f"Unexpected column '{col}' found — not in the approved schema.",
                        suggested_fix=f"Remove column '{col}' or update the schema config.",
                        severity=Severity.WARNING,
                    ))

        # SV_003 — duplicate column names
        seen: dict[str, int] = {}
        for col in actual_cols:
            seen[col] = seen.get(col, 0) + 1
        for col, count in seen.items():
            if count > 1:
                violations.append(self._violation(
                    field_name=col,
                    row_index=None,
                    actual_value=f"Appears {count} times",
                    expected="Each column name must be unique",
                    message=f"Duplicate column name '{col}' appears {count} times.",
                    suggested_fix=f"Rename or remove duplicate columns named '{col}'.",
                    severity=Severity.ERROR,
                ))

        # SV_004 — completely empty dataset
        if len(df) == 0:
            violations.append(self._violation(
                field_name=None,
                row_index=None,
                actual_value=0,
                expected="At least 1 data row",
                message="Dataset contains zero data rows.",
                suggested_fix="Verify the source file contains data rows (not just a header).",
                severity=Severity.WARNING,
            ))

        return violations
