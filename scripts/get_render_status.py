"""Get status of existing Render deployment."""
import sys
import httpx

TOKEN = "rnd_bRRneBs9NsBn1ulV9PAnNcKYVEDZ"
RENDER_API = "https://api.render.com/v1"

def api(method, path, **kwargs):
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
                "Content-Type": "application/json"}
    r = httpx.request(method, f"{RENDER_API}{path}", headers=headers, timeout=30, **kwargs)
    return r

print("\n=== Render Services ===")
r = api("GET", "/services?limit=20")
services = r.json()
for item in services:
    svc = item.get("service", item)
    name = svc.get("name","?")
    sid = svc.get("id","?")
    url = svc.get("serviceDetails", {}).get("url","") or svc.get("url","")
    status = svc.get("suspended","?")
    stype = svc.get("type","?")
    print(f"  Name: {name}")
    print(f"  ID:   {sid}")
    print(f"  Type: {stype}")
    print(f"  URL:  {url}")
    print()

print("\n=== Render Postgres DBs ===")
r = api("GET", "/postgres?limit=20")
dbs = r.json()
for item in dbs:
    db = item.get("postgres", item)
    name = db.get("name","?")
    did = db.get("id","?")
    conn = db.get("internalConnectionString","") or db.get("externalConnectionString","")
    status = db.get("status","?")
    print(f"  Name:   {name}")
    print(f"  ID:     {did}")
    print(f"  Status: {status}")
    print(f"  Conn:   {conn[:60] if conn else 'pending...'}")
    print()
