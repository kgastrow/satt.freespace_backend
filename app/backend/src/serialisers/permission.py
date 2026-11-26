"""
Pydantic models for Permission and RolePermission operations.
"""

import re
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Regex pattern for permission code validation
PERMISSION_CODE_PATTERN = re.compile(r"^[a-z_]+:[a-z_]+$")


# =============================================================================
# Permission Serializers
# =============================================================================


class CreatePermissionRequest(BaseModel):
    """Request model for creating a permission."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Permission code in format 'resource:action' (e.g., 'users:read')",
    )
    name: str = Field(
        ..., min_length=1, max_length=255, description="Human-readable permission name"
    )
    description: Optional[str] = Field(
        None, max_length=1000, description="Optional description of the permission"
    )
    display_order: int = Field(
        default=0, ge=0, description="Display order for UI grouping"
    )

    @field_validator("code")
    @classmethod
    def validate_code_format(cls, v: str) -> str:
        if not PERMISSION_CODE_PATTERN.match(v):
            raise ValueError(
                "Permission code must be in format 'resource:action' "
                "with lowercase letters and underscores only (e.g., 'users:read', 'user_roles:write')"
            )
        return v


class UpdatePermissionRequest(BaseModel):
    """Request model for updating a permission."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(
        None, min_length=1, max_length=255, description="Human-readable permission name"
    )
    description: Optional[str] = Field(
        None, max_length=1000, description="Optional description of the permission"
    )
    display_order: Optional[int] = Field(
        None, ge=0, description="Display order for UI grouping"
    )


class PermissionResponse(BaseModel):
    """Response model for a permission."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: Optional[str] = None
    resource: str
    action: str
    display_order: int
    created_time: str


class ListPermissionsResponse(BaseModel):
    """Response model for listing permissions."""

    items: list[PermissionResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# RolePermission Serializers
# =============================================================================


class GrantPermissionRequest(BaseModel):
    """Request model for granting a permission to a role."""

    model_config = ConfigDict(extra="forbid")

    permission_id: UUID = Field(..., description="UUID of the permission to grant")


class RevokePermissionRequest(BaseModel):
    """Request model for revoking a permission from a role."""

    model_config = ConfigDict(extra="forbid")

    permission_id: UUID = Field(..., description="UUID of the permission to revoke")


class AssignRolePermissionRequest(BaseModel):
    """Request model for assigning a permission to a global role (admin endpoint)."""

    model_config = ConfigDict(extra="forbid")

    role_id: UUID = Field(..., description="UUID of the global role")
    permission_id: UUID = Field(..., description="UUID of the permission to grant")


class RevokeRolePermissionRequest(BaseModel):
    """Request model for revoking a permission from a global role (admin endpoint)."""

    model_config = ConfigDict(extra="forbid")

    role_id: UUID = Field(..., description="UUID of the global role")
    permission_id: UUID = Field(..., description="UUID of the permission to revoke")


class RolePermissionResponse(BaseModel):
    """Response model for a role permission grant."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role_id: UUID
    permission_id: UUID
    granted_by: Optional[UUID] = None
    granted_time: str
    created_time: str


class RoleWithPermissionsResponse(BaseModel):
    """Response model for a role with its permission IDs."""

    id: UUID
    name: str
    description: Optional[str] = None
    permission_ids: list[UUID]


class PermissionMatrixResponse(BaseModel):
    """Response model for the permission matrix."""

    permissions: list[PermissionResponse]
    roles: list[RoleWithPermissionsResponse]


# =============================================================================
# User Permissions Serializers
# =============================================================================


class UserPermissionsResponse(BaseModel):
    """Response model for user permissions."""

    user_id: UUID
    organization_id: UUID
    permissions: list[str]


# =============================================================================
# UserTypePermission Serializers
# =============================================================================


class AssignUserTypePermissionRequest(BaseModel):
    """Request model for assigning a permission to a user type (admin endpoint)."""

    model_config = ConfigDict(extra="forbid")

    user_type_id: UUID = Field(..., description="UUID of the user type")
    permission_id: UUID = Field(..., description="UUID of the permission to grant")


class RevokeUserTypePermissionRequest(BaseModel):
    """Request model for revoking a permission from a user type (admin endpoint)."""

    model_config = ConfigDict(extra="forbid")

    user_type_id: UUID = Field(..., description="UUID of the user type")
    permission_id: UUID = Field(..., description="UUID of the permission to revoke")


class UserTypePermissionResponse(BaseModel):
    """Response model for a user type permission grant."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_type_id: UUID
    permission_id: UUID
    granted_by: Optional[UUID] = None
    granted_time: str
    created_time: str


class UserTypeWithPermissionsResponse(BaseModel):
    """Response model for a user type with its permission IDs."""

    id: UUID
    name: str
    code: str
    description: Optional[str] = None
    permission_ids: list[UUID]


class ExtendedPermissionMatrixResponse(BaseModel):
    """Response model for the extended permission matrix including user types."""

    permissions: list[PermissionResponse]
    roles: list[RoleWithPermissionsResponse]
    user_types: list[UserTypeWithPermissionsResponse]
