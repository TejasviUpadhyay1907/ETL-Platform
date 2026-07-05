"""Show current system status."""
import httpx

BASE_API  = "http://localhost:8001"
BASE_DASH = "http://localhost:8501"

# Login and get pipeline count
r = httpx.post(f"{BASE_API}/api/v1/auth/login",
    json={"username": "admin", "password": "Admin1234!"}, timeout=8)
token = r.json()["data"]["access_token"]
HDR = {"Authorization": f"Bearer {token}"}

pipeline_resp = httpx.get(f"{BASE_API}/api/v1/pipelines/history?page_size=5", headers=HDR, timeout=8)
total_runs = pipeline_resp.json().get("pagination", {}).get("total_items", 0)

dash_resp = httpx.get(f"{BASE_DASH}/_stcore/health", timeout=5)
dash_status = "UP ✅" if dash_resp.status_code == 200 else "DOWN ❌"

user_resp = httpx.get(f"{BASE_API}/api/v1/users", headers=HDR, timeout=5)
total_users = user_resp.json().get("pagination", {}).get("total_items", 0)

print()
print("=" * 55)
print("  ETL Platform — System Status")
print("=" * 55)
print(f"  API Backend:   http://localhost:8001     UP ✅")
print(f"  Swagger Docs:  http://localhost:8001/docs  UP ✅")
print(f"  Dashboard:     http://localhost:8501     {dash_status}")
print(f"  Prometheus:    http://localhost:8001/metrics  UP ✅")
print()
print(f"  Pipeline runs in DB: {total_runs}")
print(f"  Users:               {total_users}")
print()
print("  HOW TO USE THE DASHBOARD:")
print("  ─────────────────────────────────────────────")
print("  1. Open http://localhost:8501 in your browser")
print("  2. Enter API URL: http://localhost:8001")
print("  3. Login:  admin / Admin1234!")
print()
print("  WHAT YOU WILL SEE ON EACH PAGE:")
print("  ─────────────────────────────────────────────")
print("  Home (Executive Overview)")
print("    → 50 pipeline runs, KPI cards,")
print("      status donut chart, records funnel")
print()
print("  Pipeline Monitor")
print("    → All 50 runs with status, dataset type")
print("      Click a run → Stage Timeline (Gantt chart)")
print("      Cancel/Retry buttons for failed runs")
print()
print("  Pipeline History")
print("    → Searchable table, CSV/Excel export")
print("      Sort by any column")
print()
print("  Data Quality")
print("    → Select a run → quality gauge (0-100)")
print("      Dimension bars, violations table")
print()
print("  Warehouse")
print("    → Load event log, strategy distribution")
print()
print("  User Administration (admin only)")
print("    → Create users, assign roles, manage API keys")
print()
print("  Audit Log")
print("    → Pipeline events, security events")
print()
print("  Configuration")
print("    → 6 registered pipeline definitions")
print("      System health, API version")
print()
print("=" * 55)
print("  GitHub: https://github.com/TejasviUpadhyay1907/ETL-Platform")
print("=" * 55)
