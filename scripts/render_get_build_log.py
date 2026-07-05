"""Fetch actual build log text from Render."""
import httpx

TOKEN  = "rnd_bRRneBs9NsBn1ulV9PAnNcKYVEDZ"
SVC_ID = "srv-d9573v3tqb8s73eg9ecg"
API    = "https://api.render.com/v1"
H = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

# Get latest deploy ID
r = httpx.get(f"{API}/services/{SVC_ID}/deploys?limit=1", headers=H, timeout=15)
deploys = r.json()
dep = deploys[0].get("deploy") or deploys[0]
dep_id = dep.get("id","?")
print(f"Latest deploy: {dep_id} status={dep.get('status','?')}")

# Try to get logs
log_endpoints = [
    f"/services/{SVC_ID}/deploys/{dep_id}",
    f"/services/{SVC_ID}/logs?tail=100",
    f"/services/{SVC_ID}/deploys/{dep_id}/logs",
]
for ep in log_endpoints:
    r = httpx.get(f"{API}{ep}", headers=H, timeout=15)
    print(f"\n{ep}: {r.status_code}")
    if r.status_code == 200 and r.text and len(r.text) > 5:
        try:
            import json
            data = json.loads(r.text)
            print(str(data)[:600])
        except:
            print(r.text[:600])
