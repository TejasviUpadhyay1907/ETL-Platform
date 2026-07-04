"""
ExcelReader — reads .xlsx and .xls files into pandas DataFrames.

Features:
- Supports both .xlsx (openpyxl engine) and .xls (xlrd engine)
- Sheet selection: active sheet, sheet by name, or sheet by index
- Preserves values as strings (same philosophy as CSVReader)
- Chunked reading via iterrows (Excel does not support native streaming)
- Skips empty leading rows and columns when configured

Why no native chunked Excel reading?
  pandas does not support chunked reading for Excel files at the engine level.
  The entire workbook must be loaded into memory first. For Excel files up to
  the configured 500 MB limit, this is acceptable. Files larger than available
  memory should be converted to CSV before ingestion.
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

NA_VALUES: list[str] = ["", "NULL", "null", "None", "none", "N/A", "n/a", "NA", "na"]


class ExcelReader(BaseReader):
    """
    Reads .xlsx and .xls files using the appropriate pandas engine.
    """

    @property
    def reader_name(self) -> str:
        return "ExcelReader"

    def can_read(self, file_extension: str) -> bool:
        return file_extension.lower() in ("xlsx", "xls")

    def read(
        self,
        file_path: Path,
        sheet_name: str | int | None = 0,
        **kwargs: object,
    ) -> tuple[pd.DataFrame, DatasetSchema]:
        """
        Read the first (or specified) sheet from an Excel workbook.

        Args:
            file_path:   Path to the .xlsx or .xls file.
            sheet_name:  Sheet name or 0-based index. Defaults to first sheet.
            **kwargs:    Additional pandas read_excel kwargs.

        Returns:
            (DataFrame, DatasetSchema)

        Raises:
            FileReadException: If the file cannot be opened or parsed.
        """
        extension = file_path.suffix.lstrip(".").lower()
        engine = self._pick_engine(extension)

        logger.debug(
            "Reading Excel file",
            filename=file_path.name,
            engine=engine,
            sheet=sheet_name,
        )

        try:
            df = pd.read_excel(
                file_path,
                sheet_name=sheet_name,
                engine=engine,
                dtype=str,              # preserve all values as strings
                keep_default_na=False,
                na_values=NA_VALUES,
            )
        except ValueError as exc:
            msg = str(exc)
            if "sheet" in msg.lower():
                raise FileReadException(
                    message=(
                        f"Sheet '{sheet_name}' not found in '{file_path.name}'. "
                        f"Original error: {exc}"
                    )
                ) from exc
            raise FileReadException(
                message=f"Cannot parse Excel file '{file_path.name}': {exc}"
            ) from exc
        except Exception as exc:
            msg = str(exc).lower()
            if "encrypted" in msg or "password" in msg:
                raise FileReadException(
                    message=f"Excel file '{file_path.name}' is password-protected."
                ) from exc
            raise FileReadException(
                message=f"Cannot open Excel file '{file_path.name}': {exc}"
            ) from exc

        # Normalise column names
        df.columns = [str(c).strip() for c in df.columns]

        # Drop fully-empty rows and columns (common in Excel exports)
        df = df.dropna(how="all").dropna(axis=1, how="all")

        schema = self._build_schema(df)
        logger.info(
            "Excel file read",
            filename=file_path.name,
            sheet=sheet_name,
            rows=len(df),
            columns=len(df.columns),
        )
        return df, schema

    def read_chunked(
        self,
        file_path: Path,
        chunk_size: int = 10_000,
        sheet_name: str | int | None = 0,
        **kwargs: object,
    ) -> Generator[pd.DataFrame, None, None]:
        """
        Yield chunks by slicing the fully-loaded DataFrame.

        Excel does not support streaming reads, so this loads the file once
        and slices the resulting DataFrame into chunk_size pieces.

        Args:
            file_path:  Path to the Excel file.
            chunk_size: Rows per chunk.
            sheet_name: Sheet to read.

        Yields:
            DataFrames of up to chunk_size rows.
        """
        df, _ = self.read(file_path, sheet_name=sheet_name)
        total_rows = len(df)
        logger.debug(
            "Chunking Excel file",
            filename=file_path.name,
            total_rows=total_rows,
            chunk_size=chunk_size,
        )

        for start in range(0, total_rows, chunk_size):
            chunk = df.iloc[start : start + chunk_size].copy()
            logger.debug(
                f"Excel chunk rows {start}–{start + len(chunk) - 1}",
                filename=file_path.name,
            )
            yield chunk

    def get_sheet_names(self, file_path: Path) -> list[str]:
        """
        Return all sheet names without loading any data.

        Useful for previewing workbook structure before committing to a read.
        """
        extension = file_path.suffix.lstrip(".").lower()
        try:
            if extension == "xlsx":
                import openpyxl
                wb = openpyxl.load_workbook(str(file_path), read_only=True)
                names = wb.sheetnames
                wb.close()
                return names
            elif extension == "xls":
                import xlrd
                wb = xlrd.open_workbook(str(file_path), on_demand=True)
                names = wb.sheet_names()
                wb.release_resources()
                return names
        except Exception as exc:
            raise FileReadException(
                message=f"Cannot read sheet names from '{file_path.name}': {exc}"
            ) from exc
        return []

    @staticmethod
    def _pick_engine(extension: str) -> str:
        """Select the correct pandas Excel engine for the file type."""
        return "openpyxl" if extension == "xlsx" else "xlrd"
