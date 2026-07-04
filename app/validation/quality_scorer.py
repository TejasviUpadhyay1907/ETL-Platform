"""
QualityScoreCalculator — computes the six-dimensional quality score.

Dimensions:
  completeness  — (non-null cells / total cells) × 100
  validity      — (valid rows / total rows) × 100
  consistency   — penalised by format violations and type violations
  uniqueness    — (1 − duplicate_rate) × 100
  integrity     — (1 − orphan_rate) × 100
  timeliness    — penalised by date validation failures

Overall score = weighted average (completeness 30%, validity 35%,
consistency 15%, uniqueness 10%, integrity 5%, timeliness 5%).
"""

from __future__ import annotations

import pandas as pd

from app.validation.models import QualityScore, RuleViolation, Severity


class QualityScoreCalculator:
    """Computes the enterprise quality score from validation results."""

    def calculate(
        self,
        df: pd.DataFrame,
        violations: list[RuleViolation],
        invalid_indices: set[int],
        warning_indices: set[int],
        total_rules_executed: int = 0,
    ) -> QualityScore:
        """
        Compute all quality dimensions and return a populated QualityScore.

        Args:
            df:                    The original DataFrame.
            violations:            All violations from the executor.
            invalid_indices:       Row indices with at least one ERROR violation.
            warning_indices:       Row indices with WARNING violations only.
            total_rules_executed:  Total rules that ran.

        Returns:
            Fully populated QualityScore with overall_score and letter_grade set.
        """
        score = QualityScore()
        total_rows = len(df)

        if total_rows == 0:
            score.compute_overall()
            return score

        # --- Record counts ---
        score.total_records   = total_rows
        score.invalid_records = len(invalid_indices)
        score.warning_records = len(warning_indices - invalid_indices)
        score.valid_records   = total_rows - score.invalid_records - score.warning_records
        score.total_violations   = len(violations)
        score.error_violations   = sum(1 for v in violations if v.severity == Severity.ERROR)
        score.warning_violations = sum(1 for v in violations if v.severity == Severity.WARNING)
        score.total_rules_executed = total_rules_executed
        score.rules_failed = len({v.rule_code for v in violations if v.severity == Severity.ERROR})
        score.rules_passed = max(0, total_rules_executed - score.rules_failed)

        # --- Completeness: non-null cells / total cells ---
        total_cells = total_rows * len(df.columns) if len(df.columns) > 0 else 1
        non_null_cells = df.notna().sum().sum()
        score.completeness = min(100.0, non_null_cells / total_cells * 100)

        # --- Validity: rows with no ERROR violations ---
        score.validity = (
            (total_rows - score.invalid_records) / total_rows * 100
        )

        # --- Consistency: penalised by format (FMT) and type (DT) violations ---
        format_violations = sum(
            1 for v in violations
            if v.rule_category in ("format", "dtype")
            and v.row_index is not None
        )
        affected_rows = min(format_violations, total_rows)
        score.consistency = max(0.0, 100.0 - (affected_rows / total_rows * 100))

        # --- Uniqueness: 1 - duplicate_rate ---
        dup_violations = sum(
            1 for v in violations
            if v.rule_category == "duplicate"
            and v.severity == Severity.WARNING
            and v.row_index is not None
        )
        score.uniqueness = max(0.0, 100.0 - (dup_violations / total_rows * 100))

        # --- Integrity: 1 - orphan_rate ---
        ref_violations = sum(
            1 for v in violations
            if v.rule_category == "referential"
            and v.row_index is not None
        )
        if ref_violations > 0:
            score.integrity = max(0.0, 100.0 - (ref_violations / total_rows * 100))

        # --- Timeliness: penalised by date validation failures ---
        date_violations = sum(
            1 for v in violations
            if "date" in (v.field_name or "").lower()
            and v.row_index is not None
        )
        if date_violations > 0:
            score.timeliness = max(0.0, 100.0 - (date_violations / total_rows * 100))

        score.compute_overall()
        return score
