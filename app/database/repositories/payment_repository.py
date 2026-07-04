"""
PaymentRepository — database operations for the Payment model.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models.operational.payments import Payment
from app.database.repositories.base_repository import BaseRepository
from app.logging.logger import get_logger

logger = get_logger(__name__)


class PaymentRepository(BaseRepository[Payment]):
    """Repository for Payment CRUD and query operations."""

    model_class = Payment

    def get_by_gateway_reference(self, gateway_reference: str) -> Payment | None:
        """Find a payment by its payment gateway transaction ID."""
        stmt = select(Payment).where(
            Payment.gateway_reference == gateway_reference.strip()
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_order(self, order_id: uuid.UUID) -> list[Payment]:
        """Return all payment records for a specific order."""
        stmt = (
            select(Payment)
            .where(Payment.order_id == order_id)
            .order_by(Payment.payment_date.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_by_date_range(
        self,
        date_from: date,
        date_to: date,
        method: str | None = None,
        status: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[Payment]:
        """Return payments within a date range with optional filters."""
        stmt = (
            select(Payment)
            .where(
                Payment.payment_date >= date_from,
                Payment.payment_date <= date_to,
            )
            .order_by(Payment.payment_date.desc())
            .limit(limit)
            .offset(offset)
        )
        if method:
            stmt = stmt.where(Payment.payment_method == method)
        if status:
            stmt = stmt.where(Payment.transaction_status == status)
        return list(self.session.execute(stmt).scalars().all())

    def get_revenue_by_method(
        self, date_from: date, date_to: date
    ) -> list[dict[str, Any]]:
        """Aggregate payment revenue grouped by payment method."""
        stmt = (
            select(
                Payment.payment_method,
                func.count(Payment.id).label("transaction_count"),
                func.sum(Payment.amount).label("total_amount"),
            )
            .where(
                Payment.payment_date >= date_from,
                Payment.payment_date <= date_to,
                Payment.transaction_type == "payment",
                Payment.transaction_status == "settled",
            )
            .group_by(Payment.payment_method)
            .order_by(func.sum(Payment.amount).desc())
        )
        rows = self.session.execute(stmt).all()
        return [
            {
                "payment_method": row.payment_method,
                "transaction_count": row.transaction_count,
                "total_amount": float(row.total_amount or 0),
            }
            for row in rows
        ]

    def get_total_collected(self, order_id: uuid.UUID) -> Decimal:
        """Return total amount collected for an order across all settled payments."""
        stmt = select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.order_id == order_id,
            Payment.transaction_type == "payment",
            Payment.transaction_status == "settled",
        )
        result = self.session.execute(stmt).scalar_one()
        return Decimal(str(result))

    def bulk_upsert(self, payment_data: list[dict[str, Any]]) -> int:
        """Bulk insert payments. Payments are generally not updated after creation."""
        from sqlalchemy.dialects.postgresql import insert

        if not payment_data:
            return 0
        stmt = insert(Payment).values(payment_data)
        # Only update mutable fields (status can change after initial insert)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={"transaction_status": stmt.excluded.transaction_status},
        )
        result = self.session.execute(stmt)
        self.session.flush()
        logger.info(f"Bulk upserted {result.rowcount} payments")
        return result.rowcount
