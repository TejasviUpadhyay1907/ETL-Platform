"""
FileTypeDetector — validates file-level properties before any content is read.

Responsibilities (file-level ONLY, no content inspection):
1. Verify the file exists and is readable
2. Validate the file extension against the allowed list
3. Validate the MIME type
4. Enforce the maximum file size limit
5. Detect whether a CSV file is readable (open without error)
6. Detect whether an Excel file is readable and not password-protected
7. Detect file encoding for CSV files
8. Detect CSV delimiter

Does NOT:
- Read or parse data rows
- Validate column names or types
- Apply any business rules

Design: raises specific custom exceptions from app.core.exceptions so
callers get a machine-readable error_code alongside the human message.
"""

import os
import re
import sys
from pathlib import Path

from app.core.exceptions import (
    FileNotFoundException,
    FileReadException,
    FileTooLargeException,
    InvalidFileTypeException,
)
from app.logging.logger import get_logger

logger = get_logger(__name__)

# MIME types accepted per extension
ALLOWED_MIME_TYPES: dict[str, set[str]] = {
    "csv": {
        "text/csv",
        "text/plain",
        "application/csv",
        "application/octet-stream",
    },
    "xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
        "application/zip",
    },
    "xls": {
        "application/vnd.ms-excel",
        "application/octet-stream",
        "application/x-xls",
    },
}

# Encoding candidates tried in order for CSV files
ENCODING_CANDIDATES: list[str] = [
    "utf-8-sig",   # UTF-8 with BOM (Excel CSV exports)
    "utf-8",
    "latin-1",     # ISO-8859-1 — covers most Western European characters
    "cp1252",      # Windows Western European
    "utf-16",
]

# CSV sniffer sample size (bytes)
CSV_SNIFFER_SAMPLE = 8192


class FileValidationResult:
    """
    Outcome of file-level validation.

    All detected properties (encoding, delimiter, sheet names) are stored here
    so they do not need to be re-detected during reading.
    """

    __slots__ = (
        "is_valid",
        "extension",
        "mime_type",
        "encoding",
        "delimiter",
        "excel_sheet_names",
        "excel_active_sheet",
        "error_message",
    )

    def __init__(self) -> None:
        self.is_valid: bool = False
        self.extension: str = ""
        self.mime_type: str | None = None
        self.encoding: str | None = None
        self.delimiter: str | None = None
        self.excel_sheet_names: list[str] = []
        self.excel_active_sheet: str | None = None
        self.error_message: str | None = None


class FileTypeDetector:
    """
    Validates a file at the filesystem and format level.

    This detector is stateless — each call to validate() operates independently.
    Instantiate once and reuse across multiple file validations.
    """

    def __init__(
        self,
        allowed_extensions: list[str] | None = None,
        max_size_bytes: int | None = None,
    ) -> None:
        """
        Args:
            allowed_extensions: Extensions to accept (default: csv, xlsx, xls).
            max_size_bytes:     Maximum file size. Loaded from config if None.
        """
        if allowed_extensions is None:
            from app.core.config import get_config
            allowed_extensions = get_config().allowed_file_types_list

        if max_size_bytes is None:
            from app.core.config import get_config
            max_size_bytes = get_config().max_upload_size_bytes

        self._allowed_extensions: frozenset[str] = frozenset(
            e.lower().lstrip(".") for e in allowed_extensions
        )
        self._max_size_bytes: int = max_size_bytes

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, file_path: Path) -> FileValidationResult:
        """
        Run all file-level checks on the given path.

        Returns a FileValidationResult with all detected properties.
        Raises a specific exception on the first fatal error encountered.

        Args:
            file_path: Path to the file to validate.

        Returns:
            FileValidationResult with is_valid=True and detected properties.

        Raises:
            FileNotFoundException:    File does not exist.
            FileReadException:        File is not readable (permissions, corrupt).
            FileTooLargeException:    File exceeds max_size_bytes.
            InvalidFileTypeException: Extension or MIME type not allowed.
        """
        result = FileValidationResult()

        self._check_exists(file_path)
        self._check_readable(file_path)
        self._check_size(file_path)

        extension = self._extract_extension(file_path)
        self._check_extension(extension, file_path.name)
        result.extension = extension

        mime_type = self._detect_mime_type(file_path)
        self._check_mime_type(mime_type, extension, file_path.name)
        result.mime_type = mime_type

        # Format-specific checks
        if extension == "csv":
            result.encoding = self._detect_encoding(file_path)
            result.delimiter = self._detect_delimiter(file_path, result.encoding)
            self._check_csv_readable(file_path, result.encoding)
        elif extension in ("xlsx", "xls"):
            sheets = self._detect_excel_sheets(file_path, extension)
            result.excel_sheet_names = sheets
            result.excel_active_sheet = sheets[0] if sheets else None

        result.is_valid = True
        logger.debug(
            "File validated",
            filename=file_path.name,
            extension=extension,
            encoding=result.encoding,
            delimiter=repr(result.delimiter),
        )
        return result

    # ------------------------------------------------------------------
    # Private checks
    # ------------------------------------------------------------------

    def _check_exists(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundException(
                message=f"File not found: '{path.name}'"
            )
        if not path.is_file():
            raise FileNotFoundException(
                message=f"Path is not a file: '{path.name}'"
            )

    def _check_readable(self, path: Path) -> None:
        if not os.access(path, os.R_OK):
            raise FileReadException(
                message=f"Permission denied reading file: '{path.name}'"
            )

    def _check_size(self, path: Path) -> None:
        size = path.stat().st_size
        if size == 0:
            raise FileReadException(
                message=f"File is empty: '{path.name}'"
            )
        if size > self._max_size_bytes:
            from app.utils.file_utils import format_file_size
            raise FileTooLargeException(
                message=(
                    f"File '{path.name}' ({format_file_size(size)}) "
                    f"exceeds maximum allowed size "
                    f"({format_file_size(self._max_size_bytes)})."
                ),
                file_size_bytes=size,
                max_size_bytes=self._max_size_bytes,
            )

    def _extract_extension(self, path: Path) -> str:
        return path.suffix.lstrip(".").lower()

    def _check_extension(self, extension: str, filename: str) -> None:
        if not extension:
            raise InvalidFileTypeException(
                message=f"File '{filename}' has no extension.",
                file_extension="",
                allowed_types=sorted(self._allowed_extensions),
            )
        if extension not in self._allowed_extensions:
            raise InvalidFileTypeException(
                message=(
                    f"File extension '.{extension}' is not supported. "
                    f"Allowed: {sorted(self._allowed_extensions)}"
                ),
                file_extension=extension,
                allowed_types=sorted(self._allowed_extensions),
            )

    def _detect_mime_type(self, path: Path) -> str | None:
        """
        Detect MIME type using the standard mimetypes module.

        Falls back to None if detection fails — the MIME check is then skipped
        rather than blocking ingestion for an unrecognised but valid file.
        """
        import mimetypes
        mime, _ = mimetypes.guess_type(str(path))
        return mime

    def _check_mime_type(
        self, mime_type: str | None, extension: str, filename: str
    ) -> None:
        """Warn on unexpected MIME type but do not reject (mimetypes is unreliable)."""
        if mime_type is None:
            return  # Cannot determine — skip check
        allowed = ALLOWED_MIME_TYPES.get(extension, set())
        if allowed and mime_type not in allowed:
            logger.warning(
                "Unexpected MIME type for file",
                filename=filename,
                detected_mime=mime_type,
                expected_mimes=sorted(allowed),
            )

    def _detect_encoding(self, path: Path) -> str:
        """
        Detect the character encoding of a CSV file.

        Tries candidate encodings in order and returns the first that decodes
        the file's first 64 KB without errors.

        Falls back to 'latin-1' as a last resort — latin-1 never raises a
        UnicodeDecodeError because it maps all 256 byte values.
        """
        sample_size = 65536  # 64 KB sample
        with path.open("rb") as f:
            raw = f.read(sample_size)

        # Check for BOM markers
        if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
            return "utf-16"
        if raw.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"

        for enc in ENCODING_CANDIDATES:
            try:
                raw.decode(enc, errors="strict")
                return enc
            except (UnicodeDecodeError, LookupError):
                continue

        logger.warning(f"Could not detect encoding for {path.name}, defaulting to latin-1")
        return "latin-1"

    def _detect_delimiter(self, path: Path, encoding: str | None = None) -> str:
        """
        Detect the CSV field delimiter using Python's csv.Sniffer.

        Falls back to comma if sniffing fails — comma is the correct default
        for the vast majority of CSV files in the retail domain.
        """
        import csv

        enc = encoding or "utf-8"
        try:
            with path.open("r", encoding=enc, errors="replace") as f:
                sample = f.read(CSV_SNIFFER_SAMPLE)
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            return dialect.delimiter
        except csv.Error:
            return ","  # safe fallback

    def _check_csv_readable(self, path: Path, encoding: str | None) -> None:
        """Verify the CSV file can be opened and has at least one non-empty line."""
        enc = encoding or "utf-8"
        try:
            with path.open("r", encoding=enc, errors="replace") as f:
                first_line = f.readline()
            if not first_line.strip():
                raise FileReadException(
                    message=f"CSV file '{path.name}' appears to contain no header row."
                )
        except OSError as exc:
            raise FileReadException(
                message=f"Cannot read CSV file '{path.name}': {exc}"
            ) from exc

    def _detect_excel_sheets(
        self, path: Path, extension: str
    ) -> list[str]:
        """
        Read the sheet names from an Excel workbook without loading cell data.

        Uses openpyxl (xlsx) or xlrd (xls) as appropriate.
        Detects password-protected workbooks and raises FileReadException.
        """
        try:
            if extension == "xlsx":
                import openpyxl
                try:
                    wb = openpyxl.load_workbook(
                        str(path), read_only=True, data_only=True
                    )
                    sheets = wb.sheetnames
                    wb.close()
                    return sheets
                except Exception as exc:
                    msg = str(exc).lower()
                    if "encrypted" in msg or "password" in msg or "protected" in msg:
                        raise FileReadException(
                            message=(
                                f"Excel file '{path.name}' is password-protected. "
                                "Remove the password before uploading."
                            )
                        ) from exc
                    raise FileReadException(
                        message=f"Cannot open Excel file '{path.name}': {exc}"
                    ) from exc

            elif extension == "xls":
                import xlrd
                try:
                    wb = xlrd.open_workbook(str(path), on_demand=True)
                    sheets = wb.sheet_names()
                    wb.release_resources()
                    return sheets
                except xlrd.XLRDError as exc:
                    msg = str(exc).lower()
                    if "workbook" in msg and ("password" in msg or "encrypted" in msg):
                        raise FileReadException(
                            message=f"Excel file '{path.name}' is password-protected."
                        ) from exc
                    raise FileReadException(
                        message=f"Cannot read .xls file '{path.name}': {exc}"
                    ) from exc

        except FileReadException:
            raise
        except Exception as exc:
            raise FileReadException(
                message=f"Unexpected error inspecting Excel file '{path.name}': {exc}"
            ) from exc

        return []
