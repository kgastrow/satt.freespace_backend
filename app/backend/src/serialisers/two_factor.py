from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GetOrganizationTwoFactorSettingsResponse(BaseModel):
    """Response for getting organization 2FA settings."""

    id: UUID
    organization_id: UUID
    two_factor_allowed: bool
    two_factor_policy: Literal["disabled", "optional", "mandatory"]
    grace_period_days: int
    enforcement_start_time: Optional[datetime] = None
    two_factor_app_name: Optional[str] = None
    created_time: datetime
    updated_time: datetime

    model_config = ConfigDict(from_attributes=True)


class UpdateOrganizationTwoFactorSettingsRequest(BaseModel):
    """Request to update organization 2FA settings (org admin)."""

    two_factor_policy: Optional[Literal["disabled", "optional", "mandatory"]] = Field(
        None
    )
    grace_period_days: Optional[int] = Field(None, ge=1, le=30)
    two_factor_app_name: Optional[str] = Field(None, max_length=100)

    model_config = ConfigDict(extra="forbid")


class UpdateOrganizationTwoFactorAllowedRequest(BaseModel):
    """Request to allow/disallow 2FA for an organization (super admin)."""

    two_factor_allowed: bool

    model_config = ConfigDict(extra="forbid")


class TwoFactorSetupResponse(BaseModel):
    """Response for initiating 2FA setup."""

    secret: str
    provisioning_uri: str
    qr_code_data: str


class VerifyTwoFactorSetupRequest(BaseModel):
    """Request to verify 2FA setup."""

    code: str = Field(..., min_length=6, max_length=6)
    secret: str = Field(
        ..., min_length=16, description="Base32 TOTP secret from setup step"
    )

    model_config = ConfigDict(extra="forbid")


class VerifyTwoFactorSetupResponse(BaseModel):
    """Response after successful 2FA verification."""

    message: str
    message_code: str
    backup_codes: list[str]


class UserTwoFactorStatusResponse(BaseModel):
    """Response for user's 2FA status."""

    is_enabled: bool
    verified_at: Optional[datetime] = None


class BackupCodesResponse(BaseModel):
    """Response for backup codes (only returned at setup time)."""

    backup_codes: list[str]


class BackupCodesInfoResponse(BaseModel):
    """Response for backup codes status (remaining count)."""

    total_codes: int
    remaining_codes: int
    used_codes: int


class DeleteTwoFactorRequest(BaseModel):
    """Request to delete 2FA, requires password re-authentication."""

    password: str = Field(
        ..., min_length=1, description="User's current password for re-authentication"
    )

    model_config = ConfigDict(extra="forbid")


class DeleteTwoFactorResponse(BaseModel):
    """Response after deleting 2FA."""

    message: str
    message_code: str


class TwoFactorPolicyResponse(BaseModel):
    """Response for org 2FA policy (available to all authenticated users)."""

    two_factor_available: bool  # Combined check: allowed AND policy != disabled
    two_factor_policy: Literal["disabled", "optional", "mandatory"]
    is_mandatory: bool
    grace_period_days: Optional[int] = None
    enforcement_deadline: Optional[datetime] = (
        None  # When mandatory 2FA must be set up by
    )
    user_has_2fa: bool  # Whether the current user has 2FA enabled
    requires_setup: bool  # True if mandatory and user doesn't have 2FA set up


class UserWithout2FAInfo(BaseModel):
    """Basic user info for users without 2FA."""

    id: UUID
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UsersWithout2FAResponse(BaseModel):
    """Response for listing users without 2FA enabled."""

    users: list[UserWithout2FAInfo]
    total: int
