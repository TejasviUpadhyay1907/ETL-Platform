"""Unit tests for pipeline domain models."""
import pytest
from app.pipeline.models import (
    PipelineState, StageName, RetryPolicy, PipelineStageResult,
    PipelineMetrics, CheckpointData, PipelineResult, PipelineEvent
)


class TestPipelineState:
    def test_valid_transition_running_to_completed(self):
        assert PipelineState.is_valid_transition("running", "completed") is True

    def test_valid_transition_running_to_failed(self):
        assert PipelineState.is_valid_transition("running", "failed") is True

    def test_valid_transition_running_to_cancelled(self):
        assert PipelineState.is_valid_transition("running", "cancelled") is True

    def test_invalid_transition_completed_to_running(self):
        assert PipelineState.is_valid_transition("completed", "running") is False

    def test_invalid_transition_completed_to_any(self):
        for state in ("running", "queued", "retrying", "failed", "cancelled"):
            assert PipelineState.is_valid_transition("completed", state) is False

    def test_invalid_transition_failed_to_running(self):
        assert PipelineState.is_valid_transition("failed", "running") is False

    def test_failed_can_retry(self):
        assert PipelineState.is_valid_transition("failed", "retrying") is True

    def test_retrying_to_running(self):
        assert PipelineState.is_valid_transition("retrying", "running") is True

    def test_terminal_states(self):
        assert PipelineState.is_terminal("completed") is True
        assert PipelineState.is_terminal("failed") is True
        assert PipelineState.is_terminal("cancelled") is True
        assert PipelineState.is_terminal("running") is False

    def test_created_to_queued(self):
        assert PipelineState.is_valid_transition("created", "queued") is True

    def test_queued_to_running(self):
        assert PipelineState.is_valid_transition("queued", "running") is True


class TestStageName:
    def test_stage_order_correct(self):
        assert StageName.ORDER["ingestion"] == 0
        assert StageName.ORDER["validation"] == 1
        assert StageName.ORDER["cleaning"] == 2
        assert StageName.ORDER["transformation"] == 3
        assert StageName.ORDER["load"] == 4

    def test_all_stages_present(self):
        assert len(StageName.ALL) == 5
        assert "ingestion" in StageName.ALL
        assert "load" in StageName.ALL


class TestRetryPolicy:
    def test_default_policy(self):
        p = RetryPolicy.default()
        assert p.max_retries == 3
        assert p.backoff_strategy == "exponential"

    def test_no_retry_policy(self):
        p = RetryPolicy.no_retry()
        assert p.max_retries == 0

    def test_exponential_backoff(self):
        p = RetryPolicy(retry_delay_seconds=5.0, backoff_multiplier=2.0, max_delay_seconds=300.0)
        assert p.get_delay(0) == pytest.approx(5.0)
        assert p.get_delay(1) == pytest.approx(10.0)
        assert p.get_delay(2) == pytest.approx(20.0)

    def test_linear_backoff(self):
        p = RetryPolicy(retry_delay_seconds=5.0, backoff_strategy="linear", max_delay_seconds=300.0)
        assert p.get_delay(0) == pytest.approx(5.0)
        assert p.get_delay(1) == pytest.approx(10.0)
        assert p.get_delay(2) == pytest.approx(15.0)

    def test_immediate_backoff(self):
        p = RetryPolicy(backoff_strategy="immediate")
        assert p.get_delay(0) == 0.0
        assert p.get_delay(5) == 0.0

    def test_max_delay_capped(self):
        p = RetryPolicy(retry_delay_seconds=5.0, backoff_multiplier=10.0, max_delay_seconds=50.0)
        assert p.get_delay(3) <= 50.0

    def test_from_dict(self):
        d = {"max_retries": 5, "retry_delay_seconds": 10.0, "backoff_strategy": "linear"}
        p = RetryPolicy.from_dict(d)
        assert p.max_retries == 5
        assert p.retry_delay_seconds == 10.0


class TestPipelineMetrics:
    def test_compute_throughput(self):
        m = PipelineMetrics(total_duration_seconds=10.0, total_records_ingested=1000)
        m.compute_throughput()
        assert m.throughput_rows_per_sec == pytest.approx(100.0)

    def test_throughput_zero_duration(self):
        m = PipelineMetrics(total_duration_seconds=0.0, total_records_ingested=1000)
        m.compute_throughput()
        assert m.throughput_rows_per_sec == 0.0

    def test_to_dict(self):
        m = PipelineMetrics(total_duration_seconds=5.0, total_records_ingested=500)
        d = m.to_dict()
        assert d["total_duration_seconds"] == pytest.approx(5.0)
        assert d["total_records_ingested"] == 500
        assert "stage_durations" in d


class TestCheckpointData:
    def test_to_dict(self):
        cp = CheckpointData(
            pipeline_run_id="run-123",
            pipeline_name="orders_pipeline",
            dataset_type="orders",
            last_completed_stage="validation",
            completed_stages=["ingestion", "validation"],
        )
        d = cp.to_dict()
        assert d["last_completed_stage"] == "validation"
        assert "ingestion" in d["completed_stages"]
        assert "created_at" in d


class TestPipelineResult:
    def test_record_count(self):
        import pandas as pd
        r = PipelineResult(
            pipeline_run_id="run-001",
            pipeline_name="orders_pipeline",
            dataset_type="orders",
            transformed_df=pd.DataFrame({"a": [1, 2, 3]}),
        )
        assert r.record_count == 3

    def test_get_stage_result(self):
        from datetime import datetime
        r = PipelineResult(
            pipeline_run_id="run-001",
            pipeline_name="p",
            dataset_type="orders",
        )
        sr = PipelineStageResult(
            stage_name="ingestion", stage_order=0, status="success",
            started_at=datetime.utcnow(),
        )
        r.stage_results.append(sr)
        assert r.get_stage_result("ingestion") is sr
        assert r.get_stage_result("nonexistent") is None

    def test_to_summary_dict(self):
        r = PipelineResult(
            pipeline_run_id="run-001",
            pipeline_name="orders_pipeline",
            dataset_type="orders",
            status="completed",
            success=True,
        )
        d = r.to_summary_dict()
        assert d["status"] == "completed"
        assert d["success"] is True
        assert "metrics" in d

    def test_repr(self):
        r = PipelineResult(
            pipeline_run_id="abc12345-0000-0000-0000-000000000000",
            pipeline_name="orders_pipeline",
            dataset_type="orders",
            status="completed",
        )
        assert "orders_pipeline" in repr(r)
        assert "completed" in repr(r)
