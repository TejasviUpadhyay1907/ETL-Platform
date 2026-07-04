"""
CategoricalCleaner — normalizes categorical field values.

Operations per-field from cleaning.yaml:
  string_case: lower|upper|title    — case normalization
  alias_map: {raw: normalized}       — explicit value remapping
  unknown_strategy: flag|drop|keep   — handle values not in allowed list
  allowed_values: [...]              — set of valid category values

Priority: 45
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.cleaning.base_cleaner import BaseCleaningRule
from app.cleaning.models import CleaningAction


class CategoricalCleaner(BaseCleaningRule):
    """Normalizes categorical columns using YAML-driven alias maps and case rules."""

    rule_name = "CategoricalCleaner"
    rule_category = "categorical"
    priority = 45

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
            col = col_lower.get(fld_lower)
            if col is None:
                continue

            series = result[col].astype(str).str.strip()
            before = series.copy()

            # Case normalization
            case = cfg.get("string_case", "")
            if case == "lower":
                series = series.str.lower()
            elif case == "upper":
                series = series.str.upper()
            elif case == "title":
                series = series.str.title()

            # Alias mapping (raw → canonical)
            alias_map: dict[str, str] = {
                str(k).lower(): str(v)
                for k, v in cfg.get("alias_map", {}).items()
            }
            if alias_map:
                series = series.apply(
                    lambda v: alias_map.get(v.lower(), v)
                )

            # Record changes
            changed = series != before
            for idx in result.index[changed]:
                actions.append(self._action(
                    "CAT_001", col, int(idx), before.at[idx], series.at[idx],
                    "map_category",
                    f"Category normalized in '{col}'",
                ))

            result[col] = series

            # Unknown value handling
            allowed = cfg.get("allowed_values", [])
            if allowed:
                allowed_lower = {str(v).lower() for v in allowed}
                unknown_strategy = cfg.get("unknown_strategy", "keep").lower()
                default_cat = cfg.get("default_value", "unknown")

                for idx in result.index:
                    val = str(result.at[idx, col]).lower()
                    if val in ("nan", "none", ""):
                        continue
                    if val not in allowed_lower:
                        orig = result.at[idx, col]
                        if unknown_strategy == "flag":
                            result.at[idx, col] = default_cat
                            actions.append(self._action(
                                "CAT_002", col, int(idx), orig, default_cat,
                                "map_category",
                                f"Unknown category '{orig}' replaced with '{default_cat}'",
                                confidence=0.6,
                            ))
                        elif unknown_strategy == "drop":
                            rows_to_drop.add(idx)
                            actions.append(self._action(
                                "CAT_003", col, int(idx), orig, None,
                                "drop_row",
                                f"Row dropped: unknown category '{orig}' in '{col}'",
                            ))

        if rows_to_drop:
            result = result.drop(index=list(rows_to_drop)).reset_index(drop=True)

        return result, actions
