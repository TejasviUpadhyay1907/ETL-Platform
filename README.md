<div align="center">

# ⚡ Enterprise ETL & Data Quality Platform

**A production-grade, end-to-end data engineering platform built from first principles.**

[![CI](https://github.com/TejasviUpadhyay1907/ETL-Platform/actions/workflows/ci.yml/badge.svg)](https://github.com/TejasviUpadhyay1907/ETL-Platform/actions)
[![Tests](https://img.shields.io/badge/tests-1148%20passing-brightgreen)](#testing)
[![Coverage](https://img.shields.io/badge/coverage-79%25-brightgreen)](#testing)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-MIT-blue)](#license)
[![Version](https://img.shields.io/badge/version-1.0.0-blue)](CHANGELOG.md)

### 🌐 [Live Dashboard](https://etl-platform-kdkbvzas5q9fpuffvq8zs2.streamlit.app) &nbsp;|&nbsp; 📡 [Live API](https://etl-platform-api.onrender.com) &nbsp;|&nbsp; 📖 [Swagger UI](https://etl-platform-api.onrender.com/docs)

*Login: `admin` / `Admin1234!`*

</div>

---

## What Is This?

A complete data engineering platform that automatically processes raw business data through a **5-stage ETL pipeline**:

```
Upload CSV/Excel
       ↓
  1. Ingestion    → File parsing, deduplication, schema detection
  2. Validation   → 9 rule types, quality scoring (0–100), violation tracking
  3. Cleaning     → 7 strategies: nulls, dedup, formats, dates, business rules
  4. Transformation → 8 transformers: derived columns, type casting, feature engineering
  5. Loading      → PostgreSQL warehouse with upsert, incremental, bulk strategies
       ↓
Real-time Dashboard + Audit Trail
```

**In 2.3 seconds, 25,000 rows go from raw CSV to clean warehouse data with full lineage.**

---

## 🚀 Live Deployment

| Service | URL | Status |
|---------|-----|--------|
| **Operations Dashboard** | [etl-platform-kdkbvzas5q9fpuffvq8zs2.streamlit.app](https://etl-platform-kdkbvzas5q9fpuffvq8zs2.streamlit.app) | ✅ Live |
| **REST API** | [etl-platform-api.onrender.com](https://etl-platform-api.onrender.com) | ✅ Live |
| **Swagger UI** | [etl-platform-api.onrender.com/docs](https://etl-platform-api.onrender.com/docs) | ✅ Live |
| **Prometheus Metrics** | [etl-platform-api.onrender.com/metrics](https://etl-platform-api.onrender.com/metrics) | ✅ Live |

> **Note:** Free tier spins down after 15 min inactivity — first request takes ~30s to wake up.

**Demo credentials:** `admin` / `Admin1234!`

---

## ✨ Features

### ETL Pipeline
| Stage | What It Does |
|-------|-------------|
| **Ingestion** | CSV/Excel/ZIP upload, SHA-256 dedup, schema auto-detection |
| **Validation** | 9 validators: schema, nulls, duplicates, types, formats, statistical, categorical, business rules, referential integrity |
| **Cleaning** | 7 strategies: null fill, deduplication, string normalization, numeric cleaning, date standardization, categorical mapping, business rule fixes |
| **Transformation** | 8 transformers: type casting, date extraction, derived columns, business rules, feature engineering |
| **Loading** | 5 strategies: Upsert, Bulk Insert, Append, Replace, Incremental with full idempotency |

### Security
- JWT authentication (access + refresh tokens, 7-day rotation)
- 5 RBAC roles: Administrator, Data Engineer, Operator, Analyst, Viewer
- 16 granular permissions
- API key management (scoped: admin/pipeline/readonly)
- Rate limiting (60 req/min per user, configurable)
- bcrypt password hashing

### Observability
- Prometheus `/metrics` endpoint (8 metric families)
- Structured JSON logging with correlation IDs
- Pre-built Grafana dashboards (System Health, Pipeline Execution)
- 6 alert rules (APIDown, HighErrorRate, SlowResponse, etc.)

### Dashboard (10 pages)
| Page | Description |
|------|-------------|
| 🏠 Executive Overview | KPIs, system status, pipeline funnel, recent runs |
| 🔄 Pipeline Monitor | Live status, stage timeline (Gantt), cancel/retry |
| 📋 Pipeline History | Searchable, sortable, CSV/Excel export |
| 🎯 Data Quality | Quality gauges, dimension bars, violations table, trend charts |
| 📥 **Ingestion** | **File upload → instant pipeline execution** |
| 🏭 Warehouse | Load events, strategy distribution, metrics |
| 👥 User Administration | Users, roles, API keys management |
| 🔍 Audit Log | Event timeline, security events, export |
| ⚙️ Configuration | Pipeline definitions, system health |
| 🧹 Cleaning & ⚗️ Transformation | Stage-level analytics |

---

## 🛠 Technology Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI 0.115 + Uvicorn |
| Database | PostgreSQL 15 + SQLAlchemy 2.0 + Alembic |
| Data Processing | Pandas 2.2 + NumPy 2.0 |
| Authentication | JWT (python-jose) + bcrypt (passlib) |
| Dashboard | Streamlit 1.56 + Plotly 6.3 |
| Metrics | Prometheus Client 0.21 |
| Containerization | Docker + Docker Compose |
| Orchestration | Kubernetes-ready manifests |
| CI/CD | GitHub Actions (lint, test, coverage, security, docker build) |
| Monitoring | Prometheus + Grafana |

---

## ⚡ Quick Start

### Option 1 — Use the Live Demo (0 minutes)

1. Open: **https://etl-platform-kdkbvzas5q9fpuffvq8zs2.streamlit.app**
2. Login: `admin` / `Admin1234!`
3. Go to **📥 Ingestion** → download a sample file → upload it → watch the pipeline run

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
cp .env.example .env             # edit: set SECRET_KEY, JWT_SECRET

# 4. Start PostgreSQL
docker run -d --name etl_pg \
  -e POSTGRES_USER=etl_user \
  -e POSTGRES_PASSWORD=etl_password \
  -e POSTGRES_DB=etl_platform \
  -p 5432:5432 postgres:15-alpine

# 5. Setup & start
python scripts/setup_database.py
python scripts/start_dev.py --with-dashboard
```

| Service | URL |
|---------|-----|
| API | http://localhost:8001 |
| Swagger | http://localhost:8001/docs |
| Dashboard | http://localhost:8501 |

### Option 3 — Docker Compose

```bash
cp .env.example .env   # set SECRET_KEY, JWT_SECRET, DB_PASSWORD
docker-compose -f docker-compose.prod.yml up -d
docker-compose -f docker-compose.prod.yml exec api python scripts/setup_database.py
```

---

## 📁 Project Structure

```
ETL-Platform/
├── app/                        # Application source
│   ├── api/                    # FastAPI routers + schemas (62 endpoints)
│   │   ├── routers/            # auth, pipelines, ingest, quality, load, users...
│   │   ├── schemas/            # Pydantic request/response models
│   │   └── middleware/         # JWT auth, rate limiting
│   ├── auth/                   # JWT, bcrypt, RBAC, user service
│   ├── cleaning/               # Cleaning engine + 7 strategies
│   ├── core/                   # Config, exceptions, app factory
│   ├── database/               # 22 ORM models, 11 repositories, engine
│   ├── ingestion/              # CSV/Excel/ZIP readers, file detection
│   ├── loading/                # Warehouse loader + 5 strategies
│   ├── middleware/             # Logging, security headers, Prometheus metrics
│   ├── observability/          # Prometheus metrics definitions
│   ├── pipeline/               # Orchestration engine, checkpoints, retry
│   ├── transformation/         # Transformation engine + 8 transformers
│   └── validation/             # Validation engine + 9 validators
│
├── dashboard/                  # Streamlit operations dashboard
│   ├── Home.py                 # Executive overview entry point
│   ├── pages/                  # 10 dashboard pages
│   └── utils/                  # API client, auth, charts, formatting
│
├── tests/                      # 1,148 tests
│   ├── unit/                   # Fast tests (SQLite, no external deps)
│   └── integration/            # API + DB tests
│
├── docker/                     # Dockerfiles, Nginx, Prometheus, Grafana configs
├── k8s/                        # Kubernetes manifests (Deployment, HPA, Ingress...)
├── migrations/                 # Alembic database migrations
├── scripts/                    # Setup, seed, backup utility scripts
├── benchmarks/                 # Performance benchmarks + Locust load tests
├── config/                     # YAML dataset configurations
└── docs/                       # 20 architecture + operational documents
```

---

## 🧪 Testing

```bash
# All unit tests (no DB required)
pytest tests/unit/ -q

# With coverage report
pytest tests/unit/ --cov=app --cov-report=term-missing

# Full suite
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
| CSV parse — 10,000 rows | ~0.8s (~12,500 rows/sec) |
| Full ETL pipeline — 25,000 rows | ~2.3 seconds |

---

## 🔐 Security

- Passwords hashed with **bcrypt** (rounds=12)
- JWT signed with **HS256**, configurable expiry
- API keys stored as **SHA-256 hashes** — plaintext shown once
- Rate limiting: 60 req/min / 1,000 req/hr per user
- Account locking after 5 consecutive failed logins
- OWASP API Top 10 compliant (see [SECURITY_CHECKLIST.md](docs/SECURITY_CHECKLIST.md))

---

## 📦 Deployment

### Render.com (current production)

The API is deployed on [Render.com](https://render.com) free tier with PostgreSQL.

For your own deployment:
```bash
# Fork/clone → connect to Render → set env vars → deploy
# See DEPLOYMENT_GUIDE.md for step-by-step instructions
```

### Docker / Kubernetes

```bash
# Production stack with monitoring
docker-compose -f docker-compose.prod.yml \
               -f docker-compose.monitoring.yml up -d

# Kubernetes
kubectl apply -f k8s/
```

Full deployment guides: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [FIRST_TIME_SETUP.md](FIRST_TIME_SETUP.md) | Step-by-step setup guide (5 min) |
| [RUNNING_THE_PROJECT.md](RUNNING_THE_PROJECT.md) | All ways to run the platform |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Cloud deployment (AWS, GCP, Render, Docker) |
| [SYSTEM_FLOW.md](SYSTEM_FLOW.md) | Complete ETL data flow with diagrams |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common errors and fixes |
| [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) | Development setup, conventions, extensions |
| [docs/OPERATIONS_RUNBOOK.md](docs/OPERATIONS_RUNBOOK.md) | Incident response, maintenance |
| [docs/SECURITY_CHECKLIST.md](docs/SECURITY_CHECKLIST.md) | OWASP compliance, security review |
| [docs/INTERVIEW_PREP.md](docs/INTERVIEW_PREP.md) | Architecture Q&A, trade-offs, system design |
| [CHANGELOG.md](CHANGELOG.md) | Full version history |

---

## 🗺 Roadmap

| Version | Features |
|---------|---------|
| v1.1 | Background tasks (Celery + Redis), async pipeline execution |
| v1.2 | Multi-tenancy, workspace isolation |
| v2.0 | Distributed execution (Ray), streaming ingestion (Kafka) |

---

## 🤝 Contributing

See [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) for setup, coding standards, and how to add new dataset types, validators, cleaning strategies, and transformers.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

Built with ❤️ using FastAPI · SQLAlchemy · Streamlit · Plotly · Prometheus · PostgreSQL

**[⭐ Star this repo](https://github.com/TejasviUpadhyay1907/ETL-Platform)** if you find it useful!

</div>
