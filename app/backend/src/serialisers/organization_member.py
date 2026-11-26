from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OrganizationMemberResponse(BaseModel):
    """Response model for a single organization member"""

    id: str
    email: str
    email_verified: bool
    is_admin: bool
    created_time: str
    model_config = ConfigDict(extra="forbid")


class ListOrganizationMembersResponse(BaseModel):
    """Response model for listing organization members"""

    items: list[OrganizationMemberResponse]
    total: int
    limit: int
    offset: int
    model_config = ConfigDict(extra="forbid")


class RemoveOrganizationMemberRequest(BaseModel):
    """Request model for removing a member from organization"""

    user_id: UUID
    model_config = ConfigDict(extra="forbid")
