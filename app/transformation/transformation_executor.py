"""
TransformationExecutor — runs all transformers in priority order.

Maintains the working DataFrame between transformers — each transformer
receives the output of the previous one. This enables sequential enrichment
where later transformers can use columns created by earlier ones.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.logging.logger import get_logger
from app.transformation.models import TransformationAction, TransformationMetrics
from app.transformation.transformer_registry import TransformationRegistry

logger = get_logger(__name__)


@dataclass
class ExecutionStats:
    transformers_executed: int = 0
    transformers_skipped:  int = 0
    total_actions:         int = 0
    total_duration_ms:     float = 0.0
    transformer_timings:   dict[str, float] = field(default_factory=dict)


class TransformationExecutor:
    """Runs all registered transformers sequentially."""

    def execute(
        self,
        df: pd.DataFrame,
        registry: TransformationRegistry,
        dataset_type: str,
    ) -> tuple[pd.DataFrame, list[TransformationAction], ExecutionStats]:
        """
        Run all transformers in order against the working DataFrame.

        Args:
            df:           Copy of cleaned_df (starting state).
            registry:     Populated TransformationRegistry.
            dataset_type: Dataset type string.

        Returns:
            (final_df, all_actions, stats)
        """
        all_actions: list[TransformationAction] = []
        stats = ExecutionStats()
        working_df = df.copy()
        ordered = registry.get_ordered()

        logger.info(
            "Transformation execution started",
            dataset_type=dataset_type,
            rows=len(working_df),
            transformers=len(ordered),
        )
        total_start = time.perf_counter()

        for transformer in ordered:
            if not transformer.enabled:
                stats.transformers_skipped += 1
                continue

            result_df, actions, duration_ms = transformer.execute(working_df, dataset_type)
            working_df = result_df
            all_actions.extend(actions)
            stats.transformers_executed += 1
            stats.total_actions += len(actions)
            stats.transformer_timings[transformer.transformer_name] = round(duration_ms, 2)

            logger.debug(
                f"Transformer {transformer.transformer_name} complete",
                actions=len(actions),
                duration_ms=round(duration_ms, 1),
                new_cols=len(result_df.columns) - len(df.columns),
            )

        stats.total_duration_ms = (time.perf_counter() - total_start) * 1000
        logger.info(
            "Transformation execution complete",
            dataset_type=dataset_type,
            output_rows=len(working_df),
            output_cols=len(working_df.columns),
            total_actions=stats.total_actions,
            duration_ms=round(stats.total_duration_ms, 1),
        )
        return working_df, all_actions, stats


def _build_metrics(
    input_df: pd.DataFrame,
    output_df: pd.DataFrame,
    actions: list[TransformationAction],
    stats: ExecutionStats,
) -> TransformationMetrics:
    """Build a TransformationMetrics from the execution results."""
    metrics = TransformationMetrics(
        total_rows_input=len(input_df),
        total_rows_output=len(output_df),
        total_actions=stats.total_actions,
        total_duration_ms=stats.total_duration_ms,
        transformers_executed=stats.transformers_executed,
        transformers_skipped=stats.transformers_skipped,
    )
    # Count actions by category
    for action in actions:
        cat = action.rule_category
        if cat == "standardization":
            metrics.columns_renamed += 1
        elif cat == "type_cast":
            metrics.columns_type_cast += 1
        elif cat == "derived":
            metrics.derived_columns_created += 1
        elif cat == "business":
            metrics.business_calcs_applied += 1
        elif cat == "lookup":
            metrics.lookup_enrichments += 1
        elif cat == "date":
            metrics.date_transforms += 1
        elif cat == "categorical":
            metrics.categorical_maps += 1
        elif cat == "feature":
            metrics.features_engineered += 1
    return metrics
