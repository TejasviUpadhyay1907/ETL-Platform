"""
Prometheus metrics collection middleware.

Instruments every HTTP request with:
- Counter: total requests by method, endpoint, status
- Histogram: request duration in seconds
- Gauge: currently active requests

Normalizes endpoint paths to avoid high-cardinality labels
(e.g., /api/v1/pipelines/abc-123 → /api/v1/pipelines/{id}).
"""
from __future__ import annotations

import re
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match

# ---------------------------------------------------------------------------
# Path normalization — prevents cardinality explosion in Prometheus
# ---------------------------------------------------------------------------

_UUID_RE  = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_DIGIT_RE = re.compile(r"/\d+(?=/|$)")


def _normalize_path(path: str) -> str:
    """Replace UUIDs and numeric IDs with placeholders."""
    path = _UUID_RE.sub("{id}", path)
    path = _DIGIT_RE.sub("/{id}", path)
    return path


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """
    Thin middleware that records Prometheus metrics per HTTP request.

    Skips /metrics and /health paths to avoid self-instrumentation noise.
    """

    _SKIP_PATHS = frozenset({"/metrics", "/api/v1/health/ping", "/api/v1/health/live"})

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        if path in self._SKIP_PATHS:
            return await call_next(request)

        from app.observability.metrics import (
            http_active_requests,
            record_http_request,
        )

        normalized = _normalize_path(path)
        method = request.method
        http_active_requests.inc()
        start = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            duration = time.perf_counter() - start
            http_active_requests.dec()
            record_http_request(method, normalized, status_code, duration)

        return response
