"""
Data Quality API router — /api/v1/quality

Endpoints:
  POST /api/v1/quality/run                          — run validation on a dataset
  GET  /api/v1/quality/report/{pipeline_run_id}    — full violation list
  GET  /api/v1/quality/summary/{pipeline_run_id}   — summary with quality score
  GET  /api/v1/quality/score/{pipeline_run_id}     — quality score only
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Query

from app.api.dependencies import DbSession, Pagination
from app.api.schemas.base_schemas import APIResponse, PaginatedResponse
from app.api.schemas.quality_schemas import (
    QualityScoreResponse,
    ValidationSummaryResponse,
    ViolationResponse,
)
from app.logging.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/quality", tags=["Data Quality"])


@router.post(
    "/run",
    response_model=APIResponse[ValidationSummaryResponse],
    summary="Run validation on an ingested dataset",
    description=(
        "Validates a previously ingested dataset (identified by ingestion_event_id). "
        "Runs all configured validation rules and returns a quality score and summary."
    ),
)
def run_validation(
    db: DbSession,
    ingestion_event_id: Annotated[str, Body(embed=True, description="Ingestion event UUID")],
    pipeline_run_id: Annotated[str | None, Body(embed=True)] = None,
    dataset_type: Annotated[str | None, Body(embed=True)] = None,
) -> APIResponse[ValidationSummaryResponse]:
    """Validate a dataset by its ingestion event ID."""
    import uuid as _uuid
    from app.database.repositories.ingestion_event_repository import IngestionEventRepository
    from app.core.exceptions import NotFoundException

    # Load the ingestion event to get the stored file path
    repo = IngestionEventRepository(db)
    event = repo.get_by_id_or_raise(_uuid.UUID(ingestion_event_id))

    # Load the file and build a Dataset object
    from pathlib import Path
    from app.ingestion.readers.reader_factory import ReaderFactory
    from app.ingestion.models import Dataset, DatasetSchema, FileMetadata

    file_path = Path(event.file_path)
    if not file_path.exists():
        from app.core.exceptions import FileNotFoundException
        raise FileNotFoundException(message=f"Stored file not found: {event.file_path}")

    reader = ReaderFactory.get_reader(event.file_extension)
    df, schema = reader.read(file_path)

    meta = FileMetadata(
        ingestion_id=ingestion_event_id,
        original_filename=event.original_filename,
        stored_filename=event.stored_filename,
        file_path=file_path,
        file_extension=event.file_extension,
        file_size_bytes=event.file_size_bytes,
        dataset_type=dataset_type or event.dataset_type,
    )
    dataset = Dataset(
        metadata=meta,
        dataframe=df,
        schema=schema,
        ingestion_event_id=ingestion_event_id,
        pipeline_run_id=pipeline_run_id,
    )

    # Run validation
    from app.validation.validator import ValidationEngine
    engine = ValidationEngine(session=db)
    result = engine.validate(dataset, pipeline_run_id=pipeline_run_id)

    summary = ValidationSummaryResponse.from_report(result.report, result.passed_threshold)
    return APIResponse[ValidationSummaryResponse].ok(data=summary)


@router.get(
    "/report/{pipeline_run_id}",
    response_model=PaginatedResponse[ViolationResponse],
    summary="Get full violation report for a pipeline run",
)
def get_validation_report(
    pipeline_run_id: uuid.UUID,
    db: DbSession,
    pagination: Pagination,
    severity: str | None = Query(default=None, description="Filter by severity: error, warning, info"),
    category: str | None = Query(default=None, description="Filter by rule category"),
) -> PaginatedResponse[ViolationResponse]:
    """Return paginated violations for a pipeline run."""
    from sqlalchemy import select, desc
    from app.database.models.audit.validation_failure import ValidationFailure

    stmt = (
        select(ValidationFailure)
        .where(ValidationFailure.pipeline_run_id == pipeline_run_id)
        .order_by(ValidationFailure.created_at)
    )
    if severity:
        stmt = stmt.where(ValidationFailure.severity == severity)

    all_rows = list(db.execute(stmt).scalars().all())
    total = len(all_rows)

    paged = all_rows[pagination.offset: pagination.offset + pagination.page_size]
    violations = [
        ViolationResponse(
            rule_code=r.rule_code,
            rule_category="business",
            severity=r.severity,
            field_name=r.field_name,
            row_index=r.row_index,
            actual_value=r.original_value,
            expected=r.rule_description or "",
            message=r.failure_message,
            suggested_fix="",
        )
        for r in paged
    ]

    return PaginatedResponse[ViolationResponse].ok(
        data=violations,
        total_items=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/score/{pipeline_run_id}",
    response_model=APIResponse[QualityScoreResponse],
    summary="Get quality score for a pipeline run",
)
def get_quality_score(
    pipeline_run_id: uuid.UUID,
    db: DbSession,
) -> APIResponse[QualityScoreResponse]:
    """Retrieve the stored quality score for a pipeline run."""
    from sqlalchemy import select
    from app.database.models.audit.quality_score import DataQualityScore
    from app.core.exceptions import NotFoundException

    stmt = select(DataQualityScore).where(
        DataQualityScore.pipeline_run_id == pipeline_run_id
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        raise NotFoundException(
            message=f"No quality score found for pipeline run {pipeline_run_id}"
        )

    return APIResponse[QualityScoreResponse].ok(
        data=QualityScoreResponse(
            overall_score=float(row.quality_score),
            letter_grade=_to_grade(float(row.quality_score)),
            completeness=float(row.quality_score),
            validity=float(row.quality_score),
            consistency=float(row.quality_score),
            uniqueness=float(row.quality_score),
            integrity=float(row.quality_score),
            timeliness=float(row.quality_score),
            total_records=row.total_records,
            valid_records=row.valid_records,
            invalid_records=row.invalid_records,
            warning_records=row.warning_records,
            total_violations=row.total_records - row.loaded_records,
            error_violations=row.invalid_records,
            warning_violations=row.warning_records,
            total_rules_executed=0,
        )
    )


@router.get(
    "/summary/{pipeline_run_id}",
    response_model=APIResponse[dict],
    summary="Get validation summary for a pipeline run",
)
def get_validation_summary(
    pipeline_run_id: uuid.UUID,
    db: DbSession,
) -> APIResponse[dict]:
    """Get a high-level validation summary for a pipeline run."""
    from sqlalchemy import select
    from app.database.models.pipeline.pipeline_run import PipelineRun
    from app.core.exceptions import NotFoundException

    stmt = select(PipelineRun).where(PipelineRun.id == pipeline_run_id)
    run = db.execute(stmt).scalar_one_or_none()
    if run is None:
        raise NotFoundException(message=f"Pipeline run {pipeline_run_id} not found")

    return APIResponse[dict].ok(data={
        "pipeline_run_id": str(run.id),
        "dataset_type": run.dataset_type,
        "status": run.status,
        "total_records": run.total_records,
        "valid_records": run.valid_records,
        "invalid_records": run.invalid_records,
        "quality_score": float(run.quality_score) if run.quality_score else None,
    })


def _to_grade(score: float) -> str:
    if score >= 97: return "A+"
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"
