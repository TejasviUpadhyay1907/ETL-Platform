"""
DerivedFieldCalculator — standalone expression evaluator.

Wraps DerivedColumnTransformer for use as a utility outside the pipeline.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.transformation.transformers.derived_column_transformer import DerivedColumnTransformer


def compute_derived_fields(
    df: pd.DataFrame,
    derived_fields: list[dict[str, Any]],
    dataset_type: str = "unknown",
) -> pd.DataFrame:
    """
    Apply derived field expressions and return the enriched DataFrame.

    Args:
        df:             Input DataFrame.
        derived_fields: List of {name, expression, description} dicts.
        dataset_type:   Used for rule_code naming.

    Returns:
        New DataFrame with derived columns added.
    """
    transformer = DerivedColumnTransformer(derived_fields=derived_fields)
    result, _ = transformer.transform(df, dataset_type)
    return result
