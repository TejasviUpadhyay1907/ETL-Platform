"""Warehouse loading package — Stage 5 of the ETL pipeline."""
from app.loading.loader import WarehouseLoader
from app.loading.models import (
    LoadResult, LoadReport, LoadMetrics, LoadStrategy,
    LoadBatchResult, LoadStrategyType,
)
from app.loading.load_registry import LoadRegistry, get_load_registry

__all__ = [
    "WarehouseLoader",
    "LoadResult", "LoadReport", "LoadMetrics",
    "LoadStrategy", "LoadBatchResult", "LoadStrategyType",
    "LoadRegistry", "get_load_registry",
]
