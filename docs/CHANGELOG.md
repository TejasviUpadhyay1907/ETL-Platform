# Changelog

All notable changes to the ETL Platform are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/).

---

## [v1.0.0] — 2025-07-05

### 🎉 Initial Production Release

The first production release of the Enterprise ETL & Data Quality Platform.
Built across 12 phases over a complete engineering lifecycle.

---

### Added — Phase 1: Architecture
- Software Requirements Specification (SRS)
- High-Level Design (HLD) and Low-Level Design (LLD)
- ETL Workflow, Data Flow, and Component Diagrams
- Folder structure specification and development roadmap

### Added — Phase 2: Infrastructure
- FastAPI application factory with CORS, GZip, TrustedHost middleware
- Security headers middleware (X-Frame-Options, X-Content-Type-Options, HSTS)
- Request ID and structured JSON logging middleware
- Docker multi-stage production Dockerfile
- GitHub Actions CI (lint, typecheck, test, docker-build)
- Health check endpoints: `/health`, `/ping`, `/ready`, `/live`, `/version`

### Added — Phase 3: Database Design
- 15 PostgreSQL ORM models (customers, suppliers, products, inventory, orders, payments, pipeline runs, stage results, ingestion events, reports, audit logs, quality scores, validation failures, cleaning logs, reports)
- 11 repository classes with full CRUD
- Alembic migration infrastructure
- Seed data script

### Added — Phase 4: Ingestion Engine
- CSV and Excel (xlsx/xls) file readers
- ZIP archive extraction
- File type detection and dataset type resolution
- SHA-256 content hashing for deduplication
- `IngestionService` and `DirectoryWatcher`
- `RawFileStore` for persistent file management

### Added — Phase 5: Validation Engine
- 9 validators: schema, missing values, duplicates, data types, format, statistical, categorical, business rules, referential integrity
- `ValidationEngine` and `RuleRegistry`
- `QualityScorer` with dimension-level scoring (completeness, validity, consistency, uniqueness, integrity, timeliness)
- Quality threshold enforcement

### Added — Phase 6: Cleaning Engine
- 7 cleaning strategies: NullHandler, Deduplication, StringNormalizer, NumericCleaner, DateStandardizer, CategoricalCleaner, BusinessRuleCleaner
- `CleaningEngine` and `CleaningRegistry`
- Full Cleaning → Transformation chain

### Added — Phase 7: Transformation Engine
- 8 transformers: Standardization, TypeCast, Date, DerivedColumn, BusinessRule, Categorical, Lookup, FeatureEngineering
- `TransformationEngine` and `TransformationRegistry`

### Added — Phase 8: Pipeline Orchestration
- `PipelineExecutor` — complete Ingestion → Validation → Cleaning → Transformation → Load execution
- `StageExecutor` with timing, error capture, and event emission
- `CheckpointManager` — resume from any stage after failure
- `RetryManager` — exponential/linear/immediate backoff strategies
- `PipelineRegistry` — declarative pipeline definitions
- `TriggerService` — start/cancel/retry/resume API
- 7-state state machine (queued → running → succeeded/failed/cancelled/retrying)

### Added — Phase 9: Warehouse Loader
- 5 load strategies: BulkInsert, Upsert, Append, Replace, Incremental
- `WarehouseLoader` with idempotent execution (per pipeline_run_id)
- `LoadRegistry` — dataset-type-to-strategy mapping
- Full audit trail via `AuditLog`
- Load metrics: rows_inserted, rows_updated, rows_skipped, rows_failed, throughput

### Added — Phase 10: API Platform & Security
- JWT authentication (access + refresh tokens, 7-day rotation)
- bcrypt password hashing with transparent rehash on login
- RBAC: 5 built-in roles (administrator, data_engineer, operator, analyst, viewer)
- 16 granular permissions (pipelines:run, users:write, api_keys:create, …)
- API key management (scoped: admin/pipeline/readonly, SHA-256 hashed)
- User session tracking with refresh token revocation
- `JWTAuthMiddleware` — per-request token validation
- `RateLimitMiddleware` — sliding window per user/IP (configurable)
- 9 new routers: auth, users, roles, permissions, api-keys
- Account locking after 5 failed logins

### Added — Phase 11: Operations Dashboard
- Streamlit dashboard with 10 pages
- Executive Overview — KPIs, system status, pipeline funnel
- Pipeline Monitor — live runs, stage timeline, cancel/retry
- Pipeline History — searchable, sortable, CSV/Excel export
- Data Quality — gauges, dimension bars, violations table, trend charts
- Warehouse — load events, strategy distribution, metrics
- User Administration — users, roles, API keys CRUD
- Audit Log — event timeline, severity distribution, export
- Ingestion Monitor — file events, dataset distribution
- Configuration Viewer — pipeline definitions, health, API docs
- Cleaning and Transformation dashboards

### Added — Phase 12: Production Readiness
- Prometheus metrics endpoint (`/metrics`)
- `PrometheusMetricsMiddleware` — instruments all HTTP requests
- 8 metric families: HTTP counters, histograms, pipeline counters, quality gauges, warehouse counters, auth counters
- `docker-compose.prod.yml` — production stack with health checks, resource limits
- `docker-compose.monitoring.yml` — Prometheus + Grafana + node-exporter + postgres-exporter
- `Dockerfile.dashboard` — multi-stage Streamlit image
- Kubernetes manifests: Namespace, Deployment, Service, Ingress, HPA, PVC, NetworkPolicy, ConfigMap, Secret
- Grafana dashboard JSON (System Health, Pipeline Execution)
- Prometheus alert rules (APIDown, HighErrorRate, SlowAPIResponse, DatabaseDown, HighMemoryUsage, PipelineFailureSpike)
- Nginx production config with rate limiting, security headers, WebSocket proxy
- Database backup/restore shell scripts with retention rotation
- `benchmark_pipeline.py` — throughput and latency benchmarks
- `locustfile.py` — Locust load test scenarios (ReadOnly, Operations, AuthStress)
- Enhanced CI: security audit (pip-audit), SBOM generation, release workflow, coverage artifacts
- Complete documentation: README, Developer Guide, Operations Runbook, Portfolio Package, Interview Prep

---

### Test Coverage Summary (v1.0.0)
- **Total tests:** 1148
- **Pass rate:** 100% (1148/1148)
- **Coverage:** 79.48% (threshold: 78%)

### Known Limitations
- Dashboard auto-refresh uses Streamlit `time.sleep` — a separate WebSocket push mechanism would be more efficient at scale
- Rate limiter uses in-process dict — must be replaced with Redis for multi-instance deployments
- Prometheus metrics are in-process — counter resets on restart; use Pushgateway for batch jobs
- File ingestion is synchronous — large files (>100MB) will block the API worker; recommend Celery/background task integration for v1.1

### Upgrade Path from v1.0.0
- v1.1: Background task queue (Celery + Redis)
- v1.2: Multi-tenancy support
- v1.3: REST API v2 (backward-compatible)
- v2.0: Async pipeline execution (asyncio / Ray)

[v1.0.0]: https://github.com/TejasviUpadhyay1907/ETL-Platform/releases/tag/v1.0.0
