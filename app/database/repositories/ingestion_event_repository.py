"""
IngestionEventRepository — database operations for IngestionEvent.
"""

import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database.models.pipeline.ingestion_event import IngestionEvent
from app.database.repositories.base_repository import BaseRepository
from app.logging.logger import get_logger

logger = get_logger(__name__)


class IngestionEventRepository(BaseRepository[IngestionEvent]):
    """Repository for IngestionEvent operations."""

    model_class = IngestionEvent

    def get_by_file_hash(self, file_hash: str) -> IngestionEvent | None:
        """Check if a file with this SHA-256 hash was previously processed."""
        stmt = (
            select(IngestionEvent)
            .where(
                IngestionEvent.file_hash == file_hash,
                IngestionEvent.status.in_(["processed", "processing"]),
            )
            .order_by(desc(IngestionEvent.created_at))
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_recent_by_dataset(
        self, dataset_type: str, limit: int = 20
    ) -> list[IngestionEvent]:
        """Return recent ingestion events for a dataset type."""
        stmt = (
            select(IngestionEvent)
            .where(IngestionEvent.dataset_type == dataset_type)
            .order_by(desc(IngestionEvent.created_at))
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def mark_processed(self, event_id: uuid.UUID, run_id: uuid.UUID) -> None:
        """Mark an ingestion event as processed and link to the pipeline run."""
        event = self.get_by_id(event_id)
        if event:
            event.status = "processed"
            event.pipeline_run_id = run_id
            self.session.flush()

    def mark_rejected(self, event_id: uuid.UUID, reason: str) -> None:
        """Mark an ingestion event as rejected with a reason."""
        event = self.get_by_id(event_id)
        if event:
            event.status = "rejected"
            event.rejection_reason = reason
            self.session.flush()
