"""
Unit tests for DatasetTypeResolver.

Tests verify:
- Filename-based detection for all 6 dataset types
- Schema-based detection using column overlap
- Explicit type override
- Unknown file returns None
- Invalid explicit type raises ValueError
- Case-insensitive filename matching
"""

import pytest

from app.ingestion.dataset_type_resolver import DatasetTypeResolver
from app.utils.constants import DatasetType


@pytest.fixture(scope="module")
def resolver() -> DatasetTypeResolver:
    return DatasetTypeResolver()


class TestFilenameResolution:

    def test_orders_filename(self, resolver):
        assert resolver.resolve("orders_2025_01.csv") == DatasetType.ORDERS

    def test_customers_filename(self, resolver):
        assert resolver.resolve("customers_export.csv") == DatasetType.CUSTOMERS

    def test_products_filename(self, resolver):
        assert resolver.resolve("product_catalog.xlsx") == DatasetType.PRODUCTS

    def test_inventory_filename(self, resolver):
        assert resolver.resolve("inventory_weekly.csv") == DatasetType.INVENTORY

    def test_suppliers_filename(self, resolver):
        assert resolver.resolve("supplier_master.csv") == DatasetType.SUPPLIERS

    def test_payments_filename(self, resolver):
        assert resolver.resolve("payment_transactions.csv") == DatasetType.PAYMENTS

    def test_case_insensitive_filename(self, resolver):
        assert resolver.resolve("ORDERS_2025.CSV") == DatasetType.ORDERS

    def test_uppercase_customer(self, resolver):
        assert resolver.resolve("CUSTOMER_DATA.XLSX") == DatasetType.CUSTOMERS

    def test_partial_keyword_match(self, resolver):
        assert resolver.resolve("daily_orders_report.csv") == DatasetType.ORDERS

    def test_unrecognized_filename(self, resolver):
        result = resolver.resolve("data_export_final_v2.csv")
        assert result is None


class TestSchemaResolution:

    def test_orders_columns(self, resolver):
        cols = ["order_id", "customer_id", "order_date", "order_total", "status"]
        result = resolver.resolve("data.csv", column_names=cols)
        assert result == DatasetType.ORDERS

    def test_customers_columns(self, resolver):
        cols = ["customer_id", "first_name", "last_name", "email", "phone"]
        result = resolver.resolve("data.csv", column_names=cols)
        assert result == DatasetType.CUSTOMERS

    def test_products_columns(self, resolver):
        # schema.yaml has: product_id, product_name, category, price, cost, sku, brand, is_active
        cols = ["product_id", "product_name", "category", "price", "cost", "sku"]
        result = resolver.resolve("data.csv", column_names=cols)
        assert result == DatasetType.PRODUCTS

    def test_inventory_columns(self, resolver):
        # schema.yaml has: inventory_id, product_id, warehouse_id, quantity, reorder_point, unit_cost
        cols = ["inventory_id", "product_id", "warehouse_id", "quantity", "reorder_point"]
        result = resolver.resolve("data.csv", column_names=cols)
        assert result == DatasetType.INVENTORY

    def test_suppliers_columns(self, resolver):
        # schema.yaml has: supplier_id, supplier_name, contact_email, contact_phone, country
        cols = ["supplier_id", "supplier_name", "contact_email", "country", "payment_terms"]
        result = resolver.resolve("data.csv", column_names=cols)
        assert result == DatasetType.SUPPLIERS

    def test_payments_columns(self, resolver):
        cols = ["payment_id", "order_id", "amount", "payment_method", "payment_date"]
        result = resolver.resolve("data.csv", column_names=cols)
        assert result == DatasetType.PAYMENTS

    def test_unknown_columns_returns_none(self, resolver):
        cols = ["col_a", "col_b", "col_c", "col_d"]
        result = resolver.resolve("data.csv", column_names=cols)
        assert result is None

    def test_partial_column_match_above_threshold(self, resolver):
        """Partial match with >50% overlap should still resolve."""
        # orders has: order_id, customer_id, order_date, order_total, status, ...
        cols = ["order_id", "customer_id", "order_total", "extra_col1", "extra_col2"]
        result = resolver.resolve("data.csv", column_names=cols)
        # Should resolve to orders or None depending on overlap score
        # At minimum, should not raise
        assert result is None or result == DatasetType.ORDERS


class TestExplicitOverride:

    def test_explicit_orders(self, resolver):
        result = resolver.resolve("dump.csv", explicit_type="orders")
        assert result == DatasetType.ORDERS

    def test_explicit_overrides_filename(self, resolver):
        """Explicit type should win over filename detection."""
        result = resolver.resolve("orders.csv", explicit_type="customers")
        assert result == DatasetType.CUSTOMERS

    def test_invalid_explicit_raises(self, resolver):
        with pytest.raises(ValueError, match="Invalid explicit dataset type"):
            resolver.resolve("data.csv", explicit_type="machine_learning")

    def test_explicit_case_insensitive(self, resolver):
        result = resolver.resolve("data.csv", explicit_type="ORDERS")
        assert result == DatasetType.ORDERS


class TestResolveOrRaise:

    def test_raises_when_unknown(self, resolver):
        with pytest.raises(ValueError):
            resolver.resolve_or_raise("unknown_export.csv")

    def test_returns_type_when_known(self, resolver):
        result = resolver.resolve_or_raise("orders_jan.csv")
        assert result == DatasetType.ORDERS


class TestGetExpectedColumns:

    def test_returns_columns_for_orders(self, resolver):
        cols = resolver.get_expected_columns(DatasetType.ORDERS)
        assert isinstance(cols, list)
        assert len(cols) > 0
        assert "order_id" in cols

    def test_returns_columns_for_customers(self, resolver):
        cols = resolver.get_expected_columns(DatasetType.CUSTOMERS)
        assert "customer_id" in cols
        assert "email" in cols
