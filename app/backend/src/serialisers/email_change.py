"""
Pydantic serializers for email change API endpoints.
Request/response models for the multi-step email change verification flow.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.serialisers.common import NormalizedEmail


class InitiateEmailChangeRequest(BaseModel):
    """Request to initiate an email change."""

    new_email: NormalizedEmail = Field(
        ..., max_length=255, description="The new email address"
    )
    model_config = ConfigDict(extra="forbid")


class InitiateEmailChangeResponse(BaseModel):
    """Response after initiating email change."""

    message: str
    message_code: str
    request_id: str
    status: str


class VerifyIdentityRequest(BaseModel):
    """Request to verify user identity (password or 2FA)."""

    verification_method: Literal["password", "totp", "sms_2fa"] = Field(
        ..., description="Method of identity verification"
    )
    verification_value: str = Field(
        ..., min_length=1, max_length=255, description="Password or 2FA code"
    )
    model_config = ConfigDict(extra="forbid")


class VerifyIdentityResponse(BaseModel):
    """Response after identity verification."""

    message: str
    message_code: str
    status: str


class VerifyOTPRequest(BaseModel):
    """Request to verify OTP sent to new email."""

    otp_code: str = Field(
        ..., min_length=6, max_length=6, description="6-digit OTP code"
    )
    model_config = ConfigDict(extra="forbid")

    @field_validator("otp_code")
    @classmethod
    def validate_otp_format(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("OTP must be numeric")
        return v


class VerifyOTPResponse(BaseModel):
    """Response after OTP verification and email change completion."""

    message: str
    message_code: str
    status: str


class ResendOTPRequest(BaseModel):
    """Request to resend OTP to new email."""

    model_config = ConfigDict(extra="forbid")


class ResendOTPResponse(BaseModel):
    """Response after resending OTP."""

    message: str
    message_code: str


class CancelEmailChangeResponse(BaseModel):
    """Response after cancelling email change request."""

    message: str
    message_code: str


class EmailChangeStatusResponse(BaseModel):
    """Response for getting current email change request status."""

    has_active_request: bool
    request_id: Optional[str] = None
    old_email: Optional[str] = None
    new_email: Optional[str] = None
    status: Optional[str] = None
    identity_verified: Optional[bool] = None
    otp_attempts: Optional[int] = None
    otp_resend_count: Optional[int] = None
    expires_at: Optional[datetime] = None
