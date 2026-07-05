"""
Deploy ETL Platform to Render.com via Render API.
Usage: python scripts/deploy_render.py --api-key rnd_YOUR_KEY_HERE
"""
import argparse
import json
import sys
import time

import httpx

RENDER_API = "https://api.render.com/v1"
GITHUB_REPO = "https://github.com/TejasviUpadhyay1907/ETL-Platform"
BRANCH = "main"


def sep(msg):
    print(f"\n{'='*55}\n  {msg}\n{'='*55}")


def api(method, path, token, **kwargs):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json",
                "Content-Type": "application/json"}
    r = httpx.request(method, f"{RENDER_API}{path}", headers=headers, timeout=30, **kwargs)
    return r


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True, help="Render API key (rnd_...)")
    args = parser.parse_args()
    TOKEN = args.api_key

    # Verify key
    sep("Step 1 — Verify Render API key")
    r = api("GET", "/owners?limit=1", TOKEN)
    if r.status_code != 200:
        print(f"  Invalid API key: {r.status_code} {r.text[:200]}")
        sys.exit(1)
    owner = r.json()[0]["owner"]
    owner_id = owner["id"]
    print(f"  Logged in as: {owner['name']} ({owner['email']})")
    print(f"  Owner ID: {owner_id}")

    # Create PostgreSQL database
    sep("Step 2 — Create PostgreSQL Database")
    db_payload = {
        "databaseName": "etl_platform",
        "databaseUser": "etl_user",
        "enableHighAvailability": False,
        "plan": "free",
        "region": "oregon",
        "name": "etl-platform-db",
        "ownerId": owner_id,
    }
    r = api("POST", "/postgres", TOKEN, json=db_payload)
    if r.status_code in (200, 201):
        db = r.json()
        db_id = db["id"]
        db_url_internal = db.get("internalConnectionString", "")
        print(f"  Database created: {db_id}")
        print(f"  Connection: {db_url_internal[:50]}...")
    elif r.status_code == 409:
        print("  Database already exists — fetching existing...")
        r2 = api("GET", "/postgres?limit=20", TOKEN)
        dbs = [d for d in r2.json() if d.get("name") == "etl-platform-db"]
        if dbs:
            db_id = dbs[0]["id"]
            db_url_internal = dbs[0].get("internalConnectionString", "")
            print(f"  Using existing DB: {db_id}")
        else:
            print("  No DB found, will use DATABASE_URL env var after service creation")
            db_id = None
            db_url_internal = ""
    else:
        print(f"  DB creation failed: {r.status_code} {r.text[:300]}")
        db_id = None
        db_url_internal = ""

    # Wait for DB to be available
    if db_id and not db_url_internal:
        print("  Waiting for database connection string...")
        for _ in range(10):
            time.sleep(5)
            r = api("GET", f"/postgres/{db_id}", TOKEN)
            if r.status_code == 200:
                db_url_internal = r.json().get("internalConnectionString", "")
                if db_url_internal:
                    print(f"  DB ready: {db_url_internal[:50]}...")
                    break

    # Build env vars list
    env_vars = [
        {"key": "APP_ENV",                      "value": "production"},
        {"key": "APP_NAME",                     "value": "ETL Platform"},
        {"key": "APP_VERSION",                  "value": "1.0.0"},
        {"key": "SECRET_KEY",                   "value": "PUQcxci0oVVxAwoJ61HP2RmYXgjOGZzMIXYXh8L1FXg"},
        {"key": "JWT_SECRET",                   "value": "12xSKl8UYBxlyhzbDq2BxvwbdFCAYOjfjF5pYV-ewsA"},
        {"key": "API_KEY_SALT",                 "value": "zzQNuUEq1v8Bw8lDA1jOyA"},
        {"key": "JWT_ALGORITHM",                "value": "HS256"},
        {"key": "JWT_EXPIRATION_MINUTES",       "value": "1440"},
        {"key": "LOG_LEVEL",                    "value": "INFO"},
        {"key": "LOG_JSON_FORMAT",              "value": "True"},
        {"key": "RATE_LIMIT_ENABLED",           "value": "True"},
        {"key": "CORS_ENABLED",                 "value": "True"},
        {"key": "CORS_ORIGINS",                 "value": "*"},
        {"key": "PIPELINE_ENABLE_SCHEDULER",    "value": "False"},
        {"key": "MAX_UPLOAD_SIZE_MB",           "value": "100"},
        {"key": "UPLOAD_DIRECTORY",             "value": "/tmp/raw"},
        {"key": "REPORT_DIRECTORY",             "value": "/tmp/reports"},
        {"key": "ARCHIVE_DIRECTORY",            "value": "/tmp/archive"},
        {"key": "DB_POOL_SIZE",                 "value": "3"},
        {"key": "DB_MAX_OVERFLOW",              "value": "5"},
        {"key": "DB_POOL_TIMEOUT",              "value": "30"},
        {"key": "QUALITY_SCORE_WARNING_THRESHOLD", "value": "80"},
        {"key": "QUALITY_SCORE_FAILURE_THRESHOLD", "value": "50"},
    ]

    if db_url_internal:
        # Convert internal postgres:// to postgresql+psycopg2://
        db_url_alchemy = db_url_internal.replace("postgres://", "postgresql+psycopg2://")
        env_vars.append({"key": "DATABASE_URL", "value": db_url_alchemy})

    # Create Web Service
    sep("Step 3 — Create Web Service from GitHub")
    svc_payload = {
        "type": "web_service",
        "name": "etl-platform-api",
        "ownerId": owner_id,
        "repo": GITHUB_REPO,
        "branch": BRANCH,
        "rootDir": "",
        "buildFilter": {"paths": []},
        "serviceDetails": {
            "env": "python",
            "buildCommand": "pip install -r requirements.txt",
            "startCommand": "python scripts/setup_database.py --skip-seed && uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1",
            "plan": "free",
            "region": "oregon",
            "numInstances": 1,
            "healthCheckPath": "/api/v1/health/ping",
            "envVars": env_vars,
        },
    }
    r = api("POST", "/services", TOKEN, json=svc_payload)
    if r.status_code in (200, 201):
        svc = r.json()
        svc_id = svc["id"]
        svc_url = svc.get("serviceDetails", {}).get("url", "")
        deploy_id = svc.get("deployId", "")
        print(f"  Service created: {svc_id}")
        print(f"  URL: https://{svc_url}" if svc_url else "  URL will be assigned after deploy")
    elif r.status_code == 409:
        print("  Service already exists — fetching...")
        r2 = api("GET", "/services?limit=20", TOKEN)
        svcs = [s for s in r2.json() if s.get("name") == "etl-platform-api"]
        if svcs:
            svc_id = svcs[0]["id"]
            svc_url = svcs[0].get("serviceDetails", {}).get("url", "")
            print(f"  Using existing service: {svc_id}")
            # Trigger redeploy
            rd = api("POST", f"/services/{svc_id}/deploys", TOKEN, json={"clearCache": "clear"})
            print(f"  Redeploy triggered: {rd.status_code}")
        else:
            print(f"  Service not found")
            sys.exit(1)
    else:
        print(f"  Service creation failed: {r.status_code}")
        print(f"  Response: {r.text[:500]}")
        sys.exit(1)

    # Monitor deployment
    sep("Step 4 — Monitoring Deployment")
    final_url = svc_url if svc_url else "etl-platform-api.onrender.com"
    print(f"  Build started. This takes 3-5 minutes on free tier.")
    print(f"  Monitor: https://dashboard.render.com")
    print()
    print(f"  When ready, your live URLs will be:")
    print(f"  API:     https://{final_url}/api/v1/health/ping")
    print(f"  Swagger: https://{final_url}/docs")
    print(f"  Metrics: https://{final_url}/metrics")
    print()
    print(f"  After first deploy, create admin user:")
    print(f"  Go to: https://dashboard.render.com/web/{svc_id}/shell")
    print(f"  Run:   python scripts/create_admin_user.py")
    print()
    print(f"  Login: admin / Admin1234!")


if __name__ == "__main__":
    main()
