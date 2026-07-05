"""Fetch actual build log from Render."""
import httpx, json

TOKEN  = "rnd_bRRneBs9NsBn1ulV9PAnNcKYVEDZ"
SVC_ID = "srv-d9573v3tqb8s73eg9ecg"
BUILD_ID = "bld-d9575vls14us7384k250"
API    = "https://api.render.com/v1"
H = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

# Try getting logs from build
endpoints = [
    f"/services/{SVC_ID}/deploys",
    f"/services/{SVC_ID}/events?limit=5",
]
for ep in endpoints:
    r = httpx.get(f"{API}{ep}", headers=H, timeout=15)
    print(f"\n{ep}: {r.status_code}")
    if r.status_code == 200 and r.text:
        try:
            data = r.json()
            print(json.dumps(data[:2] if isinstance(data,list) else data, indent=2)[:800])
        except:
            print(r.text[:400])
