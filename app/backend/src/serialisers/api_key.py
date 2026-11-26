"""
Pydantic serializers for API key management endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from src.serialisers.permission import PermissionResponse


class CreateApiKeyRequest(BaseModel):
    """Request to create a new API key"""

    name: str = Field(..., min_length=1, max_length=255)
    expires_at: Optional[datetime] = Field(None)
    permissions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class CreateApiKeyResponse(BaseModel):
    """Response when creating a new API key - includes the full key ONLY ONCE"""

    id: str
    name: str
    key: str
    prefix: str
    scope: str
    expires_at: Optional[str] = None
    permissions: list[str]
    created_time: str
    message: str
    message_code: str = Field(..., description="Translation code for i18n")

    model_config = ConfigDict(from_attributes=True)


class ApiKeyDetailResponse(BaseModel):
    """Response for API key details (without the actual key)"""

    id: str
    name: str
    prefix: str
    scope: str
    expires_at: Optional[str] = None
    last_used_at: Optional[str] = None
    created_by: str
    created_time: str
    updated_time: Optional[str] = None
    permissions: list[str]

    model_config = ConfigDict(from_attributes=True)


class ApiKeyListResponse(BaseModel):
    """Response for listing API keys"""

    items: list[ApiKeyDetailResponse]
    total: int
    limit: int
    offset: int


class UpdateApiKeyRequest(BaseModel):
    """Request to update an API key (name only - expiration cannot be modified)"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)

    model_config = ConfigDict(extra="forbid")


class UpdateApiKeyResponse(BaseModel):
    """Response after updating an API key"""

    id: str
    name: str
    prefix: str
    updated_time: Optional[str] = None
    message: str
    message_code: str = Field(..., description="Translation code for i18n")

    model_config = ConfigDict(from_attributes=True)


class DeleteApiKeyResponse(BaseModel):
    """Response after deleting (revoking) an API key"""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")


class AssignPermissionsRequest(BaseModel):
    """Request to assign permissions to an API key"""

    permissions: list[str] = Field(..., min_length=1)

    model_config = ConfigDict(extra="forbid")


class AssignPermissionsResponse(BaseModel):
    """Response after assigning permissions"""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    permissions: list[str]


class RemovePermissionsRequest(BaseModel):
    """Request to remove permissions from an API key"""

    permissions: list[str] = Field(..., min_length=1)

    model_config = ConfigDict(extra="forbid")


class RemovePermissionsResponse(BaseModel):
    """Response after removing permissions"""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    removed_count: int
    permissions: list[str]


class AssignablePermissionsResponse(BaseModel):
    """Response containing permissions the user can assign to API keys"""

    permissions: list["PermissionResponse"] = Field(
        ..., description="List of permissions the user can assign"
    )
