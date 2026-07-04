"""
CLI health check script for monitoring integration.

Usage:
    python scripts/health_check.py
    python scripts/health_check.py --host localhost --port 8000

Returns exit code 0 if healthy, 1 if unhealthy.
Implementation: Milestone 3
"""
import sys

def main() -> None:
    try:
        import httpx
        response = httpx.get("http://localhost:8000/api/v1/health/ping", timeout=5.0)
        response.raise_for_status()
        print(f"Health check passed: {response.json()}")
        sys.exit(0)
    except Exception as e:
        print(f"Health check FAILED: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
