"""
IngestionService — top-level orchestrator for the ingestion stage.

This is the single entry point for all ingestion operations. It coordinates:
  1. FileTypeDetector   — validate extension, MIME, size, encoding
  2. RawFileStore       — persist the file to versioned storage
  3. HashGenerator      — compute SHA-256 fingerprint
  4. DatasetTypeResolver — classify the dataset type
  5. ReaderFactory      — select the correct reader
  6. Reader.read()      — load the file into a DataFrame
  7. MetadataExtractor  — assemble complete FileMetadata
  8. IngestionTracker   — write to database, detect duplicates

Returns a Dataset object ready for the downstream validation stage,
or an IngestionResult with failure details if any step fails.

Design:
- Stateless between calls — each ingest() call is independent
- All external dependencies injected via constructor
- Never raises exceptions to the caller — always returns IngestionResult
- Every error path is logged with full context
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_config
from app.core.exceptions import ETLPlatformException, FileReadException
from app.ingestion.dataset_type_resolver import DatasetTypeResolver
from app.ingestion.file_type_detector import FileTypeDetector
from app.ingestion.hash_generator import HashGenerator
from app.ingestion.ingestion_tracker import DuplicatePolicy, IngestionTracker
from app.ingestion.metadata_extractor import MetadataExtractor
from app.ingestion.models import Dataset, DatasetSchema, FileMetadata, IngestionResult, IngestionStatus
from app.ingestion.raw_file_store import RawFileStore
from app.ingestion.readers.reader_factory import ReaderFactory
from app.logging.logger import get_logger

logger = get_logger(__name__)


class IngestionService:
    """
    Orchestrates the complete ingestion pipeline for a single file.

    All dependencies are injected, making the service fully testable
    without touching the file system or database.
    """

    def __init__(
        self,
        session: Session,
        file_store: RawFileStore | None = None,
        detector: FileTypeDetector | None = None,
        resolver: DatasetTypeResolver | None = None,
        hash_gen: HashGenerator | None = None,
        extractor: MetadataExtractor | None = None,
        duplicate_policy: str = DuplicatePolicy.REJECT,
    ) -> None:
        """
        Args:
            session:           SQLAlchemy session for database writes.
            file_store:        RawFileStore instance. Built from config if None.
            detector:          FileTypeDetector. Built from config if None.
            resolver:          DatasetTypeResolver. Built lazily if None.
            hash_gen:          HashGenerator. Created fresh if None.
            extractor:         MetadataExtractor. Created fresh if None.
            duplicate_policy:  'reject' | 'reprocess'.
        """
        config = get_config()

        self._session = session
        self._store = file_store or RawFileStore(config.upload_directory)
        self._detector = detector or FileTypeDetector()
        self._resolver = resolver or DatasetTypeResolver()
        self._hash_gen = hash_gen or HashGenerator()
        self._extractor = extractor or MetadataExtractor()
        self._tracker = IngestionTracker(session, duplicate_policy)

    # ------------------------------------------------------------------
    # Primary ingestion entry point
    # ------------------------------------------------------------------

    def ingest(
        self,
        source_path: Path,
        original_filename: str | None = None,
        explicit_dataset_type: str | None = None,
        source_type: str = "upload",
        uploaded_by: str | None = None,
        source_ip: str | None = None,
    ) -> IngestionResult:
        """
        Ingest a single file through the complete ingestion pipeline.

        Args:
            source_path:           Path to the file to ingest (temp upload or disk path).
            original_filename:     Original filename from the upload. Defaults to source_path.name.
            explicit_dataset_type: Override auto-detection (optional).
            source_type:           'upload' | 'directory_watch' | 'api_push'.
            uploaded_by:           User or API key identifier.
            source_ip:             Client IP address.

        Returns:
            IngestionResult — always returned, never raises.
        """
        start_time = time.perf_counter()
        ingestion_id = str(uuid.uuid4())
        fname = original_filename or source_path.name

        logger.info(
            "Ingestion started",
            ingestion_id=ingestion_id,
            filename=fname,
            source_type=source_type,
        )

        try:
            result = self._run_ingestion_pipeline(
                source_path=source_path,
                original_filename=fname,
                ingestion_id=ingestion_id,
                explicit_dataset_type=explicit_dataset_type,
                source_type=source_type,
                uploaded_by=uploaded_by,
                source_ip=source_ip,
            )
        except Exception as exc:
            duration = time.perf_counter() - start_time
            logger.error(
                "Ingestion failed with unhandled exception",
                ingestion_id=ingestion_id,
                filename=fname,
                error=str(exc),
                exc_info=True,
            )
            return IngestionResult(
                success=False,
                status=IngestionStatus.REJECTED,
                error_message=str(exc),
                error_code="INGESTION_UNEXPECTED_ERROR",
                duration_seconds=duration,
            )

        result.duration_seconds = time.perf_counter() - start_time
        logger.info(
            "Ingestion complete",
            ingestion_id=ingestion_id,
            status=result.status,
            success=result.success,
            duration_ms=round(result.duration_seconds * 1000, 1),
        )
        return result

    def ingest_bytes(
        self,
        content: bytes,
        original_filename: str,
        explicit_dataset_type: str | None = None,
        source_type: str = "upload",
        uploaded_by: str | None = None,
        source_ip: str | None = None,
    ) -> IngestionResult:
        """
        Ingest a file supplied as raw bytes (e.g., from FastAPI UploadFile).

        Writes bytes to a temporary path and delegates to ingest().
        The temporary file is cleaned up after ingestion completes.

        Args:
            content:               Raw file bytes.
            original_filename:     Original filename (used for extension detection).
            explicit_dataset_type: Override auto-detection (optional).
            source_type:           'upload' | 'directory_watch' | 'api_push'.
            uploaded_by:           User or API key identifier.
            source_ip:             Client IP address.

        Returns:
            IngestionResult.
        """
        import tempfile

        # Write bytes to a secure temp file with the correct extension preserved
        suffix = Path(original_filename).suffix
        with tempfile.NamedTemporaryFile(
            suffix=suffix, delete=False
        ) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            return self.ingest(
                source_path=tmp_path,
                original_filename=original_filename,
                explicit_dataset_type=explicit_dataset_type,
                source_type=source_type,
                uploaded_by=uploaded_by,
                source_ip=source_ip,
            )
        finally:
            # Always clean up the temp file
            tmp_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _run_ingestion_pipeline(
        self,
        source_path: Path,
        original_filename: str,
        ingestion_id: str,
        explicit_dataset_type: str | None,
        source_type: str,
        uploaded_by: str | None,
        source_ip: str | None,
    ) -> IngestionResult:
        """Execute all ingestion steps in order. Returns IngestionResult."""

        # ── Step 1: File-level validation ──────────────────────────────
        logger.debug("Step 1: File validation", filename=original_filename)
        try:
            validation = self._detector.validate(source_path)
        except ETLPlatformException as exc:
            return IngestionResult(
                success=False,
                status=IngestionStatus.REJECTED,
                error_message=exc.message,
                error_code=exc.error_code,
            )

        # ── Step 2: Hash generation ─────────────────────────────────────
        logger.debug("Step 2: Hash generation", filename=original_filename)
        file_hash = self._hash_gen.generate(source_path)

        # ── Step 3: Duplicate check ─────────────────────────────────────
        logger.debug("Step 3: Duplicate check", filename=original_filename)
        is_dup, existing_id = self._tracker.check_duplicate(file_hash)

        if is_dup and self._tracker.should_reject_duplicate():
            return IngestionResult(
                success=False,
                status=IngestionStatus.DUPLICATE,
                error_message=(
                    f"File '{original_filename}' is a duplicate of a previously "
                    f"ingested file (event {existing_id})."
                ),
                error_code="DUPLICATE_FILE",
                is_duplicate=True,
                duplicate_of_event_id=existing_id,
            )

        # ── Step 4: Dataset type resolution ────────────────────────────
        logger.debug("Step 4: Dataset type resolution", filename=original_filename)
        dataset_type_str: str | None = None
        try:
            dt = self._resolver.resolve(
                filename=original_filename,
                explicit_type=explicit_dataset_type,
            )
            dataset_type_str = dt.value if dt else None
        except ValueError as exc:
            return IngestionResult(
                success=False,
                status=IngestionStatus.REJECTED,
                error_message=str(exc),
                error_code="UNKNOWN_DATASET_TYPE",
            )

        if dataset_type_str is None:
            return IngestionResult(
                success=False,
                status=IngestionStatus.REJECTED,
                error_message=(
                    f"Cannot determine dataset type for '{original_filename}'. "
                    "Rename the file to include a recognised keyword or pass "
                    "dataset_type explicitly."
                ),
                error_code="UNKNOWN_DATASET_TYPE",
            )

        # ── Step 5: Store the file ──────────────────────────────────────
        logger.debug("Step 5: Store file", filename=original_filename)
        stored_path = self._store.store(
            source_path=source_path,
            dataset_type=dataset_type_str,
            original_filename=original_filename,
            ingestion_id=ingestion_id,
        )

        # ── Step 6: Read file into DataFrame ───────────────────────────
        logger.debug("Step 6: Read file", filename=original_filename)
        reader = ReaderFactory.get_reader(validation.extension)

        read_kwargs: dict[str, Any] = {}
        if validation.extension == "csv":
            read_kwargs["encoding"] = validation.encoding or "utf-8"
            read_kwargs["delimiter"] = validation.delimiter or ","
        elif validation.extension in ("xlsx", "xls"):
            if validation.excel_active_sheet is not None:
                read_kwargs["sheet_name"] = validation.excel_active_sheet

        try:
            dataframe, schema = reader.read(stored_path, **read_kwargs)
        except ETLPlatformException as exc:
            self._store.delete(stored_path)
            return IngestionResult(
                success=False,
                status=IngestionStatus.REJECTED,
                error_message=exc.message,
                error_code=exc.error_code,
            )

        # ── Step 7: Schema-based type refinement ───────────────────────
        if dataset_type_str is None:
            dt = self._resolver.resolve(
                filename=original_filename,
                column_names=schema.column_names,
                explicit_type=explicit_dataset_type,
            )
            dataset_type_str = dt.value if dt else "unknown"

        # ── Step 8: Metadata assembly ───────────────────────────────────
        logger.debug("Step 8: Metadata assembly", filename=original_filename)
        file_metadata = self._extractor.extract(
            file_path=stored_path,
            original_filename=original_filename,
            stored_filename=stored_path.name,
            ingestion_id=ingestion_id,
            validation_result=validation,
            file_hash=file_hash,
            dataset_type=dataset_type_str,
            schema=schema,
            source_type=source_type,
            uploaded_by=uploaded_by,
            source_ip=source_ip,
        )

        # ── Step 9: Persist ingestion event to database ─────────────────
        logger.debug("Step 9: Persist metadata", filename=original_filename)
        event_id = self._tracker.create_event(file_metadata)
        self._tracker.mark_processed(
            event_id,
            row_count_raw=file_metadata.row_count_raw,
            row_count_data=file_metadata.row_count_data,
        )
        self._session.commit()

        # ── Step 10: Build Dataset object ───────────────────────────────
        dataset = Dataset(
            metadata=file_metadata,
            dataframe=dataframe,
            schema=schema,
            processing_id=ingestion_id,
            ingestion_event_id=event_id,
            reader_used=reader.reader_name,
        )

        logger.info(
            "Dataset ingested successfully",
            ingestion_id=ingestion_id,
            dataset_type=dataset_type_str,
            rows=dataset.row_count,
            columns=dataset.column_count,
            reader=reader.reader_name,
        )

        return IngestionResult(
            success=True,
            status=IngestionStatus.PROCESSED,
            dataset=dataset,
            ingestion_event_id=event_id,
            file_metadata=file_metadata,
            is_duplicate=is_dup,  # True when reprocess policy is active
            duplicate_of_event_id=existing_id,
        )
