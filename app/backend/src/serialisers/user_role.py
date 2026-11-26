from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AssignRoleRequest(BaseModel):
    user_id: UUID
    role_id: UUID
    model_config = ConfigDict(extra="forbid")


class RevokeRoleRequest(BaseModel):
    user_id: UUID
    role_id: UUID
    model_config = ConfigDict(extra="forbid")


class GetUserRoleRequest(BaseModel):
    id: UUID
    model_config = ConfigDict(extra="forbid")


class GetUserRolesRequest(BaseModel):
    user_id: UUID
    model_config = ConfigDict(extra="forbid")


class UserRoleResponse(BaseModel):
    id: UUID
    user_id: UUID
    role_id: UUID
    role_name: str
    assigned_by: Optional[UUID]
    assigned_by_email: Optional[str]
    created_time: str
    deleted_time: Optional[str] = None  # Set when role is revoked


class ListUserRolesResponse(BaseModel):
    items: list[UserRoleResponse]
    total: int
    limit: int
    offset: int


# API response models


class AssignRoleResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    user_role: UserRoleResponse


class RevokeRoleResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    user_role: UserRoleResponse
