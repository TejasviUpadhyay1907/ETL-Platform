"""
Database Reset Script — ETL Platform v1.0.0
============================================
WARNING: This script DESTROYS all data and resets the database to a clean state.
Intended for development and demo resets ONLY.

Steps:
  1. Drop all tables
  2. Re-run all migrations
  3. Re-seed roles and permissions
  4. Re-create default users
  5. Optionally seed demo data

Usage:
    python scripts/reset_database.py           # confirm interactively
    python scripts/reset_database.py --yes     # skip confirmation
    python scripts/reset_database.py --yes --with-demo-data
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset the database to a clean state (DESTROYS ALL DATA)",
    )
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--with-demo-data", action="store_true", help="Seed small demo dataset after reset")
    args = parser.parse_args()

    print("\n" + "!" * 60)
    print("  WARNING: DATABASE RESET")
    print("  This will DROP ALL TABLES and recreate them.")
    print("  ALL DATA WILL BE PERMANENTLY DELETED.")
    print("!" * 60)

    if not args.yes:
        confirm = input("\nType 'RESET' to confirm: ").strip()
        if confirm != "RESET":
            print("Cancelled.")
            sys.exit(0)

    from app.logging.logger import setup_logging
    setup_logging()

    print("\n[1/4] Dropping all tables…")
    try:
        from app.database.init_db import drop_all_tables
        drop_all_tables()
        print("  ✓ All tables dropped")
    except Exception as e:
        print(f"  ✗ Drop failed: {e}")
        sys.exit(1)

    print("\n[2/4] Running migrations…")
    try:
        from app.database.init_db import run_migrations
        run_migrations()
        print("  ✓ Migrations applied")
    except Exception as e:
        print(f"  ✗ Migration failed: {e}")
        sys.exit(1)

    print("\n[3/4] Seeding roles and default users…")
    try:
        from app.database.engine import get_session
        from app.auth.rbac import seed_roles_and_permissions
        from app.auth.user_service import UserService

        with get_session() as session:
            seed_roles_and_permissions(session)
            svc = UserService(session)
            for username, email, password, roles, is_super in [
                ("admin",    "admin@etlplatform.local",    "Admin1234!",    ["administrator"], True),
                ("engineer", "engineer@etlplatform.local", "Engineer1234!", ["data_engineer"], False),
                ("analyst",  "analyst@etlplatform.local",  "Analyst1234!",  ["analyst"],       False),
                ("viewer",   "viewer@etlplatform.local",   "Viewer1234!",   ["viewer"],        False),
            ]:
                svc.create_user(username=username, email=email, password=password,
                                role_names=roles, is_superuser=is_super)
                print(f"  ✓ Created user: {username}")
            session.commit()
    except Exception as e:
        print(f"  ✗ Seeding failed: {e}")
        sys.exit(1)

    print("\n[4/4] Seeding demo data…")
    if args.with_demo_data:
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "scripts/seed_data.py", "--count", "tiny"],
                check=True, capture_output=True, text=True,
            )
            print(result.stdout[-500:] if result.stdout else "")
            print("  ✓ Demo data seeded (tiny preset)")
        except subprocess.CalledProcessError as e:
            print(f"  ⚠ Demo data seed failed (non-fatal): {e.stderr[-200:]}")
    else:
        print("  Skipped (add --with-demo-data to include demo records)")

    print("\n" + "=" * 60)
    print("  Database Reset Complete!")
    print("=" * 60)
    print("\nDefault credentials:")
    print("  admin / Admin1234!")
    print()


if __name__ == "__main__":
    main()
