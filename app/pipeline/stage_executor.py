"""
StageExecutor — wraps each ETL engine call with timing, error capture, and events.

Every stage follows the same pattern:
  1. Emit STAGE_STARTED event
  2. Execute the stage engine
  3. Emit STAGE_COMPLETED or STAGE_FAILED event
  4. Return PipelineStageResult

The StageExecutor contains NO business logic — it only calls the
already-implemented engines and records what happened.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.logging.logger import get_logger
from app.pipeline.context import PipelineContext
from app.pipeline.models import PipelineStageResult, StageName

logger = get_logger(__name__)


class StageExecutor:
    """Executes one pipeline stage and returns a PipelineStageResult."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Stage 1: Ingestion
    # ------------------------------------------------------------------

    def run_ingestion(
        self, ctx: PipelineContext, event_emitter: "EventEmitter"
    ) -> PipelineStageResult:
        """Execute the ingestion stage using the existing IngestionService."""
        stage = StageName.INGESTION
        result = self._make_result(stage, 0)
        event_emitter.emit_stage_started(ctx, stage)
        start = time.perf_counter()

        try:
            from app.ingestion.ingestion_service import IngestionService
            from app.ingestion.raw_file_store import RawFileStore
            from pathlib import Path
            from app.core.config import get_config

            config = get_config()

            # If ingestion_event_id is provided, load the already-ingested dataset
            # instead of re-ingesting (avoids duplicate detection failure)
            if ctx.ingestion_event_id:
                ingestion_result = self._load_from_ingestion_event(
                    ctx.ingestion_event_id, ctx.dataset_type
                )
            elif ctx.source_file_path:
                svc = IngestionService(
                    session=self._session,
                    file_store=RawFileStore(config.upload_directory),
                )
                ingestion_result = svc.ingest(
                    source_path=Path(ctx.source_file_path),
                    original_filename=ctx.original_filename or Path(ctx.source_file_path).name,
                    explicit_dataset_type=ctx.dataset_type,
                    source_type=ctx.trigger_type,
                    uploaded_by=ctx.triggered_by,
                )
            else:
                from app.ingestion.models import IngestionResult, IngestionStatus
                ingestion_result = IngestionResult(
                    success=False,
                    status=IngestionStatus.REJECTED,
                    error_message="No source_file_path or ingestion_event_id provided",
                    error_code="NO_SOURCE_FILE",
                )

            result.stage_output = ingestion_result
            result.duration_ms = (time.perf_counter() - start) * 1000
            result.completed_at = datetime.now(tz=timezone.utc)

            if ingestion_result.success:
                ds = ingestion_result.dataset
                result.output_records = ds.row_count if ds else 0
                result.input_records  = ds.row_count if ds else 0
                result.status = "success"
                result.details = {
                    "ingestion_event_id": ingestion_result.ingestion_event_id,
                    "reader_used": ds.reader_used if ds else "",
                    "file_hash": ingestion_result.file_metadata.file_hash
                        if ingestion_result.file_metadata else None,
                }
                event_emitter.emit_stage_completed(ctx, stage, result)
            else:
                result.status = "failed"
                result.error_message = ingestion_result.error_message
                event_emitter.emit_stage_failed(ctx, stage, result)

        except Exception as exc:
            result = self._handle_exception(ctx, stage, result, exc, event_emitter, start)

        return result

    # ------------------------------------------------------------------
    # Stage 2: Validation
    # ------------------------------------------------------------------

    def run_validation(
        self, ctx: PipelineContext, ingestion_result: Any, event_emitter: "EventEmitter"
    ) -> PipelineStageResult:
        """Execute the validation stage using the existing ValidationEngine."""
        stage = StageName.VALIDATION
        result = self._make_result(stage, 1)
        event_emitter.emit_stage_started(ctx, stage)
        start = time.perf_counter()

        try:
            from app.validation.validator import ValidationEngine

            dataset = ingestion_result.dataset
            result.input_records = dataset.row_count if dataset else 0

            engine = ValidationEngine(session=self._session)
            val_result = engine.validate(dataset, pipeline_run_id=ctx.pipeline_run_id)

            result.stage_output = val_result
            result.duration_ms  = (time.perf_counter() - start) * 1000
            result.completed_at = datetime.now(tz=timezone.utc)
            result.output_records   = val_result.valid_count + val_result.warning_count
            result.rejected_records = val_result.rejected_count
            result.warning_count    = len(val_result.report.warning_violations)
            result.quality_score    = val_result.quality_score

            result.status = "success" if val_result.success else "warning"
            result.details = {
                "quality_score":  val_result.quality_score,
                "letter_grade":   val_result.letter_grade,
                "valid_count":    val_result.valid_count,
                "rejected_count": val_result.rejected_count,
                "total_violations": val_result.report.violation_count,
            }
            event_emitter.emit_stage_completed(ctx, stage, result)

        except Exception as exc:
            result = self._handle_exception(ctx, stage, result, exc, event_emitter, start)

        return result

    # ------------------------------------------------------------------
    # Stage 3: Cleaning
    # ------------------------------------------------------------------

    def run_cleaning(
        self, ctx: PipelineContext, validation_result: Any, event_emitter: "EventEmitter"
    ) -> PipelineStageResult:
        """Execute the cleaning stage using the existing CleaningEngine."""
        stage = StageName.CLEANING
        result = self._make_result(stage, 2)
        event_emitter.emit_stage_started(ctx, stage)
        start = time.perf_counter()

        try:
            from app.cleaning.cleaner import CleaningEngine

            result.input_records = (
                validation_result.valid_count + validation_result.warning_count
            )
            engine = CleaningEngine(session=self._session)
            clean_result = engine.clean(
                validation_result,
                pipeline_run_id=ctx.pipeline_run_id,
                original_filename=ctx.original_filename,
            )

            result.stage_output   = clean_result
            result.duration_ms    = (time.perf_counter() - start) * 1000
            result.completed_at   = datetime.now(tz=timezone.utc)
            result.output_records = clean_result.row_count
            result.rejected_records = clean_result.rows_dropped
            result.warning_count  = len(clean_result.warnings)
            result.status         = "success" if clean_result.success else "failed"
            result.error_message  = clean_result.errors[0] if clean_result.errors else None
            result.details        = {
                "rows_dropped":   clean_result.rows_dropped,
                "total_actions":  clean_result.total_actions,
                "cleaning_pct":   clean_result.cleaning_metrics.cleaning_pct,
            }

            if clean_result.success:
                event_emitter.emit_stage_completed(ctx, stage, result)
            else:
                event_emitter.emit_stage_failed(ctx, stage, result)

        except Exception as exc:
            result = self._handle_exception(ctx, stage, result, exc, event_emitter, start)

        return result

    # ------------------------------------------------------------------
    # Stage 4: Transformation
    # ------------------------------------------------------------------

    def run_transformation(
        self, ctx: PipelineContext, cleaning_result: Any, event_emitter: "EventEmitter"
    ) -> PipelineStageResult:
        """Execute the transformation stage using the existing TransformationEngine."""
        stage = StageName.TRANSFORMATION
        result = self._make_result(stage, 3)
        event_emitter.emit_stage_started(ctx, stage)
        start = time.perf_counter()

        try:
            from app.transformation.transformation_engine import TransformationEngine

            result.input_records = cleaning_result.row_count
            engine = TransformationEngine(session=self._session)
            trans_result = engine.transform(
                cleaned_df=cleaning_result.cleaned_df,
                dataset_type=cleaning_result.dataset_type,
                original_filename=ctx.original_filename,
                pipeline_run_id=ctx.pipeline_run_id,
            )

            result.stage_output   = trans_result
            result.duration_ms    = (time.perf_counter() - start) * 1000
            result.completed_at   = datetime.now(tz=timezone.utc)
            result.output_records = trans_result.row_count
            result.status         = "success" if trans_result.success else "failed"
            result.error_message  = trans_result.error_message
            result.details        = {
                "added_columns":   trans_result.report.added_columns,
                "total_actions":   len(trans_result.report.actions),
                "output_columns":  len(trans_result.columns),
            }

            if trans_result.success:
                event_emitter.emit_stage_completed(ctx, stage, result)
            else:
                event_emitter.emit_stage_failed(ctx, stage, result)

        except Exception as exc:
            result = self._handle_exception(ctx, stage, result, exc, event_emitter, start)

        return result

    # ------------------------------------------------------------------
    # Stage 5: Load (placeholder interface)
    # ------------------------------------------------------------------

    def run_load(
        self, ctx: PipelineContext, transformation_result: Any, event_emitter: "EventEmitter"
    ) -> PipelineStageResult:
        """
        Load stage — calls the production WarehouseLoader (Phase 9).

        Receives the TransformationResult and writes the analytics-ready
        DataFrame to the target warehouse tables using the configured load strategy.
        """
        stage = StageName.LOAD
        result = self._make_result(stage, 4)
        event_emitter.emit_stage_started(ctx, stage)
        start = time.perf_counter()

        try:
            from app.loading.loader import WarehouseLoader

            rows = transformation_result.row_count if transformation_result else 0
            result.input_records = rows

            loader = WarehouseLoader(session=self._session)
            load_result = loader.load(
                transformed_df=transformation_result.transformed_df,
                dataset_type=transformation_result.dataset_type,
                pipeline_run_id=ctx.pipeline_run_id,
            )

            result.duration_ms    = (time.perf_counter() - start) * 1000
            result.completed_at   = datetime.now(tz=timezone.utc)
            result.output_records = load_result.rows_loaded
            result.rejected_records = load_result.rows_failed
            result.status         = "success" if load_result.success else "failed"
            result.error_message  = load_result.error_message
            result.stage_output   = load_result
            result.details        = {
                "rows_loaded":    load_result.rows_loaded,
                "rows_inserted":  load_result.rows_inserted,
                "rows_updated":   load_result.rows_updated,
                "rows_skipped":   load_result.rows_skipped,
                "rows_failed":    load_result.rows_failed,
                "target_table":   load_result.target_table,
                "strategy_used":  load_result.strategy_used,
                "idempotent_skip": load_result.idempotent_skip,
            }

            if load_result.success:
                event_emitter.emit_stage_completed(ctx, stage, result)
            else:
                event_emitter.emit_stage_failed(ctx, stage, result)

        except Exception as exc:
            result = self._handle_exception(ctx, stage, result, exc, event_emitter, start)

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _make_result(self, stage_name: str, order: int) -> PipelineStageResult:
        return PipelineStageResult(
            stage_name=stage_name,
            stage_order=order,
            status="running",
            started_at=datetime.now(tz=timezone.utc),
        )

    def _load_from_ingestion_event(self, ingestion_event_id: str, dataset_type: str):
        """
        Load an already-ingested dataset from an IngestionEvent record.

        Used when the file was pre-ingested via /ingest/upload and we want
        to run the pipeline without re-ingesting (avoids duplicate detection).
        """
        from app.ingestion.models import (
            IngestionResult, IngestionStatus, Dataset, DatasetSchema, FileMetadata
        )
        from sqlalchemy import select
        import uuid as _uuid
        from pathlib import Path

        try:
            from app.database.models.pipeline.ingestion_event import IngestionEvent
            ev = self._session.execute(
                select(IngestionEvent).where(
                    IngestionEvent.id == _uuid.UUID(ingestion_event_id)
                )
            ).scalar_one_or_none()

            if ev is None:
                return IngestionResult(
                    success=False,
                    status=IngestionStatus.REJECTED,
                    error_message=f"Ingestion event {ingestion_event_id} not found",
                    error_code="EVENT_NOT_FOUND",
                )

            # Re-read the stored file to get the DataFrame
            file_path = Path(ev.file_path) if ev.file_path else None

            if file_path is None or not file_path.exists():
                # File path not available — try re-reading from stored_filename
                return IngestionResult(
                    success=False,
                    status=IngestionStatus.REJECTED,
                    error_message=f"Stored file not found for event {ingestion_event_id}",
                    error_code="FILE_NOT_FOUND",
                )

            from app.ingestion.readers.reader_factory import ReaderFactory
            reader = ReaderFactory.get_reader(ev.file_extension)
            df, schema = reader.read(file_path)

            meta = FileMetadata(
                original_filename=ev.original_filename,
                stored_filename=ev.stored_filename,
                file_path=file_path,
                file_extension=ev.file_extension,
                file_size_bytes=ev.file_size_bytes,
                dataset_type=dataset_type or ev.dataset_type,
            )
            dataset = Dataset(
                metadata=meta,
                dataframe=df,
                schema=schema,
                ingestion_event_id=ingestion_event_id,
            )
            return IngestionResult(
                success=True,
                status=IngestionStatus.PROCESSED,
                dataset=dataset,
                ingestion_event_id=ingestion_event_id,
                file_metadata=meta,
            )

        except Exception as exc:
            logger.warning(f"Failed to load from ingestion event {ingestion_event_id}: {exc}")
            return IngestionResult(
                success=False,
                status=IngestionStatus.REJECTED,
                error_message=str(exc),
                error_code="EVENT_LOAD_ERROR",
            )

    def _handle_exception(
        self,
        ctx: PipelineContext,
        stage: str,
        result: PipelineStageResult,
        exc: Exception,
        event_emitter: "EventEmitter",
        start: float,
    ) -> PipelineStageResult:
        result.status = "failed"
        result.error_message = str(exc)
        result.duration_ms = (time.perf_counter() - start) * 1000
        result.completed_at = datetime.now(tz=timezone.utc)
        logger.error(
            f"Stage '{stage}' failed unexpectedly",
            stage=stage,
            run_id=ctx.pipeline_run_id,
            error=str(exc),
            exc_info=True,
        )
        event_emitter.emit_stage_failed(ctx, stage, result)
        return result


# ---------------------------------------------------------------------------
# Event emitter (lightweight, inline)
# ---------------------------------------------------------------------------

class EventEmitter:
    """Emits pipeline lifecycle events to the audit log."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _emit(
        self,
        event_type: str,
        run_id: str,
        stage: str | None,
        message: str,
        context_data: dict[str, Any] | None = None,
        severity: str = "INFO",
    ) -> None:
        try:
            import uuid as _uuid
            from app.database.models.audit.audit_log import AuditLog
            log = AuditLog(
                event_type=event_type,
                severity=severity,
                run_id=_uuid.UUID(run_id),
                stage=stage,
                message=message,
                context_data=context_data or {},
            )
            self._session.add(log)
            self._session.flush()
        except Exception as exc:
            logger.error(f"Failed to emit event {event_type}: {exc}")

    def emit_pipeline_started(self, ctx: PipelineContext) -> None:
        self._emit("PIPELINE_STARTED", ctx.pipeline_run_id, None,
                   f"Pipeline '{ctx.pipeline_name}' started for dataset '{ctx.dataset_type}'",
                   {"pipeline_name": ctx.pipeline_name, "dataset_type": ctx.dataset_type,
                    "triggered_by": ctx.triggered_by})

    def emit_pipeline_completed(self, ctx: PipelineContext, metrics: dict) -> None:
        self._emit("PIPELINE_COMPLETED", ctx.pipeline_run_id, None,
                   f"Pipeline '{ctx.pipeline_name}' completed successfully",
                   metrics)

    def emit_pipeline_failed(self, ctx: PipelineContext, error: str, stage: str | None) -> None:
        self._emit("PIPELINE_FAILED", ctx.pipeline_run_id, stage,
                   f"Pipeline '{ctx.pipeline_name}' failed at stage '{stage}': {error}",
                   {"error": error, "failed_stage": stage}, severity="ERROR")

    def emit_pipeline_cancelled(self, ctx: PipelineContext) -> None:
        self._emit("PIPELINE_CANCELLED", ctx.pipeline_run_id, None,
                   f"Pipeline '{ctx.pipeline_name}' was cancelled")

    def emit_stage_started(self, ctx: PipelineContext, stage: str) -> None:
        self._emit("STAGE_STARTED", ctx.pipeline_run_id, stage,
                   f"Stage '{stage}' started")

    def emit_stage_completed(
        self, ctx: PipelineContext, stage: str, result: PipelineStageResult
    ) -> None:
        self._emit("STAGE_COMPLETED", ctx.pipeline_run_id, stage,
                   f"Stage '{stage}' completed: {result.output_records} records",
                   result.to_dict())

    def emit_stage_failed(
        self, ctx: PipelineContext, stage: str, result: PipelineStageResult
    ) -> None:
        self._emit("STAGE_FAILED", ctx.pipeline_run_id, stage,
                   f"Stage '{stage}' failed: {result.error_message}",
                   result.to_dict(), severity="ERROR")

    def emit_retry_started(self, ctx: PipelineContext, attempt: int, stage: str) -> None:
        self._emit("STAGE_STARTED", ctx.pipeline_run_id, stage,
                   f"Retry attempt {attempt} for stage '{stage}'",
                   {"attempt": attempt, "stage": stage})
