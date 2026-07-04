"""
AppendStrategy — always insert; never overwrite existing records.

Silently skips records that conflict with existing primary keys.
Use when you want to add new records but leave existing ones untouched.

Implementation: Uses INSERT OR IGNORE (SQLite) / INSERT ... ON CONFLICT DO NOTHING (PG).
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd

from app.loading.models import LoadBatchResult, LoadMetrics, LoadStrategyType
from app.loading.strategies.base_strategy import BaseLoadStrategy
from app.logging.logger import get_logger

logger = get_logger(__name__)


class AppendStrategy(BaseLoadStrategy):
    """Append-only strategy: inserts new records, silently skips conflicts."""

    strategy_name = LoadStrategyType.APPEND

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

        metrics.total_rows_input = len(df)
        chunks = self._chunk_df(df)
        metrics.batch_count = len(chunks)
        total_start = time.perf_counter()

        # Detect dialect for ON CONFLICT syntax
        dialect = ""
        try:
            dialect = self._session.bind.dialect.name
        except Exception:
            pass

        for i, chunk in enumerate(chunks):
            batch_start = time.perf_counter()
            batch = LoadBatchResult(
                batch_number=i + 1,
                batch_size=self._config.batch_size,
                rows_attempted=len(chunk),
            )
            try:
                records = self._df_to_records(chunk)
                if not records:
                    continue

                inserted, skipped = self._insert_ignore(records, target_table, dialect)
                batch.rows_inserted = inserted
                batch.rows_skipped  = skipped
                metrics.rows_inserted += inserted
                metrics.rows_skipped  += skipped

            except Exception as exc:
                batch.rows_failed = len(chunk)
                batch.error_message = str(exc)
                metrics.rows_failed += len(chunk)
                logger.warning(f"Append batch {i+1} failed: {exc}")
                try:
                    self._session.rollback()
                except Exception:
                    pass

            batch.duration_ms = (time.perf_counter() - batch_start) * 1000
            batch_results.append(batch)

        metrics.total_duration_ms = (time.perf_counter() - total_start) * 1000
        metrics.compute_derived()
        return metrics, batch_results

    def _insert_ignore(
        self,
        records: list[dict[str, Any]],
        target_table: str,
        dialect: str,
    ) -> tuple[int, int]:
        """Insert records, silently skipping conflicts. Returns (inserted, skipped)."""
        from sqlalchemy import text

        cols = list(records[0].keys())
        col_str = ", ".join(f'"{c}"' for c in cols)
        val_str = ", ".join(f":{c}" for c in cols)

        if dialect == "postgresql":
            stmt_str = (
                f'INSERT INTO "{target_table}" ({col_str}) VALUES ({val_str}) '
                f'ON CONFLICT DO NOTHING'
            )
        else:  # SQLite
            stmt_str = (
                f'INSERT OR IGNORE INTO "{target_table}" ({col_str}) VALUES ({val_str})'
            )

        stmt = text(stmt_str)
        conn = self._session.connection()
        result = conn.execute(stmt, records)
        self._session.flush()

        inserted = result.rowcount if result.rowcount >= 0 else len(records)
        skipped  = max(0, len(records) - inserted)
        return inserted, skipped
