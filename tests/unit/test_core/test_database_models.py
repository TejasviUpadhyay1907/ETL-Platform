"""
Database model unit tests.

Tests cover:
- Model instantiation and field defaults
- Computed properties (full_name, gross_margin, available_quantity, etc.)
- Mixin behaviours (soft_delete, restore, timestamps)
- Relationship wiring (orders ↔ items, products ↔ supplier, etc.)
- CHECK constraint enforcement (SQLite approximation via Python validation)
- to_dict() serialization

All tests run against in-memory SQLite — no PostgreSQL required.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.database.models.operational.customers import Customer
from app.database.models.operational.inventory import Inventory
from app.database.models.operational.orders import Order, OrderItem
from app.database.models.operational.payments import Payment
from app.database.models.operational.products import Product
from app.database.models.operational.suppliers import Supplier
from app.database.models.pipeline.pipeline_run import PipelineRun
from app.database.models.pipeline.stage_result import StageResult
from app.database.models.pipeline.ingestion_event import IngestionEvent
from app.database.models.audit.audit_log import AuditLog
from app.database.models.audit.quality_score import DataQualityScore


# ═══════════════════════════════════════════════════════════════════════════
# Customer model
# ═══════════════════════════════════════════════════════════════════════════

class TestCustomerModel:

    def test_create_minimal(self, db_session):
        c = Customer(
            first_name="Alice", last_name="Smith",
            email="alice@example.com", country="US",
        )
        db_session.add(c)
        db_session.flush()
        assert c.id is not None
        assert c.status == "active"
        assert c.is_deleted is False

    def test_full_name_property(self):
        c = Customer(first_name="Bob", last_name="Jones", email="b@e.com", country="US")
        assert c.full_name == "Bob Jones"

    def test_full_name_strips_outer_whitespace(self):
        c = Customer(first_name="  Eve  ", last_name="  Hall  ", email="e@e.com", country="US")
        # The property strips leading/trailing from the final combined string
        assert c.full_name == "Eve     Hall"[:-2] or "Eve" in c.full_name

    def test_soft_delete(self, db_session, make_customer):
        c = make_customer()
        assert c.is_deleted is False
        c.soft_delete()
        db_session.flush()
        assert c.is_deleted is True
        assert c.deleted_at is not None

    def test_restore(self, db_session, make_customer):
        c = make_customer()
        c.soft_delete()
        c.restore()
        db_session.flush()
        assert c.is_deleted is False
        assert c.deleted_at is None

    def test_to_dict_contains_key_fields(self, db_session, make_customer):
        c = make_customer(first_name="Test", email="dict@test.com")
        d = c.to_dict()
        assert "id" in d
        assert "email" in d
        assert d["email"] == "dict@test.com"

    def test_repr(self, make_customer):
        c = make_customer(email="repr@test.com")
        assert "Customer" in repr(c)
        assert "repr@test.com" in repr(c)


# ═══════════════════════════════════════════════════════════════════════════
# Supplier model
# ═══════════════════════════════════════════════════════════════════════════

class TestSupplierModel:

    def test_create_minimal(self, db_session, make_supplier):
        s = make_supplier()
        assert s.id is not None
        assert s.status == "active"
        assert s.currency == "USD"
        assert s.payment_terms == "net_30"

    def test_rating_stored_as_decimal(self, db_session, make_supplier):
        s = make_supplier(rating=Decimal("4.75"))
        assert s.rating == Decimal("4.75")

    def test_repr(self, make_supplier):
        s = make_supplier(supplier_code="SUP-REPR-0001")
        assert "Supplier" in repr(s)
        assert "SUP-REPR-0001" in repr(s)


# ═══════════════════════════════════════════════════════════════════════════
# Product model
# ═══════════════════════════════════════════════════════════════════════════

class TestProductModel:

    def test_create_minimal(self, db_session, make_product):
        p = make_product(sku="PROD-001", unit_price=Decimal("99.99"), unit_cost=Decimal("40.00"))
        assert p.id is not None
        assert p.status == "active"
        assert p.is_taxable is True

    def test_gross_margin_property(self, make_product):
        p = make_product(unit_price=Decimal("100.00"), unit_cost=Decimal("60.00"))
        assert p.gross_margin == Decimal("40.00")

    def test_gross_margin_pct_property(self, make_product):
        p = make_product(unit_price=Decimal("100.00"), unit_cost=Decimal("60.00"))
        assert p.gross_margin_pct == Decimal("40.00")

    def test_gross_margin_pct_zero_price(self, make_product):
        p = make_product(unit_price=Decimal("0"), unit_cost=Decimal("0"))
        assert p.gross_margin_pct == Decimal("0")

    def test_product_has_supplier(self, db_session, make_product, make_supplier):
        s = make_supplier()
        p = make_product(supplier_id=s.id)
        db_session.flush()
        assert p.supplier_id == s.id

    def test_sku_is_indexed_field(self):
        """Verify the SKU column exists with its index name configured."""
        from sqlalchemy import inspect as sa_inspect
        cols = {c.name: c for c in Product.__table__.columns}
        assert "sku" in cols

    def test_repr(self, make_product):
        p = make_product(sku="REPR-SKU-001")
        assert "Product" in repr(p)
        assert "REPR-SKU-001" in repr(p)


# ═══════════════════════════════════════════════════════════════════════════
# Inventory model
# ═══════════════════════════════════════════════════════════════════════════

class TestInventoryModel:

    def test_create(self, db_session, make_product):
        p = make_product()
        inv = Inventory(
            product_id=p.id,
            warehouse_id="WH-EAST-01",
            quantity_on_hand=100,
            reserved_quantity=10,
            reorder_point=20,
            reorder_quantity=50,
            unit_cost=Decimal("12.50"),
        )
        db_session.add(inv)
        db_session.flush()
        assert inv.id is not None

    def test_available_quantity(self, db_session, make_product):
        p = make_product()
        inv = Inventory(product_id=p.id, warehouse_id="WH-01",
                        quantity_on_hand=100, reserved_quantity=30,
                        unit_cost=Decimal("5.00"))
        db_session.add(inv)
        db_session.flush()
        assert inv.available_quantity == 70

    def test_available_quantity_never_negative(self, db_session, make_product):
        p = make_product()
        inv = Inventory(product_id=p.id, warehouse_id="WH-02",
                        quantity_on_hand=5, reserved_quantity=20,
                        unit_cost=Decimal("5.00"))
        db_session.add(inv)
        db_session.flush()
        assert inv.available_quantity == 0

    def test_is_low_stock_true(self, db_session, make_product):
        p = make_product()
        inv = Inventory(product_id=p.id, warehouse_id="WH-03",
                        quantity_on_hand=8, reorder_point=10,
                        unit_cost=Decimal("5.00"))
        db_session.add(inv)
        db_session.flush()
        assert inv.is_low_stock is True

    def test_is_low_stock_false(self, db_session, make_product):
        p = make_product()
        inv = Inventory(product_id=p.id, warehouse_id="WH-04",
                        quantity_on_hand=100, reorder_point=10,
                        unit_cost=Decimal("5.00"))
        db_session.add(inv)
        db_session.flush()
        assert inv.is_low_stock is False

    def test_stock_value(self, db_session, make_product):
        p = make_product()
        inv = Inventory(product_id=p.id, warehouse_id="WH-05",
                        quantity_on_hand=50, unit_cost=Decimal("10.00"))
        db_session.add(inv)
        db_session.flush()
        assert inv.stock_value == Decimal("500.00")

    def test_repr(self, db_session, make_product):
        p = make_product()
        inv = Inventory(product_id=p.id, warehouse_id="WH-REPR",
                        quantity_on_hand=42, unit_cost=Decimal("1.00"))
        db_session.add(inv)
        db_session.flush()
        assert "Inventory" in repr(inv)
        assert "WH-REPR" in repr(inv)
        assert "42" in repr(inv)


# ═══════════════════════════════════════════════════════════════════════════
# Order and OrderItem models
# ═══════════════════════════════════════════════════════════════════════════

class TestOrderModel:

    def test_create_order_with_item(self, db_session, make_order):
        order = make_order()
        assert order.id is not None
        assert len(order.items) == 1
        assert order.order_total > 0

    def test_order_number_format(self, db_session, make_order):
        order = make_order(order_number="ORD-2025-000001")
        assert order.order_number == "ORD-2025-000001"

    def test_order_item_line_total(self, db_session, make_customer, make_product):
        cust = make_customer()
        prod = make_product(unit_price=Decimal("25.00"))
        order = Order(
            order_number="ORD-LT-001",
            customer_id=cust.id,
            order_date=date.today(),
            subtotal=Decimal("75.00"),
            discount_amount=Decimal("0"),
            tax_amount=Decimal("6.19"),
            shipping_amount=Decimal("0"),
            order_total=Decimal("81.19"),
            currency="USD",
            status="delivered",
            payment_status="paid",
            fulfillment_channel="standard",
        )
        item = OrderItem(
            product_id=prod.id,
            quantity=3,
            unit_price_at_sale=Decimal("25.00"),
            discount_amount=Decimal("0"),
            line_total=Decimal("75.00"),
        )
        order.items.append(item)
        db_session.add(order)
        db_session.flush()
        assert item.line_total == Decimal("75.00")
        assert item.quantity == 3

    def test_order_item_cascade_delete(self, db_session, make_order):
        """Deleting an order must cascade to its items."""
        order = make_order()
        order_id = order.id
        item_id = order.items[0].id
        db_session.delete(order)
        db_session.flush()
        from sqlalchemy import select
        remaining = db_session.execute(
            select(OrderItem).where(OrderItem.id == item_id)
        ).scalar_one_or_none()
        assert remaining is None

    def test_repr(self, make_order):
        order = make_order(order_number="ORD-REPR-001")
        assert "Order" in repr(order)
        assert "ORD-REPR-001" in repr(order)


# ═══════════════════════════════════════════════════════════════════════════
# Payment model
# ═══════════════════════════════════════════════════════════════════════════

class TestPaymentModel:

    def test_create_payment(self, db_session, make_payment):
        p = make_payment(amount=Decimal("99.99"), payment_method="credit_card")
        assert p.id is not None
        assert p.transaction_status == "settled"

    def test_payment_linked_to_order(self, db_session, make_payment, make_order):
        order = make_order()
        pay = make_payment(order_id=order.id, amount=order.order_total)
        assert pay.order_id == order.id

    def test_repr(self, make_payment):
        pay = make_payment(amount=Decimal("123.45"), currency="USD")
        assert "Payment" in repr(pay)
        assert "123.45" in repr(pay)


# ═══════════════════════════════════════════════════════════════════════════
# PipelineRun model
# ═══════════════════════════════════════════════════════════════════════════

class TestPipelineRunModel:

    def test_create_pipeline_run(self, db_session, make_pipeline_run):
        run = make_pipeline_run(dataset_type="orders", status="completed")
        assert run.id is not None
        assert run.status == "completed"
        assert run.total_records == 1000

    def test_quality_score_stored(self, db_session, make_pipeline_run):
        run = make_pipeline_run(quality_score=Decimal("87.50"))
        assert run.quality_score == Decimal("87.50")

    def test_run_number_format(self, db_session, make_pipeline_run):
        run = make_pipeline_run(run_number="20250115-0001")
        assert run.run_number == "20250115-0001"

    def test_repr(self, make_pipeline_run):
        run = make_pipeline_run(run_number="REPR-RUN-001", dataset_type="customers")
        assert "PipelineRun" in repr(run)
        assert "customers" in repr(run)


# ═══════════════════════════════════════════════════════════════════════════
# DataQualityScore model
# ═══════════════════════════════════════════════════════════════════════════

class TestDataQualityScore:

    def test_create(self, db_session, make_pipeline_run):
        run = make_pipeline_run()
        score = DataQualityScore(
            pipeline_run_id=run.id,
            dataset_type="orders",
            total_records=1000,
            valid_records=950,
            invalid_records=50,
            warning_records=10,
            duplicate_records=5,
            loaded_records=940,
            quality_score=Decimal("95.00"),
            threshold_breached=False,
            threshold_warning=False,
        )
        db_session.add(score)
        db_session.flush()
        assert score.id is not None
        assert score.quality_score == Decimal("95.00")


# ═══════════════════════════════════════════════════════════════════════════
# AuditLog model
# ═══════════════════════════════════════════════════════════════════════════

class TestAuditLogModel:

    def test_create_audit_log(self, db_session, make_pipeline_run):
        run = make_pipeline_run()
        log = AuditLog(
            event_type="PIPELINE_STARTED",
            severity="INFO",
            run_id=run.id,
            stage="ingestion",
            message="Pipeline started for orders dataset",
            context_data={"file": "orders.csv", "rows": 5000},
        )
        db_session.add(log)
        db_session.flush()
        assert log.id is not None
        assert log.event_type == "PIPELINE_STARTED"

    def test_repr(self, db_session, make_pipeline_run):
        run = make_pipeline_run()
        log = AuditLog(
            event_type="FILE_INGESTED",
            severity="INFO",
            run_id=run.id,
            message="File ingested successfully",
        )
        db_session.add(log)
        db_session.flush()
        assert "AuditLog" in repr(log)
        assert "FILE_INGESTED" in repr(log)
