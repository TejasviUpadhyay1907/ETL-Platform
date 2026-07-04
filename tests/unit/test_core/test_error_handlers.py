"""
Coverage tests for app/api/error_handlers.py.

Tests the async exception handler functions directly without a live ASGI server.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.datastructures import URL


def _make_request(path: str = "/api/v1/test", method: str = "GET") -> Request:
    """Build a minimal Starlette Request object for handler testing."""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": [],
    }
    request = Request(scope)
    request.state.request_id = "test-req-id-001"
    return request


class TestETLPlatformExceptionHandler:

    @pytest.mark.asyncio
    async def test_returns_json_response(self):
        from app.api.error_handlers import etl_platform_exception_handler
        from app.core.exceptions import ETLPlatformException

        exc = ETLPlatformException(
            message="Something went wrong",
            error_code="PLATFORM_ERROR",
            status_code=500,
        )
        request = _make_request()
        response = await etl_platform_exception_handler(request, exc)
        assert response.status_code == 500
        import json
        body = json.loads(response.body)
        assert body["success"] is False
        assert body["error"]["code"] == "PLATFORM_ERROR"

    @pytest.mark.asyncio
    async def test_not_found_exception(self):
        from app.api.error_handlers import etl_platform_exception_handler
        from app.core.exceptions import NotFoundException

        exc = NotFoundException(message="Pipeline abc-123 not found")
        request = _make_request()
        response = await etl_platform_exception_handler(request, exc)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_exception_with_details(self):
        from app.api.error_handlers import etl_platform_exception_handler
        from app.core.exceptions import ValidationException

        exc = ValidationException(
            message="Validation failed",
            details=[{"field": "email", "message": "Invalid format"}],
        )
        request = _make_request()
        response = await etl_platform_exception_handler(request, exc)
        import json
        body = json.loads(response.body)
        assert len(body["error"]["details"]) == 1


class TestValidationExceptionHandler:

    @pytest.mark.asyncio
    async def test_returns_422(self):
        from app.api.error_handlers import validation_exception_handler

        # Simulate a pydantic v2 validation error via RequestValidationError
        errors = [
            {"loc": ("body", "email"), "msg": "value is not a valid email",
             "type": "value_error.email", "ctx": {}},
        ]
        exc = RequestValidationError(errors=errors)
        request = _make_request()
        response = await validation_exception_handler(request, exc)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_details_populated(self):
        from app.api.error_handlers import validation_exception_handler
        import json

        errors = [
            {"loc": ("body", "name"), "msg": "field required", "type": "missing"},
            {"loc": ("body", "age"), "msg": "value is not an integer",
             "type": "type_error.integer"},
        ]
        exc = RequestValidationError(errors=errors)
        request = _make_request()
        response = await validation_exception_handler(request, exc)
        body = json.loads(response.body)
        assert len(body["error"]["details"]) == 2
        assert body["error"]["code"] == "REQUEST_VALIDATION_FAILED"


class TestHTTPExceptionHandler:

    @pytest.mark.asyncio
    async def test_404_mapped_correctly(self):
        from app.api.error_handlers import http_exception_handler
        import json

        exc = StarletteHTTPException(status_code=404, detail="Not found")
        request = _make_request()
        response = await http_exception_handler(request, exc)
        assert response.status_code == 404
        body = json.loads(response.body)
        assert body["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_403_mapped_correctly(self):
        from app.api.error_handlers import http_exception_handler
        import json

        exc = StarletteHTTPException(status_code=403, detail="Forbidden")
        request = _make_request()
        response = await http_exception_handler(request, exc)
        assert response.status_code == 403
        body = json.loads(response.body)
        assert body["error"]["code"] == "FORBIDDEN"

    @pytest.mark.asyncio
    async def test_unknown_status_code_uses_fallback(self):
        from app.api.error_handlers import http_exception_handler
        import json

        exc = StarletteHTTPException(status_code=418, detail="I'm a teapot")
        request = _make_request()
        response = await http_exception_handler(request, exc)
        body = json.loads(response.body)
        assert body["error"]["code"] == "HTTP_ERROR"


class TestUnhandledExceptionHandler:

    @pytest.mark.asyncio
    async def test_returns_500(self):
        from app.api.error_handlers import unhandled_exception_handler
        import json

        exc = RuntimeError("Unexpected crash")
        request = _make_request()
        response = await unhandled_exception_handler(request, exc)
        assert response.status_code == 500
        body = json.loads(response.body)
        assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"

    @pytest.mark.asyncio
    async def test_development_mode_shows_message(self):
        from app.api.error_handlers import unhandled_exception_handler
        import json

        exc = RuntimeError("Detailed dev error")
        request = _make_request()

        mock_config = MagicMock()
        mock_config.is_development = True

        with patch("app.core.config.get_config", return_value=mock_config):
            response = await unhandled_exception_handler(request, exc)

        body = json.loads(response.body)
        assert "Detailed dev error" in body["error"]["message"]

    @pytest.mark.asyncio
    async def test_production_mode_hides_message(self):
        from app.api.error_handlers import unhandled_exception_handler
        import json

        exc = RuntimeError("Internal secret error")
        request = _make_request()

        mock_config = MagicMock()
        mock_config.is_development = False

        with patch("app.core.config.get_config", return_value=mock_config):
            response = await unhandled_exception_handler(request, exc)

        body = json.loads(response.body)
        assert "Internal secret error" not in body["error"]["message"]
        assert "internal error" in body["error"]["message"].lower()


class TestRegisterExceptionHandlers:

    def test_register_does_not_raise(self):
        from app.api.error_handlers import register_exception_handlers
        from fastapi import FastAPI

        app = FastAPI()
        register_exception_handlers(app)
        # No assertion needed — just ensure it doesn't raise
