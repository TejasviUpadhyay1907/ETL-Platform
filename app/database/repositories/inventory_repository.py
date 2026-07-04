"""
InventoryRepository — database operations for the Inventory model.
"""

import uuid
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.database.models.operational.inventory import Inventory
from app.database.repositories.base_repository import BaseRepository
from app.logging.logger import get_logger

logger = get_logger(__name__)


class InventoryRepository(BaseRepository[Inventory]):
    """Repository for Inventory CRUD and query operations."""

    model_class = Inventory

    def get_by_product_warehouse(
        self, product_id: uuid.UUID, warehouse_id: str
    ) -> Inventory | None:
        """Find the inventory record for a specific product at a specific warehouse."""
        stmt = select(Inventory).where(
            Inventory.product_id == product_id,
            Inventory.warehouse_id == warehouse_id,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_product(self, product_id: uuid.UUID) -> list[Inventory]:
        """Return all inventory records for a product across all warehouses."""
        stmt = (
            select(Inventory)
            .where(Inventory.product_id == product_id)
            .order_by(Inventory.warehouse_id)
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_low_stock(self, warehouse_id: str | None = None) -> list[Inventory]:
        """Return inventory records where quantity_on_hand <= reorder_point."""
        stmt = select(Inventory).where(
            Inventory.quantity_on_hand <= Inventory.reorder_point
        )
        if warehouse_id:
            stmt = stmt.where(Inventory.warehouse_id == warehouse_id)
        stmt = stmt.order_by(Inventory.quantity_on_hand)
        return list(self.session.execute(stmt).scalars().all())

    def get_by_warehouse(
        self, warehouse_id: str, limit: int = 100, offset: int = 0
    ) -> list[Inventory]:
        """Return all inventory records at a warehouse."""
        stmt = (
            select(Inventory)
            .where(Inventory.warehouse_id == warehouse_id)
            .order_by(Inventory.product_id)
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_total_stock_value(self, warehouse_id: str | None = None) -> float:
        """Calculate total inventory value (sum of quantity * unit_cost)."""
        stmt = select(
            func.sum(Inventory.quantity_on_hand * Inventory.unit_cost)
        )
        if warehouse_id:
            stmt = stmt.where(Inventory.warehouse_id == warehouse_id)
        result = self.session.execute(stmt).scalar_one_or_none()
        return float(result or 0)

    def bulk_upsert(self, inventory_data: list[dict[str, Any]]) -> int:
        """Bulk upsert on (product_id, warehouse_id) composite key."""
        from sqlalchemy.dialects.postgresql import insert

        if not inventory_data:
            return 0
        stmt = insert(Inventory).values(inventory_data)
        update_cols = {
            c.name: c
            for c in stmt.excluded
            if c.name not in ("id", "product_id", "warehouse_id", "created_at", "created_by")
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_inventory_product_warehouse",
            set_=update_cols,
        )
        result = self.session.execute(stmt)
        self.session.flush()
        logger.info(f"Bulk upserted {result.rowcount} inventory records")
        return result.rowcount
