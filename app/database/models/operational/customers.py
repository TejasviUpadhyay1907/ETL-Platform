"""
Customer ORM model.

Represents the enterprise customer master record. Every order, payment, and
interaction in the system is ultimately tied back to a customer.

Design decisions:
- email has a UNIQUE constraint — the business key for customer identity
- phone/dob/gender are nullable — not always collected
- status uses a CHECK constraint to enforce the allowed state machine
- full_name is a generated column (server-side CONCAT) for search convenience
- Soft-delete via SoftDeleteMixin — customers are never physically deleted
  because orders, payments, and audit logs reference them
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import AuditMixin, Base, SoftDeleteMixin, UUIDMixin


class Customer(UUIDMixin, AuditMixin, SoftDeleteMixin, Base):
    """
    Customer master record.

    Stores all identifying and contact information for a retail customer.
    The anchor for Orders, Payments, and all customer-facing analytics.
    """

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("email", name="uq_customers_email"),
        CheckConstraint(
            "status IN ('active','inactive','suspended','pending_verification')",
            name="ck_customers_status",
        ),
        CheckConstraint(
            "gender IN ('male','female','non_binary','prefer_not_to_say') OR gender IS NULL",
            name="ck_customers_gender",
        ),
        # Composite index: country + city for geo-based analytics queries
        Index("ix_customers_country_city", "country", "city"),
        # Partial index: only active customers — most queries filter by active status
        Index(
            "ix_customers_email_active",
            "email",
            postgresql_where="is_deleted = false",
        ),
        {"comment": "Customer master data — anchor for all business transactions"},
    )

    # ------------------------------------------------------------------
    # Identity fields
    # ------------------------------------------------------------------
    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Legal first name",
    )
    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Legal last name",
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Primary email address — unique business key",
    )
    phone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="Primary contact phone number (E.164 format preferred)",
    )
    gender: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Gender identity: male, female, non_binary, prefer_not_to_say",
    )
    date_of_birth: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Date of birth for age-restricted product validation",
    )

    # ------------------------------------------------------------------
    # Address fields
    # ------------------------------------------------------------------
    address_line1: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Street address line 1",
    )
    address_line2: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Street address line 2 (apt, suite, etc.)",
    )
    city: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="City of residence",
    )
    state: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="State or province",
    )
    country: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        server_default="US",
        comment="ISO 3166-1 alpha-2 country code",
    )
    postal_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="ZIP or postal code",
    )

    # ------------------------------------------------------------------
    # Business fields
    # ------------------------------------------------------------------
    customer_segment: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="standard",
        comment="Customer tier: standard, silver, gold, platinum, vip",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default="active",
        index=True,
        comment="Lifecycle status: active, inactive, suspended, pending_verification",
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Free-form internal notes about this customer",
    )

    # ------------------------------------------------------------------
    # Source tracking (where did this record come from?)
    # ------------------------------------------------------------------
    source_system: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Originating system (e.g., web_store, mobile_app, crm_import)",
    )
    external_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="ID in the source system for reconciliation",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    orders: Mapped[list["Order"]] = relationship(  # type: ignore[name-defined]
        "Order",
        back_populates="customer",
        lazy="select",
        cascade="save-update, merge",
        # Do NOT cascade delete — orders must be preserved for audit
    )

    def __repr__(self) -> str:
        return f"Customer(id={self.id}, email={self.email!r}, status={self.status!r})"

    @property
    def full_name(self) -> str:
        """Computed full name from first and last name."""
        return f"{self.first_name} {self.last_name}".strip()
