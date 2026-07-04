"""
Integration-style unit tests for IngestionService.

Uses the in-memory SQLite DB (db_session fixture) so no real PostgreSQL needed.
Tests verify the complete ingestion pipeline end-to-end:
- Successful ingestion of CSV / Excel
- Correct Dataset object returned
- IngestionEvent written to database
- Duplicate detection (reject policy)
- Duplicate reprocess policy
- Unknown dataset type rejection
- Oversized file rejection
- Empty file rejection
- Unsupported extension rejection
- Metadata correctness
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.ingestion.ingestion_service import IngestionService
from app.ingestion.ingestion_tracker import DuplicatePolicy
from app.ingestion.models import Dataset, IngestionResult, IngestionStatus
from app.ingestion.raw_file_store import RawFileStore
from app.ingestion.file_type_detector import FileTypeDetector
from app.ingestion.dataset_type_resolver import DatasetTypeResolver
from app.ingestion.hash_generator import HashGenerator
from app.ingestion.metadata_extractor import MetadataExtractor


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_service(db_session, tmp_path: Path, duplicate_policy: str = DuplicatePolicy.REJECT) -> IngestionService:
    """Build an IngestionService wired to in-memory SQLite and tmp_path store."""
    return IngestionService(
        session=db_session,
        file_store=RawFileStore(tmp_path / "raw"),
        detector=FileTypeDetector(
            allowed_extensions=["csv", "xlsx", "xls"],
            max_size_bytes=50 * 1024 * 1024,
        ),
        resolver=DatasetTypeResolver(),
        hash_gen=HashGenerator(),
        extractor=MetadataExtractor(),
        duplicate_policy=duplicate_policy,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Happy path — CSV ingestion
# ─────────────────────────────────────────────────────────────────────────────

class TestCSVIngestionSuccess:

    def test_orders_ingestion_succeeds(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(
            source_path=test_data_dir / "orders_valid.csv",
            original_filename="orders_valid.csv",
        )
        assert result.success is True
        assert result.status == IngestionStatus.PROCESSED

    def test_returns_dataset_object(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "orders_valid.csv")
        assert isinstance(result.dataset, Dataset)

    def test_dataset_has_correct_row_count(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "orders_valid.csv")
        assert result.dataset.row_count == 5

    def test_dataset_has_correct_columns(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "orders_valid.csv")
        assert "order_id" in result.dataset.columns
        assert "order_total" in result.dataset.columns

    def test_dataset_type_detected(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "orders_valid.csv")
        assert result.dataset.dataset_type == "orders"

    def test_dataset_type_explicit_override(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(
            test_data_dir / "orders_valid.csv",
            explicit_dataset_type="customers",
        )
        # Even though filename says orders, explicit wins
        assert result.dataset.dataset_type == "customers"

    def test_file_hash_is_64_chars(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "orders_valid.csv")
        assert result.file_metadata.file_hash is not None
        assert len(result.file_metadata.file_hash) == 64

    def test_reader_used_is_csv(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "orders_valid.csv")
        assert result.dataset.reader_used == "CSVReader"

    def test_ingestion_event_id_returned(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "orders_valid.csv")
        assert result.ingestion_event_id is not None

    def test_duration_recorded(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "orders_valid.csv")
        assert result.duration_seconds > 0

    def test_customers_ingestion(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "customers_valid.csv")
        assert result.success
        assert result.dataset.dataset_type == "customers"
        assert result.dataset.row_count == 5

    def test_products_ingestion(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "products_valid.csv")
        assert result.success
        assert result.dataset.row_count == 5

    def test_payments_ingestion(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "payments_valid.csv")
        assert result.success
        assert result.dataset.row_count == 5

    def test_suppliers_ingestion(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "suppliers_valid.csv")
        assert result.success
        assert result.dataset.row_count == 3

    def test_inventory_ingestion(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "inventory_valid.csv")
        assert result.success
        assert result.dataset.row_count == 5

    def test_all_values_preserved_as_strings(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "orders_valid.csv")
        df = result.dataset.dataframe
        assert df["order_total"].iloc[0] == "250.00"

    def test_latin1_encoding_ingested(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(
            test_data_dir / "orders_latin1.csv",
            explicit_dataset_type="orders",
        )
        assert result.success
        assert result.dataset.row_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# Happy path — Excel ingestion
# ─────────────────────────────────────────────────────────────────────────────

class TestExcelIngestionSuccess:

    def test_xlsx_ingestion_succeeds(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "orders_valid.xlsx")
        assert result.success
        assert result.dataset.row_count == 3

    def test_reader_used_is_excel(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "orders_valid.xlsx")
        assert result.dataset.reader_used == "ExcelReader"

    def test_multi_sheet_xlsx_reads_first_sheet(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(
            test_data_dir / "multi_sheet.xlsx",
            explicit_dataset_type="orders",
        )
        assert result.success
        assert "order_id" in result.dataset.columns

    def test_excel_metadata_correct(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "orders_valid.xlsx")
        assert result.file_metadata.excel_sheet_names == ["Orders"]
        assert result.file_metadata.file_extension == "xlsx"


# ─────────────────────────────────────────────────────────────────────────────
# Ingest from bytes
# ─────────────────────────────────────────────────────────────────────────────

class TestIngestBytes:

    def test_ingest_bytes_csv(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        content = (test_data_dir / "orders_valid.csv").read_bytes()
        result = svc.ingest_bytes(
            content=content,
            original_filename="orders_valid.csv",
        )
        assert result.success
        assert result.dataset.row_count == 5

    def test_ingest_bytes_xlsx(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        content = (test_data_dir / "orders_valid.xlsx").read_bytes()
        result = svc.ingest_bytes(
            content=content,
            original_filename="orders_valid.xlsx",
        )
        assert result.success

    def test_ingest_bytes_with_metadata(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        content = (test_data_dir / "customers_valid.csv").read_bytes()
        result = svc.ingest_bytes(
            content=content,
            original_filename="customers_valid.csv",
            uploaded_by="test-api-key",
            source_ip="127.0.0.1",
        )
        assert result.success
        assert result.file_metadata.uploaded_by == "test-api-key"
        assert result.file_metadata.source_ip == "127.0.0.1"


# ─────────────────────────────────────────────────────────────────────────────
# Duplicate detection
# ─────────────────────────────────────────────────────────────────────────────

class TestDuplicateDetection:

    def test_second_upload_rejected_with_reject_policy(
        self, db_session, tmp_path, test_data_dir
    ):
        svc = make_service(db_session, tmp_path, duplicate_policy=DuplicatePolicy.REJECT)
        # First upload
        r1 = svc.ingest(test_data_dir / "orders_valid.csv")
        assert r1.success

        # Same file again — should be rejected
        r2 = svc.ingest(test_data_dir / "orders_valid.csv")
        assert r2.success is False
        assert r2.is_duplicate is True
        assert r2.status == IngestionStatus.DUPLICATE
        assert r2.error_code == "DUPLICATE_FILE"

    def test_duplicate_references_original_event(
        self, db_session, tmp_path, test_data_dir
    ):
        svc = make_service(db_session, tmp_path, duplicate_policy=DuplicatePolicy.REJECT)
        r1 = svc.ingest(test_data_dir / "orders_valid.csv")
        r2 = svc.ingest(test_data_dir / "orders_valid.csv")
        assert r2.duplicate_of_event_id == r1.ingestion_event_id

    def test_reprocess_policy_allows_duplicate(
        self, db_session, tmp_path, test_data_dir
    ):
        svc = make_service(db_session, tmp_path, duplicate_policy=DuplicatePolicy.REPROCESS)
        r1 = svc.ingest(test_data_dir / "orders_valid.csv")
        assert r1.success

        r2 = svc.ingest(test_data_dir / "orders_valid.csv")
        assert r2.success is True
        assert r2.is_duplicate is True  # flagged but not rejected

    def test_different_files_not_duplicate(
        self, db_session, tmp_path, test_data_dir
    ):
        svc = make_service(db_session, tmp_path)
        r1 = svc.ingest(test_data_dir / "orders_valid.csv")
        r2 = svc.ingest(test_data_dir / "customers_valid.csv")
        assert r1.success
        assert r2.success
        assert r2.is_duplicate is False


# ─────────────────────────────────────────────────────────────────────────────
# Error paths
# ─────────────────────────────────────────────────────────────────────────────

class TestIngestionErrors:

    def test_missing_file_returns_failure(self, db_session, tmp_path):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(Path("/nonexistent/path/orders.csv"))
        assert result.success is False
        assert result.error_code is not None

    def test_unsupported_extension_rejected(self, db_session, tmp_path, tmp_path_factory):
        svc = make_service(db_session, tmp_path)
        bad_file = tmp_path / "data.json"
        bad_file.write_bytes(b'{"key": "value"}')
        result = svc.ingest(bad_file)
        assert result.success is False
        assert "INVALID_FILE_TYPE" in (result.error_code or "")

    def test_empty_file_rejected(self, db_session, tmp_path):
        svc = make_service(db_session, tmp_path)
        empty = tmp_path / "empty.csv"
        empty.write_bytes(b"")
        result = svc.ingest(empty)
        assert result.success is False

    def test_oversized_file_rejected(self, db_session, tmp_path):
        tiny_detector = FileTypeDetector(
            allowed_extensions=["csv"],
            max_size_bytes=10,  # 10 bytes max
        )
        svc = IngestionService(
            session=db_session,
            file_store=RawFileStore(tmp_path / "raw"),
            detector=tiny_detector,
        )
        big_file = tmp_path / "orders_big.csv"
        big_file.write_bytes(b"order_id,total\nORD-001,100.00\n")
        result = svc.ingest(big_file)
        assert result.success is False
        assert result.error_code == "FILE_TOO_LARGE"

    def test_unknown_dataset_type_rejected(self, db_session, tmp_path, tmp_path_factory):
        svc = make_service(db_session, tmp_path)
        f = tmp_path / "completely_unknown.csv"
        f.write_text("col_a,col_b,col_c\nval1,val2,val3\n", encoding="utf-8")
        result = svc.ingest(f)
        assert result.success is False
        assert result.error_code == "UNKNOWN_DATASET_TYPE"

    def test_invalid_explicit_type_rejected(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(
            test_data_dir / "orders_valid.csv",
            explicit_dataset_type="invalid_type_xyz",
        )
        assert result.success is False

    def test_result_never_raises(self, db_session, tmp_path):
        """IngestionService must never propagate exceptions to the caller."""
        svc = make_service(db_session, tmp_path)
        # Pass a directory (not a file) — should not raise
        result = svc.ingest(tmp_path)
        assert isinstance(result, IngestionResult)
        assert result.success is False


# ─────────────────────────────────────────────────────────────────────────────
# Metadata accuracy
# ─────────────────────────────────────────────────────────────────────────────

class TestMetadataAccuracy:

    def test_metadata_file_size_correct(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        src = test_data_dir / "orders_valid.csv"
        result = svc.ingest(src)
        assert result.file_metadata.file_size_bytes == src.stat().st_size

    def test_metadata_encoding_detected(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "orders_valid.csv")
        assert result.file_metadata.encoding is not None

    def test_metadata_delimiter_detected(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "orders_valid.csv")
        assert result.file_metadata.delimiter == ","

    def test_metadata_row_counts_correct(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(test_data_dir / "orders_valid.csv")
        assert result.file_metadata.row_count_data == 5
        # raw includes header row
        assert result.file_metadata.row_count_raw == 6

    def test_metadata_original_filename_preserved(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(
            test_data_dir / "orders_valid.csv",
            original_filename="my_orders_upload.csv",
        )
        assert result.file_metadata.original_filename == "my_orders_upload.csv"

    def test_metadata_source_type_recorded(self, db_session, tmp_path, test_data_dir):
        svc = make_service(db_session, tmp_path)
        result = svc.ingest(
            test_data_dir / "orders_valid.csv",
            source_type="directory_watch",
        )
        assert result.file_metadata.source_type == "directory_watch"
