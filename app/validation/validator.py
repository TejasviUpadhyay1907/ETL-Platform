"""
ValidationEngine — top-level orchestrator for the validation stage.

Receives a Dataset from the Ingestion Engine and returns a ValidationResult.
Never modifies the Dataset — it only reads and analyzes.

Pipeline:
  Dataset
    ↓ RuleRegistry.build_for_dataset()   — load all rules from config
    ↓ ValidationExecutor.execute()        — run all rules, collect violations
    ↓ ValidationAnnotator.annotate()      — partition into valid/rejected/warning
    ↓ QualityScoreCalculator.calculate()  — compute 6-dimensional score
    ↓ Build ValidationReport
    ↓ ValidationRepository.persist()      — store to database (if session provided)
    ↓ ValidationResult
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_config
from app.ingestion.models import Dataset
from app.logging.logger import get_logger
from app.validation.annotator import ValidationAnnotator
from app.validation.models import (
    QualityScore,
    Severity,
    ValidationReport,
    ValidationResult,
)
from app.validation.quality_scorer import QualityScoreCalculator
from app.validation.rule_engine import ValidationExecutor
from app.validation.rule_registry import RuleRegistry

logger = get_logger(__name__)


class ValidationEngine:
    """
    Orchestrates the complete validation pipeline for a single Dataset.

    Stateless: create a new instance per validation run or reuse across
    multiple datasets (the engine carries no per-dataset state).
    """

    def __init__(
        self,
        session: Session | None = None,
        quality_warning_threshold: float | None = None,
        quality_failure_threshold: float | None = None,
        references: dict[str, set[str]] | None = None,
    ) -> None:
        """
        Args:
            session:                   SQLAlchemy session for persisting results.
                                       If None, results are not persisted.
            quality_warning_threshold: Score below this triggers a WARNING.
                                       Loaded from config if None.
            quality_failure_threshold: Score below this causes passed_threshold=False.
                                       Loaded from config if None.
            references:                {fk_column: reference_value_set} for
                                       referential integrity checks.
        """
        config = get_config()
        self._session = session
        self._warn_threshold = quality_warning_threshold or float(
            config.quality_score_warning_threshold
        )
        self._fail_threshold = quality_failure_threshold or float(
            config.quality_score_failure_threshold
        )
        self._references = references or {}
        self._executor = ValidationExecutor()
        self._annotator = ValidationAnnotator()
        self._scorer = QualityScoreCalculator()

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------

    def validate(
        self,
        dataset: Dataset,
        pipeline_run_id: str | None = None,
    ) -> ValidationResult:
        """
        Validate a Dataset and return a complete ValidationResult.

        This method NEVER modifies the dataset's DataFrame.

        Args:
            dataset:         Dataset from the Ingestion Engine.
            pipeline_run_id: Optional pipeline run ID for DB correlation.

        Returns:
            ValidationResult — always returned, never raises.
        """
        start = time.perf_counter()
        dataset_type = dataset.dataset_type or "unknown"

        logger.info(
            "Validation started",
            dataset_type=dataset_type,
            rows=dataset.row_count,
            columns=dataset.column_count,
            filename=dataset.metadata.original_filename,
        )

        try:
            result = self._run_validation_pipeline(dataset, pipeline_run_id)
        except Exception as exc:
            duration = time.perf_counter() - start
            logger.error(
                "Validation failed with unhandled exception",
                dataset_type=dataset_type,
                error=str(exc),
                exc_info=True,
            )
            return ValidationResult(
                success=False,
                dataset_type=dataset_type,
                error_message=str(exc),
                error_code="VALIDATION_UNEXPECTED_ERROR",
                duration_seconds=duration,
            )

        result.duration_seconds = time.perf_counter() - start
        logger.info(
            "Validation complete",
            dataset_type=dataset_type,
            quality_score=result.quality_score,
            grade=result.letter_grade,
            valid=result.valid_count,
            rejected=result.rejected_count,
            duration_ms=round(result.duration_seconds * 1000, 1),
        )
        return result

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _run_validation_pipeline(
        self,
        dataset: Dataset,
        pipeline_run_id: str | None,
    ) -> ValidationResult:
        dataset_type = dataset.dataset_type or "unknown"
        df = dataset.dataframe  # NEVER reassigned — read-only

        # Step 1: Build rule registry from YAML config
        registry = RuleRegistry.build_for_dataset(
            dataset_type=dataset_type,
            references=self._references,
        )

        # Step 2: Execute all rules
        violations, stats, column_profiles = self._executor.execute(
            df=df,
            registry=registry,
            dataset_type=dataset_type,
        )

        # Step 3: Partition rows into valid/rejected/warning
        valid_df, rejected_df, warning_df, invalid_idx, warning_idx = (
            self._annotator.annotate(df, violations)
        )

        # Step 4: Compute quality score
        quality_score = self._scorer.calculate(
            df=df,
            violations=violations,
            invalid_indices=invalid_idx,
            warning_indices=warning_idx,
            total_rules_executed=stats.rules_executed,
        )

        # Step 5: Build ValidationReport
        report = ValidationReport(
            pipeline_run_id=pipeline_run_id,
            ingestion_event_id=dataset.ingestion_event_id,
            dataset_type=dataset_type,
            original_filename=dataset.metadata.original_filename,
            violations=violations,
            column_profiles=column_profiles,
            quality_score=quality_score,
            invalid_row_indices=invalid_idx,
            warning_row_indices=warning_idx,
        )

        # Extract schema-level findings
        from app.validation.models import RuleViolation
        for v in violations:
            if v.rule_category == "schema":
                if "missing" in v.message.lower() and v.field_name:
                    if v.field_name not in report.missing_columns:
                        report.missing_columns.append(v.field_name)
                elif "unexpected" in v.message.lower() and v.field_name:
                    if v.field_name not in report.unexpected_columns:
                        report.unexpected_columns.append(v.field_name)
                elif "duplicate column" in v.message.lower() and v.field_name:
                    if v.field_name not in report.duplicate_columns:
                        report.duplicate_columns.append(v.field_name)

        # Step 6: Persist to database (if session available)
        if self._session is not None:
            self._persist(report, quality_score, pipeline_run_id)

        passed = quality_score.overall_score >= self._fail_threshold

        return ValidationResult(
            success=True,
            dataset_type=dataset_type,
            valid_df=valid_df,
            rejected_df=rejected_df,
            warning_df=warning_df,
            report=report,
            quality_score=quality_score.overall_score,
            letter_grade=quality_score.letter_grade,
            passed_threshold=passed,
        )

    def _persist(
        self,
        report: ValidationReport,
        quality_score: QualityScore,
        pipeline_run_id: str | None,
    ) -> None:
        """Persist quality score and violation summaries to the database."""
        try:
            from app.validation.validation_repository import ValidationRepository
            repo = ValidationRepository(self._session)
            repo.persist(
                report=report,
                quality_score=quality_score,
                pipeline_run_id=pipeline_run_id,
                warn_threshold=self._warn_threshold,
                fail_threshold=self._fail_threshold,
            )
        except Exception as exc:
            logger.error(f"Failed to persist validation results: {exc}", exc_info=True)
