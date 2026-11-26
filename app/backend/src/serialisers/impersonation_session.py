from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ImpersonationSessionCreate(BaseModel):
    """Request to create a new impersonation session"""

    target_user_id: UUID = Field(..., description="ID of the user to impersonate")
    ip_address: Optional[str] = Field(None, max_length=255)
    user_agent: Optional[str] = Field(None, max_length=500)

    model_config = ConfigDict(extra="forbid")


class ImpersonationSessionResponse(BaseModel):
    """Response containing impersonation session details"""

    id: UUID
    created_time: datetime
    impersonator_id: UUID
    target_user_id: UUID
    target_organization_id: UUID
    ended_time: Optional[datetime]
    ip_address: Optional[str]
    user_agent: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class ImpersonationSessionListResponse(BaseModel):
    """Paginated list of impersonation sessions"""

    items: list[ImpersonationSessionResponse]
    total: int
    limit: int
    offset: int


class StartImpersonationResponse(BaseModel):
    """Response when starting an impersonation session"""

    impersonation_token: str = Field(
        ..., description="JWT token for impersonating the target user"
    )
    session: ImpersonationSessionResponse
    message: str
    message_code: str = Field(..., description="Translation code for i18n")


class EndImpersonationResponse(BaseModel):
    """Response when ending an impersonation session"""

    access_token: str = Field(..., description="JWT token for the original admin user")
    session: ImpersonationSessionResponse
    message: str
    message_code: str = Field(..., description="Translation code for i18n")


class ImpersonatorInfo(BaseModel):
    """Basic info about the impersonator for history display"""

    id: UUID
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class MyImpersonationHistoryItem(BaseModel):
    """Single item in user's impersonation history with impersonator details"""

    id: UUID
    created_time: datetime
    ended_time: datetime
    impersonator: ImpersonatorInfo

    model_config = ConfigDict(from_attributes=True)

    @property
    def duration_seconds(self) -> float:
        """Calculate session duration in seconds"""
        return (self.ended_time - self.created_time).total_seconds()


class MyImpersonationHistoryResponse(BaseModel):
    """Paginated list of impersonation sessions where user was the target"""

    sessions: list[MyImpersonationHistoryItem]
    total: int
    limit: int
    offset: int


class ImpersonationSessionStatusResponse(BaseModel):
    """Response for checking current impersonation session status"""

    active: bool
    session: Optional[ImpersonationSessionResponse] = None

    model_config = ConfigDict(from_attributes=True)
