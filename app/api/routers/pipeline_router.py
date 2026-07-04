"""
Pipeline Orchestration API router.

POST /api/v1/pipelines/run                       — trigger a new pipeline run
POST /api/v1/pipelines/{run_id}/resume           — resume from checkpoint
POST /api/v1/pipelines/{run_id}/retry            — retry from scratch
POST /api/v1/pipelines/{run_id}/cancel           — cancel a running pipeline
GET  /api/v1/pipelines                           — list pipeline runs (with filters)
GET  /api/v1/pipelines/{run_id}                  — get run details
GET  /api/v1/pipelines/{run_id}/events           — lifecycle events for a run
GET  /api/v1/pipelines/{run_id}/metrics          — execution metrics
GET  /api/v1/pipelines/{run_id}/checkpoints      — checkpoint history
GET  /api/v1/pipelines/history                   — paginated execution history
GET  /api/v1/pipelines/definitions               — list registered pipeline definitions
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Query

from app.api.dependencies import DbSession, Pagination
from app.api.schemas.base_schemas import APIResponse, PaginatedResponse
from app.api.schemas.pipeline_schemas import (
    PipelineDefinitionResponse,
    PipelineHistoryItem,
    PipelineMetricsResponse,
    PipelineRunResponse,
    PipelineTriggerRequest,
)
from app.logging.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/pipelines", tags=["Pipeline Orchestration"])


# ── POST /api/v1/pipelines/run ─────────────────────────────────────────────

@router.post(
    "/run",
    response_model=APIResponse[PipelineRunResponse],
    summary="Trigger a new pipeline run",
    description=(
        "Executes the full ETL pipeline: Ingestion → Validation → Cleaning → "
        "Transformation → Load(placeholder). Returns the complete PipelineResult."
    ),
)
def run_pipeline(
    db: DbSession,
    request: PipelineTriggerRequest,
) -> APIResponse[PipelineRunResponse]:
    from app.pipeline.trigger_service import PipelineTriggerService

    svc = PipelineTriggerService(db)
    result = svc.trigger(
        dataset_type=request.dataset_type,
        source_file_path=request.source_file_path,
        original_filename=request.original_filename,
        pipeline_name=request.pipeline_name,
        triggered_by=request.triggered_by,
        trigger_type=request.trigger_type,
        retry_policy=request.retry_policy.model_dump() if request.retry_policy else None,
    )
    return APIResponse[PipelineRunResponse].ok(data=PipelineRunResponse.from_result(result))


# ── POST /api/v1/pipelines/{run_id}/resume ─────────────────────────────────

@router.post(
    "/{run_id}/resume",
    response_model=APIResponse[PipelineRunResponse],
    summary="Resume a pipeline from its last checkpoint",
)
def resume_pipeline(
    run_id: uuid.UUID,
    db: DbSession,
    source_file_path: Annotated[str, Body(embed=True)] = "",
) -> APIResponse[PipelineRunResponse]:
    from app.pipeline.trigger_service import PipelineTriggerService
    svc = PipelineTriggerService(db)
    result = svc.resume(str(run_id), source_file_path=source_file_path)
    return APIResponse[PipelineRunResponse].ok(data=PipelineRunResponse.from_result(result))


# ── POST /api/v1/pipelines/{run_id}/retry ──────────────────────────────────

@router.post(
    "/{run_id}/retry",
    response_model=APIResponse[PipelineRunResponse],
    summary="Retry a failed pipeline run from scratch",
)
def retry_pipeline(
    run_id: uuid.UUID,
    db: DbSession,
    source_file_path: Annotated[str, Body(embed=True)] = "",
) -> APIResponse[PipelineRunResponse]:
    from app.pipeline.trigger_service import PipelineTriggerService
    svc = PipelineTriggerService(db)
    result = svc.retry(str(run_id), source_file_path=source_file_path)
    return APIResponse[PipelineRunResponse].ok(data=PipelineRunResponse.from_result(result))


# ── POST /api/v1/pipelines/{run_id}/cancel ─────────────────────────────────

@router.post(
    "/{run_id}/cancel",
    response_model=APIResponse[dict],
    summary="Cancel a running pipeline",
)
def cancel_pipeline(run_id: uuid.UUID, db: DbSession) -> APIResponse[dict]:
    from app.pipeline.trigger_service import PipelineTriggerService
    svc = PipelineTriggerService(db)
    success = svc.cancel(str(run_id))
    return APIResponse[dict].ok(data={"cancelled": success, "run_id": str(run_id)})


# ── GET /api/v1/pipelines ─────────────────────────────────────────────────

@router.get(
    "",
    response_model=PaginatedResponse[PipelineHistoryItem],
    summary="List pipeline runs",
)
def list_pipeline_runs(
    db: DbSession,
    pagination: Pagination,
    status: str | None = Query(default=None),
    dataset_type: str | None = Query(default=None),
    pipeline_name: str | None = Query(default=None),
) -> PaginatedResponse[PipelineHistoryItem]:
    from sqlalchemy import select, desc
    from app.database.models.pipeline.pipeline_run import PipelineRun

    stmt = select(PipelineRun).order_by(desc(PipelineRun.created_at))
    if status:
        stmt = stmt.where(PipelineRun.status == status)
    if dataset_type:
        stmt = stmt.where(PipelineRun.dataset_type == dataset_type)
    if pipeline_name:
        stmt = stmt.where(PipelineRun.pipeline_name == pipeline_name)

    all_runs = list(db.execute(stmt).scalars().all())
    total = len(all_runs)
    paged = all_runs[pagination.offset: pagination.offset + pagination.page_size]

    return PaginatedResponse[PipelineHistoryItem].ok(
        data=[_run_to_history_item(r) for r in paged],
        total_items=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


# ── GET /api/v1/pipelines/{run_id} ───────────────────────────────────────

@router.get(
    "/{run_id}",
    response_model=APIResponse[dict],
    summary="Get pipeline run details",
)
def get_pipeline_run(run_id: uuid.UUID, db: DbSession) -> APIResponse[dict]:
    from sqlalchemy import select
    from app.database.models.pipeline.pipeline_run import PipelineRun
    from app.database.models.pipeline.stage_result import StageResult
    from app.core.exceptions import NotFoundException

    run = db.execute(select(PipelineRun).where(PipelineRun.id == run_id)).scalar_one_or_none()
    if run is None:
        raise NotFoundException(message=f"Pipeline run {run_id} not found")

    stages = list(db.execute(
        select(StageResult)
        .where(StageResult.pipeline_run_id == run_id)
        .order_by(StageResult.stage_order)
    ).scalars().all())

    return APIResponse[dict].ok(data={
        "id": str(run.id),
        "run_number": run.run_number,
        "pipeline_name": run.pipeline_name,
        "dataset_type": run.dataset_type,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "duration_seconds": float(run.duration_seconds) if run.duration_seconds else None,
        "total_records": run.total_records,
        "valid_records": run.valid_records,
        "quality_score": float(run.quality_score) if run.quality_score else None,
        "error_message": run.error_message,
        "triggered_by": run.triggered_by,
        "stage_results": [
            {
                "stage_name": s.stage_name,
                "stage_order": s.stage_order,
                "status": s.status,
                "duration_ms": s.duration_ms,
                "input_records": s.input_records,
                "output_records": s.output_records,
                "error_message": s.error_message,
            }
            for s in stages
        ],
    })


# ── GET /api/v1/pipelines/{run_id}/events ────────────────────────────────

@router.get(
    "/{run_id}/events",
    response_model=PaginatedResponse[dict],
    summary="Get lifecycle events for a pipeline run",
)
def get_pipeline_events(
    run_id: uuid.UUID,
    db: DbSession,
    pagination: Pagination,
    event_type: str | None = Query(default=None),
) -> PaginatedResponse[dict]:
    from sqlalchemy import select
    from app.database.models.audit.audit_log import AuditLog

    stmt = (
        select(AuditLog)
        .where(AuditLog.run_id == run_id)
        .order_by(AuditLog.created_at)
    )
    if event_type:
        stmt = stmt.where(AuditLog.event_type == event_type)

    all_events = list(db.execute(stmt).scalars().all())
    total = len(all_events)
    paged = all_events[pagination.offset: pagination.offset + pagination.page_size]

    return PaginatedResponse[dict].ok(
        data=[{
            "event_type": e.event_type,
            "stage": e.stage,
            "message": e.message,
            "severity": e.severity,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        } for e in paged],
        total_items=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


# ── GET /api/v1/pipelines/{run_id}/metrics ───────────────────────────────

@router.get(
    "/{run_id}/metrics",
    response_model=APIResponse[dict],
    summary="Get execution metrics for a pipeline run",
)
def get_pipeline_metrics(run_id: uuid.UUID, db: DbSession) -> APIResponse[dict]:
    from sqlalchemy import select
    from app.database.models.pipeline.pipeline_run import PipelineRun
    from app.core.exceptions import NotFoundException

    run = db.execute(select(PipelineRun).where(PipelineRun.id == run_id)).scalar_one_or_none()
    if run is None:
        raise NotFoundException(message=f"Pipeline run {run_id} not found")

    return APIResponse[dict].ok(data={
        "run_id": str(run.id),
        "status": run.status,
        "duration_seconds": float(run.duration_seconds) if run.duration_seconds else None,
        "total_records": run.total_records,
        "valid_records": run.valid_records,
        "cleaned_records": run.cleaned_records,
        "loaded_records": run.loaded_records,
        "failed_records": run.failed_records,
        "warning_count": run.warning_count,
        "quality_score": float(run.quality_score) if run.quality_score else None,
        "stage_metrics": run.metrics or {},
    })


# ── GET /api/v1/pipelines/{run_id}/checkpoints ───────────────────────────

@router.get(
    "/{run_id}/checkpoints",
    response_model=APIResponse[list],
    summary="Get checkpoint history for a pipeline run",
)
def get_pipeline_checkpoints(run_id: uuid.UUID, db: DbSession) -> APIResponse[list]:
    from app.pipeline.checkpoint_manager import CheckpointManager
    mgr = CheckpointManager(db)
    checkpoints = mgr.list_checkpoints(str(run_id))
    return APIResponse[list].ok(data=checkpoints)


# ── GET /api/v1/pipelines/history ────────────────────────────────────────

@router.get(
    "/history",
    response_model=PaginatedResponse[PipelineHistoryItem],
    summary="Get paginated pipeline execution history",
)
def get_pipeline_history(
    db: DbSession,
    pagination: Pagination,
    dataset_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> PaginatedResponse[PipelineHistoryItem]:
    return list_pipeline_runs(db, pagination, status, dataset_type, None)


# ── GET /api/v1/pipelines/definitions ────────────────────────────────────

@router.get(
    "/definitions",
    response_model=APIResponse[list[PipelineDefinitionResponse]],
    summary="List all registered pipeline definitions",
)
def list_pipeline_definitions() -> APIResponse[list[PipelineDefinitionResponse]]:
    from app.pipeline.pipeline_registry import get_registry
    registry = get_registry()
    return APIResponse[list[PipelineDefinitionResponse]].ok(
        data=[
            PipelineDefinitionResponse(**d.to_dict())
            for d in registry.list_all()
        ]
    )


# ── Helper ────────────────────────────────────────────────────────────────

def _run_to_history_item(run) -> PipelineHistoryItem:
    return PipelineHistoryItem(
        id=str(run.id),
        run_number=run.run_number,
        pipeline_name=run.pipeline_name,
        dataset_type=run.dataset_type,
        status=run.status,
        quality_score=float(run.quality_score) if run.quality_score else None,
        total_records=run.total_records,
        duration_seconds=float(run.duration_seconds) if run.duration_seconds else None,
        created_at=run.created_at.isoformat() if run.created_at else "",
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        triggered_by=run.triggered_by,
    )
