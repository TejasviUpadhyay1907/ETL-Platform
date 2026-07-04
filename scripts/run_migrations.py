"""
Database migration runner.

Wraps Alembic upgrade to the head revision. This script is the standard
way to apply pending migrations in all environments.

Usage:
    python scripts/run_migrations.py                 # upgrade to head
    python scripts/run_migrations.py --revision abc  # upgrade to specific revision
    python scripts/run_migrations.py --downgrade -1  # downgrade one step
    python scripts/run_migrations.py --show          # show current revision

Also available via Alembic CLI directly:
    alembic upgrade head
    alembic current
    alembic history
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run database migrations")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--revision",
        default="head",
        help="Target revision (default: head)",
    )
    group.add_argument(
        "--downgrade",
        metavar="REV",
        help="Downgrade to revision (e.g., -1, base, or a revision ID)",
    )
    group.add_argument(
        "--show",
        action="store_true",
        help="Show current revision without running migrations",
    )

    args = parser.parse_args()

    from alembic import command
    from app.database.init_db import get_alembic_config
    from app.logging.logger import setup_logging, get_logger

    setup_logging()
    logger = get_logger(__name__)

    cfg = get_alembic_config()

    if args.show:
        print("Current Alembic revision:")
        command.current(cfg, verbose=True)
    elif args.downgrade:
        logger.warning(f"Downgrading database to revision: {args.downgrade}")
        command.downgrade(cfg, args.downgrade)
        print(f"Downgrade to '{args.downgrade}' complete.")
    else:
        logger.info(f"Upgrading database to revision: {args.revision}")
        command.upgrade(cfg, args.revision)
        print(f"Migration to '{args.revision}' complete.")


if __name__ == "__main__":
    main()
