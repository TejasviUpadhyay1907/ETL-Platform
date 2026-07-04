"""
CleaningExecutor — runs all cleaners sequentially in priority order.

Each cleaner receives the output DataFrame of the previous one.
This enables chained cleaning where later cleaners work on already-cleaned data.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pandas as pd

from app.cleaning.models import CleaningAction
from app.cleaning.cleaning_registry import CleaningRegistry
from app.logging.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ExecutorStats:
    cleaners_executed: int = 0
    cleaners_skipped:  int = 0
    total_actions:     int = 0
    total_duration_ms: float = 0.0
    cleaner_timings:   dict[str, float] = field(default_factory=dict)


class CleaningExecutor:
    """Executes all registered cleaners sequentially."""

    def execute(
        self,
        df: pd.DataFrame,
        registry: CleaningRegistry,
        dataset_type: str,
    ) -> tuple[pd.DataFrame, list[CleaningAction], ExecutorStats]:
        """
        Run cleaners in priority order against the working DataFrame.

        Returns:
            (cleaned_df, all_actions, stats)
        """
        all_actions: list[CleaningAction] = []
        stats = ExecutorStats()
        working = df.copy()
        ordered = registry.get_ordered()

        logger.info(
            "Cleaning execution started",
            dataset_type=dataset_type,
            rows=len(working),
            cleaners=len(ordered),
        )
        total_start = time.perf_counter()

        for cleaner in ordered:
            result_df, actions, duration_ms = cleaner.execute(working, dataset_type)
            working = result_df
            all_actions.extend(actions)
            stats.cleaners_executed += 1
            stats.total_actions += len(actions)
            stats.cleaner_timings[cleaner.rule_name] = round(duration_ms, 2)

            logger.debug(
                f"Cleaner {cleaner.rule_name} complete",
                actions=len(actions),
                rows_remaining=len(working),
                duration_ms=round(duration_ms, 1),
            )

        stats.total_duration_ms = (time.perf_counter() - total_start) * 1000
        logger.info(
            "Cleaning execution complete",
            dataset_type=dataset_type,
            output_rows=len(working),
            total_actions=stats.total_actions,
            duration_ms=round(stats.total_duration_ms, 1),
        )
        return working, all_actions, stats
