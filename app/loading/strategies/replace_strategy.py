"""
ReplaceStrategy — truncate target table then reload all records.

Transactional: the DELETE and INSERT happen in the same transaction.
If the INSERT fails, the DELETE is rolled back and the table is preserved.

Use for:
- Daily full refreshes of reference tables
- Replacing a partition
- Small tables where a full reload is acceptable

WARNING: All existing records are deleted. Use only when the full dataset
is always available in the pipeline.
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
from sqlalchemy import text

from app.loading.models import LoadBatchResult, LoadMetrics, LoadStrategyType
from app.loading.strategies.base_strategy import BaseLoadStrategy
from app.logging.logger import get_logger

logger = get_logger(__name__)


class ReplaceStrategy(BaseLoadStrategy):
    """Replace strategy: DELETE all + INSERT all within a single transaction."""

    strategy_name = LoadStrategyType.REPLACE

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
        total_start = time.perf_counter()

        try:
            conn = self._session.connection()

            # Step 1: Delete all existing records
            delete_result = conn.execute(text(f'DELETE FROM "{target_table}"'))
            deleted_count = delete_result.rowcount
            logger.info(
                f"ReplaceStrategy: deleted {deleted_count} existing rows from '{target_table}'"
            )

            if df.empty:
                self._session.flush()
                metrics.total_duration_ms = (time.perf_counter() - total_start) * 1000
                return metrics, batch_results

            # Step 2: Insert all records in batches
            chunks = self._chunk_df(df)
            metrics.batch_count = len(chunks)

            for i, chunk in enumerate(chunks):
                batch_start = time.perf_counter()
                batch = LoadBatchResult(
                    batch_number=i + 1,
                    batch_size=self._config.batch_size,
                    rows_attempted=len(chunk),
                )
                records = self._df_to_records(chunk)
                if records:
                    cols = list(records[0].keys())
                    col_str = ", ".join(f'"{c}"' for c in cols)
                    val_str = ", ".join(f":{c}" for c in cols)
                    stmt = text(
                        f'INSERT INTO "{target_table}" ({col_str}) VALUES ({val_str})'
                    )
                    conn.execute(stmt, records)
                    batch.rows_inserted = len(chunk)
                    metrics.rows_inserted += len(chunk)

                batch.duration_ms = (time.perf_counter() - batch_start) * 1000
                batch_results.append(batch)

            self._session.flush()
            logger.info(
                f"ReplaceStrategy: inserted {metrics.rows_inserted} rows into '{target_table}'"
            )

        except Exception as exc:
            metrics.rows_failed = len(df)
            try:
                self._session.rollback()
            except Exception:
                pass
            logger.error(
                f"ReplaceStrategy failed for '{target_table}': {exc}",
                exc_info=True,
            )
            batch_results.append(LoadBatchResult(
                batch_number=1,
                batch_size=len(df),
                rows_attempted=len(df),
                rows_failed=len(df),
                error_message=str(exc),
            ))

        metrics.total_duration_ms = (time.perf_counter() - total_start) * 1000
        metrics.compute_derived()
        return metrics, batch_results
