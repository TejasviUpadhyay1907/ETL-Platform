"""
LoadRegistry — maps dataset types to their default load strategy and target table.

Factory Pattern: WarehouseLoader asks the registry which strategy to use
for a given dataset_type and receives a configured strategy instance.

Adding a new dataset type requires only adding an entry here.
No engine changes needed.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.loading.models import LoadStrategy, LoadStrategyType
from app.logging.logger import get_logger

logger = get_logger(__name__)

# ── Default configuration per dataset type ─────────────────────────────────

_DATASET_CONFIG: dict[str, dict[str, Any]] = {
    "customers": {
        "target_table":    "customers",
        "strategy_type":   LoadStrategyType.UPSERT,
        "conflict_columns": ["email"],
        "batch_size":      500,
    },
    "suppliers": {
        "target_table":    "suppliers",
        "strategy_type":   LoadStrategyType.UPSERT,
        "conflict_columns": ["supplier_code"],
        "batch_size":      200,
    },
    "products": {
        "target_table":    "products",
        "strategy_type":   LoadStrategyType.UPSERT,
        "conflict_columns": ["sku"],
        "batch_size":      500,
    },
    "inventory": {
        "target_table":    "inventory",
        "strategy_type":   LoadStrategyType.UPSERT,
        "conflict_columns": ["product_id", "warehouse_id"],
        "batch_size":      1000,
    },
    "orders": {
        "target_table":    "orders",
        "strategy_type":   LoadStrategyType.UPSERT,
        "conflict_columns": ["order_number"],
        "batch_size":      1000,
    },
    "payments": {
        "target_table":    "payments",
        "strategy_type":   LoadStrategyType.APPEND,
        "conflict_columns": [],
        "batch_size":      1000,
    },
}


class LoadRegistry:
    """Resolves load strategy and target table for a dataset type."""

    def __init__(self) -> None:
        self._overrides: dict[str, dict[str, Any]] = {}

    def get_strategy(
        self,
        session: Session,
        dataset_type: str,
        strategy_override: str | None = None,
        batch_size_override: int | None = None,
    ) -> tuple["BaseLoadStrategy", str]:  # type: ignore[name-defined]
        """
        Return (strategy_instance, target_table) for a dataset type.

        Args:
            session:           SQLAlchemy session.
            dataset_type:      e.g. 'orders'.
            strategy_override: Override the default strategy type.
            batch_size_override: Override the default batch size.

        Returns:
            (BaseLoadStrategy instance, target_table name)
        """
        from app.loading.strategies.base_strategy import BaseLoadStrategy

        cfg = {**_DATASET_CONFIG.get(dataset_type, {})}
        cfg.update(self._overrides.get(dataset_type, {}))

        # Apply overrides
        if strategy_override:
            cfg["strategy_type"] = strategy_override
        if batch_size_override:
            cfg["batch_size"] = batch_size_override

        # Default fallback for unknown dataset types
        if not cfg:
            cfg = {
                "target_table":    dataset_type,
                "strategy_type":   LoadStrategyType.UPSERT,
                "conflict_columns": [],
                "batch_size":      1000,
            }

        strategy_cfg = LoadStrategy(
            strategy_type=cfg.get("strategy_type", LoadStrategyType.UPSERT),
            batch_size=cfg.get("batch_size", 1000),
            conflict_columns=cfg.get("conflict_columns", []),
        )
        target_table = cfg.get("target_table", dataset_type)
        strategy_instance = self._build_strategy(session, strategy_cfg)

        logger.debug(
            f"LoadRegistry: {dataset_type} → {strategy_instance.strategy_name} → {target_table}"
        )
        return strategy_instance, target_table

    def register_override(self, dataset_type: str, config: dict[str, Any]) -> None:
        """Override the default config for a dataset type (for testing / custom pipelines)."""
        self._overrides[dataset_type] = config

    @staticmethod
    def _build_strategy(session: Session, cfg: LoadStrategy):
        from app.loading.strategies.upsert_strategy import UpsertStrategy
        from app.loading.strategies.bulk_insert_strategy import BulkInsertStrategy
        from app.loading.strategies.append_strategy import AppendStrategy
        from app.loading.strategies.replace_strategy import ReplaceStrategy
        from app.loading.strategies.incremental_strategy import IncrementalStrategy

        mapping = {
            LoadStrategyType.UPSERT:      UpsertStrategy,
            LoadStrategyType.BULK_INSERT: BulkInsertStrategy,
            LoadStrategyType.APPEND:      AppendStrategy,
            LoadStrategyType.REPLACE:     ReplaceStrategy,
            LoadStrategyType.INCREMENTAL: IncrementalStrategy,
        }
        cls = mapping.get(cfg.strategy_type, UpsertStrategy)
        return cls(session, cfg)


# Module-level singleton
_registry: LoadRegistry | None = None


def get_load_registry() -> LoadRegistry:
    global _registry
    if _registry is None:
        _registry = LoadRegistry()
    return _registry
