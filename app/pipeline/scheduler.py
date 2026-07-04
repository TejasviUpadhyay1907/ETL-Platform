"""
PipelineScheduler — cron-based pipeline trigger using APScheduler.

Polls configured directories and triggers pipelines on a schedule.
Designed as an optional component — if disabled, pipelines run on-demand only.
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_config
from app.logging.logger import get_logger

logger = get_logger(__name__)


class PipelineScheduler:
    """
    Lightweight scheduler wrapping APScheduler for periodic pipeline triggers.

    Disabled by default — set PIPELINE_ENABLE_SCHEDULER=True to activate.
    """

    def __init__(self) -> None:
        self._scheduler = None
        self._jobs: dict[str, Any] = {}

    def start(self) -> None:
        config = get_config()
        if not config.pipeline_enable_scheduler:
            logger.info("Pipeline scheduler disabled (PIPELINE_ENABLE_SCHEDULER=False)")
            return
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            self._scheduler = BackgroundScheduler()
            self._scheduler.start()
            logger.info("Pipeline scheduler started")
        except Exception as exc:
            logger.error(f"Failed to start scheduler: {exc}")

    def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Pipeline scheduler stopped")

    def add_directory_watch_job(
        self,
        dataset_type: str,
        watch_directory: str,
        interval_seconds: int = 60,
    ) -> str | None:
        """Register a periodic directory scan job for a dataset type."""
        if self._scheduler is None:
            return None
        try:
            job_id = f"watch_{dataset_type}"
            self._scheduler.add_job(
                func=self._scan_directory,
                trigger="interval",
                seconds=interval_seconds,
                id=job_id,
                kwargs={"dataset_type": dataset_type, "directory": watch_directory},
                replace_existing=True,
            )
            self._jobs[job_id] = {
                "dataset_type": dataset_type,
                "directory": watch_directory,
                "interval_seconds": interval_seconds,
            }
            logger.info(f"Scheduled directory watch job: {job_id}")
            return job_id
        except Exception as exc:
            logger.error(f"Failed to add watch job: {exc}")
            return None

    def _scan_directory(self, dataset_type: str, directory: str) -> None:
        """Internal: scan directory and trigger pipeline for new files."""
        try:
            from pathlib import Path
            from app.database.engine import get_session
            from app.pipeline.trigger_service import PipelineTriggerService

            watch_path = Path(directory)
            if not watch_path.exists():
                return

            from app.utils.constants import ALLOWED_FILE_EXTENSIONS
            for file_path in watch_path.iterdir():
                if file_path.suffix.lstrip(".").lower() in ALLOWED_FILE_EXTENSIONS:
                    with get_session() as session:
                        svc = PipelineTriggerService(session)
                        svc.trigger(
                            dataset_type=dataset_type,
                            source_file_path=str(file_path),
                            original_filename=file_path.name,
                            triggered_by="scheduler",
                            trigger_type="scheduled",
                        )
        except Exception as exc:
            logger.error(f"Scheduler scan failed: {exc}")
