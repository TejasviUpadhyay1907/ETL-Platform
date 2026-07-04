"""
FieldMapper — standalone utility for column renaming.

Used by the TransformationEngine to apply field_mappings from config.
Also exposed as a standalone tool for direct use in tests and scripts.
"""

from __future__ import annotations

import pandas as pd


def apply_field_mappings(
    df: pd.DataFrame,
    field_mappings: dict[str, str],
) -> tuple[pd.DataFrame, dict[str, str]]:
    """
    Rename DataFrame columns using a source → target mapping dict.

    Case-insensitive source matching.

    Returns:
        (renamed_df, applied_renames) where applied_renames is {old: new}
    """
    col_lower = {c.lower(): c for c in df.columns}
    rename_map: dict[str, str] = {}

    for src, tgt in field_mappings.items():
        orig = col_lower.get(src.lower())
        if orig and orig != tgt:
            rename_map[orig] = tgt

    if rename_map:
        return df.rename(columns=rename_map), rename_map
    return df, {}
