"""
PipelineTriggerService — API-facing entry point for pipeline execution.

Bridges the REST API layer and PipelineExecutor.
Validates inputs, resolves pipeline definitions, and delegates to the executor.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.logging.logger import get_logger
from app.pipeline.engine import PipelineExecutor
from app.pipeline.models import PipelineResult, RetryPolicy, PipelineState

logger = get_logger(__name__)


class PipelineTriggerService:
    """Validates and dispatches pipeline execution requests."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._executor = PipelineExecutor(session)

    def trigger(
        self,
        dataset_type: str,
        source_file_path: str = "",
        original_filename: str = "",
        ingestion_event_id: str | None = None,
        pipeline_name: str | None = None,
        triggered_by: str = "api",
        trigger_type: str = "manual",
        retry_policy: dict[str, Any] | None = None,
    ) -> PipelineResult:
        """
        Trigger a new pipeline run.

        Args:
            dataset_type:      One of the supported DatasetType values.
            source_file_path:  Absolute path to the file to process.
            original_filename: Original filename for audit.
            pipeline_name:     Override pipeline name (defaults to dataset_type).
            triggered_by:      User / API key / scheduler identifier.
            trigger_type:      manual | scheduled | api | directory_watch.
            retry_policy:      Override default retry config as a dict.

        Returns:
            PipelineResult.
        """
        from app.utils.constants import DatasetType
        try:
            DatasetType(dataset_type)
        except ValueError:
            valid = [t.value for t in DatasetType]
            return self._error_result(
                dataset_type,
                f"Invalid dataset_type '{dataset_type}'. Valid: {valid}",
                "INVALID_DATASET_TYPE",
            )

        policy = RetryPolicy.from_dict(retry_policy) if retry_policy else RetryPolicy.default()
        name = pipeline_name or f"{dataset_type}_pipeline"

        logger.info(
            "Pipeline trigger received",
            pipeline=name,
            dataset_type=dataset_type,
            triggered_by=triggered_by,
        )

        return self._executor.execute(
            pipeline_name=name,
            dataset_type=dataset_type,
            source_file_path=source_file_path,
            original_filename=original_filename,
            ingestion_event_id=ingestion_event_id,
            triggered_by=triggered_by,
            trigger_type=trigger_type,
            retry_policy=policy,
        )

    def resume(self, pipeline_run_id: str, source_file_path: str = "") -> PipelineResult:
        """Resume a pipeline from its last checkpoint."""
        run = self._get_run(pipeline_run_id)
        if run is None:
            return self._error_result(
                "unknown", f"Pipeline run {pipeline_run_id} not found", "RUN_NOT_FOUND"
            )

        logger.info(f"Resuming pipeline run {pipeline_run_id}")
        return self._executor.execute(
            pipeline_name=run.pipeline_name,
            dataset_type=run.dataset_type,
            source_file_path=source_file_path,
            original_filename="",
            triggered_by="resume",
            trigger_type="manual",
            resume_from_checkpoint=pipeline_run_id,
        )

    def retry(self, pipeline_run_id: str, source_file_path: str = "") -> PipelineResult:
        """Retry a failed pipeline run from scratch."""
        run = self._get_run(pipeline_run_id)
        if run is None:
            return self._error_result(
                "unknown", f"Pipeline run {pipeline_run_id} not found", "RUN_NOT_FOUND"
            )

        logger.info(f"Retrying pipeline run {pipeline_run_id}")
        return self._executor.execute(
            pipeline_name=run.pipeline_name,
            dataset_type=run.dataset_type,
            source_file_path=source_file_path,
            triggered_by="retry",
            trigger_type="manual",
        )

    def cancel(self, pipeline_run_id: str) -> bool:
        """Mark a running pipeline as cancelled."""
        run = self._get_run(pipeline_run_id)
        if run is None:
            return False
        if not PipelineState.is_valid_transition(run.status, PipelineState.CANCELLED):
            logger.warning(f"Cannot cancel run in status '{run.status}'")
            return False
        run.status = PipelineState.CANCELLED
        self._session.flush()
        self._session.commit()
        logger.info(f"Pipeline run {pipeline_run_id} cancelled")
        return True

    def _get_run(self, pipeline_run_id: str):
        try:
            import uuid
            from app.database.models.pipeline.pipeline_run import PipelineRun
            from sqlalchemy import select
            stmt = select(PipelineRun).where(PipelineRun.id == uuid.UUID(pipeline_run_id))
            return self._session.execute(stmt).scalar_one_or_none()
        except Exception:
            return None

    @staticmethod
    def _error_result(dataset_type: str, message: str, code: str) -> PipelineResult:
        import uuid
        return PipelineResult(
            pipeline_run_id=str(uuid.uuid4()),
            pipeline_name="unknown",
            dataset_type=dataset_type,
            status=PipelineState.FAILED,
            success=False,
            error_message=message,
            error_code=code,
            errors=[message],
        )
