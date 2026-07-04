"""
Pipeline Orchestration Engine tests.

Strategy:
- Model/logic tests (state machine, retry, checkpoint, registry) run against real SQLite
- Executor tests mock all 5 ETL engine calls to avoid PostgreSQL dependencies and speed
- One "smoke" test exercises the trigger service with mocked engines
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
import uuid

import pandas as pd
import pytest

from app.pipeline.models import (
    PipelineResult, PipelineState, PipelineStageResult,
    RetryPolicy, StageName, CheckpointData, PipelineMetrics
)
from app.pipeline.retry_manager import RetryManager
from app.pipeline.checkpoint_manager import CheckpointManager
from app.pipeline.pipeline_registry import PipelineRegistry, PipelineDefinition, get_registry
from app.pipeline.context import PipelineContext


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_stage_result(stage: str, order: int, status: str = "success",
                       rows_out: int = 5) -> PipelineStageResult:
    sr = PipelineStageResult(
        stage_name=stage, stage_order=order, status=status,
        started_at=datetime.utcnow(), output_records=rows_out,
    )
    sr.completed_at = datetime.utcnow()
    sr.duration_ms = 10.0
    return sr


def _make_mock_df(rows: int = 5) -> pd.DataFrame:
    return pd.DataFrame({
        "order_id":    [f"ORD-{i:03d}" for i in range(rows)],
        "order_total": [f"{i * 10.0:.2f}" for i in range(rows)],
        "status":      ["delivered"] * rows,
    })


# ─────────────────────────────────────────────────────────────────────────────
# RetryManager
# ─────────────────────────────────────────────────────────────────────────────

class TestRetryManager:

    def test_should_retry_within_limit(self):
        mgr = RetryManager(RetryPolicy(max_retries=3))
        assert mgr.should_retry(0) is True
        assert mgr.should_retry(2) is True

    def test_should_not_retry_at_limit(self):
        mgr = RetryManager(RetryPolicy(max_retries=3))
        assert mgr.should_retry(3) is False

    def test_stage_scoped_retry_match(self):
        mgr = RetryManager(RetryPolicy(max_retries=3, retry_on_stages=["validation"]))
        assert mgr.should_retry(0, failed_stage="validation") is True

    def test_stage_scoped_retry_no_match(self):
        mgr = RetryManager(RetryPolicy(max_retries=3, retry_on_stages=["validation"]))
        assert mgr.should_retry(0, failed_stage="ingestion") is False

    def test_no_retry_policy(self):
        mgr = RetryManager(RetryPolicy.no_retry())
        assert mgr.should_retry(0) is False

    def test_get_delay_immediate(self):
        mgr = RetryManager(RetryPolicy(backoff_strategy="immediate"))
        assert mgr.get_delay_seconds(0) == 0.0

    def test_get_delay_exponential(self):
        mgr = RetryManager(RetryPolicy(retry_delay_seconds=2.0, backoff_multiplier=2.0))
        assert mgr.get_delay_seconds(0) == pytest.approx(2.0)
        assert mgr.get_delay_seconds(1) == pytest.approx(4.0)

    def test_get_delay_linear(self):
        mgr = RetryManager(RetryPolicy(retry_delay_seconds=3.0, backoff_strategy="linear",
                                        max_delay_seconds=300.0))
        assert mgr.get_delay_seconds(0) == pytest.approx(3.0)
        assert mgr.get_delay_seconds(1) == pytest.approx(6.0)

    def test_max_delay_capped(self):
        mgr = RetryManager(RetryPolicy(retry_delay_seconds=5.0, backoff_multiplier=10.0,
                                        max_delay_seconds=50.0))
        assert mgr.get_delay_seconds(3) <= 50.0


# ─────────────────────────────────────────────────────────────────────────────
# CheckpointManager
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckpointManager:

    def test_save_returns_checkpoint(self, db_session):
        run_id = str(uuid.uuid4())
        mgr = CheckpointManager(db_session)
        cp = mgr.save(
            pipeline_run_id=run_id,
            pipeline_name="orders_pipeline",
            dataset_type="orders",
            completed_stages=["ingestion"],
            stage_results=[_make_stage_result("ingestion", 0)],
        )
        assert cp.last_completed_stage == "ingestion"
        assert "ingestion" in cp.completed_stages
        assert cp.pipeline_run_id == run_id

    def test_save_and_load_checkpoint(self, db_session):
        run_id = str(uuid.uuid4())
        mgr = CheckpointManager(db_session)
        mgr.save(
            pipeline_run_id=run_id,
            pipeline_name="orders_pipeline",
            dataset_type="orders",
            completed_stages=["ingestion"],
            stage_results=[_make_stage_result("ingestion", 0)],
        )
        loaded = mgr.load_latest(run_id)
        assert loaded is not None
        assert loaded.last_completed_stage == "ingestion"
        assert loaded.dataset_type == "orders"

    def test_load_returns_none_for_unknown_run(self, db_session):
        mgr = CheckpointManager(db_session)
        result = mgr.load_latest(str(uuid.uuid4()))
        assert result is None

    def test_multiple_checkpoints_loads_latest(self, db_session):
        run_id = str(uuid.uuid4())
        mgr = CheckpointManager(db_session)
        for stage in ["ingestion", "validation", "cleaning"]:
            mgr.save(
                pipeline_run_id=run_id,
                pipeline_name="orders_pipeline",
                dataset_type="orders",
                completed_stages=[stage],
                stage_results=[_make_stage_result(stage, 0)],
            )
        loaded = mgr.load_latest(run_id)
        assert loaded is not None
        # The last saved checkpoint has stage "cleaning"
        assert loaded.last_completed_stage == "cleaning"

    def test_list_checkpoints(self, db_session):
        run_id = str(uuid.uuid4())
        mgr = CheckpointManager(db_session)
        mgr.save(run_id, "p", "orders", ["ingestion"],
                 [_make_stage_result("ingestion", 0)])
        checkpoints = mgr.list_checkpoints(run_id)
        assert len(checkpoints) >= 1
        assert checkpoints[0]["stage"] == "ingestion"
        assert checkpoints[0]["is_checkpoint"] is True

    def test_retry_count_preserved(self, db_session):
        run_id = str(uuid.uuid4())
        mgr = CheckpointManager(db_session)
        mgr.save(run_id, "p", "orders", ["ingestion"],
                 [_make_stage_result("ingestion", 0)], retry_count=2)
        loaded = mgr.load_latest(run_id)
        assert loaded.retry_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# PipelineRegistry
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineRegistry:

    def test_default_pipelines_registered(self):
        reg = PipelineRegistry()
        assert reg.count() >= 6

    def test_get_by_name(self):
        reg = PipelineRegistry()
        defn = reg.get_by_name("orders_pipeline")
        assert defn is not None
        assert defn.dataset_type == "orders"

    def test_get_by_dataset_type(self):
        reg = PipelineRegistry()
        defn = reg.get_by_dataset_type("customers")
        assert defn is not None
        assert defn.name == "customers_pipeline"

    def test_unknown_name_returns_none(self):
        reg = PipelineRegistry()
        assert reg.get_by_name("nonexistent_pipeline") is None

    def test_enable_disable(self):
        reg = PipelineRegistry()
        reg.disable("orders_pipeline")
        assert reg.get_by_name("orders_pipeline").enabled is False
        reg.enable("orders_pipeline")
        assert reg.get_by_name("orders_pipeline").enabled is True

    def test_list_enabled_excludes_disabled(self):
        reg = PipelineRegistry()
        reg.disable("products_pipeline")
        enabled_names = [d.name for d in reg.list_enabled()]
        assert "products_pipeline" not in enabled_names
        assert "orders_pipeline" in enabled_names
        reg.enable("products_pipeline")  # restore

    def test_register_custom_pipeline(self):
        reg = PipelineRegistry()
        custom = PipelineDefinition(name="custom_test_pipeline", dataset_type="orders")
        reg.register(custom)
        assert reg.get_by_name("custom_test_pipeline") is custom

    def test_pipeline_definition_from_dict(self):
        d = {"name": "test_p", "dataset_type": "payments",
             "enabled": True, "max_runtime_seconds": 1800,
             "description": "Test", "version": "2.0"}
        defn = PipelineDefinition.from_dict(d)
        assert defn.name == "test_p"
        assert defn.max_runtime_seconds == 1800

    def test_pipeline_definition_to_dict(self):
        defn = PipelineDefinition(name="p", dataset_type="orders", description="d")
        d = defn.to_dict()
        assert d["name"] == "p"
        assert "stage_order" in d


# ─────────────────────────────────────────────────────────────────────────────
# PipelineContext
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineContext:

    def test_context_is_immutable(self):
        ctx = PipelineContext(pipeline_run_id="run-001",
                              pipeline_name="p", dataset_type="orders")
        with pytest.raises((AttributeError, TypeError)):
            ctx.pipeline_run_id = "different"

    def test_with_ingestion_event(self):
        ctx = PipelineContext(pipeline_run_id="run-001",
                              pipeline_name="p", dataset_type="orders")
        ctx2 = ctx.with_ingestion_event("event-123")
        assert ctx2.ingestion_event_id == "event-123"
        assert ctx.ingestion_event_id is None  # original unchanged
        assert ctx2.pipeline_run_id == "run-001"

    def test_default_retry_policy(self):
        ctx = PipelineContext(pipeline_run_id="r", pipeline_name="p", dataset_type="orders")
        assert ctx.retry_policy.max_retries == 3


# ─────────────────────────────────────────────────────────────────────────────
# PipelineExecutor — mocked ETL engines (fast, no PostgreSQL/filesystem)
# ─────────────────────────────────────────────────────────────────────────────

def _patch_stage_executor(db_session, df: pd.DataFrame | None = None):
    """
    Return a PipelineExecutor with all 5 stage methods mocked.
    Each stage returns a successful PipelineStageResult with a mock output.
    """
    from app.pipeline.engine import PipelineExecutor
    from app.pipeline.stage_executor import EventEmitter
    from app.ingestion.models import IngestionResult, IngestionStatus, Dataset, DatasetSchema, FileMetadata
    from app.validation.models import ValidationResult, ValidationReport, QualityScore
    from app.cleaning.models import CleaningResult, CleaningReport, CleaningMetrics
    from app.transformation.models import TransformationResult, TransformationReport, TransformationMetrics
    from pathlib import Path

    target_df = df if df is not None else _make_mock_df(5)

    # Build mock stage outputs
    meta = FileMetadata(original_filename="orders.csv", stored_filename="orders.csv",
                        file_path=Path("/tmp/orders.csv"), file_extension="csv",
                        file_size_bytes=1024, dataset_type="orders")
    schema = DatasetSchema(column_names=list(target_df.columns),
                           column_dtypes={c: "object" for c in target_df.columns},
                           row_count=len(target_df), column_count=len(target_df.columns))
    dataset = Dataset(metadata=meta, dataframe=target_df, schema=schema,
                      ingestion_event_id="evt-001", reader_used="CSVReader")
    ing_result = IngestionResult(success=True, status=IngestionStatus.PROCESSED,
                                  dataset=dataset, ingestion_event_id="evt-001",
                                  file_metadata=meta)

    qs = QualityScore(completeness=95.0, validity=90.0, consistency=88.0,
                      uniqueness=100.0, integrity=100.0, timeliness=100.0,
                      total_records=5, valid_records=5)
    qs.compute_overall()
    val_result = ValidationResult(success=True, dataset_type="orders",
                                   valid_df=target_df, rejected_df=pd.DataFrame(),
                                   warning_df=pd.DataFrame(), quality_score=qs.overall_score,
                                   letter_grade=qs.letter_grade, passed_threshold=True,
                                   report=ValidationReport(dataset_type="orders",
                                                           quality_score=qs))

    clean_result = CleaningResult(cleaned_df=target_df.copy(), dataset_type="orders",
                                   cleaning_report=CleaningReport(dataset_type="orders"),
                                   cleaning_metrics=CleaningMetrics(total_rows_input=5,
                                                                    total_rows_output=5),
                                   success=True, original_df=target_df.copy())

    trans_metrics = TransformationMetrics(total_rows_input=5, total_rows_output=5)
    trans_report = TransformationReport(dataset_type="orders",
                                         metrics=trans_metrics,
                                         input_columns=list(target_df.columns),
                                         output_columns=list(target_df.columns))
    trans_result = TransformationResult(success=True, dataset_type="orders",
                                         transformed_df=target_df.copy(), report=trans_report)

    executor = PipelineExecutor(db_session)

    def mock_run_ingestion(ctx, ee):
        sr = _make_stage_result("ingestion", 0, "success", len(target_df))
        sr.stage_output = ing_result
        sr.details = {"ingestion_event_id": "evt-001", "reader_used": "CSVReader"}
        ee.emit_stage_started(ctx, "ingestion")
        ee.emit_stage_completed(ctx, "ingestion", sr)
        return sr

    def mock_run_validation(ctx, ingestion_res, ee):
        sr = _make_stage_result("validation", 1, "success", len(target_df))
        sr.stage_output = val_result
        sr.quality_score = qs.overall_score
        ee.emit_stage_started(ctx, "validation")
        ee.emit_stage_completed(ctx, "validation", sr)
        return sr

    def mock_run_cleaning(ctx, val_res, ee):
        sr = _make_stage_result("cleaning", 2, "success", len(target_df))
        sr.stage_output = clean_result
        ee.emit_stage_started(ctx, "cleaning")
        ee.emit_stage_completed(ctx, "cleaning", sr)
        return sr

    def mock_run_transformation(ctx, clean_res, ee):
        sr = _make_stage_result("transformation", 3, "success", len(target_df))
        sr.stage_output = trans_result
        ee.emit_stage_started(ctx, "transformation")
        ee.emit_stage_completed(ctx, "transformation", sr)
        return sr

    def mock_run_load(ctx, trans_res, ee):
        sr = _make_stage_result("load", 4, "success", len(target_df))
        sr.stage_output = {"status": "ready_for_loading", "rows_ready": len(target_df)}
        ee.emit_stage_started(ctx, "load")
        ee.emit_stage_completed(ctx, "load", sr)
        return sr

    executor._stage_executor.run_ingestion = mock_run_ingestion
    executor._stage_executor.run_validation = mock_run_validation
    executor._stage_executor.run_cleaning = mock_run_cleaning
    executor._stage_executor.run_transformation = mock_run_transformation
    executor._stage_executor.run_load = mock_run_load

    return executor



class TestPipelineExecutor:
    """All tests use RetryPolicy.no_retry() to prevent backoff sleep."""

    def test_full_pipeline_returns_result(self, db_session):
        executor = _patch_stage_executor(db_session)
        result = executor.execute(
            pipeline_name="orders_pipeline", dataset_type="orders",
            triggered_by="test", retry_policy=RetryPolicy.no_retry(),
        )
        assert isinstance(result, PipelineResult)
        assert result.dataset_type == "orders"

    def test_full_pipeline_succeeds(self, db_session):
        executor = _patch_stage_executor(db_session)
        result = executor.execute(
            pipeline_name="orders_pipeline", dataset_type="orders",
            retry_policy=RetryPolicy.no_retry(),
        )
        assert result.success is True
        assert result.status == PipelineState.SUCCEEDED

    def test_all_stages_complete(self, db_session):
        executor = _patch_stage_executor(db_session)
        result = executor.execute(
            pipeline_name="orders_pipeline", dataset_type="orders",
            retry_policy=RetryPolicy.no_retry(),
        )
        assert set(result.completed_stages) == set(StageName.ALL)

    def test_stage_results_populated(self, db_session):
        executor = _patch_stage_executor(db_session)
        result = executor.execute(
            pipeline_name="orders_pipeline", dataset_type="orders",
            retry_policy=RetryPolicy.no_retry(),
        )
        stage_names = [sr.stage_name for sr in result.stage_results]
        for stage in StageName.ALL:
            assert stage in stage_names

    def test_transformed_df_populated(self, db_session):
        executor = _patch_stage_executor(db_session)
        result = executor.execute(
            pipeline_name="orders_pipeline", dataset_type="orders",
            retry_policy=RetryPolicy.no_retry(),
        )
        assert isinstance(result.transformed_df, pd.DataFrame)
        assert len(result.transformed_df) == 5

    def test_metrics_populated(self, db_session):
        executor = _patch_stage_executor(db_session)
        result = executor.execute(
            pipeline_name="orders_pipeline", dataset_type="orders",
            retry_policy=RetryPolicy.no_retry(),
        )
        assert result.metrics.total_duration_seconds >= 0
        assert result.metrics.total_records_ingested == 5

    def test_checkpoints_saved_on_success(self, db_session):
        executor = _patch_stage_executor(db_session)
        result = executor.execute(
            pipeline_name="orders_pipeline", dataset_type="orders",
            retry_policy=RetryPolicy.no_retry(),
        )
        assert result.success is True
        assert len(result.completed_stages) == 5

    def test_duration_recorded(self, db_session):
        executor = _patch_stage_executor(db_session)
        result = executor.execute(
            pipeline_name="orders_pipeline", dataset_type="orders",
            retry_policy=RetryPolicy.no_retry(),
        )
        assert result.duration_seconds > 0

    def test_retry_count_zero_on_success(self, db_session):
        executor = _patch_stage_executor(db_session)
        result = executor.execute(
            pipeline_name="orders_pipeline", dataset_type="orders",
            retry_policy=RetryPolicy.no_retry(),
        )
        assert result.retry_count == 0

    def test_pipeline_run_id_is_uuid(self, db_session):
        executor = _patch_stage_executor(db_session)
        result = executor.execute(
            pipeline_name="orders_pipeline", dataset_type="orders",
            retry_policy=RetryPolicy.no_retry(),
        )
        uuid.UUID(result.pipeline_run_id)  # raises ValueError if invalid

    def test_failed_ingestion_returns_failed_result(self, db_session):
        from app.pipeline.engine import PipelineExecutor
        executor = PipelineExecutor(db_session)

        def mock_fail(ctx, ee):
            sr = _make_stage_result("ingestion", 0, "failed", 0)
            sr.error_message = "File not found"
            ee.emit_stage_failed(ctx, "ingestion", sr)
            return sr

        executor._stage_executor.run_ingestion = mock_fail
        result = executor.execute(
            pipeline_name="orders_pipeline", dataset_type="orders",
            retry_policy=RetryPolicy.no_retry(),
        )
        assert result.success is False
        assert result.failed_stage == "ingestion"
        assert result.status == PipelineState.FAILED

    def test_partial_failure_at_validation(self, db_session):
        executor = _patch_stage_executor(db_session)

        def mock_fail(ctx, ing, ee):
            sr = _make_stage_result("validation", 1, "failed", 0)
            sr.error_message = "Schema mismatch"
            ee.emit_stage_failed(ctx, "validation", sr)
            return sr

        executor._stage_executor.run_validation = mock_fail
        result = executor.execute(
            pipeline_name="orders_pipeline", dataset_type="orders",
            retry_policy=RetryPolicy.no_retry(),
        )
        assert result.success is False
        assert result.failed_stage == "validation"
        assert "ingestion" in result.completed_stages
        assert "validation" not in result.completed_stages

    def test_no_retry_policy_runs_once(self, db_session):
        call_count = [0]
        executor = _patch_stage_executor(db_session)

        def mock_fail(ctx, ee):
            call_count[0] += 1
            sr = _make_stage_result("ingestion", 0, "failed", 0)
            sr.error_message = "Persistent failure"
            ee.emit_stage_failed(ctx, "ingestion", sr)
            return sr

        executor._stage_executor.run_ingestion = mock_fail
        result = executor.execute(
            pipeline_name="orders_pipeline", dataset_type="orders",
            retry_policy=RetryPolicy.no_retry(),
        )
        assert call_count[0] == 1  # ran exactly once
        assert result.retry_count == 0

    def test_completed_stages_list_correct_order(self, db_session):
        executor = _patch_stage_executor(db_session)
        result = executor.execute(
            pipeline_name="orders_pipeline", dataset_type="orders",
            retry_policy=RetryPolicy.no_retry(),
        )
        assert result.completed_stages == list(StageName.ALL)

    def test_stage_results_have_timing(self, db_session):
        executor = _patch_stage_executor(db_session)
        result = executor.execute(
            pipeline_name="orders_pipeline", dataset_type="orders",
            retry_policy=RetryPolicy.no_retry(),
        )
        for sr in result.stage_results:
            assert sr.duration_ms >= 0
            assert sr.started_at is not None

    def test_phase9_contract(self, db_session):
        """
        CRITICAL: PipelineResult must expose exactly the fields Phase 9 needs.

        Phase 9 Warehouse Loader will call:
            loader.load(pipeline_result.transformed_df, pipeline_result.dataset_type)
        """
        executor = _patch_stage_executor(db_session)
        result = executor.execute(
            pipeline_name="orders_pipeline", dataset_type="orders",
            retry_policy=RetryPolicy.no_retry(),
        )
        # Phase 9 contract
        assert isinstance(result.transformed_df, pd.DataFrame)
        assert isinstance(result.dataset_type, str)
        assert isinstance(result.pipeline_run_id, str)
        assert result.dataset_type == "orders"
        assert hasattr(result, "metrics")
        assert hasattr(result, "stage_results")
        assert hasattr(result, "completed_stages")
        assert hasattr(result, "ingestion_event_id")


class TestTriggerService:

    def test_invalid_dataset_type_returns_error(self, db_session):
        from app.pipeline.trigger_service import PipelineTriggerService
        svc = PipelineTriggerService(db_session)
        result = svc.trigger(dataset_type="invalid_xyz")
        assert result.success is False
        assert result.error_code == "INVALID_DATASET_TYPE"

    def test_cancel_unknown_run_returns_false(self, db_session):
        from app.pipeline.trigger_service import PipelineTriggerService
        svc = PipelineTriggerService(db_session)
        assert svc.cancel(str(uuid.uuid4())) is False

    def test_trigger_calls_executor_with_correct_params(self, db_session):
        from app.pipeline.trigger_service import PipelineTriggerService
        from unittest.mock import patch as _patch

        svc = PipelineTriggerService(db_session)
        expected = PipelineResult(
            pipeline_run_id=str(uuid.uuid4()),
            pipeline_name="orders_pipeline",
            dataset_type="orders",
            status=PipelineState.SUCCEEDED,
            success=True,
        )
        with _patch.object(svc._executor, "execute", return_value=expected) as mock:
            result = svc.trigger(
                dataset_type="orders",
                source_file_path="/tmp/orders.csv",
                triggered_by="test",
            )
            assert result is expected
            call_kwargs = mock.call_args[1]
            assert call_kwargs["dataset_type"] == "orders"
            assert call_kwargs["triggered_by"] == "test"

    def test_resume_unknown_run_attempts_fresh_start(self, db_session):
        from app.pipeline.trigger_service import PipelineTriggerService
        from unittest.mock import patch as _patch

        svc = PipelineTriggerService(db_session)
        expected = PipelineResult(
            pipeline_run_id=str(uuid.uuid4()),
            pipeline_name="orders_pipeline",
            dataset_type="orders",
            status=PipelineState.SUCCEEDED,
            success=True,
        )
        with _patch.object(svc._executor, "execute", return_value=expected):
            result = svc.resume(str(uuid.uuid4()))
            assert isinstance(result, PipelineResult)

    def test_trigger_uses_pipeline_name_default(self, db_session):
        from app.pipeline.trigger_service import PipelineTriggerService
        from unittest.mock import patch as _patch

        svc = PipelineTriggerService(db_session)
        captured = {}

        def mock_execute(**kwargs):
            captured.update(kwargs)
            return PipelineResult(
                pipeline_run_id=str(uuid.uuid4()),
                pipeline_name=kwargs.get("pipeline_name", ""),
                dataset_type="orders",
                status=PipelineState.SUCCEEDED,
                success=True,
            )

        with _patch.object(svc._executor, "execute", side_effect=mock_execute):
            svc.trigger(dataset_type="orders")
            assert captured.get("pipeline_name") == "orders_pipeline"


class TestRetryManagerWait:
    """Tests for RetryManager.wait() — uses immediate strategy to avoid sleep."""

    def test_wait_immediate_no_sleep(self):
        """Immediate strategy should not sleep at all."""
        import time
        mgr = RetryManager(RetryPolicy(backoff_strategy="immediate"))
        start = time.perf_counter()
        mgr.wait(0)
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1  # no sleep

    def test_get_delay_returns_zero_for_immediate(self):
        mgr = RetryManager(RetryPolicy(backoff_strategy="immediate"))
        assert mgr.get_delay_seconds(5) == 0.0

    def test_policy_max_retries_respected(self):
        mgr = RetryManager(RetryPolicy(max_retries=2))
        assert mgr.should_retry(0) is True
        assert mgr.should_retry(1) is True
        assert mgr.should_retry(2) is False


class TestStageExecutorEventEmitter:
    """Test EventEmitter without DB interaction via mocked session."""

    def _make_ctx(self) -> PipelineContext:
        return PipelineContext(
            pipeline_run_id=str(uuid.uuid4()),
            pipeline_name="test_pipeline",
            dataset_type="orders",
        )

    def test_event_emitter_logs_pipeline_started(self, db_session):
        from app.pipeline.stage_executor import EventEmitter
        ee = EventEmitter(db_session)
        ctx = self._make_ctx()
        # Should not raise
        ee.emit_pipeline_started(ctx)

    def test_event_emitter_logs_stage_started(self, db_session):
        from app.pipeline.stage_executor import EventEmitter
        ee = EventEmitter(db_session)
        ctx = self._make_ctx()
        ee.emit_stage_started(ctx, "ingestion")

    def test_event_emitter_logs_stage_completed(self, db_session):
        from app.pipeline.stage_executor import EventEmitter
        ee = EventEmitter(db_session)
        ctx = self._make_ctx()
        sr = _make_stage_result("ingestion", 0, "success", 5)
        ee.emit_stage_completed(ctx, "ingestion", sr)

    def test_event_emitter_logs_stage_failed(self, db_session):
        from app.pipeline.stage_executor import EventEmitter
        ee = EventEmitter(db_session)
        ctx = self._make_ctx()
        sr = _make_stage_result("ingestion", 0, "failed", 0)
        sr.error_message = "Test failure"
        ee.emit_stage_failed(ctx, "ingestion", sr)

    def test_event_emitter_pipeline_completed(self, db_session):
        from app.pipeline.stage_executor import EventEmitter
        ee = EventEmitter(db_session)
        ctx = self._make_ctx()
        ee.emit_pipeline_completed(ctx, {"total_duration_seconds": 1.5})

    def test_event_emitter_pipeline_failed(self, db_session):
        from app.pipeline.stage_executor import EventEmitter
        ee = EventEmitter(db_session)
        ctx = self._make_ctx()
        ee.emit_pipeline_failed(ctx, "Something went wrong", "ingestion")

    def test_event_emitter_pipeline_cancelled(self, db_session):
        from app.pipeline.stage_executor import EventEmitter
        ee = EventEmitter(db_session)
        ctx = self._make_ctx()
        ee.emit_pipeline_cancelled(ctx)

    def test_stage_executor_run_load_placeholder(self, db_session):
        """Load stage should always succeed as a placeholder."""
        from app.pipeline.stage_executor import StageExecutor, EventEmitter
        from app.transformation.models import TransformationResult, TransformationReport, TransformationMetrics

        ctx = PipelineContext(
            pipeline_run_id=str(uuid.uuid4()),
            pipeline_name="orders_pipeline",
            dataset_type="orders",
        )
        ee = EventEmitter(db_session)
        se = StageExecutor(db_session)

        df = _make_mock_df(3)
        metrics = TransformationMetrics(total_rows_input=3, total_rows_output=3)
        report = TransformationReport(dataset_type="orders", metrics=metrics,
                                       input_columns=list(df.columns),
                                       output_columns=list(df.columns))
        trans_result = TransformationResult(
            success=True, dataset_type="orders",
            transformed_df=df, report=report,
        )
        sr = se.run_load(ctx, trans_result, ee)
        assert sr.status == "success"
        assert sr.stage_name == "load"
        assert sr.output_records == 3


class TestPipelineStageResultModel:
    """Tests for PipelineStageResult."""

    def test_to_dict_keys(self):
        sr = _make_stage_result("ingestion", 0, "success", 100)
        d = sr.to_dict()
        for key in ("stage_name", "stage_order", "status", "duration_ms",
                    "input_records", "output_records"):
            assert key in d

    def test_error_message_in_dict(self):
        sr = _make_stage_result("validation", 1, "failed", 0)
        sr.error_message = "Type mismatch"
        d = sr.to_dict()
        assert d["error_message"] == "Type mismatch"

    def test_quality_score_in_dict(self):
        sr = _make_stage_result("validation", 1, "success", 100)
        sr.quality_score = 92.5
        d = sr.to_dict()
        assert d["quality_score"] == 92.5


class TestPipelineRegistryGlobal:
    """Test the module-level singleton registry."""

    def test_get_registry_returns_same_instance(self):
        reg1 = get_registry()
        reg2 = get_registry()
        assert reg1 is reg2

    def test_get_registry_has_default_pipelines(self):
        reg = get_registry()
        assert reg.get_by_name("orders_pipeline") is not None

    def test_all_dataset_types_have_pipeline(self):
        from app.utils.constants import DatasetType
        reg = get_registry()
        for ds in DatasetType:
            defn = reg.get_by_dataset_type(ds.value)
            assert defn is not None, f"No pipeline for dataset type: {ds.value}"
