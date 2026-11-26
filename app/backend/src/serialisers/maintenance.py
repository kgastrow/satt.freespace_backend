"""
Maintenance mode serializer models.
Contains all Pydantic models for maintenance mode API endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MaintenanceStatusResponse(BaseModel):
    """Public response model for maintenance mode status (unauthenticated endpoint)"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        ..., description="Whether maintenance mode is currently active"
    )
    message: Optional[str] = Field(
        None, description="Custom message to display during maintenance"
    )
    scheduled_start: Optional[datetime] = Field(
        None, description="When maintenance is scheduled to start (if scheduled)"
    )
    scheduled_end: Optional[datetime] = Field(
        None,
        description="When maintenance is scheduled to end (if scheduled or active)",
    )
    allow_super_admin: bool = Field(
        default=False,
        description="Whether super admins are allowed to access during maintenance",
    )


class MaintenanceConfigResponse(BaseModel):
    """Admin response model for full maintenance configuration with history"""

    model_config = ConfigDict(from_attributes=True)

    enabled: bool
    message: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    allow_super_admin: bool
    updated_time: Optional[str] = None
    updated_by_user_id: Optional[str] = None


class UpdateMaintenanceRequest(BaseModel):
    """Request model for updating maintenance configuration (super admin only)"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(..., description="Enable or disable maintenance mode")
    message: Optional[str] = Field(
        None,
        max_length=500,
        description="Custom message to display during maintenance",
    )
    scheduled_start: Optional[datetime] = Field(
        None, description="When to automatically start maintenance (future timestamp)"
    )
    scheduled_end: Optional[datetime] = Field(
        None, description="When to automatically end maintenance (future timestamp)"
    )
    allow_super_admin: bool = Field(
        default=True,
        description="Whether super admins can access during maintenance",
    )


class UpdateMaintenanceResponse(BaseModel):
    """Response model for updating maintenance configuration"""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    config: MaintenanceConfigResponse


# =============================================================================
# Maintenance History Serializers
# =============================================================================


class UserSummary(BaseModel):
    """Minimal user info for history records"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: str


class MaintenanceHistoryResponse(BaseModel):
    """Response model for a single maintenance history record"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str = Field(
        ..., description="Status: scheduled, active, completed, cancelled"
    )
    scheduled_start: Optional[datetime] = Field(
        None, description="When maintenance was scheduled to start"
    )
    scheduled_end: Optional[datetime] = Field(
        None, description="When maintenance was scheduled to end"
    )
    actual_start: Optional[datetime] = Field(
        None, description="When maintenance actually started"
    )
    actual_end: Optional[datetime] = Field(
        None, description="When maintenance actually ended"
    )
    message: Optional[str] = Field(None, description="Maintenance message")
    started_by: Optional[UserSummary] = Field(
        None, description="User who started maintenance"
    )
    ended_by: Optional[UserSummary] = Field(
        None, description="User who ended maintenance"
    )
    created_time: datetime


class MaintenanceHistoryListResponse(BaseModel):
    """Response model for paginated maintenance history list"""

    items: list[MaintenanceHistoryResponse]
    total: int
    limit: int
    offset: int
