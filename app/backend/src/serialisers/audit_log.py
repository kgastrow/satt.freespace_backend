"""
Pydantic schemas for audit log API.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditLogResponse(BaseModel):
    """Response schema for a single audit log entry."""

    id: UUID
    created_time: datetime
    organization_id: UUID
    actor_id: Optional[UUID] = None
    actor_email: Optional[str] = Field(
        None, description="Email of the actor who performed the action"
    )
    action: str = Field(..., description="Action type: CREATE, UPDATE, or DELETE")
    resource_type: str = Field(..., description="Type of resource affected")
    resource_id: UUID = Field(..., description="ID of the resource affected")
    resource_name: Optional[str] = Field(
        None, description="Human-readable name/identifier for the resource"
    )
    resource_context: Optional[dict] = Field(
        None, description="Additional context captured at audit time"
    )
    changes: Optional[dict] = Field(
        None, description="Changes made: {field: {old: x, new: y}}"
    )
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    impersonated_by: Optional[UUID] = Field(
        None,
        description="UUID of super admin who was impersonating when action was performed",
    )
    impersonator_email: Optional[str] = Field(
        None, description="Email of the super admin who was impersonating"
    )

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    """Response schema for paginated audit log list."""

    items: list[AuditLogResponse]
    total: int = Field(..., description="Total number of matching audit logs")
    limit: int = Field(..., description="Number of items per page")
    offset: int = Field(..., description="Number of items skipped")

    model_config = ConfigDict(extra="forbid")


class AuditLogFilterParams(BaseModel):
    """Query parameters for filtering audit logs."""

    resource_type: Optional[str] = Field(
        None, description="Filter by resource type (e.g., 'User', 'Role')"
    )
    resource_id: Optional[UUID] = Field(
        None, description="Filter by specific resource ID"
    )
    action: Optional[str] = Field(
        None, description="Filter by action type (CREATE, UPDATE, DELETE)"
    )
    actor_id: Optional[UUID] = Field(
        None, description="Filter by actor (user who performed action)"
    )
    date_from: Optional[datetime] = Field(None, description="Filter from this date")
    date_to: Optional[datetime] = Field(None, description="Filter until this date")
    limit: int = Field(
        default=50, ge=1, le=100, description="Number of items per page (max 100)"
    )
    offset: int = Field(default=0, ge=0, description="Number of items to skip")

    model_config = ConfigDict(extra="forbid")


class ResourceHistoryResponse(BaseModel):
    """Response schema for resource audit history."""

    resource_type: str
    resource_id: UUID
    history: list[AuditLogResponse]
    total: int

    model_config = ConfigDict(extra="forbid")
