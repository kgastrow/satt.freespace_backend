"""
Admin API serializer models.
Contains all Pydantic models for admin-related API endpoints.
"""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# System Config Models
# =============================================================================


class SystemConfigResponse(BaseModel):
    """Response model for a system configuration entry"""

    model_config = ConfigDict(from_attributes=True)

    key: str
    value: Any
    description: Optional[str] = None
    updated_time: str
    updated_by_user_id: Optional[str] = None


class ListSystemConfigResponse(BaseModel):
    """Response model for listing all system configurations"""

    items: list[SystemConfigResponse]
    total: int
    limit: int
    offset: int


class UpdateSystemConfigRequest(BaseModel):
    """Request model for updating a system configuration"""

    model_config = ConfigDict(extra="forbid")

    value: Any = Field(..., description="The new configuration value (JSON)")
    description: Optional[str] = Field(
        None, description="Optional description of the config"
    )


class UpdateSystemConfigResponse(BaseModel):
    """Response model for updating a system configuration"""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    config: SystemConfigResponse


# =============================================================================
# Notification Provider Models
# =============================================================================


class NotificationProviderResponse(BaseModel):
    """Response model for a notification provider"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    channel: str
    is_active: bool
    is_default: bool
    config: dict  # Sensitive fields should be masked
    created_time: str
    updated_time: Optional[str] = None


class ListNotificationProvidersResponse(BaseModel):
    """Response model for listing notification providers"""

    items: list[NotificationProviderResponse]
    total: int
    limit: int
    offset: int


class CreateNotificationProviderRequest(BaseModel):
    """Request model for creating a notification provider"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Provider name (e.g., aws_sns, twilio)",
    )
    channel: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Channel type: sms, whatsapp, email",
    )
    is_active: bool = Field(default=True, description="Whether the provider is active")
    is_default: bool = Field(
        default=False,
        description="Whether this is the default provider for the channel",
    )
    config: dict = Field(..., description="Provider-specific configuration")


class CreateNotificationProviderResponse(BaseModel):
    """Response model for creating a notification provider"""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    provider: NotificationProviderResponse


class UpdateNotificationProviderRequest(BaseModel):
    """Request model for updating a notification provider"""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=1, max_length=50)
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    config: Optional[dict] = None


class UpdateNotificationProviderResponse(BaseModel):
    """Response model for updating a notification provider"""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    provider: NotificationProviderResponse


class DeleteNotificationProviderResponse(BaseModel):
    """Response model for deactivating a notification provider"""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    provider_id: str


# =============================================================================
# System Template Models
# =============================================================================


class SystemTemplateResponse(BaseModel):
    """Response model for a system notification template"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    description: Optional[str] = None
    channel: str
    subject: Optional[str] = None
    body_text: str
    body_html: Optional[str] = None
    variables: Optional[dict] = None
    is_active: bool
    created_time: str
    updated_time: Optional[str] = None


class ListSystemTemplatesResponse(BaseModel):
    """Response model for listing system templates"""

    items: list[SystemTemplateResponse]
    total: int
    limit: int
    offset: int


class CreateSystemTemplateRequest(BaseModel):
    """Request model for creating a system template"""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Template code (e.g., welcome_email)",
    )
    name: str = Field(
        ..., min_length=1, max_length=255, description="Human-readable template name"
    )
    description: Optional[str] = Field(None, description="Template description")
    channel: str = Field(
        ..., min_length=1, max_length=20, description="Channel: email, sms, whatsapp"
    )
    subject: Optional[str] = Field(
        None, max_length=255, description="Email subject (for email channel)"
    )
    body_text: str = Field(..., min_length=1, description="Plain text body content")
    body_html: Optional[str] = Field(None, description="HTML body content (for email)")
    variables: Optional[dict] = Field(None, description="Template variables schema")
    is_active: bool = Field(default=True, description="Whether the template is active")


class CreateSystemTemplateResponse(BaseModel):
    """Response model for creating a system template"""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    template: SystemTemplateResponse


class UpdateSystemTemplateRequest(BaseModel):
    """Request model for updating a system template"""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    subject: Optional[str] = Field(None, max_length=255)
    body_text: Optional[str] = Field(None, min_length=1)
    body_html: Optional[str] = None
    variables: Optional[dict] = None
    is_active: Optional[bool] = None


class UpdateSystemTemplateResponse(BaseModel):
    """Response model for updating a system template"""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    template: SystemTemplateResponse


class DeleteSystemTemplateResponse(BaseModel):
    """Response model for deleting a system template"""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    template_id: str


# =============================================================================
# System Category Models
# =============================================================================


class SystemCategoryResponse(BaseModel):
    """Response model for a system notification category"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    description: Optional[str] = None
    default_enabled: bool
    user_configurable: bool
    display_order: int
    created_time: str
    updated_time: Optional[str] = None


class ListSystemCategoriesResponse(BaseModel):
    """Response model for listing system categories"""

    items: list[SystemCategoryResponse]
    total: int
    limit: int
    offset: int


class CreateSystemCategoryRequest(BaseModel):
    """Request model for creating a system category"""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Category code (e.g., marketing, announcements)",
    )
    name: str = Field(
        ..., min_length=1, max_length=100, description="Human-readable category name"
    )
    description: Optional[str] = Field(None, description="Category description")
    default_enabled: bool = Field(
        default=True, description="Whether users are opted-in by default"
    )
    user_configurable: bool = Field(
        default=True, description="Whether users can change this preference"
    )
    display_order: int = Field(default=0, description="Order for display in UI")


class CreateSystemCategoryResponse(BaseModel):
    """Response model for creating a system category"""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    category: SystemCategoryResponse


# =============================================================================
# File Settings Admin Models
# =============================================================================


class OrganizationFileSettingsResponse(BaseModel):
    """Response model for organization file settings"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    organization_name: Optional[str] = None
    max_file_size_bytes: int
    max_video_size_bytes: int
    allowed_extensions: list[str]
    user_storage_quota_bytes: Optional[int] = None
    org_storage_quota_bytes: Optional[int] = None
    signed_url_expiry_seconds: int
    deleted_file_retention_days: int
    created_time: str
    updated_time: Optional[str] = None


class ListOrganizationFileSettingsResponse(BaseModel):
    """Response model for listing all organization file settings"""

    items: list[OrganizationFileSettingsResponse]
    total: int
    limit: int
    offset: int


class TriggerHardDeleteRequest(BaseModel):
    """Request model for triggering hard delete of old files"""

    model_config = ConfigDict(extra="forbid")

    organization_id: Optional[str] = Field(
        None, description="Specific organization ID (optional, all if not provided)"
    )
    dry_run: bool = Field(
        default=True, description="If true, only report what would be deleted"
    )


class TriggerHardDeleteResponse(BaseModel):
    """Response model for hard delete operation"""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    files_deleted: int
    total_bytes_freed: int
    dry_run: bool


# =============================================================================
# S3 Storage Config Models
# =============================================================================


class S3ConfigResponse(BaseModel):
    """Response model for S3 storage configuration"""

    enabled: bool
    bucket: Optional[str] = None
    region: Optional[str] = None
    endpoint_url: Optional[str] = None


class UpdateS3ConfigRequest(BaseModel):
    """Request model for updating S3 configuration"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(..., description="Enable or disable S3 storage")
    bucket: Optional[str] = Field(None, description="S3 bucket name")
    region: Optional[str] = Field(None, description="AWS region")
    endpoint_url: Optional[str] = Field(
        None, description="Custom endpoint URL for S3-compatible services"
    )


class UpdateS3ConfigResponse(BaseModel):
    """Response model for updating S3 configuration"""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    config: S3ConfigResponse
