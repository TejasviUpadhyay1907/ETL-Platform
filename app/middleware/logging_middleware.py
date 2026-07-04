"""
Request Logging Middleware.

Logs every incoming HTTP request and outgoing response with:
- HTTP method and path
- Status code
- Execution time in milliseconds
- Request ID (from RequestIDMiddleware)
- Client IP

This creates a complete access log for every API request, suitable
for performance analysis and security auditing.
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.logging.logger import get_logger

logger = get_logger(__name__)

# Paths to skip from access logging (noisy health checks)
SKIP_PATHS: frozenset[str] = frozenset(
    {
        "/api/v1/health/ping",
        "/favicon.ico",
    }
)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs every HTTP request and response.

    Captures timing at the middleware level to include the full
    request processing time (routing, handler, response formatting).
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Log request details and response status/timing."""
        start_time = time.perf_counter()
        request_id = getattr(request.state, "request_id", None)

        # Skip verbose access logging for health check noise, but still add timing header
        if request.url.path in SKIP_PATHS:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000
            response.headers["X-Process-Time-Ms"] = f"{duration_ms:.1f}"
            return response

        # Log incoming request
        logger.info(
            f"→ {request.method} {request.url.path}",
            method=request.method,
            path=request.url.path,
            query_string=str(request.url.query),
            client_host=request.client.host if request.client else "unknown",
            request_id=request_id,
        )

        # Process request and capture any errors
        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000

        # Log response
        log_method = logger.warning if response.status_code >= 400 else logger.info
        log_method(
            f"← {response.status_code} {request.method} {request.url.path} "
            f"[{duration_ms:.1f}ms]",
            status_code=response.status_code,
            method=request.method,
            path=request.url.path,
            duration_ms=round(duration_ms, 2),
            request_id=request_id,
        )

        # Add timing header for client visibility
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.1f}"

        return response
