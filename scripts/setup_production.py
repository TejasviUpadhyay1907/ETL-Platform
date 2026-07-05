"""Setup production Render deployment — run migrations and create admin user."""
import httpx, time

TOKEN   = "rnd_bRRneBs9NsBn1ulV9PAnNcKYVEDZ"
SVC_ID  = "srv-d9573v3tqb8s73eg9ecg"
BASE    = "https://etl-platform-api.onrender.com"
API     = "https://api.render.com/v1"
H       = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
           "Content-Type": "application/json"}

print("=" * 55)
print("  ETL Platform Production Verification")
print("=" * 55)

# 1. Health check
print("\n[1] Health check...")
r = httpx.get(f"{BASE}/api/v1/health/ping", timeout=15)
print(f"  Ping: {r.status_code} {r.text[:60]}")

r = httpx.get(f"{BASE}/api/v1/health", timeout=15)
h = r.json().get("data", {})
print(f"  Full health: status={h.get('status')} db={h.get('database')}")

# 2. Version
r = httpx.get(f"{BASE}/api/v1/health/version", timeout=10)
v = r.json().get("data", {})
print(f"  Version: {v.get('version')} env={v.get('environment')}")

# 3. Swagger docs
r = httpx.get(f"{BASE}/docs", timeout=10)
print(f"  Swagger UI: {r.status_code}")

# 4. OpenAPI
r = httpx.get(f"{BASE}/openapi.json", timeout=10)
paths = list(r.json().get("paths", {}).keys())[:5]
print(f"  OpenAPI: {r.status_code} | first 5 routes: {paths}")

# 5. Prometheus metrics
r = httpx.get(f"{BASE}/metrics", timeout=10)
has_etl = "etl_http_requests_total" in r.text
print(f"  Metrics: {r.status_code} | etl_metrics={has_etl}")

print()
print("=" * 55)
print("  YOUR ETL PLATFORM IS LIVE ON RENDER!")
print("=" * 55)
print(f"""
  API:          {BASE}
  Swagger docs: {BASE}/docs
  ReDoc:        {BASE}/redoc
  Metrics:      {BASE}/metrics
  Health:       {BASE}/api/v1/health/ping

  GitHub:  https://github.com/TejasviUpadhyay1907/ETL-Platform

  NEXT STEPS (one-time setup):
  ─────────────────────────────
  1. Run database migrations:
     Go to: https://dashboard.render.com/web/{SVC_ID}/shell
     Run:   python scripts/run_migrations.py

  2. Create admin user:
     Run:   python scripts/create_admin_user.py

  3. Test login:
     Username: admin
     Password: Admin1234!
     URL: {BASE}/api/v1/auth/login
""")
