"""
FileReceiver — accepts files from multiple sources and routes them to IngestionService.

Supports two ingestion modes:
  1. Upload mode   — file bytes arrive via the REST API (FastAPI UploadFile)
  2. Directory poll — files are discovered on the local file system

The FileReceiver is a thin adapter layer. It handles source-specific concerns
(reading bytes from HTTP, scanning directories) and then delegates all
real work to IngestionService.

Design: keeps the IngestionService free from HTTP or file-system details.
"""

from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_config
from app.ingestion.ingestion_service import IngestionService
from app.ingestion.models import IngestionResult
from app.logging.logger import get_logger
from app.utils.constants import ALLOWED_FILE_EXTENSIONS

logger = get_logger(__name__)


class FileReceiver:
    """
    Accepts files from the API or directory watcher and feeds them to IngestionService.

    One FileReceiver instance handles both upload and directory-poll modes.
    Create a new instance per request/scan cycle (it holds a session reference).
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._service = IngestionService(session)

    # ------------------------------------------------------------------
    # API upload mode
    # ------------------------------------------------------------------

    def receive_upload(
        self,
        file_bytes: bytes,
        original_filename: str,
        explicit_dataset_type: str | None = None,
        uploaded_by: str | None = None,
        source_ip: str | None = None,
    ) -> IngestionResult:
        """
        Accept a file uploaded via the REST API.

        Args:
            file_bytes:            Raw bytes of the uploaded file.
            original_filename:     Filename as provided by the user.
            explicit_dataset_type: Caller-supplied type override.
            uploaded_by:           API key or user identifier.
            source_ip:             Client IP address.

        Returns:
            IngestionResult.
        """
        logger.info(
            "File upload received",
            filename=original_filename,
            size_bytes=len(file_bytes),
            uploaded_by=uploaded_by,
        )

        return self._service.ingest_bytes(
            content=file_bytes,
            original_filename=original_filename,
            explicit_dataset_type=explicit_dataset_type,
            source_type="upload",
            uploaded_by=uploaded_by,
            source_ip=source_ip,
        )

    def receive_file_path(
        self,
        file_path: Path,
        explicit_dataset_type: str | None = None,
        source_type: str = "directory_watch",
    ) -> IngestionResult:
        """
        Accept a file that already exists on the local file system.

        Used by DirectoryWatcher and integration tests.

        Args:
            file_path:             Path to the file.
            explicit_dataset_type: Caller-supplied type override.
            source_type:           'directory_watch' | 'upload' | 'api_push'.

        Returns:
            IngestionResult.
        """
        logger.info(
            "File path received",
            filename=file_path.name,
            source_type=source_type,
        )

        return self._service.ingest(
            source_path=file_path,
            original_filename=file_path.name,
            explicit_dataset_type=explicit_dataset_type,
            source_type=source_type,
        )


class BatchFileReceiver:
    """
    Processes multiple files in sequence, collecting all results.

    Used for bulk uploads (multiple files in one API call) and
    directory poll batches.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._receiver = FileReceiver(session)

    def receive_many_paths(
        self,
        file_paths: list[Path],
        source_type: str = "directory_watch",
    ) -> list[IngestionResult]:
        """
        Ingest a list of file paths, returning one result per file.

        Processing continues even if individual files fail — results include
        both successes and failures.

        Args:
            file_paths:  List of paths to ingest.
            source_type: Source label applied to all files.

        Returns:
            List of IngestionResult, one per input file, in the same order.
        """
        results: list[IngestionResult] = []
        total = len(file_paths)
        logger.info(f"Batch ingestion started: {total} files")

        for i, path in enumerate(file_paths, 1):
            logger.debug(f"Processing file {i}/{total}: {path.name}")
            result = self._receiver.receive_file_path(path, source_type=source_type)
            results.append(result)

        success_count = sum(1 for r in results if r.success)
        logger.info(
            f"Batch ingestion complete: {success_count}/{total} succeeded"
        )
        return results

    def receive_many_uploads(
        self,
        files: list[tuple[bytes, str]],
        uploaded_by: str | None = None,
        source_ip: str | None = None,
    ) -> list[IngestionResult]:
        """
        Ingest multiple uploaded files (bytes, filename) pairs.

        Args:
            files:       List of (file_bytes, original_filename) tuples.
            uploaded_by: API key or user identifier.
            source_ip:   Client IP address.

        Returns:
            List of IngestionResult, one per file.
        """
        results: list[IngestionResult] = []
        logger.info(f"Batch upload received: {len(files)} files")

        for file_bytes, filename in files:
            result = self._receiver.receive_upload(
                file_bytes=file_bytes,
                original_filename=filename,
                uploaded_by=uploaded_by,
                source_ip=source_ip,
            )
            results.append(result)

        return results
