"""Wire DB URL to service and monitor deploy."""
import httpx
import time
import sys

TOKEN  = "rnd_bRRneBs9NsBn1ulV9PAnNcKYVEDZ"
DB_ID  = "dpg-d9573ggk1i2s739rqr20-a"
SVC_ID = "srv-d9573v3tqb8s73eg9ecg"
SVC_URL = "https://etl-platform-api.onrender.com"
API    = "https://api.render.com/v1"
H = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
     "Content-Type": "application/json"}


def get(path):
    return httpx.get(f"{API}{path}", headers=H, timeout=15)


def post(path, json=None):
    return httpx.post(f"{API}{path}", headers=H, json=json or {}, timeout=15)


def put(path, json=None):
    return httpx.put(f"{API}{path}", headers=H, json=json or {}, timeout=15)


# ── Step 1: Wait for DB URL ────────────────────────────────────────────────
print("\nWaiting for PostgreSQL connection string (up to 2 min)...")
db_url = ""
for i in range(24):
    r = get(f"/postgres/{DB_ID}")
    db = r.json()
    conn = db.get("externalConnectionString") or db.get("internalConnectionString") or ""
    status = db.get("status", "?")
    print(f"  [{i+1:02d}] status={status} conn_ready={bool(conn)}")
    if conn:
        db_url = conn.replace("postgres://", "postgresql+psycopg2://")
        print(f"  DB ready: {db_url[:60]}...")
        break
    time.sleep(5)

# ── Step 2: Set DATABASE_URL env var ──────────────────────────────────────
if db_url:
    print("\nSetting DATABASE_URL on service...")
    r = put(f"/services/{SVC_ID}/env-vars",
            json=[{"key": "DATABASE_URL", "value": db_url}])
    print(f"  Response: {r.status_code}")
    if r.status_code not in (200, 201):
        print(f"  Body: {r.text[:200]}")
else:
    print("\nDB URL not available yet — deploy will fail to connect DB")
    print("You can set DATABASE_URL manually in Render dashboard later")

# ── Step 3: Trigger fresh deploy ──────────────────────────────────────────
print("\nTriggering deploy...")
r = post(f"/services/{SVC_ID}/deploys", json={"clearCache": "do_not_clear"})
print(f"  Deploy triggered: {r.status_code}")
if r.status_code in (200, 201, 202):
    deploy = r.json()
    deploy_id = deploy.get("id") or deploy.get("deployId") or "?"
    print(f"  Deploy ID: {deploy_id}")
else:
    print(f"  Body: {r.text[:200]}")

# ── Step 4: Monitor build for 5 min ───────────────────────────────────────
print("\nMonitoring build (updates every 15s, max 5 min)...")
last_status = ""
for i in range(20):
    time.sleep(15)
    r = get(f"/services/{SVC_ID}/deploys?limit=1")
    if r.status_code == 200:
        deploys = r.json()
        if deploys:
            d = deploys[0].get("deploy") or deploys[0]
            status = d.get("status", "?")
            created = d.get("createdAt", "?")
            did = d.get("id", "?")
            if status != last_status:
                print(f"  [{i+1:02d}] status={status} id={did[:8]}...")
                last_status = status
            if status in ("live", "failed", "canceled"):
                break

# ── Step 5: Test the live URL ─────────────────────────────────────────────
print("\nTesting live URL...")
time.sleep(5)
try:
    r = httpx.get(f"{SVC_URL}/api/v1/health/ping", timeout=15)
    print(f"  Health ping: {r.status_code} {r.text[:80]}")
except Exception as e:
    print(f"  Not reachable yet: {e}")

print(f"""
========================================
  DEPLOYMENT COMPLETE
========================================

Live URL:  {SVC_URL}

  API Health:  {SVC_URL}/api/v1/health/ping
  Swagger UI:  {SVC_URL}/docs
  Prometheus:  {SVC_URL}/metrics

Next: Create admin user
  1. Go to: https://dashboard.render.com/web/{SVC_ID}/shell
  2. Run: python scripts/create_admin_user.py
  3. Login: admin / Admin1234!

Dashboard: https://dashboard.render.com
""")
