"""
PipelineExecutor — orchestrates the complete ETL pipeline execution.

Coordinates:
  Ingestion → Validation → Cleaning → Transformation → Load(placeholder)

Responsibilities:
  - Create and manage PipelineRun DB records
  - Execute each stage via StageExecutor
  - Save checkpoints after each stage
  - Handle failures with RetryManager
  - Emit events via EventEmitter
  - Return PipelineResult

This engine contains ZERO business logic.
It calls the already-implemented engines and records results.
"""

from __future__ import annotations

import socket
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.logging.logger import get_logger
from app.pipeline.checkpoint_manager import CheckpointManager
from app.pipeline.context import PipelineContext
from app.pipeline.models import (
    PipelineMetrics,
    PipelineResult,
    PipelineState,
    PipelineStageResult,
    RetryPolicy,
    StageName,
)
from app.pipeline.retry_manager import RetryManager
from app.pipeline.stage_executor import EventEmitter, StageExecutor

logger = get_logger(__name__)


class PipelineExecutor:
    """
    Orchestrates the full ETL pipeline lifecycle for one dataset file.

    Stateless between calls — create a fresh instance per execution.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._stage_executor = StageExecutor(session)
        self._checkpoint_mgr = CheckpointManager(session)
        self._event_emitter  = EventEmitter(session)

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------

    def execute(
        self,
        pipeline_name: str,
        dataset_type: str,
        source_file_path: str = "",
        original_filename: str = "",
        ingestion_event_id: str | None = None,
        triggered_by: str = "api",
        trigger_type: str = "manual",
        retry_policy: RetryPolicy | None = None,
        resume_from_checkpoint: str | None = None,
        dry_run: bool = False,
    ) -> PipelineResult:
        """
        Execute the complete pipeline from ingestion through transformation.

        Args:
            pipeline_name:            Name from pipeline definition / YAML.
            dataset_type:             One of the DatasetType values.
            source_file_path:         Absolute path to the source file.
            original_filename:        Original filename for audit trail.
            triggered_by:             API key / user / scheduler identifier.
            trigger_type:             manual | scheduled | api | directory_watch.
            retry_policy:             Override default retry configuration.
            resume_from_checkpoint:   pipeline_run_id to resume from.
            dry_run:                  If True, run without DB writes.

        Returns:
            PipelineResult — always returned, never raises.
        """
        policy = retry_policy or RetryPolicy.default()
        retry_mgr = RetryManager(policy)

        # Build or resume run
        if resume_from_checkpoint:
            return self._resume(
                resume_from_checkpoint, pipeline_name, dataset_type,
                source_file_path, original_filename, policy, retry_mgr
            )

        run_id = str(uuid.uuid4())
        ctx = PipelineContext(
            pipeline_run_id=run_id,
            pipeline_name=pipeline_name,
            dataset_type=dataset_type,
            source_file_path=source_file_path,
            original_filename=original_filename or source_file_path.split("/")[-1],
            ingestion_event_id=ingestion_event_id,
            triggered_by=triggered_by,
            trigger_type=trigger_type,
            retry_policy=policy,
            dry_run=dry_run,
        )

        return self._run_with_retry(ctx, retry_mgr, start_from_stage=None)

    # ------------------------------------------------------------------
    # Resume from checkpoint
    # ------------------------------------------------------------------

    def _resume(
        self,
        original_run_id: str,
        pipeline_name: str,
        dataset_type: str,
        source_file_path: str,
        original_filename: str,
        policy: RetryPolicy,
        retry_mgr: RetryManager,
    ) -> PipelineResult:
        """Resume a pipeline from its last checkpoint."""
        checkpoint = self._checkpoint_mgr.load_latest(original_run_id)
        if checkpoint is None:
            logger.warning(
                f"No checkpoint found for run {original_run_id} — starting fresh"
            )
            ctx = PipelineContext(
                pipeline_run_id=original_run_id,
                pipeline_name=pipeline_name,
                dataset_type=dataset_type,
                source_file_path=source_file_path,
                original_filename=original_filename,
                retry_policy=policy,
            )
            return self._run_with_retry(ctx, retry_mgr, start_from_stage=None)

        logger.info(
            f"Resuming pipeline {original_run_id} from stage "
            f"'{checkpoint.last_completed_stage}'",
            run_id=original_run_id,
        )
        ctx = PipelineContext(
            pipeline_run_id=original_run_id,
            pipeline_name=checkpoint.pipeline_name or pipeline_name,
            dataset_type=checkpoint.dataset_type or dataset_type,
            source_file_path=source_file_path,
            original_filename=original_filename,
            retry_policy=policy,
        )
        next_order = checkpoint.last_completed_stage_order + 1
        next_stage = StageName.ALL[next_order] if next_order < len(StageName.ALL) else None
        return self._run_with_retry(
            ctx, retry_mgr,
            start_from_stage=next_stage,
            prior_checkpoint=checkpoint,
        )

    # ------------------------------------------------------------------
    # Retry wrapper
    # ------------------------------------------------------------------

    def _run_with_retry(
        self,
        ctx: PipelineContext,
        retry_mgr: RetryManager,
        start_from_stage: str | None = None,
        prior_checkpoint=None,
    ) -> PipelineResult:
        attempt = 0
        result = None

        while True:
            if attempt > 0:
                self._event_emitter.emit_retry_started(ctx, attempt, ctx.pipeline_name)
                retry_mgr.wait(attempt - 1)

            result = self._run_pipeline(ctx, start_from_stage, attempt, prior_checkpoint)

            if result.success or not retry_mgr.should_retry(
                attempt, result.failed_stage
            ):
                break

            attempt += 1
            result.retry_count = attempt
            result.status = PipelineState.RETRYING
            logger.info(
                f"Retrying pipeline '{ctx.pipeline_name}' attempt {attempt}",
                run_id=ctx.pipeline_run_id,
                attempt=attempt,
            )

        return result

    # ------------------------------------------------------------------
    # Core execution loop
    # ------------------------------------------------------------------

    def _run_pipeline(
        self,
        ctx: PipelineContext,
        start_from_stage: str | None,
        attempt: int,
        prior_checkpoint: Any,
    ) -> PipelineResult:
        run_id = ctx.pipeline_run_id
        start_time = time.perf_counter()

        # Build PipelineResult container
        result = PipelineResult(
            pipeline_run_id=run_id,
            pipeline_name=ctx.pipeline_name,
            dataset_type=ctx.dataset_type,
            run_number=self._generate_run_number(),
            status=PipelineState.RUNNING,
            original_filename=ctx.original_filename,
            triggered_by=ctx.triggered_by,
            trigger_type=ctx.trigger_type,
            retry_count=attempt,
            started_at=datetime.now(tz=timezone.utc),
        )

        # Create DB record
        db_run = self._create_db_run(ctx, result)

        self._event_emitter.emit_pipeline_started(ctx)
        logger.info(
            "Pipeline execution started",
            run_id=run_id,
            pipeline=ctx.pipeline_name,
            dataset=ctx.dataset_type,
            attempt=attempt,
        )

        try:
            # Determine which stages to execute
            stages_to_run = self._stages_to_execute(start_from_stage)
            stage_outputs: dict[str, Any] = {}

            # Stage execution loop
            for stage_name in stages_to_run:
                result.current_stage = stage_name
                self._update_db_run_stage(db_run, stage_name)

                stage_result = self._execute_stage(ctx, stage_name, stage_outputs)
                result.stage_results.append(stage_result)

                if stage_result.status == "failed":
                    result.failed_stage = stage_name
                    result.status = PipelineState.FAILED
                    result.error_message = stage_result.error_message
                    result.errors.append(
                        f"Stage '{stage_name}' failed: {stage_result.error_message}"
                    )
                    break

                # Store output for next stage
                if stage_result.stage_output is not None:
                    stage_outputs[stage_name] = stage_result.stage_output
                result.completed_stages.append(stage_name)
                result.warnings.extend(self._extract_warnings(stage_result))

                # Save checkpoint
                self._checkpoint_mgr.save(
                    pipeline_run_id=run_id,
                    pipeline_name=ctx.pipeline_name,
                    dataset_type=ctx.dataset_type,
                    completed_stages=result.completed_stages,
                    stage_results=result.stage_results,
                    retry_count=attempt,
                    last_output_summary=self._summarize_output(stage_name, stage_result),
                )

                # Create DB stage result
                self._create_db_stage_result(db_run, stage_result)

            # Finalize result
            duration = time.perf_counter() - start_time
            result.duration_seconds = duration
            result.completed_at = datetime.now(tz=timezone.utc)

            if result.status == PipelineState.RUNNING:
                result.status = PipelineState.SUCCEEDED
                result.success = True

            # Extract final transformed DataFrame
            if StageName.TRANSFORMATION in stage_outputs:
                trans = stage_outputs[StageName.TRANSFORMATION]
                result.transformed_df = trans.transformed_df
            elif StageName.CLEANING in stage_outputs:
                clean = stage_outputs[StageName.CLEANING]
                result.transformed_df = clean.cleaned_df

            # Extract ingestion event ID
            if StageName.INGESTION in stage_outputs:
                ing = stage_outputs[StageName.INGESTION]
                result.ingestion_event_id = ing.ingestion_event_id

            # Build metrics
            result.metrics = self._build_metrics(result, duration)

            # Update DB run record
            self._finalize_db_run(db_run, result)
            try:
                self._session.commit()
            except Exception:
                pass

            if result.success:
                self._event_emitter.emit_pipeline_completed(ctx, result.metrics.to_dict())
            else:
                self._event_emitter.emit_pipeline_failed(
                    ctx, result.error_message or "Unknown error", result.failed_stage
                )

            logger.info(
                "Pipeline execution finished",
                run_id=run_id,
                status=result.status,
                duration_ms=round(duration * 1000, 1),
                records=result.record_count,
            )

        except Exception as exc:
            duration = time.perf_counter() - start_time
            result.duration_seconds = duration
            result.completed_at = datetime.now(tz=timezone.utc)
            result.success = False
            result.status = PipelineState.FAILED
            result.error_message = str(exc)
            result.errors.append(str(exc))
            logger.error(
                "Pipeline execution failed unexpectedly",
                run_id=run_id,
                error=str(exc),
                exc_info=True,
            )
            try:
                self._finalize_db_run(db_run, result)
                self._session.commit()
                self._event_emitter.emit_pipeline_failed(ctx, str(exc), result.current_stage)
            except Exception:
                pass

        return result

    # ------------------------------------------------------------------
    # Stage dispatch
    # ------------------------------------------------------------------

    def _execute_stage(
        self,
        ctx: PipelineContext,
        stage_name: str,
        stage_outputs: dict[str, Any],
    ) -> PipelineStageResult:
        """Dispatch execution to the correct stage method."""
        se = self._stage_executor
        ee = self._event_emitter

        if stage_name == StageName.INGESTION:
            return se.run_ingestion(ctx, ee)

        elif stage_name == StageName.VALIDATION:
            ingestion = stage_outputs.get(StageName.INGESTION)
            if ingestion is None or ingestion.dataset is None:
                r = PipelineStageResult(stage_name=stage_name, stage_order=1, status="skipped")
                r.error_message = "No ingestion output available for validation"
                return r
            return se.run_validation(ctx, ingestion, ee)

        elif stage_name == StageName.CLEANING:
            validation = stage_outputs.get(StageName.VALIDATION)
            if validation is None:
                r = PipelineStageResult(stage_name=stage_name, stage_order=2, status="skipped")
                r.error_message = "No validation output available for cleaning"
                return r
            return se.run_cleaning(ctx, validation, ee)

        elif stage_name == StageName.TRANSFORMATION:
            cleaning = stage_outputs.get(StageName.CLEANING)
            if cleaning is None:
                r = PipelineStageResult(stage_name=stage_name, stage_order=3, status="skipped")
                r.error_message = "No cleaning output available for transformation"
                return r
            return se.run_transformation(ctx, cleaning, ee)

        elif stage_name == StageName.LOAD:
            transformation = stage_outputs.get(StageName.TRANSFORMATION)
            return se.run_load(ctx, transformation, ee)

        else:
            r = PipelineStageResult(stage_name=stage_name, stage_order=99, status="skipped")
            r.error_message = f"Unknown stage: {stage_name}"
            return r

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _create_db_run(self, ctx: PipelineContext, result: PipelineResult):
        """Create the PipelineRun DB record — silently fails if DB unavailable."""
        try:
            import socket as _socket
            from app.database.models.pipeline.pipeline_run import PipelineRun
            run_obj = PipelineRun(
                id=uuid.UUID(ctx.pipeline_run_id),
                run_number=result.run_number,
                pipeline_name=ctx.pipeline_name,
                dataset_type=ctx.dataset_type,
                status="running",
                started_at=result.started_at,
                triggered_by=ctx.triggered_by,
                trigger_type=ctx.trigger_type,
                execution_host=_socket.gethostname(),
            )
            self._session.add(run_obj)
            self._session.flush()
            return run_obj
        except Exception as exc:
            # Non-fatal — pipeline can run without DB tracking
            try:
                self._session.rollback()
            except Exception:
                pass
            logger.warning(f"Could not create DB run record (non-fatal): {exc}")
            return None

    def _update_db_run_stage(self, db_run: Any, stage_name: str) -> None:
        if db_run:
            try:
                db_run.error_stage = stage_name
                self._session.flush()
            except Exception:
                pass

    def _create_db_stage_result(self, db_run: Any, stage_result: PipelineStageResult) -> None:
        if db_run is None:
            return
        try:
            from app.database.models.pipeline.stage_result import StageResult
            sr = StageResult(
                pipeline_run_id=db_run.id,
                stage_name=stage_result.stage_name,
                stage_order=stage_result.stage_order,
                status=stage_result.status,
                started_at=stage_result.started_at,
                completed_at=stage_result.completed_at,
                duration_ms=int(stage_result.duration_ms) if stage_result.duration_ms else None,
                input_records=stage_result.input_records,
                output_records=stage_result.output_records,
                rejected_records=stage_result.rejected_records,
                warning_records=stage_result.warning_count,
                quality_score=Decimal(str(round(stage_result.quality_score, 2)))
                    if stage_result.quality_score else None,
                error_message=stage_result.error_message,
                details=stage_result.details,
            )
            self._session.add(sr)
            self._session.flush()
        except Exception as exc:
            try:
                self._session.rollback()
            except Exception:
                pass
            logger.warning(f"Could not create stage result record (non-fatal): {exc}")

    def _finalize_db_run(self, db_run: Any, result: PipelineResult) -> None:
        if db_run is None:
            return
        try:
            db_run.status = result.status
            db_run.completed_at = result.completed_at
            db_run.duration_seconds = Decimal(str(round(result.duration_seconds, 3)))
            db_run.error_message = result.error_message
            db_run.total_records  = result.metrics.total_records_ingested
            db_run.valid_records  = result.metrics.total_records_valid
            db_run.cleaned_records = result.metrics.total_records_cleaned
            db_run.loaded_records = result.metrics.total_records_loaded
            db_run.failed_records = result.metrics.total_records_rejected
            db_run.warning_count  = result.metrics.warning_count
            db_run.quality_score  = Decimal(str(round(result.metrics.quality_score, 2))) \
                if result.metrics.quality_score else None
            db_run.metrics = result.metrics.to_dict()
            self._session.flush()
        except Exception as exc:
            try:
                self._session.rollback()
            except Exception:
                pass
            logger.warning(f"Could not finalize DB run record (non-fatal): {exc}")

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _stages_to_execute(self, start_from: str | None) -> list[str]:
        if start_from is None:
            return list(StageName.ALL)
        start_order = StageName.ORDER.get(start_from, 0)
        return [s for s in StageName.ALL if StageName.ORDER[s] >= start_order]

    def _build_metrics(self, result: PipelineResult, duration: float) -> PipelineMetrics:
        m = PipelineMetrics(total_duration_seconds=duration)
        for sr in result.stage_results:
            m.stage_durations[sr.stage_name] = round(sr.duration_ms, 2)
            if sr.stage_name == StageName.INGESTION:
                m.total_records_ingested = sr.output_records
            elif sr.stage_name == StageName.VALIDATION:
                m.total_records_valid = sr.output_records
            elif sr.stage_name == StageName.CLEANING:
                m.total_records_cleaned = sr.output_records
                m.total_records_rejected += sr.rejected_records
            elif sr.stage_name == StageName.TRANSFORMATION:
                m.total_records_transformed = sr.output_records
            elif sr.stage_name == StageName.LOAD:
                m.total_records_loaded = sr.output_records
            m.warning_count += sr.warning_count
            if sr.quality_score is not None:
                m.quality_score = sr.quality_score

        m.retry_count = result.retry_count
        m.compute_throughput()
        return m

    def _extract_warnings(self, stage_result: PipelineStageResult) -> list[str]:
        warnings = []
        if stage_result.warning_count > 0:
            warnings.append(
                f"Stage '{stage_result.stage_name}' had {stage_result.warning_count} warnings"
            )
        return warnings

    def _summarize_output(
        self, stage_name: str, stage_result: PipelineStageResult
    ) -> dict[str, Any]:
        return {
            "stage": stage_name,
            "status": stage_result.status,
            "output_records": stage_result.output_records,
            "quality_score": stage_result.quality_score,
        }

    @staticmethod
    def _generate_run_number() -> str:
        from datetime import date
        import random
        return f"{date.today().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
