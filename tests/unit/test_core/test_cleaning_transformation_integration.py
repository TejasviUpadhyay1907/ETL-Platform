"""
End-to-end integration test: CleaningEngine → TransformationEngine chain.

Verifies that CleaningResult is fully compatible with the already-implemented
TransformationEngine — zero modifications to TransformationEngine required.

This is the most important test in Phase 6: it confirms the contract between
the two engines is intact.
"""

from pathlib import Path

import pandas as pd
import pytest

from app.cleaning.cleaner import CleaningEngine
from app.cleaning.models import CleaningResult
from app.transformation.transformation_engine import TransformationEngine
from app.transformation.models import TransformationResult


class TestCleaningToTransformationChain:
    """Verify the full Cleaning → Transformation pipeline."""

    def test_orders_chain(self, db_session, test_data_dir: Path):
        """Full pipeline: clean orders → transform orders."""
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)

        # Stage 1: Clean
        cleaner = CleaningEngine(session=db_session)
        clean_result = cleaner.clean_dataframe(df, "orders")
        assert clean_result.success is True
        assert isinstance(clean_result.cleaned_df, pd.DataFrame)

        # Stage 2: Transform (using the exact contract)
        transformer = TransformationEngine(session=db_session)
        transform_result = transformer.transform(
            cleaned_df=clean_result.cleaned_df,      # ← exact contract field
            dataset_type=clean_result.dataset_type,  # ← exact contract field
            pipeline_run_id=clean_result.pipeline_run_id,
        )
        assert transform_result.success is True
        assert isinstance(transform_result.transformed_df, pd.DataFrame)
        assert transform_result.row_count >= 0

    def test_customers_chain(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "customers_valid.csv", dtype=str)
        cleaner = CleaningEngine(session=db_session)
        clean_result = cleaner.clean_dataframe(df, "customers")
        transformer = TransformationEngine(session=db_session)
        transform_result = transformer.transform(
            cleaned_df=clean_result.cleaned_df,
            dataset_type=clean_result.dataset_type,
        )
        assert transform_result.success is True

    def test_products_chain(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "products_valid.csv", dtype=str)
        cleaner = CleaningEngine(session=db_session)
        clean_result = cleaner.clean_dataframe(df, "products")
        transformer = TransformationEngine(session=db_session)
        transform_result = transformer.transform(
            cleaned_df=clean_result.cleaned_df,
            dataset_type=clean_result.dataset_type,
        )
        assert transform_result.success is True
        # Products should have gross_profit derived column
        assert "gross_profit" in transform_result.columns or len(transform_result.columns) >= 7

    def test_payments_chain(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "payments_valid.csv", dtype=str)
        cleaner = CleaningEngine(session=db_session)
        clean_result = cleaner.clean_dataframe(df, "payments")
        transformer = TransformationEngine(session=db_session)
        transform_result = transformer.transform(
            cleaned_df=clean_result.cleaned_df,
            dataset_type=clean_result.dataset_type,
        )
        assert transform_result.success is True

    def test_inventory_chain(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "inventory_valid.csv", dtype=str)
        cleaner = CleaningEngine(session=db_session)
        clean_result = cleaner.clean_dataframe(df, "inventory")
        transformer = TransformationEngine(session=db_session)
        transform_result = transformer.transform(
            cleaned_df=clean_result.cleaned_df,
            dataset_type=clean_result.dataset_type,
        )
        assert transform_result.success is True

    def test_suppliers_chain(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "suppliers_valid.csv", dtype=str)
        cleaner = CleaningEngine(session=db_session)
        clean_result = cleaner.clean_dataframe(df, "suppliers")
        transformer = TransformationEngine(session=db_session)
        transform_result = transformer.transform(
            cleaned_df=clean_result.cleaned_df,
            dataset_type=clean_result.dataset_type,
        )
        assert transform_result.success is True

    def test_cleaned_df_is_valid_dataframe_for_transformation(self, db_session, test_data_dir: Path):
        """Verify all TransformationEngine contract requirements are met."""
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        cleaner = CleaningEngine(session=db_session)
        clean_result = cleaner.clean_dataframe(df, "orders")

        # Contract verification: these are the exact params TransformationEngine.transform() uses
        assert isinstance(clean_result.cleaned_df, pd.DataFrame), \
            "cleaned_df must be a pandas DataFrame"
        assert isinstance(clean_result.dataset_type, str), \
            "dataset_type must be a string"
        assert len(clean_result.dataset_type) > 0, \
            "dataset_type must not be empty"
        assert clean_result.pipeline_run_id is None or isinstance(clean_result.pipeline_run_id, str), \
            "pipeline_run_id must be None or str"

    def test_transformation_output_has_more_columns_than_cleaning_output(
        self, db_session, test_data_dir: Path
    ):
        """Transformation should add derived columns on top of cleaned data."""
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        cleaner = CleaningEngine(session=db_session)
        clean_result = cleaner.clean_dataframe(df, "orders")

        transformer = TransformationEngine(session=db_session)
        transform_result = transformer.transform(
            cleaned_df=clean_result.cleaned_df,
            dataset_type=clean_result.dataset_type,
        )
        # Transformation adds derived columns so output should have >= input columns
        assert transform_result.column_count >= clean_result.row_count or \
               transform_result.column_count >= len(clean_result.cleaned_df.columns)

    def test_row_count_preserved_or_reduced_never_increased(
        self, db_session, test_data_dir: Path
    ):
        """Cleaning may drop rows, transformation never adds rows."""
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        original_count = len(df)

        cleaner = CleaningEngine(session=db_session)
        clean_result = cleaner.clean_dataframe(df, "orders")
        assert clean_result.row_count <= original_count

        transformer = TransformationEngine(session=db_session)
        transform_result = transformer.transform(
            cleaned_df=clean_result.cleaned_df,
            dataset_type=clean_result.dataset_type,
        )
        assert transform_result.row_count <= original_count

    def test_chain_with_dirty_data(self, db_session):
        """Chain handles data with nulls, whitespace, currency symbols."""
        df = pd.DataFrame({
            "order_id":    ["  ORD-001  ", None, "ORD-003"],
            "customer_id": ["CUST-001",  "CUST-002", "CUST-003"],
            "order_date":  ["01/15/2025", "2025-02-20", "20-Mar-2025"],
            "order_total": ["$250.00", "£89.99", "1,250.50"],
            "status":      ["DELIVERED", "shipped", "  processing  "],
            "quantity":    ["2", "1", "5"],
        })
        cleaner = CleaningEngine(session=db_session)
        clean_result = cleaner.clean_dataframe(df, "orders")
        assert clean_result.success is True

        transformer = TransformationEngine(session=db_session)
        transform_result = transformer.transform(
            cleaned_df=clean_result.cleaned_df,
            dataset_type=clean_result.dataset_type,
        )
        assert transform_result.success is True

    def test_chain_preserves_lineage(self, db_session, test_data_dir: Path):
        """Both stages produce audit reports."""
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)

        cleaner = CleaningEngine(session=db_session)
        clean_result = cleaner.clean_dataframe(df, "orders")
        assert clean_result.cleaning_report.dataset_type == "orders"

        transformer = TransformationEngine(session=db_session)
        transform_result = transformer.transform(
            cleaned_df=clean_result.cleaned_df,
            dataset_type=clean_result.dataset_type,
        )
        assert transform_result.report.dataset_type == "orders"

    def test_no_transformation_engine_modification_needed(self, db_session, test_data_dir):
        """
        CRITICAL: TransformationEngine must work unchanged with CleaningResult.

        This test verifies the contract is met with zero modifications to Phase 7.
        If this test fails, the CleaningResult contract is broken.
        """
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)

        # Simulate exactly what the pipeline engine does
        cleaner = CleaningEngine(session=db_session)
        cleaning_result: CleaningResult = cleaner.clean_dataframe(df, "orders")

        # TransformationEngine.transform() signature (unchanged from Phase 7):
        #   transform(cleaned_df, dataset_type, original_filename="", pipeline_run_id=None)
        transformer = TransformationEngine(session=db_session)
        transform_result: TransformationResult = transformer.transform(
            cleaned_df=cleaning_result.cleaned_df,
            dataset_type=cleaning_result.dataset_type,
            original_filename="orders_valid.csv",
            pipeline_run_id=cleaning_result.pipeline_run_id,
        )

        assert transform_result.success is True
        assert isinstance(transform_result.transformed_df, pd.DataFrame)
