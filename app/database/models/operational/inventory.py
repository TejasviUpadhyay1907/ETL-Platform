"""
Inventory ORM model.

Tracks stock levels per product per warehouse location. A product can
have multiple inventory records (one per warehouse), enabling multi-location
stock management.

Design decisions:
- Composite UNIQUE on (product_id, warehouse_id) — one record per product-location pair
- quantity_on_hand uses INTEGER — fractional units are not supported in this domain
- reserved_quantity tracks stock committed to pending orders (not yet shipped)
- available_quantity is a computed property: on_hand - reserved
- reorder_point and reorder_quantity drive automated purchasing alerts
- last_counted_at tracks when a physical stock count was last performed
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import AuditMixin, Base, TimestampMixin, UUIDMixin


class Inventory(UUIDMixin, AuditMixin, Base):
    """
    Inventory stock level record per product per warehouse.

    Tracks current stock, reserved stock, reorder thresholds, and
    unit costs for the COGS calculation.
    """

    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "warehouse_id",
            name="uq_inventory_product_warehouse",
        ),
        CheckConstraint(
            "quantity_on_hand >= 0",
            name="ck_inventory_quantity_non_negative",
        ),
        CheckConstraint(
            "reserved_quantity >= 0",
            name="ck_inventory_reserved_non_negative",
        ),
        CheckConstraint(
            "reorder_point >= 0",
            name="ck_inventory_reorder_point_non_negative",
        ),
        CheckConstraint(
            "unit_cost >= 0",
            name="ck_inventory_unit_cost_non_negative",
        ),
        # Index for warehouse-level stock reports
        Index("ix_inventory_warehouse_id", "warehouse_id"),
        # Partial index for low-stock alerts — filtered queries on a small subset
        Index(
            "ix_inventory_low_stock",
            "product_id",
            "warehouse_id",
            postgresql_where="quantity_on_hand <= reorder_point",
        ),
        {"comment": "Stock level tracking per product per warehouse"},
    )

    # ------------------------------------------------------------------
    # Foreign keys
    # ------------------------------------------------------------------
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT", name="fk_inventory_product"),
        nullable=False,
        index=True,
        comment="Product this inventory record belongs to",
    )
    warehouse_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Warehouse or location identifier (e.g., WH-EAST-01)",
    )

    # ------------------------------------------------------------------
    # Stock quantities
    # ------------------------------------------------------------------
    quantity_on_hand: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Physical units currently in the warehouse",
    )
    reserved_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Units committed to pending/processing orders, not yet shipped",
    )
    reorder_point: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="10",
        comment="Trigger a reorder when quantity_on_hand falls to this level",
    )
    reorder_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="50",
        comment="Standard order quantity when reordering from supplier",
    )

    # ------------------------------------------------------------------
    # Costing
    # ------------------------------------------------------------------
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        server_default="0.0000",
        comment="Weighted average cost per unit at this location",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        server_default="USD",
        comment="ISO 4217 currency code for the cost",
    )

    # ------------------------------------------------------------------
    # Audit / physical count
    # ------------------------------------------------------------------
    last_counted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of the last physical stock count",
    )
    last_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of the last stock receipt (PO delivery)",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    product: Mapped["Product"] = relationship(  # type: ignore[name-defined]
        "Product",
        back_populates="inventory_records",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"Inventory(product_id={self.product_id}, "
            f"warehouse={self.warehouse_id!r}, "
            f"on_hand={self.quantity_on_hand})"
        )

    @property
    def available_quantity(self) -> int:
        """Units available for new orders (on_hand minus reserved)."""
        return max(0, self.quantity_on_hand - self.reserved_quantity)

    @property
    def is_low_stock(self) -> bool:
        """True when stock has reached or dropped below the reorder point."""
        return self.quantity_on_hand <= self.reorder_point

    @property
    def stock_value(self) -> Decimal:
        """Total inventory value at this location (on_hand × unit_cost)."""
        return Decimal(self.quantity_on_hand) * self.unit_cost
