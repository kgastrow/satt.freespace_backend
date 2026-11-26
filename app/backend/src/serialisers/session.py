"""
Session serializers for session management API.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SessionDeviceInfo(BaseModel):
    """Device information parsed from user-agent."""

    device_type: str = Field(
        ..., description="Device type: mobile, tablet, desktop, unknown"
    )
    browser: str = Field(..., description="Browser name and version")
    os: str = Field(..., description="Operating system name and version")


class SessionLocation(BaseModel):
    """Geographic location from IP address."""

    city: Optional[str] = Field(None, description="City name")
    country: Optional[str] = Field(None, description="Country name")
    country_code: Optional[str] = Field(
        None, description="ISO 3166-1 alpha-2 country code"
    )


class SessionResponse(BaseModel):
    """Response model for a single session."""

    id: str = Field(..., description="Session ID")
    device: SessionDeviceInfo = Field(..., description="Device information")
    location: SessionLocation = Field(..., description="Geographic location")
    ip_address: Optional[str] = Field(None, description="Partially masked IP address")
    auth_provider: Optional[str] = Field(
        None, description="Authentication provider (email, google, etc.)"
    )
    created_time: datetime = Field(..., description="Session creation timestamp")
    updated_time: datetime = Field(..., description="Last activity timestamp")
    is_current: bool = Field(..., description="Whether this is the current session")

    model_config = ConfigDict(from_attributes=True)


class SessionListResponse(BaseModel):
    """Response model for listing sessions."""

    items: list[SessionResponse] = Field(..., description="List of active sessions")
    total: int = Field(..., description="Total number of active sessions")
    limit: int = Field(..., description="Maximum number of sessions per page")
    offset: int = Field(..., description="Number of sessions skipped")


class RevokeOtherSessionsRequest(BaseModel):
    """Request model for revoking all other sessions."""

    current_refresh_token: str = Field(
        ...,
        description="Current session's refresh token to exclude from revocation",
    )

    model_config = ConfigDict(extra="forbid")


class RevokeSessionResponse(BaseModel):
    """Response model for session revocation."""

    message: str = Field(..., description="Success message")
    message_code: str = Field(..., description="Translation code for i18n")


class RevokeOtherSessionsResponse(BaseModel):
    """Response model for revoking other sessions."""

    message: str = Field(..., description="Success message")
    message_code: str = Field(..., description="Translation code for i18n")
    revoked_count: int = Field(..., description="Number of sessions revoked")
