"""
Serializers for SystemConfig API.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SystemConfigResponse(BaseModel):
    """Response schema for a single system config entry."""

    id: UUID
    key: str
    value: Any
    description: Optional[str] = None
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None
    updated_by_user_id: Optional[UUID] = None
    updated_by_email: Optional[str] = None
    is_sensitive: bool = False  # True if value is encrypted/masked

    model_config = ConfigDict(from_attributes=True)


class SystemConfigListResponse(BaseModel):
    """Response schema for list of system configs."""

    items: list[SystemConfigResponse]
    total: int
    limit: int
    offset: int


class CreateSystemConfigRequest(BaseModel):
    """Request schema for creating a system config."""

    key: str = Field(..., min_length=1, max_length=100)
    value: Any
    description: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class UpdateSystemConfigRequest(BaseModel):
    """Request schema for updating a system config."""

    value: Any
    description: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class DeleteSystemConfigResponse(BaseModel):
    """Response schema for deleting a system config."""

    message: str
    message_code: str
