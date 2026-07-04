"""Pydantic schemas for cleaning and data API responses."""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel


class CleaningMetricsResponse(BaseModel):
    total_rows_input: int
    total_rows_output: int
    rows_dropped: int
    rows_modified: int
    cells_modified: int
    nulls_filled: int
    nulls_dropped: int
    duplicates_removed: int
    strings_trimmed: int
    dates_standardized: int
    categories_mapped: int
    outliers_clipped: int
    total_actions: int
    rules_executed: int
    total_duration_ms: float
    cleaning_pct: float


class CleaningSummaryResponse(BaseModel):
    report_id: str
    dataset_type: str
    original_filename: str
    cleaned_at: str
    duration_seconds: float
    metrics: CleaningMetricsResponse
    input_columns: list[str]
    output_columns: list[str]
    dropped_rows: int
    total_actions: int
    warnings: list[str]
    errors: list[str]
    success: bool

    @classmethod
    def from_result(cls, result: Any) -> "CleaningSummaryResponse":
        r = result.cleaning_report
        m = result.cleaning_metrics
        return cls(
            report_id=r.report_id,
            dataset_type=r.dataset_type,
            original_filename=r.original_filename,
            cleaned_at=r.cleaned_at.isoformat(),
            duration_seconds=r.duration_seconds,
            metrics=CleaningMetricsResponse(**m.to_dict()),
            input_columns=r.input_columns,
            output_columns=r.output_columns,
            dropped_rows=len(r.dropped_row_indices),
            total_actions=len(r.actions),
            warnings=result.warnings,
            errors=result.errors,
            success=result.success,
        )


class CleaningActionResponse(BaseModel):
    rule_code: str
    rule_category: str
    field_name: str | None
    row_index: int | None
    original_value: str | None
    cleaned_value: str | None
    action_type: str
    reason: str
    confidence: float


class CleaningDiffRow(BaseModel):
    row_index: int | None
    field_name: str | None
    original_value: str | None
    cleaned_value: str | None
    rule_code: str
    action_type: str
    reason: str
