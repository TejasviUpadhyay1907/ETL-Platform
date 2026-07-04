"""
Load Reports API router — /api/v1/load

POST /api/v1/load/run                    — trigger a load for a pipeline run
GET  /api/v1/load/report/{run_id}        — load audit report
GET  /api/v1/load/summary/{run_id}       — load summary
GET  /api/v1/load/metrics/{run_id}       — load metrics
GET  /api/v1/load/history                — load history (paginated)
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body

from app.api.dependencies import DbSession, Pagination
from app.api.schemas.base_schemas import APIResponse, PaginatedResponse
from app.logging.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/load", tags=["Warehouse Loading"])


@router.post(
    "/run",
    response_model=APIResponse[dict],
    summary="Trigger a warehouse load for a completed pipeline run",
)
def run_load(
    db: DbSession,
    pipeline_run_id: Annotated[str, Body(embed=True)],
    dataset_type: Annotated[str, Body(embed=True)],
    strategy: Annotated[str | None, Body(embed=True)] = None,
) -> APIResponse[dict]:
    """Load transformed data for a pipeline run into the warehouse."""
    from sqlalchemy import select
    from pathlib import Path
    from app.database.models.pipeline.pipeline_run import PipelineRun
    from app.database.models.audit.audit_log import AuditLog
    from app.ingestion.readers.reader_factory import ReaderFactory
    from app.transformation.transformation_engine import TransformationEngine
    from app.loading.loader import WarehouseLoader
    from app.core.exceptions import NotFoundException
    import uuid as _uuid

    # Get the transformation output from audit log context
    stmt = (
        select(AuditLog)
        .where(
            AuditLog.run_id == _uuid.UUID(pipeline_run_id),
            AuditLog.stage == "transformation",
            AuditLog.event_type == "STAGE_COMPLETED",
        )
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    trans_log = db.execute(stmt).scalar_one_or_none()

    if trans_log is None:
        # Try loading from ingestion event
        from app.database.models.pipeline.ingestion_event import IngestionEvent
        ie_stmt = (
            select(IngestionEvent)
            .where(IngestionEvent.pipeline_run_id == _uuid.UUID(pipeline_run_id))
            .limit(1)
        )
        event = db.execute(ie_stmt).scalar_one_or_none()
        if event is None:
            raise NotFoundException(message=f"No data found for pipeline run {pipeline_run_id}")

        # Re-read and transform the file
        file_path = Path(event.file_path)
        if not file_path.exists():
            from app.core.exceptions import FileNotFoundException
            raise FileNotFoundException(message=f"File not found: {event.file_path}")

        reader = ReaderFactory.get_reader(event.file_extension)
        df, _ = reader.read(file_path)

        engine = TransformationEngine(session=db)
        trans_result = engine.transform(
            cleaned_df=df,
            dataset_type=dataset_type,
            pipeline_run_id=pipeline_run_id,
        )
        target_df = trans_result.transformed_df
    else:
        # Use a minimal DataFrame from the context data (just for re-triggering)
        import pandas as pd
        target_df = pd.DataFrame()

    loader = WarehouseLoader(session=db, strategy_override=strategy)
    result = loader.load(
        transformed_df=target_df,
        dataset_type=dataset_type,
        pipeline_run_id=pipeline_run_id,
    )

    return APIResponse[dict].ok(data={
        "success": result.success,
        "rows_loaded": result.rows_loaded,
        "rows_inserted": result.rows_inserted,
        "rows_updated": result.rows_updated,
        "rows_failed": result.rows_failed,
        "strategy_used": result.strategy_used,
        "target_table": result.target_table,
        "idempotent_skip": result.idempotent_skip,
        "error_message": result.error_message,
    })


@router.get(
    "/report/{pipeline_run_id}",
    response_model=APIResponse[dict],
    summary="Get load audit report for a pipeline run",
)
def get_load_report(
    pipeline_run_id: uuid.UUID,
    db: DbSession,
) -> APIResponse[dict]:
    from sqlalchemy import select
    from app.database.models.audit.audit_log import AuditLog
    from app.core.exceptions import NotFoundException

    stmt = (
        select(AuditLog)
        .where(
            AuditLog.run_id == pipeline_run_id,
            AuditLog.event_type == "RECORD_LOADED",
            AuditLog.stage == "load",
        )
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    log = db.execute(stmt).scalar_one_or_none()
    if log is None:
        raise NotFoundException(message=f"No load report for run {pipeline_run_id}")

    return APIResponse[dict].ok(data=log.context_data or {})


@router.get(
    "/summary/{pipeline_run_id}",
    response_model=APIResponse[dict],
    summary="Get load summary for a pipeline run",
)
def get_load_summary(
    pipeline_run_id: uuid.UUID,
    db: DbSession,
) -> APIResponse[dict]:
    from sqlalchemy import select
    from app.database.models.pipeline.pipeline_run import PipelineRun
    from app.core.exceptions import NotFoundException

    run = db.execute(
        select(PipelineRun).where(PipelineRun.id == pipeline_run_id)
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundException(message=f"Pipeline run {pipeline_run_id} not found")

    return APIResponse[dict].ok(data={
        "pipeline_run_id": str(run.id),
        "dataset_type": run.dataset_type,
        "status": run.status,
        "total_records": run.total_records,
        "loaded_records": run.loaded_records,
        "failed_records": run.failed_records,
        "quality_score": float(run.quality_score) if run.quality_score else None,
    })


@router.get(
    "/metrics/{pipeline_run_id}",
    response_model=APIResponse[dict],
    summary="Get load execution metrics",
)
def get_load_metrics(
    pipeline_run_id: uuid.UUID,
    db: DbSession,
) -> APIResponse[dict]:
    from sqlalchemy import select
    from app.database.models.audit.audit_log import AuditLog
    from app.core.exceptions import NotFoundException

    stmt = (
        select(AuditLog)
        .where(
            AuditLog.run_id == pipeline_run_id,
            AuditLog.event_type == "RECORD_LOADED",
            AuditLog.stage == "load",
        )
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    log = db.execute(stmt).scalar_one_or_none()
    if log is None:
        raise NotFoundException(message=f"No load metrics for run {pipeline_run_id}")

    ctx = log.context_data or {}
    return APIResponse[dict].ok(data=ctx.get("metrics", {}))


@router.get(
    "/history",
    response_model=PaginatedResponse[dict],
    summary="Get paginated load history",
)
def get_load_history(
    db: DbSession,
    pagination: Pagination,
    dataset_type: str | None = None,
) -> PaginatedResponse[dict]:
    from sqlalchemy import select, desc
    from app.database.models.audit.audit_log import AuditLog

    stmt = (
        select(AuditLog)
        .where(AuditLog.event_type == "RECORD_LOADED", AuditLog.stage == "load")
        .order_by(desc(AuditLog.created_at))
    )

    all_logs = list(db.execute(stmt).scalars().all())
    if dataset_type:
        all_logs = [
            l for l in all_logs
            if (l.context_data or {}).get("dataset_type") == dataset_type
        ]

    total = len(all_logs)
    paged = all_logs[pagination.offset: pagination.offset + pagination.page_size]

    return PaginatedResponse[dict].ok(
        data=[{
            "run_id": str(l.run_id) if l.run_id else None,
            "message": l.message,
            "created_at": l.created_at.isoformat() if l.created_at else None,
            "success": l.severity == "INFO",
            "metrics": (l.context_data or {}).get("metrics", {}),
        } for l in paged],
        total_items=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )
