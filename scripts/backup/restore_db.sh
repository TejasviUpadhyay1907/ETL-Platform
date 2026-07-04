#!/usr/bin/env bash
# =============================================================================
# ETL Platform — PostgreSQL Restore Script
# =============================================================================
# Usage: ./restore_db.sh --backup-file /path/to/backup.dump [--drop-existing]
#
# Restores a pg_dump archive created by backup_db.sh.
# WARNING: --drop-existing will DROP the target database before restoring.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a; source "${PROJECT_ROOT}/.env"; set +a
fi

DB_USER="${DB_USER:-etl_user}"
DB_PASSWORD="${DB_PASSWORD:-etl_password}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-etl_platform}"
BACKUP_FILE=""
DROP_EXISTING=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --backup-file)   BACKUP_FILE="$2"; shift 2 ;;
        --drop-existing) DROP_EXISTING=true; shift ;;
        *)               echo "Unknown argument: $1"; exit 1 ;;
    esac
done

if [[ -z "${BACKUP_FILE}" ]]; then
    echo "ERROR: --backup-file is required"
    echo "Usage: $0 --backup-file /path/to/backup.dump [--drop-existing]"
    exit 1
fi

if [[ ! -f "${BACKUP_FILE}" ]]; then
    echo "ERROR: Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

echo "[$(date -Iseconds)] Starting restore..."
echo "  Backup: ${BACKUP_FILE}"
echo "  Target: ${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

if [[ "${DROP_EXISTING}" == "true" ]]; then
    echo "  WARNING: Dropping existing database '${DB_NAME}'..."
    PGPASSWORD="${DB_PASSWORD}" psql \
        --host="${DB_HOST}" --port="${DB_PORT}" \
        --username="${DB_USER}" --dbname=postgres \
        -c "DROP DATABASE IF EXISTS \"${DB_NAME}\";"
    PGPASSWORD="${DB_PASSWORD}" psql \
        --host="${DB_HOST}" --port="${DB_PORT}" \
        --username="${DB_USER}" --dbname=postgres \
        -c "CREATE DATABASE \"${DB_NAME}\" OWNER \"${DB_USER}\";"
fi

PGPASSWORD="${DB_PASSWORD}" pg_restore \
    --host="${DB_HOST}" \
    --port="${DB_PORT}" \
    --username="${DB_USER}" \
    --dbname="${DB_NAME}" \
    --no-password \
    --verbose \
    --clean \
    --if-exists \
    "${BACKUP_FILE}" 2>&1

echo "[$(date -Iseconds)] Restore complete."
