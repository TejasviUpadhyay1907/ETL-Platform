"""
StatisticalValidator — computes column profiles and detects statistical anomalies.

This validator does NOT produce row-level violations for out-of-range values —
that is the job of BusinessRuleValidator. Instead it:
  - Builds a ColumnProfile for every numeric column
  - Flags dataset-level statistical anomalies (extreme skew, suspiciously uniform data)
  - Detects outliers using IQR method and generates a dataset-level summary violation

Checks:
  STAT_001 — column contains outliers (IQR method)
  STAT_002 — column has extreme skewness (|skewness| > threshold)
  STAT_003 — column has zero variance (all values identical)
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from app.validation.models import ColumnProfile, RuleViolation, Severity
from app.validation.rules.base_rule import BaseValidationRule


class StatisticalValidator(BaseValidationRule):
    """Computes statistical profiles and detects distribution anomalies."""

    rule_code = "STAT"
    rule_category = "statistical"
    description = "Statistical profile and anomaly detection"
    priority = 60

    def __init__(
        self,
        outlier_iqr_multiplier: float = 1.5,
        skewness_threshold: float = 3.0,
        top_n_values: int = 10,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.iqr_multiplier = outlier_iqr_multiplier
        self.skew_threshold = skewness_threshold
        self.top_n = top_n_values
        # Profiles built during validate() — accessible after execution
        self.column_profiles: dict[str, ColumnProfile] = {}

    def validate(self, df: pd.DataFrame, dataset_type: str) -> list[RuleViolation]:
        violations: list[RuleViolation] = []
        if df.empty:
            return violations

        self.column_profiles = {}

        for col in df.columns:
            profile = self._build_profile(df, col)
            self.column_profiles[col] = profile

            # STAT_003 — zero variance numeric column
            if profile.std_dev is not None and profile.std_dev == 0.0 and profile.non_null_count > 1:
                violations.append(self._violation(
                    field_name=col, row_index=None,
                    actual_value=f"All values = {profile.min_value}",
                    expected="Column should have meaningful variance",
                    message=f"Column '{col}' has zero variance — all {profile.non_null_count} values are identical.",
                    suggested_fix="Investigate whether this column provides meaningful information.",
                    severity=Severity.WARNING,
                ))

            # STAT_001 — outliers
            if profile.outlier_count > 0:
                pct = profile.outlier_count / max(profile.non_null_count, 1) * 100
                violations.append(self._violation(
                    field_name=col, row_index=None,
                    actual_value=f"{profile.outlier_count} outliers ({pct:.1f}%)",
                    expected=f"Values within IQR × {self.iqr_multiplier} fence",
                    message=(
                        f"Column '{col}' has {profile.outlier_count} outlier values "
                        f"({pct:.1f}% of non-null values)."
                    ),
                    suggested_fix="Review outliers — they may indicate data entry errors.",
                    severity=Severity.WARNING,
                ))

            # STAT_002 — extreme skewness
            if profile.skewness is not None and abs(profile.skewness) > self.skew_threshold:
                violations.append(self._violation(
                    field_name=col, row_index=None,
                    actual_value=f"skewness = {profile.skewness:.2f}",
                    expected=f"|skewness| <= {self.skew_threshold}",
                    message=(
                        f"Column '{col}' is highly skewed (skewness = {profile.skewness:.2f}). "
                        "Distribution may be non-representative."
                    ),
                    suggested_fix="Consider log-transforming or reviewing the data distribution.",
                    severity=Severity.WARNING,
                ))

        return violations

    def _build_profile(self, df: pd.DataFrame, col: str) -> ColumnProfile:
        series = df[col]
        total = len(series)
        null_count = int(series.isna().sum())
        non_null = series.dropna()
        non_null_count = len(non_null)

        # String analysis
        str_series = series.dropna().astype(str)
        empty_str = int((str_series.str.strip() == "").sum())
        has_lead  = bool((str_series != str_series.str.lstrip()).any())
        has_trail = bool((str_series != str_series.str.rstrip()).any())
        has_mixed = False
        if len(str_series) > 0:
            upper = str_series.str.upper()
            lower = str_series.str.lower()
            # Mixed case: not all-upper AND not all-lower
            all_upper = (str_series == upper).all()
            all_lower = (str_series == lower).all()
            has_mixed = not all_upper and not all_lower

        # Unique count
        unique_count = int(series.nunique(dropna=True))
        dup_count = non_null_count - unique_count if non_null_count >= unique_count else 0

        # Top values
        top_values: list[tuple[str, int]] = []
        if non_null_count > 0:
            top = non_null.astype(str).value_counts().head(self.top_n)
            top_values = [(str(k), int(v)) for k, v in top.items()]

        # Rare values (< 1% frequency)
        rare_count = 0
        if non_null_count > 0:
            val_counts = non_null.astype(str).value_counts()
            rare_count = int((val_counts < max(1, non_null_count * 0.01)).sum())

        # Numeric statistics
        min_v = max_v = mean_v = med_v = std_v = q1_v = q3_v = iqr_v = skew_v = None
        outlier_count = 0
        numeric = pd.to_numeric(non_null, errors="coerce").dropna()
        if len(numeric) > 0:
            min_v  = float(numeric.min())
            max_v  = float(numeric.max())
            mean_v = float(numeric.mean())
            med_v  = float(numeric.median())
            std_v  = float(numeric.std()) if len(numeric) > 1 else 0.0
            q1_v   = float(numeric.quantile(0.25))
            q3_v   = float(numeric.quantile(0.75))
            iqr_v  = q3_v - q1_v
            skew_v = float(numeric.skew()) if len(numeric) > 2 else 0.0

            # IQR outlier detection
            lower = q1_v - self.iqr_multiplier * iqr_v
            upper = q3_v + self.iqr_multiplier * iqr_v
            outlier_count = int(((numeric < lower) | (numeric > upper)).sum())

            # Handle NaN skewness
            if math.isnan(skew_v):
                skew_v = None

        return ColumnProfile(
            column_name=col,
            dtype_detected=str(series.dtype),
            total_count=total,
            null_count=null_count,
            non_null_count=non_null_count,
            null_pct=null_count / total * 100 if total > 0 else 0.0,
            unique_count=unique_count,
            duplicate_count=max(0, dup_count),
            min_value=min_v, max_value=max_v, mean=mean_v, median=med_v,
            std_dev=std_v, q1=q1_v, q3=q3_v, iqr=iqr_v, skewness=skew_v,
            outlier_count=outlier_count,
            top_values=top_values,
            rare_value_count=rare_count,
            has_leading_whitespace=has_lead,
            has_trailing_whitespace=has_trail,
            has_mixed_case=has_mixed,
            empty_string_count=empty_str,
        )
