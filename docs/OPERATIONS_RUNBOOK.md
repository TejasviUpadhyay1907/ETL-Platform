# Operations Runbook — ETL Platform v1.0.0

## Service Overview

| Service | Port | Health Check |
|---------|------|-------------|
| FastAPI API | 8000 | `GET /api/v1/health` |
| Streamlit Dashboard | 8501 | `GET /_stcore/health` |
| PostgreSQL | 5432 | `pg_isready` |
| Nginx | 80/443 | `GET /health` |
| Prometheus | 9090 | `GET /-/healthy` |
| Grafana | 3000 | `GET /api/health` |

---

## Starting / Stopping

```bash
# Start all services
docker-compose -f docker-compose.prod.yml up -d

# Stop all services (preserve data)
docker-compose -f docker-compose.prod.yml down

# Restart one service
docker-compose -f docker-compose.prod.yml restart api

# View logs
docker-compose -f docker-compose.prod.yml logs -f api
docker-compose -f docker-compose.prod.yml logs --tail=100 api
```

---

## Health Checks

```bash
# Quick health
curl http://localhost:8000/api/v1/health/ping

# Full health (DB connectivity + filesystem)
curl http://localhost:8000/api/v1/health | python -m json.tool

# Check all containers
docker-compose -f docker-compose.prod.yml ps

# Prometheus targets
curl http://localhost:9090/api/v1/targets | python -m json.tool
```

---

## Common Incidents

### API is returning 503 — Database unavailable

**Symptoms:** `GET /api/v1/health` returns `{"status": "unhealthy", "database": "unhealthy"}`

**Diagnosis:**
```bash
docker-compose -f docker-compose.prod.yml ps db
docker-compose -f docker-compose.prod.yml logs --tail=50 db
```

**Resolution:**
```bash
# Restart DB
docker-compose -f docker-compose.prod.yml restart db

# Wait for health check, then restart API
docker-compose -f docker-compose.prod.yml restart api

# Verify
curl http://localhost:8000/api/v1/health | python -m json.tool
```

---

### Pipeline stuck in "running" state

**Symptoms:** Pipeline run shows `status=running` for >1 hour

**Diagnosis:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/pipelines/$RUN_ID | python -m json.tool

curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/pipelines/$RUN_ID/events
```

**Resolution:**
```bash
# Cancel via API
curl -X POST -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/pipelines/$RUN_ID/cancel

# Or retry
curl -X POST -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/pipelines/$RUN_ID/retry
```

---

### High API error rate (5xx)

**Symptoms:** Prometheus alert `HighErrorRate` fires; Grafana shows 5xx spike

**Diagnosis:**
```bash
# Check recent errors in logs
docker-compose -f docker-compose.prod.yml logs api | grep "ERROR" | tail -50

# Check Prometheus for error patterns
# Query: sum(rate(etl_http_requests_total{status=~"5.."}[5m])) by (endpoint)
```

**Resolution:**
1. Check DB connectivity (see above)
2. Check disk space: `df -h`
3. Check memory: `docker stats etl_prod_api`
4. Restart API if needed: `docker-compose restart api`

---

### Account locked out

**Symptoms:** User cannot log in; receives `ACCOUNT_LOCKED` error

**Resolution:**
```bash
# Unlock via API (requires administrator JWT)
curl -X POST \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     http://localhost:8000/api/v1/users/$USER_ID/unlock
```

---

### Disk space critical

**Symptoms:** `HighDiskUsage` alert; API failing to write logs or data files

**Resolution:**
```bash
# Check what's consuming space
du -sh /var/lib/docker/volumes/etl_prod_*

# Rotate application logs
docker-compose -f docker-compose.prod.yml exec api \
    find /app/logs -name "*.log" -mtime +7 -delete

# Prune unused Docker resources
docker system prune -f

# Archive old data
./scripts/backup/backup_db.sh --retention-days 14
```

---

## Database Maintenance

### Manual backup
```bash
./scripts/backup/backup_db.sh
ls -lh data/backups/db/
```

### Restore from backup
```bash
./scripts/backup/restore_db.sh \
    --backup-file data/backups/db/etl_platform_20250705_030000.dump \
    --drop-existing
```

### Vacuum and analyze
```bash
docker-compose exec db psql -U etl_user -d etl_platform \
    -c "VACUUM ANALYZE;"
```

### Check table sizes
```bash
docker-compose exec db psql -U etl_user -d etl_platform -c "
SELECT schemaname, tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 20;"
```

---

## Scheduled Maintenance Windows

| Task | Frequency | Script |
|------|-----------|--------|
| Database backup | Daily 03:00 | `scripts/backup/backup_db.sh` |
| Config backup | Weekly Sunday 02:00 | `scripts/backup/backup_config.sh` |
| Log rotation | Weekly | Docker logging `max-size` config |
| VACUUM ANALYZE | Weekly | Cron on DB host |

---

## Upgrade Procedure

```bash
# 1. Backup database FIRST
./scripts/backup/backup_db.sh

# 2. Pull new image / code
git fetch && git checkout v1.1.0

# 3. Run migrations (offline)
docker-compose -f docker-compose.prod.yml exec api \
    alembic upgrade head

# 4. Rolling restart
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d --no-deps api

# 5. Verify
curl http://localhost:8000/api/v1/health
```

---

## Log Reference

All logs are structured JSON in production. Key fields:

| Field | Description |
|-------|-------------|
| `timestamp` | ISO-8601 UTC timestamp |
| `level` | DEBUG/INFO/WARNING/ERROR/CRITICAL |
| `message` | Human-readable description |
| `request_id` | Correlation ID (X-Request-ID) |
| `path` | HTTP request path |
| `method` | HTTP method |
| `status_code` | HTTP response status |
| `duration_ms` | Request processing time |
| `run_id` | Pipeline run UUID (for pipeline events) |
| `stage` | ETL stage name |

Query logs:
```bash
# Filter errors in last hour
docker-compose logs api 2>&1 | \
    python -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line)
        if d.get('level') in ('ERROR','CRITICAL'):
            print(json.dumps(d, indent=2))
    except: pass
" | head -100
```
