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
    from app.database.engine import get_session
    from app.auth.rbac import seed_roles_and_permissions
    from app.auth.user_service import UserService

    with get_session() as session:
        seed_roles_and_permissions(session)

        svc = UserService(session)
        for username, email, password, roles, is_super in [
            ("admin",    "admin@etlplatform.local",    "Admin1234!",    ["administrator"], True),
            ("engineer", "engineer@etlplatform.local", "Engineer1234!", ["data_engineer"], False),
        ]:
            if not svc.get_user_by_username(username):
                svc.create_user(username, email, password, roles, is_superuser=is_super)
                print(f"Created user: {username}")
        session.commit()
    print("RBAC seeding complete.")
except Exception as e:
    print(f"Seeding warning (non-fatal): {e}")

print("Database setup done. Starting API...")
PYEOF

echo "Starting uvicorn on port ${PORT:-10000}..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-10000}" --workers 1 --log-level info
