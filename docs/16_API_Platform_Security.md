# Phase 10 — Enterprise API Platform & Security Layer

## Overview

Phase 10 transforms the ETL platform into a production-ready secured backend service. Every existing pipeline, ingestion, data, quality, and load API is now protected by JWT authentication and RBAC. New endpoints cover user management, role administration, and API key lifecycle.

```
Client Request
     │
     ▼
RateLimitMiddleware   ← sliding-window per user/IP
     │
     ▼
JWTAuthMiddleware     ← validates Bearer token or X-API-Key
     │
     ▼
RequestIDMiddleware   ← attaches X-Request-ID
     │
     ▼
RequestLoggingMiddleware
     │
     ▼
SecurityHeadersMiddleware  ← CORS, CSP, HSTS, X-Frame-Options…
     │
     ▼
FastAPI Router
     │
     ▼
Depends(get_current_user)   ← loads user + permissions from request.state
     │
     ├── Depends(require_permission("pipelines:run"))
     ├── Depends(require_role("administrator"))
     │
     ▼
Service Layer  →  ETL Engines (unchanged)
     │
     ▼
AuditLog  ← security events persisted
     │
     ▼
APIResponse[T]  ← standard envelope
```

---

## Authentication

### JWT Flow

```
POST /api/v1/auth/login  →  { access_token, refresh_token }
                                    │
              ┌─────────────────────┘
              ▼
Authorization: Bearer <access_token>   (60-minute default lifetime)
              │
              ▼
POST /api/v1/auth/refresh  ←  refresh_token   (7-day lifetime)
              │
              ▼
              new access_token + new refresh_token (rotation)
              │
POST /api/v1/auth/logout   ←  refresh_token   (revokes session)
```

**Access token payload:**
```json
{
  "sub":      "user-uuid",
  "username": "alice",
  "roles":    ["data_engineer"],
  "scope":    "access",
  "jti":      "uuid4",
  "iat":      1234567890,
  "exp":      1234567890
}
```

### API Key Authentication

API keys are an alternative to JWT for programmatic/CI access:

```
X-API-Key: etl_<64 hex chars>
```

Keys are:
- Stored as SHA-256 hashes — the plaintext is returned **once** at creation
- Scoped: `admin` | `pipeline` | `readonly`
- Validated against the `api_keys` table on every request
- Tracked: `last_used_at`, `request_count`

---

## RBAC Model

```
User  ──has──►  Role  ──has──►  Permission
                                  resource:action
```

### Built-in Roles

| Role | Description | Key Permissions |
|------|-------------|----------------|
| `administrator` | Full access | all permissions |
| `data_engineer` | Pipeline + data management | pipelines:*, data:*, api_keys:create |
| `operator` | Trigger and monitor pipelines | pipelines:run/cancel/read, data:read |
| `analyst` | Read-only analytics | pipelines:read, data:read, quality:read |
| `viewer` | Minimal read access | pipelines:read, data:read |

### Permission Naming Convention

```
resource:action

resources: pipelines, data, quality, users, roles, api_keys, admin
actions:   read, write, run, cancel, delete, create, revoke, rotate, all
```

### Superuser

Users with `is_superuser=True` bypass all permission checks. Assign sparingly.

---

## Database Models

### New Auth Tables (Phase 10)

| Table | Description |
|-------|-------------|
| `users` | User accounts with bcrypt-hashed passwords |
| `roles` | Named role definitions |
| `permissions` | Granular resource:action capabilities |
| `user_roles` | Many-to-many join: User ↔ Role |
| `role_permissions` | Many-to-many join: Role ↔ Permission |
| `api_keys` | Hashed API keys with scope and expiry |
| `user_sessions` | Active refresh token sessions |

---

## API Endpoints

### Authentication — `/api/v1/auth`

| Method | Path | Auth Required | Description |
|--------|------|--------------|-------------|
| `POST` | `/login` | No | Login → access + refresh token |
| `POST` | `/logout` | Yes | Revoke refresh token / session |
| `POST` | `/refresh` | No | Exchange refresh token for new pair |
| `POST` | `/change-password` | Yes | Change authenticated user's password |
| `GET`  | `/me` | Yes | Current user profile |

### User Management — `/api/v1/users`

| Method | Path | Permission |
|--------|------|-----------|
| `GET` | `/users` | `users:read` |
| `POST` | `/users` | `users:write` |
| `GET` | `/users/{id}` | `users:read` or self |
| `PUT` | `/users/{id}` | `users:write` |
| `DELETE` | `/users/{id}` | `users:delete` |
| `POST` | `/users/{id}/roles` | `roles:write` |
| `DELETE` | `/users/{id}/roles/{name}` | `roles:write` |
| `POST` | `/users/{id}/unlock` | `users:write` |

### Roles & Permissions — `/api/v1/roles`, `/api/v1/permissions`

| Method | Path | Permission |
|--------|------|-----------|
| `GET` | `/roles` | `roles:read` |
| `GET` | `/roles/{name}` | `roles:read` |
| `GET` | `/permissions` | `roles:read` |

### API Keys — `/api/v1/api-keys`

| Method | Path | Permission |
|--------|------|-----------|
| `POST` | `/api-keys` | `api_keys:create` |
| `GET` | `/api-keys` | `api_keys:read` |
| `DELETE` | `/api-keys/{id}` | `api_keys:revoke` |
| `POST` | `/api-keys/{id}/rotate` | `api_keys:rotate` |

---

## Rate Limiting

The `RateLimitMiddleware` uses an in-memory sliding window:

| Window | Default | Config key |
|--------|---------|-----------|
| Per minute | 60 req/min | `RATE_LIMIT_PER_MINUTE` |
| Per hour | 1000 req/hr | `RATE_LIMIT_PER_HOUR` |

Rate limit key priority: JWT `user_id` → client IP.

Response headers on every request:
```
X-RateLimit-Limit-Minute: 60
X-RateLimit-Remaining-Minute: 57
X-RateLimit-Limit-Hour: 1000
X-RateLimit-Remaining-Hour: 998
```

On violation → `429 Too Many Requests` with `Retry-After` header.

**Production note:** Replace the in-process `defaultdict` with a Redis-backed counter for multi-instance deployments.

---

## Security Headers

Set by `SecurityHeadersMiddleware` on every response:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
```

CORS is configured via `AppConfig.cors_*` settings. HSTS is added automatically in production mode.

---

## Public Endpoints (No Auth Required)

```
/api/v1/health/*
/api/v1/auth/login
/api/v1/auth/refresh
/docs
/redoc
/openapi.json
/static/*
```

All other endpoints require a valid Bearer token or X-API-Key.

---

## Account Security

| Feature | Behaviour |
|---------|-----------|
| Password hashing | bcrypt rounds=12 |
| Account locking | Locked after 5 consecutive failed logins |
| Transparent rehash | Old hashes upgraded on next successful login |
| Soft delete | Deleted users cannot log in; data preserved |
| Session revocation | Logout revokes the refresh token (rotation) |
| Key expiry | API keys support optional expiry timestamps |

---

## Configuration (`.env`)

```env
SECRET_KEY=change-me-in-production-min-32-chars
JWT_SECRET=change-me-in-production-min-32-chars
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000

CORS_ENABLED=true
CORS_ORIGINS=https://app.example.com
```

---

## Test Coverage

| Test file | Tests | Coverage area |
|-----------|-------|--------------|
| `test_auth_models.py` | 28 | DB models, RBAC seeding |
| `test_auth_services.py` | 37 | Password, JWT, API keys, AuthService, UserService |
| `test_auth_api.py` | 28 | Auth/Users/Roles/APIKeys endpoints, RBAC enforcement |

**Total new Phase 10 tests: 93**
**Full suite: 1051 tests, 0 failures**

---

## Extension Guide

### Adding a new role

```python
# app/auth/rbac.py
BUILT_IN_ROLES.append(RoleDef(
    name="data_scientist",
    display_name="Data Scientist",
    description="Read access plus pipeline trigger rights.",
    permissions=[Perm.DATA_READ, Perm.PIPELINES_READ, Perm.PIPELINES_RUN],
))
```

Then re-run `seed_roles_and_permissions(session)`.

### Protecting an endpoint

```python
from fastapi import Depends
from app.api.dependencies import require_permission
from app.auth.rbac import Perm

@router.post("/my-endpoint")
def my_endpoint(
    current_user: dict = Depends(require_permission(Perm.DATA_WRITE))
):
    ...
```

### OAuth hook (future)

`app/auth/jwt_handler.py` issues standard JWTs. To add an OAuth provider:
1. Add `POST /api/v1/auth/oauth/{provider}` endpoint
2. Exchange the provider token for a user record (create if first login)
3. Call `create_access_token()` + `create_refresh_token()` — same as password login
4. No changes to middleware or RBAC needed
