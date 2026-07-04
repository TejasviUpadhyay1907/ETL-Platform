"""
ValidationRepository — persists validation results to the database.

Stores:
  - ValidationFailure records (one per rule violation with row context)
  - DataQualityScore record (aggregated score per pipeline run)
  - AuditLog event for the validation stage

Design: keeps all DB writes in one place so the ValidationEngine
remains infrastructure-free. Injected via dependency.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.logging.logger import get_logger
from app.validation.models import ValidationReport, QualityScore, Severity

logger = get_logger(__name__)


class ValidationRepository:
    """Writes validation results to the metadata and audit tables."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def persist(
        self,
        report: ValidationReport,
        quality_score: QualityScore,
        pipeline_run_id: str | None,
        warn_threshold: float = 80.0,
        fail_threshold: float = 50.0,
    ) -> None:
        """
        Persist the complete validation outcome to the database.

        Args:
            report:           Full ValidationReport.
            quality_score:    Computed QualityScore.
            pipeline_run_id:  UUID string of the pipeline run (may be None).
            warn_threshold:   Score below which a warning is triggered.
            fail_threshold:   Score below which a failure is triggered.
        """
        try:
            run_uuid = uuid.UUID(pipeline_run_id) if pipeline_run_id else None
            self._persist_quality_score(quality_score, report, run_uuid,
                                        warn_threshold, fail_threshold)
            self._persist_violations(report, run_uuid)
            self._persist_audit_event(report, quality_score, run_uuid)
            self._session.flush()
            logger.debug(
                "Validation results persisted",
                run_id=pipeline_run_id,
                violations=len(report.violations),
                score=quality_score.overall_score,
            )
        except Exception as exc:
            logger.error(f"Failed to persist validation results: {exc}", exc_info=True)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _persist_quality_score(
        self,
        qs: QualityScore,
        report: ValidationReport,
        run_uuid: uuid.UUID | None,
        warn_threshold: float,
        fail_threshold: float,
    ) -> None:
        if run_uuid is None:
            return
        from app.database.repositories.audit_log_repository import AuditLogRepository
        repo = AuditLogRepository(self._session)
        score_data = {
            "id": uuid.uuid4(),
            "pipeline_run_id": run_uuid,
            "dataset_type": report.dataset_type,
            "total_records": qs.total_records,
            "valid_records": qs.valid_records,
            "invalid_records": qs.invalid_records,
            "warning_records": qs.warning_records,
            "duplicate_records": 0,
            "loaded_records": 0,
            "quality_score": Decimal(str(round(qs.overall_score, 2))),
            "warning_threshold": Decimal(str(warn_threshold)),
            "failure_threshold": Decimal(str(fail_threshold)),
            "threshold_breached": qs.overall_score < fail_threshold,
            "threshold_warning": qs.overall_score < warn_threshold,
        }
        repo.upsert_quality_score(score_data)

    def _persist_violations(
        self,
        report: ValidationReport,
        run_uuid: uuid.UUID | None,
    ) -> None:
        """Bulk-insert the top 1000 error violations as ValidationFailure records."""
        if run_uuid is None or not report.violations:
            return

        from app.database.repositories.audit_log_repository import AuditLogRepository
        repo = AuditLogRepository(self._session)

        error_violations = [
            v for v in report.violations
            if v.severity == Severity.ERROR and v.row_index is not None
        ][:1000]

        if not error_violations:
            return

        failure_records = [
            {
                "id": uuid.uuid4(),
                "pipeline_run_id": run_uuid,
                "row_index": v.row_index,
                "dataset_type": report.dataset_type,
                "rule_code": v.rule_code,
                "rule_description": v.rule_description or v.expected,
                "field_name": v.field_name,
                "original_value": str(v.actual_value)[:1000] if v.actual_value is not None else None,
                "failure_message": v.message[:500],
                "severity": v.severity,
            }
            for v in error_violations
        ]
        repo.bulk_insert_validation_failures(failure_records)

    def _persist_audit_event(
        self,
        report: ValidationReport,
        qs: QualityScore,
        run_uuid: uuid.UUID | None,
    ) -> None:
        if run_uuid is None:
            return
        from app.database.repositories.audit_log_repository import AuditLogRepository
        repo = AuditLogRepository(self._session)
        event_type = "VALIDATION_FAILURE" if report.has_errors else "STAGE_COMPLETED"
        repo.log_event(
            event_type=event_type,
            message=(
                f"Validation complete: {report.dataset_type}, "
                f"score={qs.overall_score:.1f} ({qs.letter_grade}), "
                f"violations={report.violation_count}"
            ),
            run_id=run_uuid,
            stage="validation",
            context_data={
                "quality_score": qs.overall_score,
                "letter_grade": qs.letter_grade,
                "total_violations": report.violation_count,
                "error_violations": len(report.error_violations),
                "valid_records": qs.valid_records,
                "invalid_records": qs.invalid_records,
            },
        )
