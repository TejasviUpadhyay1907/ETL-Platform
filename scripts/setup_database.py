"""
Database Setup Script — ETL Platform v1.0.0
============================================
Performs the complete database initialization sequence:
  1. Verify PostgreSQL connectivity
  2. Run Alembic migrations (creates all tables)
  3. Seed RBAC roles and permissions
  4. Create default admin user (optional)
  5. Verify all tables exist

Usage:
    python scripts/setup_database.py
    python scripts/setup_database.py --skip-seed
    python scripts/setup_database.py --admin-password MySecurePass123!
    python scripts/setup_database.py --help

This script is idempotent — safe to run multiple times.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def print_step(n: int, total: int, msg: str) -> None:
    print(f"\n[{n}/{total}] {msg}")


def check_failed(msg: str) -> None:
    print(f"  ✗ FAILED: {msg}")
    sys.exit(1)


def check_ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set up the ETL Platform database from scratch.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/setup_database.py
  python scripts/setup_database.py --skip-seed
  python scripts/setup_database.py --admin-password AdminPass123!
        """,
    )
    parser.add_argument("--skip-seed",  action="store_true", help="Skip creating default admin user")
    parser.add_argument("--admin-password", default="Admin1234!", help="Password for default admin (default: Admin1234!)")
    args = parser.parse_args()

    TOTAL_STEPS = 5
    print("\n" + "=" * 60)
    print("  ETL Platform — Database Setup")
    print("=" * 60)

    # ── Step 1: Verify configuration ────────────────────────────────────────
    print_step(1, TOTAL_STEPS, "Verifying configuration…")
    try:
        from app.core.config import get_config
        from app.logging.logger import setup_logging
        setup_logging()
        cfg = get_config()
        check_ok(f"Config loaded — APP_ENV={cfg.app_env}")
        check_ok(f"Database URL: {str(cfg.database_url)[:60]}…")
    except Exception as e:
        check_failed(f"Configuration error: {e}\nEnsure .env exists and DATABASE_URL is set.")

    # ── Step 2: Verify DB connectivity ──────────────────────────────────────
    print_step(2, TOTAL_STEPS, "Connecting to PostgreSQL…")
    try:
        from app.database.init_db import verify_connection
        verify_connection()
        check_ok("PostgreSQL connection successful")
    except Exception as e:
        check_failed(
            f"Cannot connect to PostgreSQL: {e}\n"
            "  Ensure PostgreSQL is running and DATABASE_URL is correct.\n"
            "  Quick start: docker run -d --name etl_pg \\\n"
            "    -e POSTGRES_USER=etl_user -e POSTGRES_PASSWORD=etl_password \\\n"
            "    -e POSTGRES_DB=etl_platform -p 5432:5432 postgres:15-alpine"
        )

    # ── Step 3: Run migrations ───────────────────────────────────────────────
    print_step(3, TOTAL_STEPS, "Running Alembic migrations…")
    try:
        from app.database.init_db import run_migrations, get_current_revision
        run_migrations()
        rev = get_current_revision()
        check_ok(f"Migrations applied — revision: {rev}")
    except Exception as e:
        check_failed(f"Migration failed: {e}")

    # ── Step 4: Verify tables ────────────────────────────────────────────────
    print_step(4, TOTAL_STEPS, "Verifying database schema…")
    try:
        from app.database.init_db import check_tables_exist
        if check_tables_exist():
            check_ok("All required tables present")
        else:
            check_failed("Some tables are missing. Check migration output above.")
    except Exception as e:
        check_failed(f"Schema verification error: {e}")

    # ── Step 5: Seed RBAC + default users ───────────────────────────────────
    print_step(5, TOTAL_STEPS, "Seeding RBAC roles, permissions, and default users…")
    if args.skip_seed:
        print("  Skipped (--skip-seed)")
    else:
        try:
            from app.database.engine import get_session
            from app.auth.rbac import seed_roles_and_permissions
            from app.auth.user_service import UserService

            with get_session() as session:
                # Seed roles and permissions
                seed_roles_and_permissions(session)
                check_ok("Roles and permissions seeded (5 roles, 16 permissions)")

                # Create default users
                svc = UserService(session)
                users_created = []

                default_users = [
                    ("admin",    "admin@etlplatform.local",    args.admin_password, ["administrator"], True),
                    ("engineer", "engineer@etlplatform.local", "Engineer1234!",     ["data_engineer"], False),
                    ("analyst",  "analyst@etlplatform.local",  "Analyst1234!",      ["analyst"],       False),
                    ("viewer",   "viewer@etlplatform.local",   "Viewer1234!",       ["viewer"],        False),
                ]

                for username, email, password, roles, is_super in default_users:
                    # Skip if already exists
                    existing = svc.get_user_by_username(username)
                    if existing:
                        print(f"  → User '{username}' already exists — skipping")
                        continue
                    user = svc.create_user(
                        username=username,
                        email=email,
                        password=password,
                        role_names=roles,
                        is_superuser=is_super,
                    )
                    users_created.append(username)
                    check_ok(f"Created user: {username} (roles: {', '.join(roles)})")

                session.commit()

        except Exception as e:
            # Non-fatal — RBAC can be set up manually via API
            print(f"  ⚠ Warning: could not seed users: {e}")
            print("  You can create the admin user manually via:")
            print("    python scripts/create_admin_user.py")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Database Setup Complete!")
    print("=" * 60)
    print("\nDefault credentials (change in production!):")
    print("  Admin:    admin / Admin1234!")
    print("  Engineer: engineer / Engineer1234!")
    print("  Analyst:  analyst / Analyst1234!")
    print("  Viewer:   viewer / Viewer1234!")
    print("\nNext steps:")
    print("  1. Start the API:       python main.py")
    print("  2. Start the dashboard: streamlit run dashboard/Home.py")
    print("  3. API docs:            http://localhost:8000/docs")
    print("  4. Dashboard:           http://localhost:8501")
    print()


if __name__ == "__main__":
    main()
