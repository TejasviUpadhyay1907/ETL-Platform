# First-Time Setup Guide — ETL Platform v1.0.0

> **Goal:** Get the platform running from zero in under 10 minutes.

---

## What You Need (Prerequisites)

| Requirement | Minimum Version | Check Command |
|-------------|----------------|---------------|
| Python | 3.12+ | `python --version` |
| pip | 23+ | `pip --version` |
| PostgreSQL **or** Docker | PG 15+ / Docker 24+ | `psql --version` or `docker --version` |
| Git | Any | `git --version` |

No Node.js, Java, or other runtimes required.

---

## Step 1 — Clone the Repository

```bash
git clone https://github.com/TejasviUpadhyay1907/ETL-Platform.git
cd ETL-Platform
```

---

## Step 2 — Create a Virtual Environment

```bash
# Create
python -m venv .venv

# Activate — Windows
.venv\Scripts\activate

# Activate — macOS/Linux
source .venv/bin/activate
```

---

## Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

This installs FastAPI, SQLAlchemy, Alembic, Pydantic, Streamlit, Plotly, and all other dependencies. Takes ~2 minutes on first run.

---

## Step 4 — Configure Environment

```bash
cp .env.example .env
```

Open `.env` and set these **three required values**:

```bash
# Generate SECRET_KEY:
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate JWT_SECRET (run again for a different value):
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Paste the outputs into `.env`:

```dotenv
SECRET_KEY=<paste generated value here>
JWT_SECRET=<paste generated value here>
API_KEY_SALT=<any 16+ character string>
DATABASE_URL=postgresql+psycopg2://etl_user:etl_password@localhost:5432/etl_platform
```

Everything else can stay as the default for local development.

---

## Step 5 — Start PostgreSQL

**Option A — Docker (recommended, no PostgreSQL install needed):**

```bash
docker run -d \
  --name etl_postgres \
  -e POSTGRES_USER=etl_user \
  -e POSTGRES_PASSWORD=etl_password \
  -e POSTGRES_DB=etl_platform \
  -p 5432:5432 \
  postgres:15-alpine
```

**Option B — Local PostgreSQL already running:**

```bash
# Create the database (run as postgres superuser)
psql -U postgres -c "CREATE USER etl_user WITH PASSWORD 'etl_password';"
psql -U postgres -c "CREATE DATABASE etl_platform OWNER etl_user;"
```

---

## Step 6 — Initialize the Database

```bash
python scripts/setup_database.py
```

This single command:
- Verifies the database connection
- Runs all Alembic migrations (creates 22 tables)
- Seeds 5 RBAC roles and 16 permissions
- Creates 4 default user accounts

Expected output:
```
[1/5] Verifying configuration…
  ✓ Config loaded — APP_ENV=development
[2/5] Connecting to PostgreSQL…
  ✓ PostgreSQL connection successful
[3/5] Running Alembic migrations…
  ✓ Migrations applied — revision: <hash>
[4/5] Verifying database schema…
  ✓ All required tables present
[5/5] Seeding RBAC roles and default users…
  ✓ Roles and permissions seeded (5 roles, 16 permissions)
  ✓ Created user: admin
  ✓ Created user: engineer
  ✓ Created user: analyst
  ✓ Created user: viewer
Database Setup Complete!
```

---

## Step 7 — Start the API

```bash
python main.py
```

Open http://localhost:8000/api/v1/health/ping — you should see:
```json
{"ping": "pong", "timestamp": "..."}
```

Open http://localhost:8000/docs for interactive API documentation.

---

## Step 8 — Start the Dashboard

Open a **new terminal**, activate the venv, then:

```bash
streamlit run dashboard/Home.py
```

Open http://localhost:8501

Log in with: **admin / Admin1234!**

---

## Step 9 — Run Your First Pipeline

```bash
# Upload a sample CSV and trigger the ETL pipeline
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin1234!"}' | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

curl -X POST http://localhost:8000/api/v1/pipelines/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dataset_type":"orders","triggered_by":"demo"}'
```

Or use the dashboard: **Pipeline Monitor → (click Trigger)**.

---

## Default Credentials

| Username | Password | Role | Permissions |
|----------|----------|------|-------------|
| `admin` | `Admin1234!` | Administrator | Everything |
| `engineer` | `Engineer1234!` | Data Engineer | Pipelines, data, API keys |
| `analyst` | `Analyst1234!` | Analyst | Read-only data & quality |
| `viewer` | `Viewer1234!` | Viewer | Read-only pipelines & data |

> ⚠️ **Change all passwords** before exposing to any network.

---

## Quick Verification

```bash
python scripts/verify_database.py
```

All checks should show `[✓] PASS`.

---

## One-Command Start (after initial setup)

```bash
# Start API + dashboard together
python scripts/start_dev.py --with-dashboard
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| `Connection refused` on DB | Start PostgreSQL (Step 5) |
| `.env not found` | Run `cp .env.example .env` |
| `change-this` in SECRET_KEY warning | Generate real keys (Step 4) |
| Port 8000 in use | `python main.py` → edit `.env`: `PORT=8001` |
| Port 8501 in use | `streamlit run ... --server.port 8502` |

Full troubleshooting guide: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
