"""
Database Verification Script — ETL Platform v1.0.0
===================================================
Checks that the database is fully initialized and healthy.
Useful to run after setup or before starting the application.

Usage:
    python scripts/verify_database.py
    python scripts/verify_database.py --verbose
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Verify database setup")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    from app.logging.logger import setup_logging
    setup_logging()

    print("\nETL Platform — Database Verification")
    print("=" * 50)

    checks: list[tuple[str, bool, str]] = []

    # 1. Config
    try:
        from app.core.config import get_config
        cfg = get_config()
        db_url = str(cfg.database_url)
        checks.append(("Configuration loaded", True, f"APP_ENV={cfg.app_env}"))
    except Exception as e:
        checks.append(("Configuration loaded", False, str(e)))
        _print_checks(checks)
        sys.exit(1)

    # 2. DB connection
    try:
        from app.database.init_db import verify_connection
        verify_connection()
        checks.append(("PostgreSQL connectivity", True, "Connected"))
    except Exception as e:
        checks.append(("PostgreSQL connectivity", False, str(e)))
        _print_checks(checks)
        sys.exit(1)

    # 3. Migration revision
    try:
        from app.database.init_db import get_current_revision
        rev = get_current_revision()
        if rev:
            checks.append(("Alembic migrations", True, f"Revision: {rev}"))
        else:
            checks.append(("Alembic migrations", False, "No revision found — run: python scripts/setup_database.py"))
    except Exception as e:
        checks.append(("Alembic migrations", False, str(e)))

    # 4. Tables
    try:
        from app.database.init_db import check_tables_exist
        ok = check_tables_exist()
        checks.append(("Schema tables", ok, "All tables present" if ok else "Some tables missing — run migrations"))
    except Exception as e:
        checks.append(("Schema tables", False, str(e)))

    # 5. Auth tables (Phase 10)
    try:
        from sqlalchemy import inspect as sa_inspect
        from app.database.engine import get_engine
        import app.database.models  # noqa
        inspector = sa_inspect(get_engine())
        existing = set(inspector.get_table_names())
        auth_tables = {"users", "roles", "permissions", "api_keys", "user_sessions"}
        missing_auth = auth_tables - existing
        if not missing_auth:
            checks.append(("Auth tables (Phase 10)", True, f"{len(auth_tables)} auth tables present"))
        else:
            checks.append(("Auth tables (Phase 10)", False, f"Missing: {missing_auth}"))
    except Exception as e:
        checks.append(("Auth tables (Phase 10)", False, str(e)))

    # 6. RBAC seed (roles)
    try:
        from sqlalchemy import select, text
        from app.database.engine import get_session
        from app.database.models.auth.role import Role
        with get_session() as session:
            count = session.execute(select(Role)).scalars().all()
            n = len(count)
        if n >= 5:
            checks.append(("RBAC roles seeded", True, f"{n} roles found"))
        else:
            checks.append(("RBAC roles seeded", False, f"Only {n} roles — run: python scripts/setup_database.py"))
    except Exception as e:
        checks.append(("RBAC roles seeded", False, str(e)))

    # 7. Admin user
    try:
        from sqlalchemy import select
        from app.database.engine import get_session
        from app.database.models.auth.user import User
        with get_session() as session:
            admin = session.execute(
                select(User).where(User.username == "admin")
            ).scalar_one_or_none()
        if admin:
            checks.append(("Admin user exists", True, f"admin (superuser={admin.is_superuser})"))
        else:
            checks.append(("Admin user exists", False, "Create with: python scripts/setup_database.py"))
    except Exception as e:
        checks.append(("Admin user exists", False, str(e)))

    # 8. Required directories
    required_dirs = ["data/raw", "data/reports", "data/archive", "logs"]
    from pathlib import Path as _Path
    root = _Path(__file__).parent.parent
    all_dirs_ok = all((_Path(root) / d).exists() for d in required_dirs)
    checks.append(("Required directories", all_dirs_ok,
                   "All present" if all_dirs_ok else "Some missing — mkdir data/raw data/reports data/archive logs"))

    _print_checks(checks, verbose=args.verbose)

    failed = [c for c in checks if not c[1]]
    if failed:
        print(f"\n✗ {len(failed)} check(s) failed. Address the issues above.")
        sys.exit(1)
    else:
        print(f"\n✓ All {len(checks)} checks passed — database is ready!")
        sys.exit(0)


def _print_checks(checks: list[tuple[str, bool, str]], verbose: bool = False) -> None:
    for name, ok, detail in checks:
        icon = "✓" if ok else "✗"
        status = "PASS" if ok else "FAIL"
        line = f"  [{icon}] {status:<5} {name}"
        if verbose or not ok:
            line += f" — {detail}"
        print(line)


if __name__ == "__main__":
    main()
