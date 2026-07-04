"""
Order and OrderItem ORM models.

An Order is a sales transaction header. Each order contains one or more
OrderItems (line items), each referencing a Product.

Design decisions:
- Two-table header/line approach (Orders + OrderItems) follows 3NF:
  - Order-level data (customer, date, shipping) lives in Orders
  - Product-level data (sku, qty, price at time of sale) lives in OrderItems
  - Storing unit_price_at_sale on OrderItem preserves the historical price
    even if the product's current price changes later
- subtotal, tax_amount, discount_amount are stored (not computed) for two reasons:
  1. Performance: avoids re-summing line items on every report query
  2. Accuracy: preserves the exact amounts from the transaction
- order_number has a UNIQUE constraint — the human-readable business reference
- status follows a defined state machine enforced by CHECK constraint
- shipping_address is denormalized onto the order (not referencing customer address)
  because a customer's address may change after the order was placed
"""

import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
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

from app.database.base import AuditMixin, Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class Order(UUIDMixin, AuditMixin, SoftDeleteMixin, Base):
    """
    Sales order header record.

    Captures the transaction-level information for a customer purchase.
    Line items are stored in the OrderItem table.
    """

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("order_number", name="uq_orders_order_number"),
        CheckConstraint(
            "status IN ('pending','processing','confirmed','shipped',"
            "'delivered','cancelled','refunded','on_hold')",
            name="ck_orders_status",
        ),
        CheckConstraint("order_total >= 0", name="ck_orders_total_non_negative"),
        CheckConstraint("discount_amount >= 0", name="ck_orders_discount_non_negative"),
        CheckConstraint("tax_amount >= 0", name="ck_orders_tax_non_negative"),
        # Composite index for the most common query: customer's orders by date
        Index("ix_orders_customer_date", "customer_id", "order_date"),
        # Index for date-range reports (daily/monthly sales)
        Index("ix_orders_order_date", "order_date"),
        # Index for status-based pipeline queries
        Index("ix_orders_status_date", "status", "order_date"),
        {"comment": "Sales order header records"},
    )

    # ------------------------------------------------------------------
    # Order reference
    # ------------------------------------------------------------------
    order_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Human-readable order reference (e.g., ORD-2025-00001)",
    )

    # ------------------------------------------------------------------
    # Customer FK
    # ------------------------------------------------------------------
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT", name="fk_orders_customer"),
        nullable=False,
        index=True,
        comment="Customer who placed this order",
    )

    # ------------------------------------------------------------------
    # Order dates
    # ------------------------------------------------------------------
    order_date: Mapped[Date] = mapped_column(
        Date,
        nullable=False,
        comment="Date the order was placed (calendar date, not timestamp)",
    )
    required_date: Mapped[Date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Date the customer requires delivery by",
    )
    shipped_date: Mapped[Date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Date the order was shipped",
    )
    delivered_date: Mapped[Date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Date the order was confirmed as delivered",
    )

    # ------------------------------------------------------------------
    # Financial totals (stored, not computed — preserves historical values)
    # ------------------------------------------------------------------
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        nullable=False,
        server_default="0.0000",
        comment="Sum of line item amounts before tax and discount",
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        nullable=False,
        server_default="0.0000",
        comment="Total discount applied to this order",
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        nullable=False,
        server_default="0.0000",
        comment="Total tax amount",
    )
    shipping_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        server_default="0.0000",
        comment="Shipping charge added to this order",
    )
    order_total: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        nullable=False,
        server_default="0.0000",
        comment="Grand total: subtotal - discount + tax + shipping",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        server_default="USD",
        comment="ISO 4217 currency code",
    )

    # ------------------------------------------------------------------
    # Status and fulfillment
    # ------------------------------------------------------------------
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending",
        index=True,
        comment="Order lifecycle status",
    )
    payment_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="unpaid",
        comment="Payment status: unpaid, paid, partially_paid, refunded",
    )
    fulfillment_channel: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="standard",
        comment="Channel: standard, express, click_and_collect, dropship",
    )

    # ------------------------------------------------------------------
    # Shipping address (denormalized — snapshot at time of order)
    # ------------------------------------------------------------------
    shipping_address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shipping_address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shipping_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shipping_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shipping_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    shipping_postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ------------------------------------------------------------------
    # Tracking and source
    # ------------------------------------------------------------------
    tracking_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Carrier tracking number",
    )
    source_system: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Originating system: web_store, mobile_app, pos, api",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    customer: Mapped["Customer"] = relationship(  # type: ignore[name-defined]
        "Customer",
        back_populates="orders",
        lazy="select",
    )
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        lazy="select",
        cascade="all, delete-orphan",
    )
    payments: Mapped[list["Payment"]] = relationship(  # type: ignore[name-defined]
        "Payment",
        back_populates="order",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"Order(id={self.id}, number={self.order_number!r}, "
            f"total={self.order_total}, status={self.status!r})"
        )


class OrderItem(UUIDMixin, TimestampMixin, Base):
    """
    Order line item record.

    Each row represents one product within an order. The unit_price_at_sale
    field captures the exact price charged, independent of future price changes.

    Design: No soft-delete on line items — they are deleted with the order
    (cascade="all, delete-orphan" on the Order.items relationship).
    """

    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint(
            "unit_price_at_sale >= 0",
            name="ck_order_items_price_non_negative",
        ),
        CheckConstraint(
            "discount_amount >= 0",
            name="ck_order_items_discount_non_negative",
        ),
        # Index for product-level sales analytics
        Index("ix_order_items_product_id", "product_id"),
        Index("ix_order_items_order_id", "order_id"),
        {"comment": "Order line items — one row per product per order"},
    )

    # ------------------------------------------------------------------
    # Foreign keys
    # ------------------------------------------------------------------
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE", name="fk_order_items_order"),
        nullable=False,
        comment="Parent order",
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT", name="fk_order_items_product"),
        nullable=False,
        comment="Product purchased",
    )

    # ------------------------------------------------------------------
    # Line item data
    # ------------------------------------------------------------------
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of units ordered",
    )
    unit_price_at_sale: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        comment="Unit price at the time of sale — snapshot, never updated",
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        server_default="0.0000",
        comment="Per-line discount amount",
    )
    line_total: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        nullable=False,
        comment="(quantity × unit_price_at_sale) - discount_amount",
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    order: Mapped["Order"] = relationship(
        "Order",
        back_populates="items",
        lazy="select",
    )
    product: Mapped["Product"] = relationship(  # type: ignore[name-defined]
        "Product",
        back_populates="order_items",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"OrderItem(order_id={self.order_id}, product_id={self.product_id}, "
            f"qty={self.quantity}, total={self.line_total})"
        )
