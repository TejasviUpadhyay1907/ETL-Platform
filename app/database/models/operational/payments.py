"""
Payment ORM model.

Records every payment transaction against an order. An order may have
multiple partial payments (installments), refunds, and adjustments —
all stored as separate payment records with appropriate transaction types.

Design decisions:
- One payment can partially or fully settle an order (partial_amount flag)
- transaction_type distinguishes payment from refund from adjustment
- payment_method uses a CHECK constraint against the approved list
- transaction_status tracks the lifecycle of the payment authorization
- payment_gateway and gateway_reference enable reconciliation with the
  external payment processor (Stripe, PayPal, etc.)
- amount uses NUMERIC(14,4) — high precision for multi-currency support
- All amounts are stored in the transaction currency; the base_currency_amount
  field stores the USD-equivalent for consolidated reporting
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import AuditMixin, Base, TimestampMixin, UUIDMixin


class Payment(UUIDMixin, AuditMixin, Base):
    """
    Payment transaction record.

    One or more payments are associated with a single order. Supports
    partial payments, refunds, and multi-currency transactions.
    """

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint(
            "gateway_reference",
            name="uq_payments_gateway_reference",
        ),
        CheckConstraint(
            "transaction_type IN ('payment','refund','partial_refund','adjustment','chargeback')",
            name="ck_payments_transaction_type",
        ),
        CheckConstraint(
            "payment_method IN ('credit_card','debit_card','bank_transfer',"
            "'cash','cheque','paypal','stripe','apple_pay','google_pay','store_credit')",
            name="ck_payments_method",
        ),
        CheckConstraint(
            "transaction_status IN ('pending','authorized','captured',"
            "'settled','failed','cancelled','refunded','disputed')",
            name="ck_payments_status",
        ),
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        CheckConstraint(
            "exchange_rate IS NULL OR exchange_rate > 0",
            name="ck_payments_exchange_rate_positive",
        ),
        # Conditional unique index on gateway_reference (only where not NULL)
        Index(
            "ix_payments_gateway_reference_unique",
            "gateway_reference",
            unique=True,
            postgresql_where="gateway_reference IS NOT NULL",
        ),
        # Index for date-range payment reporting
        Index("ix_payments_payment_date", "payment_date"),
        # Composite index for payment reconciliation by method and date
        Index("ix_payments_method_date", "payment_method", "payment_date"),
        {"comment": "Payment transaction records linked to orders"},
    )

    # ------------------------------------------------------------------
    # Foreign key
    # ------------------------------------------------------------------
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT", name="fk_payments_order"),
        nullable=False,
        index=True,
        comment="The order this payment is applied to",
    )

    # ------------------------------------------------------------------
    # Transaction metadata
    # ------------------------------------------------------------------
    transaction_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="payment",
        comment="Type: payment, refund, partial_refund, adjustment, chargeback",
    )
    transaction_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending",
        index=True,
        comment="Processing status: pending, authorized, captured, settled, failed…",
    )

    # ------------------------------------------------------------------
    # Payment method
    # ------------------------------------------------------------------
    payment_method: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
        comment="Method used for this transaction",
    )
    payment_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Date the payment was initiated",
    )
    due_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Invoice due date (for B2B invoiced payments)",
    )

    # ------------------------------------------------------------------
    # Amount and currency
    # ------------------------------------------------------------------
    amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        nullable=False,
        comment="Payment amount in the transaction currency",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        server_default="USD",
        comment="ISO 4217 transaction currency code",
    )
    exchange_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6),
        nullable=True,
        comment="Exchange rate to base currency at time of transaction",
    )
    base_currency_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4),
        nullable=True,
        comment="Equivalent amount in base currency (USD) for consolidated reporting",
    )

    # ------------------------------------------------------------------
    # Gateway / processor information
    # ------------------------------------------------------------------
    payment_gateway: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Payment processor: stripe, paypal, adyen, square, etc.",
    )
    gateway_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="Transaction ID from the payment gateway for reconciliation",
    )
    authorization_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Authorization code from the card network",
    )

    # ------------------------------------------------------------------
    # Card details (last 4 only — never store full card numbers)
    # ------------------------------------------------------------------
    card_last_four: Mapped[str | None] = mapped_column(
        String(4),
        nullable=True,
        comment="Last 4 digits of card number for display — NEVER store full PAN",
    )
    card_brand: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Card brand: visa, mastercard, amex, discover",
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    order: Mapped["Order"] = relationship(  # type: ignore[name-defined]
        "Order",
        back_populates="payments",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"Payment(id={self.id}, order_id={self.order_id}, "
            f"amount={self.amount} {self.currency}, status={self.transaction_status!r})"
        )
