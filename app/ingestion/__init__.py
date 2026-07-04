"""
Ingestion package — Stage 1 of the ETL pipeline.

Public interface:

    from app.ingestion import IngestionService, FileReceiver, BatchFileReceiver
    from app.ingestion import Dataset, IngestionResult, FileMetadata
    from app.ingestion import ReaderFactory, DatasetTypeResolver
"""

from app.ingestion.models import (
    Dataset,
    DatasetSchema,
    FileMetadata,
    IngestionResult,
    IngestionStatus,
)
from app.ingestion.ingestion_service import IngestionService
from app.ingestion.file_receiver import BatchFileReceiver, FileReceiver
from app.ingestion.readers.reader_factory import ReaderFactory
from app.ingestion.readers.zip_reader import ZipReader
from app.ingestion.dataset_type_resolver import DatasetTypeResolver

__all__ = [
    # Core service
    "IngestionService",
    "FileReceiver",
    "BatchFileReceiver",
    # Domain models
    "Dataset",
    "DatasetSchema",
    "FileMetadata",
    "IngestionResult",
    "IngestionStatus",
    # Utilities
    "ReaderFactory",
    "ZipReader",
    "DatasetTypeResolver",
]
