"""
StandardizationTransformer — column renaming, type casting, name normalization.

Responsibilities:
  - Rename columns using field_mappings from transformations.yaml
  - Convert column names to snake_case
  - Remove illegal characters from column names
  - Cast columns to their target data types (string → Decimal, date, bool)

Priority: 10 (runs first — all subsequent transformers see the renamed columns)
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from app.transformation.base_transformer import BaseTransformer
from app.transformation.models import TransformationAction


class StandardizationTransformer(BaseTransformer):
    """Renames columns and standardizes column naming conventions."""

    transformer_name = "StandardizationTransformer"
    transformer_category = "standardization"
    priority = 10

    def __init__(
        self,
        field_mappings: dict[str, str] | None = None,
        normalize_names: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        # source_name → target_name (both stored as-is from config)
        self.field_mappings: dict[str, str] = field_mappings or {}
        self.normalize_names = normalize_names

    def transform(
        self, df: pd.DataFrame, dataset_type: str
    ) -> tuple[pd.DataFrame, list[TransformationAction]]:
        actions: list[TransformationAction] = []
        result = df.copy()

        # Step 1: Apply explicit field mappings (source → target)
        rename_map: dict[str, str] = {}
        col_lower = {c.lower(): c for c in result.columns}

        for src, tgt in self.field_mappings.items():
            orig = col_lower.get(src.lower())
            if orig and orig != tgt:
                rename_map[orig] = tgt

        if rename_map:
            result = result.rename(columns=rename_map)
            for old, new in rename_map.items():
                actions.append(self._action(
                    rule_code="FM_001",
                    column_name=new,
                    source_columns=[old],
                    transformation_type="rename",
                    description=f"Renamed column '{old}' → '{new}'",
                    rows_affected=len(result),
                ))

        # Step 2: Normalize remaining column names to snake_case
        if self.normalize_names:
            norm_map: dict[str, str] = {}
            for col in result.columns:
                normalized = _to_snake_case(col)
                if normalized != col:
                    norm_map[col] = normalized

            if norm_map:
                result = result.rename(columns=norm_map)
                for old, new in norm_map.items():
                    actions.append(self._action(
                        rule_code="FM_002",
                        column_name=new,
                        source_columns=[old],
                        transformation_type="normalize",
                        description=f"Normalized column name '{old}' → '{new}'",
                        rows_affected=len(result),
                    ))

        return result, actions


def _to_snake_case(name: str) -> str:
    """Convert a column name to snake_case, removing illegal characters."""
    # Insert underscore before capitals preceded by lowercase
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    # Replace spaces, hyphens, dots with underscores
    s = re.sub(r"[\s\-\.]+", "_", s)
    # Remove characters that are not word chars or underscore
    s = re.sub(r"[^\w]", "", s)
    return s.lower().strip("_")
