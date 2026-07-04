"""
Centralized application exception hierarchy.

All custom exceptions inherit from ETLPlatformException, enabling
uniform error handling and logging throughout the application.

Design Principle: Every exception carries a machine-readable error_code
alongside the human-readable message. This enables programmatic error handling
by API consumers without parsing message strings.
"""

from http import HTTPStatus
from typing import Any


class ETLPlatformException(Exception):
    """
    Base exception for all application-specific exceptions.

    All custom exceptions MUST inherit from this class to ensure they are
    caught and handled by the global exception handler.
    """

    # Override in subclasses to provide a default HTTP status code
    default_status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR.value
    default_error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        status_code: int | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        """
        Initialize the exception.

        Args:
            message: Human-readable error description.
            error_code: Machine-readable error code (e.g. "FILE_TOO_LARGE").
            status_code: HTTP status code to return (overrides class default).
            details: Optional list of detail objects for structured error info.
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.default_error_code
        self.status_code = status_code or self.default_status_code
        self.details = details or []

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"error_code={self.error_code!r}, "
            f"status_code={self.status_code})"
        )


# =============================================================================
# Configuration Exceptions
# =============================================================================


class ConfigurationException(ETLPlatformException):
    """
    Raised when application configuration is invalid or missing.

    Typically raised at startup — the application should fail fast
    rather than proceed with invalid configuration.
    """

    default_status_code = HTTPStatus.INTERNAL_SERVER_ERROR.value
    default_error_code = "CONFIGURATION_ERROR"

    def __init__(
        self,
        message: str,
        missing_key: str | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.missing_key = missing_key


# =============================================================================
# Database Exceptions
# =============================================================================


class DatabaseException(ETLPlatformException):
    """
    Raised when a database operation fails.

    Wraps SQLAlchemy exceptions to decouple the database library
    from the rest of the application.
    """

    default_status_code = HTTPStatus.SERVICE_UNAVAILABLE.value
    default_error_code = "DATABASE_ERROR"


class DatabaseConnectionException(DatabaseException):
    """Raised when unable to connect to the database."""

    default_error_code = "DATABASE_CONNECTION_FAILED"


class DatabaseIntegrityException(DatabaseException):
    """Raised on constraint violations (duplicate keys, FK violations, etc.)."""

    default_status_code = HTTPStatus.CONFLICT.value
    default_error_code = "DATABASE_INTEGRITY_ERROR"


# =============================================================================
# Validation Exceptions
# =============================================================================


class ValidationException(ETLPlatformException):
    """
    Raised when data fails schema or business rule validation.

    Not to be confused with Pydantic validation errors — this exception
    represents pipeline-level data quality failures, not API request errors.
    """

    default_status_code = HTTPStatus.UNPROCESSABLE_ENTITY.value
    default_error_code = "VALIDATION_FAILED"

    def __init__(
        self,
        message: str,
        dataset_type: str | None = None,
        failed_rules: list[str] | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.dataset_type = dataset_type
        self.failed_rules = failed_rules or []


# =============================================================================
# File Exceptions
# =============================================================================


class FileException(ETLPlatformException):
    """Base exception for file-related operations."""

    default_status_code = HTTPStatus.BAD_REQUEST.value
    default_error_code = "FILE_ERROR"


class FileNotFoundException(FileException):
    """Raised when an expected file is not found on the file system."""

    default_status_code = HTTPStatus.NOT_FOUND.value
    default_error_code = "FILE_NOT_FOUND"


class FileTooLargeException(FileException):
    """Raised when an uploaded file exceeds the configured maximum size."""

    default_status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE.value
    default_error_code = "FILE_TOO_LARGE"

    def __init__(self, message: str, file_size_bytes: int, max_size_bytes: int) -> None:
        super().__init__(message=message)
        self.file_size_bytes = file_size_bytes
        self.max_size_bytes = max_size_bytes


class InvalidFileTypeException(FileException):
    """Raised when an uploaded file has an unsupported extension or MIME type."""

    default_error_code = "INVALID_FILE_TYPE"

    def __init__(self, message: str, file_extension: str, allowed_types: list[str]) -> None:
        super().__init__(message=message)
        self.file_extension = file_extension
        self.allowed_types = allowed_types


class FileReadException(FileException):
    """Raised when a file cannot be parsed or read."""

    default_error_code = "FILE_READ_ERROR"


# =============================================================================
# Pipeline Exceptions
# =============================================================================


class PipelineException(ETLPlatformException):
    """Base exception for pipeline execution errors."""

    default_status_code = HTTPStatus.INTERNAL_SERVER_ERROR.value
    default_error_code = "PIPELINE_ERROR"

    def __init__(
        self,
        message: str,
        run_id: str | None = None,
        stage: str | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)
        self.run_id = run_id
        self.stage = stage


class PipelineNotFoundException(PipelineException):
    """Raised when a pipeline run with the given ID does not exist."""

    default_status_code = HTTPStatus.NOT_FOUND.value
    default_error_code = "PIPELINE_NOT_FOUND"


class PipelineStageException(PipelineException):
    """Raised when a specific pipeline stage fails during execution."""

    default_error_code = "PIPELINE_STAGE_FAILED"


class PipelineAlreadyRunningException(PipelineException):
    """Raised when attempting to start a pipeline that is already running."""

    default_status_code = HTTPStatus.CONFLICT.value
    default_error_code = "PIPELINE_ALREADY_RUNNING"


# =============================================================================
# API Exceptions
# =============================================================================


class APIException(ETLPlatformException):
    """Base exception for API-layer errors."""

    default_status_code = HTTPStatus.BAD_REQUEST.value
    default_error_code = "API_ERROR"


class NotFoundException(APIException):
    """Raised when a requested resource does not exist."""

    default_status_code = HTTPStatus.NOT_FOUND.value
    default_error_code = "NOT_FOUND"


class AuthenticationException(APIException):
    """Raised when authentication fails (invalid or missing API key)."""

    default_status_code = HTTPStatus.UNAUTHORIZED.value
    default_error_code = "AUTHENTICATION_FAILED"


class AuthorizationException(APIException):
    """Raised when an authenticated user lacks permission for an action."""

    default_status_code = HTTPStatus.FORBIDDEN.value
    default_error_code = "AUTHORIZATION_FAILED"


class RateLimitException(APIException):
    """Raised when a client exceeds the configured rate limit."""

    default_status_code = HTTPStatus.TOO_MANY_REQUESTS.value
    default_error_code = "RATE_LIMIT_EXCEEDED"

    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message=message)
        self.retry_after_seconds = retry_after_seconds


class RequestValidationException(APIException):
    """Raised when request body or query parameter validation fails."""

    default_status_code = HTTPStatus.UNPROCESSABLE_ENTITY.value
    default_error_code = "REQUEST_VALIDATION_FAILED"
