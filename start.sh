#!/usr/bin/env bash
# Render start script
set -e

echo "=== ETL Platform Starting ==="
echo "Python: $(python --version)"
echo "DATABASE_URL set: $([ -n \"$DATABASE_URL\" ] && echo YES || echo NO)"

# Create required directories
mkdir -p /tmp/raw /tmp/reports /tmp/archive

# Start the API directly
# (Migrations run separately via Render shell or on first request)
echo "Starting uvicorn on port ${PORT:-8000}..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --log-level info
