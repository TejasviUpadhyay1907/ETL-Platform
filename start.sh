#!/usr/bin/env bash
# Render start script — runs migrations then starts API
set -e

echo "=== ETL Platform v1.0.0 Starting ==="
echo "Python: $(python --version)"
echo "DATABASE_URL set: $([ -n \"$DATABASE_URL\" ] && echo YES || echo NO)"

# Create required directories
mkdir -p /tmp/raw /tmp/reports /tmp/archive

# Run database migrations (uses internal DATABASE_URL — works on Render network)
echo "Running database migrations..."
python -c "
import sys
sys.path.insert(0, '.')
from app.database.init_db import verify_connection, run_migrations, check_tables_exist
from app.logging.logger import setup_logging
setup_logging()
try:
    verify_connection()
    run_migrations()
    print('Migrations complete.')
except Exception as e:
    print(f'Migration warning: {e}')
    print('Continuing startup...')
"

# Seed RBAC roles and default admin user (idempotent — safe to run every time)
echo "Seeding RBAC roles and admin user..."
python -c "
import sys
sys.path.insert(0, '.')
try:
    from app.database.engine import get_session
    from app.auth.rbac import seed_roles_and_permissions
    from app.auth.user_service import UserService
    with get_session() as session:
        seed_roles_and_permissions(session)
        svc = UserService(session)
        if not svc.get_user_by_username('admin'):
            svc.create_user('admin', 'admin@etlplatform.local', 'Admin1234!',
                            ['administrator'], is_superuser=True)
            print('Admin user created: admin / Admin1234!')
        else:
            print('Admin user already exists.')
        session.commit()
    print('RBAC seeding complete.')
except Exception as e:
    print(f'Seeding warning (non-fatal): {e}')
    print('Continuing startup...')
"

# Start the API
echo "Starting uvicorn on port ${PORT:-10000}..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-10000}" --workers 1 --log-level info
