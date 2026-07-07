# Local Development Guide — ETL Platform v1.0.0

---

## Setup (first time only)

```bash
git clone https://github.com/TejasviUpadhyay1907/ETL-Platform.git
cd ETL-Platform
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # pre-configured dev values — edit if needed
# Start PostgreSQL:
docker run -d --name etl_pg -e POSTGRES_USER=etl_user -e POSTGRES_PASSWORD=etl_password \
  -e POSTGRES_DB=etl_platform -p 5432:5432 postgres:15-alpine
python scripts/setup_database.py
```

## Daily workflow

```bash
source .venv/bin/activate
# Terminal 1 — API with hot-reload
python main.py
# Terminal 2 — Dashboard
streamlit run dashboard/Home.py
```

Or one-command:
```bash
python scripts/start_dev.py --with-dashboard
```

## Development .env settings

For local dev, the `.env` is pre-configured. Key settings you might change:

```dotenv
DB_ECHO=True              # See every SQL query
LOG_LEVEL=DEBUG           # Verbose logging
LOG_JSON_FORMAT=False     # Human-readable logs
RATE_LIMIT_ENABLED=False  # Disable throttling during testing
```

## Adding sample data

```bash
# Tiny dataset (500 records) — fastest
python scripts/seed_data.py --count tiny

# Small dataset (7,000 records) — good for demos
python scripts/seed_data.py --count small

# Full dataset (80,000 records) — realistic load
python scripts/seed_data.py --count full

# Clear everything and re-seed
python scripts/seed_data.py --truncate --count small
```

## Testing sample CSV files

Pre-built sample files live in `data/sample/`:

| File | Records | Purpose |
|------|---------|---------|
| `orders_valid.csv` | 25 | Clean orders for happy-path demo |
| `orders_with_errors.csv` | 20 | Bad data to demo validation/cleaning |
| `customers_valid.csv` | 25 | Clean customers |
| `products_valid.csv` | 25 | Clean products |
| `suppliers_valid.csv` | 15 | Clean suppliers |
| `payments_valid.csv` | 20 | Clean payments |
| `inventory_valid.csv` | 20 | Clean inventory |

Upload via dashboard (Ingestion Monitor) or API:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin1234!"}' | \
  python -m json.tool | grep access_token | cut -d'"' -f4)

curl -X POST http://localhost:8000/api/v1/ingest/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@data/sample/orders_valid.csv" \
  -F "dataset_type=orders"
```

## Running tests

```bash
# All unit tests (fast, SQLite, no DB needed)
pytest tests/unit/ -q

# With coverage
pytest tests/unit/ --cov=app --cov-report=term-missing

# Single module
pytest tests/unit/test_core/test_auth_services.py -v

# Dashboard utilities
pytest tests/unit/test_dashboard/ -v

# Integration tests (requires running PostgreSQL)
pytest tests/integration/ -v
```

## API exploration

- **Swagger UI** — http://localhost:8000/docs
  - Click "Authorize" → enter `Bearer <token>` from login
  - Try endpoints interactively
- **ReDoc** — http://localhost:8000/redoc (clean reference docs)
- **Prometheus metrics** — http://localhost:8000/metrics

## Database management

```bash
# Check DB state
python scripts/verify_database.py --verbose

# New migration after model change
alembic revision --autogenerate -m "add_my_new_column"
python scripts/run_migrations.py

# Reset to clean state (dev only)
python scripts/reset_database.py --yes --with-demo-data

# Open DB shell
psql postgresql://etl_user:etl_password@localhost:5432/etl_platform
```

## Code quality

```bash
# Format
black app/ tests/ dashboard/ --line-length=100

# Lint
ruff check app/ tests/ dashboard/

# Type check
mypy app/ --ignore-missing-imports --no-strict-optional --exclude migrations/
```

## Project layout (quick reference)

```
app/
├── api/routers/        # HTTP endpoints (auth, pipelines, quality, etc.)
├── auth/               # JWT, passwords, RBAC, user service
├── cleaning/           # Cleaning engine + 7 strategies
├── core/               # Config, exceptions, app factory
├── database/           # ORM models, repositories, engine
├── ingestion/          # CSV/Excel readers, file detection
├── loading/            # Warehouse loader + 5 strategies
├── middleware/         # Logging, security headers, metrics
├── observability/      # Prometheus metrics definitions
├── pipeline/           # Orchestration engine, checkpoints, retry
├── transformation/     # Transformation engine + 8 transformers
└── validation/         # Validation engine + 9 validators

dashboard/
├── Home.py             # Entry point
├── pages/              # 10 dashboard pages
└── utils/              # api_client, auth, charts, formatting

tests/
├── unit/               # 1148 unit tests (SQLite, no external deps)
└── integration/        # API health tests (require running server)
```
