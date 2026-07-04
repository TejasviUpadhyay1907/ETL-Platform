"""Unit tests for cleaning domain models."""
import pandas as pd
import pytest
from app.cleaning.models import (
    CleaningAction, CleaningMetrics, CleaningReport, CleaningResult
)


class TestCleaningAction:
    def test_to_dict_has_required_keys(self):
        a = CleaningAction(
            rule_code="MV_FILL", rule_category="missing",
            field_name="order_id", row_index=3,
            original_value=None, cleaned_value="MISSING",
            action_type="fill_null", reason="Required field was null",
        )
        d = a.to_dict()
        for k in ("rule_code", "rule_category", "field_name", "row_index",
                  "original_value", "cleaned_value", "action_type", "reason"):
            assert k in d

    def test_none_original_value_serializes(self):
        a = CleaningAction("R","c","f",0,None,"X","fill_null","r")
        d = a.to_dict()
        assert d["original_value"] is None

    def test_confidence_default(self):
        a = CleaningAction("R","c","f",0,"old","new","trim","r")
        assert a.confidence == 1.0


class TestCleaningMetrics:
    def test_compute_cleaning_pct(self):
        m = CleaningMetrics(total_rows_input=100, rows_modified=25)
        m.compute_cleaning_pct()
        assert m.cleaning_pct == 25.0

    def test_zero_input_rows(self):
        m = CleaningMetrics(total_rows_input=0, rows_modified=0)
        m.compute_cleaning_pct()
        assert m.cleaning_pct == 0.0

    def test_to_dict_keys(self):
        m = CleaningMetrics(total_rows_input=10, total_rows_output=9, nulls_filled=3)
        d = m.to_dict()
        assert d["total_rows_input"] == 10
        assert d["nulls_filled"] == 3
        assert "cleaning_pct" in d


class TestCleaningReport:
    def test_to_summary_dict(self):
        r = CleaningReport(dataset_type="orders", original_filename="orders.csv")
        d = r.to_summary_dict()
        assert d["dataset_type"] == "orders"
        assert "metrics" in d
        assert "total_actions" in d

    def test_to_lineage_records(self):
        r = CleaningReport(dataset_type="orders")
        r.actions = [CleaningAction("R","c","f",0,None,"X","fill_null","reason")]
        records = r.to_lineage_records()
        assert len(records) == 1
        assert records[0]["rule_code"] == "R"


class TestCleaningResult:
    def _make_result(self, rows_out=5):
        cleaned = pd.DataFrame({"order_id": [f"ORD-{i}" for i in range(rows_out)]})
        original = pd.DataFrame({"order_id": [f"ORD-{i}" for i in range(8)]})
        rejected = pd.DataFrame({"order_id": [f"ORD-{i}" for i in range(rows_out, 8)]})
        return CleaningResult(
            cleaned_df=cleaned,
            dataset_type="orders",
            original_df=original,
            rejected_df=rejected,
            success=True,
        )

    def test_row_count(self):
        r = self._make_result(5)
        assert r.row_count == 5

    def test_rows_dropped(self):
        r = self._make_result(5)
        assert r.rows_dropped == 3

    def test_diff_returns_dataframe(self):
        r = self._make_result()
        r.cleaning_report.actions = [
            CleaningAction("R","c","order_id",0,"ORD-OLD","ORD-001","trim","reason")
        ]
        diff = r.diff()
        assert isinstance(diff, pd.DataFrame)
        assert len(diff) == 1

    def test_repr(self):
        r = self._make_result()
        assert "orders" in repr(r)

    def test_transformation_engine_contract(self):
        """TransformationEngine expects cleaned_df to be a pandas DataFrame."""
        r = self._make_result()
        assert isinstance(r.cleaned_df, pd.DataFrame)
        assert isinstance(r.dataset_type, str)
