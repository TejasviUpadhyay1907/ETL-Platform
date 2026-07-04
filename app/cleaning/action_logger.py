"""
CleaningActionLogger — aggregates CleaningActions into metrics and persists to DB.

Responsibilities:
  - Count actions by type and update CleaningMetrics
  - Bulk-insert CleaningLog records into the database
  - Write audit event to audit_log table
  - Identify which rows were modified (for metrics)
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.cleaning.models import CleaningAction, CleaningMetrics, CleaningReport
from app.logging.logger import get_logger

logger = get_logger(__name__)


class CleaningActionLogger:
    """Aggregates cleaning actions into metrics and persists audit records."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def build_metrics(
        self,
        report: CleaningReport,
        input_rows: int,
        output_rows: int,
    ) -> CleaningMetrics:
        """
        Compute CleaningMetrics by aggregating all actions in the report.

        Args:
            report:      Completed CleaningReport.
            input_rows:  Row count before cleaning.
            output_rows: Row count after cleaning.

        Returns:
            Populated CleaningMetrics.
        """
        m = CleaningMetrics(
            total_rows_input=input_rows,
            total_rows_output=output_rows,
            rows_dropped=input_rows - output_rows,
            total_actions=len(report.actions),
        )

        modified_rows: set[int] = set()

        for action in report.actions:
            if action.row_index is not None:
                modified_rows.add(action.row_index)

            at = action.action_type
            if at == "fill_null":
                m.nulls_filled += 1
                m.cells_modified += 1
            elif at == "drop_row":
                m.nulls_dropped += 1
            elif at == "remove_duplicate":
                m.duplicates_removed += 1
            elif at in ("trim", "case_normalize"):
                m.strings_trimmed += 1
                m.cells_modified += 1
            elif at == "remove_control_chars":
                m.control_chars_removed += 1
                m.cells_modified += 1
            elif at == "strip_currency":
                m.currencies_cleaned += 1
                m.cells_modified += 1
            elif at == "parse_date":
                m.dates_standardized += 1
                m.cells_modified += 1
            elif at == "map_category":
                m.categories_mapped += 1
                m.cells_modified += 1
            elif at == "clip_outlier":
                m.outliers_clipped += 1
                m.cells_modified += 1
            else:
                m.cells_modified += 1

        m.rows_modified = len(modified_rows)
        m.compute_cleaning_pct()
        return m

    def persist(
        self,
        report: CleaningReport,
        pipeline_run_id: str | None,
    ) -> None:
        """Write cleaning summary to audit_log and cleaning_log tables."""
        if self._session is None:
            return

        # Map new engine action_types to DB enum values (cleaning_logs CHECK constraint)
        _ACTION_MAP = {
            "fill_null":            "null_filled",
            "drop_row":             "null_dropped",
            "remove_duplicate":     "duplicate_removed",
            "trim":                 "string_trimmed",
            "case_normalize":       "case_normalized",
            "remove_control_chars": "string_trimmed",
            "strip_currency":       "numeric_cleaned",
            "clip_outlier":         "numeric_cleaned",
            "parse_date":           "date_standardized",
            "map_category":         "case_normalized",
            "regex_applied":        "regex_applied",
        }

        try:
            run_uuid = uuid.UUID(pipeline_run_id) if pipeline_run_id else None

            from app.database.repositories.audit_log_repository import AuditLogRepository
            audit_repo = AuditLogRepository(self._session)
            audit_repo.log_event(
                event_type="STAGE_COMPLETED",
                message=(
                    f"Cleaning complete: {report.dataset_type}, "
                    f"actions={len(report.actions)}, "
                    f"rows_dropped={report.metrics.rows_dropped}"
                ),
                run_id=run_uuid,
                stage="cleaning",
                context_data=report.to_summary_dict(),
            )

            # Bulk-insert up to 2000 cleaning log records (mapped to DB enum values)
            log_records = [
                {
                    "id": uuid.uuid4(),
                    "pipeline_run_id": run_uuid,
                    "row_index": a.row_index if a.row_index is not None else -1,
                    "dataset_type": report.dataset_type,
                    "action_type": _ACTION_MAP.get(a.action_type, "string_trimmed"),
                    "field_name": a.field_name or "unknown",
                    "original_value": str(a.original_value)[:1000] if a.original_value is not None else None,
                    "cleaned_value":  str(a.cleaned_value)[:1000]  if a.cleaned_value  is not None else None,
                }
                for a in report.actions[:2000]
                if run_uuid is not None
            ]
            if log_records:
                audit_repo.bulk_insert_cleaning_logs(log_records)

            self._session.flush()
            logger.debug(
                "Cleaning results persisted",
                run_id=pipeline_run_id,
                actions=len(report.actions),
            )
        except Exception as exc:
            logger.error(f"Failed to persist cleaning results: {exc}", exc_info=True)
