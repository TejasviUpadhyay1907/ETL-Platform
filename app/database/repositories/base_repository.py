"""
Abstract base repository providing generic CRUD operations.

All domain repositories inherit from this class to get consistent
Create, Read, Update, Delete patterns without code duplication.

Design: Repository Pattern — abstracts all database access behind a clean
interface. No SQL is written outside of repository classes. Business logic
never interacts with SQLAlchemy directly.
"""

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import DatabaseException, NotFoundException
from app.database.base import Base
from app.logging.logger import get_logger

logger = get_logger(__name__)

# Generic type variable for model classes
ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """
    Generic repository providing standard database operations.

    Type-parameterized with the ORM model class so all methods are
    type-safe and IDE-friendly.

    Usage:
        class OrderRepository(BaseRepository[Order]):
            model_class = Order
    """

    model_class: type[ModelT]  # Must be defined in subclasses

    def __init__(self, session: Session) -> None:
        """
        Initialize the repository with a database session.

        Args:
            session: SQLAlchemy session. Managed externally (via Depends or context manager).
        """
        self.session = session

    def get_by_id(self, record_id: uuid.UUID | str | int) -> ModelT | None:
        """
        Retrieve a single record by primary key.

        Args:
            record_id: Primary key value.

        Returns:
            Model instance if found, None otherwise.
        """
        try:
            return self.session.get(self.model_class, record_id)
        except Exception as e:
            logger.error(f"Error fetching {self.model_class.__name__} by id={record_id}: {e}")
            raise DatabaseException(
                message=f"Failed to retrieve {self.model_class.__name__}: {e}"
            ) from e

    def get_by_id_or_raise(self, record_id: uuid.UUID | str | int) -> ModelT:
        """
        Retrieve a single record by primary key, raising if not found.

        Args:
            record_id: Primary key value.

        Returns:
            Model instance.

        Raises:
            NotFoundException: If record with given ID does not exist.
        """
        record = self.get_by_id(record_id)
        if record is None:
            raise NotFoundException(
                message=f"{self.model_class.__name__} with id={record_id} not found",
            )
        return record

    def get_all(self, limit: int = 100, offset: int = 0) -> list[ModelT]:
        """
        Retrieve all records with pagination.

        Args:
            limit: Maximum records to return (default 100, max enforced by caller).
            offset: Number of records to skip.

        Returns:
            List of model instances.
        """
        try:
            stmt = select(self.model_class).offset(offset).limit(limit)
            result = self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error fetching all {self.model_class.__name__}: {e}")
            raise DatabaseException(
                message=f"Failed to list {self.model_class.__name__}: {e}"
            ) from e

    def count(self) -> int:
        """
        Count total records in the table.

        Returns:
            Total number of records.
        """
        from sqlalchemy import func  # Local import to avoid circular import

        try:
            stmt = select(func.count()).select_from(self.model_class)
            result = self.session.execute(stmt)
            return result.scalar_one()
        except Exception as e:
            logger.error(f"Error counting {self.model_class.__name__}: {e}")
            raise DatabaseException(
                message=f"Failed to count {self.model_class.__name__}: {e}"
            ) from e

    def create(self, **kwargs: Any) -> ModelT:
        """
        Create and persist a new record.

        Args:
            **kwargs: Column values for the new record.

        Returns:
            The created model instance with database-generated values populated.
        """
        try:
            instance = self.model_class(**kwargs)
            self.session.add(instance)
            self.session.flush()  # Flush to get generated values (e.g., UUID, timestamps)
            self.session.refresh(instance)
            logger.debug(f"Created {self.model_class.__name__}: {instance!r}")
            return instance
        except Exception as e:
            logger.error(f"Error creating {self.model_class.__name__}: {e}")
            raise DatabaseException(
                message=f"Failed to create {self.model_class.__name__}: {e}"
            ) from e

    def update(self, instance: ModelT, **kwargs: Any) -> ModelT:
        """
        Update an existing record with new values.

        Args:
            instance: Existing model instance to update.
            **kwargs: Column values to update.

        Returns:
            The updated model instance.
        """
        try:
            for key, value in kwargs.items():
                setattr(instance, key, value)
            self.session.flush()
            self.session.refresh(instance)
            logger.debug(f"Updated {self.model_class.__name__}: {instance!r}")
            return instance
        except Exception as e:
            logger.error(f"Error updating {self.model_class.__name__}: {e}")
            raise DatabaseException(
                message=f"Failed to update {self.model_class.__name__}: {e}"
            ) from e

    def delete(self, instance: ModelT) -> None:
        """
        Physically delete a record.

        Prefer soft_delete() for audit trail preservation.
        Only use hard delete for temporary/staging records.

        Args:
            instance: Model instance to delete.
        """
        try:
            self.session.delete(instance)
            self.session.flush()
            logger.debug(f"Deleted {self.model_class.__name__}: {instance!r}")
        except Exception as e:
            logger.error(f"Error deleting {self.model_class.__name__}: {e}")
            raise DatabaseException(
                message=f"Failed to delete {self.model_class.__name__}: {e}"
            ) from e

    def exists(self, record_id: uuid.UUID | str | int) -> bool:
        """
        Check if a record with the given ID exists.

        Args:
            record_id: Primary key value.

        Returns:
            True if record exists, False otherwise.
        """
        return self.get_by_id(record_id) is not None
