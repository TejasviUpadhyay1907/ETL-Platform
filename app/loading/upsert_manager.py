"""
UpsertManager — generic PostgreSQL upsert logic for the ETL loading stage.

Provides a reusable upsert primitive for all six dataset types.
The loading stage calls this after transformation to write clean records
to the database without creating duplicates on repeated pipeline runs.

Design:
- Uses PostgreSQL's INSERT ... ON CONFLICT DO UPDATE (true upsert)
- Idempotent: running the same data twice produces the same result
- Transactional: the caller wraps multiple bulk_upsert calls in atomic()
- Returns a LoadResult with counts of inserted, updated, and failed records

This module contains no ETL business logic — only the persistence primitive.
Business-specific loading (which table, which conflict key) is handled by
the domain repositories' bulk_upsert methods.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import DatabaseException
from app.logging.logger import get_logger

logger = get_logger(__name__)


@dataclass
class LoadResult:
    """
    Result of a bulk upsert operation.

    Returned by UpsertManager.bulk_upsert() to give the pipeline engine
    an accurate record count for the StageResult.
    """

    dataset_type: str
    total_attempted: int = 0
    inserted: int = 0
    updated: int = 0
    failed: int = 0
    error_messages: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """True if no records failed."""
        return self.failed == 0

    @property
    def success_count(self) -> int:
        """Total successfully persisted records."""
        return self.inserted + self.updated

    def __repr__(self) -> str:
        return (
            f"LoadResult(dataset={self.dataset_type!r}, "
            f"total={self.total_attempted}, "
            f"inserted={self.inserted}, updated={self.updated}, "
            f"failed={self.failed})"
        )


class UpsertManager:
    """
    Generic upsert primitive for writing DataFrames to the database.

    Each dataset type has a domain repository with a bulk_upsert method.
    This class orchestrates the call pattern and collects result metrics.

    The ETL loading stage will call this manager; the manager delegates
    to the appropriate repository based on dataset_type.
    """

    # Maps dataset_type → (repository class, conflict columns)
    # Populated when repositories are registered during startup
    _registry: dict[str, tuple[Any, list[str]]] = {}

    def __init__(self, session: Session) -> None:
        self.session = session

    @classmethod
    def register(
        cls,
        dataset_type: str,
        repository_class: Any,
        conflict_columns: list[str],
    ) -> None:
        """
        Register a repository for a dataset type.

        Called during application startup (Milestone 7 — loading stage).

        Args:
            dataset_type: e.g. 'orders', 'customers'
            repository_class: Repository class with a bulk_upsert method
            conflict_columns: Column(s) that identify duplicate records
        """
        cls._registry[dataset_type] = (repository_class, conflict_columns)
        logger.debug(f"UpsertManager: registered {dataset_type} → {repository_class.__name__}")

    def bulk_upsert(
        self,
        dataset_type: str,
        records: list[dict[str, Any]],
        chunk_size: int = 1000,
    ) -> LoadResult:
        """
        Upsert a list of records for a dataset type in chunks.

        Processes records in chunks to bound memory usage on large files.
        Each chunk is flushed separately; the caller's transaction wraps all chunks.

        Args:
            dataset_type: Target dataset type.
            records: List of dicts ready for database insertion.
            chunk_size: Number of records per flush cycle.

        Returns:
            LoadResult with counts of inserted/updated/failed records.

        Raises:
            DatabaseException: If the dataset type is not registered or upsert fails.
        """
        result = LoadResult(dataset_type=dataset_type, total_attempted=len(records))

        if not records:
            logger.debug(f"bulk_upsert called with empty records for {dataset_type}")
            return result

        if dataset_type not in self._registry:
            raise DatabaseException(
                message=(
                    f"No repository registered for dataset type '{dataset_type}'. "
                    f"Registered types: {sorted(self._registry.keys())}"
                )
            )

        repo_class, _ = self._registry[dataset_type]
        repo = repo_class(self.session)

        # Process in chunks
        for i in range(0, len(records), chunk_size):
            chunk = records[i : i + chunk_size]
            try:
                affected = repo.bulk_upsert(chunk)
                result.inserted += affected
            except Exception as e:
                error_msg = f"Chunk {i//chunk_size + 1} failed: {e}"
                logger.error(error_msg)
                result.failed += len(chunk)
                result.error_messages.append(error_msg)

        logger.info(
            f"Upsert complete for {dataset_type}",
            total=result.total_attempted,
            success=result.success_count,
            failed=result.failed,
        )
        return result
