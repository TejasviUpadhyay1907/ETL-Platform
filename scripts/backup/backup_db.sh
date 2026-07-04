#!/usr/bin/env bash
# =============================================================================
# ETL Platform — PostgreSQL Backup Script
# =============================================================================
# Usage: ./backup_db.sh [--retention-days 30]
#
# Creates a timestamped pg_dump archive to BACKUP_DIR.
# Rotates backups older than RETENTION_DAYS.
#
# Required environment variables (or .env):
#   DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME, BACKUP_DIR
# =============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Load .env if present
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

DB_USER="${DB_USER:-etl_user}"
DB_PASSWORD="${DB_PASSWORD:-etl_password}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-etl_platform}"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/data/backups/db}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.dump"

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --retention-days) RETENTION_DAYS="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# ── Setup ────────────────────────────────────────────────────────────────────
mkdir -p "${BACKUP_DIR}"

echo "[$(date -Iseconds)] Starting database backup..."
echo "  Source: ${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
echo "  Target: ${BACKUP_FILE}"

# ── Run backup ───────────────────────────────────────────────────────────────
PGPASSWORD="${DB_PASSWORD}" pg_dump \
    --host="${DB_HOST}" \
    --port="${DB_PORT}" \
    --username="${DB_USER}" \
    --dbname="${DB_NAME}" \
    --format=custom \
    --compress=9 \
    --no-password \
    --verbose \
    --file="${BACKUP_FILE}" 2>&1

BACKUP_SIZE="$(du -sh "${BACKUP_FILE}" | cut -f1)"
echo "[$(date -Iseconds)] Backup complete: ${BACKUP_FILE} (${BACKUP_SIZE})"

# ── Rotate old backups ───────────────────────────────────────────────────────
DELETED_COUNT=0
while IFS= read -r -d '' old_file; do
    rm -f "${old_file}"
    echo "  Removed expired backup: ${old_file}"
    ((DELETED_COUNT++))
done < <(find "${BACKUP_DIR}" -name "*.dump" -mtime "+${RETENTION_DAYS}" -print0)

echo "[$(date -Iseconds)] Rotation complete: removed ${DELETED_COUNT} expired backup(s)"
echo "[$(date -Iseconds)] Backup job finished successfully."
