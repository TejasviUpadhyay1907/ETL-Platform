"""Tests for transformation utility modules: FieldMapper and DerivedFieldCalculator."""
import pandas as pd
import pytest


class TestFieldMapper:
    def test_apply_field_mappings_renames(self):
        from app.transformation.field_mapper import apply_field_mappings
        df = pd.DataFrame({"status": ["a"], "order_id": ["1"]})
        result, applied = apply_field_mappings(df, {"status": "order_status"})
        assert "order_status" in result.columns
        assert "status" not in result.columns
        assert applied == {"status": "order_status"}

    def test_no_rename_when_same_name(self):
        from app.transformation.field_mapper import apply_field_mappings
        df = pd.DataFrame({"order_id": ["1"]})
        result, applied = apply_field_mappings(df, {"order_id": "order_id"})
        assert applied == {}
        assert list(result.columns) == ["order_id"]

    def test_case_insensitive_source(self):
        from app.transformation.field_mapper import apply_field_mappings
        df = pd.DataFrame({"STATUS": ["active"]})
        result, applied = apply_field_mappings(df, {"status": "order_status"})
        assert "order_status" in result.columns

    def test_empty_mappings_no_change(self):
        from app.transformation.field_mapper import apply_field_mappings
        df = pd.DataFrame({"col_a": [1], "col_b": [2]})
        result, applied = apply_field_mappings(df, {})
        assert list(result.columns) == ["col_a", "col_b"]
        assert applied == {}


class TestDerivedFieldCalculator:
    def test_compute_multiply(self):
        from app.transformation.derived_field_calculator import compute_derived_fields
        df = pd.DataFrame({"qty": ["5"], "price": ["10.00"]})
        result = compute_derived_fields(
            df,
            [{"name": "line_total", "expression": "multiply(qty, price)"}],
            "orders",
        )
        assert "line_total" in result.columns
        assert result["line_total"].iloc[0] == pytest.approx(50.0)

    def test_compute_days_since(self):
        from app.transformation.derived_field_calculator import compute_derived_fields
        from datetime import date, timedelta
        past = str(date.today() - timedelta(days=5))
        df = pd.DataFrame({"order_date": [past]})
        result = compute_derived_fields(
            df,
            [{"name": "age_days", "expression": "days_since(order_date)"}],
            "orders",
        )
        assert "age_days" in result.columns
        assert result["age_days"].iloc[0] == 5

    def test_multiple_derived_fields(self):
        from app.transformation.derived_field_calculator import compute_derived_fields
        df = pd.DataFrame({"price": ["100.00"], "cost": ["60.00"]})
        result = compute_derived_fields(
            df,
            [
                {"name": "profit", "expression": "subtract(price, cost)"},
                {"name": "margin", "expression": "pct(profit, price)"},
            ],
            "products",
        )
        assert "profit" in result.columns
        assert "margin" in result.columns
        assert result["profit"].iloc[0] == pytest.approx(40.0)
        assert result["margin"].iloc[0] == pytest.approx(40.0)

    def test_empty_fields_returns_same_df(self):
        from app.transformation.derived_field_calculator import compute_derived_fields
        df = pd.DataFrame({"col": ["1"]})
        result = compute_derived_fields(df, [], "test")
        assert list(result.columns) == ["col"]
