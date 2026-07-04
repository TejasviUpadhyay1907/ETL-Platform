"""
BaseTransformer — abstract interface all transformation strategies implement.

Strategy Pattern: the TransformationExecutor works against this interface only.
Each concrete transformer is an independent, swappable strategy.

Design:
- transform() receives the working DataFrame and returns a NEW DataFrame
  (or the same df if no structural changes are made) plus a list of actions
- Transformers MUST NOT use in-place mutation that would affect the caller's copy
- Each transformer is responsible for one category of transformation
- Transformers are stateless between calls (safe for reuse)
- priority controls execution order (lower runs first)
- enabled/skip logic is handled by the registry, not the transformer
"""

from __future__ import annotations

import abc
import time
from typing import Any

import pandas as pd

from app.transformation.models import TransformationAction


class BaseTransformer(abc.ABC):
    """Abstract base class for all transformation strategies."""

    # Override in subclasses
    transformer_name: str = "BaseTransformer"
    transformer_category: str = "base"
    priority: int = 100   # lower = runs earlier
    enabled: bool = True

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        priority: int | None = None,
        enabled: bool = True,
    ) -> None:
        self.config: dict[str, Any] = config or {}
        if priority is not None:
            self.priority = priority
        self.enabled = enabled

    @abc.abstractmethod
    def transform(
        self,
        df: pd.DataFrame,
        dataset_type: str,
    ) -> tuple[pd.DataFrame, list[TransformationAction]]:
        """
        Apply this transformation to the DataFrame.

        Args:
            df:           Working DataFrame (copy of cleaned_df).
                          May be modified in place OR returned as a new DataFrame.
            dataset_type: Dataset type string for config lookup.

        Returns:
            (transformed_df, actions)
            - transformed_df: DataFrame with transformations applied
            - actions: List of TransformationAction describing what was done
        """

    def execute(
        self,
        df: pd.DataFrame,
        dataset_type: str,
    ) -> tuple[pd.DataFrame, list[TransformationAction], float]:
        """
        Execute with timing. Safe wrapper around transform().

        Returns:
            (df, actions, duration_ms)
        """
        if not self.enabled:
            return df, [], 0.0

        start = time.perf_counter()
        try:
            result_df, actions = self.transform(df, dataset_type)
        except Exception as exc:
            from app.logging.logger import get_logger
            get_logger(__name__).error(
                f"Transformer {self.transformer_name} failed: {exc}",
                exc_info=True,
            )
            return df, [], 0.0
        duration_ms = (time.perf_counter() - start) * 1000
        return result_df, actions, duration_ms

    def _action(
        self,
        rule_code: str,
        column_name: str,
        source_columns: list[str],
        transformation_type: str,
        description: str,
        rows_affected: int = 0,
        execution_ms: float = 0.0,
    ) -> TransformationAction:
        """Convenience factory for TransformationAction."""
        return TransformationAction(
            rule_code=rule_code,
            rule_category=self.transformer_category,
            column_name=column_name,
            source_columns=source_columns,
            transformation_type=transformation_type,
            description=description,
            rows_affected=rows_affected,
            execution_ms=execution_ms,
        )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"priority={self.priority}, enabled={self.enabled})"
        )
