"""
MetadataExtractor — builds a complete FileMetadata object from all available sources.

After a file has been:
1. Validated by FileTypeDetector (encoding, delimiter, sheet names)
2. Hashed by HashGenerator
3. Read by the appropriate Reader (column names, row count)

…the MetadataExtractor assembles these pieces into a single FileMetadata
that is ready to be stored in the ingestion_events table.

Design: pure data assembly — no I/O, no database access.
"""

from __future__ import annotations

from pathlib import Path

from app.ingestion.models import DatasetSchema, FileMetadata
from app.ingestion.file_type_detector import FileValidationResult
from app.logging.logger import get_logger

logger = get_logger(__name__)


class MetadataExtractor:
    """Assembles FileMetadata from the outputs of prior ingestion steps."""

    def extract(
        self,
        file_path: Path,
        original_filename: str,
        stored_filename: str,
        ingestion_id: str,
        validation_result: FileValidationResult,
        file_hash: str,
        dataset_type: str | None,
        schema: DatasetSchema | None = None,
        source_type: str = "upload",
        uploaded_by: str | None = None,
        source_ip: str | None = None,
    ) -> FileMetadata:
        """
        Build a complete FileMetadata from all available ingestion inputs.

        Args:
            file_path:          Stored file path.
            original_filename:  Original name the user provided.
            stored_filename:    Name on the file system after storage.
            ingestion_id:       UUID assigned to this ingestion event.
            validation_result:  Output from FileTypeDetector.validate().
            file_hash:          SHA-256 hex digest from HashGenerator.
            dataset_type:       Resolved dataset type string (may be None).
            schema:             DatasetSchema from the reader (may be None if
                                the file was rejected before reading).
            source_type:        'upload' | 'directory_watch' | 'api_push'.
            uploaded_by:        User or API key identifier.
            source_ip:          Client IP address.

        Returns:
            Fully populated FileMetadata.
        """
        # File size from the stored file
        try:
            file_size = file_path.stat().st_size
        except OSError:
            file_size = 0

        metadata = FileMetadata(
            ingestion_id=ingestion_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=file_path,
            file_extension=validation_result.extension,
            file_size_bytes=file_size,
            file_hash=file_hash,
            source_type=source_type,
            uploaded_by=uploaded_by,
            source_ip=source_ip,
            dataset_type=dataset_type,
            encoding=validation_result.encoding,
            delimiter=validation_result.delimiter,
            excel_sheet_names=validation_result.excel_sheet_names,
            excel_active_sheet=validation_result.excel_active_sheet,
        )

        # Enrich with schema information if available
        if schema is not None:
            metadata.row_count_raw = schema.row_count + 1   # +1 for header
            metadata.row_count_data = schema.row_count
            metadata.column_count = schema.column_count

        logger.debug(
            "Metadata extracted",
            ingestion_id=ingestion_id,
            filename=original_filename,
            dataset_type=dataset_type,
            rows=metadata.row_count_data,
            cols=metadata.column_count,
        )

        return metadata
