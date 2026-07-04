"""
File system utility functions.

Provides reusable helpers for:
- Safe path construction
- Extension validation
- File size formatting
- Directory management
- Versioned file path generation for ingestion storage
"""

import hashlib
import shutil
import uuid
from datetime import date
from pathlib import Path

from app.core.exceptions import (
    FileNotFoundException,
    FileTooLargeException,
    InvalidFileTypeException,
)
from app.logging.logger import get_logger
from app.utils.constants import ALLOWED_FILE_EXTENSIONS

logger = get_logger(__name__)


def get_file_extension(filename: str) -> str:
    """
    Extract the lowercase file extension from a filename.

    Args:
        filename: File name string (e.g., "orders_2025.CSV").

    Returns:
        Lowercase extension without dot (e.g., "csv").
    """
    return Path(filename).suffix.lstrip(".").lower()


def validate_file_extension(filename: str, allowed: set[str] | None = None) -> None:
    """
    Validate that a file's extension is allowed.

    Args:
        filename: File name to validate.
        allowed: Set of allowed extensions. Defaults to ALLOWED_FILE_EXTENSIONS.

    Raises:
        InvalidFileTypeException: If extension is not allowed.
    """
    allowed = allowed or ALLOWED_FILE_EXTENSIONS
    extension = get_file_extension(filename)

    if extension not in allowed:
        raise InvalidFileTypeException(
            message=(
                f"File type '.{extension}' is not supported. "
                f"Allowed types: {sorted(allowed)}"
            ),
            file_extension=extension,
            allowed_types=sorted(allowed),
        )


def validate_file_size(size_bytes: int, max_size_bytes: int) -> None:
    """
    Validate that a file does not exceed the maximum allowed size.

    Args:
        size_bytes: Actual file size in bytes.
        max_size_bytes: Maximum allowed size in bytes.

    Raises:
        FileTooLargeException: If file exceeds maximum size.
    """
    if size_bytes > max_size_bytes:
        raise FileTooLargeException(
            message=(
                f"File size {format_file_size(size_bytes)} exceeds "
                f"maximum allowed size {format_file_size(max_size_bytes)}."
            ),
            file_size_bytes=size_bytes,
            max_size_bytes=max_size_bytes,
        )


def format_file_size(size_bytes: int) -> str:
    """
    Format a byte count into a human-readable string.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted string (e.g., "1.5 MB", "256 KB").
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def build_ingestion_path(
    base_dir: Path,
    dataset_type: str,
    ingestion_id: str,
    filename: str,
    run_date: date | None = None,
) -> Path:
    """
    Build the versioned storage path for a raw ingested file.

    Path format: {base_dir}/{dataset_type}/{YYYY-MM-DD}/{ingestion_id}/{filename}

    This versioning scheme ensures:
    - Files from different dates are separated
    - Each ingestion event has its own subdirectory
    - Original filename is preserved for traceability

    Args:
        base_dir: Root directory for raw files (e.g., data/raw).
        dataset_type: Dataset type string (e.g., "orders").
        ingestion_id: Unique ingestion event ID (UUID).
        filename: Original filename.
        run_date: Date for the path prefix. Defaults to today.

    Returns:
        Absolute Path to the target file location.
    """
    today = run_date or date.today()
    date_str = today.strftime("%Y-%m-%d")

    target_path = base_dir / dataset_type / date_str / ingestion_id / filename
    return target_path


def ensure_directory(path: Path) -> Path:
    """
    Create a directory and all parents if they don't exist.

    Args:
        path: Directory path to create.

    Returns:
        The path (for chaining).
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_copy_file(source: Path, destination: Path) -> Path:
    """
    Copy a file to a destination, creating parent directories as needed.

    Args:
        source: Source file path.
        destination: Destination file path.

    Returns:
        Destination path.

    Raises:
        FileNotFoundException: If source file does not exist.
    """
    if not source.exists():
        raise FileNotFoundException(
            message=f"Source file not found: {source}",
        )

    ensure_directory(destination.parent)
    shutil.copy2(source, destination)
    logger.debug(f"Copied file: {source} → {destination}")
    return destination


def compute_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """
    Compute the hash of a file for integrity verification.

    Args:
        file_path: Path to the file.
        algorithm: Hash algorithm (sha256, md5, etc.).

    Returns:
        Hex-encoded hash string.

    Raises:
        FileNotFoundException: If file does not exist.
    """
    if not file_path.exists():
        raise FileNotFoundException(message=f"File not found: {file_path}")

    h = hashlib.new(algorithm)
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)

    return h.hexdigest()


def count_csv_rows(file_path: Path, encoding: str = "utf-8") -> int:
    """
    Count the number of data rows in a CSV file (excluding header).

    Args:
        file_path: Path to the CSV file.
        encoding: File encoding.

    Returns:
        Number of data rows (header not counted).
    """
    count = 0
    try:
        with file_path.open("r", encoding=encoding, errors="replace") as f:
            next(f)  # Skip header
            for _ in f:
                count += 1
    except Exception as e:
        logger.warning(f"Could not count rows in {file_path}: {e}")

    return count
