"""
Data Cleaning API router — /api/v1/cleaning

Endpoints:
  POST /api/v1/cleaning/run          — run cleaning on an ingested file
  POST /api/v1/cleaning/preview      — preview changes without applying them
  POST /api/v1/cleaning/dry-run      — alias for preview
  GET  /api/v1/cleaning/report/{id}  — paginated cleaning action list
  GET  /api/v1/cleaning/summary/{id} — cleaning summary
  GET  /api/v1/cleaning/metrics/{id} — metrics only
  GET  /api/v1/cleaning/diff/{id}    — before/after diff
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Query

from app.api.dependencies import DbSession, Pagination
from app.api.schemas.base_schemas import APIResponse, PaginatedResponse
from app.api.schemas.data_schemas import (
    CleaningActionResponse,
    CleaningDiffRow,
    CleaningMetricsResponse,
    CleaningSummaryResponse,
)
from app.logging.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/cleaning", tags=["Cleaning"])


# ── POST /api/v1/cleaning/run ───────────────────────────────────────────────

@router.post(
    "/run",
    response_model=APIResponse[CleaningSummaryResponse],
    summary="Run cleaning on an ingested dataset",
)
def run_cleaning(
    db: DbSession,
    ingestion_event_id: Annotated[str, Body(embed=True)],
    pipeline_run_id:    Annotated[str | None, Body(embed=True)] = None,
    dataset_type:       Annotated[str | None, Body(embed=True)] = None,
) -> APIResponse[CleaningSummaryResponse]:
    """Clean a previously ingested file."""
    import uuid as _uuid
    from pathlib import Path
    from app.database.repositories.ingestion_event_repository import IngestionEventRepository
    from app.core.exceptions import FileNotFoundException
    from app.ingestion.readers.reader_factory import ReaderFactory
    from app.cleaning.cleaner import CleaningEngine

    event = IngestionEventRepository(db).get_by_id_or_raise(_uuid.UUID(ingestion_event_id))
    file_path = Path(event.file_path)
    if not file_path.exists():
        raise FileNotFoundException(message=f"Stored file not found: {event.file_path}")

    df, _ = ReaderFactory.get_reader(event.file_extension).read(file_path)
    engine = CleaningEngine(session=db)
    result = engine.clean_dataframe(
        df=df,
        dataset_type=dataset_type or event.dataset_type,
        pipeline_run_id=pipeline_run_id,
        original_filename=event.original_filename,
    )

    return APIResponse[CleaningSummaryResponse].ok(
        data=CleaningSummaryResponse.from_result(result)
    )


# ── POST /api/v1/cleaning/preview ──────────────────────────────────────────

@router.post(
    "/preview",
    response_model=APIResponse[CleaningSummaryResponse],
    summary="Preview cleaning changes without applying them",
)
def preview_cleaning(
    db: DbSession,
    ingestion_event_id: Annotated[str, Body(embed=True)],
    dataset_type:       Annotated[str | None, Body(embed=True)] = None,
) -> APIResponse[CleaningSummaryResponse]:
    """Dry-run cleaning: compute changes but return original data."""
    import uuid as _uuid
    from pathlib import Path
    from app.database.repositories.ingestion_event_repository import IngestionEventRepository
    from app.core.exceptions import FileNotFoundException
    from app.ingestion.readers.reader_factory import ReaderFactory
    from app.cleaning.cleaner import CleaningEngine

    event = IngestionEventRepository(db).get_by_id_or_raise(_uuid.UUID(ingestion_event_id))
    file_path = Path(event.file_path)
    if not file_path.exists():
        raise FileNotFoundException(message=f"Stored file not found: {event.file_path}")

    df, _ = ReaderFactory.get_reader(event.file_extension).read(file_path)
    engine = CleaningEngine(session=None, dry_run=True)
    result = engine.preview(df=df, dataset_type=dataset_type or event.dataset_type)

    return APIResponse[CleaningSummaryResponse].ok(
        data=CleaningSummaryResponse.from_result(result)
    )


# ── POST /api/v1/cleaning/dry-run  (alias) ─────────────────────────────────

@router.post(
    "/dry-run",
    response_model=APIResponse[CleaningSummaryResponse],
    summary="Alias for /preview — dry-run cleaning",
)
def dry_run_cleaning(
    db: DbSession,
    ingestion_event_id: Annotated[str, Body(embed=True)],
    dataset_type:       Annotated[str | None, Body(embed=True)] = None,
) -> APIResponse[CleaningSummaryResponse]:
    return preview_cleaning(db, ingestion_event_id, dataset_type)


# ── GET /api/v1/cleaning/summary/{pipeline_run_id} ─────────────────────────

@router.get(
    "/summary/{pipeline_run_id}",
    response_model=APIResponse[dict],
    summary="Get cleaning summary from audit log",
)
def get_cleaning_summary(
    pipeline_run_id: uuid.UUID,
    db: DbSession,
) -> APIResponse[dict]:
    from sqlalchemy import select
    from app.database.models.audit.audit_log import AuditLog
    from app.core.exceptions import NotFoundException

    stmt = (
        select(AuditLog)
        .where(AuditLog.run_id == pipeline_run_id, AuditLog.stage == "cleaning")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    log = db.execute(stmt).scalar_one_or_none()
    if log is None:
        raise NotFoundException(message=f"No cleaning record for run {pipeline_run_id}")
    return APIResponse[dict].ok(data=log.context_data or {})


# ── GET /api/v1/cleaning/metrics/{pipeline_run_id} ─────────────────────────

@router.get(
    "/metrics/{pipeline_run_id}",
    response_model=APIResponse[dict],
    summary="Get cleaning metrics",
)
def get_cleaning_metrics(
    pipeline_run_id: uuid.UUID,
    db: DbSession,
) -> APIResponse[dict]:
    from sqlalchemy import select
    from app.database.models.audit.audit_log import AuditLog
    from app.core.exceptions import NotFoundException

    stmt = (
        select(AuditLog)
        .where(AuditLog.run_id == pipeline_run_id, AuditLog.stage == "cleaning")
        .order_by(AuditLog.created_at.desc()).limit(1)
    )
    log = db.execute(stmt).scalar_one_or_none()
    if log is None:
        raise NotFoundException(message=f"No cleaning metrics for run {pipeline_run_id}")
    return APIResponse[dict].ok(data=(log.context_data or {}).get("metrics", {}))


# ── GET /api/v1/cleaning/report/{pipeline_run_id} ──────────────────────────

@router.get(
    "/report/{pipeline_run_id}",
    response_model=PaginatedResponse[CleaningActionResponse],
    summary="Get paginated cleaning action log",
)
def get_cleaning_report(
    pipeline_run_id: uuid.UUID,
    db: DbSession,
    pagination: Pagination,
) -> PaginatedResponse[CleaningActionResponse]:
    from sqlalchemy import select
    from app.database.models.audit.cleaning_log import CleaningLog

    stmt = (
        select(CleaningLog)
        .where(CleaningLog.pipeline_run_id == pipeline_run_id)
        .order_by(CleaningLog.created_at)
    )
    all_rows = list(db.execute(stmt).scalars().all())
    total = len(all_rows)
    paged = all_rows[pagination.offset: pagination.offset + pagination.page_size]

    return PaginatedResponse[CleaningActionResponse].ok(
        data=[
            CleaningActionResponse(
                rule_code=r.action_type.upper(),
                rule_category="cleaning",
                field_name=r.field_name or None,
                row_index=r.row_index,
                original_value=r.original_value,
                cleaned_value=r.cleaned_value,
                action_type=r.action_type,
                reason="",
                confidence=1.0,
            )
            for r in paged
        ],
        total_items=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


# ── GET /api/v1/cleaning/diff/{pipeline_run_id} ────────────────────────────

@router.get(
    "/diff/{pipeline_run_id}",
    response_model=PaginatedResponse[CleaningDiffRow],
    summary="Before/after diff for a cleaning run",
)
def get_cleaning_diff(
    pipeline_run_id: uuid.UUID,
    db: DbSession,
    pagination: Pagination,
) -> PaginatedResponse[CleaningDiffRow]:
    from sqlalchemy import select
    from app.database.models.audit.cleaning_log import CleaningLog

    stmt = (
        select(CleaningLog)
        .where(
            CleaningLog.pipeline_run_id == pipeline_run_id,
            CleaningLog.original_value != CleaningLog.cleaned_value,
        )
        .order_by(CleaningLog.created_at)
    )
    all_rows = list(db.execute(stmt).scalars().all())
    total = len(all_rows)
    paged = all_rows[pagination.offset: pagination.offset + pagination.page_size]

    return PaginatedResponse[CleaningDiffRow].ok(
        data=[
            CleaningDiffRow(
                row_index=r.row_index,
                field_name=r.field_name or None,
                original_value=r.original_value,
                cleaned_value=r.cleaned_value,
                rule_code=r.action_type.upper(),
                action_type=r.action_type,
                reason="",
            )
            for r in paged
        ],
        total_items=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )
