"""
Development Startup Script — ETL Platform v1.0.0
=================================================
Starts the complete development environment with one command:
  1. Verifies prerequisites (Python, PostgreSQL, .env)
  2. Creates required directories
  3. Runs database migrations
  4. Seeds RBAC roles and default users
  5. Starts the FastAPI backend
  6. Optionally starts the Streamlit dashboard (--with-dashboard)

Usage:
    python scripts/start_dev.py
    python scripts/start_dev.py --with-dashboard
    python scripts/start_dev.py --skip-migrations
    python scripts/start_dev.py --port 8080

The FastAPI server runs in the foreground. Use Ctrl+C to stop.
The dashboard (if started) runs in a separate process.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def step(msg: str) -> None:
    print(f"\n  → {msg}")


def ok(msg: str) -> None:
    print(f"    ✓ {msg}")


def fail(msg: str, hint: str = "") -> None:
    print(f"\n  ✗ {msg}")
    if hint:
        print(f"    Hint: {hint}")
    sys.exit(1)


def check_python_version() -> None:
    step("Checking Python version…")
    v = sys.version_info
    if v < (3, 12):
        fail(f"Python 3.12+ required, found {v.major}.{v.minor}",
             "Install Python 3.12: https://python.org/downloads/")
    ok(f"Python {v.major}.{v.minor}.{v.micro}")


def check_env_file() -> None:
    step("Checking .env file…")
    env_path = ROOT / ".env"
    if not env_path.exists():
        example = ROOT / ".env.example"
        if example.exists():
            import shutil
            shutil.copy(str(example), str(env_path))
            ok(".env created from .env.example — review and update DATABASE_URL, SECRET_KEY, JWT_SECRET")
        else:
            fail(".env not found and .env.example missing",
                 "Create .env with DATABASE_URL, SECRET_KEY, JWT_SECRET")
    else:
        ok(".env found")

    # Check required variables
    from dotenv import load_dotenv
    load_dotenv(env_path)
    missing = []
    required = ["DATABASE_URL", "SECRET_KEY", "JWT_SECRET"]
    for var in required:
        val = os.getenv(var, "")
        if not val or "change-this" in val.lower() or "change-me" in val.lower():
            missing.append(var)
    if missing:
        print(f"    ⚠ Variables with placeholder values (update for production): {', '.join(missing)}")
    else:
        ok("Required environment variables set")


def create_directories() -> None:
    step("Creating required directories…")
    dirs = [ROOT / "data" / "raw", ROOT / "data" / "reports",
            ROOT / "data" / "archive", ROOT / "logs"]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    ok("data/raw, data/reports, data/archive, logs")


def check_dependencies() -> None:
    step("Checking Python dependencies…")
    missing = []
    for pkg, import_name in [("fastapi", "fastapi"), ("uvicorn", "uvicorn"),
                               ("sqlalchemy", "sqlalchemy"), ("alembic", "alembic"),
                               ("pydantic", "pydantic"), ("passlib", "passlib"),
                               ("jose", "jose"), ("pandas", "pandas")]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)
    if missing:
        fail(f"Missing packages: {', '.join(missing)}",
             "Run: pip install -r requirements.txt")
    ok("All core dependencies installed")


def run_migrations(skip: bool) -> None:
    step("Running database migrations…")
    if skip:
        print("    Skipped (--skip-migrations)")
        return
    try:
        result = subprocess.run(
            [sys.executable, "scripts/run_migrations.py"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        if result.returncode != 0:
            fail(f"Migration failed:\n{result.stderr[-500:]}")
        ok("Migrations applied")
    except Exception as e:
        fail(f"Migration error: {e}")


def seed_rbac() -> None:
    step("Seeding RBAC roles and default users…")
    try:
        from app.database.engine import get_session
        from app.auth.rbac import seed_roles_and_permissions
        from app.auth.user_service import UserService
        from sqlalchemy.exc import IntegrityError

        with get_session() as session:
            seed_roles_and_permissions(session)
            svc = UserService(session)
            if not svc.get_user_by_username("admin"):
                svc.create_user("admin", "admin@etlplatform.local",
                                "Admin1234!", ["administrator"], is_superuser=True)
                ok("Admin user created (admin / Admin1234!)")
            else:
                ok("Admin user already exists")
            session.commit()
    except Exception as e:
        print(f"    ⚠ RBAC seed warning (non-fatal): {e}")


def start_dashboard(port: int) -> subprocess.Popen | None:
    step("Starting Streamlit dashboard…")
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "dashboard/Home.py",
             "--server.port", str(port), "--server.headless", "true",
             "--browser.gatherUsageStats", "false"],
            cwd=str(ROOT),
        )
        time.sleep(3)
        ok(f"Dashboard started — http://localhost:{port}")
        return proc
    except Exception as e:
        print(f"    ⚠ Dashboard failed to start: {e}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Start ETL Platform development environment")
    parser.add_argument("--with-dashboard", action="store_true", help="Also start Streamlit dashboard")
    parser.add_argument("--skip-migrations", action="store_true", help="Skip database migrations")
    parser.add_argument("--port", type=int, default=8000, help="API server port (default: 8000)")
    parser.add_argument("--dashboard-port", type=int, default=8501, help="Dashboard port (default: 8501)")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  ETL Platform — Development Startup")
    print("=" * 60)

    check_python_version()
    check_env_file()
    create_directories()
    check_dependencies()
    run_migrations(args.skip_migrations)
    seed_rbac()

    dashboard_proc = None
    if args.with_dashboard:
        dashboard_proc = start_dashboard(args.dashboard_port)

    print("\n" + "=" * 60)
    print("  Starting FastAPI server…")
    print("=" * 60)
    print(f"\n  API:          http://localhost:{args.port}")
    print(f"  Swagger docs: http://localhost:{args.port}/docs")
    print(f"  ReDoc:        http://localhost:{args.port}/redoc")
    print(f"  Health:       http://localhost:{args.port}/api/v1/health/ping")
    if args.with_dashboard:
        print(f"  Dashboard:    http://localhost:{args.dashboard_port}")
    print(f"\n  Login:        admin / Admin1234!")
    print("\n  Press Ctrl+C to stop.\n")

    try:
        env = os.environ.copy()
        env["APP_ENV"] = "development"
        subprocess.run(
            [sys.executable, "-m", "uvicorn", "main:app",
             "--host", "0.0.0.0", "--port", str(args.port),
             "--reload", "--log-level", "info"],
            cwd=str(ROOT), env=env,
        )
    except KeyboardInterrupt:
        print("\n\nShutting down…")
    finally:
        if dashboard_proc:
            dashboard_proc.terminate()
            print("Dashboard stopped.")


if __name__ == "__main__":
    main()
