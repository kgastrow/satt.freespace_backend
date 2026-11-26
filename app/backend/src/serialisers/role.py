from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateRoleRequest(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    is_default_on_registration: bool = Field(False)
    model_config = ConfigDict(extra="forbid")


class UpdateRoleRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    is_default_on_registration: Optional[bool] = None
    model_config = ConfigDict(extra="forbid")


class GetRoleRequest(BaseModel):
    id: UUID
    model_config = ConfigDict(extra="forbid")


class GetRoleResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    is_default_on_registration: bool
    created_time: str
    updated_time: str


class ListRolesResponse(BaseModel):
    items: list[GetRoleResponse]
    total: int
    limit: int
    offset: int


class DeleteRoleRequest(BaseModel):
    id: UUID
    model_config = ConfigDict(extra="forbid")


# API response models


class CreateRoleResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    role: GetRoleResponse


class UpdateRoleResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    role: GetRoleResponse


class DeleteRoleResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    role_id: str
