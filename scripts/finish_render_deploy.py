"""Wire DB to service and trigger deploy."""
import time
import httpx

TOKEN  = "rnd_bRRneBs9NsBn1ulV9PAnNcKYVEDZ"
SVC_ID = "srv-d9573v3tqb8s73eg9ecg"
DB_ID  = "dpg-d9573ggk1i2s739rqr20-a"
API    = "https://api.render.com/v1"
SVC_URL = "https://etl-platform-api.onrender.com"

def req(method, path, **kw):
    h = {"Authorization": f"Bearer {TOKEN}",
         "Accept": "application/json", "Content-Type": "application/json"}
    return httpx.request(method, f"{API}{path}", headers=h, timeout=30, **kw)

print("\n=== Step 1: Get DB connection string ===")
r = req("GET", f"/postgres/{DB_ID}")
db = r.json()
# Try internal first, then external
conn_int  = db.get("internalConnectionString","")
conn_ext  = db.get("externalConnectionString","")
conn_pub  = db.get("publicUrl","") 

# Build all available connections
print(f"  internal: {conn_int[:50] if conn_int else 'not ready'}")
print(f"  external: {conn_ext[:50] if conn_ext else 'not ready'}")
print(f"  public:   {conn_pub[:50] if conn_pub else 'not ready'}")

# Use external (works from service on free tier)
db_url = conn_ext or conn_pub or conn_int
if not db_url:
    print("  DB connection not ready — checking connection info...")
    info = db.get("databaseUser","") 
    print(f"  DB raw: {str(db)[:300]}")
    # Fallback: use Render's standard connection info
    dbname = db.get("databaseName","etl_platform")
    user   = db.get("databaseUser","etl_user")
    host   = db.get("host","")
    port   = db.get("port", 5432)
    pwd    = db.get("databasePassword","")
    if host:
        db_url = f"postgres://{user}:{pwd}@{host}:{port}/{dbname}"
        print(f"  Built URL: {db_url[:60]}...")

if db_url:
    # Convert to psycopg2 format
    db_url_alchemy = db_url.replace("postgres://", "postgresql+psycopg2://")
    print(f"\n  Using: {db_url_alchemy[:60]}...")

    print("\n=== Step 2: Set DATABASE_URL on service ===")
    r = req("PUT", f"/services/{SVC_ID}/env-vars",
            json=[{"key": "DATABASE_URL", "value": db_url_alchemy}])
    print(f"  Set DATABASE_URL: {r.status_code}")
    if r.status_code not in (200, 201):
        print(f"  Response: {r.text[:200]}")
else:
    print("\n  WARNING: No DB URL available. Service will use its own DATABASE_URL if set.")

print("\n=== Step 3: Trigger Deploy ===")
r = req("POST", f"/services/{SVC_ID}/deploys", json={"clearCache": "clear"})
print(f"  Deploy triggered: {r.status_code}")
if r.status_code in (200, 201):
    deploy = r.json()
    did = deploy.get("id","?")
    status = deploy.get("status","?")
    print(f"  Deploy ID: {did}")
    print(f"  Status:    {status}")
else:
    print(f"  Response: {r.text[:200]}")

print(f"""
=== Deployment In Progress ===

Your API is deploying to Render (takes 3-5 min on free tier).

LIVE URL (will be active after build):
  API:     {SVC_URL}/api/v1/health/ping
  Swagger: {SVC_URL}/docs
  Metrics: {SVC_URL}/metrics

Monitor build: https://dashboard.render.com/web/{SVC_ID}/deploys

After build completes:
  1. Open: https://dashboard.render.com/web/{SVC_ID}/shell
  2. Run:  python scripts/create_admin_user.py
  3. Login: admin / Admin1234!
""")
