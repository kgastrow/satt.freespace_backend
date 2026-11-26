"""
Phone verification serializers for API request/response models.
"""

from typing import Optional

from pydantic import BaseModel, Field
from pydantic_extra_types.phone_numbers import PhoneNumber


PhoneNumber.phone_format = "E164"


class SendPhoneOTPRequest(BaseModel):
    """Request model for sending phone OTP."""

    phone: PhoneNumber = Field(..., description="Phone number in E.164 format")


class SendPhoneOTPResponse(BaseModel):
    """Response model for sending phone OTP."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    verification_id: str
    expires_at: str


class VerifyPhoneOTPRequest(BaseModel):
    """Request model for verifying phone OTP."""

    phone: PhoneNumber = Field(..., description="Phone number in E.164 format")
    otp_code: str = Field(
        ..., min_length=6, max_length=6, description="6-digit OTP code"
    )


class VerifyPhoneOTPResponse(BaseModel):
    """Response model for verifying phone OTP."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    verified: bool
    phone: Optional[str] = None
