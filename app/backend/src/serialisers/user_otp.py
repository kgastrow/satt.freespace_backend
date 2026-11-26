from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GetUserOtpRequest(BaseModel):
    user_id: UUID
    otp_code: str

    model_config = ConfigDict(extra="forbid")


class CreateUserOtpRequest(BaseModel):
    user_id: UUID
    otp_code: str
    expires_at: datetime

    model_config = ConfigDict(extra="forbid")


class DeleteUserOtpRequest(BaseModel):
    id: UUID

    model_config = ConfigDict(extra="forbid")


# API request/response models


class GenerateOTPResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")


class VerifyOTPRequest(BaseModel):
    user_id: str
    otp_code: str
    organization_id: str

    model_config = ConfigDict(extra="forbid")


class VerifyOTPResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")


class VerifyEmailRequest(BaseModel):
    email: str
    otp_code: str
    organization_slug: str  # Required for tenant isolation

    model_config = ConfigDict(extra="forbid")


class SendVerificationEmailRequest(BaseModel):
    email: str
    organization_slug: str  # Required for tenant isolation

    model_config = ConfigDict(extra="forbid")


class SendVerificationEmailResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
