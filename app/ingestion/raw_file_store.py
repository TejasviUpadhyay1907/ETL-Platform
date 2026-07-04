"""
RawFileStore — persists uploaded files to a versioned directory structure.

Responsibility: accept a file stream or source path, write it to the correct
location under the upload directory, and return the stored path.

Directory structure:
    data/raw/{dataset_type}/{YYYY-MM-DD}/{ingestion_id}/{original_filename}

Design rationale:
- Date partitioning makes archival and retention policies easy to apply
- Ingestion ID subdirectory ensures no filename collisions across concurrent uploads
- Original filename is preserved for traceability
"""

import shutil
import uuid
from datetime import date
from pathlib import Path
from typing import BinaryIO

from app.core.exceptions import FileReadException
from app.logging.logger import get_logger

logger = get_logger(__name__)


class RawFileStore:
    """
    Writes raw uploaded files to a versioned directory under the upload root.

    Instantiate with the upload root directory (from AppConfig.upload_directory).
    """

    def __init__(self, upload_directory: Path) -> None:
        self._root = upload_directory
        self._root.mkdir(parents=True, exist_ok=True)

    def store(
        self,
        source_path: Path,
        dataset_type: str,
        original_filename: str,
        ingestion_id: str | None = None,
        run_date: date | None = None,
    ) -> Path:
        """
        Copy a file from source_path to the versioned storage location.

        Args:
            source_path:      Path to the uploaded/temporary file.
            dataset_type:     Dataset type string (e.g. 'orders').
            original_filename: Original filename to preserve.
            ingestion_id:     UUID for this ingestion event. Generated if not supplied.
            run_date:         Date prefix for the directory. Defaults to today.

        Returns:
            Absolute path where the file was stored.

        Raises:
            FileReadException: If the copy operation fails.
        """
        iid = ingestion_id or str(uuid.uuid4())
        today = run_date or date.today()
        date_str = today.strftime("%Y-%m-%d")

        target_dir = self._root / dataset_type / date_str / iid
        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / original_filename

        try:
            shutil.copy2(source_path, target_path)
        except OSError as exc:
            raise FileReadException(
                message=f"Failed to store file '{original_filename}': {exc}"
            ) from exc

        logger.debug(
            "File stored",
            original=original_filename,
            stored_path=str(target_path),
            size_bytes=target_path.stat().st_size,
        )
        return target_path

    def store_bytes(
        self,
        content: bytes,
        dataset_type: str,
        original_filename: str,
        ingestion_id: str | None = None,
        run_date: date | None = None,
    ) -> Path:
        """
        Write raw bytes directly to the versioned storage location.

        Used when the upload arrives as an in-memory bytes object
        (e.g., from FastAPI's UploadFile).

        Args:
            content:          Raw file bytes.
            dataset_type:     Dataset type string.
            original_filename: Filename to use on disk.
            ingestion_id:     UUID for this ingestion event.
            run_date:         Date prefix. Defaults to today.

        Returns:
            Absolute path where the file was written.
        """
        iid = ingestion_id or str(uuid.uuid4())
        today = run_date or date.today()
        date_str = today.strftime("%Y-%m-%d")

        target_dir = self._root / dataset_type / date_str / iid
        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / original_filename

        try:
            target_path.write_bytes(content)
        except OSError as exc:
            raise FileReadException(
                message=f"Failed to write file '{original_filename}': {exc}"
            ) from exc

        logger.debug(
            "File written from bytes",
            filename=original_filename,
            stored_path=str(target_path),
            size_bytes=len(content),
        )
        return target_path

    def get_path(
        self,
        dataset_type: str,
        ingestion_id: str,
        filename: str,
        run_date: date | None = None,
    ) -> Path:
        """
        Reconstruct the expected storage path without checking if it exists.

        Args:
            dataset_type: Dataset type string.
            ingestion_id: UUID of the ingestion event.
            filename:     Original filename.
            run_date:     Date used during storage (default: today).

        Returns:
            Expected Path object.
        """
        today = run_date or date.today()
        date_str = today.strftime("%Y-%m-%d")
        return self._root / dataset_type / date_str / ingestion_id / filename

    def delete(self, stored_path: Path) -> None:
        """
        Delete a stored file (used for cleanup after a rejected ingestion).

        Silently ignores missing files — idempotent by design.
        """
        try:
            stored_path.unlink(missing_ok=True)
            logger.debug(f"Deleted stored file: {stored_path}")
        except OSError as exc:
            logger.warning(f"Could not delete stored file '{stored_path}': {exc}")
