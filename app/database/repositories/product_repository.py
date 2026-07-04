"""
ProductRepository — database operations for the Product model.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database.models.operational.products import Product
from app.database.repositories.base_repository import BaseRepository
from app.logging.logger import get_logger

logger = get_logger(__name__)


class ProductRepository(BaseRepository[Product]):
    """Repository for Product CRUD and query operations."""

    model_class = Product

    def get_by_sku(self, sku: str) -> Product | None:
        """Find a product by its SKU (case-insensitive)."""
        stmt = select(Product).where(
            func.upper(Product.sku) == sku.upper().strip(),
            Product.is_deleted.is_(False),
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_category(
        self,
        category: str,
        status: str = "active",
        limit: int = 100,
        offset: int = 0,
    ) -> list[Product]:
        """Return products in a given category."""
        stmt = (
            select(Product)
            .where(
                Product.category == category,
                Product.status == status,
                Product.is_deleted.is_(False),
            )
            .order_by(Product.product_name)
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.execute(stmt).scalars().all())

    def search(self, query: str, limit: int = 20, offset: int = 0) -> list[Product]:
        """Search products by name, SKU, or brand."""
        term = f"%{query.lower()}%"
        stmt = (
            select(Product)
            .where(
                Product.is_deleted.is_(False),
                or_(
                    func.lower(Product.product_name).like(term),
                    func.lower(Product.sku).like(term),
                    func.lower(Product.brand).like(term),
                ),
            )
            .order_by(Product.product_name)
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_by_supplier(self, supplier_id: Any, limit: int = 100, offset: int = 0) -> list[Product]:
        """Return all products from a specific supplier."""
        stmt = (
            select(Product)
            .where(
                Product.supplier_id == supplier_id,
                Product.is_deleted.is_(False),
            )
            .order_by(Product.product_name)
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.execute(stmt).scalars().all())

    def count_by_category(self) -> dict[str, int]:
        """Return product counts grouped by category."""
        stmt = (
            select(Product.category, func.count().label("count"))
            .where(Product.is_deleted.is_(False))
            .group_by(Product.category)
            .order_by(func.count().desc())
        )
        return {row.category: row.count for row in self.session.execute(stmt).all()}

    def bulk_upsert(self, product_data: list[dict[str, Any]]) -> int:
        """Bulk upsert products on SKU conflict."""
        from sqlalchemy.dialects.postgresql import insert

        if not product_data:
            return 0
        stmt = insert(Product).values(product_data)
        update_cols = {
            c.name: c
            for c in stmt.excluded
            if c.name not in ("id", "sku", "created_at", "created_by")
        }
        stmt = stmt.on_conflict_do_update(index_elements=["sku"], set_=update_cols)
        result = self.session.execute(stmt)
        self.session.flush()
        logger.info(f"Bulk upserted {result.rowcount} products")
        return result.rowcount
