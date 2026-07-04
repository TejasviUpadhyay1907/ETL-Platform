"""
Unit tests for CSVReader, ExcelReader, and ReaderFactory.

Tests verify:
- CSV reading returns correct DataFrame and schema
- Excel reading returns correct DataFrame and schema
- Chunked CSV reading yields correct row counts per chunk
- Chunked Excel reading works
- ReaderFactory returns correct reader per extension
- ReaderFactory raises for unsupported extension
- dtype=str preservation (no silent type coercion)
- Column name whitespace stripping
- Empty data files return empty DataFrame
- Tab-separated files read correctly with correct delimiter
- latin-1 encoding files read correctly
"""

from pathlib import Path
from decimal import Decimal

import pandas as pd
import pytest

from app.core.exceptions import FileReadException, InvalidFileTypeException
from app.ingestion.readers.csv_reader import CSVReader
from app.ingestion.readers.excel_reader import ExcelReader
from app.ingestion.readers.reader_factory import ReaderFactory


@pytest.fixture(autouse=True)
def reset_factory():
    """Reset factory state between tests."""
    ReaderFactory.reset()
    yield
    ReaderFactory.reset()


# ─────────────────────────────────────────────────────────────────────────────
# CSVReader
# ─────────────────────────────────────────────────────────────────────────────

class TestCSVReader:

    def test_read_valid_csv(self, test_data_dir: Path):
        reader = CSVReader()
        df, schema = reader.read(test_data_dir / "orders_valid.csv")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 5
        assert "order_id" in df.columns

    def test_schema_correct(self, test_data_dir: Path):
        reader = CSVReader()
        df, schema = reader.read(test_data_dir / "orders_valid.csv")
        assert schema.row_count == 5
        assert schema.column_count == 6
        assert "order_id" in schema.column_names

    def test_all_columns_are_string_dtype(self, test_data_dir: Path):
        """All columns must be object/string — no silent numeric coercion."""
        reader = CSVReader()
        df, _ = reader.read(test_data_dir / "orders_valid.csv")
        for col in df.columns:
            assert df[col].dtype == object, f"Column {col!r} was coerced to {df[col].dtype}"

    def test_order_total_preserved_as_string(self, test_data_dir: Path):
        """'250.00' must remain '250.00', not be coerced to float 250.0."""
        reader = CSVReader()
        df, _ = reader.read(test_data_dir / "orders_valid.csv")
        assert df["order_total"].iloc[0] == "250.00"

    def test_column_names_stripped(self, tmp_path: Path):
        """Leading/trailing spaces in header should be stripped."""
        f = tmp_path / "spaced.csv"
        f.write_text(" order_id , total \nORD-001,100\n", encoding="utf-8")
        reader = CSVReader()
        df, _ = reader.read(f)
        assert "order_id" in df.columns
        assert "total" in df.columns

    def test_tab_delimiter(self, test_data_dir: Path):
        reader = CSVReader()
        df, _ = reader.read(test_data_dir / "orders_tab.csv", delimiter="\t")
        assert "order_id" in df.columns
        assert len(df) >= 1

    def test_latin1_encoding(self, test_data_dir: Path):
        reader = CSVReader()
        df, _ = reader.read(
            test_data_dir / "orders_latin1.csv",
            encoding="latin-1",
        )
        assert len(df) == 2
        assert "order_id" in df.columns

    def test_empty_data_file(self, test_data_dir: Path):
        """File with header but no data rows returns empty DataFrame."""
        reader = CSVReader()
        df, schema = reader.read(test_data_dir / "empty_orders.csv")
        assert len(df) == 0
        assert schema.row_count == 0
        assert "order_id" in df.columns

    def test_missing_file_raises(self, tmp_path: Path):
        reader = CSVReader()
        with pytest.raises(FileReadException):
            reader.read(tmp_path / "nonexistent.csv")

    def test_can_read_csv(self):
        assert CSVReader().can_read("csv") is True

    def test_cannot_read_xlsx(self):
        assert CSVReader().can_read("xlsx") is False

    def test_reader_name(self):
        assert CSVReader().reader_name == "CSVReader"

    def test_customers_csv(self, test_data_dir: Path):
        reader = CSVReader()
        df, schema = reader.read(test_data_dir / "customers_valid.csv")
        assert len(df) == 5
        assert "email" in df.columns

    def test_products_csv(self, test_data_dir: Path):
        reader = CSVReader()
        df, schema = reader.read(test_data_dir / "products_valid.csv")
        assert len(df) == 5
        assert "sku" in df.columns

    def test_payments_csv(self, test_data_dir: Path):
        reader = CSVReader()
        df, schema = reader.read(test_data_dir / "payments_valid.csv")
        assert len(df) == 5
        assert "payment_method" in df.columns


class TestCSVReaderChunked:

    def test_chunked_yields_dataframes(self, test_data_dir: Path):
        reader = CSVReader()
        chunks = list(reader.read_chunked(test_data_dir / "orders_valid.csv", chunk_size=2))
        assert len(chunks) >= 1
        assert all(isinstance(c, pd.DataFrame) for c in chunks)

    def test_chunked_total_rows_match(self, test_data_dir: Path):
        reader = CSVReader()
        chunks = list(reader.read_chunked(test_data_dir / "orders_valid.csv", chunk_size=2))
        total = sum(len(c) for c in chunks)
        assert total == 5

    def test_chunk_size_respected(self, test_data_dir: Path):
        reader = CSVReader()
        chunks = list(reader.read_chunked(test_data_dir / "orders_valid.csv", chunk_size=2))
        for chunk in chunks[:-1]:
            assert len(chunk) <= 2

    def test_chunked_columns_consistent(self, test_data_dir: Path):
        reader = CSVReader()
        chunks = list(reader.read_chunked(test_data_dir / "orders_valid.csv", chunk_size=2))
        col_sets = [set(c.columns) for c in chunks]
        assert all(cs == col_sets[0] for cs in col_sets)

    def test_single_chunk_when_rows_less_than_chunk_size(self, test_data_dir: Path):
        reader = CSVReader()
        chunks = list(reader.read_chunked(test_data_dir / "orders_valid.csv", chunk_size=1000))
        assert len(chunks) == 1
        assert len(chunks[0]) == 5


# ─────────────────────────────────────────────────────────────────────────────
# ExcelReader
# ─────────────────────────────────────────────────────────────────────────────

class TestExcelReader:

    def test_read_valid_xlsx(self, test_data_dir: Path):
        reader = ExcelReader()
        df, schema = reader.read(test_data_dir / "orders_valid.xlsx")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert "order_id" in df.columns

    def test_schema_correct(self, test_data_dir: Path):
        reader = ExcelReader()
        df, schema = reader.read(test_data_dir / "orders_valid.xlsx")
        assert schema.row_count == 3
        assert "order_id" in schema.column_names

    def test_all_columns_string_dtype(self, test_data_dir: Path):
        reader = ExcelReader()
        df, _ = reader.read(test_data_dir / "orders_valid.xlsx")
        for col in df.columns:
            assert df[col].dtype == object, f"Column {col!r} was coerced"

    def test_multi_sheet_reads_first_by_default(self, test_data_dir: Path):
        reader = ExcelReader()
        df, _ = reader.read(test_data_dir / "multi_sheet.xlsx")
        assert "order_id" in df.columns  # first sheet is Orders

    def test_sheet_selection_by_name(self, test_data_dir: Path):
        reader = ExcelReader()
        df, _ = reader.read(test_data_dir / "multi_sheet.xlsx", sheet_name="Orders")
        assert "order_id" in df.columns

    def test_get_sheet_names(self, test_data_dir: Path):
        reader = ExcelReader()
        sheets = reader.get_sheet_names(test_data_dir / "multi_sheet.xlsx")
        assert "Orders" in sheets
        assert len(sheets) >= 2

    def test_can_read_xlsx(self):
        assert ExcelReader().can_read("xlsx") is True

    def test_can_read_xls(self):
        assert ExcelReader().can_read("xls") is True

    def test_cannot_read_csv(self):
        assert ExcelReader().can_read("csv") is False

    def test_reader_name(self):
        assert ExcelReader().reader_name == "ExcelReader"

    def test_missing_file_raises(self, tmp_path: Path):
        reader = ExcelReader()
        with pytest.raises((FileReadException, Exception)):
            reader.read(tmp_path / "nonexistent.xlsx")


class TestExcelReaderChunked:

    def test_chunked_yields_all_rows(self, test_data_dir: Path):
        reader = ExcelReader()
        chunks = list(reader.read_chunked(test_data_dir / "orders_valid.xlsx", chunk_size=2))
        total = sum(len(c) for c in chunks)
        assert total == 3

    def test_chunked_columns_consistent(self, test_data_dir: Path):
        reader = ExcelReader()
        chunks = list(reader.read_chunked(test_data_dir / "orders_valid.xlsx", chunk_size=1))
        assert all(set(c.columns) == set(chunks[0].columns) for c in chunks)


# ─────────────────────────────────────────────────────────────────────────────
# ReaderFactory
# ─────────────────────────────────────────────────────────────────────────────

class TestReaderFactory:

    def test_csv_returns_csv_reader(self):
        reader = ReaderFactory.get_reader("csv")
        assert reader.reader_name == "CSVReader"

    def test_xlsx_returns_excel_reader(self):
        reader = ReaderFactory.get_reader("xlsx")
        assert reader.reader_name == "ExcelReader"

    def test_xls_returns_excel_reader(self):
        reader = ReaderFactory.get_reader("xls")
        assert reader.reader_name == "ExcelReader"

    def test_case_insensitive(self):
        reader = ReaderFactory.get_reader("CSV")
        assert reader.reader_name == "CSVReader"

    def test_unsupported_extension_raises(self):
        with pytest.raises(InvalidFileTypeException):
            ReaderFactory.get_reader("parquet")

    def test_supported_extensions_returns_list(self):
        exts = ReaderFactory.supported_extensions()
        assert "csv" in exts
        assert "xlsx" in exts
        assert "xls" in exts

    def test_custom_reader_registration(self):
        from app.ingestion.readers.base_reader import BaseReader
        import pandas as pd
        from app.ingestion.models import DatasetSchema
        from typing import Generator

        class FakeReader(BaseReader):
            @property
            def reader_name(self) -> str:
                return "FakeReader"

            def can_read(self, ext: str) -> bool:
                return ext == "fake"

            def read(self, fp, **kw):
                return pd.DataFrame(), DatasetSchema()

            def read_chunked(self, fp, chunk_size=1000, **kw) -> Generator:
                return iter([])

        fake = FakeReader()
        ReaderFactory._ensure_defaults_registered()
        ReaderFactory._registry["fake"] = fake
        assert ReaderFactory.get_reader("fake").reader_name == "FakeReader"
