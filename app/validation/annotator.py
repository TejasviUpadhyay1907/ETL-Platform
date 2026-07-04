"""
ValidationAnnotator — marks rows as valid, invalid, or warning based on violations.

Produces the three DataFrame subsets returned in ValidationResult:
  - valid_df:   rows with zero ERROR violations
  - rejected_df: rows with at least one ERROR violation
  - warning_df: rows that are valid but have WARNING violations

CRITICAL: This module NEVER modifies data values. It only performs
boolean indexing on the original DataFrame to produce filtered subsets.
"""

from __future__ import annotations

import pandas as pd

from app.validation.models import RuleViolation, Severity


class ValidationAnnotator:
    """
    Partitions a DataFrame into valid/rejected/warning subsets.

    Takes the complete list of violations from ValidationExecutor and
    uses row indices to partition the original DataFrame without touching values.
    """

    def annotate(
        self,
        df: pd.DataFrame,
        violations: list[RuleViolation],
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, set[int], set[int]]:
        """
        Partition the DataFrame into three subsets.

        Args:
            df:         The original DataFrame (NOT modified).
            violations: All violations from the executor.

        Returns:
            (valid_df, rejected_df, warning_df, invalid_indices, warning_indices)
        """
        # Collect row indices that have ERROR violations
        invalid_indices: set[int] = set()
        warning_indices: set[int] = set()

        for v in violations:
            if v.row_index is None:
                continue  # dataset-level violation — doesn't mark specific rows
            if v.severity == Severity.ERROR:
                invalid_indices.add(v.row_index)
            elif v.severity == Severity.WARNING:
                warning_indices.add(v.row_index)

        all_indices = set(df.index)
        valid_only_warning = warning_indices - invalid_indices
        truly_valid = all_indices - invalid_indices - valid_only_warning

        # Produce subsets via boolean indexing — values are NOT copied/changed
        valid_df    = df.loc[list(truly_valid)].copy() if truly_valid else df.iloc[0:0].copy()
        rejected_df = df.loc[list(invalid_indices)].copy() if invalid_indices else df.iloc[0:0].copy()
        warning_df  = df.loc[list(valid_only_warning)].copy() if valid_only_warning else df.iloc[0:0].copy()

        return valid_df, rejected_df, warning_df, invalid_indices, warning_indices
