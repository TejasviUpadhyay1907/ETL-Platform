# System Flow — ETL Platform v1.0.0

Complete end-to-end walkthrough of every data path, API call, and module interaction.

---

## High-Level Flow

```
User / Client
    │
    ├─── HTTP Request
    │         │
    │    ┌────▼──────────────────────────────────────────┐
    │    │            Nginx (Port 80/443)                 │
    │    │   Rate limiting · TLS termination · Proxy      │
    │    └────┬──────────────┬────────────────────────────┘
    │         │              │
    │    ┌────▼────┐   ┌─────▼──────┐
    │    │  FastAPI │   │ Streamlit  │
    │    │  :8000   │   │ Dashboard  │
    │    │          │   │  :8501     │
    │    └────┬─────┘   └─────┬──────┘
    │         │               │  (API calls via httpx)
    │    ┌────▼───────────────┘
    │    │
    │    Middleware Stack (executed per request):
    │    1. PrometheusMetricsMiddleware  → records request metrics
    │    2. RateLimitMiddleware          → enforces per-user/IP limits
    │    3. JWTAuthMiddleware            → validates Bearer token / API key
    │    4. RequestIDMiddleware          → attaches X-Request-ID
    │    5. RequestLoggingMiddleware     → logs method/path/status/duration
    │    6. SecurityHeadersMiddleware    → sets X-Frame-Options etc.
    │    7. GZipMiddleware               → compresses responses > 1KB
    │    8. CORSMiddleware               → handles preflight and headers
    │         │
    │    ┌────▼──────────────────────────────────────────┐
    │    │             FastAPI Router                      │
    │    │  /auth  /pipelines  /ingest  /quality  /load   │
    │    │  /users  /roles  /api-keys  /metrics  /health  │
    │    └────┬──────────────────────────────────────────-┘
    │         │
    │    ┌────▼──────────────────────────────────────────┐
    │    │         Dependency Layer                        │
    │    │  get_db() → Session                            │
    │    │  get_current_user() → {user_id, roles, perms}  │
    │    │  require_permission("pipelines:run")           │
    │    └────┬──────────────────────────────────────────-┘
    │         │
    │    ┌────▼──────────────────────────────────────────┐
    │    │         Service / Engine Layer                  │
    │    │  AuthService · UserService · PipelineExecutor  │
    │    │  IngestionService · ValidationEngine           │
    │    │  CleaningEngine · TransformationEngine         │
    │    │  WarehouseLoader                               │
    │    └────┬──────────────────────────────────────────-┘
    │         │
    │    ┌────▼──────────────────────────────────────────┐
    │    │         Repository Layer                        │
    │    │  CustomerRepository · OrderRepository etc.     │
    │    │  IngestionEventRepository                      │
    │    └────┬──────────────────────────────────────────-┘
    │         │
    │    ┌────▼──────────────────────────────────────────┐
    │    │         PostgreSQL 15                           │
    │    │  22 tables across 4 domains:                   │
    │    │  operational · pipeline · audit · auth         │
    │    └────────────────────────────────────────────────┘
```

---

## ETL Pipeline Flow (Step by Step)

### Trigger: `POST /api/v1/pipelines/run`

```
Request: { "dataset_type": "orders", "source_file_path": "/data/raw/orders.csv" }

1. JWTAuthMiddleware
   └─ Decodes Bearer token → sets request.state.user_id, .roles

2. require_permission("pipelines:run")
   └─ Checks user has "pipelines:run" permission
   └─ Raises 403 if not

3. PipelineTriggerService.trigger()
   └─ Looks up pipeline definition from PipelineRegistry ("orders_pipeline")
   └─ Creates pipeline_run_id (UUID)
   └─ Calls PipelineExecutor.execute()

4. PipelineExecutor creates PipelineRun DB record
   └─ status = "running"
   └─ Emits PIPELINE_STARTED to audit_log

5. Stage 1: StageExecutor.run_ingestion()
   ├─ IngestionService.ingest(source_path, dataset_type)
   │   ├─ FileTypeDetector → detect extension + MIME type
   │   ├─ HashGenerator → SHA-256 of file content (dedup check)
   │   ├─ RawFileStore → copy to data/raw/
   │   ├─ CSVReader / ExcelReader → parse into pd.DataFrame
   │   ├─ DatasetTypeResolver → confirm/override dataset_type
   │   ├─ Persist IngestionEvent to DB
   │   └─ Return IngestionResult{success, dataset, file_metadata}
   └─ Emit STAGE_COMPLETED → audit_log

6. Stage 2: StageExecutor.run_validation()
   ├─ ValidationEngine.validate(dataset)
   │   ├─ RuleRegistry → load rules for "orders" dataset
   │   ├─ Run 9 validators in sequence:
   │   │   1. SchemaMissingColumnsValidator    — required columns present
   │   │   2. NullValueValidator               — null checks per column config
   │   │   3. DuplicateRowValidator            — duplicate records
   │   │   4. DataTypeValidator                — column dtype conformance
   │   │   5. FormatValidator                  — email/phone/date formats
   │   │   6. StatisticalOutlierValidator      — z-score / IQR checks
   │   │   7. CategoricalValidator             — allowed values per column
   │   │   8. BusinessRuleValidator            — custom rule expressions
   │   │   9. ReferentialIntegrityValidator    — FK consistency
   │   ├─ QualityScorer → 6-dimension score (completeness, validity, etc.)
   │   ├─ Persist DataQualityScore + ValidationFailure records
   │   └─ Return ValidationResult{success, quality_score, valid_df, rejected_df}
   └─ Emit STAGE_COMPLETED → audit_log

7. Stage 3: StageExecutor.run_cleaning()
   ├─ CleaningEngine.clean(validation_result)
   │   ├─ CleaningRegistry → load strategies for "orders"
   │   ├─ Apply 7 strategies in order:
   │   │   1. NullHandler          — fill / drop based on config
   │   │   2. Deduplication        — remove exact and fuzzy duplicates
   │   │   3. StringNormalizer     — trim, case-normalise, encode-fix
   │   │   4. NumericCleaner       — fix types, clip ranges, round
   │   │   5. DateStandardizer     — parse all date formats → ISO 8601
   │   │   6. CategoricalCleaner   — map variants to canonical values
   │   │   7. BusinessRuleCleaner  — custom domain-specific fixes
   │   ├─ ActionLogger → records every cleaning action taken
   │   └─ Return CleaningResult{success, cleaned_df, rows_dropped, actions}
   └─ Emit STAGE_COMPLETED → audit_log

8. Stage 4: StageExecutor.run_transformation()
   ├─ TransformationEngine.transform(cleaned_df, dataset_type)
   │   ├─ TransformationRegistry → load transformers for "orders"
   │   ├─ Apply 8 transformers in order:
   │   │   1. StandardizationTransformer  — column names, units
   │   │   2. TypeCastTransformer         — cast to target dtypes
   │   │   3. DateTransformer             — extract year/month/quarter
   │   │   4. DerivedColumnTransformer    — compute margin, total, age
   │   │   5. BusinessRuleTransformer     — tier classification, scoring
   │   │   6. CategoricalTransformer      — encode, map labels
   │   │   7. LookupTransformer           — join reference data
   │   │   8. FeatureEngineeringTransformer — ML-ready features
   │   └─ Return TransformationResult{success, transformed_df, added_columns}
   └─ Emit STAGE_COMPLETED → audit_log

9. Stage 5: StageExecutor.run_load()
   ├─ WarehouseLoader.load(transformed_df, dataset_type, pipeline_run_id)
   │   ├─ Idempotency check → query audit_log for prior RECORD_LOADED
   │   ├─ LoadRegistry → resolve strategy + target table for "orders"
   │   │   Default: UpsertStrategy, table="orders"
   │   ├─ UpsertStrategy.execute(df, target_table)
   │   │   ├─ Split into batches (default 1000 rows)
   │   │   ├─ For each batch: INSERT ... ON CONFLICT DO UPDATE
   │   │   └─ Record LoadBatchResult per batch
   │   ├─ Build LoadReport with metrics
   │   ├─ Persist RECORD_LOADED to audit_log
   │   ├─ Update pipeline_runs.loaded_records
   │   └─ Return LoadResult{success, rows_inserted, rows_updated, strategy_used}
   └─ Emit STAGE_COMPLETED → audit_log

10. PipelineExecutor finalizes
    ├─ Build PipelineMetrics (duration, records by stage, quality)
    ├─ Update PipelineRun status → "succeeded"
    ├─ Emit PIPELINE_COMPLETED → audit_log
    └─ Return PipelineResult to API
```

---

## Authentication Flow

```
POST /api/v1/auth/login
  Body: {username, password}
  │
  ├─ AuthService._get_user_by_username_or_email()
  │   └─ SELECT * FROM users WHERE username = ? OR email = ?
  │
  ├─ AuthService._check_login_allowed()
  │   └─ Raises 401 if is_active=False, is_locked=True, is_deleted=True
  │
  ├─ password.verify_password(plain, hashed)
  │   └─ bcrypt.verify() — ~120ms intentionally
  │   └─ Raises 401 + increments failed_login_count on failure
  │   └─ Locks account if failed_login_count >= 5
  │
  ├─ jwt_handler.create_access_token(user_id, username, roles)
  │   └─ Signs HS256 JWT: {sub, username, roles, scope="access", jti, iat, exp}
  │
  ├─ jwt_handler.create_refresh_token(user_id)
  │   └─ Signs HS256 JWT: {sub, scope="refresh", jti, exp=+7days}
  │   └─ SHA-256 hash of raw token stored in user_sessions
  │
  ├─ Creates UserSession record (user_id, refresh_token_hash, expires_at, ip, ua)
  │
  ├─ Writes API_REQUEST event to audit_log
  │
  └─ Returns: {access_token, refresh_token, expires_in, username, roles}

Subsequent requests:
  Authorization: Bearer <access_token>
  │
  └─ JWTAuthMiddleware.dispatch()
      ├─ Extract "Bearer " prefix
      ├─ jwt_handler.decode_access_token(token)
      │   └─ jose.jwt.decode() — verifies signature + expiry
      ├─ Set request.state.user_id, .username, .roles
      └─ Pass to next middleware
```

---

## Dashboard → API Flow

```
Browser → Streamlit (http://localhost:8501)
    │
    ├─ dashboard/Home.py
    │   ├─ auth.require_auth() → checks st.session_state["access_token"]
    │   ├─ If missing → renders _render_login_form()
    │   │   └─ On submit → api_client.login() → POST /api/v1/auth/login
    │   │       └─ Stores tokens in st.session_state
    │   └─ If present → renders KPI cards, charts, recent runs table
    │       └─ api_client.get_pipeline_history() → GET /api/v1/pipelines/history
    │           └─ httpx.get(url, headers={"Authorization": "Bearer <token>"})
    │               └─ FastAPI processes → returns PaginatedResponse[PipelineHistoryItem]
    │
    └─ All 10 dashboard pages follow same pattern:
        auth.require_auth() → api_client.*() → format → st.* display
```

---

## Database Schema Map

```
Operational Tables (6):
  customers ──────┐
  suppliers ──┐   │
  products ───┤   ├── orders ── order_items
  inventory   │   │
  payments ───┴───┘

Pipeline Tables (4):
  pipeline_runs ── stage_results
  pipeline_runs ── ingestion_events
  pipeline_runs ── reports

Audit Tables (4):
  audit_logs           (immutable event log)
  validation_failures  (per-row violations)
  cleaning_logs        (per-action cleaning records)
  data_quality_scores  (per-run quality metrics)

Auth Tables (7):
  users ─── user_roles ─── roles ─── role_permissions ─── permissions
  users ─── api_keys
  users ─── user_sessions
```

---

## Metrics Flow

```
Every HTTP Request
    │
    └─ PrometheusMetricsMiddleware
        ├─ etl_http_requests_total.inc()
        ├─ etl_http_request_duration_seconds.observe()
        └─ etl_http_active_requests +1/-1

Pipeline completion
    └─ (hook point) record_pipeline_run(dataset_type, status, duration)
        ├─ etl_pipeline_runs_total.inc()
        └─ etl_pipeline_duration_seconds.observe()

GET /metrics
    └─ prometheus_client.generate_latest(REGISTRY)
        └─ Returns all metrics in Prometheus text format
            └─ Prometheus scrapes every 15 seconds
                └─ Grafana queries Prometheus for charts/alerts
```
