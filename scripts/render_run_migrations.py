"""Run database migrations on Render via their Jobs API."""
import httpx, time

TOKEN   = "rnd_bRRneBs9NsBn1ulV9PAnNcKYVEDZ"
SVC_ID  = "srv-d9573v3tqb8s73eg9ecg"
API     = "https://api.render.com/v1"
H       = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json",
           "Content-Type": "application/json"}

# Trigger a one-off job to run migrations
print("Creating migration job...")
r = httpx.post(f"{API}/services/{SVC_ID}/jobs", headers=H, timeout=30,
               json={"startCommand": "python scripts/setup_database.py --skip-seed"})
print(f"  Status: {r.status_code}")
if r.status_code in (200, 201):
    job = r.json()
    job_id = job.get("id", "?")
    print(f"  Job ID: {job_id}")
    print(f"  Status: {job.get('status','?')}")

    # Monitor job
    print("\nMonitoring job...")
    for i in range(30):
        time.sleep(5)
        r2 = httpx.get(f"{API}/services/{SVC_ID}/jobs/{job_id}", headers=H, timeout=15)
        if r2.status_code == 200:
            j = r2.json()
            status = j.get("status", "?")
            print(f"  [{i+1:02d}] {status}")
            if status in ("succeeded", "failed", "canceled"):
                print(f"\nJob {status}!")
                break
else:
    print(f"  Error: {r.text[:300]}")
    print("\nAlternative: Run manually in Render Shell:")
    print(f"  1. Go to: https://dashboard.render.com/web/{SVC_ID}/shell")
    print(f"  2. Run: python scripts/setup_database.py")
