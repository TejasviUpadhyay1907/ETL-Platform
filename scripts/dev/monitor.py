"""Monitor Render deploy and test live URL."""
import httpx, time

TOKEN   = "rnd_bRRneBs9NsBn1ulV9PAnNcKYVEDZ"
SVC_ID  = "srv-d9573v3tqb8s73eg9ecg"
SVC_URL = "https://etl-platform-api.onrender.com"
API     = "https://api.render.com/v1"
H = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
     "Content-Type": "application/json"}

# Trigger deploy
r = httpx.post(f"{API}/services/{SVC_ID}/deploys",
               headers=H, timeout=15, json={"clearCache": "do_not_clear"})
print(f"Deploy triggered: {r.status_code}")

last = ""
for i in range(60):
    try:
        time.sleep(20)
        r = httpx.get(f"{API}/services/{SVC_ID}/deploys?limit=1", headers=H, timeout=15)
        d = r.json()[0].get("deploy", r.json()[0])
        s = d.get("status", "?")
        if s != last:
            print(f"  [{i+1:02d}] {s}")
            last = s
        if s in ("live", "failed", "build_failed", "canceled", "update_failed"):
            if s == "live":
                time.sleep(8)
                try:
                    rh = httpx.get(f"{SVC_URL}/api/v1/health/ping", timeout=20)
                    print(f"\nLIVE: {rh.status_code} {rh.text[:80]}")
                    print(f"API:     {SVC_URL}")
                    print(f"Swagger: {SVC_URL}/docs")
                    print(f"Metrics: {SVC_URL}/metrics")
                except Exception as e:
                    print(f"URL not yet: {e}")
            else:
                print(f"\nDeploy ended with: {s}")
                print(f"Check: https://dashboard.render.com/web/{SVC_ID}/deploys")
            break
    except Exception as e:
        print(f"  [{i+1}] network error: {type(e).__name__} — retrying")
        time.sleep(10)
