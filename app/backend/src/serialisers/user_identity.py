"""Serializers for user identity (connected accounts) management."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserIdentityResponse(BaseModel):
    """Response model for a single user identity."""

    id: str = Field(..., description="Identity UUID")
    provider: str = Field(..., description="Provider name (e.g., 'email', 'google')")
    provider_email: str | None = Field(
        None, description="Email from the provider (if available)"
    )
    linked_at: datetime = Field(..., description="When the identity was linked")
    is_primary: bool = Field(
        ..., description="True if this matches the user's created_via"
    )
    can_unlink: bool = Field(
        ...,
        description="False if this is the only auth method and user has no password",
    )

    model_config = ConfigDict(from_attributes=True)


class UserIdentitiesResponse(BaseModel):
    """Response model for listing user identities with account metadata."""

    identities: list[UserIdentityResponse] = Field(
        ..., description="List of linked identities"
    )
    created_via: str = Field(
        ..., description="How the account was originally created ('email', 'google')"
    )
    has_password: bool = Field(..., description="Whether the user has a password set")
    two_factor_policy: str = Field(
        ...,
        description="Organization's 2FA policy ('disabled', 'optional', 'mandatory')",
    )
    two_factor_enabled: bool = Field(
        ..., description="Whether the user has 2FA enabled"
    )
    requires_setup_for_unlink: bool = Field(
        ...,
        description="True if user must set up password (and possibly 2FA) before unlinking",
    )

    model_config = ConfigDict(from_attributes=True)


class UnlinkIdentityRequest(BaseModel):
    """Request to unlink an identity (simple unlink, no body needed)."""

    model_config = ConfigDict(extra="forbid")


class UnlinkWithSetupRequest(BaseModel):
    """Request to unlink an identity with account security setup."""

    new_password: str = Field(
        ..., min_length=8, description="New password for the account"
    )
    totp_secret: str | None = Field(None, description="TOTP secret if setting up 2FA")
    totp_code: str | None = Field(
        None,
        min_length=6,
        max_length=6,
        description="TOTP code to verify 2FA setup",
    )

    model_config = ConfigDict(extra="forbid")


class UnlinkIdentityResponse(BaseModel):
    """Response for successful identity unlink."""

    message: str = Field(default="Identity unlinked successfully")
    message_code: str = Field(..., description="Translation code for i18n")


class UnlinkWithSetupResponse(BaseModel):
    """Response for successful identity unlink with setup."""

    message: str = Field(default="Account security configured and identity unlinked")
    message_code: str = Field(..., description="Translation code for i18n")
    backup_codes: list[str] | None = Field(
        None, description="Backup codes if 2FA was enabled"
    )
