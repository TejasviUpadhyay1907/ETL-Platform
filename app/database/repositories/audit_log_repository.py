"""
AuditLogRepository — INSERT-only operations for the audit log.

The audit log is immutable. This repository only supports create and read.
No update or delete methods are provided by design.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database.models.audit.audit_log import AuditLog
from app.database.models.audit.cleaning_log import CleaningLog
from app.database.models.audit.quality_score import DataQualityScore
from app.database.models.audit.validation_failure import ValidationFailure
from app.database.repositories.base_repository import BaseRepository
from app.logging.logger import get_logger

logger = get_logger(__name__)


class AuditLogRepository(BaseRepository[AuditLog]):
    """
    Insert-only repository for the audit log.

    Never exposes update() or delete() — audit records are permanent.
    """

    model_class = AuditLog

    def log_event(
        self,
        event_type: str,
        message: str,
        severity: str = "INFO",
        run_id: uuid.UUID | None = None,
        stage: str | None = None,
        user_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        context_data: dict[str, Any] | None = None,
        request_id: str | None = None,
        source_ip: str | None = None,
    ) -> AuditLog:
        """Create and persist an audit log entry."""
        entry = AuditLog(
            event_type=event_type,
            message=message,
            severity=severity,
            run_id=run_id,
            stage=stage,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            context_data=context_data,
            request_id=request_id,
            source_ip=source_ip,
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def get_by_run(
        self, run_id: uuid.UUID, limit: int = 500
    ) -> list[AuditLog]:
        """Return all audit events for a pipeline run, most recent first."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.run_id == run_id)
            .order_by(AuditLog.created_at)
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_by_event_type(
        self,
        event_type: str,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        """Return audit events of a specific type within an optional time window."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.event_type == event_type)
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
        )
        if from_dt:
            stmt = stmt.where(AuditLog.created_at >= from_dt)
        if to_dt:
            stmt = stmt.where(AuditLog.created_at <= to_dt)
        return list(self.session.execute(stmt).scalars().all())

    # ------------------------------------------------------------------
    # Validation failure operations
    # ------------------------------------------------------------------

    def bulk_insert_validation_failures(
        self, failures: list[dict[str, Any]]
    ) -> int:
        """Bulk insert validation failure records using individual adds for SQLite compat."""
        if not failures:
            return 0
        import uuid as _uuid
        for record in failures:
            # Ensure id is a UUID object
            if "id" in record and isinstance(record["id"], str):
                record["id"] = _uuid.UUID(record["id"])
            if "pipeline_run_id" in record and isinstance(record["pipeline_run_id"], str):
                record["pipeline_run_id"] = _uuid.UUID(record["pipeline_run_id"])
            obj = ValidationFailure(**record)
            self.session.add(obj)
        self.session.flush()
        return len(failures)

    # ------------------------------------------------------------------
    # Cleaning log operations
    # ------------------------------------------------------------------

    def bulk_insert_cleaning_logs(self, logs: list[dict[str, Any]]) -> int:
        """Bulk insert cleaning action log records."""
        if not logs:
            return 0
        self.session.bulk_insert_mappings(CleaningLog, logs)  # type: ignore[arg-type]
        self.session.flush()
        return len(logs)

    # ------------------------------------------------------------------
    # Quality score operations
    # ------------------------------------------------------------------

    def upsert_quality_score(self, score_data: dict[str, Any]) -> DataQualityScore:
        """
        Upsert the quality score for a pipeline run.

        Uses PostgreSQL-specific ON CONFLICT when running on PostgreSQL,
        falls back to a read-then-write pattern for SQLite (used in tests).
        """
        import sqlalchemy

        dialect_name = self.session.bind.dialect.name if self.session.bind else "sqlite"

        if dialect_name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = (
                pg_insert(DataQualityScore)
                .values(score_data)
                .on_conflict_do_update(
                    constraint="uq_quality_scores_run_id",
                    set_={
                        k: v
                        for k, v in score_data.items()
                        if k not in ("id", "pipeline_run_id", "created_at")
                    },
                )
                .returning(DataQualityScore)
            )
            result = self.session.execute(stmt)
            self.session.flush()
            return result.scalar_one()
        else:
            # SQLite fallback: check existing then insert or update
            existing = self.session.execute(
                select(DataQualityScore).where(
                    DataQualityScore.pipeline_run_id == score_data["pipeline_run_id"]
                )
            ).scalar_one_or_none()

            if existing is None:
                obj = DataQualityScore(**score_data)
                self.session.add(obj)
                self.session.flush()
                return obj
            else:
                for k, v in score_data.items():
                    if k not in ("id", "pipeline_run_id", "created_at"):
                        setattr(existing, k, v)
                self.session.flush()
                return existing

    def get_quality_scores(
        self,
        dataset_type: str | None = None,
        limit: int = 30,
    ) -> list[DataQualityScore]:
        """Return recent quality scores for trend analysis."""
        stmt = (
            select(DataQualityScore)
            .order_by(desc(DataQualityScore.created_at))
            .limit(limit)
        )
        if dataset_type:
            stmt = stmt.where(DataQualityScore.dataset_type == dataset_type)
        return list(self.session.execute(stmt).scalars().all())
