"""
TransformationEngine — top-level orchestrator for the transformation stage.

Receives a cleaned DataFrame (from the Cleaning Engine or directly) and
returns a TransformationResult containing the analytics-ready DataFrame.

Pipeline:
  cleaned_df
    ↓ TransformationRegistry.build_for_dataset()  — load transformers from YAML
    ↓ TransformationExecutor.execute()             — run all transformers
    ↓ Build TransformationReport with lineage
    ↓ TransformationRepository.persist()           — DB write (optional)
    ↓ TransformationResult                         — returned to pipeline engine

CRITICAL: The original cleaned_df is copied before transformation begins.
The TransformationEngine NEVER loads data into the database.
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.logging.logger import get_logger
from app.transformation.models import (
    TransformationAction,
    TransformationReport,
    TransformationResult,
)
from app.transformation.transformation_executor import TransformationExecutor, _build_metrics
from app.transformation.transformer_registry import TransformationRegistry

logger = get_logger(__name__)


class TransformationEngine:
    """
    Orchestrates the complete transformation pipeline for a cleaned DataFrame.

    Stateless between calls — safe to reuse across multiple datasets.
    """

    def __init__(
        self,
        session: Session | None = None,
        extra_lookups: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self._session = session
        self._extra_lookups = extra_lookups or {}
        self._executor = TransformationExecutor()

    def transform(
        self,
        cleaned_df: pd.DataFrame,
        dataset_type: str,
        original_filename: str = "",
        pipeline_run_id: str | None = None,
    ) -> TransformationResult:
        """
        Transform a cleaned DataFrame into an analytics-ready dataset.

        Args:
            cleaned_df:       The cleaned DataFrame from the Cleaning Engine.
                              COPIED before any transformation — never modified.
            dataset_type:     Dataset type string (orders, customers, etc.)
            original_filename: Source filename for audit trail.
            pipeline_run_id:  Optional pipeline run ID for DB correlation.

        Returns:
            TransformationResult — always returned, never raises.
        """
        start = time.perf_counter()
        logger.info(
            "Transformation started",
            dataset_type=dataset_type,
            rows=len(cleaned_df),
            columns=len(cleaned_df.columns),
        )
        try:
            result = self._run_pipeline(
                cleaned_df, dataset_type, original_filename, pipeline_run_id
            )
        except Exception as exc:
            duration = time.perf_counter() - start
            logger.error(
                "Transformation failed unexpectedly",
                dataset_type=dataset_type,
                error=str(exc),
                exc_info=True,
            )
            return TransformationResult(
                success=False,
                dataset_type=dataset_type,
                error_message=str(exc),
                error_code="TRANSFORMATION_UNEXPECTED_ERROR",
                duration_seconds=duration,
            )

        result.duration_seconds = time.perf_counter() - start
        result.report.duration_seconds = result.duration_seconds
        logger.info(
            "Transformation complete",
            dataset_type=dataset_type,
            output_rows=result.row_count,
            output_cols=result.column_count,
            added_cols=len(result.report.added_columns),
            duration_ms=round(result.duration_seconds * 1000, 1),
        )
        return result

    def _run_pipeline(
        self,
        cleaned_df: pd.DataFrame,
        dataset_type: str,
        original_filename: str,
        pipeline_run_id: str | None,
    ) -> TransformationResult:
        input_df = cleaned_df.copy()   # defensive copy

        # Step 1: Build registry from YAML config
        registry = TransformationRegistry.build_for_dataset(
            dataset_type=dataset_type,
            extra_lookups=self._extra_lookups,
        )

        # Step 2: Execute all transformers
        output_df, actions, stats = self._executor.execute(
            df=input_df,
            registry=registry,
            dataset_type=dataset_type,
        )

        # Step 3: Build metrics and report
        metrics = _build_metrics(input_df, output_df, actions, stats)

        input_cols  = list(input_df.columns)
        output_cols = list(output_df.columns)
        added_cols  = [c for c in output_cols if c not in set(input_cols)]
        renamed = {
            a.source_columns[0]: a.column_name
            for a in actions
            if a.transformation_type == "rename" and a.source_columns
        }

        report = TransformationReport(
            pipeline_run_id=pipeline_run_id,
            dataset_type=dataset_type,
            original_filename=original_filename,
            actions=actions,
            metrics=metrics,
            input_columns=input_cols,
            output_columns=output_cols,
            added_columns=added_cols,
            renamed_columns=renamed,
        )

        # Step 4: Persist to DB
        if self._session is not None:
            self._persist(report, pipeline_run_id)

        return TransformationResult(
            success=True,
            dataset_type=dataset_type,
            transformed_df=output_df,
            report=report,
        )

    def _persist(self, report: TransformationReport, pipeline_run_id: str | None) -> None:
        """Write transformation summary to audit log."""
        try:
            if pipeline_run_id is None:
                return
            import uuid
            from app.database.repositories.audit_log_repository import AuditLogRepository
            repo = AuditLogRepository(self._session)
            repo.log_event(
                event_type="STAGE_COMPLETED",
                message=(
                    f"Transformation complete: {report.dataset_type}, "
                    f"actions={len(report.actions)}, "
                    f"new_cols={len(report.added_columns)}"
                ),
                run_id=uuid.UUID(pipeline_run_id),
                stage="transformation",
                context_data=report.to_summary_dict(),
            )
            self._session.flush()
        except Exception as exc:
            logger.error(f"Failed to persist transformation results: {exc}", exc_info=True)
