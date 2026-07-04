"""
ReaderFactory — selects and returns the correct reader for a file extension.

Factory Pattern: the pipeline engine asks the factory for a reader and
receives a BaseReader subclass. The caller never imports CSVReader or
ExcelReader directly — all format-specific logic is hidden behind the factory.

Extensibility:
  Adding a new format (e.g. Parquet, JSON, XML) requires only:
  1. Implementing a new BaseReader subclass
  2. Registering it with ReaderFactory.register()
  No existing code needs to change.
"""

from __future__ import annotations

from app.core.exceptions import InvalidFileTypeException
from app.ingestion.readers.base_reader import BaseReader
from app.ingestion.readers.csv_reader import CSVReader
from app.ingestion.readers.excel_reader import ExcelReader
from app.logging.logger import get_logger

logger = get_logger(__name__)


class ReaderFactory:
    """
    Returns the correct BaseReader implementation for a given file extension.

    Maintains a registry of readers. Readers are registered at class level
    so the registry is shared across all instances (singleton-like registry).
    """

    # Class-level registry: extension → reader instance
    _registry: dict[str, BaseReader] = {}
    _initialized: bool = False

    @classmethod
    def _ensure_defaults_registered(cls) -> None:
        """Register built-in readers on first use."""
        if not cls._initialized:
            cls.register(CSVReader())
            cls.register(ExcelReader())
            # Register ZIP reader — extracts inner CSV/Excel and delegates
            from app.ingestion.readers.zip_reader import ZipReader
            cls._registry["zip"] = ZipReader()
            cls._initialized = True
            logger.debug(
                "ReaderFactory initialized",
                registered_extensions=list(cls._registry.keys()),
            )

    @classmethod
    def register(cls, reader: BaseReader) -> None:
        """
        Add a reader to the registry.

        The reader declares which extensions it handles via can_read().
        Multiple extensions can map to the same reader instance.

        Args:
            reader: A BaseReader implementation.
        """
        from app.utils.constants import ALLOWED_FILE_EXTENSIONS
        for ext in ALLOWED_FILE_EXTENSIONS:
            if reader.can_read(ext):
                cls._registry[ext.lower()] = reader
                logger.debug(f"Reader registered: .{ext} → {reader.reader_name}")

        # Also try common extensions beyond the allowed set
        for ext in ("csv", "xlsx", "xls"):
            if reader.can_read(ext) and ext not in cls._registry:
                cls._registry[ext] = reader

    @classmethod
    def get_reader(cls, file_extension: str) -> BaseReader:
        """
        Return the reader registered for the given file extension.

        Args:
            file_extension: Extension string without leading dot (e.g. 'csv').

        Returns:
            Appropriate BaseReader implementation.

        Raises:
            InvalidFileTypeException: No reader registered for this extension.
        """
        cls._ensure_defaults_registered()
        ext = file_extension.lower().lstrip(".")

        reader = cls._registry.get(ext)
        if reader is None:
            raise InvalidFileTypeException(
                message=(
                    f"No reader available for file extension '.{ext}'. "
                    f"Supported extensions: {sorted(cls._registry.keys())}"
                ),
                file_extension=ext,
                allowed_types=sorted(cls._registry.keys()),
            )

        logger.debug(f"Reader selected: .{ext} → {reader.reader_name}")
        return reader

    @classmethod
    def supported_extensions(cls) -> list[str]:
        """Return all registered file extensions."""
        cls._ensure_defaults_registered()
        return sorted(cls._registry.keys())

    @classmethod
    def reset(cls) -> None:
        """
        Clear the registry (used in tests to start with a clean state).
        """
        cls._registry = {}
        cls._initialized = False
