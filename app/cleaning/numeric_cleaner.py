"""
NumericCleaner — standardizes numeric field values.

Per-field operations from cleaning.yaml:
  strip_currency: true    — remove £ $ € ¥ symbols and commas
  strip_whitespace: true  — remove internal spaces
  percentage_parse: true  — convert "45%" → 0.45
  rounding: N             — round to N decimal places
  negative_as_zero: true  — floor negative values at 0
  clip_outliers: true     — IQR-based clipping
  winsorize: true         — winsorize at configurable percentiles

Priority: 35
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from app.cleaning.base_cleaner import BaseCleaningRule
from app.cleaning.models import CleaningAction

_CURRENCY_RE = re.compile(r"[£$€¥₹₩₺₽,\s]")
_PERCENT_RE  = re.compile(r"^\s*(-?[\d.]+)\s*%\s*$")


class NumericCleaner(BaseCleaningRule):
    """Cleans numeric fields: strips symbols, parses percentages, clips outliers."""

    rule_name = "NumericCleaner"
    rule_category = "numeric"
    priority = 35

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

        for fld_lower, cfg in self.field_strategies.items():
            col = col_lower.get(fld_lower)
            if col is None:
                continue

            series = result[col].astype(str)
            before_raw = result[col].copy()

            # Strip currency symbols + commas
            if cfg.get("strip_currency") or cfg.get("strip_whitespace"):
                series = series.str.replace(_CURRENCY_RE, "", regex=True).str.strip()

            # Percentage parsing: "45%" → 45.0 (stored as decimal)
            if cfg.get("percentage_parse"):
                def _parse_pct(v: str) -> str:
                    m = _PERCENT_RE.match(v)
                    return m.group(1) if m else v
                series = series.apply(_parse_pct)

            # Convert to numeric
            numeric = pd.to_numeric(series, errors="coerce")

            # Floor negatives at zero
            if cfg.get("negative_as_zero"):
                neg_mask = numeric < 0
                for idx in numeric.index[neg_mask & numeric.notna()]:
                    orig = numeric.at[idx]
                    numeric.at[idx] = 0.0
                    actions.append(self._action(
                        "NUM_001", col, int(idx), orig, 0.0,
                        "clip_outlier",
                        f"Negative value {orig} floored to 0 in '{col}'",
                    ))

            # Rounding
            precision = cfg.get("rounding")
            if precision is not None:
                numeric = numeric.round(int(precision))

            # IQR-based outlier clipping
            if cfg.get("clip_outliers"):
                q1 = numeric.quantile(0.25)
                q3 = numeric.quantile(0.75)
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
                out_mask = (numeric < lower) | (numeric > upper)
                for idx in numeric.index[out_mask & numeric.notna()]:
                    orig = numeric.at[idx]
                    clipped = max(lower, min(upper, orig))
                    numeric.at[idx] = round(clipped, 4)
                    actions.append(self._action(
                        "NUM_002", col, int(idx), orig, round(clipped, 4),
                        "clip_outlier",
                        f"Outlier {orig} clipped to [{round(lower,2)}, {round(upper,2)}]",
                        confidence=0.8,
                    ))

            # Winsorize
            if cfg.get("winsorize"):
                lo_pct = cfg.get("winsorize_lower", 0.05)
                hi_pct = cfg.get("winsorize_upper", 0.95)
                lo = numeric.quantile(lo_pct)
                hi = numeric.quantile(hi_pct)
                win_mask = (numeric < lo) | (numeric > hi)
                for idx in numeric.index[win_mask & numeric.notna()]:
                    orig = numeric.at[idx]
                    new_val = lo if orig < lo else hi
                    numeric.at[idx] = round(new_val, 4)
                    actions.append(self._action(
                        "NUM_003", col, int(idx), orig, round(new_val, 4),
                        "clip_outlier",
                        f"Value winsorized to [{round(lo,2)}, {round(hi,2)}]",
                        confidence=0.85,
                    ))

            # Record symbol-stripping changes (if values changed before numeric conversion)
            changed_mask = numeric.astype(str) != before_raw.astype(str)
            for idx in result.index[changed_mask & numeric.notna()]:
                orig_val = before_raw.at[idx]
                new_val  = numeric.at[idx]
                if str(orig_val) != str(new_val):
                    already_recorded = any(
                        a.row_index == int(idx) and a.field_name == col
                        for a in actions[-50:]
                    )
                    if not already_recorded:
                        actions.append(self._action(
                            "NUM_004", col, int(idx), orig_val, new_val,
                            "strip_currency",
                            f"Numeric value cleaned in '{col}'",
                        ))

            result[col] = numeric

        return result, actions
