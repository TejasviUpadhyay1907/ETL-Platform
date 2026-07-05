"""Check Render deployment status and get DB connection info."""
import httpx, time, json

TOKEN  = "rnd_bRRneBs9NsBn1ulV9PAnNcKYVEDZ"
SVC_ID = "srv-d9573v3tqb8s73eg9ecg"
DB_ID  = "dpg-d9573ggk1i2s739rqr20-a"
SVC_URL = "https://etl-platform-api.onrender.com"
API    = "https://api.render.com/v1"
H = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
     "Content-Type": "application/json"}

# Get full DB object to see ALL fields
r = httpx.get(f"{API}/postgres/{DB_ID}", headers=H, timeout=15)
print("DB fields available:")
db = r.json()
for k, v in db.items():
    if "connection" in k.lower() or "host" in k.lower() or "pass" in k.lower() or "url" in k.lower():
        print(f"  {k}: {str(v)[:80]}")

# Build connection string from individual fields
host = db.get("host","")
port = db.get("port", 5432)
dbname = db.get("databaseName","etl_platform")
user   = db.get("databaseUser","etl_user")
passwd = db.get("databasePassword","") or db.get("password","")
print(f"\n  host={host} port={port} db={dbname} user={user} pw={'YES' if passwd else 'NO'}")

if host and passwd:
    db_url = f"postgresql+psycopg2://{user}:{passwd}@{host}:{port}/{dbname}"
    print(f"\n  DB URL built: {db_url[:60]}...")
    # Set it
    r2 = httpx.put(f"{API}/services/{SVC_ID}/env-vars",
                   headers=H, json=[{"key":"DATABASE_URL","value":db_url}], timeout=15)
    print(f"  Set DATABASE_URL: {r2.status_code}")
    # Redeploy
    r3 = httpx.post(f"{API}/services/{SVC_ID}/deploys",
                    headers=H, json={"clearCache":"do_not_clear"}, timeout=15)
    print(f"  Redeploy: {r3.status_code}")

# Check deploy status
print("\n\nCurrent deploys:")
r = httpx.get(f"{API}/services/{SVC_ID}/deploys?limit=3", headers=H, timeout=15)
if r.status_code == 200 and r.text:
    try:
        deploys = r.json()
        for item in deploys:
            d = item.get("deploy") or item
            print(f"  id={d.get('id','?')[:12]} status={d.get('status','?')} created={d.get('createdAt','?')[:19]}")
    except Exception as e:
        print(f"  Parse error: {e} | raw: {r.text[:200]}")

# Test live URL
print("\nTesting live endpoint:")
try:
    rh = httpx.get(f"{SVC_URL}/api/v1/health/ping", timeout=10)
    print(f"  {rh.status_code}: {rh.text[:100]}")
except Exception as e:
    print(f"  Not live yet: {type(e).__name__}")
