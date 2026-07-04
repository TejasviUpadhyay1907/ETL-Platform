"""
CheckpointManager — persists and restores pipeline run state.

After each stage completes, a checkpoint is written to the audit_log table
as a JSON blob tagged with is_checkpoint=True in context_data.
If a pipeline is resumed or retried, the checkpoint is loaded and execution
resumes from the last completed stage.

Design:
- Checkpoints are stored as STAGE_COMPLETED events with context_data["is_checkpoint"]=True
- DataFrames are NOT checkpointed (too large) — only metadata
- On resume, stages before last_completed_stage are skipped
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging.logger import get_logger
from app.pipeline.models import CheckpointData, PipelineStageResult

logger = get_logger(__name__)


class CheckpointManager:
    """Creates, retrieves, and cleans up pipeline checkpoints."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(
        self,
        pipeline_run_id: str,
        pipeline_name: str,
        dataset_type: str,
        completed_stages: list[str],
        stage_results: list[PipelineStageResult],
        retry_count: int = 0,
        last_output_summary: dict[str, Any] | None = None,
    ) -> CheckpointData:
        """Persist a checkpoint after a stage completes."""
        last_stage = completed_stages[-1] if completed_stages else None
        from app.pipeline.models import StageName
        last_order = StageName.ORDER.get(last_stage, -1) if last_stage else -1

        checkpoint = CheckpointData(
            pipeline_run_id=pipeline_run_id,
            pipeline_name=pipeline_name,
            dataset_type=dataset_type,
            last_completed_stage=last_stage,
            last_completed_stage_order=last_order,
            completed_stages=list(completed_stages),
            stage_results=[sr.to_dict() for sr in stage_results],
            last_output_summary=last_output_summary or {},
            retry_count=retry_count,
        )

        try:
            from app.database.models.audit.audit_log import AuditLog
            run_uuid = uuid.UUID(pipeline_run_id)
            # Tag context_data with is_checkpoint=True so load_latest can find it
            payload = checkpoint.to_dict()
            payload["is_checkpoint"] = True

            log_entry = AuditLog(
                event_type="STAGE_COMPLETED",
                severity="INFO",
                run_id=run_uuid,
                stage=last_stage,
                message=f"[CHECKPOINT] After stage '{last_stage}'",
                context_data=payload,
            )
            self._session.add(log_entry)
            self._session.flush()
            logger.debug(
                "Checkpoint saved",
                run_id=pipeline_run_id,
                stage=last_stage,
                checkpoint_id=checkpoint.checkpoint_id,
            )
        except Exception as exc:
            logger.error(f"Failed to save checkpoint: {exc}", exc_info=True)

        return checkpoint

    def load_latest(self, pipeline_run_id: str) -> CheckpointData | None:
        """Load the most recent checkpoint for a pipeline run."""
        try:
            from app.database.models.audit.audit_log import AuditLog
            run_uuid = uuid.UUID(pipeline_run_id)

            # Fetch all STAGE_COMPLETED events for this run and filter by is_checkpoint flag
            stmt = (
                select(AuditLog)
                .where(
                    AuditLog.run_id == run_uuid,
                    AuditLog.event_type == "STAGE_COMPLETED",
                )
                .order_by(AuditLog.created_at.desc())
            )
            entries = list(self._session.execute(stmt).scalars().all())

            # Find the latest checkpoint entry
            log_entry = None
            for e in entries:
                if (e.context_data or {}).get("is_checkpoint"):
                    log_entry = e
                    break

            if log_entry is None:
                return None

            data = log_entry.context_data or {}
            checkpoint = CheckpointData(
                checkpoint_id=data.get("checkpoint_id", str(uuid.uuid4())),
                pipeline_run_id=data.get("pipeline_run_id", pipeline_run_id),
                pipeline_name=data.get("pipeline_name", ""),
                dataset_type=data.get("dataset_type", ""),
                last_completed_stage=data.get("last_completed_stage"),
                last_completed_stage_order=data.get("last_completed_stage_order", -1),
                completed_stages=data.get("completed_stages", []),
                stage_results=data.get("stage_results", []),
                last_output_summary=data.get("last_output_summary", {}),
                retry_count=data.get("retry_count", 0),
            )
            logger.debug(
                "Checkpoint loaded",
                run_id=pipeline_run_id,
                last_stage=checkpoint.last_completed_stage,
            )
            return checkpoint
        except Exception as exc:
            logger.error(f"Failed to load checkpoint: {exc}", exc_info=True)
            return None

    def list_checkpoints(self, pipeline_run_id: str) -> list[dict[str, Any]]:
        """Return all checkpoints for a run (for the /checkpoints API)."""
        try:
            from app.database.models.audit.audit_log import AuditLog
            run_uuid = uuid.UUID(pipeline_run_id)
            stmt = (
                select(AuditLog)
                .where(
                    AuditLog.run_id == run_uuid,
                    AuditLog.event_type == "STAGE_COMPLETED",
                )
                .order_by(AuditLog.created_at)
            )
            entries = list(self._session.execute(stmt).scalars().all())
            return [
                {
                    "checkpoint_id": (e.context_data or {}).get("checkpoint_id"),
                    "stage": e.stage,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                    "completed_stages": (e.context_data or {}).get("completed_stages", []),
                    "is_checkpoint": (e.context_data or {}).get("is_checkpoint", False),
                }
                for e in entries
                if (e.context_data or {}).get("is_checkpoint")
            ]
        except Exception as exc:
            logger.error(f"Failed to list checkpoints: {exc}", exc_info=True)
            return []
