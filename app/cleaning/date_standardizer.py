"""
DateStandardizer — parses and standardizes date fields to ISO 8601.

Per-field operations:
  standardize_date: true   — parse any common format, output YYYY-MM-DD
  timezone_normalize: UTC  — convert to named timezone
  remove_impossible: true  — drop rows where date is before 1900 or after 2100

Priority: 40
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from app.cleaning.base_cleaner import BaseCleaningRule
from app.cleaning.models import CleaningAction

_ISO_FORMAT = "%Y-%m-%d"
_MIN_DATE = pd.Timestamp("1900-01-01")
_MAX_DATE = pd.Timestamp("2100-12-31")


class DateStandardizer(BaseCleaningRule):
    """Parses date strings to ISO 8601 and repairs common format issues."""

    rule_name = "DateStandardizer"
    rule_category = "date"
    priority = 40

    def __init__(
        self,
        field_strategies: dict[str, dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.field_strategies: dict[str, dict[str, Any]] = {
            k.lower(): v for k, v in (field_strategies or {}).items()
        }

    def clean(
        self, df: pd.DataFrame, dataset_type: str
    ) -> tuple[pd.DataFrame, list[CleaningAction]]:
        actions: list[CleaningAction] = []
        result = df.copy()
        col_lower = {c.lower(): c for c in result.columns}
        rows_to_drop: set[int] = set()

        for fld_lower, cfg in self.field_strategies.items():
            if not cfg.get("standardize_date"):
                continue
            col = col_lower.get(fld_lower)
            if col is None:
                continue

            before = result[col].copy()
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                parsed = pd.to_datetime(result[col], errors="coerce", dayfirst=False)

            for idx in result.index:
                orig = before.at[idx]
                ts   = parsed.at[idx]

                if pd.isna(ts):
                    # Could not parse
                    if str(orig).strip() not in ("", "nan", "None", "null"):
                        actions.append(self._action(
                            "DT_001", col, int(idx), orig, None,
                            "parse_date",
                            f"Could not parse '{orig}' as a date in '{col}'",
                            confidence=0.0,
                        ))
                    continue

                # Check impossible dates
                if cfg.get("remove_impossible") and (ts < _MIN_DATE or ts > _MAX_DATE):
                    rows_to_drop.add(idx)
                    actions.append(self._action(
                        "DT_002", col, int(idx), orig, None,
                        "drop_row",
                        f"Impossible date {ts.date()} dropped from '{col}'",
                    ))
                    continue

                # Standardize to ISO YYYY-MM-DD string
                iso_str = ts.strftime(_ISO_FORMAT)
                if str(orig).strip() != iso_str:
                    result.at[idx, col] = iso_str
                    actions.append(self._action(
                        "DT_003", col, int(idx), orig, iso_str,
                        "parse_date",
                        f"Date standardized to ISO 8601: '{orig}' → '{iso_str}'",
                    ))
                else:
                    result.at[idx, col] = iso_str

        if rows_to_drop:
            result = result.drop(index=list(rows_to_drop)).reset_index(drop=True)

        return result, actions
