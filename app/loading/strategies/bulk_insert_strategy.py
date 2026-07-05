"""
BulkInsertStrategy — batch insert all records.

Uses pandas DataFrame.to_sql() which works on both PostgreSQL and SQLite.
Fails on primary key conflicts — use UpsertStrategy for idempotent loads.
"""

from __future__ import annotations

import time

import pandas as pd

from app.loading.models import LoadBatchResult, LoadMetrics, LoadStrategyType
from app.loading.strategies.base_strategy import BaseLoadStrategy
from app.logging.logger import get_logger

logger = get_logger(__name__)


class BulkInsertStrategy(BaseLoadStrategy):
    """Batch insert strategy — cross-dialect, fails on PK conflicts."""

    strategy_name = LoadStrategyType.BULK_INSERT

    def execute(
        self,
        df: pd.DataFrame,
        target_table: str,
        dataset_type: str,
        pipeline_run_id: str | None = None,
    ) -> tuple[LoadMetrics, list[LoadBatchResult]]:
        metrics = self._make_metrics(self.strategy_name, target_table)
        batch_results: list[LoadBatchResult] = []

        if df.empty:
            return metrics, batch_results

        # Drop derived/extra columns not in the target table schema
        df = self._filter_to_table_columns(df, target_table)

        metrics.total_rows_input = len(df)
        chunks = self._chunk_df(df)
        metrics.batch_count = len(chunks)
        total_start = time.perf_counter()

        for i, chunk in enumerate(chunks):
            batch_start = time.perf_counter()
            batch = LoadBatchResult(
                batch_number=i + 1,
                batch_size=self._config.batch_size,
                rows_attempted=len(chunk),
            )
            try:
                conn = self._session.connection()
                chunk.to_sql(
                    target_table,
                    con=conn,
                    if_exists="append",
                    index=False,
                    method="multi",
                )
                self._session.flush()
                batch.rows_inserted = len(chunk)
                metrics.rows_inserted += len(chunk)

            except Exception as exc:
                batch.rows_failed = len(chunk)
                batch.error_message = str(exc)
                metrics.rows_failed += len(chunk)
                logger.warning(f"BulkInsert batch {i+1} failed: {exc}")
                try:
                    self._session.rollback()
                except Exception:
                    pass
                if not self._config.allow_partial:
                    batch.duration_ms = (time.perf_counter() - batch_start) * 1000
                    batch_results.append(batch)
                    break

            batch.duration_ms = (time.perf_counter() - batch_start) * 1000
            batch_results.append(batch)

        metrics.total_duration_ms = (time.perf_counter() - total_start) * 1000
        metrics.compute_derived()
        return metrics, batch_results
