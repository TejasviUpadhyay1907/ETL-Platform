"""
Unit tests for ingestion domain models (Dataset, FileMetadata, IngestionResult).

Tests verify:
- FileMetadata.to_event_kwargs() produces correct DB-ready dict
- Dataset computed properties (row_count, is_empty, columns, etc.)
- IngestionResult success/failure flags
- DatasetSchema structure
"""

import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from app.ingestion.models import (
    Dataset,
    DatasetSchema,
    FileMetadata,
    IngestionResult,
    IngestionStatus,
)


class TestFileMetadata:

    def _make_metadata(self, **kwargs) -> FileMetadata:
        defaults = dict(
            ingestion_id=str(uuid.uuid4()),
            original_filename="orders_test.csv",
            stored_filename="orders_test.csv",
            file_path=Path("/data/raw/orders/2025-01-15/test/orders_test.csv"),
            file_extension="csv",
            file_size_bytes=1024,
            file_hash="a" * 64,
            dataset_type="orders",
            encoding="utf-8",
            delimiter=",",
            row_count_raw=6,
            row_count_data=5,
            column_count=6,
        )
        defaults.update(kwargs)
        return FileMetadata(**defaults)

    def test_to_event_kwargs_has_required_keys(self):
        m = self._make_metadata()
        kwargs = m.to_event_kwargs()
        required = {
            "original_filename", "stored_filename", "file_path",
            "file_extension", "file_size_bytes", "file_hash",
            "dataset_type", "source_type", "row_count_raw",
            "row_count_data", "status",
        }
        assert required.issubset(set(kwargs.keys()))

    def test_to_event_kwargs_status_is_received(self):
        m = self._make_metadata()
        assert m.to_event_kwargs()["status"] == IngestionStatus.RECEIVED

    def test_to_event_kwargs_file_path_is_string(self):
        m = self._make_metadata()
        val = m.to_event_kwargs()["file_path"]
        assert isinstance(val, str)

    def test_dataset_type_default_none(self):
        m = FileMetadata(
            original_filename="x.csv",
            stored_filename="x.csv",
            file_path=Path("/tmp/x.csv"),
            file_extension="csv",
            file_size_bytes=100,
        )
        assert m.dataset_type is None

    def test_to_event_kwargs_unknown_dataset_type(self):
        """When dataset_type is None, it defaults to 'unknown'."""
        m = FileMetadata(
            original_filename="x.csv",
            stored_filename="x.csv",
            file_path=Path("/tmp/x.csv"),
            file_extension="csv",
            file_size_bytes=100,
        )
        assert m.to_event_kwargs()["dataset_type"] == "unknown"


class TestDataset:

    def _make_dataset(self, rows: int = 5) -> Dataset:
        df = pd.DataFrame({
            "order_id": [f"ORD-{i:03d}" for i in range(rows)],
            "total": [str(i * 10.0) for i in range(rows)],
        })
        schema = DatasetSchema(
            column_names=list(df.columns),
            column_dtypes={"order_id": "object", "total": "object"},
            row_count=rows,
            column_count=2,
        )
        meta = FileMetadata(
            original_filename="orders.csv",
            stored_filename="orders.csv",
            file_path=Path("/data/raw/orders.csv"),
            file_extension="csv",
            file_size_bytes=256,
            dataset_type="orders",
        )
        return Dataset(metadata=meta, dataframe=df, schema=schema)

    def test_row_count_property(self):
        ds = self._make_dataset(rows=10)
        assert ds.row_count == 10

    def test_column_count_property(self):
        ds = self._make_dataset()
        assert ds.column_count == 2

    def test_columns_property(self):
        ds = self._make_dataset()
        assert "order_id" in ds.columns
        assert "total" in ds.columns

    def test_is_empty_false(self):
        ds = self._make_dataset(rows=3)
        assert ds.is_empty is False

    def test_is_empty_true(self):
        ds = self._make_dataset(rows=0)
        assert ds.is_empty is True

    def test_dataset_type_property(self):
        ds = self._make_dataset()
        assert ds.dataset_type == "orders"

    def test_head_returns_dataframe(self):
        ds = self._make_dataset(rows=10)
        head = ds.head(3)
        assert isinstance(head, pd.DataFrame)
        assert len(head) == 3

    def test_head_full_dataset_shorter(self):
        ds = self._make_dataset(rows=2)
        head = ds.head(10)
        assert len(head) == 2

    def test_repr_contains_dataset_type(self):
        ds = self._make_dataset()
        assert "orders" in repr(ds)

    def test_repr_contains_row_count(self):
        ds = self._make_dataset(rows=7)
        assert "7" in repr(ds)

    def test_processing_id_is_uuid(self):
        ds = self._make_dataset()
        assert len(ds.processing_id) == 36  # UUID4 string
        # Should not raise
        uuid.UUID(ds.processing_id)

    def test_read_at_is_datetime(self):
        ds = self._make_dataset()
        assert isinstance(ds.read_at, datetime)


class TestIngestionResult:

    def test_success_result(self):
        result = IngestionResult(success=True, status=IngestionStatus.PROCESSED)
        assert result.success is True
        assert result.is_duplicate is False
        assert result.error_message is None

    def test_failure_result(self):
        result = IngestionResult(
            success=False,
            status=IngestionStatus.REJECTED,
            error_message="File too large",
            error_code="FILE_TOO_LARGE",
        )
        assert result.success is False
        assert result.error_code == "FILE_TOO_LARGE"

    def test_duplicate_result(self):
        result = IngestionResult(
            success=False,
            status=IngestionStatus.DUPLICATE,
            is_duplicate=True,
            duplicate_of_event_id="orig-event-123",
        )
        assert result.is_duplicate is True
        assert result.duplicate_of_event_id == "orig-event-123"

    def test_repr_contains_status(self):
        result = IngestionResult(success=True, status="processed")
        assert "processed" in repr(result)


class TestDatasetSchema:

    def test_schema_creation(self):
        schema = DatasetSchema(
            column_names=["a", "b", "c"],
            column_dtypes={"a": "object", "b": "object", "c": "object"},
            row_count=100,
            column_count=3,
        )
        assert schema.row_count == 100
        assert schema.column_count == 3
        assert "a" in schema.column_names

    def test_default_has_header(self):
        schema = DatasetSchema()
        assert schema.has_header is True

    def test_empty_schema(self):
        schema = DatasetSchema()
        assert schema.row_count == 0
        assert schema.column_names == []
