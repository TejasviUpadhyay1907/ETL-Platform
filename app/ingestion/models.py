"""
Ingestion domain models.

These are pure Python dataclasses — NOT ORM models.
They carry data between ingestion subsystem components in-memory
without touching the database.

Design:
- FileMetadata  — everything known about the file on disk
- DatasetSchema — column names, types, shape discovered during reading
- Dataset       — the unified output of the ingestion stage, handed to validation
- IngestionResult — final status object returned to the pipeline engine

The Dataset object is the contract between ingestion and every downstream stage.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Ingestion status values (mirrors IngestionEvent.status in the DB)
# ---------------------------------------------------------------------------

class IngestionStatus:
    RECEIVED   = "received"
    PROCESSING = "processing"
    PROCESSED  = "processed"
    REJECTED   = "rejected"
    DUPLICATE  = "duplicate"


# ---------------------------------------------------------------------------
# FileMetadata
# ---------------------------------------------------------------------------

@dataclass
class FileMetadata:
    """
    Everything known about a raw file before reading its content.

    Populated by FileTypeDetector and HashGenerator.
    Stored in the ingestion_events table.
    """

    # Identity
    ingestion_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    original_filename: str = ""
    stored_filename: str = ""
    file_path: Path = field(default_factory=Path)
    file_extension: str = ""

    # Size & integrity
    file_size_bytes: int = 0
    file_hash: str | None = None       # SHA-256 hex digest

    # Source tracking
    source_type: str = "upload"        # upload | directory_watch | api_push
    uploaded_by: str | None = None
    source_ip: str | None = None

    # Dataset classification
    dataset_type: str | None = None    # orders | customers | products | …

    # File-level properties (detected, not content-level)
    encoding: str | None = None        # utf-8 | latin-1 | utf-8-sig | …
    delimiter: str | None = None       # CSV delimiter character
    excel_sheet_names: list[str] = field(default_factory=list)
    excel_active_sheet: str | None = None

    # Raw row counts (set after reading)
    row_count_raw: int | None = None   # total lines including header
    row_count_data: int | None = None  # data rows (header excluded)
    column_count: int | None = None

    # Timestamps
    received_at: datetime = field(default_factory=datetime.utcnow)

    def to_event_kwargs(self) -> dict[str, Any]:
        """Serialize to kwargs suitable for IngestionEventRepository.create()."""
        return {
            "original_filename": self.original_filename,
            "stored_filename":   self.stored_filename,
            "file_path":         str(self.file_path),
            "file_extension":    self.file_extension,
            "file_size_bytes":   self.file_size_bytes,
            "file_hash":         self.file_hash,
            "dataset_type":      self.dataset_type or "unknown",
            "source_type":       self.source_type,
            "uploaded_by":       self.uploaded_by,
            "source_ip":         self.source_ip,
            "row_count_raw":     self.row_count_raw,
            "row_count_data":    self.row_count_data,
            "status":            IngestionStatus.RECEIVED,
        }


# ---------------------------------------------------------------------------
# DatasetSchema
# ---------------------------------------------------------------------------

@dataclass
class DatasetSchema:
    """
    Structural snapshot of a dataset as read from the file.

    Captured by the reader immediately after loading — this is what the file
    actually contains, not what it *should* contain (that is validation's job).
    """

    column_names: list[str] = field(default_factory=list)
    column_dtypes: dict[str, str] = field(default_factory=dict)
    row_count: int = 0
    column_count: int = 0
    has_header: bool = True
    sample_rows: int = 5           # number of rows captured in sample


# ---------------------------------------------------------------------------
# Dataset  (the output of the ingestion stage)
# ---------------------------------------------------------------------------

@dataclass
class Dataset:
    """
    The unified output of the ingestion stage.

    This object is the contract between ingestion and every downstream stage
    (validation, cleaning, transformation, loading).

    A Dataset is created once per ingestion event and passed through the
    entire pipeline unchanged in structure — each stage reads from it and
    potentially replaces the DataFrame inside it.

    Design:
    - metadata carries file-level facts (path, hash, dataset_type)
    - dataframe holds the raw pandas DataFrame (all values as-read, no cleaning)
    - schema is the structural snapshot at read time
    - processing_id is the unique identifier for this pipeline pass
    """

    # Core payload
    metadata: FileMetadata
    dataframe: pd.DataFrame
    schema: DatasetSchema

    # Pipeline correlation
    processing_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ingestion_event_id: str | None = None   # set after DB record created
    pipeline_run_id: str | None = None      # set after pipeline run created

    # Ingestion provenance
    reader_used: str = ""   # "CSVReader" | "ExcelReader"
    read_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def dataset_type(self) -> str | None:
        return self.metadata.dataset_type

    @property
    def row_count(self) -> int:
        return len(self.dataframe)

    @property
    def column_count(self) -> int:
        return len(self.dataframe.columns)

    @property
    def columns(self) -> list[str]:
        return list(self.dataframe.columns)

    @property
    def is_empty(self) -> bool:
        return len(self.dataframe) == 0

    def head(self, n: int = 5) -> pd.DataFrame:
        """Return first n rows for logging/preview."""
        return self.dataframe.head(n)

    def __repr__(self) -> str:
        return (
            f"Dataset(id={self.processing_id[:8]}, "
            f"type={self.dataset_type!r}, "
            f"rows={self.row_count}, cols={self.column_count}, "
            f"reader={self.reader_used!r})"
        )


# ---------------------------------------------------------------------------
# IngestionResult  (returned to the pipeline engine)
# ---------------------------------------------------------------------------

@dataclass
class IngestionResult:
    """
    The final outcome of one ingestion operation.

    Returned by IngestionService.ingest() to the pipeline engine so it can:
    - create the StageResult record
    - decide whether to proceed to validation
    - handle duplicates according to policy
    """

    success: bool
    status: str                        # IngestionStatus constant
    dataset: Dataset | None = None     # None on failure/duplicate
    ingestion_event_id: str | None = None
    file_metadata: FileMetadata | None = None
    error_message: str | None = None
    error_code: str | None = None
    is_duplicate: bool = False
    duplicate_of_event_id: str | None = None  # ID of the original ingestion event
    duration_seconds: float = 0.0

    def __repr__(self) -> str:
        return (
            f"IngestionResult(success={self.success}, "
            f"status={self.status!r}, "
            f"duplicate={self.is_duplicate}, "
            f"error={self.error_code!r})"
        )
