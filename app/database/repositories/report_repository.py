"""
ReportRepository — database operations for Report metadata.

Stores and retrieves metadata about generated report files. The actual
report files live on the file system; this table allows the API to list
and serve downloads without scanning the file system.
"""

import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database.models.pipeline.report import Report
from app.database.repositories.base_repository import BaseRepository
from app.logging.logger import get_logger

logger = get_logger(__name__)


class ReportRepository(BaseRepository[Report]):
    """
    Repository for Report metadata CRUD and query operations.

    Usage:
        repo = ReportRepository(session)
        report = repo.register_report(run_id=..., report_type="data_quality", ...)
    """

    model_class = Report

    def get_by_run(
        self,
        run_id: uuid.UUID,
        report_type: str | None = None,
    ) -> list[Report]:
        """
        Return all reports generated for a given pipeline run.

        Args:
            run_id: Pipeline run UUID.
            report_type: Optional filter by type (data_quality, business_summary).

        Returns:
            List of Report records, most recently generated first.
        """
        stmt = (
            select(Report)
            .where(Report.pipeline_run_id == run_id)
            .order_by(desc(Report.created_at))
        )
        if report_type:
            stmt = stmt.where(Report.report_type == report_type)
        return list(self.session.execute(stmt).scalars().all())

    def get_recent(self, limit: int = 20, include_archived: bool = False) -> list[Report]:
        """
        Return the most recently generated reports.

        Args:
            limit: Max records to return.
            include_archived: If False (default), exclude archived reports.

        Returns:
            List of recent Report records.
        """
        stmt = select(Report).order_by(desc(Report.created_at)).limit(limit)
        if not include_archived:
            stmt = stmt.where(Report.is_archived.is_(False))
        return list(self.session.execute(stmt).scalars().all())

    def get_by_dataset_type(
        self, dataset_type: str, limit: int = 50
    ) -> list[Report]:
        """Return reports filtered by dataset type."""
        stmt = (
            select(Report)
            .where(
                Report.dataset_type == dataset_type,
                Report.is_archived.is_(False),
            )
            .order_by(desc(Report.created_at))
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def register_report(
        self,
        pipeline_run_id: uuid.UUID,
        report_type: str,
        file_format: str,
        file_path: str,
        file_name: str,
        dataset_type: str | None = None,
        file_size_bytes: int | None = None,
    ) -> Report:
        """
        Create a new Report metadata record after a report file is generated.

        Called by the Reporting Module immediately after writing a report file.

        Args:
            pipeline_run_id: The run this report belongs to.
            report_type: 'data_quality' or 'business_summary'.
            file_format: 'csv' or 'xlsx'.
            file_path: Absolute path to the file on disk.
            file_name: Human-readable filename for download.
            dataset_type: Dataset type the report covers (optional).
            file_size_bytes: File size (optional, filled after write).

        Returns:
            The created Report record.
        """
        report = Report(
            pipeline_run_id=pipeline_run_id,
            report_type=report_type,
            file_format=file_format,
            file_path=file_path,
            file_name=file_name,
            dataset_type=dataset_type,
            file_size_bytes=file_size_bytes,
        )
        self.session.add(report)
        self.session.flush()

        logger.info(
            "Report registered",
            report_type=report_type,
            file_format=file_format,
            run_id=str(pipeline_run_id),
            file_name=file_name,
        )
        return report

    def mark_archived(self, report_id: uuid.UUID) -> None:
        """Mark a report as archived after moving its file to cold storage."""
        report = self.get_by_id(report_id)
        if report:
            report.is_archived = True
            self.session.flush()
            logger.debug(f"Report {report_id} marked as archived")
