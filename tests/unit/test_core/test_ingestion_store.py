"""
Unit tests for RawFileStore and MetadataExtractor.

Tests verify:
- Files are stored at the correct versioned path
- store() copies source file correctly
- store_bytes() writes bytes correctly
- delete() removes stored file
- get_path() reconstructs expected path
- MetadataExtractor assembles FileMetadata correctly from all inputs
- Metadata fields are correctly populated
- row counts are set from schema
- file size is read from stored file
"""

from datetime import date
from pathlib import Path
from decimal import Decimal

import pytest

from app.ingestion.raw_file_store import RawFileStore
from app.ingestion.metadata_extractor import MetadataExtractor
from app.ingestion.models import DatasetSchema, FileMetadata
from app.ingestion.file_type_detector import FileValidationResult


# ─────────────────────────────────────────────────────────────────────────────
# RawFileStore
# ─────────────────────────────────────────────────────────────────────────────

class TestRawFileStore:

    def test_store_copies_file(self, tmp_path: Path, test_data_dir: Path):
        store = RawFileStore(tmp_path / "raw")
        stored = store.store(
            source_path=test_data_dir / "orders_valid.csv",
            dataset_type="orders",
            original_filename="orders_valid.csv",
            ingestion_id="test-id-001",
            run_date=date(2025, 1, 15),
        )
        assert stored.exists()
        assert stored.name == "orders_valid.csv"

    def test_stored_path_structure(self, tmp_path: Path, test_data_dir: Path):
        store = RawFileStore(tmp_path / "raw")
        stored = store.store(
            source_path=test_data_dir / "orders_valid.csv",
            dataset_type="orders",
            original_filename="orders_valid.csv",
            ingestion_id="abc-123",
            run_date=date(2025, 3, 10),
        )
        # Verify versioned directory structure
        assert "orders" in str(stored)
        assert "2025-03-10" in str(stored)
        assert "abc-123" in str(stored)

    def test_stored_file_content_matches_source(self, tmp_path: Path, test_data_dir: Path):
        store = RawFileStore(tmp_path / "raw")
        src = test_data_dir / "orders_valid.csv"
        stored = store.store(
            source_path=src,
            dataset_type="orders",
            original_filename="orders_valid.csv",
            ingestion_id="content-test",
        )
        assert stored.read_bytes() == src.read_bytes()

    def test_store_bytes_creates_file(self, tmp_path: Path):
        store = RawFileStore(tmp_path / "raw")
        content = b"order_id,total\nORD-001,100.00\n"
        stored = store.store_bytes(
            content=content,
            dataset_type="orders",
            original_filename="test.csv",
            ingestion_id="bytes-test",
        )
        assert stored.exists()
        assert stored.read_bytes() == content

    def test_store_bytes_size_matches(self, tmp_path: Path):
        store = RawFileStore(tmp_path / "raw")
        content = b"id,name\n1,Alice\n2,Bob\n"
        stored = store.store_bytes(
            content=content,
            dataset_type="customers",
            original_filename="customers.csv",
            ingestion_id="size-test",
        )
        assert stored.stat().st_size == len(content)

    def test_delete_removes_file(self, tmp_path: Path, test_data_dir: Path):
        store = RawFileStore(tmp_path / "raw")
        stored = store.store(
            source_path=test_data_dir / "orders_valid.csv",
            dataset_type="orders",
            original_filename="orders_valid.csv",
            ingestion_id="delete-test",
        )
        assert stored.exists()
        store.delete(stored)
        assert not stored.exists()

    def test_delete_missing_file_silent(self, tmp_path: Path):
        store = RawFileStore(tmp_path / "raw")
        # Should not raise
        store.delete(tmp_path / "does_not_exist.csv")

    def test_get_path_reconstructs_correctly(self, tmp_path: Path):
        store = RawFileStore(tmp_path / "raw")
        path = store.get_path(
            dataset_type="payments",
            ingestion_id="xyz-789",
            filename="payments.csv",
            run_date=date(2025, 6, 1),
        )
        assert path == tmp_path / "raw" / "payments" / "2025-06-01" / "xyz-789" / "payments.csv"

    def test_store_creates_parent_directories(self, tmp_path: Path, test_data_dir: Path):
        store = RawFileStore(tmp_path / "deep" / "raw")
        stored = store.store(
            source_path=test_data_dir / "orders_valid.csv",
            dataset_type="orders",
            original_filename="orders.csv",
            ingestion_id="deep-test",
        )
        assert stored.exists()

    def test_concurrent_same_filename_stores(self, tmp_path: Path, test_data_dir: Path):
        """Two different ingestion_ids for same filename do not collide."""
        store = RawFileStore(tmp_path / "raw")
        src = test_data_dir / "orders_valid.csv"
        p1 = store.store(src, "orders", "orders.csv", ingestion_id="run-001")
        p2 = store.store(src, "orders", "orders.csv", ingestion_id="run-002")
        assert p1 != p2
        assert p1.exists()
        assert p2.exists()


# ─────────────────────────────────────────────────────────────────────────────
# MetadataExtractor
# ─────────────────────────────────────────────────────────────────────────────

class TestMetadataExtractor:

    def _make_validation_result(
        self,
        extension="csv",
        encoding="utf-8",
        delimiter=",",
        sheet_names=None,
    ) -> FileValidationResult:
        r = FileValidationResult()
        r.is_valid = True
        r.extension = extension
        r.encoding = encoding
        r.delimiter = delimiter
        r.excel_sheet_names = sheet_names or []
        r.excel_active_sheet = sheet_names[0] if sheet_names else None
        return r

    def test_extract_builds_metadata(self, tmp_path: Path, test_data_dir: Path):
        extractor = MetadataExtractor()
        stored = tmp_path / "orders.csv"
        stored.write_bytes((test_data_dir / "orders_valid.csv").read_bytes())

        validation = self._make_validation_result()
        schema = DatasetSchema(
            column_names=["order_id", "total"],
            column_dtypes={"order_id": "object", "total": "object"},
            row_count=5,
            column_count=2,
        )

        meta = extractor.extract(
            file_path=stored,
            original_filename="my_orders.csv",
            stored_filename="orders.csv",
            ingestion_id="meta-test-001",
            validation_result=validation,
            file_hash="a" * 64,
            dataset_type="orders",
            schema=schema,
            source_type="upload",
            uploaded_by="test-user",
            source_ip="192.168.1.1",
        )

        assert isinstance(meta, FileMetadata)
        assert meta.original_filename == "my_orders.csv"
        assert meta.stored_filename == "orders.csv"
        assert meta.ingestion_id == "meta-test-001"
        assert meta.dataset_type == "orders"
        assert meta.encoding == "utf-8"
        assert meta.delimiter == ","
        assert meta.file_hash == "a" * 64
        assert meta.source_type == "upload"
        assert meta.uploaded_by == "test-user"
        assert meta.source_ip == "192.168.1.1"

    def test_row_counts_from_schema(self, tmp_path: Path):
        extractor = MetadataExtractor()
        stored = tmp_path / "test.csv"
        stored.write_bytes(b"id,name\n1,Alice\n2,Bob\n")

        validation = self._make_validation_result()
        schema = DatasetSchema(row_count=2, column_count=2, column_names=["id", "name"])

        meta = extractor.extract(
            file_path=stored,
            original_filename="test.csv",
            stored_filename="test.csv",
            ingestion_id="row-count-test",
            validation_result=validation,
            file_hash="b" * 64,
            dataset_type="customers",
            schema=schema,
        )

        assert meta.row_count_data == 2
        assert meta.row_count_raw == 3  # +1 for header

    def test_file_size_from_stat(self, tmp_path: Path):
        extractor = MetadataExtractor()
        content = b"order_id,total\nORD-001,100.00\n"
        stored = tmp_path / "test.csv"
        stored.write_bytes(content)

        validation = self._make_validation_result()
        meta = extractor.extract(
            file_path=stored,
            original_filename="test.csv",
            stored_filename="test.csv",
            ingestion_id="size-test",
            validation_result=validation,
            file_hash="c" * 64,
            dataset_type="orders",
        )

        assert meta.file_size_bytes == len(content)

    def test_excel_sheet_names_populated(self, tmp_path: Path):
        extractor = MetadataExtractor()
        stored = tmp_path / "test.xlsx"
        stored.write_bytes(b"fake excel bytes")

        validation = self._make_validation_result(
            extension="xlsx",
            encoding=None,
            delimiter=None,
            sheet_names=["Orders", "Metadata"],
        )

        meta = extractor.extract(
            file_path=stored,
            original_filename="orders.xlsx",
            stored_filename="test.xlsx",
            ingestion_id="excel-test",
            validation_result=validation,
            file_hash="d" * 64,
            dataset_type="orders",
        )

        assert meta.excel_sheet_names == ["Orders", "Metadata"]
        assert meta.excel_active_sheet == "Orders"
        assert meta.encoding is None
        assert meta.delimiter is None

    def test_no_schema_row_counts_none(self, tmp_path: Path):
        extractor = MetadataExtractor()
        stored = tmp_path / "test.csv"
        stored.write_bytes(b"data")

        validation = self._make_validation_result()
        meta = extractor.extract(
            file_path=stored,
            original_filename="test.csv",
            stored_filename="test.csv",
            ingestion_id="no-schema",
            validation_result=validation,
            file_hash="e" * 64,
            dataset_type="orders",
            schema=None,
        )

        assert meta.row_count_data is None
        assert meta.row_count_raw is None

    def test_to_event_kwargs_compatible(self, tmp_path: Path):
        extractor = MetadataExtractor()
        stored = tmp_path / "test.csv"
        stored.write_bytes(b"id,v\n1,2\n")

        validation = self._make_validation_result()
        schema = DatasetSchema(row_count=1, column_count=2, column_names=["id", "v"])

        meta = extractor.extract(
            file_path=stored,
            original_filename="test.csv",
            stored_filename="test.csv",
            ingestion_id="kwargs-test",
            validation_result=validation,
            file_hash="f" * 64,
            dataset_type="orders",
            schema=schema,
        )

        kwargs = meta.to_event_kwargs()
        # Verify all required DB fields are present
        for key in ("original_filename", "stored_filename", "file_path",
                    "file_extension", "file_size_bytes", "file_hash",
                    "dataset_type", "status"):
            assert key in kwargs, f"Missing key: {key}"
