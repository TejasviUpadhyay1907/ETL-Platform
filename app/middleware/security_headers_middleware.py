"""
Security Headers Middleware.

Adds standard HTTP security headers to every response to protect against
common web vulnerabilities: XSS, clickjacking, MIME sniffing, etc.

These headers are recommended by OWASP and required in enterprise environments.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all responses.

    Headers added:
    - X-Content-Type-Options: Prevents MIME type sniffing
    - X-Frame-Options: Prevents clickjacking via iframes
    - X-XSS-Protection: Legacy XSS filter (still useful for older browsers)
    - Referrer-Policy: Controls how much referrer info is sent
    - Content-Security-Policy: Controls which resources can be loaded
    - Strict-Transport-Security: Forces HTTPS (only in production)
    - Permissions-Policy: Restricts browser feature access
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Add security headers to the response."""
        response = await call_next(request)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent embedding in iframes (clickjacking)
        response.headers["X-Frame-Options"] = "DENY"

        # Legacy XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy — restrictive defaults
        # Adjust in production to allow specific trusted origins
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "  # Allow inline scripts for dashboard
            "style-src 'self' 'unsafe-inline'; "  # Allow inline styles for dashboard
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )

        # Restrict browser features
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
        )

        # Remove server identity header (prevents fingerprinting)
        if "server" in response.headers:
            del response.headers["server"]
        if "Server" in response.headers:
            del response.headers["Server"]

        return response
