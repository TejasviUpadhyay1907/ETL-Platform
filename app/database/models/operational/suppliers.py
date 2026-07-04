"""
Supplier ORM model.

Represents a vendor or supplier that provides products to the company.
Products reference Suppliers to track sourcing, and this drives purchasing
analytics and supplier performance reporting.

Design decisions:
- A supplier can supply many products (one-to-many with products)
- payment_terms stored as text (net_30, net_60, etc.) for flexibility
- rating stored as NUMERIC(3,2) to allow 0.00–5.00 scale
- country as ISO 3166-1 alpha-2 for standardized geo reporting
"""

from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import AuditMixin, Base, SoftDeleteMixin, UUIDMixin


class Supplier(UUIDMixin, AuditMixin, SoftDeleteMixin, Base):
    """
    Supplier master record.

    Tracks all vendors and suppliers the company sources products from.
    """

    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("supplier_code", name="uq_suppliers_code"),
        CheckConstraint(
            "status IN ('active','inactive','on_hold','blacklisted')",
            name="ck_suppliers_status",
        ),
        CheckConstraint(
            "rating IS NULL OR (rating >= 0 AND rating <= 5)",
            name="ck_suppliers_rating",
        ),
        Index("ix_suppliers_country_status", "country", "status"),
        {"comment": "Supplier and vendor master data"},
    )

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    supplier_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Internal unique supplier code (e.g., SUP-001234)",
    )
    company_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Legal business name of the supplier",
    )
    trade_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="DBA / trading name if different from legal name",
    )

    # ------------------------------------------------------------------
    # Contact information
    # ------------------------------------------------------------------
    contact_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Primary contact person full name",
    )
    contact_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Primary contact email",
    )
    contact_phone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="Primary contact phone number",
    )

    # ------------------------------------------------------------------
    # Address
    # ------------------------------------------------------------------
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        server_default="US",
        comment="ISO 3166-1 alpha-2 country code",
    )
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ------------------------------------------------------------------
    # Business terms
    # ------------------------------------------------------------------
    payment_terms: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="net_30",
        comment="Payment terms: net_30, net_60, net_90, prepaid, cod",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        server_default="USD",
        comment="ISO 4217 currency code for transactions with this supplier",
    )
    rating: Mapped[Decimal | None] = mapped_column(
        Numeric(3, 2),
        nullable=True,
        comment="Supplier performance rating 0.00–5.00",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="active",
        index=True,
        comment="Status: active, inactive, on_hold, blacklisted",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    products: Mapped[list["Product"]] = relationship(  # type: ignore[name-defined]
        "Product",
        back_populates="supplier",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"Supplier(id={self.id}, code={self.supplier_code!r}, name={self.company_name!r})"
