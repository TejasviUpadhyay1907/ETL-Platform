"""
Comprehensive unit tests for every transformer.
All tests use simple pandas DataFrames — no external dependencies.
"""
import math
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from app.transformation.transformers.standardization_transformer import StandardizationTransformer
from app.transformation.transformers.type_cast_transformer import TypeCastTransformer
from app.transformation.transformers.date_transformer import DateTransformer
from app.transformation.transformers.derived_column_transformer import DerivedColumnTransformer
from app.transformation.transformers.business_rule_transformer import BusinessRuleTransformer
from app.transformation.transformers.categorical_transformer import CategoricalTransformer
from app.transformation.transformers.lookup_transformer import LookupTransformer
from app.transformation.transformers.feature_engineering_transformer import FeatureEngineeringTransformer


# ─────────────────────────────────────────────────────────────────────────────
# StandardizationTransformer
# ─────────────────────────────────────────────────────────────────────────────

class TestStandardizationTransformer:

    def test_rename_columns(self):
        df = pd.DataFrame({"status": ["active"], "order_id": ["ORD-001"]})
        t = StandardizationTransformer(field_mappings={"status": "order_status"})
        result, actions = t.transform(df, "orders")
        assert "order_status" in result.columns
        assert "status" not in result.columns
        assert any(a.transformation_type == "rename" for a in actions)

    def test_no_rename_when_same_name(self):
        df = pd.DataFrame({"order_id": ["ORD-001"]})
        t = StandardizationTransformer(field_mappings={"order_id": "order_id"})
        result, actions = t.transform(df, "orders")
        rename_actions = [a for a in actions if a.transformation_type == "rename"]
        assert len(rename_actions) == 0

    def test_snake_case_normalization(self):
        df = pd.DataFrame({"OrderTotal": [100], "CustomerID": ["C1"]})
        t = StandardizationTransformer(normalize_names=True)
        result, actions = t.transform(df, "orders")
        assert "order_total" in result.columns
        assert "customer_id" in result.columns

    def test_case_insensitive_mapping(self):
        df = pd.DataFrame({"STATUS": ["active"]})
        t = StandardizationTransformer(field_mappings={"status": "order_status"})
        result, actions = t.transform(df, "orders")
        assert "order_status" in result.columns

    def test_empty_df_no_crash(self):
        df = pd.DataFrame({"col": []})
        t = StandardizationTransformer()
        result, actions = t.transform(df, "test")
        assert isinstance(result, pd.DataFrame)

    def test_original_df_not_modified(self):
        df = pd.DataFrame({"status": ["active"]})
        original_cols = list(df.columns)
        t = StandardizationTransformer(field_mappings={"status": "order_status"})
        t.transform(df, "orders")
        assert list(df.columns) == original_cols


# ─────────────────────────────────────────────────────────────────────────────
# TypeCastTransformer
# ─────────────────────────────────────────────────────────────────────────────

class TestTypeCastTransformer:

    def test_cast_numeric(self):
        df = pd.DataFrame({"price": ["10.99", "5.50", "199.99"]})
        t = TypeCastTransformer(type_map={"price": "numeric"})
        result, actions = t.transform(df, "products")
        assert pd.api.types.is_float_dtype(result["price"])
        assert result["price"].iloc[0] == pytest.approx(10.99)

    def test_cast_currency_strips_symbols(self):
        df = pd.DataFrame({"price": ["$10.99", "£5.50", "€199.99"]})
        t = TypeCastTransformer(type_map={"price": "currency"})
        result, _ = t.transform(df, "products")
        assert result["price"].iloc[0] == pytest.approx(10.99)

    def test_cast_date(self):
        df = pd.DataFrame({"order_date": ["2025-01-15", "2025-02-20"]})
        t = TypeCastTransformer(type_map={"order_date": "date"})
        result, actions = t.transform(df, "orders")
        assert pd.api.types.is_datetime64_any_dtype(result["order_date"])

    def test_cast_boolean(self):
        df = pd.DataFrame({"is_active": ["true", "false", "yes", "no"]})
        t = TypeCastTransformer(type_map={"is_active": "boolean"})
        result, _ = t.transform(df, "products")
        assert result["is_active"].iloc[0] == True
        assert result["is_active"].iloc[1] == False
        assert result["is_active"].iloc[2] == True

    def test_cast_integer(self):
        df = pd.DataFrame({"quantity": ["10", "5", "3"]})
        t = TypeCastTransformer(type_map={"quantity": "integer"})
        result, _ = t.transform(df, "orders")
        assert result["quantity"].iloc[0] == 10

    def test_invalid_numeric_becomes_nan(self):
        df = pd.DataFrame({"price": ["10.99", "not_a_number", "5.00"]})
        t = TypeCastTransformer(type_map={"price": "numeric"})
        result, _ = t.transform(df, "products")
        assert pd.isna(result["price"].iloc[1])

    def test_unknown_column_skipped(self):
        df = pd.DataFrame({"col_a": ["1", "2"]})
        t = TypeCastTransformer(type_map={"nonexistent": "numeric"})
        result, actions = t.transform(df, "test")
        assert list(result.columns) == ["col_a"]


# ─────────────────────────────────────────────────────────────────────────────
# DateTransformer
# ─────────────────────────────────────────────────────────────────────────────

class TestDateTransformer:

    def _df(self):
        return pd.DataFrame({
            "order_date": ["2025-01-15", "2025-07-04", "2024-12-25"]
        })

    def test_derives_year(self):
        df = self._df()
        t = DateTransformer(date_fields=["order_date"], derive_year=True,
                            derive_month=False, derive_quarter=False,
                            derive_week=False, derive_day_of_week=False,
                            derive_is_weekend=False, derive_age_days=False)
        result, actions = t.transform(df, "orders")
        assert "order_date_year" in result.columns
        assert result["order_date_year"].iloc[0] == 2025

    def test_derives_month(self):
        df = self._df()
        t = DateTransformer(date_fields=["order_date"], derive_year=False,
                            derive_month=True, derive_quarter=False,
                            derive_week=False, derive_day_of_week=False,
                            derive_is_weekend=False, derive_age_days=False)
        result, _ = t.transform(df, "orders")
        assert result["order_date_month"].iloc[0] == 1

    def test_derives_quarter(self):
        df = self._df()
        t = DateTransformer(date_fields=["order_date"], derive_year=False,
                            derive_month=False, derive_quarter=True,
                            derive_week=False, derive_day_of_week=False,
                            derive_is_weekend=False, derive_age_days=False)
        result, _ = t.transform(df, "orders")
        assert result["order_date_quarter"].iloc[0] == 1

    def test_derives_is_weekend(self):
        # 2025-01-11 is a Saturday
        df = pd.DataFrame({"order_date": ["2025-01-11", "2025-01-13"]})
        t = DateTransformer(date_fields=["order_date"],
                            derive_year=False, derive_month=False,
                            derive_quarter=False, derive_week=False,
                            derive_day_of_week=False, derive_is_weekend=True,
                            derive_age_days=False)
        result, _ = t.transform(df, "orders")
        assert result["order_date_is_weekend"].iloc[0] == True
        assert result["order_date_is_weekend"].iloc[1] == False

    def test_derives_age_days(self):
        today = date.today()
        past = today - timedelta(days=10)
        df = pd.DataFrame({"order_date": [str(past)]})
        t = DateTransformer(date_fields=["order_date"], derive_year=False,
                            derive_month=False, derive_quarter=False,
                            derive_week=False, derive_day_of_week=False,
                            derive_is_weekend=False, derive_age_days=True,
                            reference_date=today)
        result, _ = t.transform(df, "orders")
        assert result["order_date_age_days"].iloc[0] == 10

    def test_unparseable_dates_produce_nat(self):
        df = pd.DataFrame({"order_date": ["not-a-date"]})
        t = DateTransformer(date_fields=["order_date"])
        result, _ = t.transform(df, "orders")
        # No derived columns because all dates are NaT
        assert "order_date_year" not in result.columns or pd.isna(result["order_date_year"].iloc[0])

    def test_unknown_field_skipped(self):
        df = pd.DataFrame({"col_a": ["2025-01-15"]})
        t = DateTransformer(date_fields=["nonexistent_date"])
        result, actions = t.transform(df, "test")
        assert len(actions) == 0


# ─────────────────────────────────────────────────────────────────────────────
# DerivedColumnTransformer
# ─────────────────────────────────────────────────────────────────────────────

class TestDerivedColumnTransformer:

    def test_days_since(self):
        today = date.today()
        past = today - timedelta(days=7)
        df = pd.DataFrame({"order_date": [str(past)]})
        t = DerivedColumnTransformer(
            derived_fields=[{"name": "age_days", "expression": "days_since(order_date)"}]
        )
        result, _ = t.transform(df, "orders")
        assert "age_days" in result.columns
        assert result["age_days"].iloc[0] == 7

    def test_multiply(self):
        df = pd.DataFrame({"quantity": ["5"], "unit_price": ["10.00"]})
        t = DerivedColumnTransformer(
            derived_fields=[{"name": "line_total", "expression": "multiply(quantity, unit_price)"}]
        )
        result, _ = t.transform(df, "orders")
        assert "line_total" in result.columns
        assert result["line_total"].iloc[0] == pytest.approx(50.0)

    def test_subtract(self):
        df = pd.DataFrame({"price": ["100.00"], "cost": ["60.00"]})
        t = DerivedColumnTransformer(
            derived_fields=[{"name": "gross_profit", "expression": "subtract(price, cost)"}]
        )
        result, _ = t.transform(df, "products")
        assert result["gross_profit"].iloc[0] == pytest.approx(40.0)

    def test_divide(self):
        df = pd.DataFrame({"revenue": ["100.00"], "units": ["4"]})
        t = DerivedColumnTransformer(
            derived_fields=[{"name": "avg_price", "expression": "divide(revenue, units)"}]
        )
        result, _ = t.transform(df, "orders")
        assert result["avg_price"].iloc[0] == pytest.approx(25.0)

    def test_divide_by_zero_produces_nan(self):
        df = pd.DataFrame({"revenue": ["100.00"], "units": ["0"]})
        t = DerivedColumnTransformer(
            derived_fields=[{"name": "avg_price", "expression": "divide(revenue, units)"}]
        )
        result, _ = t.transform(df, "orders")
        assert pd.isna(result["avg_price"].iloc[0])

    def test_pct(self):
        df = pd.DataFrame({"profit": ["40.00"], "price": ["100.00"]})
        t = DerivedColumnTransformer(
            derived_fields=[{"name": "margin_pct", "expression": "pct(profit, price)"}]
        )
        result, _ = t.transform(df, "products")
        assert result["margin_pct"].iloc[0] == pytest.approx(40.0)

    def test_if_gte_flag(self):
        df = pd.DataFrame({"order_total": ["1500.00", "200.00", "999.99"]})
        t = DerivedColumnTransformer(
            derived_fields=[{"name": "is_high_value", "expression": "if_gte(order_total, 1000)"}]
        )
        result, _ = t.transform(df, "orders")
        assert result["is_high_value"].iloc[0] == True
        assert result["is_high_value"].iloc[1] == False

    def test_year_expression(self):
        df = pd.DataFrame({"order_date": ["2025-06-15"]})
        t = DerivedColumnTransformer(
            derived_fields=[{"name": "order_year", "expression": "year(order_date)"}]
        )
        result, _ = t.transform(df, "orders")
        assert result["order_year"].iloc[0] == 2025

    def test_comparison_shorthand(self):
        df = pd.DataFrame({"order_total": ["1200.00", "50.00"]})
        t = DerivedColumnTransformer(
            derived_fields=[{"name": "is_high_value", "expression": "order_total >= 1000"}]
        )
        result, _ = t.transform(df, "orders")
        assert result["is_high_value"].iloc[0] == True
        assert result["is_high_value"].iloc[1] == False

    def test_unsupported_expression_skipped(self):
        df = pd.DataFrame({"col": ["1"]})
        t = DerivedColumnTransformer(
            derived_fields=[{"name": "bad_col", "expression": "unsupported_fn(col)"}]
        )
        result, _ = t.transform(df, "test")
        assert "bad_col" not in result.columns

    def test_add_expression(self):
        df = pd.DataFrame({"a": ["10"], "b": ["5"]})
        t = DerivedColumnTransformer(
            derived_fields=[{"name": "total", "expression": "add(a, b)"}]
        )
        result, _ = t.transform(df, "test")
        assert result["total"].iloc[0] == pytest.approx(15.0)


# ─────────────────────────────────────────────────────────────────────────────
# BusinessRuleTransformer
# ─────────────────────────────────────────────────────────────────────────────

class TestBusinessRuleTransformer:

    def test_orders_value_band(self):
        df = pd.DataFrame({"order_total": ["30", "100", "300", "800", "5000"]})
        t = BusinessRuleTransformer(dataset_type="orders")
        result, _ = t.transform(df, "orders")
        assert "order_value_band" in result.columns
        assert result["order_value_band"].iloc[0] == "micro"
        assert result["order_value_band"].iloc[4] == "enterprise"

    def test_orders_avg_unit_price(self):
        df = pd.DataFrame({"order_total": ["100.00"], "quantity": ["4"]})
        t = BusinessRuleTransformer(dataset_type="orders")
        result, _ = t.transform(df, "orders")
        assert "avg_unit_price" in result.columns
        assert result["avg_unit_price"].iloc[0] == pytest.approx(25.0)

    def test_products_gross_profit(self):
        df = pd.DataFrame({"unit_price": ["100.00"], "unit_cost": ["60.00"]})
        t = BusinessRuleTransformer(dataset_type="products")
        result, _ = t.transform(df, "products")
        assert "gross_profit" in result.columns
        assert result["gross_profit"].iloc[0] == pytest.approx(40.0)

    def test_products_margin_pct(self):
        df = pd.DataFrame({"unit_price": ["100.00"], "unit_cost": ["60.00"]})
        t = BusinessRuleTransformer(dataset_type="products")
        result, _ = t.transform(df, "products")
        assert "margin_pct" in result.columns
        assert result["margin_pct"].iloc[0] == pytest.approx(40.0)

    def test_customers_full_name(self):
        df = pd.DataFrame({"first_name": ["Alice"], "last_name": ["Smith"]})
        t = BusinessRuleTransformer(dataset_type="customers")
        result, _ = t.transform(df, "customers")
        assert "full_name" in result.columns
        assert result["full_name"].iloc[0] == "Alice Smith"

    def test_inventory_stock_value(self):
        df = pd.DataFrame({"quantity_on_hand": ["50"], "unit_cost": ["10.00"]})
        t = BusinessRuleTransformer(dataset_type="inventory")
        result, _ = t.transform(df, "inventory")
        assert "stock_value" in result.columns
        assert result["stock_value"].iloc[0] == pytest.approx(500.0)

    def test_inventory_is_low_stock(self):
        df = pd.DataFrame({
            "quantity_on_hand": ["5", "100"],
            "reorder_point": ["10", "10"],
            "unit_cost": ["1.00", "1.00"],
        })
        t = BusinessRuleTransformer(dataset_type="inventory")
        result, _ = t.transform(df, "inventory")
        assert "is_low_stock" in result.columns
        assert result["is_low_stock"].iloc[0] == True
        assert result["is_low_stock"].iloc[1] == False

    def test_payments_days_to_payment(self):
        df = pd.DataFrame({
            "payment_date": ["2025-02-14"],
            "invoice_date": ["2025-02-01"],
        })
        t = BusinessRuleTransformer(dataset_type="payments")
        result, _ = t.transform(df, "payments")
        assert "days_to_payment" in result.columns
        assert result["days_to_payment"].iloc[0] == 13

    def test_no_crash_on_missing_columns(self):
        df = pd.DataFrame({"col_a": ["1"]})
        t = BusinessRuleTransformer(dataset_type="orders")
        result, actions = t.transform(df, "orders")
        assert isinstance(result, pd.DataFrame)


# ─────────────────────────────────────────────────────────────────────────────
# CategoricalTransformer
# ─────────────────────────────────────────────────────────────────────────────

class TestCategoricalTransformer:

    def test_alias_mapping(self):
        df = pd.DataFrame({"status": ["cancelled", "ACTIVE", "inactive"]})
        t = CategoricalTransformer(
            category_mappings={"status": {"cancelled": "canceled", "active": "active_mapped"}}
        )
        result, actions = t.transform(df, "orders")
        assert result["status"].iloc[0] == "canceled"
        assert any(a.transformation_type == "map" for a in actions)

    def test_case_normalization_lower(self):
        df = pd.DataFrame({"status": ["ACTIVE", "Inactive", "PENDING"]})
        t = CategoricalTransformer(case_normalizations={"status": "lower"})
        result, actions = t.transform(df, "orders")
        assert result["status"].iloc[0] == "active"
        assert result["status"].iloc[1] == "inactive"

    def test_case_normalization_upper(self):
        df = pd.DataFrame({"country": ["us", "gb", "ca"]})
        t = CategoricalTransformer(case_normalizations={"country": "upper"})
        result, _ = t.transform(df, "customers")
        assert result["country"].iloc[0] == "US"

    def test_case_normalization_title(self):
        df = pd.DataFrame({"city": ["new york", "los angeles"]})
        t = CategoricalTransformer(case_normalizations={"city": "title"})
        result, _ = t.transform(df, "customers")
        assert result["city"].iloc[0] == "New York"

    def test_empty_df_no_crash(self):
        df = pd.DataFrame({"status": []})
        t = CategoricalTransformer(category_mappings={"status": {"a": "b"}})
        result, _ = t.transform(df, "test")
        assert isinstance(result, pd.DataFrame)


# ─────────────────────────────────────────────────────────────────────────────
# LookupTransformer
# ─────────────────────────────────────────────────────────────────────────────

class TestLookupTransformer:

    def test_country_to_region(self):
        df = pd.DataFrame({"country": ["US", "GB", "JP"]})
        t = LookupTransformer(enrich_country=True, enrich_currency=False)
        result, actions = t.transform(df, "customers")
        assert "region" in result.columns
        assert result["region"].iloc[0] == "North America"
        assert result["region"].iloc[1] == "Europe"
        assert result["region"].iloc[2] == "Asia Pacific"

    def test_unknown_country_is_unknown(self):
        df = pd.DataFrame({"country": ["XX"]})
        t = LookupTransformer(enrich_country=True, enrich_currency=False)
        result, _ = t.transform(df, "customers")
        assert result["region"].iloc[0] == "Unknown"

    def test_currency_symbol(self):
        df = pd.DataFrame({"currency": ["USD", "GBP", "EUR"]})
        t = LookupTransformer(enrich_country=False, enrich_currency=True)
        result, actions = t.transform(df, "payments")
        assert "currency_symbol" in result.columns
        assert result["currency_symbol"].iloc[0] == "$"
        assert result["currency_symbol"].iloc[1] == "£"

    def test_custom_lookup_table(self):
        df = pd.DataFrame({"category_code": ["ELEC", "APRL"]})
        t = LookupTransformer(
            lookup_tables={"category_code": {"ELEC": "Electronics", "APRL": "Apparel"}},
            lookup_targets={"category_code": "category_name"},
            enrich_country=False, enrich_currency=False,
        )
        result, actions = t.transform(df, "products")
        assert "category_name" in result.columns
        assert result["category_name"].iloc[0] == "Electronics"

    def test_no_enrichment_when_column_absent(self):
        df = pd.DataFrame({"col_a": ["1"]})
        t = LookupTransformer(enrich_country=True, enrich_currency=True)
        result, actions = t.transform(df, "test")
        assert "region" not in result.columns
        assert "currency_symbol" not in result.columns


# ─────────────────────────────────────────────────────────────────────────────
# FeatureEngineeringTransformer
# ─────────────────────────────────────────────────────────────────────────────

class TestFeatureEngineeringTransformer:

    def test_high_value_order_flag(self):
        df = pd.DataFrame({"order_total": ["1000.00", "100.00", "499.99"]})
        t = FeatureEngineeringTransformer()
        result, _ = t.transform(df, "orders")
        assert "is_high_value_order" in result.columns
        assert result["is_high_value_order"].iloc[0] == True
        assert result["is_high_value_order"].iloc[1] == False

    def test_active_order_flag(self):
        df = pd.DataFrame({
            "order_total": ["100.00", "200.00"],
            "status": ["pending", "delivered"],
        })
        t = FeatureEngineeringTransformer()
        result, _ = t.transform(df, "orders")
        assert "is_active_order" in result.columns
        assert result["is_active_order"].iloc[0] == True
        assert result["is_active_order"].iloc[1] == False

    def test_premium_customer_flag(self):
        df = pd.DataFrame({"customer_segment": ["vip", "standard", "gold"]})
        t = FeatureEngineeringTransformer()
        result, _ = t.transform(df, "customers")
        assert "is_premium_customer" in result.columns
        assert result["is_premium_customer"].iloc[0] == True
        assert result["is_premium_customer"].iloc[1] == False
        assert result["is_premium_customer"].iloc[2] == True

    def test_inventory_risk_critical(self):
        df = pd.DataFrame({
            "quantity_on_hand": ["0", "5", "25", "200"],
            "reorder_point": ["10", "10", "10", "10"],
        })
        t = FeatureEngineeringTransformer()
        result, _ = t.transform(df, "inventory")
        assert "inventory_risk" in result.columns
        assert result["inventory_risk"].iloc[0] == "critical"
        assert result["inventory_risk"].iloc[1] == "low"

    def test_payment_risk_feature(self):
        df = pd.DataFrame({"days_to_payment": ["10", "45", "75", "100"]})
        t = FeatureEngineeringTransformer()
        result, _ = t.transform(df, "payments")
        assert "payment_risk" in result.columns
        assert result["payment_risk"].iloc[0] == "on_time"
        assert result["payment_risk"].iloc[1] == "late"

    def test_product_margin_tier(self):
        df = pd.DataFrame({"margin_pct": ["5.0", "20.0", "40.0", "70.0"]})
        t = FeatureEngineeringTransformer()
        result, _ = t.transform(df, "products")
        assert "margin_tier" in result.columns
        assert result["margin_tier"].iloc[0] == "low"
        assert result["margin_tier"].iloc[3] == "premium"

    def test_no_crash_empty_df(self):
        df = pd.DataFrame()
        t = FeatureEngineeringTransformer()
        result, actions = t.transform(df, "orders")
        assert isinstance(result, pd.DataFrame)
