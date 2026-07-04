# Security Checklist — ETL Platform v1.0.0

## Authentication & Authorization

- [x] Passwords hashed with bcrypt (rounds=12) — never plaintext
- [x] JWT tokens with configurable expiry (default 60 min)
- [x] Refresh token rotation — old token revoked on use
- [x] Account locking after 5 failed logins
- [x] RBAC with 5 roles and 16 granular permissions
- [x] Superuser flag for full bypass (assign sparingly)
- [x] API keys hashed with SHA-256 — plaintext never stored
- [x] API key scoping (admin/pipeline/readonly)
- [x] Soft-delete — deleted users cannot authenticate
- [ ] TODO v1.1: MFA / TOTP support
- [ ] TODO v1.1: OAuth 2.0 provider integration

## Transport & Headers

- [x] `X-Frame-Options: DENY` — prevents clickjacking
- [x] `X-Content-Type-Options: nosniff`
- [x] `X-XSS-Protection: 1; mode=block`
- [x] `Referrer-Policy: strict-origin-when-cross-origin`
- [x] `server_tokens off` in Nginx
- [x] CORS restricted to configured origins
- [ ] TODO production: HSTS (`Strict-Transport-Security: max-age=31536000`)
- [ ] TODO production: TLS 1.2+ only in Nginx
- [ ] TODO production: CSP header

## Rate Limiting

- [x] Per-user sliding window (60 req/min, 1000 req/hr)
- [x] Per-IP fallback for unauthenticated requests
- [x] Separate stricter limit on `/auth/login` (Nginx: 5 req/min)
- [x] 429 response includes `Retry-After` header
- [ ] TODO v1.1: Redis-backed distributed rate limiter

## Input Validation

- [x] Pydantic v2 validates all request bodies and query params
- [x] File type validation (extension + MIME check)
- [x] File size limit (configurable, default 500 MB)
- [x] SQL injection prevented by SQLAlchemy ORM (no raw queries)
- [x] UUID validation on path parameters
- [x] Pattern validation on Pydantic fields (status, scope, etc.)

## Secrets Management

- [x] No secrets in source code — all from environment variables
- [x] `.env` in `.gitignore`
- [x] `.env.example` contains only placeholder values
- [x] `detect-private-key` pre-commit hook enabled
- [ ] TODO production: Use HashiCorp Vault or AWS Secrets Manager
- [ ] TODO production: Rotate JWT_SECRET and API_KEY_SALT quarterly

## Container Security

- [x] Non-root user (uid 1001) in all containers
- [x] Multi-stage builds — no build tools in production image
- [x] `python:3.12-slim` base — minimal attack surface
- [x] Read-only nginx config volume mount (`:ro`)
- [x] Internal-only backend network (`internal: true` in compose)
- [ ] TODO: Run with `--read-only` filesystem flag
- [ ] TODO: Enable Docker Content Trust for image signing

## OWASP API Security Top 10

| Risk | Status | Implementation |
|------|--------|---------------|
| API1 — Broken Object Level Auth | ✅ | Users can only access own resources; RBAC enforces object-level |
| API2 — Broken Authentication | ✅ | JWT + bcrypt + account locking |
| API3 — Broken Object Property Level Auth | ✅ | Pydantic schemas control exposed fields |
| API4 — Unrestricted Resource Consumption | ✅ | Rate limiting + file size limits |
| API5 — Broken Function Level Auth | ✅ | `require_permission()` on all sensitive endpoints |
| API6 — Unrestricted Access to Sensitive Business Flows | ✅ | Pipeline trigger requires `pipelines:run` permission |
| API7 — Server Side Request Forgery | ✅ | No user-supplied URLs processed server-side |
| API8 — Security Misconfiguration | ✅ | CORS, security headers, server_tokens off |
| API9 — Improper Inventory Management | ✅ | OpenAPI docs maintained; versioned endpoints |
| API10 — Unsafe Consumption of APIs | ✅ | All external data validated through Pydantic |

## Dependency Security

Run regularly:
```bash
pip-audit -r requirements.txt
pip list --outdated
```

Known policy:
- No packages with CVSS score ≥ 9.0 in production dependencies
- All dependencies pinned to exact versions in `requirements.txt`
- Reviewed on every PR via GitHub Actions `security` job

## Audit Trail

- [x] All login/logout events in `audit_logs` table
- [x] All API requests can be correlated via `X-Request-ID`
- [x] Pipeline events (started, completed, failed) persisted
- [x] Record load events persisted
- [x] `user_id` recorded on all audit events
- [x] Source IP recorded on authentication events
- [x] Immutable audit log (INSERT-only, no UPDATE/DELETE)
