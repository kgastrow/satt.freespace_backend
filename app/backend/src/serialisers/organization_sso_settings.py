"""
Pydantic serializers for OrganizationSSOSettings.
"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateOrganizationSSOSettingsRequest(BaseModel):
    """Request model for creating organization SSO settings."""

    google_enabled: bool = Field(False, description="Enable Google SSO")
    google_client_id: Optional[str] = Field(None, max_length=255)
    google_client_secret: Optional[str] = Field(None, max_length=255)

    model_config = ConfigDict(extra="forbid")


class UpdateOrganizationSSOSettingsRequest(BaseModel):
    """Request model for updating organization SSO settings."""

    google_enabled: Optional[bool] = Field(None, description="Enable Google SSO")
    google_client_id: Optional[str] = Field(None, max_length=255)
    google_client_secret: Optional[str] = Field(None, max_length=255)

    model_config = ConfigDict(extra="forbid")


class OrganizationSSOSettingsResponse(BaseModel):
    """Response model for organization SSO settings."""

    id: UUID
    organization_id: UUID
    sso_allowed: bool  # Master switch - controlled by super admin
    google_enabled: bool
    google_client_id: Optional[str]
    created_time: Optional[str]
    updated_time: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class SetSSOAllowedRequest(BaseModel):
    """Request model for super admin to set sso_allowed for an organization."""

    sso_allowed: bool = Field(..., description="Allow SSO for this organization")

    model_config = ConfigDict(extra="forbid")


class EnabledProvidersResponse(BaseModel):
    """Response model for enabled SSO providers."""

    providers: list[str]

    model_config = ConfigDict(extra="forbid")
