"""
Product ORM model.

Represents an item in the retail product catalog. Products are the
central reference for Orders (what was bought) and Inventory (how many
are in stock).

Design decisions:
- sku has a UNIQUE constraint — the barcode/catalog business key
- price and cost use NUMERIC(12,4) for sub-cent precision
- margin_pct is stored (not computed) so historical margins survive price changes
- category + subcategory enables a two-level hierarchy without a separate table
  (a full category table would be added if the hierarchy exceeds 2 levels)
- supplier_id FK links to Supplier for sourcing reports
- weight_grams INTEGER avoids floating-point rounding errors in shipping calc
"""

import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import AuditMixin, Base, SoftDeleteMixin, UUIDMixin


class Product(UUIDMixin, AuditMixin, SoftDeleteMixin, Base):
    """
    Product catalog record.

    Master record for every item the company sells. Referenced by order line
    items, inventory records, and supplier relationships.
    """

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_products_sku"),
        CheckConstraint("unit_price >= 0", name="ck_products_price_non_negative"),
        CheckConstraint("unit_cost >= 0", name="ck_products_cost_non_negative"),
        CheckConstraint(
            "status IN ('active','inactive','discontinued','out_of_stock','draft')",
            name="ck_products_status",
        ),
        CheckConstraint(
            "weight_grams IS NULL OR weight_grams >= 0",
            name="ck_products_weight_non_negative",
        ),
        # Composite index for category browsing — the most common product query pattern
        Index("ix_products_category_status", "category", "status"),
        Index("ix_products_supplier_category", "supplier_id", "category"),
        {"comment": "Product catalog master data"},
    )

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    sku: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Stock Keeping Unit — the unique business key for this product",
    )
    product_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Full display name of the product",
    )
    short_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Abbreviated name for labels and reports",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Full product description for catalog and web display",
    )
    brand: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        index=True,
        comment="Brand or manufacturer name",
    )

    # ------------------------------------------------------------------
    # Categorization
    # ------------------------------------------------------------------
    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Top-level product category (e.g., Electronics, Apparel)",
    )
    subcategory: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Sub-category within the top-level category",
    )

    # ------------------------------------------------------------------
    # Pricing (NUMERIC for exact decimal arithmetic — never FLOAT)
    # ------------------------------------------------------------------
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        comment="Current selling price (excluding tax)",
    )
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        server_default="0.0000",
        comment="Cost of goods (COGS) per unit",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        server_default="USD",
        comment="ISO 4217 currency code",
    )

    # ------------------------------------------------------------------
    # Physical attributes
    # ------------------------------------------------------------------
    weight_grams: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Product weight in grams (INTEGER avoids floating point errors)",
    )
    unit_of_measure: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="each",
        comment="Unit of measure: each, kg, litre, box, pack",
    )

    # ------------------------------------------------------------------
    # Status and availability
    # ------------------------------------------------------------------
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="active",
        index=True,
        comment="Product lifecycle: active, inactive, discontinued, out_of_stock, draft",
    )
    is_taxable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
        comment="Whether this product is subject to sales tax",
    )
    tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        server_default="0.0000",
        comment="Applicable tax rate as a decimal (e.g., 0.0825 = 8.25%)",
    )

    # ------------------------------------------------------------------
    # Supplier FK
    # ------------------------------------------------------------------
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL", name="fk_products_supplier"),
        nullable=True,
        index=True,
        comment="Primary supplier for this product",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    supplier: Mapped["Supplier | None"] = relationship(  # type: ignore[name-defined]
        "Supplier",
        back_populates="products",
        lazy="select",
    )
    inventory_records: Mapped[list["Inventory"]] = relationship(  # type: ignore[name-defined]
        "Inventory",
        back_populates="product",
        lazy="select",
        cascade="save-update, merge",
    )
    order_items: Mapped[list["OrderItem"]] = relationship(  # type: ignore[name-defined]
        "OrderItem",
        back_populates="product",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"Product(id={self.id}, sku={self.sku!r}, name={self.product_name!r})"

    @property
    def gross_margin(self) -> Decimal:
        """Gross margin per unit (price minus cost)."""
        return self.unit_price - self.unit_cost

    @property
    def gross_margin_pct(self) -> Decimal:
        """Gross margin as a percentage of unit price."""
        if self.unit_price == 0:
            return Decimal("0")
        return (self.gross_margin / self.unit_price * 100).quantize(Decimal("0.01"))
