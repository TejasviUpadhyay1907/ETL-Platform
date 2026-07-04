"""
CSVReader — reads CSV files into pandas DataFrames.

Features:
- Auto-detects encoding and delimiter (passed in from FileTypeDetector)
- Supports chunked reading for large files
- Preserves all values as strings on initial read (dtype=str) —
  type coercion is the job of the Cleaning/Transformation stages
- Handles BOM markers, quoted fields, and irregular whitespace headers
- Configurable null representations

Why dtype=str on all columns?
  The ingestion stage is a faithful transcription of the source file.
  We never want pandas to silently convert '00123' to 123 or '2025-01-15'
  to a Timestamp. Downstream stages own type conversion.
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import pandas as pd

from app.core.exceptions import FileReadException
from app.ingestion.models import DatasetSchema
from app.ingestion.readers.base_reader import BaseReader
from app.logging.logger import get_logger

logger = get_logger(__name__)

# Values that pandas should treat as NaN during initial read.
# Keeping this minimal: we preserve the source values and let Cleaning decide.
NA_VALUES: list[str] = ["", "NULL", "null", "None", "none", "N/A", "n/a", "NA", "na"]


class CSVReader(BaseReader):
    """
    Reads CSV files. Handles encoding, BOM, delimiter, and quoted fields.
    """

    @property
    def reader_name(self) -> str:
        return "CSVReader"

    def can_read(self, file_extension: str) -> bool:
        return file_extension.lower() == "csv"

    def read(
        self,
        file_path: Path,
        encoding: str = "utf-8",
        delimiter: str = ",",
        **kwargs: object,
    ) -> tuple[pd.DataFrame, DatasetSchema]:
        """
        Read the entire CSV file into a DataFrame.

        Args:
            file_path: Path to the CSV file.
            encoding:  Character encoding (detected by FileTypeDetector).
            delimiter: Field delimiter (detected by FileTypeDetector).
            **kwargs:  Additional pandas read_csv kwargs.

        Returns:
            (DataFrame, DatasetSchema)

        Raises:
            FileReadException: If the file cannot be parsed.
        """
        logger.debug(
            "Reading CSV file",
            filename=file_path.name,
            encoding=encoding,
            delimiter=repr(delimiter),
        )

        try:
            df = pd.read_csv(
                file_path,
                encoding=encoding,
                sep=delimiter,
                dtype=str,                    # preserve all values as strings
                keep_default_na=False,        # use our own NA list
                na_values=NA_VALUES,
                skipinitialspace=True,        # strip spaces after delimiter
                low_memory=False,             # consistent dtype inference per column
            )
        except UnicodeDecodeError as exc:
            raise FileReadException(
                message=(
                    f"Cannot decode '{file_path.name}' with encoding '{encoding}'. "
                    f"Try re-saving the file as UTF-8."
                )
            ) from exc
        except pd.errors.EmptyDataError as exc:
            raise FileReadException(
                message=f"CSV file '{file_path.name}' contains no data."
            ) from exc
        except pd.errors.ParserError as exc:
            raise FileReadException(
                message=f"CSV file '{file_path.name}' could not be parsed: {exc}"
            ) from exc
        except OSError as exc:
            raise FileReadException(
                message=f"Cannot read '{file_path.name}': {exc}"
            ) from exc

        # Strip whitespace from column names (common in manually edited CSVs)
        df.columns = [str(c).strip() for c in df.columns]

        schema = self._build_schema(df)
        logger.info(
            "CSV file read",
            filename=file_path.name,
            rows=len(df),
            columns=len(df.columns),
            encoding=encoding,
        )
        return df, schema

    def read_chunked(
        self,
        file_path: Path,
        chunk_size: int = 10_000,
        encoding: str = "utf-8",
        delimiter: str = ",",
        **kwargs: object,
    ) -> Generator[pd.DataFrame, None, None]:
        """
        Yield DataFrames in chunks for large-file processing.

        Column names are stripped of whitespace on the first chunk and
        consistently applied to all subsequent chunks.

        Args:
            file_path:  Path to the CSV file.
            chunk_size: Rows per yielded chunk.
            encoding:   Character encoding.
            delimiter:  Field delimiter.

        Yields:
            DataFrames of up to chunk_size rows.

        Raises:
            FileReadException: On read or parse error.
        """
        logger.debug(
            "Starting chunked CSV read",
            filename=file_path.name,
            chunk_size=chunk_size,
        )

        try:
            reader = pd.read_csv(
                file_path,
                encoding=encoding,
                sep=delimiter,
                dtype=str,
                keep_default_na=False,
                na_values=NA_VALUES,
                skipinitialspace=True,
                low_memory=False,
                chunksize=chunk_size,
            )

            for chunk_num, chunk in enumerate(reader):
                chunk.columns = [str(c).strip() for c in chunk.columns]
                logger.debug(
                    f"CSV chunk {chunk_num + 1} read",
                    rows=len(chunk),
                    filename=file_path.name,
                )
                yield chunk

        except UnicodeDecodeError as exc:
            raise FileReadException(
                message=f"Encoding error in '{file_path.name}': {exc}"
            ) from exc
        except pd.errors.ParserError as exc:
            raise FileReadException(
                message=f"Parse error in '{file_path.name}': {exc}"
            ) from exc
        except OSError as exc:
            raise FileReadException(
                message=f"Cannot read '{file_path.name}': {exc}"
            ) from exc
