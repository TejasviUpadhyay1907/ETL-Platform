"""
PipelineRunRepository — database operations for PipelineRun and StageResult.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, joinedload

from app.database.models.pipeline.pipeline_run import PipelineRun
from app.database.models.pipeline.stage_result import StageResult
from app.database.repositories.base_repository import BaseRepository
from app.logging.logger import get_logger

logger = get_logger(__name__)


class PipelineRunRepository(BaseRepository[PipelineRun]):
    """Repository for PipelineRun lifecycle management."""

    model_class = PipelineRun

    def get_by_run_number(self, run_number: str) -> PipelineRun | None:
        """Find a pipeline run by its human-readable run number."""
        stmt = select(PipelineRun).where(PipelineRun.run_number == run_number)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_recent(
        self,
        dataset_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PipelineRun]:
        """Return recent pipeline runs, most recent first."""
        stmt = (
            select(PipelineRun)
            .order_by(desc(PipelineRun.created_at))
            .limit(limit)
            .offset(offset)
        )
        if dataset_type:
            stmt = stmt.where(PipelineRun.dataset_type == dataset_type)
        if status:
            stmt = stmt.where(PipelineRun.status == status)
        return list(self.session.execute(stmt).scalars().all())

    def get_with_stages(self, run_id: uuid.UUID) -> PipelineRun | None:
        """Load a pipeline run with all its stage results pre-loaded."""
        stmt = (
            select(PipelineRun)
            .options(joinedload(PipelineRun.stage_results))
            .where(PipelineRun.id == run_id)
        )
        return self.session.execute(stmt).unique().scalar_one_or_none()

    def get_running(self) -> list[PipelineRun]:
        """Return all currently running pipeline runs."""
        stmt = select(PipelineRun).where(PipelineRun.status == "running")
        return list(self.session.execute(stmt).scalars().all())

    def update_status(
        self,
        run_id: uuid.UUID,
        status: str,
        error_message: str | None = None,
        error_stage: str | None = None,
        completed_at: datetime | None = None,
        duration_seconds: Decimal | None = None,
    ) -> PipelineRun | None:
        """Update the status and completion details of a pipeline run."""
        run = self.get_by_id(run_id)
        if not run:
            return None

        run.status = status
        if error_message:
            run.error_message = error_message
        if error_stage:
            run.error_stage = error_stage
        if completed_at:
            run.completed_at = completed_at
        if duration_seconds is not None:
            run.duration_seconds = duration_seconds

        self.session.flush()
        return run

    def update_counts(self, run_id: uuid.UUID, **counts: int) -> None:
        """Update record count fields on a pipeline run."""
        run = self.get_by_id(run_id)
        if not run:
            return
        for field, value in counts.items():
            if hasattr(run, field):
                setattr(run, field, value)
        self.session.flush()

    def count_by_status(
        self, dataset_type: str | None = None
    ) -> dict[str, int]:
        """Count pipeline runs grouped by status."""
        stmt = (
            select(PipelineRun.status, func.count().label("count"))
            .group_by(PipelineRun.status)
        )
        if dataset_type:
            stmt = stmt.where(PipelineRun.dataset_type == dataset_type)
        return {row.status: row.count for row in self.session.execute(stmt).all()}

    def get_average_duration(self, dataset_type: str | None = None) -> float:
        """Return the average run duration in seconds for completed runs."""
        stmt = select(func.avg(PipelineRun.duration_seconds)).where(
            PipelineRun.status == "completed"
        )
        if dataset_type:
            stmt = stmt.where(PipelineRun.dataset_type == dataset_type)
        result = self.session.execute(stmt).scalar_one_or_none()
        return float(result or 0)

    # ------------------------------------------------------------------
    # Stage result operations
    # ------------------------------------------------------------------

    def create_stage_result(self, **kwargs: Any) -> StageResult:
        """Create and persist a stage result record."""
        stage_result = StageResult(**kwargs)
        self.session.add(stage_result)
        self.session.flush()
        return stage_result

    def get_stage_results(self, run_id: uuid.UUID) -> list[StageResult]:
        """Return all stage results for a run, ordered by execution."""
        stmt = (
            select(StageResult)
            .where(StageResult.pipeline_run_id == run_id)
            .order_by(StageResult.stage_order)
        )
        return list(self.session.execute(stmt).scalars().all())

    def update_stage_result(
        self, stage_result_id: uuid.UUID, **kwargs: Any
    ) -> StageResult | None:
        """Update fields on a stage result."""
        stage = self.session.get(StageResult, stage_result_id)
        if not stage:
            return None
        for key, val in kwargs.items():
            if hasattr(stage, key):
                setattr(stage, key, val)
        self.session.flush()
        return stage
