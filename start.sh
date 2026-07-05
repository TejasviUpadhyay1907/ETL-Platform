#!/usr/bin/env bash
# Render start script — resilient DB init then start API
set -e

echo "Starting ETL Platform..."
echo "DATABASE_URL prefix: ${DATABASE_URL:0:30}..."

# Create required directories
mkdir -p /tmp/raw /tmp/reports /tmp/archive /tmp/logs

# Run migrations (non-fatal if DB not ready)
echo "Running database setup..."
python scripts/setup_database.py --skip-seed || echo "DB setup warning (non-fatal) — continuing"

# Start the API
echo "Starting uvicorn..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --log-level info
