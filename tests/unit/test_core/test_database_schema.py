"""
Database schema verification tests.

Verifies the ORM metadata is complete and correct:
- All 15 expected tables are registered
- Critical columns exist on each table
- Expected CHECK constraints are defined
- Expected UNIQUE constraints are defined
- Relationships are bidirectionally wired
- Mixin fields (timestamps, soft-delete, UUID PK) are present

These tests run against the SQLAlchemy metadata object directly —
no database connection needed. They are the cheapest possible sanity
check that the schema is what we designed.
"""

import pytest
from sqlalchemy import inspect as sa_inspect

from app.database.base import Base
import app.database.models  # noqa: F401 — registers all models


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def table_names() -> set[str]:
    """Return all table names registered in Base.metadata."""
    return set(Base.metadata.tables.keys())


def columns_of(table_name: str) -> set[str]:
    """Return column names for a table."""
    return {c.name for c in Base.metadata.tables[table_name].columns}


def constraint_names_of(table_name: str) -> set[str]:
    """Return all constraint names on a table."""
    table = Base.metadata.tables[table_name]
    return {c.name for c in table.constraints if c.name}


def index_names_of(table_name: str) -> set[str]:
    """Return all index names on a table."""
    return {i.name for i in Base.metadata.tables[table_name].indexes if i.name}


# ─────────────────────────────────────────────────────────────────────────────
# Table registration
# ─────────────────────────────────────────────────────────────────────────────

class TestTableRegistration:
    """All 15 tables must be present in Base.metadata."""

    EXPECTED_TABLES = {
        # Operational
        "customers",
        "suppliers",
        "products",
        "inventory",
        "orders",
        "order_items",
        "payments",
        # Pipeline
        "pipeline_runs",
        "ingestion_events",
        "stage_results",
        "reports",
        # Audit
        "audit_logs",
        "validation_failures",
        "cleaning_logs",
        "data_quality_scores",
        # Auth (Phase 10)
        "users",
        "roles",
        "permissions",
        "api_keys",
        "user_sessions",
        "user_roles",
        "role_permissions",
    }

    def test_all_expected_tables_registered(self):
        missing = self.EXPECTED_TABLES - table_names()
        assert missing == set(), f"Missing tables: {sorted(missing)}"

    def test_no_unexpected_tables(self):
        """No rogue tables that aren't in our design."""
        extra = table_names() - self.EXPECTED_TABLES
        assert extra == set(), f"Unexpected tables: {sorted(extra)}"

    def test_table_count(self):
        assert len(table_names()) == 22  # 15 original + 7 auth tables


# ─────────────────────────────────────────────────────────────────────────────
# Column verification (critical fields per table)
# ─────────────────────────────────────────────────────────────────────────────

class TestCustomerColumns:
    def test_uuid_primary_key(self):
        assert "id" in columns_of("customers")

    def test_business_key(self):
        assert "email" in columns_of("customers")

    def test_identity_fields(self):
        cols = columns_of("customers")
        assert "first_name" in cols
        assert "last_name" in cols

    def test_address_fields(self):
        cols = columns_of("customers")
        assert "city" in cols
        assert "country" in cols
        assert "postal_code" in cols

    def test_audit_fields(self):
        cols = columns_of("customers")
        assert "created_at" in cols
        assert "updated_at" in cols
        assert "created_by" in cols

    def test_soft_delete_fields(self):
        cols = columns_of("customers")
        assert "is_deleted" in cols
        assert "deleted_at" in cols

    def test_segment_and_status(self):
        cols = columns_of("customers")
        assert "customer_segment" in cols
        assert "status" in cols


class TestSupplierColumns:
    def test_required_columns(self):
        cols = columns_of("suppliers")
        for col in ("id", "supplier_code", "company_name", "contact_email",
                    "country", "status", "payment_terms", "currency"):
            assert col in cols, f"Missing: {col}"

    def test_rating_column(self):
        assert "rating" in columns_of("suppliers")

    def test_soft_delete(self):
        assert "is_deleted" in columns_of("suppliers")


class TestProductColumns:
    def test_required_columns(self):
        cols = columns_of("products")
        for col in ("id", "sku", "product_name", "category",
                    "unit_price", "unit_cost", "currency", "status"):
            assert col in cols, f"Missing: {col}"

    def test_supplier_fk_column(self):
        assert "supplier_id" in columns_of("products")

    def test_pricing_precision_columns(self):
        cols = columns_of("products")
        assert "tax_rate" in cols
        assert "is_taxable" in cols

    def test_soft_delete(self):
        assert "is_deleted" in columns_of("products")


class TestInventoryColumns:
    def test_required_columns(self):
        cols = columns_of("inventory")
        for col in ("id", "product_id", "warehouse_id",
                    "quantity_on_hand", "reserved_quantity",
                    "reorder_point", "reorder_quantity", "unit_cost"):
            assert col in cols, f"Missing: {col}"

    def test_no_soft_delete(self):
        """Inventory uses physical deletes — no soft delete columns."""
        cols = columns_of("inventory")
        assert "is_deleted" not in cols


class TestOrderColumns:
    def test_required_columns(self):
        cols = columns_of("orders")
        for col in ("id", "order_number", "customer_id", "order_date",
                    "subtotal", "tax_amount", "order_total", "currency",
                    "status", "payment_status"):
            assert col in cols, f"Missing: {col}"

    def test_shipping_address_denormalized(self):
        cols = columns_of("orders")
        assert "shipping_city" in cols
        assert "shipping_country" in cols
        assert "shipping_postal_code" in cols

    def test_soft_delete(self):
        assert "is_deleted" in columns_of("orders")


class TestOrderItemColumns:
    def test_required_columns(self):
        cols = columns_of("order_items")
        for col in ("id", "order_id", "product_id", "quantity",
                    "unit_price_at_sale", "discount_amount", "line_total"):
            assert col in cols, f"Missing: {col}"

    def test_no_soft_delete_on_line_items(self):
        """Line items are cascade-deleted with their order."""
        assert "is_deleted" not in columns_of("order_items")


class TestPaymentColumns:
    def test_required_columns(self):
        cols = columns_of("payments")
        for col in ("id", "order_id", "transaction_type", "transaction_status",
                    "payment_method", "payment_date", "amount", "currency"):
            assert col in cols, f"Missing: {col}"

    def test_gateway_columns(self):
        cols = columns_of("payments")
        assert "payment_gateway" in cols
        assert "gateway_reference" in cols

    def test_card_pci_safe_columns(self):
        """Only last-4 stored — never full PAN."""
        cols = columns_of("payments")
        assert "card_last_four" in cols
        assert "card_brand" in cols
        # Full card number MUST NOT be a column
        assert "card_number" not in cols
        assert "pan" not in cols


class TestPipelineRunColumns:
    def test_required_columns(self):
        cols = columns_of("pipeline_runs")
        for col in ("id", "run_number", "pipeline_name", "dataset_type",
                    "status", "total_records", "valid_records", "loaded_records",
                    "quality_score", "triggered_by"):
            assert col in cols, f"Missing: {col}"

    def test_timing_columns(self):
        cols = columns_of("pipeline_runs")
        assert "started_at" in cols
        assert "completed_at" in cols
        assert "duration_seconds" in cols

    def test_metrics_jsonb_column(self):
        assert "metrics" in columns_of("pipeline_runs")


class TestStageResultColumns:
    def test_required_columns(self):
        cols = columns_of("stage_results")
        for col in ("id", "pipeline_run_id", "stage_name", "stage_order",
                    "status", "input_records", "output_records", "rejected_records"):
            assert col in cols, f"Missing: {col}"

    def test_details_jsonb(self):
        assert "details" in columns_of("stage_results")


class TestAuditLogColumns:
    def test_required_columns(self):
        cols = columns_of("audit_logs")
        for col in ("id", "event_type", "severity", "run_id",
                    "message", "context_data"):
            assert col in cols, f"Missing: {col}"

    def test_actor_columns(self):
        cols = columns_of("audit_logs")
        assert "user_id" in cols
        assert "source_ip" in cols
        assert "request_id" in cols

    def test_entity_columns(self):
        cols = columns_of("audit_logs")
        assert "entity_type" in cols
        assert "entity_id" in cols


class TestDataQualityScoreColumns:
    def test_required_columns(self):
        cols = columns_of("data_quality_scores")
        for col in ("id", "pipeline_run_id", "dataset_type",
                    "total_records", "valid_records", "loaded_records",
                    "quality_score", "threshold_breached", "threshold_warning"):
            assert col in cols, f"Missing: {col}"


# ─────────────────────────────────────────────────────────────────────────────
# Constraint verification
# ─────────────────────────────────────────────────────────────────────────────

class TestUniqueConstraints:
    def test_customers_email_unique(self):
        assert "uq_customers_email" in constraint_names_of("customers")

    def test_suppliers_code_unique(self):
        assert "uq_suppliers_code" in constraint_names_of("suppliers")

    def test_products_sku_unique(self):
        assert "uq_products_sku" in constraint_names_of("products")

    def test_inventory_product_warehouse_unique(self):
        assert "uq_inventory_product_warehouse" in constraint_names_of("inventory")

    def test_orders_order_number_unique(self):
        assert "uq_orders_order_number" in constraint_names_of("orders")

    def test_quality_score_run_id_unique(self):
        assert "uq_quality_scores_run_id" in constraint_names_of("data_quality_scores")


class TestCheckConstraints:
    def test_customers_status_check(self):
        assert "ck_customers_status" in constraint_names_of("customers")

    def test_customers_gender_check(self):
        assert "ck_customers_gender" in constraint_names_of("customers")

    def test_suppliers_status_check(self):
        assert "ck_suppliers_status" in constraint_names_of("suppliers")

    def test_products_price_non_negative(self):
        assert "ck_products_price_non_negative" in constraint_names_of("products")

    def test_inventory_quantity_non_negative(self):
        assert "ck_inventory_quantity_non_negative" in constraint_names_of("inventory")

    def test_orders_status_check(self):
        assert "ck_orders_status" in constraint_names_of("orders")

    def test_order_items_quantity_positive(self):
        assert "ck_order_items_quantity_positive" in constraint_names_of("order_items")

    def test_payments_method_check(self):
        assert "ck_payments_method" in constraint_names_of("payments")

    def test_payments_amount_positive(self):
        assert "ck_payments_amount_positive" in constraint_names_of("payments")

    def test_pipeline_runs_status_check(self):
        assert "ck_pipeline_runs_status" in constraint_names_of("pipeline_runs")

    def test_stage_results_stage_name_check(self):
        assert "ck_stage_results_stage_name" in constraint_names_of("stage_results")

    def test_quality_score_range_check(self):
        assert "ck_quality_scores_range" in constraint_names_of("data_quality_scores")

    def test_audit_log_event_type_check(self):
        assert "ck_audit_logs_event_type" in constraint_names_of("audit_logs")


# ─────────────────────────────────────────────────────────────────────────────
# Foreign key verification (spot check critical FKs)
# ─────────────────────────────────────────────────────────────────────────────

class TestForeignKeys:
    def _get_fk_names(self, table_name: str) -> set[str]:
        table = Base.metadata.tables[table_name]
        return {fk.name for fk in table.foreign_key_constraints if fk.name}

    def test_orders_has_customer_fk(self):
        assert "fk_orders_customer" in self._get_fk_names("orders")

    def test_order_items_has_order_fk(self):
        assert "fk_order_items_order" in self._get_fk_names("order_items")

    def test_order_items_has_product_fk(self):
        assert "fk_order_items_product" in self._get_fk_names("order_items")

    def test_payments_has_order_fk(self):
        assert "fk_payments_order" in self._get_fk_names("payments")

    def test_products_has_supplier_fk(self):
        assert "fk_products_supplier" in self._get_fk_names("products")

    def test_inventory_has_product_fk(self):
        assert "fk_inventory_product" in self._get_fk_names("inventory")

    def test_stage_results_has_pipeline_run_fk(self):
        assert "fk_stage_results_pipeline_run" in self._get_fk_names("stage_results")

    def test_ingestion_events_has_pipeline_run_fk(self):
        assert "fk_ingestion_events_pipeline_run" in self._get_fk_names("ingestion_events")


# ─────────────────────────────────────────────────────────────────────────────
# Index verification (spot check key indexes)
# ─────────────────────────────────────────────────────────────────────────────

class TestIndexes:
    def test_customers_has_email_index(self):
        assert "ix_customers_email" in index_names_of("customers")

    def test_customers_has_composite_country_city_index(self):
        assert "ix_customers_country_city" in index_names_of("customers")

    def test_orders_has_customer_date_composite_index(self):
        assert "ix_orders_customer_date" in index_names_of("orders")

    def test_pipeline_runs_has_dataset_status_composite_index(self):
        assert "ix_pipeline_runs_dataset_status" in index_names_of("pipeline_runs")

    def test_audit_logs_has_event_type_created_composite_index(self):
        assert "ix_audit_logs_event_type_created" in index_names_of("audit_logs")

    def test_validation_failures_has_run_rule_composite_index(self):
        assert "ix_validation_failures_run_rule" in index_names_of("validation_failures")

    def test_payments_has_method_date_composite_index(self):
        assert "ix_payments_method_date" in index_names_of("payments")


# ─────────────────────────────────────────────────────────────────────────────
# ORM relationship verification
# ─────────────────────────────────────────────────────────────────────────────

class TestRelationships:
    def test_customer_has_orders_relationship(self):
        from app.database.models.operational.customers import Customer
        assert hasattr(Customer, "orders")

    def test_order_has_customer_relationship(self):
        from app.database.models.operational.orders import Order
        assert hasattr(Order, "customer")

    def test_order_has_items_relationship(self):
        from app.database.models.operational.orders import Order
        assert hasattr(Order, "items")

    def test_order_item_has_order_relationship(self):
        from app.database.models.operational.orders import OrderItem
        assert hasattr(OrderItem, "order")

    def test_order_item_has_product_relationship(self):
        from app.database.models.operational.orders import OrderItem
        assert hasattr(OrderItem, "product")

    def test_order_has_payments_relationship(self):
        from app.database.models.operational.orders import Order
        assert hasattr(Order, "payments")

    def test_payment_has_order_relationship(self):
        from app.database.models.operational.payments import Payment
        assert hasattr(Payment, "order")

    def test_product_has_supplier_relationship(self):
        from app.database.models.operational.products import Product
        assert hasattr(Product, "supplier")

    def test_supplier_has_products_relationship(self):
        from app.database.models.operational.suppliers import Supplier
        assert hasattr(Supplier, "products")

    def test_product_has_inventory_relationship(self):
        from app.database.models.operational.products import Product
        assert hasattr(Product, "inventory_records")

    def test_inventory_has_product_relationship(self):
        from app.database.models.operational.inventory import Inventory
        assert hasattr(Inventory, "product")

    def test_pipeline_run_has_stage_results_relationship(self):
        from app.database.models.pipeline.pipeline_run import PipelineRun
        assert hasattr(PipelineRun, "stage_results")

    def test_stage_result_has_pipeline_run_relationship(self):
        from app.database.models.pipeline.stage_result import StageResult
        assert hasattr(StageResult, "pipeline_run")

    def test_pipeline_run_has_ingestion_events_relationship(self):
        from app.database.models.pipeline.pipeline_run import PipelineRun
        assert hasattr(PipelineRun, "ingestion_events")


# ─────────────────────────────────────────────────────────────────────────────
# Mixin verification
# ─────────────────────────────────────────────────────────────────────────────

class TestMixins:
    """Verify that all appropriate tables have mixin columns."""

    TABLES_WITH_SOFT_DELETE = {
        "customers", "suppliers", "products", "orders",
    }
    TABLES_WITHOUT_SOFT_DELETE = {
        "inventory", "order_items", "payments",
        "pipeline_runs", "stage_results", "ingestion_events",
        "audit_logs", "validation_failures", "cleaning_logs",
        "data_quality_scores", "reports",
    }

    def test_soft_delete_tables_have_is_deleted(self):
        for table in self.TABLES_WITH_SOFT_DELETE:
            assert "is_deleted" in columns_of(table), f"{table} missing is_deleted"

    def test_non_soft_delete_tables_lack_is_deleted(self):
        for table in self.TABLES_WITHOUT_SOFT_DELETE:
            assert "is_deleted" not in columns_of(table), f"{table} has unexpected is_deleted"

    def test_all_tables_have_created_at(self):
        # Join tables are pure association tables — they have no timestamp columns by design.
        join_tables = {"role_permissions", "user_roles"}
        for table in table_names():
            if table in join_tables:
                continue
            assert "created_at" in columns_of(table), f"{table} missing created_at"

    def test_all_tables_have_uuid_pk(self):
        # Join tables use composite primary keys instead of a single UUID id column.
        join_tables = {"role_permissions", "user_roles"}
        for table in table_names():
            if table in join_tables:
                continue
            assert "id" in columns_of(table), f"{table} missing id (UUID PK)"

    def test_business_tables_have_audit_fields(self):
        audit_tables = {"customers", "suppliers", "products", "orders", "payments"}
        for table in audit_tables:
            cols = columns_of(table)
            assert "created_by" in cols, f"{table} missing created_by"
            assert "updated_by" in cols, f"{table} missing updated_by"


# ─────────────────────────────────────────────────────────────────────────────
# Computed property verification (no DB needed)
# ─────────────────────────────────────────────────────────────────────────────

class TestComputedProperties:
    def test_customer_full_name(self):
        from app.database.models.operational.customers import Customer
        c = Customer(first_name="Ada", last_name="Lovelace", email="a@test.com", country="GB")
        assert c.full_name == "Ada Lovelace"

    def test_product_gross_margin(self):
        from decimal import Decimal
        from app.database.models.operational.products import Product
        p = Product(
            sku="TST-001", product_name="Widget", category="Tools",
            unit_price=Decimal("100.00"), unit_cost=Decimal("40.00"), currency="USD",
        )
        assert p.gross_margin == Decimal("60.00")
        assert p.gross_margin_pct == Decimal("60.00")

    def test_inventory_available_quantity(self):
        import uuid
        from app.database.models.operational.inventory import Inventory
        inv = Inventory(
            product_id=uuid.uuid4(),
            warehouse_id="WH-01",
            quantity_on_hand=100,
            reserved_quantity=25,
            unit_cost=__import__("decimal").Decimal("5.00"),
        )
        assert inv.available_quantity == 75

    def test_inventory_is_low_stock(self):
        import uuid
        from decimal import Decimal
        from app.database.models.operational.inventory import Inventory
        inv = Inventory(
            product_id=uuid.uuid4(), warehouse_id="WH-01",
            quantity_on_hand=5, reorder_point=10, unit_cost=Decimal("1.00"),
        )
        assert inv.is_low_stock is True

    def test_inventory_stock_value(self):
        import uuid
        from decimal import Decimal
        from app.database.models.operational.inventory import Inventory
        inv = Inventory(
            product_id=uuid.uuid4(), warehouse_id="WH-01",
            quantity_on_hand=200, unit_cost=Decimal("3.50"),
        )
        assert inv.stock_value == Decimal("700.00")
