#!/usr/bin/env bash
# =============================================================================
# ETL Platform — Configuration & Metadata Backup
# =============================================================================
# Backs up config files, migration history, and pipeline metadata.
# Does NOT back up secrets or .env files.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/data/backups/config}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE="${BACKUP_DIR}/config_${TIMESTAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

echo "[$(date -Iseconds)] Backing up configuration to ${ARCHIVE}..."

tar -czf "${ARCHIVE}" \
    --exclude="${PROJECT_ROOT}/.env" \
    --exclude="${PROJECT_ROOT}/.env.*" \
    --exclude="${PROJECT_ROOT}/data" \
    --exclude="${PROJECT_ROOT}/logs" \
    --exclude="${PROJECT_ROOT}/.git" \
    --exclude="${PROJECT_ROOT}/__pycache__" \
    --exclude="${PROJECT_ROOT}/.pytest_cache" \
    -C "${PROJECT_ROOT}" \
    config/ \
    migrations/versions/ \
    alembic.ini \
    pyproject.toml \
    requirements.txt \
    requirements-dev.txt \
    2>&1

ARCHIVE_SIZE="$(du -sh "${ARCHIVE}" | cut -f1)"
echo "[$(date -Iseconds)] Config backup complete: ${ARCHIVE} (${ARCHIVE_SIZE})"
