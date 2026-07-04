"""
NullHandler — cleans null/empty values using per-field configurable strategies.

Supported strategies (from cleaning.yaml field_strategies.*.null_strategy):
  drop_row      — remove the entire row
  fill_default  — replace with a configured default_value
  fill_mean     — replace with column mean (numeric only)
  fill_median   — replace with column median (numeric only)
  fill_mode     — replace with most-frequent value
  fill_zero     — replace with 0 (numeric)
  forward_fill  — propagate last valid value forward
  backward_fill — propagate next valid value backward
  flag          — replace with a sentinel_value (marks as known-missing)
  interpolate   — linear interpolation for ordered numeric columns
  keep          — leave null as-is (explicit no-op)

Priority: 10 — runs first so later cleaners see populated values.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.cleaning.base_cleaner import BaseCleaningRule
from app.cleaning.models import CleaningAction


class NullHandler(BaseCleaningRule):
    """Per-field null value handler with configurable strategy per column."""

    rule_name = "NullHandler"
    rule_category = "missing"
    priority = 10

    def __init__(
        self,
        field_strategies: dict[str, dict[str, Any]] | None = None,
        global_null_threshold_pct: float = 100.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.field_strategies: dict[str, dict[str, Any]] = {
            k.lower(): v for k, v in (field_strategies or {}).items()
        }
        self.global_null_threshold_pct = global_null_threshold_pct

    def clean(
        self, df: pd.DataFrame, dataset_type: str
    ) -> tuple[pd.DataFrame, list[CleaningAction]]:
        actions: list[CleaningAction] = []
        result = df.copy()
        col_lower = {c.lower(): c for c in result.columns}
        rows_to_drop: set[int] = set()

        for fld_lower, strategy_cfg in self.field_strategies.items():
            col = col_lower.get(fld_lower)
            if col is None:
                continue

            strategy = strategy_cfg.get("null_strategy", "keep").lower()
            default  = strategy_cfg.get("default_value", "")
            sentinel = strategy_cfg.get("sentinel_value", "MISSING")

            # Identify null/empty positions
            null_mask = result[col].isna() | (
                result[col].astype(str).str.strip() == ""
            )
            null_indices = result.index[null_mask].tolist()
            if not null_indices:
                continue

            if strategy == "drop_row":
                rows_to_drop.update(null_indices)
                for idx in null_indices:
                    actions.append(self._action(
                        "MV_DROP", col, int(idx),
                        result.at[idx, col], None,
                        "drop_row",
                        f"Row {idx} dropped: required field '{col}' is null",
                    ))

            elif strategy == "fill_default":
                for idx in null_indices:
                    orig = result.at[idx, col]
                    result.at[idx, col] = default
                    actions.append(self._action(
                        "MV_FILL", col, int(idx), orig, default,
                        "fill_null",
                        f"Null in '{col}' replaced with default '{default}'",
                    ))

            elif strategy == "fill_mean":
                numeric = pd.to_numeric(result[col], errors="coerce")
                fill_val = numeric.mean()
                if pd.isna(fill_val):
                    continue
                fill_val = round(fill_val, 4)
                for idx in null_indices:
                    orig = result.at[idx, col]
                    result.at[idx, col] = fill_val
                    actions.append(self._action(
                        "MV_MEAN", col, int(idx), orig, fill_val,
                        "fill_null", f"Null filled with column mean {fill_val}",
                        confidence=0.8,
                    ))

            elif strategy == "fill_median":
                numeric = pd.to_numeric(result[col], errors="coerce")
                fill_val = numeric.median()
                if pd.isna(fill_val):
                    continue
                fill_val = round(fill_val, 4)
                for idx in null_indices:
                    orig = result.at[idx, col]
                    result.at[idx, col] = fill_val
                    actions.append(self._action(
                        "MV_MED", col, int(idx), orig, fill_val,
                        "fill_null", f"Null filled with column median {fill_val}",
                        confidence=0.8,
                    ))

            elif strategy == "fill_mode":
                mode_vals = result[col].dropna()
                if mode_vals.empty:
                    continue
                fill_val = mode_vals.mode().iloc[0]
                for idx in null_indices:
                    orig = result.at[idx, col]
                    result.at[idx, col] = fill_val
                    actions.append(self._action(
                        "MV_MODE", col, int(idx), orig, fill_val,
                        "fill_null", f"Null filled with column mode '{fill_val}'",
                        confidence=0.7,
                    ))

            elif strategy == "fill_zero":
                for idx in null_indices:
                    orig = result.at[idx, col]
                    result.at[idx, col] = 0
                    actions.append(self._action(
                        "MV_ZERO", col, int(idx), orig, 0,
                        "fill_null", f"Null in '{col}' replaced with 0",
                    ))

            elif strategy == "forward_fill":
                before = result[col].copy()
                result[col] = result[col].ffill()
                for idx in null_indices:
                    new_val = result.at[idx, col]
                    if new_val != before.at[idx]:
                        actions.append(self._action(
                            "MV_FFILL", col, int(idx), before.at[idx], new_val,
                            "fill_null", "Forward-filled from previous valid value",
                            confidence=0.75,
                        ))

            elif strategy == "backward_fill":
                before = result[col].copy()
                result[col] = result[col].bfill()
                for idx in null_indices:
                    new_val = result.at[idx, col]
                    if new_val != before.at[idx]:
                        actions.append(self._action(
                            "MV_BFILL", col, int(idx), before.at[idx], new_val,
                            "fill_null", "Backward-filled from next valid value",
                            confidence=0.75,
                        ))

            elif strategy == "interpolate":
                numeric = pd.to_numeric(result[col], errors="coerce")
                filled = numeric.interpolate(method="linear")
                for idx in null_indices:
                    orig = result.at[idx, col]
                    new_val = filled.at[idx]
                    if not pd.isna(new_val):
                        result.at[idx, col] = round(new_val, 4)
                        actions.append(self._action(
                            "MV_INTERP", col, int(idx), orig, round(new_val, 4),
                            "fill_null", "Interpolated from surrounding values",
                            confidence=0.7,
                        ))

            elif strategy == "flag":
                for idx in null_indices:
                    orig = result.at[idx, col]
                    result.at[idx, col] = sentinel
                    actions.append(self._action(
                        "MV_FLAG", col, int(idx), orig, sentinel,
                        "fill_null", f"Null flagged with sentinel '{sentinel}'",
                    ))
            # strategy == "keep" → no action

        # Apply row drops atomically at the end
        if rows_to_drop:
            result = result.drop(index=list(rows_to_drop)).reset_index(drop=True)

        return result, actions
