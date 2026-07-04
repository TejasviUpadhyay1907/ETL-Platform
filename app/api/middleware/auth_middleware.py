"""
JWT Bearer token authentication middleware.

Validates the Authorization: Bearer <token> header on every request.
Public endpoints (health, login, OpenAPI docs) are exempt.

The authenticated principal is attached to request.state:
    request.state.user_id    : str (UUID)
    request.state.username   : str
    request.state.roles      : list[str]
    request.state.is_api_key : bool  (True when authenticated via API key)
    request.state.principal  : dict  (full decoded payload)

Downstream dependencies (get_current_user, require_permission) read from
request.state rather than re-decoding the token, keeping auth fast.
"""
from __future__ import annotations

from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.logging.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Paths exempt from authentication
# ---------------------------------------------------------------------------
_PUBLIC_PREFIXES = (
    "/api/v1/health",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/static",
    "/favicon.ico",
)


def _is_public(path: str) -> bool:
    return any(path.startswith(p) for p in _PUBLIC_PREFIXES)


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that validates JWT Bearer tokens.

    Attaches principal info to request.state on success.
    Returns 401 for missing/invalid tokens on protected endpoints.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if _is_public(request.url.path):
            return await call_next(request)

        # Try Bearer token first, then X-API-Key header
        auth_header = request.headers.get("Authorization", "")
        x_api_key = request.headers.get("X-API-Key", "")

        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):]
            try:
                from app.auth.jwt_handler import decode_access_token
                payload = decode_access_token(token)
                request.state.user_id = payload.get("sub", "")
                request.state.username = payload.get("username", "")
                request.state.roles = payload.get("roles", [])
                request.state.is_api_key = False
                request.state.principal = payload
                return await call_next(request)
            except Exception as exc:
                logger.debug(f"JWT auth failed: {exc}")
                return _unauthorized_response(str(exc))

        elif x_api_key:
            # API key authentication — validate against DB
            # We skip DB lookup in middleware (no session here) and defer it
            # to the get_current_user dependency which has a session.
            # Just mark the request as needing API key auth.
            request.state.pending_api_key = x_api_key
            request.state.is_api_key = True
            request.state.principal = None
            return await call_next(request)

        else:
            return _unauthorized_response(
                "Authentication required. Include Authorization: Bearer <token> "
                "or X-API-Key header."
            )


def _unauthorized_response(message: str) -> Response:
    """Build a 401 JSON response."""
    import json
    from datetime import datetime

    content = json.dumps({
        "success": False,
        "data": None,
        "error": {"code": "AUTHENTICATION_REQUIRED", "message": message, "details": []},
        "meta": {"timestamp": datetime.utcnow().isoformat(), "version": "1.0"},
    })
    return Response(
        content=content,
        status_code=401,
        media_type="application/json",
    )
