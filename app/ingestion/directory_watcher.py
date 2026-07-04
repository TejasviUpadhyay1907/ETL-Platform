"""
DirectoryWatcher — polls a local directory for new files and ingests them.

Runs on a configurable interval. For each new file found:
  1. Checks the file extension against the allowed list
  2. Delegates to FileReceiver for full ingestion
  3. Moves processed files to a 'done' subdirectory
  4. Moves failed files to a 'failed' subdirectory

Design:
- Uses a simple polling model (APScheduler calls scan() on interval)
- Stateless between scans — no in-memory tracking of seen files
  (the database's file_hash deduplication is the authoritative check)
- Safe for concurrent use — each scan opens its own DB session
"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.core.config import get_config
from app.logging.logger import get_logger
from app.utils.constants import ALLOWED_FILE_EXTENSIONS

logger = get_logger(__name__)


class DirectoryWatcher:
    """
    Polls a directory for new files and feeds them to the ingestion pipeline.

    Instantiated once at startup. The scheduler calls scan() periodically.
    """

    def __init__(self, watch_directory: Path | None = None) -> None:
        """
        Args:
            watch_directory: Directory to monitor. Defaults to config.upload_directory.
                             In production, this would typically be a separate
                             'incoming' directory distinct from 'data/raw'.
        """
        config = get_config()
        self._watch_dir: Path = watch_directory or config.upload_directory
        self._done_dir: Path = self._watch_dir / "_done"
        self._failed_dir: Path = self._watch_dir / "_failed"
        self._allowed_extensions: frozenset[str] = ALLOWED_FILE_EXTENSIONS

        # Ensure subdirectories exist
        self._done_dir.mkdir(parents=True, exist_ok=True)
        self._failed_dir.mkdir(parents=True, exist_ok=True)

    def scan(self) -> dict[str, int]:
        """
        Scan the watch directory for new files and ingest each one.

        Skips the _done/ and _failed/ subdirectories.
        Returns a summary dict with processed/failed/skipped counts.

        Returns:
            {"processed": N, "failed": M, "skipped": K}
        """
        counts: dict[str, int] = {"processed": 0, "failed": 0, "skipped": 0}

        try:
            candidates = self._find_candidates()
        except OSError as exc:
            logger.error(f"Cannot scan watch directory: {exc}")
            return counts

        if not candidates:
            logger.debug("No new files found in watch directory")
            return counts

        logger.info(f"Directory scan found {len(candidates)} candidate file(s)")

        from app.database.engine import get_session
        from app.ingestion.file_receiver import FileReceiver

        for file_path in candidates:
            with get_session() as session:
                receiver = FileReceiver(session)
                result = receiver.receive_file_path(
                    file_path,
                    source_type="directory_watch",
                )

            if result.success or result.is_duplicate:
                self._move_to_done(file_path)
                counts["processed"] += 1
            else:
                self._move_to_failed(file_path, reason=result.error_code or "unknown")
                counts["failed"] += 1

        logger.info(
            "Directory scan complete",
            processed=counts["processed"],
            failed=counts["failed"],
            skipped=counts["skipped"],
        )
        return counts

    def _find_candidates(self) -> list[Path]:
        """
        Find files in the watch directory with allowed extensions.

        Skips _done/, _failed/, and hidden files.
        """
        candidates: list[Path] = []
        for path in self._watch_dir.iterdir():
            if path.is_dir():
                continue  # Skip subdirectories including _done and _failed
            if path.name.startswith("."):
                continue  # Skip hidden files
            ext = path.suffix.lstrip(".").lower()
            if ext in self._allowed_extensions:
                candidates.append(path)
            else:
                logger.debug(f"Skipping unsupported file: {path.name}")
        return candidates

    def _move_to_done(self, file_path: Path) -> None:
        """Move a successfully processed file to the _done/ subdirectory."""
        try:
            dest = self._done_dir / file_path.name
            # If same filename already exists in _done, append a counter
            if dest.exists():
                stem = file_path.stem
                suffix = file_path.suffix
                counter = 1
                while dest.exists():
                    dest = self._done_dir / f"{stem}_{counter}{suffix}"
                    counter += 1
            shutil.move(str(file_path), str(dest))
            logger.debug(f"Moved to done: {file_path.name}")
        except OSError as exc:
            logger.warning(f"Cannot move '{file_path.name}' to _done: {exc}")

    def _move_to_failed(self, file_path: Path, reason: str) -> None:
        """Move a failed file to the _failed/ subdirectory."""
        try:
            dest = self._failed_dir / file_path.name
            if dest.exists():
                stem = file_path.stem
                suffix = file_path.suffix
                import time as _time
                dest = self._failed_dir / f"{stem}_{int(_time.time())}{suffix}"
            shutil.move(str(file_path), str(dest))
            logger.debug(f"Moved to failed: {file_path.name} (reason: {reason})")
        except OSError as exc:
            logger.warning(f"Cannot move '{file_path.name}' to _failed: {exc}")
