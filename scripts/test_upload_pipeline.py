"""Test the full upload → pipeline flow on production."""
import httpx, time
from pathlib import Path

BASE   = "https://etl-platform-api.onrender.com"
SAMPLE = Path("data/sample/orders_valid.csv")

# Login
r = httpx.post(f"{BASE}/api/v1/auth/login",
               json={"username":"admin","password":"Admin1234!"}, timeout=15)
token = r.json()["data"]["access_token"]
HDR   = {"Authorization": f"Bearer {token}"}
print(f"Login: OK")

# Upload with unique content
import hashlib, time as _time
ts = int(_time.time())
content = SAMPLE.read_text(encoding="utf-8")
unique_content = content.rstrip("\n") + f"\n# test_{ts}\n"

print(f"Uploading orders CSV...")
r = httpx.post(
    f"{BASE}/api/v1/ingest/upload",
    headers={"Authorization": f"Bearer {token}"},
    files={"file": (f"orders_test_{ts}.csv", unique_content.encode(), "text/csv")},
    data={"dataset_type": "orders"},
    timeout=30,
)
print(f"Upload: {r.status_code}")
if r.status_code not in (200, 201):
    print(f"Error: {r.text[:300]}")
    exit(1)

data = r.json()["data"]
ing_id = data.get("ingestion_event_id","")
print(f"Ingestion ID: {ing_id[:8]}...")
print(f"Rows: {data.get('row_count')}")

# Trigger pipeline using ingestion_event_id
print(f"\nTriggering pipeline...")
r = httpx.post(
    f"{BASE}/api/v1/pipelines/run",
    headers={**HDR, "Content-Type": "application/json"},
    json={
        "dataset_type":       "orders",
        "pipeline_name":      "orders_pipeline",
        "triggered_by":       "test_script",
        "ingestion_event_id": ing_id,
        "original_filename":  f"orders_test_{ts}.csv",
    },
    timeout=120,
)
print(f"Pipeline: {r.status_code}")
if r.status_code != 200:
    print(f"Error: {r.text[:300]}")
    exit(1)

result = r.json()["data"]
print(f"\n{'='*50}")
print(f"Run ID:     {result.get('pipeline_run_id','')[:8]}...")
print(f"Status:     {result.get('status')}")
print(f"Success:    {result.get('success')}")
m = result.get("metrics", {})
print(f"Records In: {m.get('total_records_ingested',0)}")
print(f"Records Out:{m.get('total_records_loaded',0)}")
print(f"Quality:    {m.get('quality_score',0):.1f}%")
print(f"Duration:   {result.get('duration_seconds',0):.1f}s")
print()

stages = result.get("stage_results", [])
if stages:
    print("Stage Results:")
    for s in stages:
        icon = "[OK]" if s.get("status") in ("success","warning") else "[FAIL]"
        print(f"  {icon} {s.get('stage_name','?'):20s} in={s.get('input_records',0):>5} out={s.get('output_records',0):>5} {s.get('error_message') or ''}")

print(f"\nDone!")
