"""Check if Swagger UI docs are working on production."""
import httpx

BASE = "https://etl-platform-api.onrender.com"

r = httpx.get(f"{BASE}/docs", timeout=20)
print(f"Status:         {r.status_code}")
print(f"Size:           {len(r.text)} bytes")
print(f"Has swagger-ui: {'swagger-ui' in r.text}")
print(f"Has openapi ref:{'openapi.json' in r.text}")
print(f"Content-Type:   {r.headers.get('content-type','?')}")
print()
print("First 400 chars:")
print(r.text[:400])
print()

# Also test login still works
r2 = httpx.post(f"{BASE}/api/v1/auth/login",
    json={"username": "admin", "password": "Admin1234!"}, timeout=15)
print(f"Login: {r2.status_code} | user={r2.json().get('data',{}).get('username','?')}")
