"""
Unit tests for FileTypeDetector.

Tests verify:
- Valid CSV files pass all checks
- Valid Excel files pass all checks and return sheet names
- Extension validation rejects unsupported formats
- File size enforcement
- Missing file detection
- Empty file detection
- Encoding detection for UTF-8, latin-1
- Delimiter detection for comma, tab, semicolon
- Excel sheet name extraction
"""

import csv
from pathlib import Path

import pytest

from app.core.exceptions import (
    FileNotFoundException,
    FileReadException,
    FileTooLargeException,
    InvalidFileTypeException,
)
from app.ingestion.file_type_detector import FileTypeDetector


@pytest.fixture
def detector():
    """FileTypeDetector with 10 MB max size."""
    return FileTypeDetector(
        allowed_extensions=["csv", "xlsx", "xls"],
        max_size_bytes=10 * 1024 * 1024,
    )


@pytest.fixture
def orders_csv(test_data_dir: Path) -> Path:
    return test_data_dir / "orders_valid.csv"


@pytest.fixture
def orders_xlsx(test_data_dir: Path) -> Path:
    return test_data_dir / "orders_valid.xlsx"


class TestFileExistence:

    def test_missing_file_raises(self, detector, tmp_path):
        with pytest.raises(FileNotFoundException):
            detector.validate(tmp_path / "nonexistent.csv")

    def test_directory_raises(self, detector, tmp_path):
        d = tmp_path / "subdir"
        d.mkdir()
        with pytest.raises(FileNotFoundException):
            detector.validate(d)


class TestExtensionValidation:

    def test_csv_accepted(self, detector, orders_csv):
        result = detector.validate(orders_csv)
        assert result.is_valid
        assert result.extension == "csv"

    def test_xlsx_accepted(self, detector, orders_xlsx):
        result = detector.validate(orders_xlsx)
        assert result.is_valid
        assert result.extension == "xlsx"

    def test_exe_rejected(self, detector, tmp_path):
        f = tmp_path / "malware.exe"
        f.write_bytes(b"MZ" + b"\x00" * 100)
        with pytest.raises(InvalidFileTypeException) as exc_info:
            detector.validate(f)
        assert exc_info.value.file_extension == "exe"

    def test_no_extension_rejected(self, detector, tmp_path):
        f = tmp_path / "noextension"
        f.write_bytes(b"data,goes,here\n")
        with pytest.raises(InvalidFileTypeException):
            detector.validate(f)

    def test_pdf_rejected(self, detector, tmp_path):
        f = tmp_path / "report.pdf"
        f.write_bytes(b"%PDF-1.4 fake content")
        with pytest.raises(InvalidFileTypeException):
            detector.validate(f)


class TestFileSizeValidation:

    def test_oversized_file_raises(self, tmp_path):
        """File larger than max_size_bytes raises FileTooLargeException."""
        detector = FileTypeDetector(
            allowed_extensions=["csv"],
            max_size_bytes=100,  # tiny limit for test
        )
        f = tmp_path / "big.csv"
        f.write_bytes(b"order_id,total\n" + b"ORD-001,100.00\n" * 10)
        with pytest.raises(FileTooLargeException) as exc_info:
            detector.validate(f)
        assert exc_info.value.max_size_bytes == 100

    def test_exactly_at_limit_passes(self, tmp_path):
        content = b"id,name\n1,Alice\n"
        detector = FileTypeDetector(
            allowed_extensions=["csv"],
            max_size_bytes=len(content),
        )
        f = tmp_path / "exact.csv"
        f.write_bytes(content)
        result = detector.validate(f)
        assert result.is_valid


class TestEmptyFile:

    def test_empty_file_raises(self, detector, tmp_path):
        f = tmp_path / "empty.csv"
        f.write_bytes(b"")
        with pytest.raises(FileReadException):
            detector.validate(f)


class TestEncodingDetection:

    def test_utf8_detected(self, detector, orders_csv):
        result = detector.validate(orders_csv)
        assert result.encoding in ("utf-8", "utf-8-sig")

    def test_utf8_bom_detected(self, detector, tmp_path):
        # Write UTF-8 with BOM (common from Excel CSV exports)
        f = tmp_path / "orders_bom.csv"
        f.write_bytes(b"\xef\xbb\xbford_id,total\nORD-001,100.00\n")
        result = detector.validate(f)
        assert result.encoding == "utf-8-sig"

    def test_latin1_detected(self, detector, test_data_dir: Path):
        f = test_data_dir / "orders_latin1.csv"
        result = detector.validate(f)
        assert result.encoding in ("latin-1", "cp1252", "utf-8")

    def test_encoding_stored_in_result(self, detector, orders_csv):
        result = detector.validate(orders_csv)
        assert result.encoding is not None


class TestDelimiterDetection:

    def test_comma_delimiter(self, detector, orders_csv):
        result = detector.validate(orders_csv)
        assert result.delimiter == ","

    def test_tab_delimiter(self, detector, test_data_dir: Path):
        f = test_data_dir / "orders_tab.csv"
        result = detector.validate(f)
        assert result.delimiter == "\t"

    def test_delimiter_stored_in_result(self, detector, orders_csv):
        result = detector.validate(orders_csv)
        assert result.delimiter is not None


class TestExcelValidation:

    def test_xlsx_sheet_names_extracted(self, detector, orders_xlsx):
        result = detector.validate(orders_xlsx)
        assert result.is_valid
        assert "Orders" in result.excel_sheet_names

    def test_multi_sheet_xlsx(self, detector, test_data_dir: Path):
        f = test_data_dir / "multi_sheet.xlsx"
        result = detector.validate(f)
        assert len(result.excel_sheet_names) >= 2
        assert "Orders" in result.excel_sheet_names

    def test_active_sheet_is_first(self, detector, orders_xlsx):
        result = detector.validate(orders_xlsx)
        assert result.excel_active_sheet == result.excel_sheet_names[0]

    def test_xlsx_encoding_is_none(self, detector, orders_xlsx):
        """Excel files do not have a text encoding."""
        result = detector.validate(orders_xlsx)
        assert result.encoding is None

    def test_xlsx_delimiter_is_none(self, detector, orders_xlsx):
        """Excel files do not have a CSV delimiter."""
        result = detector.validate(orders_xlsx)
        assert result.delimiter is None


class TestDetectorEdgeCases:
    """Cover additional FileTypeDetector code paths."""

    def test_custom_allowed_extensions(self, tmp_path: Path):
        """Detector with restricted extension list."""
        detector = FileTypeDetector(
            allowed_extensions=["csv"],
            max_size_bytes=10 * 1024 * 1024,
        )
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"dummy xlsx bytes" * 100)
        with pytest.raises(InvalidFileTypeException):
            detector.validate(f)

    def test_csv_with_semicolon_delimiter(self, tmp_path: Path):
        """Detect semicolon-delimited CSV."""
        f = tmp_path / "orders.csv"
        f.write_text(
            "order_id;customer_id;order_total\nORD-001;CUST-001;100.00\n",
            encoding="utf-8",
        )
        detector = FileTypeDetector(allowed_extensions=["csv"], max_size_bytes=1024 * 1024)
        result = detector.validate(f)
        assert result.is_valid
        assert result.delimiter == ";"

    def test_csv_with_pipe_delimiter(self, tmp_path: Path):
        """Detect pipe-delimited CSV."""
        f = tmp_path / "orders.csv"
        f.write_text(
            "order_id|customer_id|order_total\nORD-001|CUST-001|100.00\n",
            encoding="utf-8",
        )
        detector = FileTypeDetector(allowed_extensions=["csv"], max_size_bytes=1024 * 1024)
        result = detector.validate(f)
        assert result.is_valid
        assert result.delimiter == "|"

    def test_file_extension_case_insensitive(self, tmp_path: Path, test_data_dir: Path):
        """Upper-case extension should be accepted."""
        f = tmp_path / "ORDERS.CSV"
        f.write_bytes((test_data_dir / "orders_valid.csv").read_bytes())
        detector = FileTypeDetector(allowed_extensions=["csv"], max_size_bytes=50 * 1024 * 1024)
        result = detector.validate(f)
        assert result.is_valid
        assert result.extension == "csv"

    def test_multi_sheet_xlsx_detection(self, tmp_path: Path, test_data_dir: Path):
        """Multi-sheet xlsx reports all sheet names."""
        import shutil
        f = tmp_path / "multi.xlsx"
        shutil.copy(test_data_dir / "multi_sheet.xlsx", f)
        detector = FileTypeDetector(allowed_extensions=["xlsx"], max_size_bytes=50 * 1024 * 1024)
        result = detector.validate(f)
        assert result.is_valid
        assert len(result.excel_sheet_names) >= 2

    def test_xlsx_with_wrong_extension_not_detected(self, tmp_path: Path):
        """A file with .txt extension is rejected even if it contains xlsx content."""
        detector = FileTypeDetector(allowed_extensions=["csv"], max_size_bytes=1024 * 1024)
        f = tmp_path / "fake.txt"
        f.write_bytes(b"some text content that is not a csv file but has enough bytes\n" * 10)
        with pytest.raises(InvalidFileTypeException):
            detector.validate(f)
