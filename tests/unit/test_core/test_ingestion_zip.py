"""
Unit tests for ZipReader.

Tests verify:
- Valid ZIP containing single CSV is read correctly
- Valid ZIP containing single XLSX is read correctly
- ZIP with multiple supported files raises FileReadException
- Corrupt ZIP raises FileReadException
- ZipReader.can_read() returns True only for 'zip'
- ReaderFactory returns ZipReader for 'zip' extension
- list_contents() returns inner filenames
"""

import zipfile
from pathlib import Path

import pytest

from app.core.exceptions import FileReadException, InvalidFileTypeException
from app.ingestion.readers.zip_reader import ZipReader
from app.ingestion.readers.reader_factory import ReaderFactory


@pytest.fixture(autouse=True)
def reset_factory():
    ReaderFactory.reset()
    yield
    ReaderFactory.reset()


class TestZipReaderCanRead:

    def test_can_read_zip(self):
        assert ZipReader().can_read("zip") is True

    def test_cannot_read_csv(self):
        assert ZipReader().can_read("csv") is False

    def test_cannot_read_xlsx(self):
        assert ZipReader().can_read("xlsx") is False

    def test_reader_name(self):
        assert ZipReader().reader_name == "ZipReader"


class TestZipReaderSuccess:

    def test_read_csv_from_zip(self, test_data_dir: Path):
        reader = ZipReader()
        df, schema = reader.read(test_data_dir / "orders_valid.zip")
        assert len(df) == 5
        assert "order_id" in df.columns

    def test_read_xlsx_from_zip(self, test_data_dir: Path):
        reader = ZipReader()
        df, schema = reader.read(test_data_dir / "orders_xlsx.zip")
        assert len(df) == 3
        assert "order_id" in df.columns

    def test_schema_populated(self, test_data_dir: Path):
        reader = ZipReader()
        df, schema = reader.read(test_data_dir / "orders_valid.zip")
        assert schema.row_count == 5
        assert "order_id" in schema.column_names

    def test_values_preserved_as_strings(self, test_data_dir: Path):
        reader = ZipReader()
        df, _ = reader.read(test_data_dir / "orders_valid.zip")
        assert df["order_total"].iloc[0] == "250.00"

    def test_list_contents(self, test_data_dir: Path):
        reader = ZipReader()
        contents = reader.list_contents(test_data_dir / "orders_valid.zip")
        assert "orders_valid.csv" in contents

    def test_list_contents_multi_file(self, test_data_dir: Path):
        reader = ZipReader()
        contents = reader.list_contents(test_data_dir / "multi_file.zip")
        assert len(contents) == 2


class TestZipReaderErrors:

    def test_multi_file_zip_raises(self, test_data_dir: Path):
        reader = ZipReader()
        with pytest.raises(FileReadException, match="multiple"):
            reader.read(test_data_dir / "multi_file.zip")

    def test_corrupt_zip_raises(self, tmp_path: Path):
        f = tmp_path / "corrupt.zip"
        f.write_bytes(b"this is not a zip file at all")
        reader = ZipReader()
        with pytest.raises(FileReadException):
            reader.read(f)

    def test_empty_zip_raises(self, tmp_path: Path):
        f = tmp_path / "empty.zip"
        with zipfile.ZipFile(f, "w") as zf:
            pass  # empty archive
        reader = ZipReader()
        with pytest.raises(FileReadException, match="no supported files"):
            reader.read(f)

    def test_zip_with_unsupported_files_raises(self, tmp_path: Path):
        f = tmp_path / "bad_contents.zip"
        inner = tmp_path / "data.json"
        inner.write_text('{"key": "value"}')
        with zipfile.ZipFile(f, "w") as zf:
            zf.write(inner, "data.json")
        reader = ZipReader()
        with pytest.raises(FileReadException, match="no supported files"):
            reader.read(f)


class TestZipReaderChunked:

    def test_chunked_yields_correct_rows(self, test_data_dir: Path):
        reader = ZipReader()
        chunks = list(reader.read_chunked(test_data_dir / "orders_valid.zip", chunk_size=2))
        total = sum(len(c) for c in chunks)
        assert total == 5

    def test_chunked_columns_consistent(self, test_data_dir: Path):
        reader = ZipReader()
        chunks = list(reader.read_chunked(test_data_dir / "orders_valid.zip", chunk_size=2))
        assert all(set(c.columns) == set(chunks[0].columns) for c in chunks)


class TestZipReaderFactoryIntegration:

    def test_factory_returns_zip_reader(self):
        reader = ReaderFactory.get_reader("zip")
        assert reader.reader_name == "ZipReader"

    def test_zip_in_supported_extensions(self):
        assert "zip" in ReaderFactory.supported_extensions()
