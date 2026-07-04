"""
CategoricalTransformer — normalizes and maps categorical field values.

Applies:
  - Value normalization (lowercase, title case)
  - Alias mapping (e.g. "cancelled" → "canceled")
  - Category merging (e.g. "on_hold", "pending" → "awaiting")
  - Config-driven from transformations.yaml category_mappings

Priority: 45
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.transformation.base_transformer import BaseTransformer
from app.transformation.models import TransformationAction


class CategoricalTransformer(BaseTransformer):
    """Normalizes categorical column values using config-driven mappings."""

    transformer_name = "CategoricalTransformer"
    transformer_category = "categorical"
    priority = 45

    def __init__(
        self,
        # {column_name: {raw_value: normalized_value}}
        category_mappings: dict[str, dict[str, str]] | None = None,
        # {column_name: "lower"|"upper"|"title"}
        case_normalizations: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.category_mappings = {
            k.lower(): v for k, v in (category_mappings or {}).items()
        }
        self.case_normalizations = {
            k.lower(): v for k, v in (case_normalizations or {}).items()
        }

    def transform(
        self, df: pd.DataFrame, dataset_type: str
    ) -> tuple[pd.DataFrame, list[TransformationAction]]:
        actions: list[TransformationAction] = []
        result = df.copy()
        col_lower = {c.lower(): c for c in result.columns}

        # Apply explicit value mappings
        for fld_lower, mapping in self.category_mappings.items():
            orig = col_lower.get(fld_lower)
            if orig is None:
                continue
            before = result[orig].copy()
            result[orig] = result[orig].astype(str).str.strip().map(
                lambda v: mapping.get(v.lower(), v)
            )
            changed = (result[orig] != before.astype(str).str.strip()).sum()
            if changed > 0:
                actions.append(self._action(
                    "CAT_001", orig, [orig], "map",
                    f"Mapped {changed} values in '{orig}' using alias table",
                    int(changed),
                ))

        # Apply case normalization
        for fld_lower, case in self.case_normalizations.items():
            orig = col_lower.get(fld_lower)
            if orig is None:
                continue
            s = result[orig].astype(str).str.strip()
            if case == "lower":
                result[orig] = s.str.lower()
            elif case == "upper":
                result[orig] = s.str.upper()
            elif case == "title":
                result[orig] = s.str.title()
            actions.append(self._action(
                "CAT_002", orig, [orig], "normalize",
                f"Normalized '{orig}' to {case} case",
                len(result),
            ))

        return result, actions
