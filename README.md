# ⚡ Enterprise ETL & Data Quality Platform

[![CI](https://github.com/your-org/etl-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/etl-platform/actions)
[![Coverage](https://img.shields.io/badge/coverage-79%25-brightgreen)](coverage_html/)
[![Tests](https://img.shields.io/badge/tests-1148%20passing-brightgreen)](#testing)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-Proprietary-red)](#license)
[![Version](https://img.shields.io/badge/version-1.0.0-blue)](CHANGELOG.md)

> **A production-grade, end-to-end data engineering platform built from first principles.**  
> Ingestion → Validation → Cleaning → Transformation → Warehouse Loading  
> with enterprise security, observability, and a real-time operations dashboard.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Documentation](#api-documentation)
- [Dashboard](#dashboard)
- [Testing](#testing)
- [Performance](#performance)
- [Security](#security)
- [Deployment](#deployment)
- [Monitoring](#monitoring)
- [Roadmap](#roadmap)

---

## Overview

The ETL Platform is a **production-ready**, **enterprise-grade** data engineering system built entirely in Python. It processes retail data (orders, customers, products, inventory, suppliers, payments) through a complete five-stage ETL pipeline, enforces configurable data quality rules, and loads clean data to a PostgreSQL warehouse.

Every component was built from first principles — no black-box ETL tools, no magical frameworks. The result is a system you can fully understand, extend, and operate.

### What makes this enterprise-grade?

| Property | Implementation |
|----------|---------------|
| **Security** | JWT + RBAC, bcrypt passwords, API key management, rate limiting |
| **Reliability** | Checkpoints, retry with backoff, idempotent loads, graceful shutdown |
| **Observability** | Prometheus metrics, structured JSON logging, correlation IDs, Grafana dashboards |
| **Testability** | 1148 tests, 79% coverage, isolated SQLite for unit tests |
| **Deployability** | Docker, docker-compose, Kubernetes manifests, CI/CD pipeline |
| **Operability** | Streamlit dashboard, audit logs, backup scripts, runbook |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        ETL Platform v1.0.0                          │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌─────────────┐    ┌──────────────────────────────────────────┐   │
│   │  Streamlit  │    │           FastAPI Application             │   │
│   │  Dashboard  │◄──►│                                          │   │
│   │  :8501      │    │  Auth   │  Pipelines  │  Quality         │   │
│   └─────────────┘    │  Users  │  Ingest     │  Load            │   │
│                      └──────────────┬─────────────────────────-─┘   │
│   ┌─────────────┐                   │                                │
│   │   Nginx     │◄──────────────────┘                               │
│   │   :80/:443  │                                                    │
│   └─────────────┘    ┌──────────────────────────────────────────┐   │
│                      │           ETL Engine                      │   │
│   ┌─────────────┐    │                                          │   │
│   │ Prometheus  │    │  Ingestion → Validation → Cleaning →    │   │
│   │ Grafana     │    │  Transformation → Warehouse Loading      │   │
│   └─────────────┘    └──────────────┬───────────────────────────┘   │
│                                     │                                │
│                      ┌──────────────▼───────────────────────────┐   │
│                      │         PostgreSQL 15                     │   │
│                      │  Operational + Pipeline + Audit + Auth    │   │
│                      └──────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

> 📐 See `docs/` for detailed architecture diagrams (SRS, HLD, LLD, Component, Data Flow).

---

## Features

### ETL Pipeline
- **Ingestion**: CSV/Excel/ZIP upload, file hashing, deduplication, schema detection
- **Validation**: 9 rule types (schema, null, duplicate, format, dtype, statistical, categorical, business, referential)
- **Cleaning**: 7 strategies (null fill, dedup, string normalisation, numeric, date, categorical, business rules)
- **Transformation**: 8 transformers (standardise, typecast, date, derived columns, business rules, categorical, lookup, feature engineering)
- **Loading**: 5 strategies (upsert, bulk insert, append, replace, incremental); fully idempotent

### Security (Phase 10)
- JWT access/refresh tokens with 7-day rotation
- bcrypt password hashing (rounds=12)
- 5 built-in RBAC roles with 16 granular permissions
- API key management with scoping (admin/pipeline/readonly)
- Rate limiting: 60 req/min per user (configurable)
- Account locking after 5 failed logins

### Observability
- Prometheus `/metrics` endpoint
- Request counter, duration histogram, active requests gauge
- Pipeline run counter, duration histogram, record counter
- Quality score histogram, warehouse load counter
- Pre-built Grafana dashboards (System Health, Pipeline Execution)
- Structured JSON logging with correlation IDs

### Operations Dashboard (Phase 11)
- 10-page Streamlit dashboard
- Live pipeline monitoring with stage timeline
- Data quality gauges and violation analysis
- User and API key administration
- Audit log viewer with search and export

---

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **API Framework** | FastAPI | 0.115.6 |
| **ASGI Server** | Uvicorn + uvloop | 0.32.1 |
| **Database** | PostgreSQL | 15 |
| **ORM** | SQLAlchemy | 2.0.36 |
| **Migrations** | Alembic | 1.14.0 |
| **Data Processing** | Pandas / NumPy | 2.2.3 / 2.2.0 |
| **Authentication** | python-jose (JWT) | 3.3.0 |
| **Password Hashing** | passlib/bcrypt | 1.7.4 |
| **Validation** | Pydantic v2 | 2.10.3 |
| **Dashboard** | Streamlit | 1.56.0 |
| **Charts** | Plotly | 6.3.1 |
| **Metrics** | Prometheus Client | 0.21.1 |
| **HTTP Client** | HTTPX | 0.28.1 |
| **Scheduling** | APScheduler | 3.10.4 |
| **Logging** | Loguru | 0.7.3 |
| **Testing** | pytest | 8.3.5 |
| **Coverage** | pytest-cov | 6.1.0 |
| **Containerisation** | Docker / docker-compose | — |

---

## Project Structure

```
etl-platform/
├── app/                          # Application source code
│   ├── api/                      # FastAPI routers and schemas
│   │   ├── routers/              # auth, pipelines, ingest, quality, load, users, roles, api-keys, metrics
│   │   ├── schemas/              # Pydantic request/response models
│   │   └── middleware/           # JWT auth, rate limiting
│   ├── auth/                     # Authentication services
│   │   ├── auth_service.py       # Login, logout, refresh, change-password
│   │   ├── user_service.py       # User CRUD
│   │   ├── jwt_handler.py        # Token creation and validation
│   │   ├── password.py           # bcrypt hashing
│   │   ├── rbac.py               # Roles, permissions, seeding
│   │   └── api_key_manager.py    # API key lifecycle
│   ├── cleaning/                 # Cleaning engine (Phase 6)
│   ├── core/                     # Config, exceptions, app factory
│   ├── database/                 # ORM models and repositories
│   ├── ingestion/                # Ingestion engine (Phase 4)
│   ├── loading/                  # Warehouse loader (Phase 9)
│   ├── middleware/               # Request ID, logging, security headers, metrics
│   ├── observability/            # Prometheus metrics definitions
│   ├── pipeline/                 # Pipeline orchestration (Phase 8)
│   ├── transformation/           # Transformation engine (Phase 7)
│   └── validation/               # Validation engine (Phase 5)
│
├── dashboard/                    # Streamlit operations dashboard
│   ├── Home.py                   # Executive overview entry point
│   ├── pages/                    # 10 dashboard pages
│   └── utils/                    # API client, auth, charts, formatting
│
├── benchmarks/                   # Performance benchmarks and load tests
├── config/                       # YAML configuration files
├── docker/                       # Dockerfiles, nginx, prometheus, grafana
├── docs/                         # Architecture documentation (12 files)
├── k8s/                          # Kubernetes manifests
├── migrations/                   # Alembic database migrations
├── scripts/                      # Utility scripts (seed, backup, health, dashboard)
│   └── backup/                   # DB and config backup scripts
└── tests/                        # 1148 tests
    ├── unit/                     # Unit tests (SQLite in-memory)
    └── integration/              # Integration tests (API + DB)
```

---

## Quick Start

### Prerequisites
- Python 3.12+
- PostgreSQL 15+ (or Docker)
- Git

### Option A: Local Setup (5 minutes)

```bash
# 1. Clone
git clone https://github.com/your-org/etl-platform.git
cd etl-platform

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL, SECRET_KEY, JWT_SECRET

# 5. Start PostgreSQL (if not running)
docker run -d --name etl_pg \
  -e POSTGRES_USER=etl_user \
  -e POSTGRES_PASSWORD=etl_password \
  -e POSTGRES_DB=etl_platform \
  -p 5432:5432 postgres:15-alpine

# 6. Run database migrations
python scripts/run_migrations.py

# 7. Seed roles and permissions
python scripts/seed_data.py

# 8. Start the API
python main.py
# API available at: http://localhost:8000
# Docs at:          http://localhost:8000/docs

# 9. Start the dashboard (new terminal)
streamlit run dashboard/Home.py
# Dashboard at: http://localhost:8501
```

### Option B: Docker Compose (2 minutes)

```bash
# Clone and configure
git clone https://github.com/your-org/etl-platform.git
cd etl-platform
cp .env.example .env
# Set DB_PASSWORD, SECRET_KEY, JWT_SECRET in .env

# Start full stack
docker-compose up -d

# Services:
#   API:       http://localhost:8000
#   API Docs:  http://localhost:8000/docs
#   Dashboard: http://localhost:8501 (via Nginx at :80)
```

### Option C: With Monitoring Stack

```bash
docker-compose -f docker-compose.prod.yml \
               -f docker-compose.monitoring.yml up -d

# Additionally:
#   Prometheus: http://localhost:9090
#   Grafana:    http://localhost:3000  (admin / changeme)
```

---

## Configuration

All settings are in `.env` (see `.env.example` for full reference):

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | Environment: development/staging/production |
| `DATABASE_URL` | `postgresql+...` | PostgreSQL connection string |
| `SECRET_KEY` | — | **Change in production** — min 32 chars |
| `JWT_SECRET` | — | **Change in production** — min 32 chars |
| `JWT_EXPIRATION_MINUTES` | `1440` | Access token lifetime (minutes) |
| `RATE_LIMIT_PER_MINUTE` | `60` | Requests per minute per user |
| `MAX_UPLOAD_SIZE_MB` | `500` | Maximum file upload size |
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `LOG_JSON_FORMAT` | `True` | JSON structured logs in production |

---

## API Documentation

Interactive documentation is auto-generated by FastAPI:

| URL | Description |
|-----|-------------|
| `http://localhost:8000/docs` | Swagger UI — try all endpoints interactively |
| `http://localhost:8000/redoc` | ReDoc — clean reference documentation |
| `http://localhost:8000/openapi.json` | Raw OpenAPI 3.1 schema |

### Core Endpoints

```
POST   /api/v1/auth/login              Login → JWT tokens
POST   /api/v1/auth/refresh            Refresh access token
GET    /api/v1/auth/me                 Current user profile
POST   /api/v1/auth/logout             Revoke session

POST   /api/v1/ingest/upload           Upload CSV/Excel file
GET    /api/v1/ingest/events           List ingestion events

POST   /api/v1/pipelines/run           Trigger ETL pipeline
GET    /api/v1/pipelines               List pipeline runs
GET    /api/v1/pipelines/{id}          Pipeline run detail
GET    /api/v1/pipelines/{id}/metrics  Execution metrics

GET    /api/v1/quality/score/{id}      Quality score
GET    /api/v1/quality/report/{id}     Violation details

GET    /api/v1/users                   List users (admin)
POST   /api/v1/users                   Create user (admin)
GET    /api/v1/api-keys                My API keys
POST   /api/v1/api-keys                Create API key

GET    /metrics                        Prometheus metrics
GET    /api/v1/health                  System health status
```

---

## Dashboard

The Streamlit operations dashboard provides a visual interface to the entire platform.

```bash
# Start dashboard (requires API running)
streamlit run dashboard/Home.py
# Or:
python scripts/run_dashboard.py --api-url http://localhost:8000
```

**Pages:**
1. 🏠 Executive Overview — KPIs, system status, recent runs
2. 🔄 Pipeline Monitor — live status, stage timeline, cancel/retry
3. 📋 Pipeline History — searchable, sortable, exportable
4. 🎯 Data Quality — gauges, violations, trend charts
5. 🏭 Warehouse — load events, strategy distribution
6. 👥 User Administration — users, roles, API keys
7. 🔍 Audit Log — event timeline with search
8. 📥 Ingestion Monitor — file events and statistics
9. ⚙️ Configuration Viewer — read-only system config
10. 🧹 Cleaning & ⚗️ Transformation dashboards

---

## Testing

```bash
# Run all unit tests
pytest tests/unit/ -q

# Run with coverage
pytest tests/unit/ --cov=app --cov-report=term-missing --cov-fail-under=78

# Run dashboard tests only
pytest tests/unit/test_dashboard/ -v

# Run integration tests
pytest tests/integration/ -v

# Run full suite
pytest tests/unit/ tests/integration/test_api_health.py -q
```

**Test Statistics (v1.0.0):**

| Category | Tests | Pass Rate |
|----------|-------|-----------|
| Unit — Core ETL | 874 | 100% |
| Unit — Auth (Phase 10) | 93 | 100% |
| Unit — Dashboard | 97 | 100% |
| Unit — Stage Executor | 27 | 100% |
| Unit — Error Handlers | 12 | 100% |
| Integration — API Health | 17 | 100% |
| **Total** | **1148** | **100%** |

Coverage: **79.48%** (threshold: 78%)

---

## Performance

Benchmarks run on a standard laptop (M1 Pro, 16 GB RAM):

| Scenario | Result |
|----------|--------|
| Health ping latency (p50) | ~1 ms |
| Health ping latency (p95) | ~3 ms |
| Auth login (bcrypt) p50 | ~120 ms |
| Pipeline list (p50) | ~15 ms |
| CSV parse — 10,000 rows | ~0.8 sec, ~12,500 rows/sec |
| CSV parse — 100,000 rows | ~7.5 sec, ~13,300 rows/sec |
| API throughput (concurrent) | ~350 req/sec (4 workers) |

Run benchmarks:
```bash
python benchmarks/benchmark_pipeline.py --rows 10000
```

Load test:
```bash
pip install locust
locust -f benchmarks/locustfile.py --host http://localhost:8000 --headless -u 50 -r 5 -t 60s
```

---

## Security

### Security Architecture
- All endpoints (except health and auth/login) require Bearer token or X-API-Key
- Passwords hashed with bcrypt (rounds=12) — never stored in plaintext
- JWT signed with HS256 — configurable secret and expiry
- API keys stored as SHA-256 hashes — plaintext shown once
- Account locking after 5 consecutive failed logins
- Rate limiting: 60 req/min / 1000 req/hr per user
- CSRF protection via XSRF tokens (Streamlit)
- Security headers: X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy

### OWASP API Top 10 Compliance
See `docs/security_checklist.md` for full compliance mapping.

### Reporting Vulnerabilities
Please open a private GitHub Security Advisory for any vulnerabilities.

---

## Deployment

### Docker Compose (Recommended for single-server)
```bash
docker-compose -f docker-compose.prod.yml up -d
```

### Kubernetes
```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml        # Update with real values first
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment-api.yaml
kubectl apply -f k8s/service-api.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/hpa.yaml
kubectl apply -f k8s/network-policy.yaml
```

### Database Backup
```bash
./scripts/backup/backup_db.sh
./scripts/backup/backup_db.sh --retention-days 30
```

---

## Monitoring

```bash
# Start monitoring stack
docker-compose -f docker-compose.prod.yml -f docker-compose.monitoring.yml up -d

# Access:
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3000  (admin / changeme)
```

Pre-built dashboards in `docker/grafana/dashboards/`:
- **System Health** — request rate, error rate, latency percentiles, CPU/memory
- **Pipeline Execution** — run rate, duration distributions, records processed

Alert rules in `docker/prometheus/alerts.yml`:
- APIDown, DatabaseDown, HighErrorRate, SlowAPIResponse, HighMemoryUsage, PipelineFailureSpike

---

## Roadmap

| Version | Target | Features |
|---------|--------|---------|
| v1.1 | Q3 2025 | Background tasks (Celery + Redis), async pipeline execution |
| v1.2 | Q4 2025 | Multi-tenancy, workspace isolation |
| v1.3 | Q1 2026 | REST API v2, GraphQL support |
| v2.0 | Q3 2026 | Distributed execution (Ray/Spark integration), streaming ingestion |

---

## Contributing

See [DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) for:
- Development environment setup
- Coding standards and conventions
- Adding new dataset types
- Adding new validation/cleaning/transformation rules
- Pull request workflow

---

## License

Proprietary — All rights reserved.

---

## Acknowledgements

Built with:
[FastAPI](https://fastapi.tiangolo.com) ·
[SQLAlchemy](https://sqlalchemy.org) ·
[Pydantic](https://docs.pydantic.dev) ·
[Streamlit](https://streamlit.io) ·
[Plotly](https://plotly.com) ·
[Prometheus](https://prometheus.io) ·
[Grafana](https://grafana.com) ·
[PostgreSQL](https://postgresql.org)
