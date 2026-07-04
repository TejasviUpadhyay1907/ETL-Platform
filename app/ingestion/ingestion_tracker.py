"""
IngestionTracker — integrates with the database to record ingestion events.

Responsibilities:
- Create IngestionEvent records before and after reading
- Check for duplicate file hashes
- Update event status as the pipeline progresses
- Apply the configured duplicate handling policy

This module is the only ingestion component that touches the database.
All other ingestion components operate on files and in-memory objects only.

Duplicate policy (from config/app.yaml):
  "reject"     — duplicate files are rejected with status='duplicate'
  "reprocess"  — duplicate files are accepted and processed again
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_config
from app.ingestion.models import FileMetadata, IngestionStatus
from app.logging.logger import get_logger

logger = get_logger(__name__)


class DuplicatePolicy:
    REJECT = "reject"
    REPROCESS = "reprocess"


class IngestionTracker:
    """
    Writes ingestion metadata to the database and detects duplicate uploads.

    Injected with a SQLAlchemy session by the IngestionService.
    """

    def __init__(
        self,
        session: Session,
        duplicate_policy: str = DuplicatePolicy.REJECT,
    ) -> None:
        """
        Args:
            session:           Open SQLAlchemy session (managed by caller).
            duplicate_policy:  'reject' | 'reprocess'. Loaded from config by default.
        """
        self._session = session
        self._duplicate_policy = duplicate_policy

        from app.database.repositories.ingestion_event_repository import (
            IngestionEventRepository,
        )
        self._repo = IngestionEventRepository(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_duplicate(self, file_hash: str) -> tuple[bool, str | None]:
        """
        Check if a file with this SHA-256 hash was already processed.

        Args:
            file_hash: SHA-256 hex digest.

        Returns:
            (is_duplicate, existing_event_id)
            existing_event_id is None if not a duplicate.
        """
        existing = self._repo.get_by_file_hash(file_hash)
        if existing is None:
            return False, None

        logger.info(
            "Duplicate file detected",
            file_hash=file_hash[:16] + "…",
            existing_event_id=str(existing.id),
            policy=self._duplicate_policy,
        )
        return True, str(existing.id)

    def create_event(self, metadata: FileMetadata) -> str:
        """
        Create an IngestionEvent record in the database.

        Called immediately after the file is stored — before reading begins.

        Args:
            metadata: Populated FileMetadata from MetadataExtractor.

        Returns:
            String UUID of the created IngestionEvent record.
        """
        kwargs = metadata.to_event_kwargs()
        event = self._repo.create(**kwargs)
        logger.info(
            "Ingestion event created",
            event_id=str(event.id),
            filename=metadata.original_filename,
            dataset_type=metadata.dataset_type,
        )
        return str(event.id)

    def mark_processing(self, event_id: str) -> None:
        """Update the event status to 'processing'."""
        self._update_status(event_id, IngestionStatus.PROCESSING)

    def mark_processed(
        self,
        event_id: str,
        pipeline_run_id: str | None = None,
        row_count_raw: int | None = None,
        row_count_data: int | None = None,
    ) -> None:
        """
        Mark the event as successfully processed.

        Optionally updates row counts and links to the pipeline run.
        """
        import uuid as _uuid
        from app.database.models.pipeline.ingestion_event import IngestionEvent

        event = self._repo.get_by_id(_uuid.UUID(event_id))
        if event is None:
            logger.warning(f"IngestionEvent {event_id} not found during mark_processed")
            return

        event.status = IngestionStatus.PROCESSED
        if pipeline_run_id:
            event.pipeline_run_id = _uuid.UUID(pipeline_run_id)
        if row_count_raw is not None:
            event.row_count_raw = row_count_raw
        if row_count_data is not None:
            event.row_count_data = row_count_data

        self._session.flush()
        logger.debug(f"IngestionEvent {event_id} marked as processed")

    def mark_rejected(self, event_id: str, reason: str) -> None:
        """Mark the event as rejected with a human-readable reason."""
        import uuid as _uuid
        self._repo.mark_rejected(_uuid.UUID(event_id), reason)
        logger.info(f"IngestionEvent {event_id} rejected: {reason}")

    def mark_duplicate(self, event_id: str, original_event_id: str) -> None:
        """Mark the event as a duplicate, referencing the original event."""
        import uuid as _uuid
        event = self._repo.get_by_id(_uuid.UUID(event_id))
        if event:
            event.status = IngestionStatus.DUPLICATE
            event.rejection_reason = f"Duplicate of event {original_event_id}"
            self._session.flush()
        logger.info(
            f"IngestionEvent {event_id} marked as duplicate of {original_event_id}"
        )

    def should_reject_duplicate(self) -> bool:
        """Return True if the policy is to reject duplicate files."""
        return self._duplicate_policy == DuplicatePolicy.REJECT

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _update_status(self, event_id: str, status: str) -> None:
        import uuid as _uuid
        event = self._repo.get_by_id(_uuid.UUID(event_id))
        if event:
            event.status = status
            self._session.flush()
