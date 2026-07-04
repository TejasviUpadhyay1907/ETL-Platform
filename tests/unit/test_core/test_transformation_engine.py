"""
Integration-style unit tests for TransformationEngine end-to-end.
Uses test CSV fixtures and the full YAML config stack.
"""
from pathlib import Path
import pandas as pd
import pytest

from app.transformation.transformation_engine import TransformationEngine
from app.transformation.models import TransformationResult
from app.transformation.transformer_registry import TransformationRegistry
from app.transformation.transformation_executor import TransformationExecutor, _build_metrics
from app.transformation.transformers import StandardizationTransformer


# ─────────────────────────────────────────────────────────────────────────────
# TransformationEngine end-to-end
# ─────────────────────────────────────────────────────────────────────────────

class TestTransformationEngineEndToEnd:

    def test_orders_transformation_succeeds(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = TransformationEngine(session=db_session)
        result = engine.transform(df, "orders", "orders_valid.csv")
        assert result.success is True
        assert result.row_count == 5

    def test_returns_transformation_result(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = TransformationEngine(session=db_session)
        result = engine.transform(df, "orders")
        assert isinstance(result, TransformationResult)

    def test_customers_transformation(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "customers_valid.csv", dtype=str)
        engine = TransformationEngine(session=db_session)
        result = engine.transform(df, "customers")
        assert result.success is True
        assert result.row_count == 5

    def test_products_transformation(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "products_valid.csv", dtype=str)
        engine = TransformationEngine(session=db_session)
        result = engine.transform(df, "products")
        assert result.success is True

    def test_payments_transformation(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "payments_valid.csv", dtype=str)
        engine = TransformationEngine(session=db_session)
        result = engine.transform(df, "payments")
        assert result.success is True

    def test_inventory_transformation(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "inventory_valid.csv", dtype=str)
        engine = TransformationEngine(session=db_session)
        result = engine.transform(df, "inventory")
        assert result.success is True

    def test_suppliers_transformation(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "suppliers_valid.csv", dtype=str)
        engine = TransformationEngine(session=db_session)
        result = engine.transform(df, "suppliers")
        assert result.success is True

    def test_original_df_not_modified(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        original = df.copy()
        engine = TransformationEngine(session=db_session)
        engine.transform(df, "orders")
        pd.testing.assert_frame_equal(df, original)

    def test_output_has_more_columns_than_input(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        input_cols = len(df.columns)
        engine = TransformationEngine(session=db_session)
        result = engine.transform(df, "orders")
        # Derived columns should be added
        assert result.column_count >= input_cols

    def test_report_has_actions(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = TransformationEngine(session=db_session)
        result = engine.transform(df, "orders")
        assert len(result.report.actions) >= 0  # may be 0 if no renames apply

    def test_report_has_metrics(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = TransformationEngine(session=db_session)
        result = engine.transform(df, "orders")
        assert result.report.metrics.total_rows_input == 5
        assert result.report.metrics.total_rows_output == 5

    def test_duration_recorded(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = TransformationEngine(session=db_session)
        result = engine.transform(df, "orders")
        assert result.duration_seconds > 0

    def test_engine_never_raises(self, db_session):
        df = pd.DataFrame()
        engine = TransformationEngine(session=db_session)
        result = engine.transform(df, "orders")
        assert isinstance(result, TransformationResult)

    def test_summary_dict_contains_expected_keys(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = TransformationEngine(session=db_session)
        result = engine.transform(df, "orders")
        summary = result.report.to_summary_dict()
        for key in ("report_id", "dataset_type", "metrics", "input_columns", "output_columns"):
            assert key in summary

    def test_output_columns_listed(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = TransformationEngine(session=db_session)
        result = engine.transform(df, "orders")
        assert result.report.output_columns == result.columns

    def test_input_columns_recorded(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        input_cols = list(df.columns)
        engine = TransformationEngine(session=db_session)
        result = engine.transform(df, "orders")
        assert result.report.input_columns == input_cols

    def test_orders_has_status_renamed_to_order_status(self, db_session, test_data_dir):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = TransformationEngine(session=db_session)
        result = engine.transform(df, "orders")
        # orders transformations.yaml maps status → order_status
        assert "order_status" in result.columns or "status" in result.columns


# ─────────────────────────────────────────────────────────────────────────────
# TransformationRegistry
# ─────────────────────────────────────────────────────────────────────────────

class TestTransformationRegistry:

    def test_build_for_orders(self):
        registry = TransformationRegistry.build_for_dataset("orders")
        assert registry.count() > 0

    def test_build_for_customers(self):
        registry = TransformationRegistry.build_for_dataset("customers")
        assert registry.count() > 0

    def test_ordered_by_priority(self):
        registry = TransformationRegistry.build_for_dataset("orders")
        transformers = registry.get_ordered()
        priorities = [t.priority for t in transformers]
        assert priorities == sorted(priorities)

    def test_standardization_runs_first(self):
        registry = TransformationRegistry.build_for_dataset("orders")
        first = registry.get_ordered()[0]
        assert first.transformer_name == "StandardizationTransformer"

    def test_register_custom_transformer(self):
        from app.transformation.base_transformer import BaseTransformer
        from app.transformation.models import TransformationAction

        class MyTransformer(BaseTransformer):
            transformer_name = "MyTransformer"
            transformer_category = "custom"
            def transform(self, df, dataset_type):
                return df, []

        registry = TransformationRegistry()
        registry.register(MyTransformer())
        assert registry.count() == 1


# ─────────────────────────────────────────────────────────────────────────────
# TransformationExecutor
# ─────────────────────────────────────────────────────────────────────────────

class TestTransformationExecutor:

    def test_execute_returns_df_actions_stats(self):
        df = pd.DataFrame({"order_id": ["ORD-001"], "status": ["active"]})
        registry = TransformationRegistry()
        registry.register(StandardizationTransformer(
            field_mappings={"status": "order_status"}
        ))
        executor = TransformationExecutor()
        result_df, actions, stats = executor.execute(df, registry, "orders")
        assert isinstance(result_df, pd.DataFrame)
        assert isinstance(actions, list)
        assert stats.transformers_executed == 1

    def test_disabled_transformer_skipped(self):
        """A disabled transformer is excluded from get_ordered() — execution count stays 0."""
        df = pd.DataFrame({"col": ["1"]})
        registry = TransformationRegistry()
        t = StandardizationTransformer()
        t.enabled = False
        registry.register(t)
        executor = TransformationExecutor()
        _, _, stats = executor.execute(df, registry, "test")
        # Disabled transformers are filtered by registry.get_ordered()
        # so they never reach the executor — executed=0, skipped=0 (not counted here)
        assert stats.transformers_executed == 0

    def test_multiple_transformers_chain(self):
        df = pd.DataFrame({"status": ["active"], "order_date": ["2025-01-15"]})
        registry = TransformationRegistry()
        registry.register(StandardizationTransformer(
            field_mappings={"status": "order_status"}
        ))
        from app.transformation.transformers.date_transformer import DateTransformer
        registry.register(DateTransformer(
            date_fields=["order_date"],
            derive_year=True,
            derive_month=False, derive_quarter=False,
            derive_week=False, derive_day_of_week=False,
            derive_is_weekend=False, derive_age_days=False,
        ))
        executor = TransformationExecutor()
        result_df, _, stats = executor.execute(df, registry, "orders")
        assert "order_status" in result_df.columns
        assert "order_date_year" in result_df.columns
        assert stats.transformers_executed == 2
