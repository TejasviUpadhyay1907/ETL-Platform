"""
Launch the ETL Platform Operations Dashboard.

Usage:
    python scripts/run_dashboard.py
    python scripts/run_dashboard.py --port 8502
    python scripts/run_dashboard.py --api-url http://etl-api:8000

The script calls `streamlit run` with the correct paths and env vars.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the ETL Platform Dashboard")
    parser.add_argument("--port",    default="8501", help="Streamlit server port (default: 8501)")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Backend API base URL")
    parser.add_argument("--host",    default="localhost", help="Streamlit server address")
    args = parser.parse_args()

    # Root of the project
    project_root = Path(__file__).parent.parent
    home_py      = project_root / "dashboard" / "Home.py"

    if not home_py.exists():
        print(f"Error: Dashboard entry point not found at {home_py}", file=sys.stderr)
        sys.exit(1)

    env = os.environ.copy()
    env["DASHBOARD_API_URL"] = args.api_url

    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(home_py),
        "--server.port",    args.port,
        "--server.address", args.host,
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]

    print(f"Starting ETL Platform Dashboard on http://{args.host}:{args.port}")
    print(f"API backend: {args.api_url}")
    print("Press Ctrl+C to stop.\n")

    try:
        subprocess.run(cmd, env=env, check=True)
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    except subprocess.CalledProcessError as exc:
        print(f"Dashboard exited with code {exc.returncode}", file=sys.stderr)
        sys.exit(exc.returncode)


if __name__ == "__main__":
    main()
