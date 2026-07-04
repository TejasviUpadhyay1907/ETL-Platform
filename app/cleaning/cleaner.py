"""
CleaningEngine — top-level orchestrator for the data cleaning stage.

Receives a ValidationResult (from Validation Engine) and produces a
CleaningResult that is fully compatible with the already-implemented
TransformationEngine.

Pipeline:
  ValidationResult
    ↓ extract valid_df + warning_df
    ↓ CleaningRegistry.build_for_dataset()  — load cleaners from YAML
    ↓ CleaningExecutor.execute()             — run all cleaners in order
    ↓ CleaningActionLogger.build_metrics()   — aggregate statistics
    ↓ CleaningReport                         — full lineage audit trail
    ↓ CleaningActionLogger.persist()         — DB write (optional)
    ↓ CleaningResult                         — handed to TransformationEngine

TransformationEngine usage (unchanged contract):
    engine = TransformationEngine(session=db)
    transform_result = engine.transform(
        cleaned_df=cleaning_result.cleaned_df,
        dataset_type=cleaning_result.dataset_type,
        pipeline_run_id=cleaning_result.pipeline_run_id,
    )
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.cleaning.action_logger import CleaningActionLogger
from app.cleaning.cleaning_executor import CleaningExecutor
from app.cleaning.cleaning_registry import CleaningRegistry
from app.cleaning.models import CleaningReport, CleaningResult
from app.logging.logger import get_logger
from app.validation.models import ValidationResult

logger = get_logger(__name__)


class CleaningEngine:
    """
    Orchestrates the complete cleaning pipeline for a validated dataset.

    Stateless between calls — safe to reuse across multiple datasets.
    """

    def __init__(
        self,
        session: Session | None = None,
        dry_run: bool = False,
    ) -> None:
        """
        Args:
            session: SQLAlchemy session for DB persistence (optional).
            dry_run: If True, compute all changes but do NOT apply them.
                     The CleaningResult.cleaned_df will equal the input df.
        """
        self._session = session
        self._dry_run = dry_run
        self._executor = CleaningExecutor()
        self._action_logger = CleaningActionLogger(session)

    # ------------------------------------------------------------------
    # Primary entry point — accepts ValidationResult
    # ------------------------------------------------------------------

    def clean(
        self,
        validation_result: ValidationResult,
        pipeline_run_id: str | None = None,
        original_filename: str = "",
    ) -> CleaningResult:
        """
        Clean a validated dataset and return a CleaningResult.

        Args:
            validation_result:  Output from the Validation Engine.
            pipeline_run_id:    Optional run ID for DB correlation.
            original_filename:  Source filename for audit trail.

        Returns:
            CleaningResult — always returned, never raises.
        """
        start = time.perf_counter()
        dataset_type = validation_result.dataset_type

        # Merge valid + warning rows — both proceed to cleaning
        input_df = pd.concat(
            [validation_result.valid_df, validation_result.warning_df],
            ignore_index=True,
        )

        logger.info(
            "Cleaning started",
            dataset_type=dataset_type,
            rows=len(input_df),
            filename=original_filename,
        )

        try:
            result = self._run_pipeline(
                input_df, dataset_type, pipeline_run_id, original_filename
            )
        except Exception as exc:
            duration = time.perf_counter() - start
            logger.error(
                "Cleaning failed unexpectedly",
                dataset_type=dataset_type,
                error=str(exc),
                exc_info=True,
            )
            return CleaningResult(
                cleaned_df=input_df.copy(),
                dataset_type=dataset_type,
                pipeline_run_id=pipeline_run_id,
                success=False,
                errors=[str(exc)],
                execution_time=duration,
                original_df=input_df.copy(),
            )

        result.execution_time = time.perf_counter() - start
        result.cleaning_report.duration_seconds = result.execution_time
        logger.info(
            "Cleaning complete",
            dataset_type=dataset_type,
            rows_in=len(input_df),
            rows_out=result.row_count,
            rows_dropped=result.rows_dropped,
            actions=result.total_actions,
            duration_ms=round(result.execution_time * 1000, 1),
        )
        return result

    # ------------------------------------------------------------------
    # Direct DataFrame entry point (for use without ValidationResult)
    # ------------------------------------------------------------------

    def clean_dataframe(
        self,
        df: pd.DataFrame,
        dataset_type: str,
        pipeline_run_id: str | None = None,
        original_filename: str = "",
    ) -> CleaningResult:
        """
        Clean a DataFrame directly without a ValidationResult wrapper.

        Used by the API endpoint and tests that don't run validation first.

        Args:
            df:               DataFrame to clean.
            dataset_type:     Dataset type string.
            pipeline_run_id:  Optional run ID.
            original_filename: Source filename for audit.

        Returns:
            CleaningResult — always returned, never raises.
        """
        start = time.perf_counter()
        try:
            result = self._run_pipeline(df, dataset_type, pipeline_run_id, original_filename)
        except Exception as exc:
            duration = time.perf_counter() - start
            logger.error(f"CleaningEngine.clean_dataframe failed: {exc}", exc_info=True)
            return CleaningResult(
                cleaned_df=df.copy(),
                dataset_type=dataset_type,
                pipeline_run_id=pipeline_run_id,
                success=False,
                errors=[str(exc)],
                execution_time=duration,
                original_df=df.copy(),
            )
        result.execution_time = time.perf_counter() - start
        result.cleaning_report.duration_seconds = result.execution_time
        return result

    # ------------------------------------------------------------------
    # Dry-run / preview mode
    # ------------------------------------------------------------------

    def preview(
        self,
        df: pd.DataFrame,
        dataset_type: str,
    ) -> CleaningResult:
        """
        Compute all cleaning changes WITHOUT applying them to the output df.

        The returned CleaningResult.cleaned_df is a COPY of the original df.
        The cleaning_report contains all actions that WOULD be applied.
        Use CleaningResult.diff() to see before/after for every change.

        Args:
            df:           Input DataFrame.
            dataset_type: Dataset type string.

        Returns:
            CleaningResult with success=True and unchanged cleaned_df.
        """
        start = time.perf_counter()
        try:
            # Run the full pipeline to discover all actions
            preview_result = self._run_pipeline(df, dataset_type, None, "")
            # Override cleaned_df with original — this is dry-run mode
            preview_result.cleaned_df = df.copy()
            preview_result.cleaning_report.warnings.append(
                "DRY RUN: cleaned_df contains original data, not cleaned data"
            )
        except Exception as exc:
            logger.error(f"Preview failed: {exc}", exc_info=True)
            return CleaningResult(
                cleaned_df=df.copy(),
                dataset_type=dataset_type,
                success=False,
                errors=[str(exc)],
                original_df=df.copy(),
            )
        preview_result.execution_time = time.perf_counter() - start
        return preview_result

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _run_pipeline(
        self,
        input_df: pd.DataFrame,
        dataset_type: str,
        pipeline_run_id: str | None,
        original_filename: str,
    ) -> CleaningResult:
        original_snapshot = input_df.copy()

        # Step 1: Build registry from YAML config
        registry = CleaningRegistry.build_for_dataset(dataset_type)

        # Step 2: Execute all cleaners
        cleaned_df, actions, stats = self._executor.execute(
            df=input_df,
            registry=registry,
            dataset_type=dataset_type,
        )

        # Step 3: Build report
        report = CleaningReport(
            pipeline_run_id=pipeline_run_id,
            dataset_type=dataset_type,
            original_filename=original_filename,
            actions=actions,
            input_columns=list(input_df.columns),
            output_columns=list(cleaned_df.columns),
        )

        # Step 4: Compute metrics
        metrics = self._action_logger.build_metrics(
            report=report,
            input_rows=len(input_df),
            output_rows=len(cleaned_df),
        )
        report.metrics = metrics

        # Record dropped row indices (rows in input not in output by position)
        if len(cleaned_df) < len(input_df):
            report.dropped_row_indices = list(
                range(len(input_df) - len(cleaned_df))
            )

        # Step 5: Persist to DB
        if self._session is not None and not self._dry_run:
            self._action_logger.persist(report, pipeline_run_id)

        # Step 6: Identify rejected rows (rows that were dropped)
        rejected_df = original_snapshot.iloc[
            len(cleaned_df):
        ].copy() if len(cleaned_df) < len(input_df) else original_snapshot.iloc[0:0].copy()

        return CleaningResult(
            cleaned_df=cleaned_df,
            dataset_type=dataset_type,
            pipeline_run_id=pipeline_run_id,
            cleaning_report=report,
            cleaning_metrics=metrics,
            success=True,
            warnings=report.warnings,
            errors=report.errors,
            original_df=original_snapshot,
            rejected_df=rejected_df,
        )
