"""
Pydantic schemas for request log API.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RequestLogResponse(BaseModel):
    """Response schema for a single request log entry."""

    id: UUID
    created_time: datetime
    organization_id: Optional[UUID] = Field(
        None, description="Organization ID (null for unauthenticated requests)"
    )
    user_id: Optional[UUID] = Field(
        None, description="User ID (null for unauthenticated requests)"
    )
    method: str = Field(..., description="HTTP method (GET, POST, etc.)")
    path: str = Field(..., description="Request path")
    status_code: int = Field(..., description="HTTP status code")
    duration_ms: int = Field(..., description="Request duration in milliseconds")
    request_body: Optional[dict[str, Any]] = Field(
        None, description="Sanitized request body"
    )
    response_body: Optional[dict[str, Any]] = Field(
        None, description="Sanitized response body"
    )
    ip_address: Optional[str] = Field(None, description="IP address of the request")
    user_agent: Optional[str] = Field(None, description="User agent string")
    error_traceback: Optional[str] = Field(
        None, description="Full stack trace for 500 errors"
    )

    model_config = ConfigDict(from_attributes=True)


class ListRequestLogsResponse(BaseModel):
    """Response schema for cursor-paginated request log list."""

    items: list[RequestLogResponse]
    next_cursor: Optional[str] = Field(
        None, description="Cursor for next page (null if no more results)"
    )
    has_more: bool = Field(..., description="Whether there are more results")
    limit: int = Field(..., description="Number of items per page")

    model_config = ConfigDict(extra="forbid")


class RequestLogFilterParams(BaseModel):
    """Query parameters for filtering request logs."""

    method: Optional[str] = Field(
        None, description="Filter by HTTP method (GET, POST, etc.)"
    )
    path: Optional[str] = Field(
        None, description="Filter by path pattern (uses SQL LIKE)"
    )
    status_code_min: Optional[int] = Field(
        None, description="Filter by minimum status code"
    )
    status_code_max: Optional[int] = Field(
        None, description="Filter by maximum status code"
    )
    date_from: Optional[datetime] = Field(None, description="Filter from this date")
    date_to: Optional[datetime] = Field(None, description="Filter until this date")
    organization_id: Optional[UUID] = Field(
        None, description="Filter by organization ID"
    )
    user_id: Optional[UUID] = Field(None, description="Filter by user ID")
    limit: int = Field(
        default=50, ge=1, le=100, description="Number of items per page (max 100)"
    )
    cursor: Optional[str] = Field(
        None, description="Cursor for pagination (from previous response)"
    )

    model_config = ConfigDict(extra="forbid")


class RequestLoggingConfigResponse(BaseModel):
    """Response schema for request logging configuration."""

    enabled: bool = Field(..., description="Whether request logging is enabled")
    db_enabled: bool = Field(..., description="Whether logs are stored in the database")
    max_body_size: int = Field(
        ..., description="Maximum request/response body size to capture (bytes)"
    )
    retention_days: int = Field(
        ..., description="Number of days to retain request logs"
    )

    model_config = ConfigDict(extra="forbid")


class UpdateRequestLoggingConfigRequest(BaseModel):
    """Request schema for updating request logging configuration."""

    enabled: bool = Field(..., description="Enable or disable request logging")
    db_enabled: bool = Field(..., description="Enable or disable database storage")
    max_body_size: int = Field(
        ...,
        ge=1024,
        le=102400,
        description="Maximum body size in bytes (1KB - 100KB)",
    )
    retention_days: int = Field(
        ...,
        ge=1,
        le=365,
        description="Retention period in days (1-365)",
    )

    model_config = ConfigDict(extra="forbid")
