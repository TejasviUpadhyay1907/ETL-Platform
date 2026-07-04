"""
Unit tests for IngestionTracker and FileReceiver.

Uses the in-memory SQLite db_session fixture.
Tests verify:
- create_event() writes to DB and returns event_id
- check_duplicate() detects known hashes
- mark_processed() updates event status
- mark_rejected() sets rejection reason
- mark_duplicate() sets duplicate status
- should_reject_duplicate() returns correct bool per policy
- FileReceiver.receive_upload() delegates to IngestionService
- FileReceiver.receive_file_path() delegates to IngestionService
- BatchFileReceiver.receive_many_paths() returns one result per file
- BatchFileReceiver.receive_many_uploads() handles multiple files
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.ingestion.ingestion_tracker import DuplicatePolicy, IngestionTracker
from app.ingestion.models import (
    FileMetadata,
    IngestionResult,
    IngestionStatus,
)


# ─────────────────────────────────────────────────────────────────────────────
# IngestionTracker
# ─────────────────────────────────────────────────────────────────────────────

class TestIngestionTracker:

    def _make_metadata(self, ingestion_id: str = "test-id-001") -> FileMetadata:
        return FileMetadata(
            ingestion_id=ingestion_id,
            original_filename="orders_test.csv",
            stored_filename="orders_test.csv",
            file_path=Path("/data/raw/orders/orders_test.csv"),
            file_extension="csv",
            file_size_bytes=1024,
            file_hash="a" * 64,
            dataset_type="orders",
            encoding="utf-8",
            delimiter=",",
            row_count_raw=6,
            row_count_data=5,
        )

    def test_create_event_returns_event_id(self, db_session):
        tracker = IngestionTracker(db_session, DuplicatePolicy.REJECT)
        meta = self._make_metadata()
        event_id = tracker.create_event(meta)
        assert event_id is not None
        assert len(event_id) == 36  # UUID string

    def test_create_event_persists_to_db(self, db_session):
        tracker = IngestionTracker(db_session, DuplicatePolicy.REJECT)
        meta = self._make_metadata()
        event_id = tracker.create_event(meta)

        # Verify it's in DB by reading back
        import uuid
        from app.database.repositories.ingestion_event_repository import IngestionEventRepository
        repo = IngestionEventRepository(db_session)
        event = repo.get_by_id(uuid.UUID(event_id))
        assert event is not None
        assert event.original_filename == "orders_test.csv"
        assert event.dataset_type == "orders"

    def test_check_duplicate_no_match(self, db_session):
        tracker = IngestionTracker(db_session, DuplicatePolicy.REJECT)
        is_dup, existing_id = tracker.check_duplicate("b" * 64)
        assert is_dup is False
        assert existing_id is None

    def test_check_duplicate_match(self, db_session):
        tracker = IngestionTracker(db_session, DuplicatePolicy.REJECT)
        meta = self._make_metadata()
        meta.file_hash = "c" * 64
        event_id = tracker.create_event(meta)
        # Mark as processed so duplicate check finds it
        tracker.mark_processed(event_id, row_count_raw=6, row_count_data=5)
        db_session.commit()

        is_dup, existing_id = tracker.check_duplicate("c" * 64)
        assert is_dup is True
        assert existing_id == event_id

    def test_mark_processed_updates_status(self, db_session):
        tracker = IngestionTracker(db_session, DuplicatePolicy.REJECT)
        meta = self._make_metadata()
        event_id = tracker.create_event(meta)
        tracker.mark_processed(event_id, row_count_raw=6, row_count_data=5)
        db_session.flush()

        import uuid
        from app.database.repositories.ingestion_event_repository import IngestionEventRepository
        repo = IngestionEventRepository(db_session)
        event = repo.get_by_id(uuid.UUID(event_id))
        assert event.status == IngestionStatus.PROCESSED
        assert event.row_count_data == 5

    def test_mark_rejected_sets_reason(self, db_session):
        tracker = IngestionTracker(db_session, DuplicatePolicy.REJECT)
        meta = self._make_metadata()
        event_id = tracker.create_event(meta)
        tracker.mark_rejected(event_id, "File is too large")
        db_session.flush()

        import uuid
        from app.database.repositories.ingestion_event_repository import IngestionEventRepository
        repo = IngestionEventRepository(db_session)
        event = repo.get_by_id(uuid.UUID(event_id))
        assert event.status == IngestionStatus.REJECTED
        assert "too large" in event.rejection_reason

    def test_mark_duplicate(self, db_session):
        tracker = IngestionTracker(db_session, DuplicatePolicy.REJECT)
        meta = self._make_metadata()
        event_id = tracker.create_event(meta)
        tracker.mark_duplicate(event_id, original_event_id="orig-001")
        db_session.flush()

        import uuid
        from app.database.repositories.ingestion_event_repository import IngestionEventRepository
        repo = IngestionEventRepository(db_session)
        event = repo.get_by_id(uuid.UUID(event_id))
        assert event.status == IngestionStatus.DUPLICATE

    def test_should_reject_duplicate_true(self, db_session):
        tracker = IngestionTracker(db_session, DuplicatePolicy.REJECT)
        assert tracker.should_reject_duplicate() is True

    def test_should_reject_duplicate_false(self, db_session):
        tracker = IngestionTracker(db_session, DuplicatePolicy.REPROCESS)
        assert tracker.should_reject_duplicate() is False

    def test_create_multiple_events_different_ids(self, db_session):
        tracker = IngestionTracker(db_session, DuplicatePolicy.REJECT)
        m1 = self._make_metadata("id-001")
        m2 = self._make_metadata("id-002")
        m1.file_hash = "d" * 64
        m2.file_hash = "e" * 64

        id1 = tracker.create_event(m1)
        id2 = tracker.create_event(m2)
        assert id1 != id2

    def test_mark_processing(self, db_session):
        tracker = IngestionTracker(db_session, DuplicatePolicy.REJECT)
        meta = self._make_metadata()
        event_id = tracker.create_event(meta)
        tracker.mark_processing(event_id)
        db_session.flush()

        import uuid
        from app.database.repositories.ingestion_event_repository import IngestionEventRepository
        repo = IngestionEventRepository(db_session)
        event = repo.get_by_id(uuid.UUID(event_id))
        assert event.status == IngestionStatus.PROCESSING


# ─────────────────────────────────────────────────────────────────────────────
# FileReceiver
# ─────────────────────────────────────────────────────────────────────────────

class TestFileReceiver:
    """Tests FileReceiver using real IngestionService with SQLite."""

    def test_receive_upload_success(self, db_session, tmp_path, test_data_dir):
        from app.ingestion.file_receiver import FileReceiver
        from app.ingestion.raw_file_store import RawFileStore
        from app.ingestion.ingestion_service import IngestionService

        svc = IngestionService(session=db_session, file_store=RawFileStore(tmp_path / "raw"))
        receiver = FileReceiver.__new__(FileReceiver)
        receiver._session = db_session
        receiver._service = svc

        content = (test_data_dir / "orders_valid.csv").read_bytes()
        result = receiver.receive_upload(
            file_bytes=content,
            original_filename="orders_valid.csv",
            uploaded_by="test-key",
            source_ip="10.0.0.1",
        )
        assert result.success is True
        assert result.file_metadata.uploaded_by == "test-key"
        assert result.file_metadata.source_ip == "10.0.0.1"

    def test_receive_file_path_success(self, db_session, tmp_path, test_data_dir):
        from app.ingestion.file_receiver import FileReceiver
        from app.ingestion.raw_file_store import RawFileStore
        from app.ingestion.ingestion_service import IngestionService

        svc = IngestionService(session=db_session, file_store=RawFileStore(tmp_path / "raw"))
        receiver = FileReceiver.__new__(FileReceiver)
        receiver._session = db_session
        receiver._service = svc

        result = receiver.receive_file_path(
            file_path=test_data_dir / "customers_valid.csv",
            source_type="directory_watch",
        )
        assert result.success is True
        assert result.file_metadata.source_type == "directory_watch"

    def test_receive_upload_failure_returns_result(self, db_session, tmp_path):
        from app.ingestion.file_receiver import FileReceiver
        from app.ingestion.raw_file_store import RawFileStore
        from app.ingestion.ingestion_service import IngestionService

        svc = IngestionService(session=db_session, file_store=RawFileStore(tmp_path / "raw"))
        receiver = FileReceiver.__new__(FileReceiver)
        receiver._session = db_session
        receiver._service = svc

        result = receiver.receive_upload(
            file_bytes=b"",
            original_filename="empty.csv",
        )
        assert result.success is False


class TestBatchFileReceiver:

    def test_receive_many_paths(self, db_session, tmp_path, test_data_dir):
        from app.ingestion.file_receiver import BatchFileReceiver
        from app.ingestion.raw_file_store import RawFileStore
        from app.ingestion.ingestion_service import IngestionService
        from app.ingestion.file_receiver import FileReceiver

        svc = IngestionService(session=db_session, file_store=RawFileStore(tmp_path / "raw"))
        inner_receiver = FileReceiver.__new__(FileReceiver)
        inner_receiver._session = db_session
        inner_receiver._service = svc

        batch = BatchFileReceiver.__new__(BatchFileReceiver)
        batch._session = db_session
        batch._receiver = inner_receiver

        paths = [
            test_data_dir / "orders_valid.csv",
            test_data_dir / "customers_valid.csv",
        ]
        results = batch.receive_many_paths(paths)
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_receive_many_continues_on_failure(self, db_session, tmp_path, test_data_dir):
        from app.ingestion.file_receiver import BatchFileReceiver
        from app.ingestion.raw_file_store import RawFileStore
        from app.ingestion.ingestion_service import IngestionService
        from app.ingestion.file_receiver import FileReceiver

        svc = IngestionService(session=db_session, file_store=RawFileStore(tmp_path / "raw"))
        inner_receiver = FileReceiver.__new__(FileReceiver)
        inner_receiver._session = db_session
        inner_receiver._service = svc

        batch = BatchFileReceiver.__new__(BatchFileReceiver)
        batch._session = db_session
        batch._receiver = inner_receiver

        paths = [
            test_data_dir / "orders_valid.csv",
            tmp_path / "nonexistent.csv",  # will fail
            test_data_dir / "customers_valid.csv",
        ]
        results = batch.receive_many_paths(paths)
        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True

    def test_receive_many_uploads(self, db_session, tmp_path, test_data_dir):
        from app.ingestion.file_receiver import BatchFileReceiver
        from app.ingestion.raw_file_store import RawFileStore
        from app.ingestion.ingestion_service import IngestionService
        from app.ingestion.file_receiver import FileReceiver

        svc = IngestionService(session=db_session, file_store=RawFileStore(tmp_path / "raw"))
        inner_receiver = FileReceiver.__new__(FileReceiver)
        inner_receiver._session = db_session
        inner_receiver._service = svc

        batch = BatchFileReceiver.__new__(BatchFileReceiver)
        batch._session = db_session
        batch._receiver = inner_receiver

        files = [
            ((test_data_dir / "orders_valid.csv").read_bytes(), "orders_valid.csv"),
            ((test_data_dir / "products_valid.csv").read_bytes(), "products_valid.csv"),
        ]
        results = batch.receive_many_uploads(files, uploaded_by="batch-key")
        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is True
