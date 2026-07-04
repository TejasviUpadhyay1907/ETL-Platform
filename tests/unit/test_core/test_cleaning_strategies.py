"""Unit tests for every cleaning strategy."""
from decimal import Decimal
import pandas as pd
import pytest

from app.cleaning.null_handler import NullHandler
from app.cleaning.deduplication import DeduplicationHandler
from app.cleaning.string_normalizer import StringNormalizer
from app.cleaning.numeric_cleaner import NumericCleaner
from app.cleaning.date_standardizer import DateStandardizer
from app.cleaning.categorical_cleaner import CategoricalCleaner
from app.cleaning.business_rule_cleaner import BusinessRuleCleaner


# ── NullHandler ────────────────────────────────────────────────────────────

class TestNullHandler:

    def test_fill_default(self):
        df = pd.DataFrame({"status": [None, "active", None]})
        h = NullHandler(field_strategies={"status": {"null_strategy": "fill_default", "default_value": "unknown"}})
        result, actions = h.clean(df, "orders")
        assert result["status"].iloc[0] == "unknown"
        assert result["status"].iloc[2] == "unknown"
        assert len(actions) == 2

    def test_drop_row(self):
        df = pd.DataFrame({"order_id": [None, "ORD-002", "ORD-003"]})
        h = NullHandler(field_strategies={"order_id": {"null_strategy": "drop_row"}})
        result, actions = h.clean(df, "orders")
        assert len(result) == 2
        assert any(a.action_type == "drop_row" for a in actions)

    def test_fill_mean(self):
        df = pd.DataFrame({"price": ["10.0", None, "20.0"]})
        h = NullHandler(field_strategies={"price": {"null_strategy": "fill_mean"}})
        result, actions = h.clean(df, "products")
        assert result["price"].iloc[1] == 15.0
        assert any(a.action_type == "fill_null" for a in actions)

    def test_fill_median(self):
        df = pd.DataFrame({"qty": ["1", "3", None, "5"]})
        h = NullHandler(field_strategies={"qty": {"null_strategy": "fill_median"}})
        result, actions = h.clean(df, "orders")
        assert result["qty"].iloc[2] == 3.0

    def test_fill_mode(self):
        df = pd.DataFrame({"status": ["active", "active", None, "inactive"]})
        h = NullHandler(field_strategies={"status": {"null_strategy": "fill_mode"}})
        result, actions = h.clean(df, "orders")
        assert result["status"].iloc[2] == "active"

    def test_fill_zero(self):
        df = pd.DataFrame({"qty": ["5", None]})
        h = NullHandler(field_strategies={"qty": {"null_strategy": "fill_zero"}})
        result, actions = h.clean(df, "inventory")
        assert result["qty"].iloc[1] == 0

    def test_flag_sentinel(self):
        df = pd.DataFrame({"product_id": [None, "P001"]})
        h = NullHandler(field_strategies={"product_id": {"null_strategy": "flag", "sentinel_value": "MISSING"}})
        result, actions = h.clean(df, "orders")
        assert result["product_id"].iloc[0] == "MISSING"

    def test_forward_fill(self):
        df = pd.DataFrame({"val": ["A", None, None, "B"]})
        h = NullHandler(field_strategies={"val": {"null_strategy": "forward_fill"}})
        result, actions = h.clean(df, "test")
        assert result["val"].iloc[1] == "A"
        assert result["val"].iloc[2] == "A"

    def test_backward_fill(self):
        df = pd.DataFrame({"val": [None, None, "C"]})
        h = NullHandler(field_strategies={"val": {"null_strategy": "backward_fill"}})
        result, actions = h.clean(df, "test")
        assert result["val"].iloc[0] == "C"

    def test_interpolate(self):
        df = pd.DataFrame({"val": ["1", None, "3"]})
        h = NullHandler(field_strategies={"val": {"null_strategy": "interpolate"}})
        result, actions = h.clean(df, "test")
        assert result["val"].iloc[1] == 2.0

    def test_keep_strategy_no_change(self):
        df = pd.DataFrame({"notes": [None, "some notes"]})
        h = NullHandler(field_strategies={"notes": {"null_strategy": "keep"}})
        result, actions = h.clean(df, "orders")
        assert len(actions) == 0

    def test_empty_df_no_crash(self):
        df = pd.DataFrame({"order_id": []})
        h = NullHandler(field_strategies={"order_id": {"null_strategy": "drop_row"}})
        result, actions = h.clean(df, "orders")
        assert len(result) == 0

    def test_original_df_not_modified(self):
        df = pd.DataFrame({"status": [None, "active"]})
        original = df.copy()
        h = NullHandler(field_strategies={"status": {"null_strategy": "fill_default", "default_value": "x"}})
        h.clean(df, "orders")
        pd.testing.assert_frame_equal(df, original)


# ── DeduplicationHandler ───────────────────────────────────────────────────

class TestDeduplicationHandler:

    def test_remove_exact_duplicates(self):
        df = pd.DataFrame({
            "order_id": ["ORD-001", "ORD-002", "ORD-001"],
            "total": ["100", "200", "100"],
        })
        h = DeduplicationHandler()
        result, actions = h.clean(df, "orders")
        assert len(result) == 2
        assert any(a.action_type == "remove_duplicate" for a in actions)

    def test_keep_first(self):
        df = pd.DataFrame({"id": ["A", "B", "A"], "val": ["1", "2", "3"]})
        h = DeduplicationHandler(key_columns=["id"], keep_strategy="keep_first")
        result, actions = h.clean(df, "test")
        assert len(result) == 2
        assert result["val"].iloc[0] == "1"  # first kept

    def test_keep_last(self):
        df = pd.DataFrame({"id": ["A", "B", "A"], "val": ["1", "2", "3"]})
        h = DeduplicationHandler(key_columns=["id"], keep_strategy="keep_last")
        result, actions = h.clean(df, "test")
        assert len(result) == 2

    def test_drop_all(self):
        df = pd.DataFrame({"id": ["A", "B", "A"]})
        h = DeduplicationHandler(key_columns=["id"], keep_strategy="drop_all")
        result, actions = h.clean(df, "test")
        assert len(result) == 1  # only "B" survives

    def test_no_duplicates_no_action(self):
        df = pd.DataFrame({"order_id": ["ORD-001", "ORD-002"]})
        h = DeduplicationHandler(key_columns=["order_id"])
        result, actions = h.clean(df, "orders")
        assert len(result) == 2
        assert len(actions) == 0

    def test_empty_df_no_crash(self):
        df = pd.DataFrame({"order_id": []})
        h = DeduplicationHandler()
        result, actions = h.clean(df, "orders")
        assert len(result) == 0


# ── StringNormalizer ───────────────────────────────────────────────────────

class TestStringNormalizer:

    def test_trim_whitespace(self):
        df = pd.DataFrame({"name": ["  Alice  ", " Bob", "Carol "]})
        h = StringNormalizer(field_strategies={"name": {"trim": True}})
        result, actions = h.clean(df, "customers")
        assert result["name"].iloc[0] == "Alice"
        assert result["name"].iloc[1] == "Bob"

    def test_lowercase(self):
        df = pd.DataFrame({"status": ["ACTIVE", "INACTIVE", "PENDING"]})
        h = StringNormalizer(field_strategies={"status": {"string_case": "lower"}})
        result, _ = h.clean(df, "orders")
        assert result["status"].iloc[0] == "active"

    def test_uppercase(self):
        df = pd.DataFrame({"country": ["us", "gb"]})
        h = StringNormalizer(field_strategies={"country": {"string_case": "upper"}})
        result, _ = h.clean(df, "customers")
        assert result["country"].iloc[0] == "US"

    def test_title_case(self):
        df = pd.DataFrame({"city": ["new york", "los angeles"]})
        h = StringNormalizer(field_strategies={"city": {"string_case": "title"}})
        result, _ = h.clean(df, "customers")
        assert result["city"].iloc[0] == "New York"

    def test_control_chars_removed(self):
        df = pd.DataFrame({"notes": ["hello\x01world", "clean"]})
        h = StringNormalizer(global_control_chars=True)
        result, actions = h.clean(df, "orders")
        assert "\x01" not in result["notes"].iloc[0]
        assert any(a.action_type == "remove_control_chars" for a in actions)

    def test_global_trim_all_string_cols(self):
        df = pd.DataFrame({"a": [" hello "], "b": [" world "]})
        h = StringNormalizer(global_trim=True)
        result, _ = h.clean(df, "test")
        assert result["a"].iloc[0] == "hello"
        assert result["b"].iloc[0] == "world"

    def test_collapse_spaces(self):
        df = pd.DataFrame({"name": ["Alice   Bob"]})
        h = StringNormalizer(field_strategies={"name": {"collapse_spaces": True}})
        result, _ = h.clean(df, "test")
        assert result["name"].iloc[0] == "Alice Bob"


# ── NumericCleaner ─────────────────────────────────────────────────────────

class TestNumericCleaner:

    def test_strip_currency(self):
        df = pd.DataFrame({"price": ["$10.99", "£5.50", "€199.99"]})
        h = NumericCleaner(field_strategies={"price": {"strip_currency": True}})
        result, actions = h.clean(df, "products")
        assert result["price"].iloc[0] == pytest.approx(10.99)
        assert result["price"].iloc[1] == pytest.approx(5.50)

    def test_strip_commas(self):
        df = pd.DataFrame({"total": ["1,234.56", "10,000.00"]})
        h = NumericCleaner(field_strategies={"total": {"strip_currency": True}})
        result, _ = h.clean(df, "orders")
        assert result["total"].iloc[0] == pytest.approx(1234.56)

    def test_negative_as_zero(self):
        df = pd.DataFrame({"qty": ["-5", "10", "-2"]})
        h = NumericCleaner(field_strategies={"qty": {"negative_as_zero": True}})
        result, actions = h.clean(df, "inventory")
        assert result["qty"].iloc[0] == 0.0
        assert result["qty"].iloc[2] == 0.0
        assert any(a.action_type == "clip_outlier" for a in actions)

    def test_rounding(self):
        df = pd.DataFrame({"price": ["10.9999", "5.0001"]})
        h = NumericCleaner(field_strategies={"price": {"strip_currency": True, "rounding": 2}})
        result, _ = h.clean(df, "products")
        assert result["price"].iloc[0] == pytest.approx(11.0)

    def test_clip_outliers(self):
        df = pd.DataFrame({"val": ["10", "11", "12", "10", "11", "1000"]})
        h = NumericCleaner(field_strategies={"val": {"clip_outliers": True}})
        result, actions = h.clean(df, "test")
        assert result["val"].iloc[5] < 1000
        assert any(a.action_type == "clip_outlier" for a in actions)

    def test_percentage_parse(self):
        df = pd.DataFrame({"discount": ["10%", "25%", "5%"]})
        h = NumericCleaner(field_strategies={"discount": {"percentage_parse": True}})
        result, _ = h.clean(df, "orders")
        assert result["discount"].iloc[0] == pytest.approx(10.0)

    def test_unknown_column_skipped(self):
        df = pd.DataFrame({"col_a": ["1.0"]})
        h = NumericCleaner(field_strategies={"nonexistent": {"strip_currency": True}})
        result, actions = h.clean(df, "test")
        assert len(actions) == 0


# ── DateStandardizer ───────────────────────────────────────────────────────

class TestDateStandardizer:

    def test_standardize_iso(self):
        df = pd.DataFrame({"order_date": ["01/15/2025", "2025-02-20", "20-Mar-2025"]})
        h = DateStandardizer(field_strategies={"order_date": {"standardize_date": True}})
        result, actions = h.clean(df, "orders")
        assert result["order_date"].iloc[0] == "2025-01-15"
        assert result["order_date"].iloc[1] == "2025-02-20"

    def test_already_iso_no_unnecessary_action(self):
        df = pd.DataFrame({"order_date": ["2025-01-15"]})
        h = DateStandardizer(field_strategies={"order_date": {"standardize_date": True}})
        result, actions = h.clean(df, "orders")
        # No action needed if already ISO
        assert result["order_date"].iloc[0] == "2025-01-15"

    def test_unparseable_date_flags_action(self):
        df = pd.DataFrame({"order_date": ["not-a-date", "2025-01-15"]})
        h = DateStandardizer(field_strategies={"order_date": {"standardize_date": True}})
        result, actions = h.clean(df, "orders")
        assert any(a.confidence == 0.0 for a in actions)

    def test_impossible_date_dropped(self):
        df = pd.DataFrame({"order_date": ["1800-01-01", "2025-01-15"]})
        h = DateStandardizer(field_strategies={
            "order_date": {"standardize_date": True, "remove_impossible": True}
        })
        result, actions = h.clean(df, "orders")
        assert len(result) == 1
        assert any(a.action_type == "drop_row" for a in actions)

    def test_empty_df_no_crash(self):
        df = pd.DataFrame({"order_date": []})
        h = DateStandardizer(field_strategies={"order_date": {"standardize_date": True}})
        result, actions = h.clean(df, "orders")
        assert len(result) == 0


# ── CategoricalCleaner ─────────────────────────────────────────────────────

class TestCategoricalCleaner:

    def test_case_normalization(self):
        df = pd.DataFrame({"status": ["ACTIVE", "Inactive", "PENDING"]})
        h = CategoricalCleaner(field_strategies={"status": {"string_case": "lower"}})
        result, actions = h.clean(df, "orders")
        assert result["status"].iloc[0] == "active"

    def test_alias_mapping(self):
        df = pd.DataFrame({"status": ["cancelled", "ACTIVE"]})
        h = CategoricalCleaner(field_strategies={
            "status": {"alias_map": {"cancelled": "canceled"}}
        })
        result, actions = h.clean(df, "orders")
        assert result["status"].iloc[0] == "canceled"
        assert any(a.action_type == "map_category" for a in actions)

    def test_unknown_flag(self):
        df = pd.DataFrame({"status": ["active", "xyz_unknown", "inactive"]})
        h = CategoricalCleaner(field_strategies={
            "status": {
                "allowed_values": ["active", "inactive"],
                "unknown_strategy": "flag",
                "default_value": "other",
            }
        })
        result, actions = h.clean(df, "orders")
        assert result["status"].iloc[1] == "other"
        assert any(a.action_type == "map_category" for a in actions)

    def test_unknown_drop(self):
        df = pd.DataFrame({"status": ["active", "xyz_bad"]})
        h = CategoricalCleaner(field_strategies={
            "status": {
                "allowed_values": ["active"],
                "unknown_strategy": "drop",
            }
        })
        result, actions = h.clean(df, "orders")
        assert len(result) == 1
        assert any(a.action_type == "drop_row" for a in actions)


# ── BusinessRuleCleaner ────────────────────────────────────────────────────

class TestBusinessRuleCleaner:

    def test_value_normalization(self):
        df = pd.DataFrame({"status": ["ACTIVE", "Active", "active", "A"]})
        h = BusinessRuleCleaner(field_rules={
            "status": [{"rule_code": "BIZ_001",
                        "match": ["ACTIVE", "Active", "A"],
                        "replace": "active",
                        "description": "Normalize active status"}]
        })
        result, actions = h.clean(df, "customers")
        assert result["status"].iloc[0] == "active"
        assert result["status"].iloc[1] == "active"
        assert result["status"].iloc[3] == "active"
        assert len(actions) == 3

    def test_no_match_no_change(self):
        df = pd.DataFrame({"status": ["active", "inactive"]})
        h = BusinessRuleCleaner(field_rules={
            "status": [{"match": ["pending"], "replace": "waiting"}]
        })
        result, actions = h.clean(df, "orders")
        assert result["status"].tolist() == ["active", "inactive"]
        assert len(actions) == 0

    def test_multiple_rules(self):
        df = pd.DataFrame({"status": ["PAID", "ACTIVE", "cancelled"]})
        h = BusinessRuleCleaner(field_rules={
            "status": [
                {"match": ["PAID", "Paid", "paid"], "replace": "paid"},
                {"match": ["ACTIVE", "Active"], "replace": "active"},
            ]
        })
        result, actions = h.clean(df, "payments")
        assert result["status"].iloc[0] == "paid"
        assert result["status"].iloc[1] == "active"

    def test_unknown_column_skipped(self):
        df = pd.DataFrame({"col_a": ["val"]})
        h = BusinessRuleCleaner(field_rules={"nonexistent": [{"match": ["x"], "replace": "y"}]})
        result, actions = h.clean(df, "test")
        assert len(actions) == 0
