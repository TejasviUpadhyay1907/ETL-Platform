"""
BaseReader — abstract interface all file readers must implement.

The Reader Factory returns a BaseReader subclass; the rest of the ingestion
pipeline works against this interface only. Callers never know whether they
are reading a CSV, Excel, or any future format.

Design:
- read() returns a tuple of (DataFrame, DatasetSchema)
- read_chunked() is a generator for large-file streaming
- Each reader is responsible for encoding, delimiter, and sheet selection
- Readers never apply business rules — they just load bytes into DataFrames
"""

from __future__ import annotations

import abc
from pathlib import Path
from typing import Generator

import pandas as pd

from app.ingestion.models import DatasetSchema


class BaseReader(abc.ABC):
    """Abstract base class for all file format readers."""

    @abc.abstractmethod
    def read(
        self,
        file_path: Path,
        **kwargs: object,
    ) -> tuple[pd.DataFrame, DatasetSchema]:
        """
        Read the entire file into a DataFrame in one pass.

        Use for files that fit comfortably in memory.

        Args:
            file_path: Path to the file.
            **kwargs:  Format-specific options (encoding, delimiter, sheet, etc.)

        Returns:
            Tuple of (DataFrame with all rows, DatasetSchema snapshot).
        """

    @abc.abstractmethod
    def read_chunked(
        self,
        file_path: Path,
        chunk_size: int = 10_000,
        **kwargs: object,
    ) -> Generator[pd.DataFrame, None, None]:
        """
        Yield DataFrames of chunk_size rows for large-file processing.

        The first chunk always contains rows 0..chunk_size-1.
        Column names are consistent across all chunks.

        Args:
            file_path:  Path to the file.
            chunk_size: Rows per chunk (default from config).
            **kwargs:   Format-specific options.

        Yields:
            DataFrames, each with up to chunk_size rows.
        """

    @abc.abstractmethod
    def can_read(self, file_extension: str) -> bool:
        """
        Return True if this reader supports the given file extension.

        Used by ReaderFactory to select the correct reader.
        """

    @property
    @abc.abstractmethod
    def reader_name(self) -> str:
        """Human-readable name for logging (e.g. 'CSVReader')."""

    def _build_schema(self, df: pd.DataFrame, has_header: bool = True) -> DatasetSchema:
        """Helper to build a DatasetSchema from a loaded DataFrame."""
        return DatasetSchema(
            column_names=list(df.columns),
            column_dtypes={col: str(df[col].dtype) for col in df.columns},
            row_count=len(df),
            column_count=len(df.columns),
            has_header=has_header,
        )
