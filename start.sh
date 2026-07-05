#!/usr/bin/env bash
# Render start script
set -e

echo "=== ETL Platform v1.0.0 Starting ==="
echo "Python: $(python --version)"
echo "DATABASE_URL set: $([ -n \"$DATABASE_URL\" ] && echo YES || echo NO)"

mkdir -p /tmp/raw /tmp/reports /tmp/archive

echo "Setting up database..."
python - <<'PYEOF'
import sys
sys.path.insert(0, '.')
from app.logging.logger import setup_logging
setup_logging()

try:
    # Step 1: Run Alembic migrations (creates 14 operational + pipeline tables)
    from app.database.init_db import verify_connection, run_migrations
    verify_connection()
    run_migrations()
    print("Alembic migrations complete.")
except Exception as e:
    print(f"Migration warning: {e}")

try:
    # Step 2: Create auth tables (not in Alembic — added in Phase 10)
    from app.database.base import Base
    from app.database.engine import get_engine
    import app.database.models  # registers ALL models including auth
    from sqlalchemy import inspect as sa_inspect

    engine = get_engine()
    inspector = sa_inspect(engine)
    existing = set(inspector.get_table_names())
    all_tables = set(Base.metadata.tables.keys())
    missing = all_tables - existing

    if missing:
        print(f"Creating missing tables: {missing}")
        tables_to_create = [Base.metadata.tables[t] for t in missing]
        Base.metadata.create_all(engine, tables=tables_to_create)
        print(f"Created {len(missing)} tables.")
    else:
        print("All tables exist.")
except Exception as e:
    print(f"Table creation warning: {e}")

try:
    # Step 3: Seed RBAC roles + create admin user
    # Use raw bcrypt directly to avoid passlib version mismatch
    import bcrypt as _bcrypt
    from app.database.engine import get_session
    from app.auth.rbac import seed_roles_and_permissions
    from app.database.models.auth.user import User as UserModel
    from app.database.models.auth.role import Role as RoleModel
    from sqlalchemy import select

    def make_hash(pwd):
        return _bcrypt.hashpw(pwd.encode(), _bcrypt.gensalt(rounds=12)).decode()

    def check_hash(pwd, hashed):
        return _bcrypt.checkpw(pwd.encode(), hashed.encode())

    with get_session() as session:
        seed_roles_and_permissions(session)

        users_to_create = [
            ("admin",    "admin@etlplatform.local",    "Admin1234!",    "administrator", True),
            ("engineer", "engineer@etlplatform.local", "Engineer1234!", "data_engineer", False),
        ]
        for username, email, password, role_name, is_super in users_to_create:
            u = session.execute(
                select(UserModel).where(UserModel.username == username)
            ).scalar_one_or_none()

            pwd_hash = make_hash(password)
            ok = check_hash(password, pwd_hash)

            if not u:
                role = session.execute(
                    select(RoleModel).where(RoleModel.name == role_name)
                ).scalar_one_or_none()
                u = UserModel(
                    username=username, email=email,
                    hashed_password=pwd_hash,
                    is_active=True, is_superuser=is_super,
                    is_locked=False, is_deleted=False,
                    failed_login_count=0,
                )
                if role:
                    u.roles.append(role)
                session.add(u)
                print(f"Created user: {username} (bcrypt_ok={ok})")
            else:
                u.hashed_password = pwd_hash
                u.is_locked = False
                u.failed_login_count = 0
                print(f"Reset password: {username} (bcrypt_ok={ok})")

        session.commit()
    print("RBAC seeding complete.")
except Exception as e:
    print(f"Seeding warning (non-fatal): {e}")
    import traceback; traceback.print_exc()

print("Database setup done. Starting API...")
PYEOF

echo "Starting uvicorn on port ${PORT:-10000}..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-10000}" --workers 1 --log-level info
