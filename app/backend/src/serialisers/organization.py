from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CreateOrganizationRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=3, max_length=255, pattern="^[a-z0-9-]+$")
    display_name: Optional[str] = Field(None, max_length=255)
    physical_address_line1: Optional[str] = Field(None, max_length=255)
    physical_address_line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=255)
    state_province: Optional[str] = Field(None, max_length=255)
    postal_code: Optional[str] = Field(None, max_length=255)
    country: Optional[str] = Field(None, max_length=255)
    contact_email: Optional[EmailStr] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=255)
    model_config = ConfigDict(extra="forbid")


class UpdateOrganizationRequest(BaseModel):
    id: UUID
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(
        None, min_length=3, max_length=255, pattern="^[a-z0-9-]+$"
    )
    is_active: Optional[bool] = None
    model_config = ConfigDict(extra="forbid")


class UpdateOrganizationAPIRequest(BaseModel):
    """Request model for API update endpoint (id comes from path parameter)"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(
        None, min_length=3, max_length=255, pattern="^[a-z0-9-]+$"
    )
    is_active: Optional[bool] = None
    model_config = ConfigDict(extra="forbid")


class GetOrganizationRequest(BaseModel):
    id: Optional[UUID] = None
    slug: Optional[str] = None
    model_config = ConfigDict(extra="forbid")


class DeleteOrganizationRequest(BaseModel):
    id: UUID
    model_config = ConfigDict(extra="forbid")


class GetOrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    is_active: bool
    created_time: str
    updated_time: str
    deletion_requested: bool = False
    deletion_requested_time: Optional[str] = None


class ListOrganizationsResponse(BaseModel):
    items: list[GetOrganizationResponse]
    total: int
    limit: int
    offset: int


class RequestDeletionRequest(BaseModel):
    """Request body for requesting organization deletion (can include reason in future)"""

    model_config = ConfigDict(extra="forbid")


class RequestDeletionResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    organization_id: str
    deletion_requested_time: str


class CancelDeletionResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    organization_id: str


# API response models


class CreateOrganizationResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    organization: GetOrganizationResponse


class UpdateOrganizationResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    organization: GetOrganizationResponse


class DeleteOrganizationResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    organization_id: str


class MemberCountResponse(BaseModel):
    organization_id: str
    member_count: int


class RemoveMemberResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    user_id: str


class HardDeleteResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    organization_id: str
    organization_name: str
    s3_files_deleted: int
    records_deleted: dict


class HardDeleteStatusResponse(BaseModel):
    organization_id: str
    can_hard_delete: bool
    days_remaining: int
    retention_days: int
    deleted_time: Optional[str] = None


class GetOrganizationDetailsResponse(BaseModel):
    id: str
    name: str
    slug: str
    display_name: Optional[str] = None
    physical_address_line1: Optional[str] = None
    physical_address_line2: Optional[str] = None
    city: Optional[str] = None
    state_province: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    logo_file_id: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class UpdateOrganizationDetailsRequest(BaseModel):
    display_name: Optional[str] = Field(None, max_length=255)
    physical_address_line1: Optional[str] = Field(None, max_length=255)
    physical_address_line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=255)
    state_province: Optional[str] = Field(None, max_length=255)
    postal_code: Optional[str] = Field(None, max_length=255)
    country: Optional[str] = Field(None, max_length=255)
    contact_email: Optional[EmailStr] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=255)
    logo_file_id: Optional[UUID] = None
    model_config = ConfigDict(extra="forbid")
