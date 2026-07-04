"""
BaseCleaningRule — abstract interface all cleaning strategies implement.

Strategy Pattern: the CleaningExecutor works against this interface only.
Each concrete cleaner is independent, testable, and swappable.

Design:
- clean() receives the working DataFrame and returns a NEW DataFrame plus
  a list of CleaningAction objects recording every modification made
- Cleaners work on COPIES — the original DataFrame is never mutated
- Cleaners are stateless between calls
- priority controls execution order (lower = runs first)
- enabled/disabled is controlled by the registry
"""

from __future__ import annotations

import abc
import time
from typing import Any

import pandas as pd

from app.cleaning.models import CleaningAction


class BaseCleaningRule(abc.ABC):
    """Abstract base class for all cleaning strategy implementations."""

    rule_name: str = "BaseCleaningRule"
    rule_category: str = "base"
    priority: int = 100
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
    def clean(
        self,
        df: pd.DataFrame,
        dataset_type: str,
    ) -> tuple[pd.DataFrame, list[CleaningAction]]:
        """
        Apply this cleaning strategy to the DataFrame.

        Args:
            df:           Working DataFrame (copy of validated_df).
            dataset_type: Dataset type string for config lookup.

        Returns:
            (cleaned_df, actions)
            - cleaned_df: DataFrame with cleaning applied (may be a new df)
            - actions:    List of CleaningAction for every change made
        """

    def execute(
        self,
        df: pd.DataFrame,
        dataset_type: str,
    ) -> tuple[pd.DataFrame, list[CleaningAction], float]:
        """Execute with timing. Returns (df, actions, duration_ms)."""
        if not self.enabled:
            return df, [], 0.0
        start = time.perf_counter()
        try:
            result_df, actions = self.clean(df, dataset_type)
        except Exception as exc:
            from app.logging.logger import get_logger
            get_logger(__name__).error(
                f"Cleaner {self.rule_name} failed: {exc}", exc_info=True
            )
            return df, [], 0.0
        return result_df, actions, (time.perf_counter() - start) * 1000

    def _action(
        self,
        rule_code: str,
        field_name: str | None,
        row_index: int | None,
        original_value: Any,
        cleaned_value: Any,
        action_type: str,
        reason: str,
        confidence: float = 1.0,
    ) -> CleaningAction:
        return CleaningAction(
            rule_code=rule_code,
            rule_category=self.rule_category,
            field_name=field_name,
            row_index=row_index,
            original_value=original_value,
            cleaned_value=cleaned_value,
            action_type=action_type,
            reason=reason,
            confidence=confidence,
            cleaning_rule_name=self.rule_name,
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(priority={self.priority}, enabled={self.enabled})"
