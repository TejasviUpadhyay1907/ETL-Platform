"""Get Render build logs for latest failed deploy."""
import httpx

TOKEN  = "rnd_bRRneBs9NsBn1ulV9PAnNcKYVEDZ"
SVC_ID = "srv-d9573v3tqb8s73eg9ecg"
DEP_ID = "dep-d9575vlt"   # latest failed deploy
API    = "https://api.render.com/v1"
H = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

r = httpx.get(f"{API}/services/{SVC_ID}/deploys/{DEP_ID}/rollback-eligible", headers=H, timeout=15)
print("rollback eligible:", r.status_code, r.text[:200])

# Get logs
r = httpx.get(f"{API}/services/{SVC_ID}/events?limit=20", headers=H, timeout=15)
print("\nService events:")
if r.status_code == 200:
    try:
        events = r.json()
        for ev in events[:10]:
            e = ev.get("event") or ev
            print(f"  type={e.get('type','?')} details={str(e.get('details',''))[:100]}")
    except:
        print(r.text[:400])

# Check deploy details
r = httpx.get(f"{API}/services/{SVC_ID}/deploys/{DEP_ID}", headers=H, timeout=15)
print(f"\nDeploy details ({r.status_code}):")
if r.status_code == 200:
    try:
        d = r.json()
        dep = d.get("deploy") or d
        print(f"  status: {dep.get('status')}")
        print(f"  cause:  {dep.get('cause','?')}")
        print(f"  error:  {dep.get('error','?')}")
        print(f"  all keys: {list(dep.keys())}")
    except:
        print(r.text[:400])
