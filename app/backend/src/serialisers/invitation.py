"""
Invitation API serialiser models.
Contains all Pydantic models for user invitation endpoints.
"""

from datetime import datetime
import json
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.models.user_invitation import UserInvitation


class CreateInvitationRequest(BaseModel):
    """Request body for creating an invitation."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(..., description="Email address of the invited user")
    role_ids: Optional[list[UUID]] = Field(
        None, description="Optional list of role IDs to assign on registration"
    )
    user_type_ids: Optional[list[UUID]] = Field(
        None, description="Optional list of user type IDs to assign on registration"
    )


class InvitationResponse(BaseModel):
    """Serialised representation of a single invitation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    invited_by_user_id: str
    invited_by_name: Optional[str] = None
    role_ids: Optional[list[str]] = None
    user_type_ids: Optional[list[str]] = None
    expires_at: datetime
    created_time: Optional[datetime] = None

    @classmethod
    def from_orm(cls, obj: UserInvitation) -> "InvitationResponse":
        role_ids: list[str] | None = None
        user_type_ids: list[str] | None = None
        if obj.role_ids:
            try:
                role_ids = json.loads(obj.role_ids)
            except (ValueError, TypeError):
                role_ids = None
        if obj.user_type_ids:
            try:
                user_type_ids = json.loads(obj.user_type_ids)
            except (ValueError, TypeError):
                user_type_ids = None

        invited_by_name: str | None = None
        if obj.invited_by:
            parts = [obj.invited_by.first_name, obj.invited_by.last_name]
            name = " ".join(p for p in parts if p)
            invited_by_name = name or obj.invited_by.email

        return cls(
            id=str(obj.id),
            email=obj.email,
            invited_by_user_id=str(obj.invited_by_user_id),
            invited_by_name=invited_by_name,
            role_ids=role_ids,
            user_type_ids=user_type_ids,
            expires_at=obj.expires_at,
            created_time=obj.created_time,
        )


class ListInvitationsResponse(BaseModel):
    """Response for listing pending invitations."""

    items: list[InvitationResponse]
    total: int


class ValidateInvitationResponse(BaseModel):
    """Public response for validating an invitation token."""

    email: str
    organization_slug: str
    expires_at: datetime


class CreateInvitationResponse(BaseModel):
    """Response after successfully creating an invitation."""

    message: str
    message_code: str
    invitation: InvitationResponse


class RevokeInvitationResponse(BaseModel):
    """Response after revoking an invitation."""

    message: str
    message_code: str
