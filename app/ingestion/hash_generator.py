"""
HashGenerator — produces a SHA-256 fingerprint for every ingested file.

The hash is the primary idempotency key: if the same file bytes are uploaded
twice, the hashes match and the system can detect the duplicate without reading
the file's content.

Design:
- Reads the file in streaming 8 KB chunks — constant memory regardless of size
- Returns a 64-character hex string (lowercase)
- Stateless and reusable
"""

import hashlib
from pathlib import Path

from app.core.exceptions import FileReadException
from app.logging.logger import get_logger

logger = get_logger(__name__)

CHUNK_SIZE = 8192  # 8 KB — optimal for most file systems


def compute_sha256(file_path: Path) -> str:
    """
    Compute the SHA-256 hash of a file using streaming reads.

    Args:
        file_path: Path to the file to hash.

    Returns:
        64-character lowercase hex digest string.

    Raises:
        FileReadException: If the file cannot be opened or read.
    """
    hasher = hashlib.sha256()
    try:
        with file_path.open("rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                hasher.update(chunk)
    except OSError as exc:
        raise FileReadException(
            message=f"Cannot hash file '{file_path.name}': {exc}"
        ) from exc

    digest = hasher.hexdigest()
    logger.debug("File hashed", filename=file_path.name, sha256=digest[:16] + "…")
    return digest


class HashGenerator:
    """
    Generates SHA-256 hashes for file deduplication.

    Thin wrapper around compute_sha256 that provides a consistent
    object-oriented interface matching the rest of the ingestion pipeline.
    """

    def generate(self, file_path: Path) -> str:
        """
        Generate the SHA-256 hash of a file.

        Args:
            file_path: Path to the file.

        Returns:
            64-character hex digest.
        """
        return compute_sha256(file_path)

    def files_are_identical(self, path_a: Path, path_b: Path) -> bool:
        """
        Compare two files by hash without loading either into memory.

        Returns True if both files have the same content.
        """
        return compute_sha256(path_a) == compute_sha256(path_b)
