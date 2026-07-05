"""Check last pipeline run error details."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx

BASE = "http://localhost:8001"
r = httpx.post(f"{BASE}/api/v1/auth/login",
    json={"username": "admin", "password": "Admin1234!"}, timeout=5)
token = r.json()["data"]["access_token"]
HDR = {"Authorization": f"Bearer {token}"}

# Last 3 runs
runs = httpx.get(f"{BASE}/api/v1/pipelines/history?page_size=5", headers=HDR, timeout=8).json()
for run in runs.get("data", [])[:3]:
    rid = run["id"]
    print(f"\nRun: {run['run_number']} | status: {run['status']} | id: {rid[:8]}...")
    events = httpx.get(f"{BASE}/api/v1/pipelines/{rid}/events?page_size=10",
                       headers=HDR, timeout=8).json()
    for ev in events.get("data", []):
        sev = ev.get("severity", "")
        etype = ev.get("event_type", "")
        stage = ev.get("stage", "") or ""
        msg = ev.get("message", "")[:120]
        print(f"  [{sev:8}] {etype:25} stage={stage:15} | {msg}")

# Also check the ingestion event
print("\n\nIngestion event details:")
ev_r = httpx.get(f"{BASE}/api/v1/ingest/events/75d878d6-35eb-4049-bc1d-b45aed928358",
                 headers=HDR, timeout=8)
if ev_r.status_code == 200:
    ev = ev_r.json().get("data", {})
    print(f"  file_path:  {ev.get('file_path')}")
    print(f"  stored_at:  {ev.get('stored_filename')}")
    print(f"  status:     {ev.get('status')}")
    print(f"  row_count:  {ev.get('row_count')}")
