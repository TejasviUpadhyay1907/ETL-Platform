"""Set all env vars and trigger final deploy on Render."""
import httpx, json, time

TOKEN  = "rnd_bRRneBs9NsBn1ulV9PAnNcKYVEDZ"
SVC_ID = "srv-d9573v3tqb8s73eg9ecg"
DB_ID  = "dpg-d9573ggk1i2s739rqr20-a"
SVC_URL = "https://etl-platform-api.onrender.com"
API    = "https://api.render.com/v1"
H = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
     "Content-Type": "application/json"}

# All env vars — DATABASE_URL will be linked from DB via Render dashboard
# but we set a placeholder; Render's auto-link overrides it when linked
all_vars = [
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
    {"key": "DB_POOL_RECYCLE",                  "value": "3600"},
    {"key": "QUALITY_SCORE_WARNING_THRESHOLD",  "value": "80"},
    {"key": "QUALITY_SCORE_FAILURE_THRESHOLD",  "value": "50"},
]

# Step 1: Set env vars
print("Setting environment variables...")
r = httpx.put(f"{API}/services/{SVC_ID}/env-vars", headers=H, json=all_vars, timeout=15)
print(f"  Set env vars: {r.status_code}")
if r.status_code not in (200, 201):
    print(f"  Error: {r.text[:200]}")

# Step 2: Update build/start command - simpler start (no DB setup on boot)
print("\nUpdating build/start commands...")
r = httpx.patch(f"{API}/services/{SVC_ID}", headers=H, json={
    "serviceDetails": {
        "envSpecificDetails": {
            "buildCommand": "pip install --upgrade pip && pip install -r requirements.txt",
            "startCommand": "uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1",
        }
    }
}, timeout=15)
print(f"  Update service: {r.status_code}")

# Step 3: Trigger deploy
print("\nTriggering deploy...")
r = httpx.post(f"{API}/services/{SVC_ID}/deploys",
               headers=H, json={"clearCache": "clear"}, timeout=15)
print(f"  Deploy: {r.status_code}")

# Step 4: Monitor
print("\nMonitoring (60s polling)...")
for i in range(15):
    time.sleep(20)
    r = httpx.get(f"{API}/services/{SVC_ID}/deploys?limit=1", headers=H, timeout=15)
    if r.status_code == 200 and r.text:
        try:
            deploys = r.json()
            if deploys:
                d = deploys[0].get("deploy") or deploys[0]
                status = d.get("status","?")
                print(f"  [{i+1:02d}] {status}")
                if status in ("live", "failed", "canceled", "build_failed"):
                    break
        except: pass

# Final test
print("\nTesting live URL...")
time.sleep(5)
try:
    r = httpx.get(f"{SVC_URL}/api/v1/health/ping", timeout=15)
    print(f"  {r.status_code}: {r.text[:100]}")
    if r.status_code == 200:
        print(f"""
========================================
  SUCCESS! Your API is LIVE
========================================
  URL:     {SVC_URL}
  Health:  {SVC_URL}/api/v1/health/ping
  Swagger: {SVC_URL}/docs
  Metrics: {SVC_URL}/metrics

  Next: Connect DB in Render dashboard
  https://dashboard.render.com/web/{SVC_ID}
  -> Environment -> Add from Database -> etl-platform-db
  -> Then redeploy with admin user setup
========================================
""")
except Exception as e:
    print(f"  Not live: {type(e).__name__}: {e}")
    print(f"\n  Check: https://dashboard.render.com/web/{SVC_ID}/deploys")
