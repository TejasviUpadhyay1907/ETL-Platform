"""End-to-end live verification of the running ETL Platform API."""
import httpx, sys

BASE = "http://localhost:8001"

def check(label, status_code, expected=200, detail=""):
    ok = status_code == expected
    icon = "[OK]" if ok else "[FAIL]"
    print(f"  {icon} {label}: {status_code}" + (f" | {detail}" if detail else ""))
    return ok

results = []
print("\nETL Platform — Live Verification")
print("=" * 50)

# 1. Health
r = httpx.get(f"{BASE}/api/v1/health", timeout=5)
h = r.json().get("data", {})
results.append(check("Health", r.status_code, detail=f"status={h.get('status')} db={h.get('database')}"))

# 2. Login
r = httpx.post(f"{BASE}/api/v1/auth/login",
    json={"username": "admin", "password": "Admin1234!"}, timeout=5)
results.append(check("Login", r.status_code, detail="admin/Admin1234!"))
if r.status_code != 200:
    print("  Cannot continue without auth token.")
    sys.exit(1)

token = r.json()["data"]["access_token"]
roles = r.json()["data"]["roles"]
HDR = {"Authorization": f"Bearer {token}"}

# 3. /me
r = httpx.get(f"{BASE}/api/v1/auth/me", headers=HDR, timeout=5)
username = r.json().get("data", {}).get("username", "?")
results.append(check("/me", r.status_code, detail=f"username={username}"))

# 4. Pipelines list
r = httpx.get(f"{BASE}/api/v1/pipelines?page_size=5", headers=HDR, timeout=5)
total = r.json().get("pagination", {}).get("total_items", 0)
results.append(check("Pipelines list", r.status_code, detail=f"total_items={total}"))

# 5. Users list
r = httpx.get(f"{BASE}/api/v1/users", headers=HDR, timeout=5)
users = r.json().get("pagination", {}).get("total_items", 0)
results.append(check("Users list", r.status_code, detail=f"users={users}"))

# 6. Roles
r = httpx.get(f"{BASE}/api/v1/roles", headers=HDR, timeout=5)
role_names = [x["name"] for x in r.json().get("data", [])]
results.append(check("Roles", r.status_code, detail=str(role_names)))

# 7. Permissions
r = httpx.get(f"{BASE}/api/v1/permissions", headers=HDR, timeout=5)
perms = len(r.json().get("data", []))
results.append(check("Permissions", r.status_code, detail=f"{perms} permissions"))

# 8. Create API Key
r = httpx.post(f"{BASE}/api/v1/api-keys", headers=HDR,
    json={"name": "verify-key", "scope": "readonly"}, timeout=5)
results.append(check("Create API Key", r.status_code, expected=201))
raw_key = r.json().get("data", {}).get("raw_key", "") if r.status_code == 201 else ""

# 9. API Key auth
if raw_key:
    r = httpx.get(f"{BASE}/api/v1/pipelines",
        headers={"X-API-Key": raw_key}, timeout=5)
    results.append(check("API Key auth", r.status_code, detail="X-API-Key works"))

# 10. Prometheus metrics
r = httpx.get(f"{BASE}/metrics", timeout=5)
has_etl = "etl_http_requests_total" in r.text
results.append(check("Prometheus /metrics", r.status_code,
    detail=f"etl_metrics={'YES' if has_etl else 'NO'}"))

# 11. Ingestion events
r = httpx.get(f"{BASE}/api/v1/ingest/events", headers=HDR, timeout=5)
results.append(check("Ingestion events", r.status_code))

# 12. Load history
r = httpx.get(f"{BASE}/api/v1/load/history", headers=HDR, timeout=5)
results.append(check("Load history", r.status_code))

# 13. Pipeline definitions
r = httpx.get(f"{BASE}/api/v1/pipelines/definitions", headers=HDR, timeout=5)
defs = len(r.json().get("data", []))
results.append(check("Pipeline definitions", r.status_code, detail=f"{defs} definitions"))

# 14. Refresh token
r2_login = httpx.post(f"{BASE}/api/v1/auth/login",
    json={"username": "admin", "password": "Admin1234!"}, timeout=5)
refresh_token = r2_login.json()["data"]["refresh_token"]
r = httpx.post(f"{BASE}/api/v1/auth/refresh",
    json={"refresh_token": refresh_token}, timeout=5)
results.append(check("Token refresh", r.status_code, detail="new access+refresh tokens"))

# 15. Swagger docs
r = httpx.get(f"{BASE}/docs", timeout=5)
results.append(check("Swagger UI /docs", r.status_code))

print()
passed = sum(results)
total = len(results)
print("=" * 50)
print(f"  Result: {passed}/{total} checks passed")
if passed == total:
    print("  ALL CHECKS PASSED — System is fully operational!")
else:
    print(f"  {total-passed} check(s) failed")
print()
print(f"  API:       http://localhost:8001")
print(f"  Swagger:   http://localhost:8001/docs")
print(f"  Metrics:   http://localhost:8001/metrics")
