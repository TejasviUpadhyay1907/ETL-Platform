"""
IncrementalStrategy — load only new records based on a watermark column.

Filters the input DataFrame to rows where watermark_column > last_watermark_value,
then delegates to UpsertStrategy for the actual write.

Watermark types supported:
  - timestamp/date: filters on datetime comparison
  - integer ID:     filters on ID > last_id
  - string hash:    filters on hash not in existing hashes (future)

The last watermark value is persisted in the audit_log after each successful
incremental load so subsequent runs know where to start from.
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.loading.models import LoadBatchResult, LoadMetrics, LoadStrategy, LoadStrategyType
from app.loading.strategies.base_strategy import BaseLoadStrategy
from app.loading.strategies.upsert_strategy import UpsertStrategy
from app.logging.logger import get_logger

logger = get_logger(__name__)


class IncrementalStrategy(BaseLoadStrategy):
    """Incremental load: only insert/update records newer than the last watermark."""

    strategy_name = LoadStrategyType.INCREMENTAL

    def execute(
        self,
        df: pd.DataFrame,
        target_table: str,
        dataset_type: str,
        pipeline_run_id: str | None = None,
    ) -> tuple[LoadMetrics, list[LoadBatchResult]]:
        metrics = self._make_metrics(self.strategy_name, target_table)
        batch_results: list[LoadBatchResult] = []

        metrics.total_rows_input = len(df)
        watermark_col = self._config.watermark_column
        watermark_val = self._config.watermark_value

        if df.empty:
            return metrics, batch_results

        # Drop derived/extra columns not in the target table schema
        df = self._filter_to_table_columns(df, target_table)

        # Apply watermark filter
        filtered_df = df
        if watermark_col and watermark_val is not None:
            col_lower = {c.lower(): c for c in df.columns}
            orig_col = col_lower.get(watermark_col.lower())
            if orig_col:
                try:
                    series = df[orig_col]
                    # Try numeric comparison first
                    numeric = pd.to_numeric(series, errors="coerce")
                    if numeric.notna().any():
                        wm_num = float(watermark_val)
                        mask = numeric > wm_num
                    else:
                        # Try datetime comparison
                        dates = pd.to_datetime(series, errors="coerce")
                        wm_dt = pd.to_datetime(watermark_val)
                        mask = dates > wm_dt

                    filtered_df = df[mask].copy()
                    skipped = len(df) - len(filtered_df)
                    metrics.rows_skipped = skipped
                    logger.info(
                        f"IncrementalStrategy: filtered to {len(filtered_df)} new records "
                        f"({skipped} skipped, watermark={watermark_val})",
                        dataset_type=dataset_type,
                    )
                except Exception as exc:
                    logger.warning(
                        f"Watermark filter failed ({exc}), loading all records",
                        dataset_type=dataset_type,
                    )
                    filtered_df = df

        if filtered_df.empty:
            logger.info(
                "IncrementalStrategy: no new records to load",
                dataset_type=dataset_type,
            )
            return metrics, batch_results

        # Delegate to UpsertStrategy for the actual write
        upsert = UpsertStrategy(self._session, self._config)
        upsert_metrics, upsert_batches = upsert.execute(
            filtered_df, target_table, dataset_type, pipeline_run_id
        )

        # Merge upsert metrics into incremental metrics
        metrics.rows_inserted      = upsert_metrics.rows_inserted
        metrics.rows_updated       = upsert_metrics.rows_updated
        metrics.rows_failed        = upsert_metrics.rows_failed
        metrics.batch_count        = upsert_metrics.batch_count
        metrics.total_duration_ms  = upsert_metrics.total_duration_ms
        metrics.compute_derived()

        return metrics, upsert_batches
