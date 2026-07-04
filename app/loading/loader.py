"""
WarehouseLoader — the production warehouse loading engine.

Replaces the placeholder in StageExecutor.run_load().

Contract (called by StageExecutor and Phase 9 in general):
    loader = WarehouseLoader(session=db)
    result = loader.load(
        transformed_df=df,
        dataset_type="orders",
        pipeline_run_id="abc-123",
    )

Pipeline:
  1. Check idempotency — has this pipeline_run_id already been loaded?
  2. Resolve strategy from LoadRegistry
  3. Execute strategy (upsert / bulk_insert / append / replace / incremental)
  4. Build LoadReport with full audit trail
  5. Persist audit record to audit_log
  6. Update pipeline_runs.loaded_records
  7. Return LoadResult
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.loading.load_registry import LoadRegistry, get_load_registry
from app.loading.models import (
    LoadReport, LoadResult, LoadStrategyType, LoadStrategy
)
from app.logging.logger import get_logger

logger = get_logger(__name__)


class WarehouseLoader:
    """
    Production warehouse loading engine.

    Stateless between calls — safe to reuse across multiple datasets.
    """

    def __init__(
        self,
        session: Session,
        registry: LoadRegistry | None = None,
        strategy_override: str | None = None,
        batch_size_override: int | None = None,
        check_idempotency: bool = True,
    ) -> None:
        self._session = session
        self._registry = registry or get_load_registry()
        self._strategy_override = strategy_override
        self._batch_size_override = batch_size_override
        self._check_idempotency = check_idempotency

    # ------------------------------------------------------------------
    # Primary entry point (Phase 9 contract)
    # ------------------------------------------------------------------

    def load(
        self,
        transformed_df: pd.DataFrame,
        dataset_type: str,
        pipeline_run_id: str | None = None,
    ) -> LoadResult:
        """
        Load a transformed DataFrame into the warehouse.

        Args:
            transformed_df:  Analytics-ready DataFrame from TransformationEngine.
            dataset_type:    Target dataset type (orders, customers, etc.)
            pipeline_run_id: Used for idempotency checking and audit trail.

        Returns:
            LoadResult — always returned, never raises.
        """
        start = time.perf_counter()
        logger.info(
            "Warehouse load started",
            dataset_type=dataset_type,
            rows=len(transformed_df),
            pipeline_run_id=pipeline_run_id,
        )

        try:
            result = self._run_load(transformed_df, dataset_type, pipeline_run_id)
        except Exception as exc:
            duration = time.perf_counter() - start
            logger.error(
                "Warehouse load failed unexpectedly",
                dataset_type=dataset_type,
                error=str(exc),
                exc_info=True,
            )
            return LoadResult(
                success=False,
                dataset_type=dataset_type,
                error_message=str(exc),
                error_code="LOAD_UNEXPECTED_ERROR",
                duration_seconds=duration,
            )

        result.duration_seconds = time.perf_counter() - start
        result.report.duration_seconds = result.duration_seconds

        logger.info(
            "Warehouse load complete",
            dataset_type=dataset_type,
            rows_loaded=result.rows_loaded,
            rows_inserted=result.rows_inserted,
            rows_updated=result.rows_updated,
            rows_failed=result.rows_failed,
            strategy=result.strategy_used,
            duration_ms=round(result.duration_seconds * 1000, 1),
        )
        return result

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _run_load(
        self,
        df: pd.DataFrame,
        dataset_type: str,
        pipeline_run_id: str | None,
    ) -> LoadResult:

        # Step 1: Idempotency check
        if self._check_idempotency and pipeline_run_id:
            if self._already_loaded(pipeline_run_id, dataset_type):
                logger.info(
                    "Idempotency check: pipeline run already loaded — skipping",
                    pipeline_run_id=pipeline_run_id,
                    dataset_type=dataset_type,
                )
                return LoadResult(
                    success=True,
                    dataset_type=dataset_type,
                    rows_skipped=len(df),
                    idempotent_skip=True,
                )

        # Step 2: Resolve strategy and target table
        strategy, target_table = self._registry.get_strategy(
            session=self._session,
            dataset_type=dataset_type,
            strategy_override=self._strategy_override,
            batch_size_override=self._batch_size_override,
        )

        # Step 3: Execute
        metrics, batch_results = strategy.execute(
            df=df,
            target_table=target_table,
            dataset_type=dataset_type,
            pipeline_run_id=pipeline_run_id,
        )

        # Step 4: Build report
        success = metrics.rows_failed == 0 or (
            strategy._config.allow_partial and metrics.rows_inserted > 0
        )
        report = LoadReport(
            pipeline_run_id=pipeline_run_id,
            dataset_type=dataset_type,
            target_table=target_table,
            strategy_used=strategy.strategy_name,
            metrics=metrics,
            batch_results=batch_results,
            success=success,
            idempotency_key=pipeline_run_id,
        )

        # Step 5: Persist audit record
        self._persist_audit(report, pipeline_run_id)

        # Step 6: Update pipeline_runs.loaded_records
        if pipeline_run_id:
            self._update_pipeline_run(pipeline_run_id, metrics.rows_loaded)

        return LoadResult(
            success=success,
            dataset_type=dataset_type,
            rows_inserted=metrics.rows_inserted,
            rows_updated=metrics.rows_updated,
            rows_skipped=metrics.rows_skipped,
            rows_failed=metrics.rows_failed,
            target_table=target_table,
            strategy_used=strategy.strategy_name,
            report=report,
        )

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    def _already_loaded(self, pipeline_run_id: str, dataset_type: str) -> bool:
        """
        Check if this pipeline run has already been loaded.

        Looks for a RECORD_LOADED audit event for this run_id.
        """
        try:
            from app.database.models.audit.audit_log import AuditLog
            from sqlalchemy import select

            run_uuid = uuid.UUID(pipeline_run_id)
            stmt = (
                select(AuditLog)
                .where(
                    AuditLog.run_id == run_uuid,
                    AuditLog.event_type == "RECORD_LOADED",
                    AuditLog.stage == "load",
                )
                .limit(1)
            )
            existing = self._session.execute(stmt).scalar_one_or_none()
            return existing is not None
        except Exception as exc:
            logger.warning(f"Idempotency check failed (will proceed): {exc}")
            return False

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _persist_audit(self, report: LoadReport, pipeline_run_id: str | None) -> None:
        """Write load summary to audit_log."""
        try:
            from app.database.models.audit.audit_log import AuditLog
            run_uuid = uuid.UUID(pipeline_run_id) if pipeline_run_id else None
            log = AuditLog(
                event_type="RECORD_LOADED",
                severity="INFO" if report.success else "ERROR",
                run_id=run_uuid,
                stage="load",
                message=(
                    f"Load {'succeeded' if report.success else 'failed'}: "
                    f"{report.dataset_type} → {report.target_table}, "
                    f"strategy={report.strategy_used}, "
                    f"rows={report.metrics.rows_loaded}"
                ),
                context_data=report.to_summary_dict(),
            )
            self._session.add(log)
            self._session.flush()
        except Exception as exc:
            logger.warning(f"Failed to persist load audit record (non-fatal): {exc}")
            try:
                self._session.rollback()
            except Exception:
                pass

    def _update_pipeline_run(self, pipeline_run_id: str, loaded_count: int) -> None:
        """Update pipeline_runs.loaded_records."""
        try:
            from app.database.models.pipeline.pipeline_run import PipelineRun
            from sqlalchemy import select
            run_uuid = uuid.UUID(pipeline_run_id)
            run = self._session.execute(
                select(PipelineRun).where(PipelineRun.id == run_uuid)
            ).scalar_one_or_none()
            if run:
                run.loaded_records = loaded_count
                self._session.flush()
        except Exception as exc:
            logger.warning(f"Failed to update pipeline run loaded_records (non-fatal): {exc}")
            try:
                self._session.rollback()
            except Exception:
                pass
