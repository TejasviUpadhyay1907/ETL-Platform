# Troubleshooting Guide — ETL Platform v1.0.0

---

## Database Issues

### `connection refused` / `could not connect to server`

**Cause:** PostgreSQL is not running.

```bash
# Start with Docker (recommended):
docker run -d --name etl_postgres \
  -e POSTGRES_USER=etl_user -e POSTGRES_PASSWORD=etl_password \
  -e POSTGRES_DB=etl_platform -p 5432:5432 postgres:15-alpine

# Check it's running:
docker ps | grep postgres
```

**For local PostgreSQL:**
```bash
# macOS
brew services start postgresql@15

# Ubuntu
sudo systemctl start postgresql

# Windows
net start postgresql-x64-15
```

---

### `FATAL: password authentication failed`

**Cause:** Wrong credentials in `DATABASE_URL`.

Check `.env`:
```dotenv
DATABASE_URL=postgresql+psycopg2://etl_user:etl_password@localhost:5432/etl_platform
#                                   ^^^^^^^^^  ^^^^^^^^^^^^
#                                   username   password (must match what you set in PostgreSQL)
```

Reset password:
```bash
psql -U postgres -c "ALTER USER etl_user WITH PASSWORD 'etl_password';"
```

---

### `relation does not exist` / `table not found`

**Cause:** Migrations have not been run.

```bash
python scripts/setup_database.py
# or just migrations:
python scripts/run_migrations.py
```

---

### `alembic_version table not found` / `can't locate revision`

**Cause:** Database exists but no migrations have been applied.

```bash
python scripts/run_migrations.py
# If that fails, check current state:
alembic current
alembic history
```

---

### `PendingRollbackError`

**Cause:** A previous DB operation failed and left the session in a broken state.

This is handled automatically by the application. If you see it in scripts:
```python
try:
    session.rollback()
except Exception:
    pass
```

---

## Application Startup Issues

### `ModuleNotFoundError: No module named 'fastapi'`

**Cause:** Virtual environment not activated or dependencies not installed.

```bash
# Activate venv
source .venv/bin/activate       # macOS/Linux
.venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt
```

---

### `pydantic_settings.main.SettingsError: Error loading ... from .env`

**Cause:** `.env` file missing or malformed.

```bash
cp .env.example .env
# Then edit .env to set required values
```

---

### `ValueError: SECRET_KEY ... min_length=32`

**Cause:** `SECRET_KEY` in `.env` is too short or still has placeholder value.

```bash
# Generate a proper key:
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Paste output into .env:
# SECRET_KEY=<generated_value>
```

---

### Port already in use

```bash
# Find what's using port 8000:
# macOS/Linux:
lsof -i :8000
# Windows:
netstat -ano | findstr :8000

# Kill it or use a different port:
PORT=8080 python main.py
# or edit .env: PORT=8080
```

---

### `APP_ENV` validation error

**Cause:** `APP_ENV` must be `development`, `staging`, or `production`.

```dotenv
APP_ENV=development   # ✓
APP_ENV=dev           # ✗ — invalid
```

---

## Authentication Issues

### `401 AUTHENTICATION_REQUIRED` on every request

**Cause:** Protected endpoint hit without a Bearer token.

```bash
# Get a token first:
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin1234!"}'

# Use it:
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/pipelines
```

---

### `401 INVALID_CREDENTIALS`

**Cause:** Wrong username or password.

Default credentials: `admin` / `Admin1234!`

If no admin user exists:
```bash
python scripts/create_admin_user.py
```

---

### `401 ACCOUNT_LOCKED`

**Cause:** 5+ consecutive failed logins locked the account.

```bash
# Unlock via API (requires another admin token):
curl -X POST http://localhost:8000/api/v1/users/<user_id>/unlock \
  -H "Authorization: Bearer <admin_token>"

# Or reset the database:
python scripts/reset_database.py --yes
```

---

### `403 INSUFFICIENT_PERMISSION`

**Cause:** The logged-in user's role does not have the required permission.

Use the `admin` account for admin operations, or assign the correct role:
```bash
# Via dashboard: User Administration → Assign Role
# Via API:
curl -X POST http://localhost:8000/api/v1/users/<user_id>/roles \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"role_name":"data_engineer"}'
```

---

## Dashboard Issues

### Dashboard shows login form even after successful login

**Cause:** API URL is wrong in the login form.

Set API URL to: `http://localhost:8000` (not `http://localhost:8501`).

---

### Dashboard shows `Cannot connect to API`

**Cause:** FastAPI is not running or is on a different port.

```bash
# Verify API is running:
curl http://localhost:8000/api/v1/health/ping
# If not running:
python main.py
```

---

### Streamlit `ModuleNotFoundError`

**Cause:** `streamlit` not installed.

```bash
pip install streamlit==1.56.0 plotly==6.3.1
```

---

### Streamlit port 8501 in use

```bash
streamlit run dashboard/Home.py --server.port 8502
```

---

## Docker Issues

### `docker-compose: command not found`

```bash
# On newer Docker versions, use:
docker compose up -d   # (space, not hyphen)
# or install docker-compose standalone:
pip install docker-compose
```

---

### `DB_PASSWORD required` error in docker-compose.prod.yml

**Cause:** `DB_PASSWORD` not set in `.env`.

```bash
# Edit .env:
DB_PASSWORD=your_secure_password_here
```

---

### Container starts but API is unhealthy

```bash
# Check logs:
docker-compose -f docker-compose.prod.yml logs api

# Common cause: DB not ready yet. Wait 30 seconds and check again.
docker-compose -f docker-compose.prod.yml ps
```

---

## Performance Issues

### Slow API responses (>2 seconds)

- Check `DB_ECHO=False` in `.env` (SQL logging adds overhead)
- Check DB pool: `DB_POOL_SIZE=10`
- Check if scheduler is running unnecessary pipelines: `PIPELINE_ENABLE_SCHEDULER=False`

---

### `MemoryError` during large file processing

- Lower `PIPELINE_CHUNK_SIZE` (e.g., `5000` instead of `10000`)
- Lower `MAX_UPLOAD_SIZE_MB`

---

## Getting More Help

```bash
# Check application logs:
tail -f logs/app.log

# Verbose database check:
python scripts/verify_database.py --verbose

# Test imports manually:
python -c "from app.core.application import create_app; app = create_app(); print('OK — routes:', len(app.routes))"

# Check all environment variables loaded:
python -c "from app.core.config import get_config; c = get_config(); print('ENV:', c.app_env, 'DB:', str(c.database_url)[:50])"
```
