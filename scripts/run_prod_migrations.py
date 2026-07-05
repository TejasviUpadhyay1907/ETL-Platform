"""Run database migrations against the Render PostgreSQL using external connection."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Override DATABASE_URL to use external Render Postgres connection
RENDER_DB_URL = (
    "postgresql+psycopg2://etl_user:bCvwJUeNJct4cCBrOCQFjVBAIaOvCrBG"
    "@dpg-d9573ggk1i2s739rqr20-a.oregon-postgres.render.com:5432/etl_platform"
    "?sslmode=require"
)
os.environ["DATABASE_URL"] = RENDER_DB_URL

from app.logging.logger import setup_logging
setup_logging()

print("Connecting to Render PostgreSQL...")
print(f"Host: dpg-d9573ggk1i2s739rqr20-a.oregon-postgres.render.com")

# Step 1: Test connection
from app.database.init_db import verify_connection
try:
    verify_connection()
    print("  Connection OK")
except Exception as e:
    print(f"  Connection FAILED: {e}")
    sys.exit(1)

# Step 2: Run migrations
print("\nRunning Alembic migrations...")
from app.database.init_db import run_migrations, get_current_revision
try:
    run_migrations()
    rev = get_current_revision()
    print(f"  Migrations complete. Revision: {rev}")
except Exception as e:
    print(f"  Migration error: {e}")
    sys.exit(1)

# Step 3: Seed RBAC
print("\nSeeding roles and creating admin user...")
try:
    from app.database.engine import get_session
    from app.auth.rbac import seed_roles_and_permissions
    from app.auth.user_service import UserService

    with get_session() as session:
        seed_roles_and_permissions(session)
        svc = UserService(session)
        existing = svc.get_user_by_username("admin")
        if existing:
            print("  Admin user already exists")
        else:
            svc.create_user("admin", "admin@etlplatform.local", "Admin1234!",
                            ["administrator"], is_superuser=True)
            print("  Admin user created: admin / Admin1234!")

        for u, e, p, roles in [
            ("engineer", "engineer@etlplatform.local", "Engineer1234!", ["data_engineer"]),
            ("analyst",  "analyst@etlplatform.local",  "Analyst1234!",  ["analyst"]),
        ]:
            if not svc.get_user_by_username(u):
                svc.create_user(u, e, p, roles)
                print(f"  Created user: {u}")
        session.commit()
    print("  RBAC seeding complete")
except Exception as e:
    print(f"  Seeding error (non-fatal): {e}")

print("""
========================================
  Production Setup Complete!
========================================

  API: https://etl-platform-api.onrender.com
  Docs: https://etl-platform-api.onrender.com/docs

  Login: admin / Admin1234!

  Test login:
  POST https://etl-platform-api.onrender.com/api/v1/auth/login
  Body: {"username":"admin","password":"Admin1234!"}
""")
