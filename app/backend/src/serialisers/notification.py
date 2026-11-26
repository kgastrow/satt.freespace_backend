"""
Notification API serializer models.
Contains all Pydantic models for notification-related API endpoints.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.logger.logger import Logger as logger
from src.serialisers.common import PaginatedResponse


# =============================================================================
# Send Notification Models
# =============================================================================


class SendNotificationRequest(BaseModel):
    """Request to send a single notification to a user."""

    channel: str = Field(..., description="Channel: email, sms, whatsapp, or in_app")
    user_id: UUID = Field(
        ...,
        description="User ID to send notification to (must be active user in organization)",
    )
    content: Optional[str] = Field(
        None, description="Message content (if not using template)"
    )
    subject: Optional[str] = Field(None, description="Subject for email notifications")
    template_code: Optional[str] = Field(None, description="Template code to use")
    template_variables: Optional[dict] = Field(
        None, description="Variables for template rendering"
    )
    category_code: Optional[str] = Field(None, description="Notification category code")
    is_urgent: bool = Field(False, description="If true, bypasses quiet hours")
    metadata: Optional[dict] = Field(None, description="Additional metadata")

    model_config = ConfigDict(extra="forbid")


class NotificationResponse(BaseModel):
    """Response for a sent notification."""

    id: UUID
    channel: str
    recipient: str
    status: str = Field(
        ..., description="Status: pending, queued, sent, delivered, failed"
    )
    provider_message_id: Optional[str] = None
    created_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SendNotificationResponse(BaseModel):
    """Response after sending a notification."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    notification: NotificationResponse

    model_config = ConfigDict(extra="forbid")


# =============================================================================
# Bulk Notification Models
# =============================================================================


# The recipient-filter key names are a public contract: they are persisted
# verbatim into BulkNotification.extra_data["recipient_filters"] and read back
# by BulkProcessor._build_recipient_conditions, so a row written before a rename
# must still resolve. Both names live here, the module that owns the contract.
VERIFIED_CONTACT_KEY = "verified_contact_only"
LEGACY_VERIFIED_CONTACT_KEY = "email_verified_only"


class RecipientFilter(BaseModel):
    """Filters for selecting bulk notification recipients.

    These field names ARE the filter contract. They are persisted verbatim into
    ``BulkNotification.extra_data["recipient_filters"]`` and read back by
    ``BulkProcessor._build_recipient_conditions``, which applies every one of
    them to both the count query and the send query. Previously the processor
    understood a different, undocumented set of keys ("role",
    "specific_user_ids", "all_users") that nothing could ever send, so every
    declared filter here was silently discarded and every bulk went org-wide.

    Filters combine with AND: each one only ever NARROWS the audience. Omitting
    all of them selects every user in the organisation.
    """

    role_ids: Optional[list[UUID]] = Field(
        None,
        description=(
            "Narrow to users holding at least one of these roles. "
            "Combined with other filters using AND."
        ),
    )
    user_ids: Optional[list[UUID]] = Field(
        None,
        description=(
            "Narrow to these specific users. Combined with other filters "
            "using AND, so pairing this with role_ids selects only users who "
            "are in BOTH lists - it never widens the audience."
        ),
    )
    exclude_user_ids: Optional[list[UUID]] = Field(
        None, description="User IDs to exclude (applied last, always wins)"
    )
    verified_contact_only: bool = Field(
        True,
        description=(
            "Only include users whose contact address FOR THE BULK'S CHANNEL is "
            "verified. The channel decides which column is checked: email -> "
            "email_verified, sms/whatsapp -> phone_verified, in_app -> nothing "
            "(there is no external address to verify). Was named "
            "'email_verified_only', which is still accepted as a deprecated "
            "alias; that name checked email_verified on EVERY channel, so an "
            "SMS blast silently skipped users who had verified their phone but "
            "not their email."
        ),
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_verified_contact_key(cls, data: Any) -> Any:
        """Accept the deprecated ``email_verified_only`` key.

        ``extra="forbid"`` means an unmigrated caller would otherwise get a 422
        on a payload that worked yesterday, so the old key is translated here
        rather than rejected. The new key wins if both are present.
        """
        if not isinstance(data, dict) or LEGACY_VERIFIED_CONTACT_KEY not in data:
            return data

        data = dict(data)
        legacy_value = data.pop(LEGACY_VERIFIED_CONTACT_KEY)
        logger.warning(
            f"RecipientFilter received deprecated '{LEGACY_VERIFIED_CONTACT_KEY}'; "
            f"use '{VERIFIED_CONTACT_KEY}' instead. The check is now channel-aware "
            "(email -> email_verified, sms/whatsapp -> phone_verified, "
            "in_app -> none)."
        )
        if VERIFIED_CONTACT_KEY not in data:
            data[VERIFIED_CONTACT_KEY] = legacy_value
        return data


class CreateBulkNotificationRequest(BaseModel):
    """Request to create a bulk notification."""

    name: str = Field(..., description="Name/description of the bulk notification")
    channel: str = Field(..., description="Channel: email, sms, whatsapp, or in_app")
    template_code: Optional[str] = Field(None, description="Template code to use")
    subject: Optional[str] = Field(
        None, description="Subject for email (if not using template)"
    )
    body_text: Optional[str] = Field(
        None, description="Message body (if not using template)"
    )
    body_html: Optional[str] = Field(
        None, description="HTML body for email (if not using template)"
    )
    recipient_filters: RecipientFilter = Field(
        ..., description="Filters to select recipients"
    )
    scheduled_time: Optional[datetime] = Field(
        None, description="Schedule for later (null = send now)"
    )
    category_code: Optional[str] = Field(None, description="Notification category code")

    model_config = ConfigDict(extra="forbid")


class BulkNotificationResponse(BaseModel):
    """Response for a bulk notification."""

    id: UUID
    name: str
    channel: str
    status: str = Field(
        ..., description="Status: pending, processing, completed, failed, cancelled"
    )
    total_recipients: int
    sent_count: int
    failed_count: int
    scheduled_time: Optional[datetime] = None
    started_time: Optional[datetime] = None
    completed_time: Optional[datetime] = None
    created_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CreateBulkNotificationResponse(BaseModel):
    """Response after creating a bulk notification."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    bulk_notification: BulkNotificationResponse

    model_config = ConfigDict(extra="forbid")


class CancelBulkNotificationResponse(BaseModel):
    """Response after cancelling a bulk notification."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    bulk_notification_id: UUID
    status: str

    model_config = ConfigDict(extra="forbid")


# =============================================================================
# Notification History Models
# =============================================================================


class NotificationDetailResponse(BaseModel):
    """Detailed notification response."""

    id: UUID
    channel: str
    provider: Optional[str] = None
    recipient: str
    user_id: Optional[UUID] = None
    template_id: Optional[UUID] = None
    subject: Optional[str] = None
    body_preview: Optional[str] = None
    status: str
    provider_message_id: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    bulk_notification_id: Optional[UUID] = None
    metadata: Optional[dict] = None
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(PaginatedResponse):
    """Paginated list of notifications."""

    items: list[NotificationDetailResponse]


# =============================================================================
# Template Models
# =============================================================================


class TemplateResponse(BaseModel):
    """Response for a notification template."""

    id: UUID
    organization_id: Optional[UUID] = Field(
        None, description="Null for system templates"
    )
    code: str
    name: str
    description: Optional[str] = None
    channel: str
    subject: Optional[str] = None
    body_text: str
    body_html: Optional[str] = None
    variables: Optional[dict] = None
    is_active: bool
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TemplateListResponse(PaginatedResponse):
    """Paginated list of templates."""

    items: list[TemplateResponse]


class CreateTemplateRequest(BaseModel):
    """Request to create a custom template."""

    code: str = Field(
        ..., min_length=1, max_length=100, description="Unique template code"
    )
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    channel: str = Field(..., description="Channel: email, sms, whatsapp, or in_app")
    subject: Optional[str] = Field(
        None, max_length=255, description="Subject for email"
    )
    body_text: str = Field(..., description="Text body content")
    body_html: Optional[str] = Field(None, description="HTML body for email")
    variables: Optional[dict] = Field(None, description="Expected variables schema")
    is_active: bool = True

    model_config = ConfigDict(extra="forbid")


class UpdateTemplateRequest(BaseModel):
    """Request to update a template."""

    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    subject: Optional[str] = Field(None, max_length=255)
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    variables: Optional[dict] = None
    is_active: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")


class CreateTemplateResponse(BaseModel):
    """Response after creating a template."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    template: TemplateResponse

    model_config = ConfigDict(extra="forbid")


class UpdateTemplateResponse(BaseModel):
    """Response after updating a template."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    template: TemplateResponse

    model_config = ConfigDict(extra="forbid")


class DeleteTemplateResponse(BaseModel):
    """Response after deleting a template."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    template_id: UUID

    model_config = ConfigDict(extra="forbid")


# =============================================================================
# Organization Settings Models
# =============================================================================


class NotificationSettingsResponse(BaseModel):
    """Organization notification settings."""

    id: UUID
    organization_id: UUID
    email_enabled: bool
    sms_enabled: bool
    whatsapp_enabled: bool
    in_app_enabled: bool
    web_push_enabled: bool
    sms_provider: Optional[str] = None
    whatsapp_provider: Optional[str] = None
    notification_retention_days: int
    sms_rate_limit: int
    whatsapp_rate_limit: int
    email_sender_name: Optional[str] = None
    sms_sender_id: Optional[str] = None
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UpdateNotificationSettingsRequest(BaseModel):
    """Request to update organization notification settings."""

    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    whatsapp_enabled: Optional[bool] = None
    in_app_enabled: Optional[bool] = None
    web_push_enabled: Optional[bool] = None
    sms_provider: Optional[str] = None
    whatsapp_provider: Optional[str] = None
    notification_retention_days: Optional[int] = Field(None, ge=1, le=365)
    sms_rate_limit: Optional[int] = Field(None, ge=1)
    whatsapp_rate_limit: Optional[int] = Field(None, ge=1)
    email_sender_name: Optional[str] = Field(None, max_length=255)
    sms_sender_id: Optional[str] = Field(None, max_length=20)

    model_config = ConfigDict(extra="forbid")


class UpdateNotificationSettingsResponse(BaseModel):
    """Response after updating notification settings."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    settings: NotificationSettingsResponse

    model_config = ConfigDict(extra="forbid")


# =============================================================================
# User Preferences Models
# =============================================================================


class UserNotificationPreferenceResponse(BaseModel):
    """User notification preferences."""

    id: UUID
    user_id: UUID
    organization_id: UUID
    email_enabled: bool
    sms_enabled: bool
    whatsapp_enabled: bool
    in_app_enabled: bool
    web_push_enabled: bool
    quiet_hours_enabled: bool
    quiet_hours_start: Optional[str] = Field(None, description="Time in HH:MM format")
    quiet_hours_end: Optional[str] = Field(None, description="Time in HH:MM format")
    quiet_hours_timezone: str
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UpdateUserPreferenceRequest(BaseModel):
    """Request to update user notification preferences."""

    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    whatsapp_enabled: Optional[bool] = None
    in_app_enabled: Optional[bool] = None
    web_push_enabled: Optional[bool] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = Field(None, description="Time in HH:MM format")
    quiet_hours_end: Optional[str] = Field(None, description="Time in HH:MM format")
    quiet_hours_timezone: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class UpdateUserPreferenceResponse(BaseModel):
    """Response after updating user preferences."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    preferences: UserNotificationPreferenceResponse

    model_config = ConfigDict(extra="forbid")


# =============================================================================
# Category Models
# =============================================================================


class CategoryResponse(BaseModel):
    """Notification category."""

    id: UUID
    organization_id: Optional[UUID] = Field(
        None, description="Null for system categories"
    )
    code: str
    name: str
    description: Optional[str] = None
    default_enabled: bool
    user_configurable: bool
    display_order: int
    created_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CategoryListResponse(PaginatedResponse):
    """Paginated list of categories."""

    items: list[CategoryResponse]


class CategoryWithPreferenceResponse(BaseModel):
    """Category with user's preference."""

    category: CategoryResponse
    email_enabled: bool
    sms_enabled: bool
    whatsapp_enabled: bool
    in_app_enabled: bool
    web_push_enabled: bool

    model_config = ConfigDict(extra="forbid")


class CategoryPreferencesResponse(BaseModel):
    """List of categories with user preferences."""

    items: list[CategoryWithPreferenceResponse]

    model_config = ConfigDict(extra="forbid")


class UpdateCategoryPreferenceRequest(BaseModel):
    """Request to update preference for a specific category."""

    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    whatsapp_enabled: Optional[bool] = None
    in_app_enabled: Optional[bool] = None
    web_push_enabled: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")


class UpdateCategoryPreferenceResponse(BaseModel):
    """Response after updating category preference."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    category_id: UUID
    email_enabled: bool
    sms_enabled: bool
    whatsapp_enabled: bool
    in_app_enabled: bool
    web_push_enabled: bool

    model_config = ConfigDict(extra="forbid")


class CreateCategoryRequest(BaseModel):
    """Request to create a notification category."""

    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    default_enabled: bool = True
    user_configurable: bool = True
    display_order: int = 0

    model_config = ConfigDict(extra="forbid")


class UpdateCategoryRequest(BaseModel):
    """Request to update a notification category."""

    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    default_enabled: Optional[bool] = None
    user_configurable: Optional[bool] = None
    display_order: Optional[int] = None

    model_config = ConfigDict(extra="forbid")


class CreateCategoryResponse(BaseModel):
    """Response after creating a category."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    category: CategoryResponse

    model_config = ConfigDict(extra="forbid")


class UpdateCategoryResponse(BaseModel):
    """Response after updating a category."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    category: CategoryResponse

    model_config = ConfigDict(extra="forbid")


class DeleteCategoryResponse(BaseModel):
    """Response after deleting a category."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    category_id: UUID

    model_config = ConfigDict(extra="forbid")


# =============================================================================
# Unsubscribe Models
# =============================================================================


class UnsubscribeInfoResponse(BaseModel):
    """Information for unsubscribe page."""

    user_email: str
    organization_name: str
    category_name: Optional[str] = None
    channel: str
    is_already_unsubscribed: bool

    model_config = ConfigDict(extra="forbid")


class UnsubscribeRequest(BaseModel):
    """Request to process unsubscribe."""

    token: str = Field(..., description="Unsubscribe token from email link")

    model_config = ConfigDict(extra="forbid")


class UnsubscribeResponse(BaseModel):
    """Response after processing unsubscribe."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    success: bool

    model_config = ConfigDict(extra="forbid")
