"""
Unit tests for the exception hierarchy.

Tests verify:
- All exceptions are constructable
- Default values are correct
- Custom fields are set properly
- Exception hierarchy is correct
"""

import pytest

from app.core.exceptions import (
    APIException,
    AuthenticationException,
    ConfigurationException,
    DatabaseConnectionException,
    DatabaseException,
    ETLPlatformException,
    FileException,
    FileTooLargeException,
    InvalidFileTypeException,
    NotFoundException,
    PipelineException,
    RateLimitException,
    ValidationException,
)


class TestETLPlatformException:
    """Base exception tests."""

    def test_basic_construction(self):
        exc = ETLPlatformException(message="Test error")
        assert exc.message == "Test error"
        assert exc.error_code == "INTERNAL_ERROR"
        assert exc.status_code == 500

    def test_custom_error_code(self):
        exc = ETLPlatformException(message="Custom", error_code="CUSTOM_CODE")
        assert exc.error_code == "CUSTOM_CODE"

    def test_custom_status_code(self):
        exc = ETLPlatformException(message="Custom", status_code=404)
        assert exc.status_code == 404

    def test_details_default_empty(self):
        exc = ETLPlatformException(message="Test")
        assert exc.details == []

    def test_is_exception(self):
        exc = ETLPlatformException(message="Test")
        assert isinstance(exc, Exception)

    def test_repr(self):
        exc = ETLPlatformException(message="Test", error_code="TEST")
        assert "ETLPlatformException" in repr(exc)
        assert "TEST" in repr(exc)


class TestDatabaseException:
    """Database exception tests."""

    def test_database_exception_status(self):
        exc = DatabaseException(message="DB error")
        assert exc.status_code == 503

    def test_connection_exception(self):
        exc = DatabaseConnectionException(message="Connection failed")
        assert exc.error_code == "DATABASE_CONNECTION_FAILED"
        assert isinstance(exc, DatabaseException)
        assert isinstance(exc, ETLPlatformException)


class TestFileExceptions:
    """File exception tests."""

    def test_file_too_large(self):
        exc = FileTooLargeException(
            message="Too large",
            file_size_bytes=1000,
            max_size_bytes=500,
        )
        assert exc.file_size_bytes == 1000
        assert exc.max_size_bytes == 500
        assert exc.status_code == 413
        assert exc.error_code == "FILE_TOO_LARGE"

    def test_invalid_file_type(self):
        exc = InvalidFileTypeException(
            message="Wrong type",
            file_extension="exe",
            allowed_types=["csv", "xlsx"],
        )
        assert exc.file_extension == "exe"
        assert exc.allowed_types == ["csv", "xlsx"]
        assert exc.error_code == "INVALID_FILE_TYPE"


class TestValidationException:
    """Validation exception tests."""

    def test_validation_exception(self):
        exc = ValidationException(
            message="Validation failed",
            dataset_type="orders",
            failed_rules=["RULE_001", "RULE_002"],
        )
        assert exc.dataset_type == "orders"
        assert len(exc.failed_rules) == 2
        assert exc.status_code == 422


class TestAPIExceptions:
    """API exception tests."""

    def test_not_found_status(self):
        exc = NotFoundException(message="Not found")
        assert exc.status_code == 404
        assert exc.error_code == "NOT_FOUND"

    def test_authentication_exception(self):
        exc = AuthenticationException(message="Auth failed")
        assert exc.status_code == 401
        assert exc.error_code == "AUTHENTICATION_FAILED"

    def test_rate_limit_exception(self):
        exc = RateLimitException(message="Too many requests", retry_after_seconds=60)
        assert exc.status_code == 429
        assert exc.retry_after_seconds == 60


class TestPipelineException:
    """Pipeline exception tests."""

    def test_pipeline_exception_with_context(self):
        exc = PipelineException(
            message="Pipeline failed",
            run_id="test-run-123",
            stage="validation",
        )
        assert exc.run_id == "test-run-123"
        assert exc.stage == "validation"
