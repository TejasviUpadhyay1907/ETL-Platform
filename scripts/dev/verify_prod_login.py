"""Verify production login and all key endpoints."""
import httpx

BASE = "https://etl-platform-api.onrender.com"

print("=== Production Full Verification ===\n")

# Login
r = httpx.post(f"{BASE}/api/v1/auth/login",
    json={"username": "admin", "password": "Admin1234!"}, timeout=15)
print(f"Login: {r.status_code}", end="")
if r.status_code == 200:
    data = r.json()["data"]
    print(f" | user={data['username']} | roles={data['roles']}")
    token = data["access_token"]
    HDR = {"Authorization": f"Bearer {token}"}

    checks = [
        ("/api/v1/auth/me",                  "GET", None),
        ("/api/v1/pipelines",                "GET", None),
        ("/api/v1/roles",                    "GET", None),
        ("/api/v1/permissions",              "GET", None),
        ("/api/v1/users",                    "GET", None),
        ("/api/v1/pipelines/definitions",    "GET", None),
        ("/api/v1/pipelines/history",        "GET", None),
        ("/api/v1/load/history",             "GET", None),
        ("/api/v1/ingest/events",            "GET", None),
        ("/metrics",                         "GET", None),
    ]
    for path, method, body in checks:
        try:
            rr = httpx.get(f"{BASE}{path}", headers=HDR, timeout=10)
            d = rr.json()
            extra = ""
            if "data" in d and isinstance(d["data"], list):
                extra = f" items={len(d['data'])}"
            elif "pagination" in d:
                extra = f" total={d['pagination'].get('total_items',0)}"
            print(f"  [{rr.status_code}] {path}{extra}")
        except Exception as e:
            print(f"  [ERR] {path}: {type(e).__name__}")
else:
    print(f" FAILED: {r.text[:200]}")

print(f"""
========================================
  DEPLOYMENT COMPLETE
========================================

  GitHub: https://github.com/TejasviUpadhyay1907/ETL-Platform
  API:    https://etl-platform-api.onrender.com
  Docs:   https://etl-platform-api.onrender.com/docs

  Login:  admin / Admin1234!

  Note: On Render free tier the API spins down after 15 min
  of inactivity. First request after sleep takes ~30s to wake up.
========================================
""")
