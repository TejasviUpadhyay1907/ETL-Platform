"""
Base API response schemas used across all endpoints.

Every API response follows the standard envelope format defined here.
This ensures consistent structure for API consumers and error handling.

Response Envelope:
{
    "success": true,
    "data": { ... },
    "error": null,
    "meta": {
        "request_id": "...",
        "timestamp": "...",
        "version": "1.0"
    }
}
"""

from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

DataT = TypeVar("DataT")


class ErrorDetail(BaseModel):
    """A single error detail item in a validation or processing error response."""

    field: str | None = Field(default=None, description="Field that caused the error")
    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable error description")


class APIError(BaseModel):
    """Structured error information returned in failed responses."""

    code: str = Field(description="Top-level machine-readable error code")
    message: str = Field(description="Human-readable error message")
    details: list[ErrorDetail] = Field(
        default_factory=list,
        description="Optional list of field-level errors",
    )


class ResponseMeta(BaseModel):
    """Metadata included in every API response."""

    request_id: str | None = Field(
        default=None, description="Unique ID for this request (for tracing)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response generation timestamp (UTC)",
    )
    version: str = Field(default="1.0", description="API version")


class APIResponse(BaseModel, Generic[DataT]):
    """
    Standard API response envelope.

    All API endpoints return this structure. Data type is parameterized
    so callers get full type safety.

    Example:
        return APIResponse[OrderData].success(data=order)
        return APIResponse[None].error(error=err)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool = Field(description="True if the request succeeded")
    data: DataT | None = Field(default=None, description="Response payload")
    error: APIError | None = Field(default=None, description="Error details if failed")
    meta: ResponseMeta = Field(
        default_factory=ResponseMeta,
        description="Response metadata",
    )

    @classmethod
    def ok(
        cls,
        data: DataT | None = None,
        request_id: str | None = None,
    ) -> "APIResponse[DataT]":
        """Create a successful response."""
        return cls(
            success=True,
            data=data,
            error=None,
            meta=ResponseMeta(request_id=request_id),
        )

    @classmethod
    def fail(
        cls,
        error_code: str,
        message: str,
        details: list[ErrorDetail] | None = None,
        request_id: str | None = None,
    ) -> "APIResponse[None]":
        """Create an error response."""
        return cls(
            success=False,
            data=None,
            error=APIError(
                code=error_code,
                message=message,
                details=details or [],
            ),
            meta=ResponseMeta(request_id=request_id),
        )


class PaginationMeta(BaseModel):
    """Pagination metadata for list responses."""

    page: int = Field(ge=1, description="Current page number")
    page_size: int = Field(ge=1, le=1000, description="Items per page")
    total_items: int = Field(ge=0, description="Total items available")
    total_pages: int = Field(ge=0, description="Total pages available")
    has_next: bool = Field(description="Whether there is a next page")
    has_previous: bool = Field(description="Whether there is a previous page")

    @classmethod
    def from_count(
        cls,
        total_items: int,
        page: int,
        page_size: int,
    ) -> "PaginationMeta":
        """Compute pagination metadata from total count."""
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        return cls(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )


class PaginatedResponse(BaseModel, Generic[DataT]):
    """Paginated list response envelope."""

    success: bool = True
    data: list[DataT] = Field(default_factory=list)
    pagination: PaginationMeta
    error: APIError | None = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)

    @classmethod
    def ok(
        cls,
        data: list[DataT],
        total_items: int,
        page: int,
        page_size: int,
        request_id: str | None = None,
    ) -> "PaginatedResponse[DataT]":
        """Create a successful paginated response."""
        return cls(
            success=True,
            data=data,
            pagination=PaginationMeta.from_count(total_items, page, page_size),
            meta=ResponseMeta(request_id=request_id),
        )


class HealthStatus(BaseModel):
    """Health check response payload."""

    status: str = Field(description="Overall status: healthy, degraded, unhealthy")
    app_name: str
    version: str
    environment: str
    database: str = Field(description="Database connectivity status")
    uptime_seconds: float | None = Field(default=None, description="Application uptime")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PingResponse(BaseModel):
    """Ping response (minimal health check)."""

    ping: str = "pong"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class VersionResponse(BaseModel):
    """Version information response."""

    app_name: str
    version: str
    environment: str
    build_date: str | None = None


# Common query parameter models for reuse across endpoints
class PaginationParams(BaseModel):
    """Standard pagination query parameters."""

    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")

    @property
    def offset(self) -> int:
        """Compute database offset from page and page_size."""
        return (self.page - 1) * self.page_size
