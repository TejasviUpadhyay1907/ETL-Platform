"""
Transaction management for multi-step database operations.

Provides a context manager that wraps multiple database operations in a
single atomic transaction. If any operation fails, all changes are rolled back.

This ensures data integrity for pipeline loading operations where partial
writes would corrupt the data state.
"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import DatabaseException
from app.logging.logger import get_logger

logger = get_logger(__name__)


class TransactionManager:
    """
    Manages explicit database transactions for multi-step operations.

    Designed for use in the Data Loader stage, where a complete set of
    records must either all be written or none at all.

    Usage:
        manager = TransactionManager(session)
        with manager.transaction() as tx:
            tx.add(record_1)
            tx.add(record_2)
            # Committed automatically on exit
            # Rolled back automatically on exception
    """

    def __init__(self, session: Session) -> None:
        """
        Initialize with an existing session.

        Args:
            session: SQLAlchemy session to manage transactions on.
        """
        self._session = session

    @contextmanager
    def transaction(self) -> Generator[Session, None, None]:
        """
        Context manager for an explicit database transaction.

        Begins a nested transaction (savepoint) if already inside a transaction,
        or a top-level transaction otherwise.

        Yields:
            The session object for use in the with block.

        Raises:
            DatabaseException: Wraps any exception that causes rollback.
        """
        try:
            yield self._session
            self._session.commit()
            logger.debug("Transaction committed successfully")

        except DatabaseException:
            # Re-raise our own exceptions without wrapping
            self._session.rollback()
            logger.error("Transaction rolled back due to database exception")
            raise

        except Exception as e:
            self._session.rollback()
            logger.error(f"Transaction rolled back due to unexpected error: {e}")
            raise DatabaseException(
                message=f"Transaction failed and was rolled back: {e}",
            ) from e


@contextmanager
def atomic(session: Session) -> Generator[Session, None, None]:
    """
    Convenience context manager for a single atomic block.

    Shorthand for TransactionManager(session).transaction().

    Usage:
        with atomic(session) as s:
            s.add(record)

    Args:
        session: SQLAlchemy session.

    Yields:
        Session for use in the with block.
    """
    manager = TransactionManager(session)
    with manager.transaction() as s:
        yield s


@contextmanager
def savepoint(session: Session, name: str | None = None) -> Generator[Any, None, None]:
    """
    Create a nested savepoint within a transaction.

    Useful for partial rollbacks — if a savepoint operation fails,
    only that segment is rolled back, not the outer transaction.

    Args:
        session: SQLAlchemy session.
        name: Optional savepoint name for debugging.

    Yields:
        Savepoint context.
    """
    with session.begin_nested() as sp:
        try:
            yield sp
            logger.debug(f"Savepoint {name or 'unnamed'} committed")
        except Exception as e:
            logger.warning(f"Savepoint {name or 'unnamed'} rolled back: {e}")
            raise
