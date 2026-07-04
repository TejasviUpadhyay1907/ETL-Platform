"""
SupplierRepository — database operations for the Supplier model.
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models.operational.suppliers import Supplier
from app.database.repositories.base_repository import BaseRepository
from app.logging.logger import get_logger

logger = get_logger(__name__)


class SupplierRepository(BaseRepository[Supplier]):
    """Repository for Supplier CRUD and query operations."""

    model_class = Supplier

    def get_by_code(self, supplier_code: str) -> Supplier | None:
        """Find a supplier by their unique supplier code."""
        stmt = select(Supplier).where(
            Supplier.supplier_code == supplier_code.upper().strip(),
            Supplier.is_deleted.is_(False),
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_email(self, email: str) -> Supplier | None:
        """Find a supplier by contact email."""
        stmt = select(Supplier).where(
            func.lower(Supplier.contact_email) == email.lower().strip(),
            Supplier.is_deleted.is_(False),
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_active(self, limit: int = 100, offset: int = 0) -> list[Supplier]:
        """Return all active suppliers."""
        stmt = (
            select(Supplier)
            .where(Supplier.status == "active", Supplier.is_deleted.is_(False))
            .order_by(Supplier.company_name)
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_by_country(self, country: str) -> list[Supplier]:
        """Return suppliers in a specific country."""
        stmt = (
            select(Supplier)
            .where(
                Supplier.country == country.upper(),
                Supplier.is_deleted.is_(False),
            )
            .order_by(Supplier.company_name)
        )
        return list(self.session.execute(stmt).scalars().all())

    def bulk_upsert(self, supplier_data: list[dict[str, Any]]) -> int:
        """Bulk upsert suppliers on supplier_code conflict."""
        from sqlalchemy.dialects.postgresql import insert

        if not supplier_data:
            return 0
        stmt = insert(Supplier).values(supplier_data)
        update_cols = {
            c.name: c
            for c in stmt.excluded
            if c.name not in ("id", "supplier_code", "created_at", "created_by")
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["supplier_code"],
            set_=update_cols,
        )
        result = self.session.execute(stmt)
        self.session.flush()
        logger.info(f"Bulk upserted {result.rowcount} suppliers")
        return result.rowcount
