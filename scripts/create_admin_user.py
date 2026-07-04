"""
Create Admin User — ETL Platform v1.0.0
=========================================
Creates the default administrator account.
Safe to run if the user already exists (idempotent).

Usage:
    python scripts/create_admin_user.py
    python scripts/create_admin_user.py --username myadmin --password SecurePass123!
    python scripts/create_admin_user.py --email admin@mycompany.com
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the default admin user")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--email",    default="admin@etlplatform.local")
    parser.add_argument("--password", default="Admin1234!")
    args = parser.parse_args()

    from app.logging.logger import setup_logging
    setup_logging()

    print(f"\nCreating admin user: {args.username}")

    try:
        from app.database.engine import get_session
        from app.auth.rbac import seed_roles_and_permissions
        from app.auth.user_service import UserService

        with get_session() as session:
            # Ensure roles exist first
            seed_roles_and_permissions(session)

            svc = UserService(session)
            existing = svc.get_user_by_username(args.username)
            if existing:
                print(f"  User '{args.username}' already exists.")
                print(f"  Email: {existing.email}")
                print(f"  Roles: {existing.role_names}")
                sys.exit(0)

            user = svc.create_user(
                username=args.username,
                email=args.email,
                password=args.password,
                role_names=["administrator"],
                is_superuser=True,
            )
            session.commit()

        print(f"\n  ✓ Admin user created successfully!")
        print(f"\n  Username: {args.username}")
        print(f"  Email:    {args.email}")
        print(f"  Password: {args.password}")
        print(f"\n  Use these credentials to log into the dashboard at http://localhost:8501")
        print(f"  or via the API at http://localhost:8000/api/v1/auth/login\n")

    except Exception as e:
        print(f"\n  ✗ Failed to create admin user: {e}")
        print("  Ensure the database is set up: python scripts/setup_database.py")
        sys.exit(1)


if __name__ == "__main__":
    main()
