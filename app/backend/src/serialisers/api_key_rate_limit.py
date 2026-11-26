"""
Serializers for API Key Rate Limit management endpoints.
"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateRateLimitRequest(BaseModel):
    """Request to create a new rate limit configuration."""

    permission_code: str = Field(..., min_length=1, max_length=100)
    requests_per_minute: int = Field(
        ..., ge=1, description="Maximum requests per minute"
    )
    burst_limit: int = Field(..., ge=1, description="Maximum burst requests allowed")
    model_config = ConfigDict(extra="forbid")


class UpdateRateLimitRequest(BaseModel):
    """Request to update an existing rate limit configuration."""

    requests_per_minute: Optional[int] = Field(
        None, ge=1, description="Maximum requests per minute"
    )
    burst_limit: Optional[int] = Field(
        None, ge=1, description="Maximum burst requests allowed"
    )
    model_config = ConfigDict(extra="forbid")


class RateLimitResponse(BaseModel):
    """Response model for a rate limit."""

    id: UUID
    permission_code: str
    requests_per_minute: int
    burst_limit: int
    created_time: str
    updated_time: str


class RateLimitListResponse(BaseModel):
    """Response model for listing rate limits."""

    items: list[RateLimitResponse]
    total: int
    limit: int
    offset: int


class CreateRateLimitResponse(BaseModel):
    """Response for rate limit creation."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    rate_limit: RateLimitResponse


class UpdateRateLimitResponse(BaseModel):
    """Response for rate limit update."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    rate_limit: RateLimitResponse


class DeleteRateLimitResponse(BaseModel):
    """Response for rate limit deletion."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    rate_limit_id: str
