"""
Alembic migration environment configuration.

This file is executed by Alembic for both online and offline migration modes.

CRITICAL: Every ORM model module MUST be imported below for autogenerate
to detect schema changes. The import populates Base.metadata.

Add new model imports to the "Model imports" section when creating new tables.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure project root is on sys.path so `app.*` imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# Alembic config (values from alembic.ini)
# ---------------------------------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Override DB URL from application config (single source of truth)
# ---------------------------------------------------------------------------
from app.core.config import get_config  # noqa: E402

app_config = get_config()
config.set_main_option("sqlalchemy.url", str(app_config.database_url))

# ---------------------------------------------------------------------------
# Model imports — ALL models MUST be imported here for autogenerate
# ---------------------------------------------------------------------------
from app.database.base import Base  # noqa: E402

# Operational models
from app.database.models.operational.customers import Customer  # noqa: F401
from app.database.models.operational.suppliers import Supplier  # noqa: F401
from app.database.models.operational.products import Product  # noqa: F401
from app.database.models.operational.inventory import Inventory  # noqa: F401
from app.database.models.operational.orders import Order, OrderItem  # noqa: F401
from app.database.models.operational.payments import Payment  # noqa: F401

# Pipeline metadata models
from app.database.models.pipeline.pipeline_run import PipelineRun  # noqa: F401
from app.database.models.pipeline.ingestion_event import IngestionEvent  # noqa: F401
from app.database.models.pipeline.report import Report  # noqa: F401
from app.database.models.pipeline.stage_result import StageResult  # noqa: F401

# Audit and quality models
from app.database.models.audit.audit_log import AuditLog  # noqa: F401
from app.database.models.audit.validation_failure import ValidationFailure  # noqa: F401
from app.database.models.audit.cleaning_log import CleaningLog  # noqa: F401
from app.database.models.audit.quality_score import DataQualityScore  # noqa: F401

# Target metadata for autogenerate
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """
    Offline mode: generate SQL script without a live DB connection.

    Run with: alembic upgrade head --sql
    Useful for reviewing migration SQL before applying to production.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_schemas=True,
        render_as_batch=False,  # PostgreSQL supports DDL in transactions natively
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Online mode: connect to DB and apply migrations directly.

    Standard mode for: alembic upgrade head
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No connection reuse during migrations
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
