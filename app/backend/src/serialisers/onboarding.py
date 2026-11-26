"""
Pydantic serializers for onboarding models.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# UserType Serializers
class CreateUserTypeRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(None)
    is_active: bool = Field(default=True)
    requires_onboarding: bool = Field(default=False)
    requires_manual_review: bool = Field(default=False)
    is_default: bool = Field(default=False)
    display_order: int = Field(default=0)
    model_config = ConfigDict(extra="forbid")


class UpdateUserTypeRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None)
    is_active: Optional[bool] = Field(None)
    requires_onboarding: Optional[bool] = Field(None)
    requires_manual_review: Optional[bool] = Field(None)
    is_default: Optional[bool] = Field(None)
    display_order: Optional[int] = Field(None)
    model_config = ConfigDict(extra="forbid")


class UserTypeResponse(BaseModel):
    id: UUID
    name: str
    code: str
    description: Optional[str]
    is_active: bool
    requires_onboarding: bool
    requires_manual_review: bool
    is_default: bool
    display_order: int
    created_time: datetime
    updated_time: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)


class UserTypeListResponse(BaseModel):
    items: list[UserTypeResponse]
    total: int
    limit: int
    offset: int


# OnboardingStep Serializers
class CreateOnboardingStepRequest(BaseModel):
    user_type_id: UUID
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(None)
    step_order: int
    required_fields: Optional[dict[str, Any]] = Field(None)
    validation_rules: Optional[dict[str, Any]] = Field(None)
    requires_verification: bool = Field(default=False)
    is_active: bool = Field(default=True)
    model_config = ConfigDict(extra="forbid")


class UpdateOnboardingStepRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None)
    step_order: Optional[int] = Field(None)
    required_fields: Optional[dict[str, Any]] = Field(None)
    validation_rules: Optional[dict[str, Any]] = Field(None)
    requires_verification: Optional[bool] = Field(None)
    is_active: Optional[bool] = Field(None)
    model_config = ConfigDict(extra="forbid")


class ReorderStepsRequest(BaseModel):
    steps: list[dict[str, Any]] = Field(
        ..., description="List of {id: UUID, step_order: int}"
    )
    model_config = ConfigDict(extra="forbid")


class OnboardingStepResponse(BaseModel):
    id: UUID
    user_type_id: UUID
    name: str
    code: str
    description: Optional[str]
    step_order: int
    required_fields: Optional[dict[str, Any]]
    validation_rules: Optional[dict[str, Any]]
    requires_verification: bool
    is_active: bool
    created_time: datetime
    updated_time: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)


class OnboardingStepListResponse(BaseModel):
    items: list[OnboardingStepResponse]
    total: int
    limit: int
    offset: int


# UserUserType Serializers
class CreateUserUserTypeRequest(BaseModel):
    user_id: UUID
    user_type_id: UUID
    model_config = ConfigDict(extra="forbid")


class UpdateOnboardingStatusRequest(BaseModel):
    status: str = Field(
        ...,
        pattern="^(pending|in_progress|pending_review|change_requested|approved|rejected)$",
        description="One of: pending, in_progress, pending_review, change_requested, approved, rejected",
    )
    model_config = ConfigDict(extra="forbid")


class UserUserTypeResponse(BaseModel):
    id: UUID
    user_id: UUID
    user_type_id: UUID
    organization_id: UUID
    onboarding_status: str
    onboarded_at: Optional[datetime]
    created_time: datetime
    updated_time: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)


class UserUserTypeListResponse(BaseModel):
    user_user_types: list[UserUserTypeResponse]


# UserOnboardingProgress Serializers
class CreateProgressRequest(BaseModel):
    user_id: UUID
    user_user_type_id: UUID
    onboarding_step_id: UUID
    submitted_data: Optional[dict[str, Any]] = Field(None)
    model_config = ConfigDict(extra="forbid")


class UpdateProgressRequest(BaseModel):
    submitted_data: Optional[dict[str, Any]] = Field(None)
    completed_time: Optional[datetime] = Field(None)
    model_config = ConfigDict(extra="forbid")


class ProgressResponse(BaseModel):
    id: UUID
    user_id: UUID
    user_user_type_id: UUID
    onboarding_step_id: UUID
    organization_id: UUID
    submitted_data: Optional[dict[str, Any]]
    completed_time: Optional[datetime]
    created_time: datetime
    updated_time: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)


class ProgressListResponse(BaseModel):
    progress: list[ProgressResponse]


# PhoneVerification Serializers
class CreatePhoneVerificationRequest(BaseModel):
    user_id: UUID
    phone: str = Field(..., min_length=10, max_length=20)
    otp_hash: str = Field(..., max_length=255)
    expires_at: datetime
    model_config = ConfigDict(extra="forbid")


class VerifyPhoneRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=20)
    otp: str = Field(..., min_length=6, max_length=6)
    model_config = ConfigDict(extra="forbid")


class PhoneVerificationResponse(BaseModel):
    id: UUID
    user_id: UUID
    organization_id: UUID
    phone: str
    expires_at: datetime
    verified: bool
    attempts_count: int
    created_time: datetime
    model_config = ConfigDict(from_attributes=True)


# OnboardingReviewComment Serializers
class RequestChangeRequest(BaseModel):
    """Request body for admin requesting changes from user."""

    comment: str = Field(..., min_length=1, max_length=2000)
    model_config = ConfigDict(extra="forbid")


class RespondToChangeRequest(BaseModel):
    """Request body for user responding to change request."""

    comment: str = Field(..., min_length=1, max_length=2000)
    model_config = ConfigDict(extra="forbid")


class ReviewCommentResponse(BaseModel):
    """Response model for a single review comment."""

    id: UUID
    author_id: UUID
    author_name: str
    author_type: str  # "admin" or "user"
    comment: str
    created_time: datetime
    model_config = ConfigDict(extra="forbid")


class ReviewCommentsResponse(BaseModel):
    """Response model for list of review comments."""

    comments: list[ReviewCommentResponse]
    model_config = ConfigDict(extra="forbid")
