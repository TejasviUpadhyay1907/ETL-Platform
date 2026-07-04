# Portfolio Package — ETL Platform v1.0.0

## 5-Minute Demo Guide

### Prerequisites
```bash
git clone https://github.com/your-org/etl-platform.git
cd etl-platform
docker-compose up -d   # 2 minutes to start
```

### Demo Script (5 minutes)

**Minute 1 — API & Health**
```bash
# Show the API is live
curl http://localhost:8000/api/v1/health | python -m json.tool

# Open Swagger in browser
open http://localhost:8000/docs
```
*Talking point: "Production FastAPI with 62 endpoints, JWT security, auto-generated OpenAPI docs."*

**Minute 2 — Authentication & RBAC**
```bash
# Login and get a token
curl -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "admin_password"}' | python -m json.tool
```
*Talking point: "JWT with refresh token rotation, bcrypt passwords, 5 RBAC roles with 16 permissions."*

**Minute 3 — Pipeline Execution**
```bash
# Trigger a pipeline (use a pre-prepared CSV in data/raw/)
TOKEN="<from login above>"
curl -X POST http://localhost:8000/api/v1/pipelines/run \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"dataset_type": "orders", "triggered_by": "demo"}' | python -m json.tool
```
*Talking point: "5-stage ETL: Ingestion → Validation → Cleaning → Transformation → Loading. Checkpoints allow retry from any stage."*

**Minute 4 — Dashboard**
```bash
open http://localhost:8501
# Login with admin/admin_password
# Navigate to Pipeline Monitor → click a run → show stage timeline
# Navigate to Data Quality → show quality gauge
```
*Talking point: "10-page real-time Streamlit dashboard with Plotly charts — pipeline monitoring, quality scores, user administration."*

**Minute 5 — Observability**
```bash
open http://localhost:9090   # Prometheus — show etl_pipeline_runs_total
open http://localhost:3000   # Grafana — show System Health dashboard
```
*Talking point: "Prometheus metrics, Grafana dashboards, 6 alert rules pre-configured."*

---

## Feature Showcase

### Core ETL

```python
# The entire ETL pipeline in one API call:
POST /api/v1/pipelines/run
{
    "dataset_type": "orders",
    "source_file_path": "/data/raw/orders_2024.csv",
    "triggered_by": "demo_user"
}

# Response includes:
# - pipeline_run_id (for tracking)
# - all 5 stage results
# - quality score (0-100)
# - records: total/valid/cleaned/loaded/failed
# - duration
```

### Data Quality

```python
# Quality report for a pipeline run:
GET /api/v1/quality/report/{pipeline_run_id}

# Returns violations with:
# - rule_code, severity (error/warning/info)
# - field_name, row_index
# - actual_value, expected
# - suggested_fix
```

### Security

```python
# API key with scoped access:
POST /api/v1/api-keys
{"name": "CI Pipeline Key", "scope": "pipeline"}

# Returns raw_key ONCE (only shown at creation):
{"raw_key": "etl_abc123...", "scope": "pipeline", "key_prefix": "etl_abc12"}

# Use in CI:
curl -H "X-API-Key: etl_abc123..." http://localhost:8000/api/v1/pipelines/run
```

---

## Key Engineering Decisions (for portfolio narrative)

1. **Built from first principles** — no black-box ETL frameworks. Every stage is custom Python that you can read, understand, and extend.

2. **Repository pattern** — business logic never touches the DB directly. This makes every service class testable with mock repositories.

3. **Strategy pattern for loading** — adding a new load strategy (e.g., S3 Parquet) means creating one new class that inherits `BaseLoadStrategy`. No existing code changes.

4. **Idempotent pipeline** — running the same file twice produces the same result. Achieved by keying on `pipeline_run_id` and using upsert by default.

5. **Progressive enhancement** — each phase built on the previous without breaking it. 1,148 tests ensure no regressions across 12 phases.

6. **Production-first mindset** — Docker, Kubernetes manifests, Prometheus metrics, Grafana dashboards, backup scripts, and a full security checklist — all included in v1.0.0.

---

## Sample API Calls

```bash
# Health check (no auth)
curl http://localhost:8000/api/v1/health/ping

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
     -d '{"username":"admin","password":"admin_password"}' \
     -H "Content-Type: application/json"

# List pipelines (authenticated)
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/pipelines?page_size=5

# Quality score
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/quality/score/$RUN_ID

# Prometheus metrics (no auth)
curl http://localhost:8000/metrics | head -30
```

---

## Project Highlights (for GitHub README / LinkedIn)

- 🏗️ **12 phases** built sequentially from architecture to production release
- 🔄 **5-stage ETL pipeline** — fully configurable, checkpointed, retryable
- 🔐 **Enterprise security** — JWT + RBAC + API keys + rate limiting
- 📊 **Real-time dashboard** — 10-page Streamlit app with Plotly charts
- 📈 **Prometheus + Grafana** — pre-built dashboards and alert rules
- ✅ **1,148 tests** — 100% pass rate, 79% coverage
- 🐳 **Docker + Kubernetes** — production-ready containerisation
- 📝 **Complete documentation** — SRS, HLD, LLD, runbook, developer guide

---

## Demo Datasets

Sample files for demonstration are in `tests/fixtures/`:
- `orders_sample.csv` — 1,000 sample orders
- `customers_sample.csv` — 500 sample customers

For a realistic demo with quality violations:
```bash
python scripts/seed_data.py --create-demo-files
```
