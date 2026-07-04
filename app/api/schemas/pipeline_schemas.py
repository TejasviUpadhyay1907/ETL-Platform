"""Pydantic schemas for pipeline orchestration API responses."""
from __future__ import annotations
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class RetryPolicyRequest(BaseModel):
    max_retries: int = Field(default=3, ge=0)
    retry_delay_seconds: float = Field(default=5.0, ge=0)
    backoff_strategy: str = Field(default="exponential")
    max_delay_seconds: float = Field(default=300.0)


class PipelineTriggerRequest(BaseModel):
    dataset_type: str
    source_file_path: str = ""
    original_filename: str = ""
    pipeline_name: str | None = None
    triggered_by: str = "api"
    trigger_type: str = "manual"
    retry_policy: RetryPolicyRequest | None = None


class StageResultResponse(BaseModel):
    stage_name: str
    stage_order: int
    status: str
    duration_ms: float
    input_records: int
    output_records: int
    rejected_records: int
    warning_count: int
    quality_score: float | None
    error_message: str | None

    @classmethod
    def from_stage_result(cls, sr: Any) -> "StageResultResponse":
        return cls(
            stage_name=sr.stage_name,
            stage_order=sr.stage_order,
            status=sr.status,
            duration_ms=round(sr.duration_ms, 2),
            input_records=sr.input_records,
            output_records=sr.output_records,
            rejected_records=sr.rejected_records,
            warning_count=sr.warning_count,
            quality_score=sr.quality_score,
            error_message=sr.error_message,
        )


class PipelineMetricsResponse(BaseModel):
    total_duration_seconds: float
    stage_durations: dict[str, float]
    total_records_ingested: int
    total_records_valid: int
    total_records_cleaned: int
    total_records_transformed: int
    total_records_loaded: int
    total_records_rejected: int
    retry_count: int
    warning_count: int
    quality_score: float | None
    throughput_rows_per_sec: float


class PipelineRunResponse(BaseModel):
    pipeline_run_id: str
    pipeline_name: str
    dataset_type: str
    run_number: str
    status: str
    success: bool
    current_stage: str | None
    completed_stages: list[str]
    failed_stage: str | None
    retry_count: int
    duration_seconds: float
    record_count: int
    error_message: str | None
    warnings: list[str]
    errors: list[str]
    stage_results: list[StageResultResponse]
    metrics: PipelineMetricsResponse | None

    @classmethod
    def from_result(cls, result: Any) -> "PipelineRunResponse":
        metrics = None
        if result.metrics:
            d = result.metrics.to_dict()
            metrics = PipelineMetricsResponse(**d)
        return cls(
            pipeline_run_id=result.pipeline_run_id,
            pipeline_name=result.pipeline_name,
            dataset_type=result.dataset_type,
            run_number=result.run_number,
            status=result.status,
            success=result.success,
            current_stage=result.current_stage,
            completed_stages=result.completed_stages,
            failed_stage=result.failed_stage,
            retry_count=result.retry_count,
            duration_seconds=round(result.duration_seconds, 3),
            record_count=result.record_count,
            error_message=result.error_message,
            warnings=result.warnings[:20],
            errors=result.errors[:10],
            stage_results=[StageResultResponse.from_stage_result(s) for s in result.stage_results],
            metrics=metrics,
        )


class PipelineHistoryItem(BaseModel):
    id: str
    run_number: str
    pipeline_name: str
    dataset_type: str
    status: str
    quality_score: float | None
    total_records: int
    duration_seconds: float | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    triggered_by: str


class PipelineDefinitionResponse(BaseModel):
    name: str
    dataset_type: str
    enabled: bool
    stage_order: list[str]
    max_runtime_seconds: int
    description: str
    version: str
