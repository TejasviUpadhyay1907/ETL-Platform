"""
OrderRepository — database operations for Order and OrderItem models.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, joinedload

from app.database.models.operational.orders import Order, OrderItem
from app.database.repositories.base_repository import BaseRepository
from app.logging.logger import get_logger

logger = get_logger(__name__)


class OrderRepository(BaseRepository[Order]):
    """Repository for Order CRUD and query operations."""

    model_class = Order

    def get_by_order_number(self, order_number: str) -> Order | None:
        """Find an order by its human-readable order number."""
        stmt = select(Order).where(
            Order.order_number == order_number.strip(),
            Order.is_deleted.is_(False),
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_customer(
        self,
        customer_id: uuid.UUID,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Order]:
        """Return orders for a customer, most recent first."""
        stmt = (
            select(Order)
            .where(Order.customer_id == customer_id, Order.is_deleted.is_(False))
            .order_by(Order.order_date.desc())
            .limit(limit)
            .offset(offset)
        )
        if status:
            stmt = stmt.where(Order.status == status)
        return list(self.session.execute(stmt).scalars().all())

    def get_by_date_range(
        self,
        date_from: date,
        date_to: date,
        status: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[Order]:
        """Return orders within a date range."""
        stmt = (
            select(Order)
            .where(
                Order.order_date >= date_from,
                Order.order_date <= date_to,
                Order.is_deleted.is_(False),
            )
            .order_by(Order.order_date.desc())
            .limit(limit)
            .offset(offset)
        )
        if status:
            stmt = stmt.where(Order.status == status)
        return list(self.session.execute(stmt).scalars().all())

    def get_with_items(self, order_id: uuid.UUID) -> Order | None:
        """Fetch an order with all its line items pre-loaded (avoids N+1)."""
        stmt = (
            select(Order)
            .options(joinedload(Order.items))
            .where(Order.id == order_id, Order.is_deleted.is_(False))
        )
        return self.session.execute(stmt).unique().scalar_one_or_none()

    def get_revenue_by_date(
        self, date_from: date, date_to: date
    ) -> list[dict[str, Any]]:
        """Return daily revenue aggregates for a date range."""
        stmt = (
            select(
                Order.order_date.label("date"),
                func.count(Order.id).label("order_count"),
                func.sum(Order.order_total).label("total_revenue"),
                func.avg(Order.order_total).label("avg_order_value"),
            )
            .where(
                Order.order_date >= date_from,
                Order.order_date <= date_to,
                Order.status.notin_(["cancelled", "refunded"]),
                Order.is_deleted.is_(False),
            )
            .group_by(Order.order_date)
            .order_by(Order.order_date)
        )
        rows = self.session.execute(stmt).all()
        return [
            {
                "date": str(row.date),
                "order_count": row.order_count,
                "total_revenue": float(row.total_revenue or 0),
                "avg_order_value": float(row.avg_order_value or 0),
            }
            for row in rows
        ]

    def count_by_status(self) -> dict[str, int]:
        """Count orders grouped by status."""
        stmt = (
            select(Order.status, func.count().label("count"))
            .where(Order.is_deleted.is_(False))
            .group_by(Order.status)
        )
        return {row.status: row.count for row in self.session.execute(stmt).all()}

    def bulk_upsert(self, order_data: list[dict[str, Any]]) -> int:
        """Bulk upsert orders on order_number conflict."""
        from sqlalchemy.dialects.postgresql import insert

        if not order_data:
            return 0
        stmt = insert(Order).values(order_data)
        update_cols = {
            c.name: c
            for c in stmt.excluded
            if c.name not in ("id", "order_number", "created_at", "created_by")
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["order_number"],
            set_=update_cols,
        )
        result = self.session.execute(stmt)
        self.session.flush()
        logger.info(f"Bulk upserted {result.rowcount} orders")
        return result.rowcount
