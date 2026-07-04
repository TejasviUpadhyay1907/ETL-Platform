"""Unit tests for transformation domain models."""
import pandas as pd
import pytest
from app.transformation.models import (
    TransformationAction, TransformationMetrics,
    TransformationReport, TransformationResult
)


class TestTransformationAction:
    def test_to_dict_has_required_keys(self):
        a = TransformationAction(
            rule_code="FM_001", rule_category="standardization",
            column_name="order_status", source_columns=["status"],
            transformation_type="rename", description="Renamed status",
            rows_affected=100, execution_ms=1.5,
        )
        d = a.to_dict()
        for k in ("rule_code", "rule_category", "column_name", "source_columns",
                  "transformation_type", "description", "rows_affected"):
            assert k in d

    def test_execution_ms_rounded(self):
        a = TransformationAction("R","c","col",[], transformation_type="rename", description="x")
        a.execution_ms = 12.3456789
        d = a.to_dict()
        assert d["execution_ms"] == round(12.3456789, 2)


class TestTransformationMetrics:
    def test_to_dict_has_required_keys(self):
        m = TransformationMetrics(
            total_rows_input=1000, total_rows_output=1000,
            derived_columns_created=3, total_actions=7,
            total_duration_ms=45.2, transformers_executed=5,
        )
        d = m.to_dict()
        assert d["total_rows_input"] == 1000
        assert d["derived_columns_created"] == 3
        assert "total_duration_ms" in d


class TestTransformationReport:
    def _make_report(self):
        return TransformationReport(
            dataset_type="orders",
            original_filename="orders.csv",
            input_columns=["order_id", "status"],
            output_columns=["order_id", "order_status", "order_year"],
            added_columns=["order_year"],
            renamed_columns={"status": "order_status"},
        )

    def test_to_summary_dict(self):
        r = self._make_report()
        d = r.to_summary_dict()
        assert d["dataset_type"] == "orders"
        assert "metrics" in d
        assert d["added_columns"] == ["order_year"]
        assert d["renamed_columns"] == {"status": "order_status"}

    def test_to_lineage_records(self):
        r = self._make_report()
        r.actions = [
            TransformationAction("FM_001","standardization","order_status",
                ["status"], "rename", "Renamed", 100),
        ]
        records = r.to_lineage_records()
        assert len(records) == 1
        assert records[0]["rule_code"] == "FM_001"


class TestTransformationResult:
    def test_row_count(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        r = TransformationResult(success=True, dataset_type="orders", transformed_df=df)
        assert r.row_count == 3

    def test_column_count(self):
        df = pd.DataFrame({"a": [1], "b": [2], "c": [3]})
        r = TransformationResult(success=True, dataset_type="orders", transformed_df=df)
        assert r.column_count == 3

    def test_columns_list(self):
        df = pd.DataFrame({"order_id": ["x"], "total": [1.0]})
        r = TransformationResult(success=True, dataset_type="orders", transformed_df=df)
        assert "order_id" in r.columns

    def test_failure_result(self):
        r = TransformationResult(
            success=False, dataset_type="orders",
            error_code="TRANSFORMATION_UNEXPECTED_ERROR",
            error_message="Something went wrong",
        )
        assert r.row_count == 0
        assert r.success is False

    def test_repr(self):
        df = pd.DataFrame({"a": [1, 2]})
        r = TransformationResult(success=True, dataset_type="orders", transformed_df=df)
        assert "orders" in repr(r)
        assert "2" in repr(r)
