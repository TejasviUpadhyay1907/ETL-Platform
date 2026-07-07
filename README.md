<div align="center">

# ⚡ Enterprise ETL & Data Quality Platform

**A production-grade, end-to-end data engineering platform built from first principles.**

[![CI](https://github.com/TejasviUpadhyay1907/ETL-Platform/actions/workflows/ci.yml/badge.svg)](https://github.com/TejasviUpadhyay1907/ETL-Platform/actions)
[![Tests](https://img.shields.io/badge/tests-1148%20passing-brightgreen)](#testing)
[![Coverage](https://img.shields.io/badge/coverage-79%25-brightgreen)](#testing)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-blue)](docs/CHANGELOG.md)

### 🌐 [Live Dashboard](https://etl-platform-kdkbvzas5q9fpuffvq8zs2.streamlit.app) &nbsp;|&nbsp; 📡 [Live API](https://etl-platform-api.onrender.com) &nbsp;|&nbsp; 📖 [Swagger UI](https://etl-platform-api.onrender.com/docs)

*Demo credentials: `admin` / `Admin1234!`*

</div>

---

## What Is This?

A complete data engineering platform that automatically processes raw business data through a **5-stage ETL pipeline**:

```
Upload CSV / Excel
        ↓
  1. Ingestion      → File parsing, SHA-256 deduplication, schema auto-detection
  2. Validation     → 9 rule types, quality scoring (0–100), violation tracking
  3. Cleaning       → 7 strategies: nulls, dedup, formats, dates, business rules
  4. Transformation → 8 transformers: derived columns, type casting, feature engineering
  5. Loading        → PostgreSQL warehouse with upsert, incremental, and bulk strategies
        ↓
  Real-time Dashboard + Full Audit Trail
```

**In ~2.3 seconds, 25,000 rows go from raw CSV to clean warehouse data with full lineage.**

---

## 🚀 Live Deployment

| Service | URL | Notes |
|---------|-----|-------|
| **Operations Dashboard** | [etl-platform-kdkbvzas5q9fpuffvq8zs2.streamlit.app](https://etl-platform-kdkbvzas5q9fpuffvq8zs2.streamlit.app) | Streamlit Cloud |
| **REST API** | [etl-platform-api.onrender.com](https://etl-platform-api.onrender.com) | Render.com free tier |
| **Swagger UI** | [etl-platform-api.onrender.com/docs](https://etl-platform-api.onrender.com/docs) | Interactive API explorer |
| **Prometheus Metrics** | [etl-platform-api.onrender.com/metrics](https://etl-platform-api.onrender.com/metrics) | Raw metrics scrape |

> **Free tier note:** The API spins down after 15 min of inactivity. First request takes ~30s to wake up.

**Demo credentials:** `admin` / `Admin1234!`

---

## ✨ Feature Overview

### ETL Pipeline

| Stage | What It Does |
|-------|-------------|
| **Ingestion** | CSV / Excel / ZIP upload, SHA-256 deduplication, schema auto-detection, file lineage |
| **Validation** | 9 validators: schema, nulls, duplicates, types, formats, statistical, categorical, business rules, referential integrity |
| **Cleaning** | 7 strategies: null fill, deduplication, string normalization, numeric cleaning, date standardization, categorical mapping, business rule fixes |
| **Transformation** | 8 transformers: type casting, date extraction, derived columns, business rules, feature engineering |
| **Loading** | 5 strategies: Upsert, Bulk Insert, Append, Replace, Incremental — all idempotent per `pipeline_run_id` |

### Security & Auth

- JWT authentication (access + refresh tokens, 7-day rotation)
- 5 RBAC roles: Administrator, Data Engineer, Operator, Analyst, Viewer
- 16 granular permissions
- API key management (scoped: `admin` / `pipeline` / `readonly`)
- Rate limiting: 60 req/min per user (sliding window, configurable)
- bcrypt password hashing (rounds=12), account locking after 5 failed logins

### Observability

- Prometheus `/metrics` endpoint (8 metric families: HTTP, pipeline, quality, warehouse, auth)
- Structured JSON logging with correlation IDs
- Pre-built Grafana dashboards (System Health, Pipeline Execution)
- 6 Prometheus alert rules: `APIDown`, `HighErrorRate`, `SlowResponse`, `DatabaseDown`, `HighMemory`, `PipelineFailureSpike`

### Operations Dashboard (10 pages)

| Page | Description |
|------|-------------|
| 🏠 Executive Overview | KPIs, system status, pipeline funnel, recent runs |
| 🔄 Pipeline Monitor | Live status, stage timeline (Gantt), cancel / retry |
| 📋 Pipeline History | Searchable, sortable, CSV/Excel export |
| 🎯 Data Quality | Quality gauges, dimension bars, violations table, trend charts |
| 📥 **Ingestion** | **File upload → instant full pipeline execution** |
| 🏭 Warehouse | Load events, strategy distribution, throughput metrics |
| 👥 User Administration | Users, roles, API keys CRUD |
| 🔍 Audit Log | Event timeline, severity distribution, export |
| ⚙️ Configuration | Pipeline definitions, system health |
| 🧹 Cleaning / ⚗️ Transformation | Stage-level analytics |

---

## ⚡ Quick Start

### Option 1 — Live Demo (0 minutes)

1. Open **https://etl-platform-kdkbvzas5q9fpuffvq8zs2.streamlit.app**
2. Login: `admin` / `Admin1234!`
3. Go to **📥 Ingestion** → upload a file from `data/sample/` → watch the pipeline run live

### Option 2 — Run Locally (5 minutes)

```bash
# 1. Clone
git clone https://github.com/TejasviUpadhyay1907/ETL-Platform.git
cd ETL-Platform

# 2. Install
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env             # set SECRET_KEY and JWT_SECRET

# 4. Start PostgreSQL
docker run -d --name etl_pg \
  -e POSTGRES_USER=etl_user \
  -e POSTGRES_PASSWORD=etl_password \
  -e POSTGRES_DB=etl_platform \
  -p 5432:5432 postgres:15-alpine

# 5. Setup DB and start
python scripts/setup_database.py
python scripts/start_dev.py --with-dashboard
```

| Service | Local URL |
|---------|-----------|
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| Dashboard | http://localhost:8501 |

### Option 3 — Docker Compose

```bash
cp .env.example .env
docker-compose -f docker-compose.prod.yml up -d
docker-compose -f docker-compose.prod.yml exec api python scripts/setup_database.py
```

Add monitoring (Prometheus + Grafana):

```bash
docker-compose -f docker-compose.prod.yml \
               -f docker-compose.monitoring.yml up -d
```

---

## 📁 Project Structure

```
ETL-Platform/
│
├── app/                        # Application source
│   ├── api/                    # FastAPI routers + schemas (62 endpoints)
│   │   ├── routers/            # auth, pipelines, ingest, quality, load, users…
│   │   ├── schemas/            # Pydantic request/response models
│   │   └── middleware/         # JWT auth, rate limiting
│   ├── auth/                   # JWT handler, bcrypt, RBAC, user service
│   ├── cleaning/               # Cleaning engine + 7 strategies
│   ├── core/                   # Config, exceptions, app factory
│   ├── database/               # 22 ORM models, 11 repositories, engine
│   ├── ingestion/              # CSV/Excel/ZIP readers, file detection
│   ├── loading/                # Warehouse loader + 5 strategies
│   ├── middleware/             # Logging, security headers, Prometheus
│   ├── observability/          # Prometheus metrics definitions
│   ├── pipeline/               # Orchestration engine, checkpoints, retry
│   ├── transformation/         # Transformation engine + 8 transformers
│   └── validation/             # Validation engine + 9 validators
│
├── dashboard/                  # Streamlit operations dashboard
│   ├── Home.py                 # Entry point (executive overview)
│   ├── pages/                  # 10 numbered dashboard pages
│   └── utils/                  # api_client, auth, charts, formatting
│
├── tests/                      # 1,148 tests
│   ├── unit/                   # Fast tests (SQLite, no external deps)
│   └── integration/            # API + DB integration tests
│
├── docker/                     # Dockerfiles, Nginx, Prometheus, Grafana configs
├── k8s/                        # Kubernetes manifests (Deployment, HPA, Ingress…)
├── migrations/                 # Alembic database migrations
├── scripts/                    # Setup, seed, backup, and utility scripts
├── benchmarks/                 # Performance benchmarks + Locust load tests
├── config/                     # YAML dataset configurations
├── data/sample/                # Ready-to-upload sample CSV files
├── docs/                       # Architecture docs, guides, runbooks
│
├── main.py                     # API entry point
├── start.sh                    # Render.com start script
├── requirements.txt            # Production dependencies
├── docker-compose.prod.yml     # Production Docker Compose
└── docker-compose.monitoring.yml # Prometheus + Grafana stack
```

---

## 🧪 Testing

```bash
# All unit tests (no DB required)
pytest tests/unit/ -q

# With coverage report
pytest tests/unit/ --cov=app --cov-report=term-missing

# Full suite (requires PostgreSQL)
pytest tests/unit/ tests/integration/test_api_health.py -q
```

| Category | Tests | Status |
|----------|-------|--------|
| Unit — ETL Engines | 874 | ✅ 100% |
| Unit — Auth (JWT, RBAC) | 93 | ✅ 100% |
| Unit — Dashboard | 97 | ✅ 100% |
| Integration — API | 17 | ✅ 100% |
| **Total** | **1,148** | **✅ 100%** |

**Coverage: 79.48%** (threshold: 78%)

---

## 📊 Performance

| Scenario | Result |
|----------|--------|
| Health ping (p50) | ~1 ms |
| Login with bcrypt (p50) | ~120 ms |
| Pipeline list (p50) | ~15 ms |
| CSV parse — 10,000 rows | ~0.8 s (~12,500 rows/s) |
| Full ETL pipeline — 25,000 rows | ~2.3 seconds |

---

## 🛠 Technology Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI 0.115 + Uvicorn |
| Database | PostgreSQL 15 + SQLAlchemy 2.0 + Alembic |
| Data Processing | Pandas 2.2 + NumPy 2.0 |
| Authentication | JWT (python-jose) + bcrypt |
| Dashboard | Streamlit 1.56 + Plotly 6.3 |
| Metrics | Prometheus Client 0.21 |
| Containerization | Docker + Docker Compose |
| Orchestration | Kubernetes-ready manifests |
| CI/CD | GitHub Actions (lint, test, coverage, security, docker build) |
| Monitoring | Prometheus + Grafana |

---

## 🔐 Security

- Passwords hashed with **bcrypt** (rounds=12)
- JWT signed with **HS256**, configurable expiry
- API keys stored as **SHA-256 hashes** — plaintext shown once at creation
- Rate limiting: 60 req/min / 1,000 req/hr per user
- Account locking after 5 consecutive failed logins
- See [docs/SECURITY_CHECKLIST.md](docs/SECURITY_CHECKLIST.md) for the OWASP API Top 10 compliance checklist

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [docs/FIRST_TIME_SETUP.md](docs/FIRST_TIME_SETUP.md) | Step-by-step setup guide (5 min) |
| [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md) | Daily dev workflow, testing, DB management |
| [docs/RUNNING_THE_PROJECT.md](docs/RUNNING_THE_PROJECT.md) | All run options: local, Docker, K8s |
| [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) | Cloud deployment (Render, AWS, GCP, Docker) |
| [docs/SYSTEM_FLOW.md](docs/SYSTEM_FLOW.md) | End-to-end data flow with diagrams |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common errors and fixes |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Full version history (all 12 phases) |
| [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) | Conventions, extension points, architecture |
| [docs/OPERATIONS_RUNBOOK.md](docs/OPERATIONS_RUNBOOK.md) | Incident response, maintenance procedures |
| [docs/SECURITY_CHECKLIST.md](docs/SECURITY_CHECKLIST.md) | OWASP compliance, security review |
| [docs/INTERVIEW_PREP.md](docs/INTERVIEW_PREP.md) | Architecture Q&A, trade-offs, system design |
| [docs/PORTFOLIO_PACKAGE.md](docs/PORTFOLIO_PACKAGE.md) | Portfolio summary for hiring managers |

**Architecture deep-dives:**

| Document | Description |
|----------|-------------|
| [docs/01_SRS.md](docs/01_SRS.md) | Software Requirements Specification |
| [docs/02_HLD.md](docs/02_HLD.md) | High-Level Design |
| [docs/03_LLD.md](docs/03_LLD.md) | Low-Level Design |
| [docs/09_Database_Design.md](docs/09_Database_Design.md) | 22-table schema with ER diagram |
| [docs/10_Ingestion_Engine.md](docs/10_Ingestion_Engine.md) | Ingestion engine internals |
| [docs/11_Validation_Engine.md](docs/11_Validation_Engine.md) | Validation rule engine |
| [docs/12_Transformation_Engine.md](docs/12_Transformation_Engine.md) | Transformation engine |
| [docs/13_Cleaning_Engine.md](docs/13_Cleaning_Engine.md) | Cleaning strategies |
| [docs/14_Orchestration_Engine.md](docs/14_Orchestration_Engine.md) | Pipeline orchestrator |

---

## 📦 Deployment

### Render.com (current production)

The API is deployed on [Render.com](https://render.com) free tier with managed PostgreSQL.

```bash
# Fork → connect Render to your GitHub → set env vars → deploy
# start.sh handles: migrations, table creation, admin seeding, uvicorn start
```

Required environment variables:

```bash
DATABASE_URL=postgresql+psycopg2://...
SECRET_KEY=<32-char random>
JWT_SECRET=<32-char random>
API_KEY_SALT=<16-char random>
```

### Kubernetes

```bash
kubectl apply -f k8s/
```

All manifests are in `k8s/`: Namespace, Deployment, Service, Ingress, HPA, PVC, NetworkPolicy, ConfigMap, Secret.

---

## 🗺 Roadmap

| Version | Features |
|---------|---------|
| v1.1 | Background tasks (Celery + Redis), async pipeline execution |
| v1.2 | Multi-tenancy, workspace isolation |
| v2.0 | Distributed execution (Ray), streaming ingestion (Kafka) |

---

## 🤝 Contributing

See [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md) for setup, conventions, and how to add new
dataset types, validators, cleaning strategies, and transformers.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

Built with ❤️ using FastAPI · SQLAlchemy · Streamlit · Plotly · Prometheus · PostgreSQL

**[⭐ Star this repo](https://github.com/TejasviUpadhyay1907/ETL-Platform)** if you find it useful!

</div>
