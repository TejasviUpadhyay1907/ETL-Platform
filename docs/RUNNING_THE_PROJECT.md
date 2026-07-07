# Running the Project — ETL Platform v1.0.0

This guide covers every way to run the platform after completing [FIRST_TIME_SETUP.md](FIRST_TIME_SETUP.md).

---

## Option 1 — Development (Local Python)

**Best for:** Development, debugging, demos on a laptop.

```bash
# Terminal 1 — API (with hot-reload)
source .venv/bin/activate      # Windows: .venv\Scripts\activate
python main.py

# Terminal 2 — Dashboard
source .venv/bin/activate
streamlit run dashboard/Home.py
```

**Or one-command:**
```bash
python scripts/start_dev.py --with-dashboard
```

| Service | URL |
|---------|-----|
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Dashboard | http://localhost:8501 |
| Prometheus metrics | http://localhost:8000/metrics |

---

## Option 2 — Docker Compose (Recommended for demos)

**Best for:** Consistent environment, sharing with others, closer to production.

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env — set SECRET_KEY, JWT_SECRET, API_KEY_SALT

# Start all services (API + DB + Dashboard + Nginx)
docker-compose -f docker-compose.prod.yml up -d

# First run: initialize the database
docker-compose -f docker-compose.prod.yml exec api python scripts/setup_database.py

# Check status
docker-compose -f docker-compose.prod.yml ps
```

| Service | URL |
|---------|-----|
| Platform (via Nginx) | http://localhost:80 |
| API direct | http://localhost:8000 |
| Dashboard direct | http://localhost:8501 |

**Logs:**
```bash
docker-compose -f docker-compose.prod.yml logs -f api
docker-compose -f docker-compose.prod.yml logs -f dashboard
```

**Stop:**
```bash
docker-compose -f docker-compose.prod.yml down
```

---

## Option 3 — Docker Compose with Monitoring

**Best for:** Demonstrating observability features (Prometheus + Grafana).

```bash
docker-compose \
  -f docker-compose.prod.yml \
  -f docker-compose.monitoring.yml \
  up -d
```

Additional services:

| Service | URL | Credentials |
|---------|-----|-------------|
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | admin / changeme |
| Node Exporter | http://localhost:9100 | — |

**Import Grafana dashboards:**
They are auto-provisioned from `docker/grafana/dashboards/`. No manual import needed.

---

## Option 4 — Development Docker Compose

**Best for:** Docker-based development with hot-reload.

```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
```

Source code is mounted as a volume — changes take effect immediately.

---

## Running Individual Components

### API only
```bash
python main.py
# or with explicit settings:
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Dashboard only
```bash
streamlit run dashboard/Home.py
# or with options:
python scripts/run_dashboard.py --port 8502 --api-url http://localhost:8000
```

### Migrations only
```bash
python scripts/run_migrations.py
# Check current state:
python scripts/run_migrations.py --show
# Rollback last migration:
python scripts/run_migrations.py --downgrade -1
```

### Seed demo data
```bash
python scripts/seed_data.py --count small   # ~7,000 records (fast)
python scripts/seed_data.py --count tiny    # ~800 records (fastest)
python scripts/seed_data.py --count full    # ~80,000 records (realistic demo)
python scripts/seed_data.py --truncate --count small  # clear + re-seed
```

---

## Health Verification

```bash
# Quick ping (no auth)
curl http://localhost:8000/api/v1/health/ping

# Full health check
curl http://localhost:8000/api/v1/health | python -m json.tool

# Database verification
python scripts/verify_database.py

# Prometheus metrics
curl http://localhost:8000/metrics | head -30
```

---

## Running Tests

```bash
# Full unit test suite (no DB required)
pytest tests/unit/ -q

# With coverage report
pytest tests/unit/ --cov=app --cov-report=term-missing

# Dashboard tests only
pytest tests/unit/test_dashboard/ -v

# Integration tests (requires running PostgreSQL)
pytest tests/integration/ -v

# Everything
pytest tests/unit/ tests/integration/test_api_health.py -q
```

---

## Stopping Everything

```bash
# Local processes: Ctrl+C in each terminal

# Docker Compose
docker-compose -f docker-compose.prod.yml down

# Docker Compose + monitoring
docker-compose -f docker-compose.prod.yml -f docker-compose.monitoring.yml down

# Stop everything and remove volumes (DESTROYS DATA)
docker-compose -f docker-compose.prod.yml down -v
```

---

## Port Reference

| Service | Default Port | Config Variable |
|---------|-------------|-----------------|
| FastAPI | 8000 | `PORT` in `.env` |
| Streamlit Dashboard | 8501 | `--server.port` |
| PostgreSQL | 5432 | in `DATABASE_URL` |
| Nginx HTTP | 80 | `HTTP_PORT` in `.env` |
| Nginx HTTPS | 443 | `HTTPS_PORT` in `.env` |
| Prometheus | 9090 | `PROMETHEUS_PORT` in `.env` |
| Grafana | 3000 | `GRAFANA_PORT` in `.env` |
| Node Exporter | 9100 | — |
| Postgres Exporter | 9187 | — |
