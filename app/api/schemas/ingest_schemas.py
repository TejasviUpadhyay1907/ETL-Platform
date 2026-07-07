"""
Pydantic schemas for ingestion API request/response models.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SingleUploadResponse(BaseModel):
    """Response for a successful single file upload."""

    ingestion_event_id: str
    processing_id: str
    original_filename: str
    stored_filename: str
    dataset_type: str | None
    file_size_bytes: int
    file_hash: str | None
    encoding: str | None
    delimiter: str | None
    row_count: int | None
    column_count: int | None
    column_names: list[str]
    excel_sheet_names: list[str]
    status: str
    is_duplicate: bool
    duplicate_of_event_id: str | None
    reader_used: str
    ingested_at: str

    @classmethod
    def from_result(cls, result: Any) -> "SingleUploadResponse":
        """Build response from an IngestionResult."""
        ds = result.dataset
        meta = result.file_metadata or (ds.metadata if ds else None)
        return cls(
            ingestion_event_id=result.ingestion_event_id or "",
            processing_id=ds.processing_id if ds else "",
            original_filename=meta.original_filename if meta else "",
            stored_filename=meta.stored_filename if meta else "",
            dataset_type=meta.dataset_type if meta else None,
            file_size_bytes=meta.file_size_bytes if meta else 0,
            file_hash=meta.file_hash if meta else None,
            encoding=meta.encoding if meta else None,
            delimiter=meta.delimiter if meta else None,
            row_count=ds.row_count if ds else None,
            column_count=ds.column_count if ds else None,
            column_names=ds.columns if ds else [],
            excel_sheet_names=meta.excel_sheet_names if meta else [],
            status=result.status,
            is_duplicate=result.is_duplicate,
            duplicate_of_event_id=result.duplicate_of_event_id,
            reader_used=ds.reader_used if ds else "",
            ingested_at=datetime.utcnow().isoformat(),
        )


class FileUploadResult(BaseModel):
    """Per-file result within a batch upload response."""

    filename: str
    success: bool
    status: str
    ingestion_event_id: str | None = None
    dataset_type: str | None = None
    row_count: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    is_duplicate: bool = False

    @classmethod
    def from_result(cls, filename: str, result: Any) -> "FileUploadResult":
        ds = result.dataset
        meta = result.file_metadata or (ds.metadata if ds else None)
        return cls(
            filename=filename,
            success=result.success,
            status=result.status,
            ingestion_event_id=result.ingestion_event_id,
            dataset_type=meta.dataset_type if meta else None,
            row_count=ds.row_count if ds else None,
            error_code=result.error_code,
            error_message=result.error_message,
            is_duplicate=result.is_duplicate,
        )


class BatchUploadResponse(BaseModel):
    """Response for a batch file upload."""

    total_files: int
    succeeded: int
    failed: int
    results: list[FileUploadResult]

    @classmethod
    def from_results(cls, results: list[Any]) -> "BatchUploadResponse":
        file_results = []
        for i, result in enumerate(results):
            meta = result.file_metadata
            ds = result.dataset
            fname = (
                meta.original_filename if meta
                else (ds.metadata.original_filename if ds else f"file_{i+1}")
            )
            file_results.append(FileUploadResult.from_result(fname, result))

        succeeded = sum(1 for r in file_results if r.success)
        return cls(
            total_files=len(results),
            succeeded=succeeded,
            failed=len(results) - succeeded,
            results=file_results,
        )


class IngestionEventResponse(BaseModel):
    """API response model for an IngestionEvent database record."""

    id: str
    original_filename: str
    stored_filename: str
    file_path: str | None         # actual stored path on disk
    file_extension: str
    file_size_bytes: int
    file_hash: str | None
    dataset_type: str
    status: str
    source_type: str
    uploaded_by: str | None
    row_count_raw: int | None
    row_count_data: int | None
    rejection_reason: str | None
    pipeline_run_id: str | None
    created_at: str

    @classmethod
    def from_orm_model(cls, event: Any) -> "IngestionEventResponse":
        return cls(
            id=str(event.id),
            original_filename=event.original_filename,
            stored_filename=event.stored_filename,
            file_path=str(event.file_path) if event.file_path else None,
            file_extension=event.file_extension,
            file_size_bytes=event.file_size_bytes,
            file_hash=event.file_hash,
            dataset_type=event.dataset_type,
            status=event.status,
            source_type=event.source_type,
            uploaded_by=event.uploaded_by,
            row_count_raw=event.row_count_raw,
            row_count_data=event.row_count_data,
            rejection_reason=event.rejection_reason,
            pipeline_run_id=str(event.pipeline_run_id) if event.pipeline_run_id else None,
            created_at=event.created_at.isoformat() if event.created_at else "",
        )
