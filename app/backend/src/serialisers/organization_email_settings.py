"""
Serializers for Organization Email Settings API.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class EmailProviderEnum(str, Enum):
    """Supported email providers."""

    SMTP = "smtp"
    SENDGRID = "sendgrid"


class EmailSettingsResponse(BaseModel):
    """
    Response schema for organization email settings.

    Credentials are masked for security.
    """

    id: UUID
    organization_id: UUID
    provider: Optional[str] = None
    provider_display: str = Field(
        default="Platform Default",
        description="Human-readable provider name",
    )

    # SMTP settings (password masked)
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password_set: bool = Field(
        default=False, description="Whether SMTP password is configured"
    )
    smtp_use_tls: Optional[bool] = None
    smtp_use_ssl: Optional[bool] = None

    # SendGrid (API key masked)
    sendgrid_api_key_set: bool = Field(
        default=False, description="Whether SendGrid API key is configured"
    )

    # Branding
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None
    reply_to_email: Optional[str] = None

    # Timestamps
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None

    # Effective config info
    using_platform_defaults: bool = Field(
        default=True, description="Whether using platform defaults for provider"
    )

    model_config = ConfigDict(from_attributes=True)


class EffectiveEmailConfigResponse(BaseModel):
    """
    Response schema for the effective (merged) email configuration.

    Shows what config will actually be used for sending emails.
    Credentials are masked.
    """

    provider: str
    provider_display: str

    # SMTP settings (masked)
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username_set: bool = False
    smtp_password_set: bool = False
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False

    # SendGrid (masked)
    sendgrid_api_key_set: bool = False

    # Branding
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None
    reply_to_email: Optional[str] = None

    # Source info
    config_source: str = Field(
        description="Where the config comes from: 'organization', 'platform', or 'default'"
    )


class UpdateEmailSettingsRequest(BaseModel):
    """Request schema for updating organization email settings."""

    provider: Optional[EmailProviderEnum] = Field(
        default=None, description="Email provider. NULL uses platform default."
    )

    # SMTP settings
    smtp_host: Optional[str] = Field(default=None, max_length=255)
    smtp_port: Optional[int] = Field(default=None, ge=1, le=65535)
    smtp_username: Optional[str] = Field(default=None, max_length=255)
    smtp_password: Optional[str] = Field(default=None, max_length=255)
    smtp_use_tls: Optional[bool] = None
    smtp_use_ssl: Optional[bool] = None

    # SendGrid settings
    sendgrid_api_key: Optional[str] = Field(default=None, max_length=255)

    # Branding
    sender_email: Optional[EmailStr] = None
    sender_name: Optional[str] = Field(default=None, max_length=255)
    reply_to_email: Optional[EmailStr] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("provider", mode="before")
    @classmethod
    def convert_provider(cls, v):
        if v == "" or v is None:
            return None
        return v


class TestEmailRequest(BaseModel):
    """Request schema for sending a test email."""

    recipient_email: EmailStr = Field(description="Email address to send test to")

    model_config = ConfigDict(extra="forbid")


class TestEmailResponse(BaseModel):
    """Response schema for test email result."""

    success: bool
    message: str
    message_code: str
    provider_used: str


class ResetEmailSettingsResponse(BaseModel):
    """Response schema for resetting email settings."""

    message: str
    message_code: str


def build_email_settings_response(
    email_settings,
    decrypted_data: dict,
) -> EmailSettingsResponse:
    """
    Build an EmailSettingsResponse from model and decrypted data.

    Args:
        email_settings: The OrganizationEmailSettings model instance
        decrypted_data: Dictionary with decrypted credential info

    Returns:
        EmailSettingsResponse with masked credentials
    """
    provider = email_settings.provider
    provider_display = "Platform Default"
    if provider == "smtp":
        provider_display = "SMTP"
    elif provider == "sendgrid":
        provider_display = "SendGrid"

    return EmailSettingsResponse(
        id=email_settings.id,
        organization_id=email_settings.organization_id,
        provider=provider,
        provider_display=provider_display,
        smtp_host=email_settings.smtp_host,
        smtp_port=email_settings.smtp_port,
        smtp_username=decrypted_data.get("smtp_username"),
        smtp_password_set=bool(decrypted_data.get("smtp_password")),
        smtp_use_tls=email_settings.smtp_use_tls,
        smtp_use_ssl=email_settings.smtp_use_ssl,
        sendgrid_api_key_set=bool(decrypted_data.get("sendgrid_api_key")),
        sender_email=email_settings.sender_email,
        sender_name=email_settings.sender_name,
        reply_to_email=email_settings.reply_to_email,
        created_time=email_settings.created_time,
        updated_time=email_settings.updated_time,
        using_platform_defaults=provider is None,
    )


def build_effective_config_response(
    email_config,
    config_source: str,
) -> EffectiveEmailConfigResponse:
    """
    Build an EffectiveEmailConfigResponse from EmailConfig.

    Args:
        email_config: The EmailConfig dataclass
        config_source: Source of config ('organization', 'platform', 'default')

    Returns:
        EffectiveEmailConfigResponse with masked credentials
    """
    provider_display = "SMTP" if email_config.provider == "smtp" else "SendGrid"

    return EffectiveEmailConfigResponse(
        provider=email_config.provider,
        provider_display=provider_display,
        smtp_host=email_config.smtp_host,
        smtp_port=email_config.smtp_port,
        smtp_username_set=bool(email_config.smtp_username),
        smtp_password_set=bool(email_config.smtp_password),
        smtp_use_tls=email_config.smtp_use_tls,
        smtp_use_ssl=email_config.smtp_use_ssl,
        sendgrid_api_key_set=bool(email_config.sendgrid_api_key),
        sender_email=email_config.sender_email,
        sender_name=email_config.sender_name,
        reply_to_email=email_config.reply_to_email,
        config_source=config_source,
    )
