"""
Tests for ValidationRepository — DB persistence of validation results.
Uses in-memory SQLite.
"""

import uuid
from decimal import Decimal

import pytest

from app.validation.models import (
    QualityScore, RuleViolation, ValidationReport, Severity
)
from app.validation.validation_repository import ValidationRepository


def _make_report(has_errors: bool = False) -> ValidationReport:
    qs = QualityScore(
        completeness=90, validity=85, consistency=88,
        uniqueness=95, integrity=100, timeliness=100,
        total_records=100, valid_records=85, invalid_records=15,
        warning_records=5,
    )
    qs.compute_overall()
    report = ValidationReport(
        dataset_type="orders",
        original_filename="orders_test.csv",
        quality_score=qs,
    )
    if has_errors:
        report.violations = [
            RuleViolation("ORD_001", "business", "error", "order_id", 0, None,
                          "Not null", "order_id is null", "Provide a value"),
            RuleViolation("ORD_002", "business", "warning", "total", 1, "-10",
                          "> 0", "negative total", "Fix total"),
        ]
        report.invalid_row_indices = {0}
        report.warning_row_indices = {1}
    return report


class TestValidationRepository:

    def test_persist_creates_quality_score(self, db_session):
        run_id = str(uuid.uuid4())
        report = _make_report()
        repo = ValidationRepository(db_session)
        repo.persist(report, report.quality_score, run_id)
        db_session.flush()

        from sqlalchemy import select
        from app.database.models.audit.quality_score import DataQualityScore
        scores = list(db_session.execute(select(DataQualityScore)).scalars().all())
        assert len(scores) >= 1
        assert scores[-1].dataset_type == "orders"

    def test_persist_with_violations(self, db_session):
        run_id = str(uuid.uuid4())
        report = _make_report(has_errors=True)
        repo = ValidationRepository(db_session)
        repo.persist(report, report.quality_score, run_id)
        db_session.flush()

        from sqlalchemy import select
        from app.database.models.audit.validation_failure import ValidationFailure
        failures = list(db_session.execute(
            select(ValidationFailure).where(
                ValidationFailure.pipeline_run_id == uuid.UUID(run_id)
            )
        ).scalars().all())
        assert len(failures) >= 1
        assert failures[0].rule_code == "ORD_001"

    def test_persist_none_run_id_safe(self, db_session):
        """Persisting with no pipeline_run_id should not raise."""
        report = _make_report()
        repo = ValidationRepository(db_session)
        # Should not raise
        repo.persist(report, report.quality_score, pipeline_run_id=None)

    def test_persist_logs_audit_event(self, db_session):
        run_id = str(uuid.uuid4())
        report = _make_report(has_errors=True)
        repo = ValidationRepository(db_session)
        repo.persist(report, report.quality_score, run_id)
        db_session.flush()

        from sqlalchemy import select
        from app.database.models.audit.audit_log import AuditLog
        logs = list(db_session.execute(
            select(AuditLog).where(AuditLog.run_id == uuid.UUID(run_id))
        ).scalars().all())
        assert len(logs) >= 1
        assert logs[0].event_type in ("VALIDATION_FAILURE", "STAGE_COMPLETED")

    def test_persist_idempotent_on_duplicate_run_id(self, db_session):
        """Calling persist twice for same run_id should not crash (upsert)."""
        run_id = str(uuid.uuid4())
        report = _make_report()
        repo = ValidationRepository(db_session)
        repo.persist(report, report.quality_score, run_id)
        db_session.flush()
        # Second call — should upsert, not duplicate
        repo.persist(report, report.quality_score, run_id)
        db_session.flush()

    def test_quality_score_values_correct(self, db_session):
        run_id = str(uuid.uuid4())
        report = _make_report()
        qs = report.quality_score
        qs.total_records = 200
        qs.valid_records = 180
        qs.invalid_records = 20
        repo = ValidationRepository(db_session)
        repo.persist(report, qs, run_id)
        db_session.flush()

        from sqlalchemy import select
        from app.database.models.audit.quality_score import DataQualityScore
        score_row = db_session.execute(
            select(DataQualityScore).where(
                DataQualityScore.pipeline_run_id == uuid.UUID(run_id)
            )
        ).scalar_one_or_none()
        assert score_row is not None
        assert score_row.total_records == 200
        assert score_row.valid_records == 180
