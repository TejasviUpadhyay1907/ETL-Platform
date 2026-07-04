"""
Targeted coverage tests for StageExecutor individual stage methods.

These tests call each stage method directly with minimal mocks so we cover
the lines in stage_executor.py that the full-pipeline tests miss
(lines 43–244 — the per-stage run_* methods and error paths).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.pipeline.context import PipelineContext
from app.pipeline.models import PipelineStageResult, RetryPolicy, StageName
from app.pipeline.stage_executor import EventEmitter, StageExecutor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx() -> PipelineContext:
    return PipelineContext(
        pipeline_run_id=str(uuid.uuid4()),
        pipeline_name="orders_pipeline",
        dataset_type="orders",
        source_file_path="/tmp/orders.csv",
        original_filename="orders.csv",
    )


def _make_df(rows: int = 3) -> pd.DataFrame:
    return pd.DataFrame({
        "id":    [str(uuid.uuid4()) for _ in range(rows)],
        "name":  [f"Row {i}" for i in range(rows)],
        "value": [float(i) for i in range(rows)],
    })


# ---------------------------------------------------------------------------
# run_ingestion
# ---------------------------------------------------------------------------

class TestRunIngestion:

    def test_no_source_file_returns_failed(self, db_session):
        se = StageExecutor(db_session)
        ee = EventEmitter(db_session)
        ctx = PipelineContext(
            pipeline_run_id=str(uuid.uuid4()),
            pipeline_name="orders_pipeline",
            dataset_type="orders",
            # deliberately no source_file_path
        )
        result = se.run_ingestion(ctx, ee)
        assert result.stage_name == StageName.INGESTION
        assert result.status == "failed"
        assert result.error_message is not None

    def test_ingestion_success_path(self, db_session):
        """Mock IngestionService.ingest() to return a successful result."""
        from app.ingestion.models import (
            IngestionResult, IngestionStatus, Dataset, DatasetSchema, FileMetadata
        )
        from pathlib import Path

        df = _make_df(3)
        meta = FileMetadata(
            original_filename="orders.csv",
            stored_filename="orders_stored.csv",
            file_path=Path("/tmp/orders.csv"),
            file_extension="csv",
            file_size_bytes=512,
            dataset_type="orders",
        )
        schema = DatasetSchema(
            column_names=list(df.columns),
            column_dtypes={c: "object" for c in df.columns},
            row_count=3,
            column_count=len(df.columns),
        )
        dataset = Dataset(
            metadata=meta,
            dataframe=df,
            schema=schema,
            ingestion_event_id="evt-999",
            reader_used="CSVReader",
        )
        mock_result = IngestionResult(
            success=True,
            status=IngestionStatus.PROCESSED,
            dataset=dataset,
            ingestion_event_id="evt-999",
            file_metadata=meta,
        )

        se = StageExecutor(db_session)
        ee = EventEmitter(db_session)
        ctx = _ctx()

        with patch("app.ingestion.ingestion_service.IngestionService.ingest",
                   return_value=mock_result):
            result = se.run_ingestion(ctx, ee)

        assert result.stage_name == StageName.INGESTION
        assert result.status == "success"
        assert result.output_records == 3

    def test_ingestion_failure_result(self, db_session):
        """IngestionService returns a failure — stage should be 'failed'."""
        from app.ingestion.models import IngestionResult, IngestionStatus

        mock_result = IngestionResult(
            success=False,
            status=IngestionStatus.REJECTED,
            error_message="Unsupported file type",
            error_code="UNSUPPORTED_FORMAT",
        )

        se = StageExecutor(db_session)
        ee = EventEmitter(db_session)
        ctx = _ctx()

        with patch("app.ingestion.ingestion_service.IngestionService.ingest",
                   return_value=mock_result):
            result = se.run_ingestion(ctx, ee)

        assert result.status == "failed"
        assert "Unsupported" in (result.error_message or "")

    def test_ingestion_exception_caught(self, db_session):
        """If IngestionService raises, stage_result.status should be 'failed'."""
        se = StageExecutor(db_session)
        ee = EventEmitter(db_session)
        ctx = _ctx()

        with patch("app.ingestion.ingestion_service.IngestionService.ingest",
                   side_effect=RuntimeError("Disk full")):
            result = se.run_ingestion(ctx, ee)

        assert result.status == "failed"
        assert "Disk full" in (result.error_message or "")


# ---------------------------------------------------------------------------
# run_validation
# ---------------------------------------------------------------------------

class TestRunValidation:

    def _mock_val_result(self, df: pd.DataFrame):
        from app.validation.models import (
            ValidationResult, ValidationReport, QualityScore
        )
        qs = QualityScore(
            completeness=95.0, validity=90.0, consistency=88.0,
            uniqueness=100.0, integrity=100.0, timeliness=100.0,
            total_records=len(df), valid_records=len(df),
        )
        qs.compute_overall()
        return ValidationResult(
            success=True,
            dataset_type="orders",
            valid_df=df,
            rejected_df=pd.DataFrame(),
            warning_df=pd.DataFrame(),
            quality_score=qs.overall_score,
            letter_grade=qs.letter_grade,
            passed_threshold=True,
            report=ValidationReport(dataset_type="orders", quality_score=qs),
        )

    def _mock_ingestion(self, df: pd.DataFrame):
        from app.ingestion.models import (
            IngestionResult, IngestionStatus, Dataset, DatasetSchema, FileMetadata
        )
        from pathlib import Path
        meta = FileMetadata(
            original_filename="o.csv", stored_filename="o.csv",
            file_path=Path("/tmp/o.csv"), file_extension="csv",
            file_size_bytes=100, dataset_type="orders",
        )
        schema = DatasetSchema(
            column_names=list(df.columns),
            column_dtypes={c: "object" for c in df.columns},
            row_count=len(df), column_count=len(df.columns),
        )
        dataset = Dataset(
            metadata=meta, dataframe=df, schema=schema,
            ingestion_event_id="evt-1", reader_used="CSVReader",
        )
        return IngestionResult(
            success=True, status=IngestionStatus.PROCESSED,
            dataset=dataset, ingestion_event_id="evt-1", file_metadata=meta,
        )

    def test_validation_success(self, db_session):
        df = _make_df(3)
        ing_result = self._mock_ingestion(df)
        val_result = self._mock_val_result(df)

        se = StageExecutor(db_session)
        ee = EventEmitter(db_session)
        ctx = _ctx()

        with patch("app.validation.validator.ValidationEngine.validate",
                   return_value=val_result):
            result = se.run_validation(ctx, ing_result, ee)

        assert result.stage_name == StageName.VALIDATION
        assert result.status in ("success", "warning")
        assert result.quality_score is not None

    def test_validation_exception_caught(self, db_session):
        df = _make_df(2)
        ing_result = self._mock_ingestion(df)

        se = StageExecutor(db_session)
        ee = EventEmitter(db_session)
        ctx = _ctx()

        with patch("app.validation.validator.ValidationEngine.validate",
                   side_effect=RuntimeError("Schema error")):
            result = se.run_validation(ctx, ing_result, ee)

        assert result.status == "failed"
        assert "Schema error" in (result.error_message or "")


# ---------------------------------------------------------------------------
# run_cleaning
# ---------------------------------------------------------------------------

class TestRunCleaning:

    def _mock_val_result(self, df: pd.DataFrame):
        from app.validation.models import (
            ValidationResult, ValidationReport, QualityScore
        )
        qs = QualityScore(
            completeness=95.0, validity=90.0, consistency=88.0,
            uniqueness=100.0, integrity=100.0, timeliness=100.0,
            total_records=len(df), valid_records=len(df),
        )
        qs.compute_overall()
        return ValidationResult(
            success=True, dataset_type="orders",
            valid_df=df, rejected_df=pd.DataFrame(), warning_df=pd.DataFrame(),
            quality_score=qs.overall_score, letter_grade=qs.letter_grade,
            passed_threshold=True,
            report=ValidationReport(dataset_type="orders", quality_score=qs),
        )

    def _mock_cleaning_result(self, df: pd.DataFrame):
        from app.cleaning.models import CleaningResult, CleaningReport, CleaningMetrics
        return CleaningResult(
            cleaned_df=df.copy(),
            dataset_type="orders",
            cleaning_report=CleaningReport(dataset_type="orders"),
            cleaning_metrics=CleaningMetrics(
                total_rows_input=len(df), total_rows_output=len(df)
            ),
            success=True,
            original_df=df.copy(),
        )

    def test_cleaning_success(self, db_session):
        df = _make_df(3)
        val_result = self._mock_val_result(df)
        clean_result = self._mock_cleaning_result(df)

        se = StageExecutor(db_session)
        ee = EventEmitter(db_session)
        ctx = _ctx()

        with patch("app.cleaning.cleaner.CleaningEngine.clean",
                   return_value=clean_result):
            result = se.run_cleaning(ctx, val_result, ee)

        assert result.stage_name == StageName.CLEANING
        assert result.status == "success"
        assert result.output_records == 3

    def test_cleaning_failure_result(self, db_session):
        from app.cleaning.models import CleaningResult, CleaningReport, CleaningMetrics
        df = _make_df(2)
        val_result = self._mock_val_result(df)
        bad_result = CleaningResult(
            cleaned_df=df.copy(),
            dataset_type="orders",
            cleaning_report=CleaningReport(dataset_type="orders"),
            cleaning_metrics=CleaningMetrics(total_rows_input=2, total_rows_output=2),
            success=False,
            original_df=df.copy(),
            errors=["Missing required columns"],
        )

        se = StageExecutor(db_session)
        ee = EventEmitter(db_session)
        ctx = _ctx()

        with patch("app.cleaning.cleaner.CleaningEngine.clean", return_value=bad_result):
            result = se.run_cleaning(ctx, val_result, ee)

        assert result.status == "failed"

    def test_cleaning_exception_caught(self, db_session):
        df = _make_df(2)
        val_result = self._mock_val_result(df)

        se = StageExecutor(db_session)
        ee = EventEmitter(db_session)
        ctx = _ctx()

        with patch("app.cleaning.cleaner.CleaningEngine.clean",
                   side_effect=RuntimeError("Memory error")):
            result = se.run_cleaning(ctx, val_result, ee)

        assert result.status == "failed"
        assert "Memory error" in (result.error_message or "")


# ---------------------------------------------------------------------------
# run_transformation
# ---------------------------------------------------------------------------

class TestRunTransformation:

    def _mock_cleaning_result(self, df: pd.DataFrame):
        from app.cleaning.models import CleaningResult, CleaningReport, CleaningMetrics
        return CleaningResult(
            cleaned_df=df.copy(), dataset_type="orders",
            cleaning_report=CleaningReport(dataset_type="orders"),
            cleaning_metrics=CleaningMetrics(
                total_rows_input=len(df), total_rows_output=len(df)
            ),
            success=True, original_df=df.copy(),
        )

    def _mock_trans_result(self, df: pd.DataFrame):
        from app.transformation.models import (
            TransformationResult, TransformationReport, TransformationMetrics
        )
        metrics = TransformationMetrics(
            total_rows_input=len(df), total_rows_output=len(df)
        )
        report = TransformationReport(
            dataset_type="orders", metrics=metrics,
            input_columns=list(df.columns), output_columns=list(df.columns),
        )
        return TransformationResult(
            success=True, dataset_type="orders",
            transformed_df=df.copy(), report=report,
        )

    def test_transformation_success(self, db_session):
        df = _make_df(3)
        clean_result = self._mock_cleaning_result(df)
        trans_result = self._mock_trans_result(df)

        se = StageExecutor(db_session)
        ee = EventEmitter(db_session)
        ctx = _ctx()

        with patch("app.transformation.transformation_engine.TransformationEngine.transform",
                   return_value=trans_result):
            result = se.run_transformation(ctx, clean_result, ee)

        assert result.stage_name == StageName.TRANSFORMATION
        assert result.status == "success"
        assert result.output_records == 3

    def test_transformation_failure_result(self, db_session):
        from app.transformation.models import (
            TransformationResult, TransformationReport, TransformationMetrics
        )
        df = _make_df(2)
        clean_result = self._mock_cleaning_result(df)
        metrics = TransformationMetrics(total_rows_input=2, total_rows_output=0)
        report = TransformationReport(
            dataset_type="orders", metrics=metrics,
            input_columns=list(df.columns), output_columns=[],
        )
        bad_result = TransformationResult(
            success=False, dataset_type="orders",
            transformed_df=pd.DataFrame(), report=report,
            error_message="Type cast failure",
        )

        se = StageExecutor(db_session)
        ee = EventEmitter(db_session)
        ctx = _ctx()

        with patch("app.transformation.transformation_engine.TransformationEngine.transform",
                   return_value=bad_result):
            result = se.run_transformation(ctx, clean_result, ee)

        assert result.status == "failed"

    def test_transformation_exception_caught(self, db_session):
        df = _make_df(2)
        clean_result = self._mock_cleaning_result(df)

        se = StageExecutor(db_session)
        ee = EventEmitter(db_session)
        ctx = _ctx()

        with patch("app.transformation.transformation_engine.TransformationEngine.transform",
                   side_effect=ValueError("Bad column")):
            result = se.run_transformation(ctx, clean_result, ee)

        assert result.status == "failed"
        assert "Bad column" in (result.error_message or "")


# ---------------------------------------------------------------------------
# EventEmitter additional paths
# ---------------------------------------------------------------------------

class TestEventEmitterEdgeCases:

    def test_emit_retry_started(self, db_session):
        ee = EventEmitter(db_session)
        ctx = PipelineContext(
            pipeline_run_id=str(uuid.uuid4()),
            pipeline_name="orders_pipeline",
            dataset_type="orders",
        )
        # Should not raise
        ee.emit_retry_started(ctx, attempt=1, stage="ingestion")

    def test_emit_pipeline_cancelled(self, db_session):
        ee = EventEmitter(db_session)
        ctx = PipelineContext(
            pipeline_run_id=str(uuid.uuid4()),
            pipeline_name="orders_pipeline",
            dataset_type="orders",
        )
        ee.emit_pipeline_cancelled(ctx)

    def test_emit_with_bad_run_id_does_not_raise(self, db_session):
        """If run_id is not a valid UUID, _emit should swallow the error gracefully."""
        ee = EventEmitter(db_session)
        ctx = PipelineContext(
            pipeline_run_id="not-a-uuid",
            pipeline_name="orders_pipeline",
            dataset_type="orders",
        )
        # Should not propagate
        ee.emit_pipeline_started(ctx)
