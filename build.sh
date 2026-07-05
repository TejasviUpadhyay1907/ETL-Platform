#!/usr/bin/env bash
# Render build script
set -o errexit

# Install system dependencies for psycopg2
apt-get update -y 2>/dev/null || true
apt-get install -y --no-install-recommends libpq-dev gcc 2>/dev/null || true

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

echo "Build complete."
