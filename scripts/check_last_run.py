"""Check last pipeline run error details."""
import httpx

BASE = "https://etl-platform-api.onrender.com"
r = httpx.post(f"{BASE}/api/v1/auth/login",
               json={"username":"admin","password":"Admin1234!"}, timeout=15)
token = r.json()["data"]["access_token"]
HDR = {"Authorization": f"Bearer {token}"}

# Get latest run
r = httpx.get(f"{BASE}/api/v1/pipelines/history?page_size=1", headers=HDR, timeout=15)
runs = r.json().get("data", [])
if not runs:
    print("No runs found")
    exit(0)

run = runs[0]
rid = run["id"]
print(f"Run: {run['run_number']} | status={run['status']} | id={rid[:8]}")

# Get events for this run
r = httpx.get(f"{BASE}/api/v1/pipelines/{rid}/events?page_size=20", headers=HDR, timeout=15)
events = r.json().get("data", [])
for ev in events:
    sev = ev.get("severity","")
    etype = ev.get("event_type","")
    stage = ev.get("stage","") or ""
    msg = ev.get("message","")[:120]
    if sev in ("ERROR","WARNING") or "failed" in etype.lower():
        print(f"  [{sev}] {etype} stage={stage}")
        print(f"         {msg}")
