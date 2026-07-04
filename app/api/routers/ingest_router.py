"""
Ingestion API router — /api/v1/ingest

Endpoints:
  POST /api/v1/ingest/upload              — single file upload
  POST /api/v1/ingest/upload/batch        — multiple files in one request
  GET  /api/v1/ingest/events              — list ingestion events (paginated)
  GET  /api/v1/ingest/events/{event_id}   — get event details
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile, status

from app.api.dependencies import DbSession, Pagination
from app.api.schemas.base_schemas import APIResponse, PaginatedResponse
from app.api.schemas.ingest_schemas import (
    BatchUploadResponse,
    IngestionEventResponse,
    SingleUploadResponse,
)
from app.logging.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/ingest", tags=["Ingestion"])


# ---------------------------------------------------------------------------
# POST /api/v1/ingest/upload
# ---------------------------------------------------------------------------

@router.post(
    "/upload",
    response_model=APIResponse[SingleUploadResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a single dataset file",
    description=(
        "Upload a CSV or Excel file for ingestion. "
        "The file is validated, hashed, stored, and read into an internal "
        "Dataset object ready for the downstream validation stage. "
        "Returns ingestion metadata including dataset type, row count, and event ID."
    ),
)
async def upload_single_file(
    request: Request,
    db: DbSession,
    file: UploadFile = File(..., description="CSV or Excel file to ingest"),
    dataset_type: str | None = Form(
        default=None,
        description=(
            "Override dataset type detection. "
            "One of: orders, customers, products, inventory, suppliers, payments"
        ),
    ),
) -> APIResponse[SingleUploadResponse]:
    """Ingest a single uploaded file."""
    from app.ingestion.file_receiver import FileReceiver

    request_id = getattr(request.state, "request_id", None)
    client_ip = request.client.host if request.client else None

    logger.info(
        "Upload received",
        filename=file.filename,
        content_type=file.content_type,
        dataset_type_hint=dataset_type,
        request_id=request_id,
    )

    content = await file.read()
    receiver = FileReceiver(db)
    result = receiver.receive_upload(
        file_bytes=content,
        original_filename=file.filename or "unknown_file",
        explicit_dataset_type=dataset_type,
        uploaded_by=request.headers.get("X-API-Key"),
        source_ip=client_ip,
    )

    if result.success:
        payload = SingleUploadResponse.from_result(result)
        return APIResponse[SingleUploadResponse].ok(data=payload, request_id=request_id)

    # Return 422 for rejected/duplicate files so clients get structured error
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    if result.is_duplicate:
        http_status = status.HTTP_409_CONFLICT

    from fastapi.responses import JSONResponse
    from app.api.schemas.base_schemas import APIError, ResponseMeta
    import datetime

    error_body = {
        "success": False,
        "data": None,
        "error": {
            "code": result.error_code or "INGESTION_FAILED",
            "message": result.error_message or "Ingestion failed",
            "details": [],
        },
        "meta": {
            "request_id": request_id,
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "version": "1.0",
        },
    }
    return JSONResponse(status_code=http_status, content=error_body)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# POST /api/v1/ingest/upload/batch
# ---------------------------------------------------------------------------

@router.post(
    "/upload/batch",
    response_model=APIResponse[BatchUploadResponse],
    status_code=status.HTTP_207_MULTI_STATUS,
    summary="Upload multiple dataset files in one request",
    description=(
        "Upload up to 10 CSV or Excel files in a single request. "
        "Each file is processed independently. The response includes "
        "per-file results — partial success is possible."
    ),
)
async def upload_batch_files(
    request: Request,
    db: DbSession,
    files: list[UploadFile] = File(..., description="Up to 10 files"),
    dataset_type: str | None = Form(
        default=None,
        description="Apply same dataset type override to all files",
    ),
) -> APIResponse[BatchUploadResponse]:
    """Ingest multiple files in a single request."""
    from app.ingestion.file_receiver import BatchFileReceiver

    if len(files) > 10:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 10 files per batch upload.",
        )

    request_id = getattr(request.state, "request_id", None)
    client_ip = request.client.host if request.client else None
    api_key = request.headers.get("X-API-Key")

    file_pairs: list[tuple[bytes, str]] = []
    for f in files:
        content = await f.read()
        file_pairs.append((content, f.filename or "unknown_file"))

    receiver = BatchFileReceiver(db)
    results = receiver.receive_many_uploads(
        files=file_pairs,
        uploaded_by=api_key,
        source_ip=client_ip,
    )

    payload = BatchUploadResponse.from_results(results)
    return APIResponse[BatchUploadResponse].ok(data=payload, request_id=request_id)


# ---------------------------------------------------------------------------
# GET /api/v1/ingest/events
# ---------------------------------------------------------------------------

@router.get(
    "/events",
    response_model=PaginatedResponse[IngestionEventResponse],
    summary="List ingestion events",
    description="Returns a paginated list of file ingestion events, most recent first.",
)
def list_ingestion_events(
    db: DbSession,
    pagination: Pagination,
    dataset_type: str | None = None,
    status: str | None = None,
) -> PaginatedResponse[IngestionEventResponse]:
    """List ingestion events with optional filtering."""
    from app.database.repositories.ingestion_event_repository import (
        IngestionEventRepository,
    )
    from sqlalchemy import desc, select
    from app.database.models.pipeline.ingestion_event import IngestionEvent

    repo = IngestionEventRepository(db)

    # Build filtered query
    stmt = select(IngestionEvent).order_by(desc(IngestionEvent.created_at))
    if dataset_type:
        stmt = stmt.where(IngestionEvent.dataset_type == dataset_type)
    if status:
        stmt = stmt.where(IngestionEvent.status == status)

    total = db.execute(
        select(IngestionEvent).where(
            *(
                [IngestionEvent.dataset_type == dataset_type] if dataset_type else []
            )
        )
    ).scalars().all()
    total_count = len(total)

    stmt = stmt.limit(pagination.page_size).offset(pagination.offset)
    events = list(db.execute(stmt).scalars().all())

    return PaginatedResponse[IngestionEventResponse].ok(
        data=[IngestionEventResponse.from_orm_model(e) for e in events],
        total_items=total_count,
        page=pagination.page,
        page_size=pagination.page_size,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/ingest/events/{event_id}
# ---------------------------------------------------------------------------

@router.get(
    "/events/{event_id}",
    response_model=APIResponse[IngestionEventResponse],
    summary="Get ingestion event details",
)
def get_ingestion_event(
    event_id: uuid.UUID,
    db: DbSession,
) -> APIResponse[IngestionEventResponse]:
    """Retrieve a single ingestion event by ID."""
    from app.database.repositories.ingestion_event_repository import (
        IngestionEventRepository,
    )
    from app.core.exceptions import NotFoundException

    repo = IngestionEventRepository(db)
    event = repo.get_by_id_or_raise(event_id)
    return APIResponse[IngestionEventResponse].ok(
        data=IngestionEventResponse.from_orm_model(event)
    )
