"""Fix Render service config and redeploy with correct Python version."""
import httpx, json

TOKEN  = "rnd_bRRneBs9NsBn1ulV9PAnNcKYVEDZ"
SVC_ID = "srv-d9573v3tqb8s73eg9ecg"
API    = "https://api.render.com/v1"
H = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
     "Content-Type": "application/json"}

# Get current service config
r = httpx.get(f"{API}/services/{SVC_ID}", headers=H, timeout=15)
svc = r.json()
sd = svc.get("serviceDetails", {})
print("Current config:")
print(f"  buildCommand: {sd.get('buildCommand','?')}")
print(f"  startCommand: {sd.get('startCommand','?')[:60]}")
print(f"  envSpecificDetails: {json.dumps(sd.get('envSpecificDetails',{}))[:200]}")

# Update service with correct build/start commands
# Render Python free tier: use pip with explicit upgrade first
update_payload = {
    "serviceDetails": {
        "buildCommand": "pip install --upgrade pip && pip install -r requirements.txt",
        "startCommand": "uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1",
        "envSpecificDetails": {
            "buildCommand": "pip install --upgrade pip && pip install -r requirements.txt",
            "startCommand": "uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1",
        },
    }
}
print("\nUpdating service config...")
r = httpx.patch(f"{API}/services/{SVC_ID}", headers=H, json=update_payload, timeout=15)
print(f"  Update: {r.status_code}")
if r.status_code not in (200, 201):
    print(f"  Body: {r.text[:300]}")

# Set remaining env vars including DATABASE_URL via Render's connection string
# The free PostgreSQL on Render exposes it as an env var when services are linked
# Let's check what env vars are on the service
print("\nCurrent env vars on service:")
r = httpx.get(f"{API}/services/{SVC_ID}/env-vars", headers=H, timeout=15)
if r.status_code == 200 and r.text:
    try:
        evars = r.json()
        for ev in evars[:10]:
            e = ev.get("envVar") or ev
            print(f"  {e.get('key','?')}: {str(e.get('value',''))[:40]}")
    except Exception as ex:
        print(f"  {r.text[:300]}")

# Add DATABASE_URL using Render internal DB URL format
# On Render free tier PostgreSQL, the connection string is available as:
# postgresql://etl_user:PASSWORD@dpg-xxxxx-a.oregon-postgres.render.com/etl_platform
# We need to get the password from the DB
print("\nDB info:")
r = httpx.get(f"{API}/postgres/dpg-d9573ggk1i2s739rqr20-a", headers=H, timeout=15)
db = r.json()
print(json.dumps({k:v for k,v in db.items() if k not in ['createdAt','updatedAt','expiresAt','dashboardUrl']}, indent=2)[:500])
