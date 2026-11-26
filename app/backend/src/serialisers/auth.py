from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from src.serialisers.common import NormalizedEmail


class LoginRequest(BaseModel):
    email: NormalizedEmail = Field(..., description="User email address")
    password: str = Field(..., min_length=1, description="User password")
    organization_slug: str = Field(
        ..., min_length=1, description="Organization identifier"
    )
    model_config = ConfigDict(extra="forbid")


class AccessTokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")


class LoginResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="Refresh token")


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh token")
    model_config = ConfigDict(extra="forbid")


class RefreshTokenResponse(BaseModel):
    access_token: str = Field(..., description="New JWT access token")


class LogoutRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh token to invalidate")
    model_config = ConfigDict(extra="forbid")


class LogoutAllRequest(BaseModel):
    user_id: str = Field(..., description="User ID to log out from all devices")
    model_config = ConfigDict(extra="forbid")


# Password Reset Serializers
class PasswordResetRequestRequest(BaseModel):
    """Request to initiate password reset."""

    email: NormalizedEmail = Field(
        ..., description="Email address of the account to reset"
    )
    organization_slug: str = Field(
        ..., min_length=1, description="Organization identifier"
    )

    model_config = ConfigDict(extra="forbid")


class PasswordResetRequestResponse(BaseModel):
    """Response for password reset request - intentionally vague for security."""

    message: str = Field(
        default="If an account exists with this email, a password reset link has been sent.",
        description="Status message",
    )
    message_code: str = Field(..., description="Translation code for i18n")


class PasswordResetConfirmRequest(BaseModel):
    """Request to confirm password reset with new password."""

    token: str = Field(..., min_length=1, description="Password reset token from email")
    new_password: str = Field(
        ..., min_length=8, description="New password (minimum 8 characters)"
    )
    organization_slug: str = Field(
        ..., min_length=1, description="Organization identifier"
    )

    model_config = ConfigDict(extra="forbid")


class PasswordResetConfirmResponse(BaseModel):
    """Response for successful password reset."""

    message: str = Field(
        default="Password has been reset successfully. You can now log in with your new password.",
        description="Status message",
    )
    message_code: str = Field(..., description="Translation code for i18n")


class LoginResponseWith2FA(BaseModel):
    """Login response when 2FA is required."""

    requires_2fa: bool = Field(default=True, description="Indicates 2FA is required")
    two_factor_token: str = Field(
        ..., description="Temporary token for 2FA verification"
    )


class Verify2FARequest(BaseModel):
    """Request to verify 2FA code."""

    two_factor_token: str = Field(..., description="Temporary token from initial login")
    code: str = Field(
        ...,
        min_length=6,
        max_length=8,
        description="6-digit TOTP or 8-character backup code",
    )

    model_config = ConfigDict(extra="forbid")


# SSO Account Linking Serializers
class SSOLinkingRequiredResponse(BaseModel):
    """Response when SSO login requires account linking confirmation."""

    requires_linking: bool = Field(
        default=True, description="Indicates account linking is required"
    )
    link_token: str = Field(..., description="Temporary token for linking confirmation")
    email: str = Field(..., description="Email address of the existing account")
    provider: str = Field(..., description="SSO provider name (e.g., 'google')")


class ConfirmLinkRequest(BaseModel):
    """Request to confirm SSO account linking.

    The link token alone only proves that somebody completed an OAuth flow for
    an address that matches an existing account, so the endpoint additionally
    requires proof that the caller controls that account. Exactly one of two
    proofs is accepted:

    1. An existing bearer session for the same user in the same organization,
       sent in the ``Authorization`` header rather than in this body.
    2. ``password`` - the existing account's password, re-entered. This is the
       signed-out SSO callback path.
    """

    link_token: str = Field(..., description="Token from SSO linking required response")
    password: Optional[str] = Field(
        default=None,
        description=(
            "Password of the existing account. One of the two accepted proofs "
            "of account control; omit it when the caller is already signed in "
            "as that account and proves control with its bearer session."
        ),
    )

    model_config = ConfigDict(extra="forbid")


# Check Email (Two-Step Login) Serializers
class CheckEmailRequest(BaseModel):
    """Request to check available auth methods for an email."""

    email: NormalizedEmail = Field(..., description="User email address")
    organization_slug: str = Field(
        ..., min_length=1, description="Organization identifier"
    )

    model_config = ConfigDict(extra="forbid")


class CheckEmailResponse(BaseModel):
    """Response with available authentication methods for the email."""

    exists: bool = Field(..., description="Whether an account exists with this email")
    auth_methods: list[str] = Field(
        default_factory=list,
        description="Available auth methods: 'password', 'google', etc.",
    )
