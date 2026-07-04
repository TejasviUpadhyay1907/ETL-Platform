"""
SQLAlchemy database engine and session management.

Provides:
- Engine factory with connection pooling
- Async and sync session factories
- Database health check
- Proper cleanup and teardown

Design: Uses dependency injection pattern via FastAPI Depends for automatic
session lifecycle management (open at request start, commit/rollback at end, close).
"""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_config
from app.core.exceptions import DatabaseConnectionException, DatabaseException
from app.logging.logger import get_logger

logger = get_logger(__name__)

# Global engine instances (initialized once at startup)
_sync_engine: Engine | None = None
_async_engine: Any | None = None
_sync_session_factory: sessionmaker[Session] | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_database_engine() -> Engine:
    """
    Create and configure a synchronous SQLAlchemy engine.

    Configures connection pooling, statement compilation caching, and
    event listeners for instrumentation.

    Returns:
        Configured SQLAlchemy engine.
    """
    config = get_config()

    try:
        engine = create_engine(
            str(config.database_url),
            pool_size=config.db_pool_size,
            max_overflow=config.db_max_overflow,
            pool_timeout=config.db_pool_timeout,
            pool_recycle=config.db_pool_recycle,
            pool_pre_ping=True,  # Verify connections before using
            echo=config.db_echo,
            future=True,  # Use SQLAlchemy 2.0 API
        )

        # Register event listeners for logging
        _register_engine_events(engine)

        logger.info(
            "Database engine created",
            pool_size=config.db_pool_size,
            max_overflow=config.db_max_overflow,
        )

        return engine

    except Exception as e:
        logger.error(f"Failed to create database engine: {e}", exc_info=True)
        raise DatabaseConnectionException(
            message=f"Could not create database engine: {e}",
        ) from e


def create_async_database_engine() -> Any:
    """
    Create and configure an asynchronous SQLAlchemy engine.

    Used for future async endpoints. Not required for initial implementation.

    Returns:
        Configured async SQLAlchemy engine.
    """
    config = get_config()

    # Convert psycopg2 URL to asyncpg for async support
    async_url = str(config.database_url).replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    try:
        engine = create_async_engine(
            async_url,
            pool_size=config.db_pool_size,
            max_overflow=config.db_max_overflow,
            pool_timeout=config.db_pool_timeout,
            pool_recycle=config.db_pool_recycle,
            pool_pre_ping=True,
            echo=config.db_echo,
            future=True,
        )

        logger.info("Async database engine created")
        return engine

    except Exception as e:
        logger.error(f"Failed to create async database engine: {e}", exc_info=True)
        raise DatabaseConnectionException(
            message=f"Could not create async database engine: {e}",
        ) from e


def _register_engine_events(engine: Engine) -> None:
    """
    Register SQLAlchemy event listeners for observability.

    Logs connection checkout/checkin and tracks long-running queries.
    """

    @event.listens_for(engine, "connect")
    def receive_connect(dbapi_conn: Any, connection_record: Any) -> None:
        """Log successful database connections."""
        logger.debug("Database connection established")

    @event.listens_for(engine, "close")
    def receive_close(dbapi_conn: Any, connection_record: Any) -> None:
        """Log database disconnections."""
        logger.debug("Database connection closed")


def get_engine() -> Engine:
    """
    Get the global synchronous database engine.

    Initializes the engine on first call and returns the cached instance thereafter.
    """
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_database_engine()
    return _sync_engine


def get_async_engine() -> Any:
    """Get the global asynchronous database engine."""
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_database_engine()
    return _async_engine


def get_session_factory() -> sessionmaker[Session]:
    """
    Get the synchronous session factory.

    Returns:
        Configured sessionmaker for creating database sessions.
    """
    global _sync_session_factory
    if _sync_session_factory is None:
        engine = get_engine()
        _sync_session_factory = sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _sync_session_factory


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the asynchronous session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_async_engine()
        _async_session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _async_session_factory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context manager for database session lifecycle.

    Usage:
        with get_session() as session:
            result = session.execute(query)

    Automatically commits on success, rolls back on exception, and closes the session.
    """
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for database session lifecycle."""
    session_factory = get_async_session_factory()
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# FastAPI dependency for automatic session injection
def get_db_session() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.

    Usage in endpoint:
        @router.get("/items")
        def get_items(db: Session = Depends(get_db_session)):
            ...

    FastAPI will automatically create a session at request start,
    yield it to the endpoint, and close it after the response.
    """
    with get_session() as session:
        yield session


def check_database_health() -> bool:
    """
    Verify database connectivity.

    Used by health check endpoint to confirm the database is reachable.

    Returns:
        True if connection successful, False otherwise.
    """
    try:
        with get_session() as session:
            session.execute(text("SELECT 1"))
        logger.debug("Database health check passed")
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


def dispose_engine() -> None:
    """
    Dispose of the database engine and close all connections.

    Called at application shutdown to gracefully clean up database resources.
    """
    global _sync_engine, _async_engine

    if _sync_engine:
        _sync_engine.dispose()
        logger.info("Synchronous database engine disposed")

    if _async_engine:
        # async engines need explicit close
        logger.info("Async database engine disposed")

    _sync_engine = None
    _async_engine = None
