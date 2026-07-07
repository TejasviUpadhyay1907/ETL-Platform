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
├── app/                            # Application source code
│   ├── api/                        # FastAPI layer (62 endpoints)
│   │   ├── routers/                # auth, pipelines, ingest, quality, users…
│   │   ├── schemas/                # Pydantic request/response models
│   │   └── middleware/             # JWT auth, rate limiting
│   ├── auth/                       # JWT handler, bcrypt, RBAC, user service
│   ├── cleaning/                   # Cleaning engine + 7 strategies
│   ├── core/                       # Config, exceptions, app factory
│   ├── database/                   # 22 ORM models, 11 repositories, engine
│   │   ├── models/audit/           # AuditLog, CleaningLog, QualityScore
│   │   ├── models/auth/            # User, Role, Permission, ApiKey
│   │   ├── models/operational/     # Customers, Orders, Products, Payments…
│   │   └── models/pipeline/        # PipelineRun, StageResult, IngestionEvent
│   ├── ingestion/                  # CSV/Excel/ZIP readers, dedup, schema detect
│   │   └── readers/                # csv_reader, excel_reader, zip_reader
│   ├── loading/                    # Warehouse loader + 5 strategies
│   │   └── strategies/             # upsert, bulk_insert, append, replace, incr
│   ├── logging/                    # Structured JSON logging, audit emitter
│   ├── middleware/                 # Request ID, security headers, metrics
│   ├── observability/              # Prometheus metric definitions
│   ├── pipeline/                   # Orchestration engine, checkpoints, retry
│   ├── reporting/                  # Report builders, PDF/Excel export
│   ├── static/                     # Swagger UI assets (served locally)
│   ├── transformation/             # Transformation engine + 8 transformers
│   │   └── transformers/           # Per-dataset transformer implementations
│   ├── utils/                      # Date, file, hash, string utilities
│   └── validation/                 # Validation engine + 9 validators
│       └── rules/                  # Per-dataset rule implementations
│
├── dashboard/                      # Streamlit operations dashboard
│   ├── Home.py                     # Entry point — executive overview
│   ├── requirements.txt            # Streamlit Cloud deployment deps
│   ├── pages/                      # 10 dashboard pages (numbered)
│   └── utils/                      # api_client, auth, charts, formatting
│
├── tests/                          # 1,148 tests
│   ├── fixtures/                   # Sample CSV/Excel/ZIP test files
│   ├── unit/                       # Fast tests (SQLite, no external deps)
│   │   ├── test_core/              # Auth, config, DB, pipeline, validation…
│   │   ├── test_cleaning/          # Cleaning strategy unit tests
│   │   ├── test_transformation/    # Transformer unit tests
│   │   ├── test_validation/        # Validator unit tests
│   │   ├── test_reporting/         # Report builder tests
│   │   └── test_dashboard/         # Dashboard utility tests
│   └── integration/                # API + DB integration tests
│
├── config/                         # YAML dataset configurations
│   └── datasets/                   # Per-dataset: schema, rules, cleaning, transforms
│       └── {orders,customers,…}/   # orders/, customers/, products/, …
│
├── docker/                         # All Docker-related configs
│   ├── Dockerfile                  # Production API image
│   ├── Dockerfile.dashboard        # Streamlit dashboard image
│   ├── Dockerfile.dev              # Development image (hot-reload)
│   ├── grafana/                    # Grafana dashboards + provisioning
│   ├── nginx/                      # nginx.conf, nginx.prod.conf
│   ├── postgres/                   # PostgreSQL init.sql
│   └── prometheus/                 # prometheus.yml, alert rules
│
├── k8s/                            # Kubernetes manifests
│   ├── deployment-api.yaml         # API Deployment + HPA
│   ├── ingress.yaml                # Ingress with TLS
│   ├── network-policy.yaml         # Network isolation
│   └── …                          # namespace, service, pvc, secret, configmap
│
├── migrations/                     # Alembic database migrations
│   └── versions/                   # Versioned migration scripts
│
├── scripts/                        # Utility scripts
│   ├── setup_database.py           # One-command DB init + seed
│   ├── seed_data.py                # Load demo data (tiny/small/full)
│   ├── run_migrations.py           # Apply / rollback Alembic migrations
│   ├── start_dev.py                # Start API + dashboard together
│   ├── create_admin_user.py        # Create admin user manually
│   ├── create_api_key.py           # Generate scoped API key
│   ├── reset_database.py           # Wipe and re-init (dev only)
│   ├── verify_database.py          # Verify schema + connectivity
│   ├── health_check.py             # Quick API health probe
│   ├── status.py                   # Show pipeline + system status
│   ├── run_demo_pipeline.py        # Run end-to-end demo
│   ├── run_dashboard.py            # Start dashboard with options
│   ├── backup/                     # DB backup / restore shell scripts
│   └── dev/                        # Dev + debug utilities
│       ├── monitor.py              # Trigger + watch Render deploys
│       ├── test_upload_pipeline.py # End-to-end upload test
│       └── verify_prod_login.py    # Verify production credentials
│
├── benchmarks/                     # Performance testing
│   ├── benchmark_pipeline.py       # Throughput + latency benchmarks
│   └── locustfile.py               # Locust load test scenarios
│
├── data/                           # Data directories
│   ├── sample/                     # Ready-to-use demo CSV files ✓ (committed)
│   ├── raw/                        # Ingested files (runtime, gitignored)
│   ├── reports/                    # Generated reports (runtime, gitignored)
│   └── archive/                    # Archived files (runtime, gitignored)
│
├── docs/                           # All documentation (25+ files)
│   ├── README.md                   # Documentation index
│   ├── FIRST_TIME_SETUP.md         # Zero-to-running in 5 min
│   ├── LOCAL_DEVELOPMENT.md        # Daily dev workflow
│   ├── RUNNING_THE_PROJECT.md      # All run options
│   ├── DEPLOYMENT_GUIDE.md         # Cloud deployment guide
│   ├── SYSTEM_FLOW.md              # End-to-end data flow
│   ├── TROUBLESHOOTING.md          # Common errors + fixes
│   ├── DEVELOPER_GUIDE.md          # Conventions, extension points
│   ├── OPERATIONS_RUNBOOK.md       # Incident response, maintenance
│   ├── SECURITY_CHECKLIST.md       # OWASP API Top 10 compliance
│   ├── CHANGELOG.md                # Full version history
│   ├── INTERVIEW_PREP.md           # Architecture Q&A, trade-offs
│   ├── PORTFOLIO_PACKAGE.md        # Portfolio summary
│   └── 01_SRS.md … 17_*.md        # Architecture deep-dives (17 docs)
│
├── logs/                           # Application logs (runtime, gitignored)
│
├── main.py                         # FastAPI application entry point
├── alembic.ini                     # Alembic migrations config
├── pyproject.toml                  # Black, Ruff, Mypy, pytest config
├── requirements.txt                # Production dependencies (pinned)
├── requirements-render.txt         # Render.com build dependencies
├── requirements-dev.txt            # Development + test dependencies
├── render.yaml                     # Render.com service blueprint
├── start.sh                        # Render start: migrate → seed → uvicorn
├── build.sh                        # Render build: apt deps → pip install
├── Procfile                        # Process declarations (Heroku/Render)
├── docker-compose.yml              # Base Docker Compose
├── docker-compose.prod.yml         # Production stack (API + DB + Nginx)
├── docker-compose.dev.yml          # Dev stack (hot-reload)
├── docker-compose.monitoring.yml   # Monitoring stack (Prometheus + Grafana)
├── .env.example                    # Environment variable template
├── .dockerignore                   # Docker build exclusions
├── .editorconfig                   # Editor formatting rules
├── .pre-commit-config.yaml         # Pre-commit hooks (black, ruff, mypy)
└── LICENSE                         # MIT License
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
| [docs/15_Warehouse_Loader.md](docs/15_Warehouse_Loader.md) | Warehouse loader internals |
| [docs/16_API_Platform_Security.md](docs/16_API_Platform_Security.md) | API security design |
| [docs/17_Operations_Dashboard.md](docs/17_Operations_Dashboard.md) | Dashboard design |

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
