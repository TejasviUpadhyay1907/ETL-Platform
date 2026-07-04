"""
BusinessRuleCleaner — applies YAML-driven value normalizations.

Examples from cleaning.yaml:
  - field: status
    rules:
      - match: ["ACTIVE", "Active", "active", "A"]
        replace: "active"
      - match: ["PAID", "Paid", "paid"]
        replace: "paid"

This cleaner standardizes inconsistent representations of the same value.
It runs after string normalization so case variants are already collapsed.

Priority: 50
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.cleaning.base_cleaner import BaseCleaningRule
from app.cleaning.models import CleaningAction


class BusinessRuleCleaner(BaseCleaningRule):
    """Applies explicit value normalization rules loaded from YAML."""

    rule_name = "BusinessRuleCleaner"
    rule_category = "business"
    priority = 50

    def __init__(
        self,
        field_rules: dict[str, list[dict[str, Any]]] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Args:
            field_rules: {column_lower: [{match: [...], replace: val}, ...]}
        """
        super().__init__(**kwargs)
        self.field_rules: dict[str, list[dict[str, Any]]] = {
            k.lower(): v for k, v in (field_rules or {}).items()
        }

    def clean(
        self, df: pd.DataFrame, dataset_type: str
    ) -> tuple[pd.DataFrame, list[CleaningAction]]:
        actions: list[CleaningAction] = []
        result = df.copy()
        col_lower = {c.lower(): c for c in result.columns}

        for fld_lower, rules in self.field_rules.items():
            col = col_lower.get(fld_lower)
            if col is None:
                continue

            for rule in rules:
                match_vals = {str(v).lower() for v in rule.get("match", [])}
                replace_val = rule.get("replace", "")
                rule_code = rule.get("rule_code", "BIZ_001")
                description = rule.get("description", f"Business rule: {match_vals} → {replace_val}")

                for idx in result.index:
                    current = str(result.at[idx, col])
                    if current.lower() in match_vals and current != replace_val:
                        result.at[idx, col] = replace_val
                        actions.append(self._action(
                            rule_code, col, int(idx), current, replace_val,
                            "map_category",
                            description,
                        ))

        return result, actions
