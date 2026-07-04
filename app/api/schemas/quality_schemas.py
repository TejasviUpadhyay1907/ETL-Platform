"""Pydantic schemas for validation quality API responses."""
from __future__ import annotations
from datetime import datetime
from typing import Any
from pydantic import BaseModel


class QualityScoreResponse(BaseModel):
    overall_score: float
    letter_grade: str
    completeness: float
    validity: float
    consistency: float
    uniqueness: float
    integrity: float
    timeliness: float
    total_records: int
    valid_records: int
    invalid_records: int
    warning_records: int
    total_violations: int
    error_violations: int
    warning_violations: int
    total_rules_executed: int

    @classmethod
    def from_quality_score(cls, qs: Any) -> "QualityScoreResponse":
        return cls(**qs.to_dict())


class ValidationSummaryResponse(BaseModel):
    report_id: str
    dataset_type: str
    original_filename: str
    validated_at: str
    duration_seconds: float
    quality_score: QualityScoreResponse
    total_violations: int
    error_violations: int
    warning_violations: int
    missing_columns: list[str]
    unexpected_columns: list[str]
    passed_threshold: bool

    @classmethod
    def from_report(cls, report: Any, passed: bool) -> "ValidationSummaryResponse":
        d = report.to_summary_dict()
        return cls(
            report_id=d["report_id"],
            dataset_type=d["dataset_type"],
            original_filename=d["original_filename"],
            validated_at=d["validated_at"],
            duration_seconds=d["duration_seconds"],
            quality_score=QualityScoreResponse.from_quality_score(report.quality_score),
            total_violations=d["total_violations"],
            error_violations=d["error_violations"],
            warning_violations=d["warning_violations"],
            missing_columns=d["missing_columns"],
            unexpected_columns=d["unexpected_columns"],
            passed_threshold=passed,
        )


class ViolationResponse(BaseModel):
    rule_code: str
    rule_category: str
    severity: str
    field_name: str | None
    row_index: int | None
    actual_value: str | None
    expected: str
    message: str
    suggested_fix: str
