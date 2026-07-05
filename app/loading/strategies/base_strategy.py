"""
BaseLoadStrategy — abstract interface all loading strategies implement.

Strategy Pattern: WarehouseLoader works against this interface only.
Each concrete strategy is independently testable.

Design:
- execute() receives a DataFrame and writes it to the target table
- Returns (LoadReport, list[LoadBatchResult]) — never raises to the caller
- All strategies are stateless between calls
"""

from __future__ import annotations

import abc
import time
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.loading.models import LoadBatchResult, LoadMetrics, LoadReport, LoadStrategy
from app.logging.logger import get_logger

logger = get_logger(__name__)


class BaseLoadStrategy(abc.ABC):
    """Abstract base for all warehouse loading strategies."""

    strategy_name: str = "BaseStrategy"

    def __init__(self, session: Session, strategy_config: LoadStrategy) -> None:
        self._session = session
        self._config = strategy_config

    @abc.abstractmethod
    def execute(
        self,
        df: pd.DataFrame,
        target_table: str,
        dataset_type: str,
        pipeline_run_id: str | None = None,
    ) -> tuple[LoadMetrics, list[LoadBatchResult]]:
        """
        Write the DataFrame to target_table.

        Args:
            df:              Transformed DataFrame from the pipeline.
            target_table:    Name of the target database table.
            dataset_type:    Dataset type string for repository dispatch.
            pipeline_run_id: For idempotency tracking.

        Returns:
            (metrics, batch_results)
        """

    def _chunk_df(self, df: pd.DataFrame) -> list[pd.DataFrame]:
        """Split DataFrame into batches of config.batch_size rows."""
        size = self._config.batch_size
        return [df.iloc[i: i + size] for i in range(0, len(df), size)]

    def _make_metrics(self, strategy_type: str, target_table: str) -> LoadMetrics:
        m = LoadMetrics(strategy_used=strategy_type, target_table=target_table)
        return m

    def _df_to_records(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Convert DataFrame to list of dicts, handling NaN → None."""
        import math
        records = df.where(df.notna(), other=None).to_dict(orient="records")
        # Replace float NaN that survived the where() call
        clean: list[dict[str, Any]] = []
        for row in records:
            clean.append({
                k: (None if (isinstance(v, float) and math.isnan(v)) else v)
                for k, v in row.items()
            })
        return clean

    def _filter_to_table_columns(self, df: pd.DataFrame, target_table: str) -> pd.DataFrame:
        """
        Drop any DataFrame columns that do not exist in the target database table.

        The transformation stage adds derived columns (order_year, is_high_value, etc.)
        that have no corresponding column in the warehouse schema. Passing them to
        the DB causes 'Unconsumed column names' errors. This method strips them first.

        Works for both PostgreSQL and SQLite.
        """
        try:
            from sqlalchemy import inspect as _inspect
            inspector = _inspect(self._session.bind)
            db_cols = {col["name"] for col in inspector.get_columns(target_table)}
            if not db_cols:
                return df  # Table not found — pass through unchanged
            df_cols = set(df.columns)
            valid_cols = [c for c in df.columns if c in db_cols]
            dropped   = df_cols - db_cols
            if dropped:
                logger.debug(
                    f"Dropped {len(dropped)} derived columns before loading into '{target_table}': "
                    f"{sorted(dropped)[:10]}{'…' if len(dropped) > 10 else ''}",
                )
            return df[valid_cols] if valid_cols else df
        except Exception as exc:
            logger.warning(f"Column filtering skipped ({exc}) — using full DataFrame")
            return df
