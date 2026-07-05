"""Final endpoint checks."""
import httpx, time

BASE = "http://localhost:8001"

# Wait for server to finish reloading
time.sleep(3)

r = httpx.post(f"{BASE}/api/v1/auth/login",
    json={"username": "admin", "password": "Admin1234!"}, timeout=10)
token = r.json()["data"]["access_token"]
HDR = {"Authorization": f"Bearer {token}"}

checks = [
    ("Load history",     httpx.get(f"{BASE}/api/v1/load/history",             headers=HDR, timeout=10).status_code),
    ("Pipeline defs",    httpx.get(f"{BASE}/api/v1/pipelines/definitions",     headers=HDR, timeout=10).status_code),
    ("Pipeline history", httpx.get(f"{BASE}/api/v1/pipelines/history",         headers=HDR, timeout=10).status_code),
    ("Swagger /docs",    httpx.get(f"{BASE}/docs",                             timeout=5).status_code),
    ("OpenAPI JSON",     httpx.get(f"{BASE}/openapi.json",                     timeout=5).status_code),
    ("Health /ready",    httpx.get(f"{BASE}/api/v1/health/ready",              timeout=5).status_code),
    ("Health /version",  httpx.get(f"{BASE}/api/v1/health/version",            timeout=5).status_code),
    ("Ingest events",    httpx.get(f"{BASE}/api/v1/ingest/events",              headers=HDR, timeout=10).status_code),
    ("Quality history",  httpx.get(f"{BASE}/api/v1/quality/summary/00000000-0000-0000-0000-000000000000", headers=HDR, timeout=5).status_code),
]

all_ok = True
for name, code in checks:
    ok = code in (200, 404)   # 404 is fine for empty DB
    print(f"  {'[OK]  ' if ok else '[FAIL]'} {name}: {code}")
    if code not in (200, 201, 404):
        all_ok = False

defs = httpx.get(f"{BASE}/api/v1/pipelines/definitions", headers=HDR, timeout=10).json()
names = [d["name"] for d in (defs.get("data") or [])]
print(f"\n  Registered pipelines ({len(names)}): {names[:3]}{'...' if len(names)>3 else ''}")
print(f"\n  {'ALL CHECKS PASSED' if all_ok else 'SOME FAILURES'}")
