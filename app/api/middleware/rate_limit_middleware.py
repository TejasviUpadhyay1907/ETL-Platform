"""
In-memory sliding-window rate limiter middleware.

Limits:
  - Per authenticated user (user_id from JWT)
  - Per IP address (for unauthenticated / API key requests)

Strategy: token-bucket / sliding window using an in-process dict.
Production note: Replace with Redis-backed counters for multi-instance deployments.

Configuration (from AppConfig):
  rate_limit_enabled:    bool  (kill switch)
  rate_limit_per_minute: int   (default 60)
  rate_limit_per_hour:   int   (default 1000)
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.logging.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Paths exempt from rate limiting (health / metrics)
# ---------------------------------------------------------------------------
_EXEMPT_PREFIXES = ("/api/v1/health", "/docs", "/redoc", "/openapi.json", "/static")


def _is_exempt(path: str) -> bool:
    return any(path.startswith(p) for p in _EXEMPT_PREFIXES)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter.

    Two windows checked per request:
      1. Per-minute  (short burst)
      2. Per-hour    (daily quota proxy)

    Returns 429 Too Many Requests with Retry-After header on violation.
    """

    def __init__(self, app, per_minute: int = 60, per_hour: int = 1000) -> None:
        super().__init__(app)
        self._per_minute = per_minute
        self._per_hour = per_hour
        # {key: deque of timestamps}
        self._minute_windows: dict[str, deque] = defaultdict(deque)
        self._hour_windows: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        from app.core.config import get_config
        cfg = get_config()

        if not cfg.rate_limit_enabled or _is_exempt(request.url.path):
            return await call_next(request)

        rate_key = self._get_rate_key(request)
        now = time.time()

        # -- Per-minute window --
        minute_q = self._minute_windows[rate_key]
        cutoff_min = now - 60
        while minute_q and minute_q[0] < cutoff_min:
            minute_q.popleft()

        if len(minute_q) >= self._per_minute:
            retry_after = int(60 - (now - minute_q[0])) + 1
            return self._rate_limit_response(retry_after, "per-minute limit exceeded")

        # -- Per-hour window --
        hour_q = self._hour_windows[rate_key]
        cutoff_hour = now - 3600
        while hour_q and hour_q[0] < cutoff_hour:
            hour_q.popleft()

        if len(hour_q) >= self._per_hour:
            retry_after = int(3600 - (now - hour_q[0])) + 1
            return self._rate_limit_response(retry_after, "per-hour limit exceeded")

        minute_q.append(now)
        hour_q.append(now)

        response = await call_next(request)

        # Inject rate-limit headers
        response.headers["X-RateLimit-Limit-Minute"] = str(self._per_minute)
        response.headers["X-RateLimit-Remaining-Minute"] = str(
            max(0, self._per_minute - len(minute_q))
        )
        response.headers["X-RateLimit-Limit-Hour"] = str(self._per_hour)
        response.headers["X-RateLimit-Remaining-Hour"] = str(
            max(0, self._per_hour - len(hour_q))
        )
        return response

    def _get_rate_key(self, request: Request) -> str:
        """
        Determine the rate-limit key for this request.

        Priority: JWT user_id > IP address
        """
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return f"user:{user_id}"
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"

    def _rate_limit_response(self, retry_after: int, reason: str) -> Response:
        import json
        from datetime import datetime

        logger.warning(f"Rate limit exceeded: {reason}")
        content = json.dumps({
            "success": False,
            "data": None,
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": f"Too many requests — {reason}. Try again in {retry_after}s.",
                "details": [],
            },
            "meta": {"timestamp": datetime.utcnow().isoformat(), "version": "1.0"},
        })
        resp = Response(content=content, status_code=429, media_type="application/json")
        resp.headers["Retry-After"] = str(retry_after)
        return resp
