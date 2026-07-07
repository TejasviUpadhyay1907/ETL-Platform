"""Check ingest event response schema."""
import httpx

BASE = "https://etl-platform-api.onrender.com"
r = httpx.post(f"{BASE}/api/v1/auth/login",
               json={"username":"admin","password":"Admin1234!"}, timeout=15)
token = r.json()["data"]["access_token"]
HDR = {"Authorization": f"Bearer {token}"}

r2 = httpx.get(f"{BASE}/api/v1/ingest/events?page_size=3", headers=HDR, timeout=15)
events = r2.json().get("data", [])
print(f"Total events: {r2.json().get('pagination',{}).get('total_items',0)}")
for ev in events[:2]:
    print("\nEvent fields:", list(ev.keys()))
    for k, v in ev.items():
        print(f"  {k}: {str(v)[:60]}")
