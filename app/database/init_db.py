"""
Database initialization and migration management.

Handles the full lifecycle of database setup:
  1. Connection verification
  2. Alembic migration execution (schema creation/upgrade)
  3. Post-migration health check
  4. Graceful startup integration

This module is called during application startup (via the FastAPI lifespan
event) and also by the standalone migration script.

Design: Uses Alembic's programmatic API rather than subprocess calls so that
the same Python process that runs the app can also run migrations without
spawning a child process or requiring the CLI to be installed.
"""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.core.config import get_config
from app.core.exceptions import DatabaseConnectionException, DatabaseException
from app.logging.logger import get_logger

logger = get_logger(__name__)

# Project root — alembic.ini sits here
PROJECT_ROOT = Path(__file__).parent.parent.parent


def get_alembic_config() -> Config:
    """
    Build an Alembic Config object pointing at the project's alembic.ini.

    Overrides the sqlalchemy.url from the application configuration so that
    migrations always use the same database URL as the running application.
    """
    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    app_config = get_config()
    alembic_cfg.set_main_option("sqlalchemy.url", str(app_config.database_url))
    return alembic_cfg


def verify_connection() -> None:
    """
    Verify the database is reachable before attempting any migration.

    Raises:
        DatabaseConnectionException: If the database cannot be contacted.
    """
    from app.database.engine import get_session

    logger.info("Verifying database connection...")
    try:
        with get_session() as session:
            session.execute(text("SELECT 1"))
        logger.info("Database connection verified successfully")
    except Exception as exc:
        logger.error(f"Database connection failed: {exc}")
        raise DatabaseConnectionException(
            message=f"Cannot connect to database: {exc}"
        ) from exc


def get_current_revision() -> str | None:
    """
    Return the current Alembic revision applied to the database.

    Returns:
        The current revision string (e.g., 'a1b2c3d4e5f6'), or None if
        the alembic_version table doesn't exist yet (fresh database).
    """
    from app.database.engine import get_session

    try:
        with get_session() as session:
            result = session.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            )
            row = result.fetchone()
            return row[0] if row else None
    except Exception:
        return None  # Table doesn't exist on a fresh database


def run_migrations() -> None:
    """
    Run all pending Alembic migrations (equivalent to `alembic upgrade head`).

    Safe to call on a database that is already at head — Alembic is a no-op
    if no new migrations are pending.

    Raises:
        DatabaseException: If migration execution fails.
    """
    logger.info("Running database migrations...")
    try:
        alembic_cfg = get_alembic_config()
        command.upgrade(alembic_cfg, "head")
        current = get_current_revision()
        logger.info(f"Migrations complete. Current revision: {current}")
    except Exception as exc:
        logger.error(f"Migration failed: {exc}", exc_info=True)
        raise DatabaseException(
            message=f"Database migration failed: {exc}"
        ) from exc


def check_tables_exist() -> bool:
    """
    Verify that the expected application tables exist in the database.

    Used as a post-migration health check.

    Returns:
        True if all required tables are present, False otherwise.
    """
    from app.database.engine import get_engine

    required_tables = {
        "customers", "suppliers", "products", "inventory",
        "orders", "order_items", "payments",
        "pipeline_runs", "ingestion_events", "stage_results",
        "audit_logs", "validation_failures", "cleaning_logs",
        "data_quality_scores",
    }

    engine = get_engine()
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    missing = required_tables - existing_tables

    if missing:
        logger.warning(f"Missing database tables: {sorted(missing)}")
        return False

    logger.info(f"All {len(required_tables)} required tables verified")
    return True


def initialize_database(run_migrations_on_startup: bool = True) -> None:
    """
    Full database initialization sequence for application startup.

    Steps:
      1. Verify database connectivity
      2. Run pending migrations (if enabled)
      3. Verify all tables exist
      4. Log success

    Args:
        run_migrations_on_startup: If True, runs Alembic migrations.
            Set False in test environments where the schema is pre-created.

    Raises:
        DatabaseConnectionException: Database unreachable.
        DatabaseException: Migration or table verification failure.
    """
    logger.info("Initializing database...")

    # Step 1: Verify connectivity
    verify_connection()

    # Step 2: Run migrations
    if run_migrations_on_startup:
        run_migrations()
    else:
        logger.info("Skipping migrations (disabled for this environment)")

    # Step 3: Verify tables
    if not check_tables_exist():
        raise DatabaseException(
            message=(
                "Database initialization incomplete: one or more required tables "
                "are missing. Ensure migrations ran successfully."
            )
        )

    logger.info("Database initialization complete")


def create_all_tables() -> None:
    """
    Create all tables directly from SQLAlchemy metadata (bypasses Alembic).

    USE ONLY IN TESTS. Never use this in production — it skips Alembic's
    migration tracking and produces an unversioned schema.
    """
    from app.database.base import Base
    from app.database.engine import get_engine
    # Import all models to populate Base.metadata
    import app.database.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("All tables created directly from metadata (test mode)")


def drop_all_tables() -> None:
    """
    Drop all application tables.

    USE ONLY IN TESTS. Irreversible in production.
    """
    from app.database.base import Base
    from app.database.engine import get_engine
    import app.database.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(engine)
    logger.info("All tables dropped (test mode)")
