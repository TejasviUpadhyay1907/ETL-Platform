"""Get PostgreSQL credentials from Render and set DATABASE_URL on service."""
import httpx

TOKEN  = "rnd_bRRneBs9NsBn1ulV9PAnNcKYVEDZ"
DB_ID  = "dpg-d9573ggk1i2s739rqr20-a"
SVC_ID = "srv-d9573v3tqb8s73eg9ecg"
API    = "https://api.render.com/v1"
H = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
     "Content-Type": "application/json"}

# Try the connection-info endpoint
endpoints_to_try = [
    f"/postgres/{DB_ID}/connection-info",
    f"/postgres/{DB_ID}/credentials",
    f"/postgres/{DB_ID}/connection",
    f"/postgres/{DB_ID}",
]

db_url = None
for ep in endpoints_to_try:
    r = httpx.get(f"{API}{ep}", headers=H, timeout=15)
    print(f"{ep}: {r.status_code}")
    if r.status_code == 200 and r.text:
        import json
        try:
            data = r.json()
            print(f"  Keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
            # Look for any connection string or password
            for key, val in (data.items() if isinstance(data, dict) else []):
                if any(x in key.lower() for x in ['connection','url','pass','host','string']):
                    print(f"  {key}: {str(val)[:80]}")
                    if 'connection' in key.lower() and isinstance(val, str) and 'postgres' in val:
                        db_url = val
        except:
            print(f"  raw: {r.text[:200]}")

if not db_url:
    # The DB hostname on Render follows a pattern: dpg-ID.region-postgres.render.com
    # We know: user=etl_user, db=etl_platform, host=dpg-d9573ggk1i2s739rqr20-a.oregon-postgres.render.com
    # Password must be fetched from dashboard — let's try the retrieve-password endpoint
    r = httpx.post(f"{API}/postgres/{DB_ID}/retrieve-password", headers=H, timeout=15)
    print(f"\nretrieve-password: {r.status_code} {r.text[:200]}")
