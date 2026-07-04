"""
Global exception handlers for FastAPI.

Maps application exceptions and framework exceptions to standardized
HTTP responses using the APIResponse envelope format.

Every exception type has a registered handler. Unhandled exceptions
fall through to the generic 500 handler.
"""

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    APIException,
    AuthenticationException,
    AuthorizationException,
    ConfigurationException,
    DatabaseConnectionException,
    DatabaseException,
    ETLPlatformException,
    FileException,
    NotFoundException,
    PipelineException,
    RateLimitException,
    ValidationException,
)
from app.logging.logger import get_logger

logger = get_logger(__name__)


def _build_error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: list[dict] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    """Build a standardized JSON error response."""
    content = {
        "success": False,
        "data": None,
        "error": {
            "code": error_code,
            "message": message,
            "details": details or [],
        },
        "meta": {
            "request_id": request_id,
            "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
            "version": "1.0",
        },
    }
    return JSONResponse(status_code=status_code, content=content)


def _get_request_id(request: Request) -> str | None:
    """Extract request ID from request state (set by RequestIDMiddleware)."""
    return getattr(request.state, "request_id", None)


async def etl_platform_exception_handler(
    request: Request, exc: ETLPlatformException
) -> JSONResponse:
    """Handle all custom application exceptions."""
    request_id = _get_request_id(request)

    logger.error(
        f"Application exception: {exc.error_code}",
        path=request.url.path,
        method=request.method,
        error_code=exc.error_code,
        message=exc.message,
        status_code=exc.status_code,
        request_id=request_id,
    )

    return _build_error_response(
        status_code=exc.status_code,
        error_code=exc.error_code,
        message=exc.message,
        details=[d for d in exc.details] if exc.details else None,
        request_id=request_id,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic request validation errors."""
    request_id = _get_request_id(request)

    # Format pydantic validation errors into our standard detail format
    details = [
        {
            "field": ".".join(str(loc) for loc in error["loc"]) if error.get("loc") else None,
            "code": error.get("type", "VALIDATION_ERROR"),
            "message": error.get("msg", "Validation error"),
        }
        for error in exc.errors()
    ]

    logger.warning(
        "Request validation failed",
        path=request.url.path,
        error_count=len(details),
        request_id=request_id,
    )

    return _build_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error_code="REQUEST_VALIDATION_FAILED",
        message="Request validation failed. Check the details for field-level errors.",
        details=details,
        request_id=request_id,
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handle Starlette/FastAPI HTTP exceptions (404, 405, etc.)."""
    request_id = _get_request_id(request)

    # Map status code to error code
    error_code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        413: "PAYLOAD_TOO_LARGE",
        422: "UNPROCESSABLE_ENTITY",
        429: "TOO_MANY_REQUESTS",
        500: "INTERNAL_SERVER_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }
    error_code = error_code_map.get(exc.status_code, "HTTP_ERROR")

    logger.warning(
        f"HTTP {exc.status_code}: {exc.detail}",
        path=request.url.path,
        status_code=exc.status_code,
        request_id=request_id,
    )

    return _build_error_response(
        status_code=exc.status_code,
        error_code=error_code,
        message=str(exc.detail),
        request_id=request_id,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unexpected exceptions.

    Logs the full traceback and returns a generic 500 response.
    Never exposes internal error details to the client in production.
    """
    from app.core.config import get_config

    request_id = _get_request_id(request)
    config = get_config()

    logger.exception(
        f"Unhandled exception on {request.method} {request.url.path}",
        exc_info=exc,
        request_id=request_id,
    )

    # In development, include the error message; in production, use generic message
    message = str(exc) if config.is_development else "An internal error occurred."

    return _build_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code="INTERNAL_SERVER_ERROR",
        message=message,
        request_id=request_id,
    )


def register_exception_handlers(app: "FastAPI") -> None:  # type: ignore[name-defined]  # noqa: F821
    """
    Register all exception handlers on the FastAPI application.

    Called once during app initialization.

    Args:
        app: FastAPI application instance.
    """
    from fastapi import FastAPI  # Local import to avoid circular

    app.add_exception_handler(ETLPlatformException, etl_platform_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)  # type: ignore[arg-type]

    logger.debug("Exception handlers registered")
