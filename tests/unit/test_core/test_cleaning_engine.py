"""
Integration-style unit tests for CleaningEngine end-to-end.
Tests the complete pipeline and the TransformationEngine contract.
"""
from pathlib import Path
import pandas as pd
import pytest

from app.cleaning.cleaner import CleaningEngine
from app.cleaning.models import CleaningResult
from app.cleaning.cleaning_registry import CleaningRegistry
from app.cleaning.cleaning_executor import CleaningExecutor
from app.validation.models import ValidationResult


def make_validation_result(df: pd.DataFrame, dataset_type: str = "orders") -> ValidationResult:
    return ValidationResult(
        success=True,
        dataset_type=dataset_type,
        valid_df=df.copy(),
        rejected_df=pd.DataFrame(),
        warning_df=pd.DataFrame(),
        quality_score=85.0,
        passed_threshold=True,
    )


class TestCleaningEngineEndToEnd:

    def test_orders_cleaning_succeeds(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = CleaningEngine(session=db_session)
        result = engine.clean_dataframe(df, "orders", original_filename="orders_valid.csv")
        assert result.success is True
        assert isinstance(result.cleaned_df, pd.DataFrame)

    def test_customers_cleaning_succeeds(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "customers_valid.csv", dtype=str)
        engine = CleaningEngine(session=db_session)
        result = engine.clean_dataframe(df, "customers")
        assert result.success is True

    def test_products_cleaning_succeeds(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "products_valid.csv", dtype=str)
        engine = CleaningEngine(session=db_session)
        result = engine.clean_dataframe(df, "products")
        assert result.success is True

    def test_payments_cleaning_succeeds(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "payments_valid.csv", dtype=str)
        engine = CleaningEngine(session=db_session)
        result = engine.clean_dataframe(df, "payments")
        assert result.success is True

    def test_returns_cleaning_result_type(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = CleaningEngine(session=db_session)
        result = engine.clean_dataframe(df, "orders")
        assert isinstance(result, CleaningResult)

    def test_cleaned_df_is_dataframe(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = CleaningEngine(session=db_session)
        result = engine.clean_dataframe(df, "orders")
        assert isinstance(result.cleaned_df, pd.DataFrame)

    def test_original_df_not_modified(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        original = df.copy()
        engine = CleaningEngine(session=db_session)
        engine.clean_dataframe(df, "orders")
        pd.testing.assert_frame_equal(df, original)

    def test_original_df_preserved_in_result(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = CleaningEngine(session=db_session)
        result = engine.clean_dataframe(df, "orders")
        assert len(result.original_df) == len(df)

    def test_cleaning_report_has_metrics(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = CleaningEngine(session=db_session)
        result = engine.clean_dataframe(df, "orders")
        assert result.cleaning_metrics.total_rows_input == len(df)

    def test_engine_never_raises(self, db_session):
        df = pd.DataFrame()
        engine = CleaningEngine(session=db_session)
        result = engine.clean_dataframe(df, "orders")
        assert isinstance(result, CleaningResult)

    def test_duration_recorded(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = CleaningEngine(session=db_session)
        result = engine.clean_dataframe(df, "orders")
        assert result.execution_time > 0

    def test_accepts_validation_result(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        vr = make_validation_result(df, "orders")
        engine = CleaningEngine(session=db_session)
        result = engine.clean(vr)
        assert result.success is True
        assert isinstance(result.cleaned_df, pd.DataFrame)

    def test_validation_result_merges_valid_and_warning(self, db_session):
        valid_df = pd.DataFrame({"order_id": ["ORD-001", "ORD-002"], "status": ["active", "pending"]})
        warning_df = pd.DataFrame({"order_id": ["ORD-003"], "status": ["unknown"]})
        vr = ValidationResult(
            success=True,
            dataset_type="orders",
            valid_df=valid_df,
            warning_df=warning_df,
            rejected_df=pd.DataFrame(),
        )
        engine = CleaningEngine(session=db_session)
        result = engine.clean(vr)
        assert result.row_count <= 3  # may drop rows, but started with 3

    def test_transformation_engine_contract(self, db_session, test_data_dir: Path):
        """Verify CleaningResult is fully compatible with TransformationEngine.transform()."""
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = CleaningEngine(session=db_session)
        result = engine.clean_dataframe(df, "orders")

        # These are the exact fields TransformationEngine.transform() uses
        assert isinstance(result.cleaned_df, pd.DataFrame)
        assert isinstance(result.dataset_type, str)
        assert result.dataset_type == "orders"
        # pipeline_run_id may be None — that is also valid
        assert result.pipeline_run_id is None or isinstance(result.pipeline_run_id, str)

    def test_report_summary_dict(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = CleaningEngine(session=db_session)
        result = engine.clean_dataframe(df, "orders")
        summary = result.cleaning_report.to_summary_dict()
        assert "metrics" in summary
        assert summary["dataset_type"] == "orders"

    def test_suppliers_cleaning(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "suppliers_valid.csv", dtype=str)
        engine = CleaningEngine(session=db_session)
        result = engine.clean_dataframe(df, "suppliers")
        assert result.success is True

    def test_inventory_cleaning(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "inventory_valid.csv", dtype=str)
        engine = CleaningEngine(session=db_session)
        result = engine.clean_dataframe(df, "inventory")
        assert result.success is True


class TestPreviewMode:

    def test_preview_returns_original_data(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = CleaningEngine(session=None, dry_run=True)
        result = engine.preview(df=df, dataset_type="orders")
        assert result.success is True
        # Preview mode: cleaned_df should equal original df
        pd.testing.assert_frame_equal(result.cleaned_df, df)

    def test_preview_records_actions(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        engine = CleaningEngine(session=None)
        result = engine.preview(df=df, dataset_type="orders")
        # Actions list exists (may be empty for clean data, but the report is built)
        assert isinstance(result.cleaning_report.actions, list)

    def test_preview_diff_is_dataframe(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        # Add a dirty row to ensure some actions
        df.loc[0, "order_id"] = "  ORD-001  "  # with whitespace
        engine = CleaningEngine(session=None)
        result = engine.preview(df=df, dataset_type="orders")
        diff = result.diff()
        assert isinstance(diff, pd.DataFrame)


class TestCleaningRegistry:

    def test_build_for_orders(self):
        registry = CleaningRegistry.build_for_dataset("orders")
        assert registry.count() > 0

    def test_build_for_customers(self):
        registry = CleaningRegistry.build_for_dataset("customers")
        assert registry.count() > 0

    def test_null_handler_runs_first(self):
        registry = CleaningRegistry.build_for_dataset("orders")
        ordered = registry.get_ordered()
        assert ordered[0].rule_name == "NullHandler"

    def test_ordered_by_priority(self):
        registry = CleaningRegistry.build_for_dataset("orders")
        priorities = [c.priority for c in registry.get_ordered()]
        assert priorities == sorted(priorities)

    def test_register_custom_cleaner(self):
        from app.cleaning.base_cleaner import BaseCleaningRule
        from app.cleaning.models import CleaningAction

        class MyCleaner(BaseCleaningRule):
            rule_name = "MyCleaner"
            rule_category = "custom"
            def clean(self, df, dataset_type):
                return df, []

        registry = CleaningRegistry()
        registry.register(MyCleaner())
        assert registry.count() == 1


class TestCleaningExecutor:

    def test_execute_returns_tuple(self):
        from app.cleaning.null_handler import NullHandler
        df = pd.DataFrame({"status": [None, "active"]})
        registry = CleaningRegistry()
        registry.register(NullHandler(
            field_strategies={"status": {"null_strategy": "fill_default", "default_value": "unknown"}}
        ))
        executor = CleaningExecutor()
        result_df, actions, stats = executor.execute(df, registry, "orders")
        assert isinstance(result_df, pd.DataFrame)
        assert isinstance(actions, list)
        assert stats.cleaners_executed == 1

    def test_executor_chains_cleaners(self):
        from app.cleaning.null_handler import NullHandler
        from app.cleaning.string_normalizer import StringNormalizer

        df = pd.DataFrame({"status": [None, "  ACTIVE  "]})
        registry = CleaningRegistry()
        registry.register(NullHandler(
            field_strategies={"status": {"null_strategy": "fill_default", "default_value": "unknown"}}
        ))
        registry.register(StringNormalizer(
            field_strategies={"status": {"trim": True, "string_case": "lower"}}
        ))
        executor = CleaningExecutor()
        result_df, actions, stats = executor.execute(df, registry, "orders")
        assert result_df["status"].iloc[0] == "unknown"
        assert result_df["status"].iloc[1] == "active"
        assert stats.cleaners_executed == 2
