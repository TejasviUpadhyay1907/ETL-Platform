# Phase 11 — Enterprise Operations Dashboard

## Overview

The ETL Platform Operations Dashboard is a production-grade Streamlit application that serves as the operational control center for the entire ETL platform. It consumes all existing FastAPI endpoints exclusively — no backend logic is duplicated.

**Target audience:** Data Engineers, Operations Engineers, Administrators

```
Streamlit Dashboard
       │
       ▼
 dashboard/utils/api_client.py   ← all API calls (httpx)
       │
       ▼
 FastAPI Backend  (http://localhost:8000)
       │
       ├── /api/v1/auth/*
       ├── /api/v1/pipelines/*
       ├── /api/v1/quality/*
       ├── /api/v1/load/*
       ├── /api/v1/ingest/*
       ├── /api/v1/users/*
       ├── /api/v1/roles/*
       └── /api/v1/api-keys/*
```

---

## Architecture

```
dashboard/
├── Home.py                        ← Entry point + Executive Overview
├── .streamlit/
│   └── config.toml                ← Theme, server config
├── pages/
│   ├── 1_Pipeline_Monitor.py      ← Live pipeline status + drill-down
│   ├── 2_Pipeline_History.py      ← Searchable history + export
│   ├── 3_Data_Quality.py          ← Quality scores, violations, trends
│   ├── 4_Warehouse.py             ← Load events, strategies, metrics
│   ├── 5_User_Administration.py   ← Users, roles, API keys (admin)
│   ├── 6_Audit_Log.py             ← Audit events, security log
│   ├── 7_Ingestion.py             ← Ingestion events, file stats
│   ├── 8_Configuration.py         ← Pipeline definitions, system health
│   ├── 9_Cleaning_Dashboard.py    ← Cleaning metrics, pass rates
│   └── 10_Transformation_Dashboard.py ← Transformation throughput
└── utils/
    ├── __init__.py
    ├── api_client.py              ← All HTTP calls to the FastAPI backend
    ├── auth.py                    ← JWT session management
    ├── charts.py                  ← Reusable Plotly chart builders
    ├── formatting.py              ← Numbers, durations, badges, export
    └── state.py                   ← Auto-refresh, filter persistence
```

---

## Dashboard Pages

### Home — Executive Overview
- System status banner (healthy / degraded / unhealthy)
- KPI cards: total runs, success rate, failures, running, records, avg duration
- Pipeline status donut chart
- Records funnel (ingested → validated → cleaned → loaded)
- Recent pipeline runs table
- Auto-refresh control (10s / 30s / 60s / 120s)

### 1. Pipeline Monitor
- Live counts: running, queued, completed, failed, retrying
- Status distribution donut
- Filterable runs table (status, dataset type)
- Run drill-down: stage timeline (Gantt), stage duration bar chart, stage results table
- Checkpoint inspection
- Cancel and Retry action buttons

### 2. Pipeline History
- Paginated, searchable, sortable history
- Filters: status, dataset, date
- Client-side search across pipeline name, run number, triggered_by
- CSV and Excel export

### 3. Data Quality Dashboard
- Quality gauge (0–100 with colour zones)
- Dimension bars (completeness, validity, consistency, uniqueness, integrity, timeliness)
- Violations pie (errors / warnings / info)
- Violation details table (filterable)
- Quality score trend line across runs
- Dataset comparison support

### 4. Warehouse Dashboard
- Rows loaded, failed, load success rate KPIs
- Load strategy distribution bar chart
- Rows loaded over time (per run)
- Load event log with metrics (inserted, updated, skipped, failed)
- Per-run detail with load metrics bar chart
- CSV and Excel export

### 5. User Administration *(admin/engineer only)*
- User list with roles, status, last login
- Create user form
- Assign / revoke roles
- Unlock locked accounts
- Delete user (with confirmation)
- Roles and permissions viewer
- API key management: create, list, revoke, rotate (raw key shown once)

### 6. Audit Log
- Events aggregated from recent pipeline runs
- Event type and severity distribution charts
- Scatter timeline of recent events
- Filters: run, event type, free-text search
- CSV and Excel export

### 7. Ingestion Monitor
- KPIs: total events, processed, rejected, duplicates, rows
- Dataset type and status distribution charts
- Filterable event table with search
- CSV export

### 8. Configuration Viewer *(read-only)*
- All registered pipeline definitions with stage order
- Definition detail JSON viewer
- System health status
- API version info and OpenAPI doc links

### 9. Cleaning Dashboard
- Clean rate KPIs and trend line
- Per-run cleaning summary table
- Stage drill-down (input, output, rejected for cleaning stage)

### 10. Transformation Dashboard
- Input vs output records grouped bar chart
- Transformation rate KPI
- Stage detail: all stage metrics for selected run
- Stage duration bar chart from pipeline metrics

---

## Authentication Flow

```
1. User opens dashboard → Home.py
2. If no access_token in session_state → login form shown
3. User submits credentials → POST /api/v1/auth/login
4. On success → tokens stored in st.session_state:
   - access_token (JWT, 60 min default)
   - refresh_token (7 days)
   - username, roles, user_id
5. All API calls inject:  Authorization: Bearer <access_token>
6. 401 response → token cleared → user shown login form
7. Logout button → POST /api/v1/auth/logout → state cleared
```

### Role-Aware UI
- All pages require authentication (`require_auth()`)
- User Administration page additionally checks `is_engineer()` (administrator or data_engineer)
- Action buttons (cancel, retry, create user, delete user) check `is_admin()`
- Pages display only what the authenticated user's role permits

---

## Running the Dashboard

### Prerequisites
- FastAPI backend running: `python main.py` or `uvicorn main:app`
- Python 3.12+ with `streamlit` and `plotly` installed

```bash
# Install dependencies (already in requirements.txt)
pip install streamlit==1.56.0 plotly==6.3.1

# Start the FastAPI backend first
python main.py

# Then start the dashboard
streamlit run dashboard/Home.py

# Or use the launch script
python scripts/run_dashboard.py

# Custom port and API URL
python scripts/run_dashboard.py --port 8502 --api-url http://etl-api:8000
```

Default URL: **http://localhost:8501**

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DASHBOARD_API_URL` | `http://localhost:8000` | Backend API base URL |
| `DASHBOARD_API_TIMEOUT` | `15` | HTTP request timeout (seconds) |

---

## Configuration

`dashboard/.streamlit/config.toml` controls:
- Dark theme (primary: blue, background: dark slate)
- Server port 8501
- XSRF protection enabled
- Usage stats disabled

---

## Performance

| Technique | Implementation |
|-----------|---------------|
| Lazy loading | Data only fetched when page renders |
| Client-side search | Avoids extra API calls for text filtering |
| Pagination | All list endpoints paginated (default 20 rows) |
| Streamlit caching | `st.cache_data` can be added to `api_client.py` functions for slow endpoints |
| Auto-refresh | Opt-in via sidebar checkbox, configurable interval |

---

## Export Formats

All list pages support export via `st.download_button`:

| Format | Content | Use case |
|--------|---------|----------|
| CSV | Raw data, UTF-8 | Spreadsheet analysis |
| Excel (`.xlsx`) | Formatted workbook | Sharing with stakeholders |

---

## Testing

| Test file | Tests | Covers |
|-----------|-------|--------|
| `test_formatting.py` | 43 | Number, duration, date, badge, export, envelope helpers |
| `test_charts.py` | 29 | All Plotly chart builders with synthetic data |
| `test_api_client.py` | 20 | HTTP calls, auth headers, error handling (mocked httpx) |
| `test_auth_utils.py` | 18 | Session state, role checks, auth guards |

**Total new tests: 97** (all passing)  
**Full suite: 1148 tests, 0 failures**

Run dashboard tests only:
```bash
python -m pytest tests/unit/test_dashboard/ -v
```

---

## Deployment

### Docker (with existing docker-compose)

Add to `docker-compose.yml`:
```yaml
dashboard:
  build:
    context: .
    dockerfile: docker/Dockerfile
  command: streamlit run dashboard/Home.py --server.port 8501 --server.headless true
  ports:
    - "8501:8501"
  environment:
    - DASHBOARD_API_URL=http://api:8000
  depends_on:
    - api
```

### Nginx reverse proxy

```nginx
location /dashboard/ {
    proxy_pass http://localhost:8501/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
}
```

Streamlit uses WebSockets for live updates — ensure `Upgrade` headers are forwarded.

---

## Extension Guide

### Adding a new page

1. Create `dashboard/pages/N_Page_Name.py`
2. Add `st.set_page_config(...)` as the first Streamlit call
3. Call `require_auth()` to gate the page
4. Use `api_client.py` functions for all data — never import `app.*`
5. Use `charts.py` for Plotly figures, `formatting.py` for display values

### Adding a new chart

Add a function to `dashboard/utils/charts.py`:
```python
def my_chart(data: list[dict]) -> go.Figure:
    fig = go.Figure(...)
    return _apply_layout(fig, "My Chart Title", height=300)
```

### Adding a new API call

Add a function to `dashboard/utils/api_client.py`:
```python
def get_my_endpoint(param: str) -> dict[str, Any]:
    return _safe_get(f"{_get_base_url()}/api/v1/my-endpoint", params={"param": param})
```
