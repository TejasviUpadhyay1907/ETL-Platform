"""Tests for CleaningActionLogger — metrics building and DB persistence."""
import uuid
import pandas as pd
import pytest

from app.cleaning.action_logger import CleaningActionLogger
from app.cleaning.models import CleaningAction, CleaningReport, CleaningMetrics


def _make_report(actions=None, dataset_type="orders"):
    r = CleaningReport(dataset_type=dataset_type, original_filename="test.csv")
    if actions:
        r.actions = actions
    return r


def _action(action_type, field="order_id", row_index=0, orig=None, cleaned="X"):
    return CleaningAction(
        rule_code="TEST_001", rule_category="test",
        field_name=field, row_index=row_index,
        original_value=orig, cleaned_value=cleaned,
        action_type=action_type, reason="test",
    )


class TestCleaningActionLoggerMetrics:

    def test_build_metrics_counts_nulls_filled(self):
        actions = [_action("fill_null", orig=None, cleaned="unknown")]
        report = _make_report(actions)
        logger = CleaningActionLogger(session=None)
        metrics = logger.build_metrics(report, input_rows=10, output_rows=10)
        assert metrics.nulls_filled == 1
        assert metrics.cells_modified == 1
        assert metrics.total_rows_input == 10

    def test_build_metrics_counts_duplicates_removed(self):
        actions = [_action("remove_duplicate", field=None)]
        report = _make_report(actions)
        logger = CleaningActionLogger(session=None)
        metrics = logger.build_metrics(report, input_rows=5, output_rows=4)
        assert metrics.duplicates_removed == 1
        assert metrics.rows_dropped == 1

    def test_build_metrics_counts_strings_trimmed(self):
        actions = [_action("trim"), _action("case_normalize")]
        report = _make_report(actions)
        logger = CleaningActionLogger(session=None)
        metrics = logger.build_metrics(report, input_rows=2, output_rows=2)
        assert metrics.strings_trimmed == 2
        assert metrics.cells_modified == 2

    def test_build_metrics_counts_dates(self):
        actions = [_action("parse_date"), _action("parse_date")]
        report = _make_report(actions)
        logger = CleaningActionLogger(session=None)
        metrics = logger.build_metrics(report, input_rows=5, output_rows=5)
        assert metrics.dates_standardized == 2

    def test_build_metrics_counts_categories(self):
        actions = [_action("map_category")]
        report = _make_report(actions)
        logger = CleaningActionLogger(session=None)
        metrics = logger.build_metrics(report, input_rows=3, output_rows=3)
        assert metrics.categories_mapped == 1

    def test_build_metrics_counts_outliers(self):
        actions = [_action("clip_outlier")]
        report = _make_report(actions)
        logger = CleaningActionLogger(session=None)
        metrics = logger.build_metrics(report, input_rows=4, output_rows=4)
        assert metrics.outliers_clipped == 1

    def test_build_metrics_computes_cleaning_pct(self):
        actions = [_action("fill_null", row_index=0), _action("trim", row_index=1)]
        report = _make_report(actions)
        logger = CleaningActionLogger(session=None)
        metrics = logger.build_metrics(report, input_rows=10, output_rows=10)
        assert metrics.rows_modified == 2
        assert metrics.cleaning_pct == 20.0

    def test_build_metrics_empty_actions(self):
        report = _make_report(actions=[])
        logger = CleaningActionLogger(session=None)
        metrics = logger.build_metrics(report, input_rows=5, output_rows=5)
        assert metrics.total_actions == 0
        assert metrics.rows_modified == 0
        assert metrics.cleaning_pct == 0.0

    def test_build_metrics_currencies_cleaned(self):
        actions = [_action("strip_currency", orig="$10.99", cleaned="10.99")]
        report = _make_report(actions)
        logger = CleaningActionLogger(session=None)
        metrics = logger.build_metrics(report, input_rows=3, output_rows=3)
        assert metrics.currencies_cleaned == 1

    def test_build_metrics_control_chars(self):
        actions = [_action("remove_control_chars", orig="a\x01b", cleaned="ab")]
        report = _make_report(actions)
        logger = CleaningActionLogger(session=None)
        metrics = logger.build_metrics(report, input_rows=2, output_rows=2)
        assert metrics.control_chars_removed == 1


class TestCleaningActionLoggerPersist:

    def test_persist_writes_audit_log(self, db_session):
        run_id = str(uuid.uuid4())
        report = _make_report()
        report.pipeline_run_id = run_id
        logger = CleaningActionLogger(session=db_session)
        logger.persist(report, pipeline_run_id=run_id)
        db_session.flush()

        from sqlalchemy import select
        from app.database.models.audit.audit_log import AuditLog
        logs = list(db_session.execute(
            select(AuditLog).where(AuditLog.run_id == uuid.UUID(run_id))
        ).scalars().all())
        assert len(logs) >= 1
        assert logs[0].stage == "cleaning"

    def test_persist_with_cleaning_actions(self, db_session):
        run_id = str(uuid.uuid4())
        actions = [
            _action("fill_null", field="order_id", row_index=0, orig=None, cleaned="MISSING"),
            _action("trim", field="status", row_index=1, orig="  active  ", cleaned="active"),
        ]
        report = _make_report(actions=actions)
        report.pipeline_run_id = run_id
        logger = CleaningActionLogger(session=db_session)
        logger.persist(report, pipeline_run_id=run_id)
        db_session.flush()

        from sqlalchemy import select
        from app.database.models.audit.cleaning_log import CleaningLog
        logs = list(db_session.execute(
            select(CleaningLog).where(CleaningLog.pipeline_run_id == uuid.UUID(run_id))
        ).scalars().all())
        assert len(logs) == 2

    def test_persist_none_session_silent(self):
        """No session → persist is a no-op, no exception."""
        report = _make_report()
        logger = CleaningActionLogger(session=None)
        # Should not raise
        logger.persist(report, pipeline_run_id=None)

    def test_persist_none_run_id_silent(self, db_session):
        """No run_id → persist is a no-op."""
        report = _make_report()
        logger = CleaningActionLogger(session=db_session)
        # Should not raise
        logger.persist(report, pipeline_run_id=None)
