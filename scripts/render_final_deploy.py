"""Set DATABASE_URL and trigger final Render deploy."""
import httpx, time

TOKEN  = "rnd_bRRneBs9NsBn1ulV9PAnNcKYVEDZ"
SVC_ID = "srv-d9573v3tqb8s73eg9ecg"
DB_ID  = "dpg-d9573ggk1i2s739rqr20-a"
SVC_URL = "https://etl-platform-api.onrender.com"
API    = "https://api.render.com/v1"
H = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
     "Content-Type": "application/json"}

# Step 1: Get DB connection string
print("Getting DB connection string...")
r = httpx.get(f"{API}/postgres/{DB_ID}/connection-info", headers=H, timeout=15)
conn_info = r.json()
ext_conn = conn_info.get("externalConnectionString", "")
int_conn = conn_info.get("internalConnectionString", "")
print(f"  External: {ext_conn[:60]}...")
print(f"  Internal: {int_conn[:60]}...")

# Use internal connection (service-to-service on Render, faster)
# Convert to SQLAlchemy psycopg2 format
db_url = int_conn.replace("postgresql://", "postgresql+psycopg2://")
print(f"  Using:    {db_url[:60]}...")

# Step 2: Set all env vars including DATABASE_URL
print("\nSetting all environment variables...")
all_vars = [
    {"key": "DATABASE_URL",                     "value": db_url},
    {"key": "APP_ENV",                          "value": "production"},
    {"key": "APP_NAME",                         "value": "ETL Platform"},
    {"key": "APP_VERSION",                      "value": "1.0.0"},
    {"key": "SECRET_KEY",                       "value": "PUQcxci0oVVxAwoJ61HP2RmYXgjOGZzMIXYXh8L1FXg"},
    {"key": "JWT_SECRET",                       "value": "12xSKl8UYBxlyhzbDq2BxvwbdFCAYOjfjF5pYV-ewsA"},
    {"key": "API_KEY_SALT",                     "value": "zzQNuUEq1v8Bw8lDA1jOyA"},
    {"key": "JWT_ALGORITHM",                    "value": "HS256"},
    {"key": "JWT_EXPIRATION_MINUTES",           "value": "1440"},
    {"key": "LOG_LEVEL",                        "value": "INFO"},
    {"key": "LOG_JSON_FORMAT",                  "value": "True"},
    {"key": "RATE_LIMIT_ENABLED",               "value": "True"},
    {"key": "CORS_ENABLED",                     "value": "True"},
    {"key": "CORS_ORIGINS",                     "value": "*"},
    {"key": "PIPELINE_ENABLE_SCHEDULER",        "value": "False"},
    {"key": "MAX_UPLOAD_SIZE_MB",               "value": "100"},
    {"key": "UPLOAD_DIRECTORY",                 "value": "/tmp/raw"},
    {"key": "REPORT_DIRECTORY",                 "value": "/tmp/reports"},
    {"key": "ARCHIVE_DIRECTORY",                "value": "/tmp/archive"},
    {"key": "DB_POOL_SIZE",                     "value": "3"},
    {"key": "DB_MAX_OVERFLOW",                  "value": "5"},
    {"key": "DB_POOL_TIMEOUT",                  "value": "30"},
    {"key": "QUALITY_SCORE_WARNING_THRESHOLD",  "value": "80"},
    {"key": "QUALITY_SCORE_FAILURE_THRESHOLD",  "value": "50"},
]
r = httpx.put(f"{API}/services/{SVC_ID}/env-vars", headers=H, json=all_vars, timeout=15)
print(f"  Status: {r.status_code}")

# Step 3: Update build/start command
print("\nUpdating start command to use start.sh...")
r = httpx.patch(f"{API}/services/{SVC_ID}", headers=H, json={
    "serviceDetails": {
        "envSpecificDetails": {
            "buildCommand": "pip install --upgrade pip && pip install -r requirements.txt",
            "startCommand": "bash start.sh",
        }
    }
}, timeout=15)
print(f"  Update: {r.status_code}")

# Step 4: Trigger deploy
print("\nTriggering deploy...")
r = httpx.post(f"{API}/services/{SVC_ID}/deploys",
               headers=H, json={"clearCache": "do_not_clear"}, timeout=15)
print(f"  Deploy: {r.status_code}")

# Step 5: Monitor
print("\nMonitoring build (every 20s, max 15 min)...")
last_status = ""
for i in range(45):
    time.sleep(20)
    r = httpx.get(f"{API}/services/{SVC_ID}/deploys?limit=1", headers=H, timeout=15)
    if r.status_code == 200 and r.text:
        try:
            d = r.json()[0].get("deploy") or r.json()[0]
            status = d.get("status", "?")
            if status != last_status:
                print(f"  [{i+1:02d}] {status}")
                last_status = status
            if status in ("live", "failed", "build_failed", "canceled"):
                break
        except:
            pass

# Final test
print("\nTesting live endpoint...")
time.sleep(10)
for attempt in range(3):
    try:
        r = httpx.get(f"{SVC_URL}/api/v1/health/ping", timeout=20)
        print(f"  {r.status_code}: {r.text[:80]}")
        if r.status_code == 200:
            print(f"""
========================================
  YOUR ETL PLATFORM IS LIVE!
========================================
  API:     {SVC_URL}
  Swagger: {SVC_URL}/docs
  Metrics: {SVC_URL}/metrics
  Health:  {SVC_URL}/api/v1/health/ping

  Login:   admin / Admin1234!

  Next — Create admin user:
  1. Go to: https://dashboard.render.com/web/{SVC_ID}/shell
  2. Run:   python scripts/create_admin_user.py
========================================
""")
        break
    except Exception as e:
        print(f"  Attempt {attempt+1}: {type(e).__name__}")
        time.sleep(10)
