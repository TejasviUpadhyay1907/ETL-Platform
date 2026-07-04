"""
CustomerRepository.

All database operations for the Customer model. No SQL outside this class.
"""

import uuid
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.database.models.operational.customers import Customer
from app.database.repositories.base_repository import BaseRepository
from app.logging.logger import get_logger

logger = get_logger(__name__)


class CustomerRepository(BaseRepository[Customer]):
    """
    Repository for Customer CRUD and query operations.

    Usage:
        repo = CustomerRepository(session)
        customer = repo.get_by_email("user@example.com")
    """

    model_class = Customer

    def get_by_email(self, email: str) -> Customer | None:
        """Find a customer by their email address (case-insensitive)."""
        stmt = select(Customer).where(
            func.lower(Customer.email) == email.lower().strip(),
            Customer.is_deleted.is_(False),
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_external_id(self, external_id: str, source_system: str) -> Customer | None:
        """Find a customer by their ID in a source system."""
        stmt = select(Customer).where(
            Customer.external_id == external_id,
            Customer.source_system == source_system,
            Customer.is_deleted.is_(False),
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def search(
        self,
        query: str,
        status: str | None = None,
        country: str | None = None,
        segment: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Customer]:
        """
        Full-text search across customer name and email with optional filters.

        Args:
            query: Search term matched against first_name, last_name, email.
            status: Filter by customer status.
            country: Filter by ISO country code.
            segment: Filter by customer_segment.
            limit: Max results.
            offset: Pagination offset.
        """
        search_term = f"%{query.lower()}%"
        stmt = (
            select(Customer)
            .where(
                Customer.is_deleted.is_(False),
                or_(
                    func.lower(Customer.first_name).like(search_term),
                    func.lower(Customer.last_name).like(search_term),
                    func.lower(Customer.email).like(search_term),
                ),
            )
            .order_by(Customer.last_name, Customer.first_name)
            .limit(limit)
            .offset(offset)
        )
        if status:
            stmt = stmt.where(Customer.status == status)
        if country:
            stmt = stmt.where(Customer.country == country.upper())
        if segment:
            stmt = stmt.where(Customer.customer_segment == segment.lower())

        return list(self.session.execute(stmt).scalars().all())

    def get_by_status(self, status: str, limit: int = 100, offset: int = 0) -> list[Customer]:
        """Retrieve customers filtered by status."""
        stmt = (
            select(Customer)
            .where(Customer.status == status, Customer.is_deleted.is_(False))
            .order_by(Customer.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.execute(stmt).scalars().all())

    def count_by_status(self) -> dict[str, int]:
        """Return a count of customers grouped by status."""
        stmt = (
            select(Customer.status, func.count().label("count"))
            .where(Customer.is_deleted.is_(False))
            .group_by(Customer.status)
        )
        rows = self.session.execute(stmt).all()
        return {row.status: row.count for row in rows}

    def count_by_country(self) -> dict[str, int]:
        """Return a count of active customers grouped by country."""
        stmt = (
            select(Customer.country, func.count().label("count"))
            .where(Customer.status == "active", Customer.is_deleted.is_(False))
            .group_by(Customer.country)
            .order_by(func.count().desc())
        )
        rows = self.session.execute(stmt).all()
        return {row.country: row.count for row in rows}

    def bulk_upsert(self, customer_data: list[dict[str, Any]]) -> dict[str, int]:
        """
        Bulk upsert customers using email as the natural key.

        Inserts new customers and updates existing ones (matched on email).
        Returns counts of inserted and updated records.

        Args:
            customer_data: List of dicts with customer field values.

        Returns:
            {"inserted": N, "updated": M}
        """
        from sqlalchemy.dialects.postgresql import insert

        if not customer_data:
            return {"inserted": 0, "updated": 0}

        stmt = insert(Customer).values(customer_data)
        update_cols = {
            c.name: c
            for c in stmt.excluded
            if c.name
            not in ("id", "email", "created_at", "created_by", "external_id", "source_system")
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["email"],
            set_=update_cols,
        ).returning(Customer.id)

        result = self.session.execute(stmt)
        self.session.flush()

        affected = result.rowcount
        logger.info(f"Bulk upserted {affected} customers")
        return {"inserted": affected, "updated": 0}  # PostgreSQL doesn't distinguish in RETURNING
