"""
Repository layer unit tests.

Tests cover:
- All CRUD operations via BaseRepository
- Domain-specific query methods
- Bulk upsert operations
- Pagination and filtering
- Soft-delete filtering
- Pipeline run lifecycle management

All tests use the in-memory SQLite engine via the db_session fixture.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.database.repositories.audit_log_repository import AuditLogRepository
from app.database.repositories.customer_repository import CustomerRepository
from app.database.repositories.inventory_repository import InventoryRepository
from app.database.repositories.order_repository import OrderRepository
from app.database.repositories.payment_repository import PaymentRepository
from app.database.repositories.pipeline_run_repository import PipelineRunRepository
from app.database.repositories.product_repository import ProductRepository
from app.database.repositories.supplier_repository import SupplierRepository


# ═══════════════════════════════════════════════════════════════════════════
# BaseRepository (tested via CustomerRepository as a proxy)
# ═══════════════════════════════════════════════════════════════════════════

class TestBaseRepository:

    def test_get_by_id_found(self, db_session, make_customer):
        cust = make_customer()
        repo = CustomerRepository(db_session)
        result = repo.get_by_id(cust.id)
        assert result is not None
        assert result.id == cust.id

    def test_get_by_id_not_found(self, db_session):
        import uuid
        repo = CustomerRepository(db_session)
        result = repo.get_by_id(uuid.uuid4())
        assert result is None

    def test_get_by_id_or_raise_found(self, db_session, make_customer):
        cust = make_customer()
        repo = CustomerRepository(db_session)
        result = repo.get_by_id_or_raise(cust.id)
        assert result.id == cust.id

    def test_get_by_id_or_raise_missing(self, db_session):
        import uuid
        from app.core.exceptions import NotFoundException
        repo = CustomerRepository(db_session)
        with pytest.raises(NotFoundException):
            repo.get_by_id_or_raise(uuid.uuid4())

    def test_get_all_returns_list(self, db_session, make_customer):
        make_customer()
        make_customer()
        make_customer()
        repo = CustomerRepository(db_session)
        result = repo.get_all(limit=10, offset=0)
        assert len(result) >= 3

    def test_get_all_pagination(self, db_session, make_customer):
        for _ in range(5):
            make_customer()
        repo = CustomerRepository(db_session)
        page1 = repo.get_all(limit=3, offset=0)
        page2 = repo.get_all(limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) >= 2
        # Pages should have different IDs
        ids1 = {r.id for r in page1}
        ids2 = {r.id for r in page2}
        assert ids1.isdisjoint(ids2)

    def test_count(self, db_session, make_customer):
        initial = CustomerRepository(db_session).count()
        make_customer()
        make_customer()
        assert CustomerRepository(db_session).count() == initial + 2

    def test_update(self, db_session, make_customer):
        cust = make_customer(status="active")
        repo = CustomerRepository(db_session)
        updated = repo.update(cust, status="suspended")
        assert updated.status == "suspended"

    def test_delete(self, db_session, make_customer):
        cust = make_customer()
        cid = cust.id
        repo = CustomerRepository(db_session)
        repo.delete(cust)
        assert repo.get_by_id(cid) is None

    def test_exists_true(self, db_session, make_customer):
        cust = make_customer()
        repo = CustomerRepository(db_session)
        assert repo.exists(cust.id) is True

    def test_exists_false(self, db_session):
        import uuid
        repo = CustomerRepository(db_session)
        assert repo.exists(uuid.uuid4()) is False


# ═══════════════════════════════════════════════════════════════════════════
# CustomerRepository
# ═══════════════════════════════════════════════════════════════════════════

class TestCustomerRepository:

    def test_get_by_email(self, db_session, make_customer):
        cust = make_customer(email="findme@example.com")
        repo = CustomerRepository(db_session)
        result = repo.get_by_email("findme@example.com")
        assert result is not None
        assert result.id == cust.id

    def test_get_by_email_case_insensitive(self, db_session, make_customer):
        make_customer(email="Case@Example.COM")
        repo = CustomerRepository(db_session)
        result = repo.get_by_email("case@example.com")
        assert result is not None

    def test_get_by_email_not_found(self, db_session):
        repo = CustomerRepository(db_session)
        assert repo.get_by_email("nobody@example.com") is None

    def test_get_by_email_excludes_deleted(self, db_session, make_customer):
        cust = make_customer(email="deleted@example.com")
        cust.soft_delete()
        db_session.flush()
        repo = CustomerRepository(db_session)
        result = repo.get_by_email("deleted@example.com")
        assert result is None

    def test_get_by_status(self, db_session, make_customer):
        make_customer(status="active")
        make_customer(status="active")
        make_customer(status="inactive")
        repo = CustomerRepository(db_session)
        active = repo.get_by_status("active")
        assert len(active) >= 2
        assert all(c.status == "active" for c in active)

    def test_count_by_status(self, db_session, make_customer):
        make_customer(status="active")
        make_customer(status="active")
        make_customer(status="suspended")
        repo = CustomerRepository(db_session)
        counts = repo.count_by_status()
        assert counts.get("active", 0) >= 2
        assert counts.get("suspended", 0) >= 1

    def test_search_by_first_name(self, db_session, make_customer):
        make_customer(first_name="Unique", last_name="Name", email="unique@test.com")
        repo = CustomerRepository(db_session)
        results = repo.search("unique")
        assert any(c.first_name == "Unique" for c in results)

    def test_search_by_email(self, db_session, make_customer):
        make_customer(email="searchable@company.com")
        repo = CustomerRepository(db_session)
        results = repo.search("searchable")
        assert any("searchable" in c.email for c in results)


# ═══════════════════════════════════════════════════════════════════════════
# SupplierRepository
# ═══════════════════════════════════════════════════════════════════════════

class TestSupplierRepository:

    def test_get_by_code(self, db_session, make_supplier):
        sup = make_supplier(supplier_code="SUP-FIND-0001")
        repo = SupplierRepository(db_session)
        result = repo.get_by_code("SUP-FIND-0001")
        assert result is not None
        assert result.id == sup.id

    def test_get_by_code_not_found(self, db_session):
        repo = SupplierRepository(db_session)
        assert repo.get_by_code("SUP-NONE-9999") is None

    def test_get_active(self, db_session, make_supplier):
        make_supplier(status="active")
        make_supplier(status="inactive")
        repo = SupplierRepository(db_session)
        actives = repo.get_active()
        assert all(s.status == "active" for s in actives)

    def test_get_by_country(self, db_session, make_supplier):
        make_supplier(country="CA")
        make_supplier(country="GB")
        repo = SupplierRepository(db_session)
        ca = repo.get_by_country("CA")
        assert all(s.country == "CA" for s in ca)


# ═══════════════════════════════════════════════════════════════════════════
# ProductRepository
# ═══════════════════════════════════════════════════════════════════════════

class TestProductRepository:

    def test_get_by_sku(self, db_session, make_product):
        p = make_product(sku="SKU-FIND-001")
        repo = ProductRepository(db_session)
        result = repo.get_by_sku("SKU-FIND-001")
        assert result is not None
        assert result.id == p.id

    def test_get_by_sku_case_insensitive(self, db_session, make_product):
        make_product(sku="SKU-CASE-001")
        repo = ProductRepository(db_session)
        result = repo.get_by_sku("sku-case-001")
        assert result is not None

    def test_get_by_category(self, db_session, make_product):
        make_product(category="Electronics", status="active")
        make_product(category="Electronics", status="active")
        make_product(category="Apparel", status="active")
        repo = ProductRepository(db_session)
        elec = repo.get_by_category("Electronics")
        assert all(p.category == "Electronics" for p in elec)
        assert len(elec) >= 2

    def test_search_by_name(self, db_session, make_product):
        make_product(product_name="SuperWidget Pro 3000")
        repo = ProductRepository(db_session)
        results = repo.search("superwidget")
        assert any("SuperWidget" in p.product_name for p in results)

    def test_count_by_category(self, db_session, make_product):
        make_product(category="Sports")
        make_product(category="Sports")
        make_product(category="Health")
        repo = ProductRepository(db_session)
        counts = repo.count_by_category()
        assert counts.get("Sports", 0) >= 2
        assert counts.get("Health", 0) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# InventoryRepository
# ═══════════════════════════════════════════════════════════════════════════

class TestInventoryRepository:

    def test_get_by_product_warehouse(self, db_session, make_product):
        from app.database.models.operational.inventory import Inventory
        p = make_product()
        inv = Inventory(product_id=p.id, warehouse_id="WH-EAST-01",
                        quantity_on_hand=100, unit_cost=Decimal("5.00"))
        db_session.add(inv)
        db_session.flush()
        repo = InventoryRepository(db_session)
        result = repo.get_by_product_warehouse(p.id, "WH-EAST-01")
        assert result is not None
        assert result.quantity_on_hand == 100

    def test_get_by_product_all_warehouses(self, db_session, make_product):
        from app.database.models.operational.inventory import Inventory
        p = make_product()
        for wh in ["WH-EAST-01", "WH-WEST-01"]:
            db_session.add(Inventory(product_id=p.id, warehouse_id=wh,
                                     quantity_on_hand=50, unit_cost=Decimal("5.00")))
        db_session.flush()
        repo = InventoryRepository(db_session)
        records = repo.get_by_product(p.id)
        assert len(records) == 2

    def test_get_low_stock(self, db_session, make_product):
        from app.database.models.operational.inventory import Inventory
        p = make_product()
        low = Inventory(product_id=p.id, warehouse_id="WH-LOW-01",
                        quantity_on_hand=3, reorder_point=10, unit_cost=Decimal("5.00"))
        db_session.add(low)
        db_session.flush()
        repo = InventoryRepository(db_session)
        low_stock = repo.get_low_stock()
        assert any(i.product_id == p.id for i in low_stock)


# ═══════════════════════════════════════════════════════════════════════════
# OrderRepository
# ═══════════════════════════════════════════════════════════════════════════

class TestOrderRepository:

    def test_get_by_order_number(self, db_session, make_order):
        order = make_order(order_number="ORD-REPO-0001")
        repo = OrderRepository(db_session)
        result = repo.get_by_order_number("ORD-REPO-0001")
        assert result is not None
        assert result.id == order.id

    def test_get_by_customer(self, db_session, make_order, make_customer):
        cust = make_customer()
        make_order(customer_id=cust.id)
        make_order(customer_id=cust.id)
        repo = OrderRepository(db_session)
        orders = repo.get_by_customer(cust.id)
        assert len(orders) >= 2
        assert all(o.customer_id == cust.id for o in orders)

    def test_get_by_date_range(self, db_session, make_order):
        from datetime import date, timedelta
        today = date.today()
        make_order(order_date=today - timedelta(days=5))
        make_order(order_date=today - timedelta(days=1))
        make_order(order_date=today - timedelta(days=30))
        repo = OrderRepository(db_session)
        recent = repo.get_by_date_range(today - timedelta(days=7), today)
        assert len(recent) >= 2
        assert all(o.order_date >= today - timedelta(days=7) for o in recent)

    def test_get_with_items(self, db_session, make_order):
        order = make_order()
        repo = OrderRepository(db_session)
        result = repo.get_with_items(order.id)
        assert result is not None
        assert len(result.items) >= 1

    def test_count_by_status(self, db_session, make_order):
        make_order(status="delivered")
        make_order(status="delivered")
        make_order(status="pending")
        repo = OrderRepository(db_session)
        counts = repo.count_by_status()
        assert counts.get("delivered", 0) >= 2
        assert counts.get("pending", 0) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# PaymentRepository
# ═══════════════════════════════════════════════════════════════════════════

class TestPaymentRepository:

    def test_get_by_order(self, db_session, make_payment, make_order):
        order = make_order()
        make_payment(order_id=order.id)
        make_payment(order_id=order.id)
        repo = PaymentRepository(db_session)
        payments = repo.get_by_order(order.id)
        assert len(payments) >= 2
        assert all(p.order_id == order.id for p in payments)

    def test_get_total_collected(self, db_session, make_payment, make_order):
        order = make_order()
        make_payment(order_id=order.id, amount=Decimal("50.00"),
                     transaction_type="payment", transaction_status="settled")
        make_payment(order_id=order.id, amount=Decimal("25.00"),
                     transaction_type="payment", transaction_status="settled")
        repo = PaymentRepository(db_session)
        total = repo.get_total_collected(order.id)
        assert total == Decimal("75.00")


# ═══════════════════════════════════════════════════════════════════════════
# PipelineRunRepository
# ═══════════════════════════════════════════════════════════════════════════

class TestPipelineRunRepository:

    def test_get_by_run_number(self, db_session, make_pipeline_run):
        run = make_pipeline_run(run_number="RUN-REPO-0001")
        repo = PipelineRunRepository(db_session)
        result = repo.get_by_run_number("RUN-REPO-0001")
        assert result is not None
        assert result.id == run.id

    def test_get_recent(self, db_session, make_pipeline_run):
        make_pipeline_run(dataset_type="orders")
        make_pipeline_run(dataset_type="customers")
        make_pipeline_run(dataset_type="orders")
        repo = PipelineRunRepository(db_session)
        recent = repo.get_recent(limit=10)
        assert len(recent) >= 3

    def test_get_recent_filter_by_dataset(self, db_session, make_pipeline_run):
        make_pipeline_run(dataset_type="orders")
        make_pipeline_run(dataset_type="products")
        repo = PipelineRunRepository(db_session)
        orders_only = repo.get_recent(dataset_type="orders")
        assert all(r.dataset_type == "orders" for r in orders_only)

    def test_update_status(self, db_session, make_pipeline_run):
        run = make_pipeline_run(status="running")
        repo = PipelineRunRepository(db_session)
        updated = repo.update_status(run.id, status="completed")
        assert updated.status == "completed"

    def test_update_status_with_error(self, db_session, make_pipeline_run):
        run = make_pipeline_run(status="running")
        repo = PipelineRunRepository(db_session)
        repo.update_status(run.id, status="failed",
                           error_message="Validation failed",
                           error_stage="validation")
        db_session.flush()
        assert run.status == "failed"
        assert run.error_message == "Validation failed"
        assert run.error_stage == "validation"

    def test_count_by_status(self, db_session, make_pipeline_run):
        make_pipeline_run(status="completed")
        make_pipeline_run(status="completed")
        make_pipeline_run(status="failed")
        repo = PipelineRunRepository(db_session)
        counts = repo.count_by_status()
        assert counts.get("completed", 0) >= 2
        assert counts.get("failed", 0) >= 1

    def test_create_stage_result(self, db_session, make_pipeline_run):
        run = make_pipeline_run()
        repo = PipelineRunRepository(db_session)
        stage = repo.create_stage_result(
            pipeline_run_id=run.id,
            stage_name="validation",
            stage_order=1,
            status="success",
            input_records=1000,
            output_records=950,
            rejected_records=50,
            warning_records=10,
            quality_score=Decimal("95.00"),
        )
        assert stage.id is not None
        assert stage.stage_name == "validation"

    def test_get_stage_results_ordered(self, db_session, make_pipeline_run):
        run = make_pipeline_run()
        repo = PipelineRunRepository(db_session)
        for order, name in enumerate(["ingestion","validation","cleaning"]):
            repo.create_stage_result(
                pipeline_run_id=run.id,
                stage_name=name,
                stage_order=order,
                status="success",
                input_records=1000,
                output_records=1000 - order * 10,
                rejected_records=order * 10,
                warning_records=0,
            )
        stages = repo.get_stage_results(run.id)
        assert len(stages) == 3
        orders = [s.stage_order for s in stages]
        assert orders == sorted(orders)


# ═══════════════════════════════════════════════════════════════════════════
# AuditLogRepository
# ═══════════════════════════════════════════════════════════════════════════

class TestAuditLogRepository:

    def test_log_event(self, db_session, make_pipeline_run):
        run = make_pipeline_run()
        repo = AuditLogRepository(db_session)
        log = repo.log_event(
            event_type="PIPELINE_STARTED",
            message="Pipeline execution started",
            severity="INFO",
            run_id=run.id,
            stage="ingestion",
        )
        assert log.id is not None
        assert log.event_type == "PIPELINE_STARTED"

    def test_get_by_run(self, db_session, make_pipeline_run):
        run = make_pipeline_run()
        repo = AuditLogRepository(db_session)
        repo.log_event(event_type="PIPELINE_STARTED", message="Started", run_id=run.id)
        repo.log_event(event_type="STAGE_COMPLETED", message="Stage done", run_id=run.id)
        logs = repo.get_by_run(run.id)
        assert len(logs) == 2
        assert all(l.run_id == run.id for l in logs)

    def test_get_by_event_type(self, db_session):
        repo = AuditLogRepository(db_session)
        repo.log_event(event_type="SYSTEM_STARTUP", message="System started", severity="INFO")
        repo.log_event(event_type="SYSTEM_STARTUP", message="System started again", severity="INFO")
        repo.log_event(event_type="API_REQUEST", message="API call", severity="INFO")
        startup_logs = repo.get_by_event_type("SYSTEM_STARTUP")
        assert len(startup_logs) >= 2
        assert all(l.event_type == "SYSTEM_STARTUP" for l in startup_logs)

    def test_bulk_insert_validation_failures(self, db_session, make_pipeline_run):
        import uuid as uuid_lib
        run = make_pipeline_run()
        repo = AuditLogRepository(db_session)
        failures = [
            {
                "id": uuid_lib.uuid4(),
                "pipeline_run_id": run.id,   # pass actual UUID object, not str
                "row_index": i,
                "dataset_type": "orders",
                "rule_code": f"ORD_00{i}",
                "failure_message": f"Failure on row {i}",
                "severity": "error",
            }
            for i in range(5)
        ]
        count = repo.bulk_insert_validation_failures(failures)
        assert count == 5
