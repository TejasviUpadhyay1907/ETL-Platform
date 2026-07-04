"""
Comprehensive unit tests for all validation rules.

Every validator is tested independently — no external dependencies.
"""

import pandas as pd
import pytest

from app.validation.models import Severity
from app.validation.rules.schema_validator import SchemaValidator
from app.validation.rules.missing_value_validator import MissingValueValidator
from app.validation.rules.data_type_validator import DataTypeValidator
from app.validation.rules.duplicate_validator import DuplicateValidator
from app.validation.rules.business_rule_validator import BusinessRuleValidator
from app.validation.rules.format_validator import FormatValidator
from app.validation.rules.statistical_validator import StatisticalValidator
from app.validation.rules.categorical_validator import CategoricalValidator
from app.validation.rules.referential_integrity_validator import ReferentialIntegrityValidator


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def orders_df(**overrides):
    data = {
        "order_id":    ["ORD-001", "ORD-002", "ORD-003"],
        "customer_id": ["CUST-001", "CUST-002", "CUST-003"],
        "order_date":  ["2025-01-15", "2025-01-16", "2025-01-17"],
        "order_total": ["250.00", "89.99", "1250.50"],
        "status":      ["delivered", "shipped", "processing"],
        "quantity":    ["2", "1", "5"],
    }
    data.update(overrides)
    return pd.DataFrame(data)


# ─────────────────────────────────────────────────────────────────────────────
# SchemaValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaValidator:

    def test_all_required_present_no_violations(self):
        df = orders_df()
        v = SchemaValidator(expected_columns=list(df.columns), required_columns=list(df.columns))
        violations = v.validate(df, "orders")
        schema_violations = [x for x in violations if "missing" in x.message.lower()]
        assert len(schema_violations) == 0

    def test_missing_required_column(self):
        df = orders_df()
        df = df.drop(columns=["order_id"])
        v = SchemaValidator(expected_columns=["order_id", "customer_id"], required_columns=["order_id"])
        violations = v.validate(df, "orders")
        assert any(viol.field_name == "order_id" for viol in violations)

    def test_duplicate_column_detected(self):
        df = pd.DataFrame({"col_a": [1], "Col_a": [2]})
        v = SchemaValidator(expected_columns=["col_a"])
        violations = v.validate(df, "test")
        dup = [x for x in violations if "duplicate column" in x.message.lower()]
        assert len(dup) >= 1

    def test_empty_dataset_warning(self):
        df = pd.DataFrame({"order_id": [], "order_total": []})
        v = SchemaValidator(expected_columns=["order_id", "order_total"])
        violations = v.validate(df, "orders")
        assert any("zero" in x.message.lower() or "empty" in x.message.lower() for x in violations)

    def test_unexpected_column_warning(self):
        df = orders_df()
        df["extra_col"] = "extra"
        v = SchemaValidator(expected_columns=list(orders_df().columns), allow_extra_columns=False)
        violations = v.validate(df, "orders")
        assert any("extra_col" in (x.field_name or "") for x in violations)


# ─────────────────────────────────────────────────────────────────────────────
# MissingValueValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingValueValidator:

    def test_no_nulls_no_violations(self):
        df = orders_df()
        v = MissingValueValidator(required_fields=["order_id", "customer_id"])
        assert len(v.validate(df, "orders")) == 0

    def test_null_required_field_error(self):
        df = orders_df()
        df.loc[1, "order_id"] = None
        v = MissingValueValidator(required_fields=["order_id"])
        violations = v.validate(df, "orders")
        assert any(x.row_index == 1 and x.severity == Severity.ERROR for x in violations)

    def test_high_null_rate_warning(self):
        df = pd.DataFrame({
            "order_id": ["ORD-001", None, None, None, None, None],
            "status":   ["ok", "ok", "ok", "ok", "ok", "ok"],
        })
        v = MissingValueValidator(null_threshold_pct=20.0)
        violations = v.validate(df, "orders")
        assert any("null" in x.message.lower() for x in violations)

    def test_completely_empty_column_warning(self):
        df = pd.DataFrame({"order_id": ["ORD-001", "ORD-002"], "notes": [None, None]})
        v = MissingValueValidator()
        violations = v.validate(df, "orders")
        assert any("completely empty" in x.message.lower() for x in violations)

    def test_empty_string_treated_as_null(self):
        df = pd.DataFrame({"order_id": ["ORD-001", "  ", "ORD-003"]})
        v = MissingValueValidator(required_fields=["order_id"])
        violations = v.validate(df, "orders")
        assert any(x.row_index == 1 for x in violations)

    def test_empty_dataframe_returns_empty(self):
        df = pd.DataFrame({"order_id": []})
        v = MissingValueValidator(required_fields=["order_id"])
        assert v.validate(df, "orders") == []


# ─────────────────────────────────────────────────────────────────────────────
# DataTypeValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestDataTypeValidator:

    def test_valid_numeric_field(self):
        df = pd.DataFrame({"price": ["10.99", "5.00", "199.99"]})
        v = DataTypeValidator(field_types={"price": "decimal"})
        assert v.validate(df, "products") == []

    def test_invalid_numeric_field(self):
        df = pd.DataFrame({"price": ["10.99", "not_a_number", "199.99"]})
        v = DataTypeValidator(field_types={"price": "decimal"})
        violations = v.validate(df, "products")
        assert any(x.row_index == 1 for x in violations)

    def test_valid_date_field(self):
        df = pd.DataFrame({"order_date": ["2025-01-15", "2025-02-20", "2025-03-10"]})
        v = DataTypeValidator(field_types={"order_date": "date"})
        assert len([x for x in v.validate(df, "orders") if x.row_index is not None]) == 0

    def test_invalid_date_field(self):
        df = pd.DataFrame({"order_date": ["2025-01-15", "not-a-date", "2025-03-10"]})
        v = DataTypeValidator(field_types={"order_date": "date"})
        violations = v.validate(df, "orders")
        row_violations = [x for x in violations if x.row_index is not None]
        assert len(row_violations) >= 1

    def test_valid_email(self):
        df = pd.DataFrame({"email": ["alice@example.com", "bob@test.org"]})
        v = DataTypeValidator(field_types={"email": "email"})
        row_v = [x for x in v.validate(df, "customers") if x.row_index is not None]
        assert len(row_v) == 0

    def test_invalid_email(self):
        df = pd.DataFrame({"email": ["alice@example.com", "not-an-email", "bob@test.org"]})
        v = DataTypeValidator(field_types={"email": "email"})
        violations = [x for x in v.validate(df, "customers") if x.row_index is not None]
        assert len(violations) >= 1

    def test_valid_integer(self):
        df = pd.DataFrame({"quantity": ["1", "5", "10"]})
        v = DataTypeValidator(field_types={"quantity": "integer"})
        assert v.validate(df, "orders") == []

    def test_unknown_column_skipped(self):
        df = pd.DataFrame({"col_a": ["1", "2"]})
        v = DataTypeValidator(field_types={"nonexistent_col": "integer"})
        assert v.validate(df, "test") == []


# ─────────────────────────────────────────────────────────────────────────────
# DuplicateValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestDuplicateValidator:

    def test_no_duplicates_no_violations(self):
        df = orders_df()
        v = DuplicateValidator(key_fields=["order_id"])
        assert v.validate(df, "orders") == []

    def test_exact_duplicate_rows_detected(self):
        df = pd.DataFrame({
            "order_id": ["ORD-001", "ORD-001"],
            "total":    ["100.00", "100.00"],
        })
        v = DuplicateValidator(check_full_row_duplicates=True)
        violations = v.validate(df, "orders")
        assert any(x.rule_category == "duplicate" for x in violations)

    def test_duplicate_key_detected(self):
        df = pd.DataFrame({
            "order_id": ["ORD-001", "ORD-002", "ORD-001"],
            "total":    ["100.00", "200.00", "150.00"],
        })
        v = DuplicateValidator(key_fields=["order_id"])
        violations = v.validate(df, "orders")
        assert any(x.row_index == 2 and x.field_name == "order_id" for x in violations)

    def test_composite_key_duplicate(self):
        df = pd.DataFrame({
            "product_id":   ["P1", "P1", "P2"],
            "warehouse_id": ["WH1", "WH1", "WH1"],
        })
        v = DuplicateValidator(composite_keys=[["product_id", "warehouse_id"]])
        violations = v.validate(df, "inventory")
        assert any("product_id" in (x.field_name or "") for x in violations)

    def test_empty_df_no_violations(self):
        df = pd.DataFrame({"order_id": []})
        v = DuplicateValidator(key_fields=["order_id"])
        assert v.validate(df, "orders") == []


# ─────────────────────────────────────────────────────────────────────────────
# BusinessRuleValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestBusinessRuleValidator:

    def _rules(self):
        return [
            {"rule_code": "ORD_001", "field": "order_id",    "check": "not_null",    "severity": "error"},
            {"rule_code": "ORD_002", "field": "order_total", "check": "greater_than","value": 0, "severity": "error"},
            {"rule_code": "ORD_005", "field": "status",      "check": "in_list",
             "values": ["pending","delivered","shipped","cancelled","processing"], "severity": "error"},
        ]

    def test_valid_data_no_violations(self):
        df = orders_df()
        v = BusinessRuleValidator(rules=self._rules())
        assert v.validate(df, "orders") == []

    def test_null_required_field_violation(self):
        df = orders_df()
        df.loc[0, "order_id"] = None
        v = BusinessRuleValidator(rules=self._rules())
        violations = v.validate(df, "orders")
        assert any(x.rule_code == "ORD_001" and x.row_index == 0 for x in violations)

    def test_negative_total_violation(self):
        df = orders_df()
        df.loc[1, "order_total"] = "-50.00"
        v = BusinessRuleValidator(rules=self._rules())
        violations = v.validate(df, "orders")
        assert any(x.rule_code == "ORD_002" and x.row_index == 1 for x in violations)

    def test_invalid_status_violation(self):
        df = orders_df()
        df.loc[2, "status"] = "unknown_status"
        v = BusinessRuleValidator(rules=self._rules())
        violations = v.validate(df, "orders")
        assert any(x.rule_code == "ORD_005" and x.row_index == 2 for x in violations)

    def test_between_check(self):
        rules = [{"rule_code": "P1", "field": "discount", "check": "between",
                  "min": 0, "max": 100, "severity": "error"}]
        df = pd.DataFrame({"discount": ["10", "50", "150"]})
        v = BusinessRuleValidator(rules=rules)
        violations = v.validate(df, "test")
        assert any(x.row_index == 2 for x in violations)

    def test_min_length_check(self):
        rules = [{"rule_code": "C1", "field": "name", "check": "min_length", "value": 3, "severity": "warning"}]
        df = pd.DataFrame({"name": ["Alice", "Bo", "Carol"]})
        v = BusinessRuleValidator(rules=rules)
        violations = v.validate(df, "test")
        assert any(x.row_index == 1 for x in violations)

    def test_regex_match_check(self):
        rules = [{"rule_code": "R1", "field": "code", "check": "regex_match",
                  "pattern": r"^[A-Z]{3}-\d{3}$", "severity": "error"}]
        df = pd.DataFrame({"code": ["ABC-123", "INVALID", "DEF-456"]})
        v = BusinessRuleValidator(rules=rules)
        violations = v.validate(df, "test")
        assert any(x.row_index == 1 for x in violations)

    def test_valid_email_check(self):
        rules = [{"rule_code": "E1", "field": "email", "check": "valid_email", "severity": "error"}]
        df = pd.DataFrame({"email": ["a@b.com", "not-email", "c@d.com"]})
        v = BusinessRuleValidator(rules=rules)
        violations = v.validate(df, "customers")
        assert any(x.row_index == 1 for x in violations)

    def test_unique_check(self):
        rules = [{"rule_code": "U1", "field": "sku", "check": "unique", "severity": "error"}]
        df = pd.DataFrame({"sku": ["SKU-001", "SKU-002", "SKU-001"]})
        v = BusinessRuleValidator(rules=rules)
        violations = v.validate(df, "products")
        assert any(x.row_index == 2 for x in violations)


# ─────────────────────────────────────────────────────────────────────────────
# FormatValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatValidator:

    def test_clean_fields_no_violations(self):
        df = pd.DataFrame({"name": ["Alice", "Bob"], "email": ["a@b.com", "c@d.com"]})
        v = FormatValidator(check_whitespace_fields=["name"], email_fields=["email"])
        assert v.validate(df, "customers") == []

    def test_leading_whitespace_detected(self):
        df = pd.DataFrame({"name": [" Alice", "Bob"]})
        v = FormatValidator(check_whitespace_fields=["name"])
        violations = v.validate(df, "customers")
        assert any(x.row_index == 0 for x in violations)

    def test_trailing_whitespace_detected(self):
        df = pd.DataFrame({"name": ["Alice ", "Bob"]})
        v = FormatValidator(check_whitespace_fields=["name"])
        violations = v.validate(df, "customers")
        assert any(x.row_index == 0 for x in violations)

    def test_invalid_email_detected(self):
        df = pd.DataFrame({"email": ["good@email.com", "bad-email"]})
        v = FormatValidator(email_fields=["email"])
        violations = v.validate(df, "customers")
        assert any(x.row_index == 1 for x in violations)

    def test_control_chars_detected(self):
        df = pd.DataFrame({"notes": ["good value", "bad\x01value"]})
        v = FormatValidator(check_control_chars=True)
        violations = v.validate(df, "orders")
        assert any(x.row_index == 1 for x in violations)


# ─────────────────────────────────────────────────────────────────────────────
# StatisticalValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestStatisticalValidator:

    def test_builds_column_profiles(self):
        df = pd.DataFrame({"price": ["10.00","20.00","30.00","40.00","50.00"]})
        v = StatisticalValidator()
        v.validate(df, "products")
        assert "price" in v.column_profiles
        profile = v.column_profiles["price"]
        assert profile.non_null_count == 5

    def test_zero_variance_warning(self):
        df = pd.DataFrame({"val": ["5","5","5","5","5"]})
        v = StatisticalValidator()
        violations = v.validate(df, "test")
        assert any("zero variance" in x.message.lower() for x in violations)

    def test_outlier_detection(self):
        df = pd.DataFrame({"price": ["10","11","12","10","11","1000"]})
        v = StatisticalValidator(outlier_iqr_multiplier=1.5)
        violations = v.validate(df, "products")
        assert any("outlier" in x.message.lower() for x in violations)

    def test_null_count_in_profile(self):
        df = pd.DataFrame({"col": ["1", None, "3"]})
        v = StatisticalValidator()
        v.validate(df, "test")
        profile = v.column_profiles["col"]
        assert profile.null_count == 1

    def test_empty_df_no_crash(self):
        df = pd.DataFrame({"col": []})
        v = StatisticalValidator()
        violations = v.validate(df, "test")
        assert isinstance(violations, list)


# ─────────────────────────────────────────────────────────────────────────────
# CategoricalValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestCategoricalValidator:

    def test_valid_categories_no_violations(self):
        df = pd.DataFrame({"status": ["active","inactive","active"]})
        v = CategoricalValidator(categorical_fields={"status": ["active","inactive"]})
        cat_v = [x for x in v.validate(df, "customers") if x.rule_category == "categorical"]
        unknown = [x for x in cat_v if "unknown" in x.message.lower()]
        assert len(unknown) == 0

    def test_unknown_category_warning(self):
        df = pd.DataFrame({"status": ["active","unknown_val","inactive"]})
        v = CategoricalValidator(categorical_fields={"status": ["active","inactive"]})
        violations = v.validate(df, "customers")
        assert any("unknown_val" in (x.actual_value or "") for x in violations)

    def test_case_inconsistency_detected(self):
        df = pd.DataFrame({"status": ["Active","active","ACTIVE"]})
        v = CategoricalValidator(
            categorical_fields={"status": ["active"]},
            check_case_consistency=True,
        )
        violations = v.validate(df, "customers")
        assert any("case" in x.message.lower() for x in violations)


# ─────────────────────────────────────────────────────────────────────────────
# ReferentialIntegrityValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestReferentialIntegrityValidator:

    def test_all_refs_valid_no_violations(self):
        df = pd.DataFrame({"customer_id": ["CUST-001","CUST-002","CUST-003"]})
        v = ReferentialIntegrityValidator(
            references={"customer_id": {"CUST-001","CUST-002","CUST-003"}}
        )
        row_v = [x for x in v.validate(df,"orders") if x.row_index is not None]
        assert len(row_v) == 0

    def test_orphan_record_detected(self):
        df = pd.DataFrame({"customer_id": ["CUST-001","CUST-999","CUST-003"]})
        v = ReferentialIntegrityValidator(
            references={"customer_id": {"CUST-001","CUST-003"}}
        )
        violations = v.validate(df, "orders")
        assert any(x.actual_value == "CUST-999" for x in violations)

    def test_empty_references_no_violations(self):
        df = pd.DataFrame({"customer_id": ["CUST-001"]})
        v = ReferentialIntegrityValidator(references={})
        assert v.validate(df, "orders") == []

    def test_high_orphan_rate_error(self):
        df = pd.DataFrame({"customer_id": ["X","X","X","CUST-001"]})
        v = ReferentialIntegrityValidator(
            references={"customer_id": {"CUST-001"}},
            orphan_rate_threshold_pct=5.0,
        )
        violations = v.validate(df, "orders")
        summary = [x for x in violations if x.row_index is None]
        assert any(x.severity == Severity.ERROR for x in summary)
