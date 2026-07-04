"""
Request ID Middleware.

Assigns a unique UUID to every incoming request and attaches it to:
1. The request state (for use in logging and error responses)
2. The response headers (X-Request-ID) so clients can correlate requests

This enables distributed tracing and makes it easy to find a specific
request in logs when debugging production issues.
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that assigns a unique request ID to every request.

    The ID is read from the incoming X-Request-ID header if present
    (allowing clients to set their own trace ID), or generated as a new UUID.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Assign request ID and propagate through request/response cycle."""
        # Use client-provided ID if present, else generate new one
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())

        # Attach to request state for use in handlers and logging
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Echo back in response headers for client correlation
        response.headers[REQUEST_ID_HEADER] = request_id

        return response
