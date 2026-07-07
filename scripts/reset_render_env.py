"""Re-set all environment variables on Render service."""
import httpx

TOKEN  = "rnd_bRRneBs9NsBn1ulV9PAnNcKYVEDZ"
DB_ID  = "dpg-d9573ggk1i2s739rqr20-a"
SVC_ID = "srv-d9573v3tqb8s73eg9ecg"
API    = "https://api.render.com/v1"
H = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
     "Content-Type": "application/json"}

# Get DB connection string
r = httpx.get(f"{API}/postgres/{DB_ID}/connection-info", headers=H, timeout=15)
conn = r.json()
int_conn = conn.get("internalConnectionString", "")
print(f"DB internal: {int_conn[:60]}...")

db_url = int_conn.replace("postgresql://", "postgresql+psycopg2://")

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
    {"key": "CORS_ALLOW_CREDENTIALS",           "value": "False"},
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

print(f"Setting {len(all_vars)} environment variables...")
r = httpx.put(f"{API}/services/{SVC_ID}/env-vars", headers=H,
              json=all_vars, timeout=15)
print(f"Status: {r.status_code}")
if r.status_code not in (200, 201):
    print(f"Error: {r.text[:200]}")
else:
    print("All env vars set successfully.")
    # Verify DATABASE_URL was set
    r2 = httpx.get(f"{API}/services/{SVC_ID}/env-vars", headers=H, timeout=15)
    if r2.status_code == 200 and r2.text:
        evars = r2.json()
        for ev in evars:
            e = ev.get("envVar") or ev
            if e.get("key") == "DATABASE_URL":
                print(f"DATABASE_URL: {str(e.get('value',''))[:60]}...")
                break
