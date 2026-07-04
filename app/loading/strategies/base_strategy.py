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
