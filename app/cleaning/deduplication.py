"""
DeduplicationHandler — removes duplicate rows with configurable keep strategy.

Strategies:
  keep_first  — keep first occurrence, drop subsequent duplicates
  keep_last   — keep last occurrence, drop earlier duplicates
  drop_all    — drop every row involved in a duplicate group

Supports:
  - Full-row deduplication (all columns identical)
  - Subset deduplication (configurable key columns)
  - Composite key deduplication (multiple columns together)

Priority: 20 — runs after null handling so dedup keys are filled first.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.cleaning.base_cleaner import BaseCleaningRule
from app.cleaning.models import CleaningAction


class DeduplicationHandler(BaseCleaningRule):
    """Removes duplicate rows using configurable key and strategy."""

    rule_name = "DeduplicationHandler"
    rule_category = "duplicate"
    priority = 20

    def __init__(
        self,
        key_columns: list[str] | None = None,   # None = all columns
        keep_strategy: str = "keep_first",       # keep_first | keep_last | drop_all
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.key_columns = [c.lower() for c in (key_columns or [])]
        self.keep_strategy = keep_strategy.lower()

    def clean(
        self, df: pd.DataFrame, dataset_type: str
    ) -> tuple[pd.DataFrame, list[CleaningAction]]:
        actions: list[CleaningAction] = []
        if df.empty:
            return df, actions

        col_lower = {c.lower(): c for c in df.columns}

        # Resolve key columns to actual column names
        if self.key_columns:
            subset = [col_lower[k] for k in self.key_columns if k in col_lower]
        else:
            subset = None  # use all columns

        # Determine keep parameter
        keep_map = {
            "keep_first": "first",
            "keep_last":  "last",
            "drop_all":   False,
        }
        keep = keep_map.get(self.keep_strategy, "first")

        # Identify duplicate mask
        dup_mask = df.duplicated(subset=subset, keep=keep)
        dup_indices = df.index[dup_mask].tolist()

        if not dup_indices:
            return df, actions

        # Record each dropped row
        for idx in dup_indices:
            key_vals = (
                {k: str(df.at[idx, col_lower[k]]) for k in self.key_columns if k in col_lower}
                if self.key_columns else {}
            )
            actions.append(self._action(
                rule_code="DUP_001",
                field_name=None,
                row_index=int(idx),
                original_value=str(key_vals) if key_vals else "<duplicate row>",
                cleaned_value=None,
                action_type="remove_duplicate",
                reason=(
                    f"Duplicate row removed (strategy={self.keep_strategy}). "
                    f"Keys: {key_vals or 'all columns matched'}"
                ),
            ))

        result = df[~dup_mask].copy().reset_index(drop=True)
        return result, actions
