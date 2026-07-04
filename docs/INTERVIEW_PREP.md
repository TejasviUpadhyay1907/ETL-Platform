# Interview Preparation Guide — ETL Platform v1.0.0

## Project Summary (30-second pitch)

> "I built a production-grade ETL & Data Quality Platform from scratch in Python. It processes retail data through a five-stage pipeline — ingestion, validation, cleaning, transformation, and warehouse loading — with enterprise security (JWT + RBAC), a real-time Streamlit operations dashboard, and a full observability stack. It has 1,148 automated tests and is containerized with Docker and Kubernetes-ready manifests."

---

## Architecture Explanation

### How does data flow through the system?

```
File Upload (CSV/Excel)
    │
    ▼
IngestionService       — reads file, detects type, hashes content, stores raw copy
    │
    ▼
ValidationEngine       — runs 9 rule types, computes quality score (0–100), flags violations
    │
    ▼
CleaningEngine         — applies 7 strategies: fill nulls, dedup, normalise strings, fix dates…
    │
    ▼
TransformationEngine   — derives columns, casts types, applies business rules, lookups…
    │
    ▼
WarehouseLoader        — loads to PostgreSQL using configured strategy (upsert/bulk/append…)
    │
    ▼
PipelineResult         — audit log, metrics, quality score persisted; dashboard updated
```

### Why did you choose this architecture?

- **Separation of concerns**: each engine has exactly one responsibility
- **Testability**: every engine can be tested in isolation with mock inputs
- **Extensibility**: adding a new dataset type requires only a config file + ORM model
- **Reliability**: checkpoints allow resume from any stage after failure
- **Idempotency**: same file ingested twice → same result, no duplicates

---

## 50 Likely Interview Questions & Model Answers

### ETL / Data Engineering

**Q1: What is ETL and how did you implement each stage?**
- **Extract** (Ingestion): read CSV/Excel with pandas, detect schema, compute SHA-256 hash for deduplication
- **Transform** (Validation + Cleaning + Transformation): validate schema/rules, clean nulls/formats, derive business columns
- **Load**: write to PostgreSQL using configurable strategy (upsert ensures idempotency)

**Q2: How did you ensure data quality?**
I implemented 9 validator types: schema validation, null checks, duplicate detection, data type verification, format validation (email/phone/date), statistical outlier detection, categorical value checks, custom business rules, and referential integrity. Each produces a violation record with row index, field name, and suggested fix. The `QualityScorer` aggregates across 6 dimensions to produce a 0–100 score with letter grade.

**Q3: What is idempotency and how did you achieve it?**
Idempotency means running the same operation twice produces the same result. I achieved it by keying on `pipeline_run_id` — before loading, the `WarehouseLoader` queries `audit_log` for a prior `RECORD_LOADED` event with the same run ID. If found, it returns immediately with `idempotent_skip=True`. The upsert strategy also ensures no duplicates via conflict columns.

**Q4: How does the incremental load strategy work?**
It filters the DataFrame to only rows where the `watermark_column` (e.g., `updated_at` or `id`) is greater than the stored `watermark_value`. Only new or changed records are inserted, saving time and bandwidth on large tables.

**Q5: How did you handle large files efficiently?**
- Chunked reading with configurable `PIPELINE_CHUNK_SIZE` (default 10,000 rows)
- Batch loading with configurable `batch_size` (default 1,000 rows per batch)
- In-memory pandas DataFrames are bounded by chunk size
- Progress tracked per batch in `LoadBatchResult`

**Q6: What database design decisions did you make?**
- UUID primary keys everywhere (no sequential integers that leak row counts)
- Separate audit tables (immutable, INSERT-only) for compliance
- JSONB for flexible context data in audit logs
- Composite indexes on high-cardinality query patterns (dataset_type + status, run_id + event_type)
- Soft deletes on business tables to preserve audit trail

**Q7: How did you design the pipeline retry mechanism?**
The `RetryManager` wraps `PipelineExecutor` with configurable policies: max retries, backoff strategy (exponential/linear/immediate), and optional stage-scoped retries (e.g., only retry the `validation` stage). The `CheckpointManager` persists completed stages so retries resume from the last successful stage, not from scratch.

**Q8: What is the difference between your cleaning and transformation stages?**
- **Cleaning**: fixes data quality issues — fills nulls, removes duplicates, normalises formats, standardises dates. The output should be the same data as input, just correct.
- **Transformation**: adds business value — derives new columns (margin %, order total), aggregates, applies lookup tables, engineers features. The output may have more columns and different shapes than input.

---

### Security

**Q9: How does JWT authentication work in your platform?**
1. User POSTs credentials → `AuthService.login()` verifies bcrypt hash
2. Two tokens issued: access (60-min, signed HS256 JWT) + refresh (7-day)
3. Access token carries `sub` (user ID), `roles`, `scope=access`, `jti` (JWT ID)
4. `JWTAuthMiddleware` decodes token on every protected request, populates `request.state`
5. `get_current_user()` dependency reads from `request.state` and lazy-loads permissions from DB
6. Refresh token rotation: old session revoked when refresh is used → prevents replay attacks

**Q10: How does RBAC work in your system?**
Three-tier: User → Role → Permission. A user can have multiple roles; each role has multiple permissions (e.g., `pipelines:run`, `users:read`). The `require_permission()` dependency factory gates endpoints: it fetches the user's full permission set (aggregated from all roles) and raises 403 if the required permission is missing. Superusers bypass all checks.

**Q11: Why did you hash API keys with SHA-256 instead of bcrypt?**
API keys don't need the expensive bcrypt work factor because they're long random strings (64 hex chars = 256 bits of entropy). An attacker with the DB can't brute-force a 256-bit random key regardless of hash speed. bcrypt's slowness is designed for short human-chosen passwords. SHA-256 lookup is fast and correct for long random secrets.

---

### System Design

**Q12: How would you scale this system to handle 1M records/hour?**
1. Replace synchronous file ingestion with a message queue (Kafka/SQS) + worker pool
2. Horizontally scale the API with Kubernetes HPA (already have manifests)
3. Replace in-process rate limiter with Redis Sorted Sets
4. Use PostgreSQL read replicas for dashboard queries
5. Partition `audit_logs` by month (already designed for it — RANGE partition by `created_at`)
6. Add Redis caching for pipeline definitions and quality reports

**Q13: What would you do differently if starting over?**
1. Make the pipeline async from day one (async SQLAlchemy, asyncio stage execution)
2. Use a task queue (Celery) for pipeline execution — the API would not block on long-running ETL
3. Separate the metrics collection into a sidecar rather than middleware
4. Use an event sourcing pattern for pipeline state — easier to audit and replay

**Q14: What are the trade-offs of your technology choices?**
- **Pandas** over PySpark: simpler, works on a single server. Trade-off: limited to RAM-sized datasets.
- **PostgreSQL** over a data warehouse: supports both OLTP (user/pipeline metadata) and OLAP (quality reports). Trade-off: not optimised for columnar analytics.
- **Streamlit** over React: extremely fast to build, Python-native. Trade-off: less customisable UI, server-side rendering.
- **SQLite for tests** over testcontainers PostgreSQL: test speed (~50x faster). Trade-off: can't test PostgreSQL-specific features (JSONB operators, UUID type).

---

### Python / FastAPI

**Q15: How does FastAPI's dependency injection work?**
Dependencies are declared as function parameters annotated with `Depends()`. FastAPI resolves them at request time, handling the full dependency graph including caching (same request) and generator-based cleanup. I use it for: DB sessions (per-request, auto-closed), current user resolution, pagination params, permission guards.

**Q16: What is Pydantic v2 and how did you use it?**
Pydantic v2 is a data validation library using Rust-powered core. I use it for: request body validation (POST /users schema), response models (type-safe serialisation), configuration (BaseSettings loads from .env), and domain model validation. V2's `model_validator` and `field_validator` replace V1's `validator` decorator.

**Q17: How did you design the response envelope?**
Every endpoint returns `APIResponse[T]` — a generic Pydantic model with `success: bool`, `data: T | None`, `error: APIError | None`, and `meta: ResponseMeta`. This gives API consumers a consistent contract: always check `success` first, then read `data` or `error`. Paginated responses use `PaginatedResponse[T]` which adds a `pagination` block.

---

### Testing

**Q18: How did you achieve test isolation without a real PostgreSQL?**
The `sqlite_engine` fixture (session-scoped) creates an in-memory SQLite DB and runs `Base.metadata.create_all()`. JSONB columns are patched to JSON for SQLite compatibility. Each test gets a `db_session` fixture that wraps execution in a transaction and rolls back after the test. This gives complete isolation in ~50ms per test vs ~500ms with a real Postgres container.

**Q19: How did you mock the Streamlit session state in dashboard tests?**
`st.session_state` is a special dict-like object. I used `monkeypatch.setattr(st, "session_state", _FakeState(), raising=False)` to replace it with a plain dict subclass. This lets dashboard utility functions run in pytest without a Streamlit context.

**Q20: What is your test pyramid strategy?**
- **Unit tests** (95%): test individual classes in isolation with mock dependencies. Fast, cheap, run on every commit.
- **Integration tests** (5%): test the API layer end-to-end (HTTP → DB). Require a running server but catch contract issues.
- No end-to-end browser tests — the Streamlit dashboard is covered by unit tests on utilities and a real client test with dependency override.

---

### Monitoring & Operations

**Q21: What Prometheus metrics did you expose and why?**
- `etl_http_requests_total` (counter by method/endpoint/status) — to track error rates and throughput
- `etl_http_request_duration_seconds` (histogram) — to compute latency percentiles (p50/p95/p99)
- `etl_pipeline_runs_total` (counter by status/dataset) — to detect failure spikes
- `etl_pipeline_duration_seconds` (histogram) — to identify slow pipelines
- `etl_quality_score` (histogram) — to track data quality trends
- `etl_http_active_requests` (gauge) — to detect overload

**Q22: How would you set a meaningful SLO for this system?**
- **Availability**: 99.9% uptime for `/api/v1/health/ping`
- **Latency**: p95 < 500ms for read endpoints; p95 < 5s for pipeline trigger
- **Error rate**: < 0.1% 5xx over any 5-minute window
- **Pipeline success rate**: > 95% success over any 1-hour window

---

## Key Engineering Decisions

| Decision | Why | Trade-off |
|----------|-----|-----------|
| Multi-stage Docker build | Smaller production image (~200MB vs ~1.5GB) | Longer build time |
| Repository pattern | Decouples DB from business logic; testable | More boilerplate |
| Strategy pattern for loading | New load type = new class, no existing code changes | More classes |
| In-memory rate limiter | Zero dependencies, instant setup | Doesn't work multi-instance |
| Refresh token rotation | Prevents replay attacks after session theft | Slightly more complex client |
| Soft deletes | Preserves audit trail, GDPR "right to erasure" handled at app layer | Requires `is_deleted=False` filter everywhere |

---

## Resume Mapping

| Bullet Point | Evidence in Project |
|-------------|---------------------|
| "Designed and built a production ETL pipeline" | Phases 4–9, `app/pipeline/`, `app/ingestion/`, etc. |
| "Implemented enterprise security with JWT + RBAC" | Phase 10, `app/auth/`, `app/api/middleware/` |
| "Built REST APIs serving N endpoints" | 62 registered routes, Swagger at `/docs` |
| "Achieved 79% test coverage with 1,148 tests" | `pytest tests/unit/ --cov=app` |
| "Containerized with Docker and Kubernetes" | `docker/`, `k8s/`, `docker-compose.prod.yml` |
| "Implemented observability with Prometheus and Grafana" | `app/observability/`, `docker/prometheus/`, `docker/grafana/` |
| "Built real-time operations dashboard" | Phase 11, `dashboard/` |
| "Used SQLAlchemy with 22 ORM models and Alembic migrations" | `app/database/models/`, `migrations/` |
