"""
Notification API endpoints.
Provides endpoints for sending notifications, managing templates, user preferences,
bulk notifications, and notification history.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from src.api.deps import (
    CurrentUser,
    get_current_user,
    get_session,
    require_permission,
)
from src.core.exceptions import create_http_exception
from src.core.query_params import get_pagination_params, parse_filters, parse_sort
from src.core.response_codes import get_response_code
from src.crud.bulk_notification import (
    cancel_bulk_notification as crud_cancel_bulk,
)
from src.crud.bulk_notification import (
    create_bulk_notification as crud_create_bulk,
)
from src.crud.bulk_notification import (
    get_bulk_notification as crud_get_bulk,
)
from src.crud.notification import (
    get_notification_by_id,
    get_notifications,
)
from src.crud.notification_category import (
    create_category as crud_create_category,
)
from src.crud.notification_category import (
    delete_category as crud_delete_category,
)
from src.crud.notification_category import (
    get_categories,
)
from src.crud.notification_category import (
    update_category as crud_update_category,
)
from src.crud.notification_template import (
    create_template as crud_create_template,
)
from src.crud.notification_template import (
    delete_template as crud_delete_template,
)
from src.crud.notification_template import (
    get_template_by_code as crud_get_template_by_code,
)
from src.crud.notification_template import (
    get_templates,
)
from src.crud.notification_template import (
    update_template as crud_update_template,
)
from src.crud.organization_notification_settings import (
    get_or_create_organization_notification_settings,
    update_organization_notification_settings,
)
from src.crud.user_notification_preference import (
    get_categories_with_preferences,
    get_or_create_user_preference,
    update_user_category_preference,
    update_user_preference,
)
from src.logger.logger import Logger as logger
from src.serialisers.notification import (
    BulkNotificationResponse,
    CancelBulkNotificationResponse,
    CategoryListResponse,
    CategoryPreferencesResponse,
    CategoryResponse,
    CategoryWithPreferenceResponse,
    CreateBulkNotificationRequest,
    CreateBulkNotificationResponse,
    CreateCategoryRequest,
    CreateCategoryResponse,
    CreateTemplateRequest,
    CreateTemplateResponse,
    DeleteCategoryResponse,
    DeleteTemplateResponse,
    NotificationDetailResponse,
    NotificationListResponse,
    NotificationSettingsResponse,
    SendNotificationRequest,
    SendNotificationResponse,
    TemplateListResponse,
    TemplateResponse,
    UnsubscribeInfoResponse,
    UnsubscribeRequest,
    UnsubscribeResponse,
    UpdateCategoryPreferenceRequest,
    UpdateCategoryPreferenceResponse,
    UpdateCategoryRequest,
    UpdateCategoryResponse,
    UpdateNotificationSettingsRequest,
    UpdateNotificationSettingsResponse,
    UpdateTemplateRequest,
    UpdateTemplateResponse,
    UpdateUserPreferenceRequest,
    UpdateUserPreferenceResponse,
    UserNotificationPreferenceResponse,
)
from src.services.notifications import (
    bulk_processor,
    notification_dispatcher,
    unsubscribe_service,
)
from src.services.tasks import TaskQueue


# =============================================================================
# SDL Configuration
# =============================================================================

# Templates DSL configuration
TEMPLATE_ALLOWED_FILTERS = {"channel"}
TEMPLATE_ALLOWED_SORTS = {"created_time", "name", "code", "channel"}

# Categories DSL configuration
CATEGORY_ALLOWED_FILTERS: set[str] = set()  # No filters currently
CATEGORY_ALLOWED_SORTS = {"created_time", "name", "display_order"}

# Notifications DSL configuration
NOTIFICATION_ALLOWED_FILTERS = {"channel", "status", "user_id", "created_time"}
NOTIFICATION_ALLOWED_SORTS = {"created_time", "channel", "status"}


# =============================================================================
# Router
# =============================================================================

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _mask_email(email: str) -> str:
    """
    Mask an email address to prevent information disclosure.

    Converts "john.doe@example.com" to "j***@example.com"
    """
    if not email or "@" not in email:
        return "***"

    local_part, domain = email.rsplit("@", 1)
    if len(local_part) <= 1:
        masked_local = "*"
    else:
        masked_local = local_part[0] + "***"

    return f"{masked_local}@{domain}"


# =============================================================================
# Send Notification Endpoints
# =============================================================================


@router.post(
    "/send",
    response_model=SendNotificationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_notification(
    request: SendNotificationRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notifications:send"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Send a single notification to a user.

    Requires notifications:send permission. Notification will be processed based on user preferences
    and organization settings.

    The `user_id` must be an active user within the same organization.

    You must provide either:
    - `content` (direct message content), OR
    - `template_code` with optional `template_variables`
    """
    from src.crud.user import get_user_by_id

    # Validate content/template
    if not request.content and not request.template_code:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'content' or 'template_code' must be provided",
            detail_code="common.validation_error",
        )

    if request.channel not in ("email", "sms", "whatsapp", "in_app"):
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Channel must be 'email', 'sms', 'whatsapp', or 'in_app'",
            detail_code="common.validation_error",
        )

    organization_id = str(current_user.organization_id)

    # Verify user exists and belongs to the same organization
    target_user = await get_user_by_id(
        session=session,
        user_id=str(request.user_id),
        organization_id=organization_id,
    )

    if not target_user:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in organization",
            detail_code="user.not_found",
        )

    # Send to user by looking up their contact info
    result = await notification_dispatcher.send_to_user(
        session=session,
        user_id=str(request.user_id),
        organization_id=organization_id,
        channel=request.channel,
        content=request.content or "",
        category_code=request.category_code,
        is_urgent=request.is_urgent or False,
        template_code=request.template_code,
        template_vars=request.template_variables,
        subject=request.subject,
    )

    if not result:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to send notification - user may not have contact details for this channel",
            detail_code="notification.send_failed",
        )

    from src.serialisers.notification import NotificationResponse

    return SendNotificationResponse(
        message="Notification sent successfully",
        message_code=get_response_code("notification.sent"),
        notification=NotificationResponse(
            id=UUID(result["id"]),
            channel=result.get("channel", request.channel),
            recipient=result.get("recipient", ""),
            status=result.get("status", "sent"),
            provider_message_id=result.get("provider_message_id"),
            created_time=result.get("created_time"),
        ),
    )


# =============================================================================
# Bulk Notification Endpoints
# =============================================================================


@router.post(
    "/bulk",
    response_model=CreateBulkNotificationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bulk_notification(
    request: CreateBulkNotificationRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notifications:send"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a bulk notification.

    Requires notifications:send permission. The notification will be queued for background processing.
    Use the returned ID to check status.

    You must provide either:
    - `template_code` to use a template, OR
    - `body_text` (and optionally `body_html` for email)
    """

    if not request.template_code and not request.body_text:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'template_code' or 'body_text' must be provided",
            detail_code="common.validation_error",
        )

    if request.channel not in ("email", "sms", "whatsapp", "in_app"):
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Channel must be 'email', 'sms', 'whatsapp', or 'in_app'",
            detail_code="common.validation_error",
        )

    organization_id = str(current_user.organization_id)

    # Serialise once, in JSON mode, and use the SAME dict for the count and for
    # the persisted side-car. The processor must select its recipients from
    # exactly the filters that were counted here, and JSON mode is also what
    # makes the dict storable in the extra_data JSON column (model_dump()
    # leaves UUID objects behind, which json.dumps cannot encode).
    recipient_filters = request.recipient_filters.model_dump(mode="json")

    # Count recipients based on filters using efficient COUNT query.
    #
    # request.channel is also what is persisted as BulkNotification.channel
    # below, and the processor reads the channel back off that column - so the
    # count and the send resolve the same channel-aware verification filter
    # (email -> email_verified, sms/whatsapp -> phone_verified, in_app -> none)
    # from a single source of truth.
    total_recipients = await bulk_processor.count_recipients(
        session=session,
        org_id=organization_id,
        filters=recipient_filters,
        channel=request.channel,
    )

    if total_recipients == 0:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No recipients match the specified filters",
            detail_code="common.validation_error",
        )

    # Resolve the template now, not at send time. bulk_processor renders from
    # BulkNotification.template_id, and nothing used to set it: a template_code
    # that resolved to nothing (or to nothing on this channel) queued a job
    # that mailed an EMPTY BODY to every recipient and reported success.
    template_id = None
    if request.template_code:
        template = await crud_get_template_by_code(
            session=session,
            organization_id=organization_id,
            code=request.template_code,
            channel=request.channel,
        )
        if not template:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"No active '{request.channel}' template with code "
                    f"'{request.template_code}'"
                ),
                detail_code="notification.template_not_found",
            )
        template_id = str(template.id)

    # Create the bulk notification record
    bulk_notification = await crud_create_bulk(
        session=session,
        organization_id=organization_id,
        user_id=str(current_user.id),
        data={
            "name": request.name,
            "channel": request.channel,
            "template_id": template_id,
            "subject": request.subject,
            "body_text": request.body_text,
            "body_html": request.body_html,
            "total_recipients": total_recipients,
            "scheduled_time": request.scheduled_time,
            # The JSON side-car bulk_processor reads its recipient filters and
            # category back out of. Written as part of the insert, so a row can
            # never exist without the filters that scope it.
            "extra_data": {
                "recipient_filters": recipient_filters,
                "template_code": request.template_code,
                "category_code": request.category_code,
            },
        },
    )

    # Enqueue for background processing
    await TaskQueue.enqueue_job(
        "process_bulk_notification_task",
        str(bulk_notification.id),
        0,  # Start from batch 0
    )

    return CreateBulkNotificationResponse(
        message="Bulk notification created and queued for processing",
        message_code=get_response_code("notification.sent"),
        bulk_notification=BulkNotificationResponse(
            id=bulk_notification.id,
            name=bulk_notification.name,
            channel=bulk_notification.channel,
            status=bulk_notification.status,
            total_recipients=bulk_notification.total_recipients,
            sent_count=bulk_notification.sent_count,
            failed_count=bulk_notification.failed_count,
            created_time=bulk_notification.created_time,
            scheduled_time=bulk_notification.scheduled_time,
            started_time=bulk_notification.started_time,
            completed_time=bulk_notification.completed_time,
        ),
    )


@router.get("/bulk/{bulk_id}", response_model=BulkNotificationResponse)
async def get_bulk_notification_status(
    bulk_id: UUID,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notifications:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get the status of a bulk notification.

    Requires notifications:read permission.
    """
    organization_id = str(current_user.organization_id)

    bulk_notification = await crud_get_bulk(
        session=session,
        bulk_id=str(bulk_id),
        organization_id=organization_id,
    )

    if not bulk_notification:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bulk notification not found",
            detail_code="notification.not_found",
        )

    return BulkNotificationResponse(
        id=bulk_notification.id,
        name=bulk_notification.name,
        channel=bulk_notification.channel,
        status=bulk_notification.status,
        total_recipients=bulk_notification.total_recipients,
        sent_count=bulk_notification.sent_count,
        failed_count=bulk_notification.failed_count,
        created_time=bulk_notification.created_time,
        scheduled_time=bulk_notification.scheduled_time,
        started_time=bulk_notification.started_time,
        completed_time=bulk_notification.completed_time,
    )


@router.post("/bulk/{bulk_id}/cancel", response_model=CancelBulkNotificationResponse)
async def cancel_bulk_notification(
    bulk_id: UUID,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notifications:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Cancel a pending or processing bulk notification.

    Requires notifications:write permission. Only notifications with status 'pending' or 'processing'
    can be cancelled.
    """
    organization_id = str(current_user.organization_id)

    try:
        bulk_notification = await crud_cancel_bulk(
            session=session,
            bulk_id=str(bulk_id),
            organization_id=organization_id,
        )

        if not bulk_notification:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bulk notification not found",
                detail_code="notification.not_found",
            )

        return CancelBulkNotificationResponse(
            message="Bulk notification cancelled successfully",
            message_code=get_response_code("notification.sent"),
            bulk_notification_id=bulk_notification.id,
            status=bulk_notification.status,
        )
    except ValueError:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel bulk notification in current state",
            detail_code="common.validation_error",
        )


# =============================================================================
# Template Endpoints (Org Admin)
# =============================================================================
# NOTE: These routes MUST come before /{notification_id} to avoid route conflicts


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates(
    request: Request,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notification_templates:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    include_system: bool = Query(True, description="Include system templates"),
):
    """
    List notification templates with SDL filtering, sorting, and pagination.

    Requires notification_templates:read permission. Returns both system templates and organization-specific templates.

    **Filter examples:**
    - `filter[channel]=email` - exact match on channel

    **Sort:** `sort=created_time:desc` or `sort=name:asc`

    **Pagination:** `limit=50&offset=0`
    """
    organization_id = current_user.organization_id

    # Parse SDL parameters
    filters = parse_filters(request, allowed_fields=TEMPLATE_ALLOWED_FILTERS)
    sorts = parse_sort(
        request.query_params.get("sort"),
        allowed_fields=TEMPLATE_ALLOWED_SORTS,
        default_sort="created_time:desc",
    )
    limit, offset = get_pagination_params(request)

    templates, total = await get_templates(
        session=session,
        organization_id=organization_id,
        filters=filters,
        sorts=sorts,
        limit=limit,
        offset=offset,
    )

    items = [
        TemplateResponse(
            id=tmpl.id,
            organization_id=tmpl.organization_id,
            code=tmpl.code,
            name=tmpl.name,
            description=tmpl.description,
            channel=tmpl.channel,
            subject=tmpl.subject,
            body_text=tmpl.body_text,
            body_html=tmpl.body_html,
            variables=tmpl.variables,
            is_active=tmpl.is_active,
            created_time=tmpl.created_time,
            updated_time=tmpl.updated_time,
        )
        for tmpl in templates
    ]

    return TemplateListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/templates",
    response_model=CreateTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    request: CreateTemplateRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notification_templates:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a custom notification template.

    Requires notification_templates:write permission. Template code must be unique within the organization.
    """
    organization_id = current_user.organization_id

    if request.channel not in ("email", "sms", "whatsapp", "in_app"):
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Channel must be 'email', 'sms', 'whatsapp', or 'in_app'",
            detail_code="common.validation_error",
        )

    try:
        template = await crud_create_template(
            session=session,
            organization_id=organization_id,
            template_data=request.model_dump(),
        )

        return CreateTemplateResponse(
            message="Template created successfully",
            message_code=get_response_code("notification.template_created"),
            template=TemplateResponse(
                id=template.id,
                organization_id=template.organization_id,
                code=template.code,
                name=template.name,
                description=template.description,
                channel=template.channel,
                subject=template.subject,
                body_text=template.body_text,
                body_html=template.body_html,
                variables=template.variables,
                is_active=template.is_active,
                created_time=template.created_time,
                updated_time=template.updated_time,
            ),
        )
    except ValueError:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid template data",
            detail_code="common.validation_error",
        )


@router.put("/templates/{template_id}", response_model=UpdateTemplateResponse)
async def update_template(
    template_id: UUID,
    request: UpdateTemplateRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notification_templates:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update a custom notification template.

    Requires notification_templates:write permission. Only organization-specific templates can be updated.
    """
    organization_id = current_user.organization_id

    try:
        template = await crud_update_template(
            session=session,
            template_id=str(template_id),
            organization_id=organization_id,
            template_data=request.model_dump(exclude_unset=True),
        )

        if not template:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found",
                detail_code="notification.template_not_found",
            )

        return UpdateTemplateResponse(
            message="Template updated successfully",
            message_code=get_response_code("notification.template_updated"),
            template=TemplateResponse(
                id=template.id,
                organization_id=template.organization_id,
                code=template.code,
                name=template.name,
                description=template.description,
                channel=template.channel,
                subject=template.subject,
                body_text=template.body_text,
                body_html=template.body_html,
                variables=template.variables,
                is_active=template.is_active,
                created_time=template.created_time,
                updated_time=template.updated_time,
            ),
        )
    except ValueError:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid template update data",
            detail_code="common.validation_error",
        )


@router.delete("/templates/{template_id}", response_model=DeleteTemplateResponse)
async def delete_template(
    template_id: UUID,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notification_templates:delete"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Delete a custom notification template.

    Requires notification_templates:delete permission. Only organization-specific templates can be deleted.
    """
    organization_id = current_user.organization_id

    try:
        template = await crud_delete_template(
            session=session,
            template_id=str(template_id),
            organization_id=organization_id,
        )

        if not template:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found",
                detail_code="notification.template_not_found",
            )

        return DeleteTemplateResponse(
            message="Template deleted successfully",
            message_code=get_response_code("notification.template_deleted"),
            template_id=template.id,
        )
    except ValueError:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete template",
            detail_code="common.validation_error",
        )


# =============================================================================
# Organization Settings Endpoints (Org Admin)
# =============================================================================


@router.get("/settings", response_model=NotificationSettingsResponse)
async def get_notification_settings(
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notification_settings:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get organization notification settings.

    Requires notification_settings:read permission.
    """
    organization_id = current_user.organization_id

    settings = await get_or_create_organization_notification_settings(
        session=session,
        organization_id=organization_id,
    )

    return NotificationSettingsResponse(
        id=settings.id,
        organization_id=settings.organization_id,
        email_enabled=settings.email_enabled,
        sms_enabled=settings.sms_enabled,
        whatsapp_enabled=settings.whatsapp_enabled,
        in_app_enabled=settings.in_app_enabled,
        web_push_enabled=settings.web_push_enabled,
        sms_provider=settings.sms_provider,
        whatsapp_provider=settings.whatsapp_provider,
        notification_retention_days=settings.notification_retention_days,
        sms_rate_limit=settings.sms_rate_limit,
        whatsapp_rate_limit=settings.whatsapp_rate_limit,
        email_sender_name=settings.email_sender_name,
        sms_sender_id=settings.sms_sender_id,
        created_time=settings.created_time,
        updated_time=settings.updated_time,
    )


@router.put("/settings", response_model=UpdateNotificationSettingsResponse)
async def update_notification_settings(
    request: UpdateNotificationSettingsRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notification_settings:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update organization notification settings.

    Requires notification_settings:write permission.
    """
    organization_id = current_user.organization_id

    settings = await update_organization_notification_settings(
        session=session,
        organization_id=organization_id,
        settings_data=request.model_dump(exclude_unset=True),
    )

    return UpdateNotificationSettingsResponse(
        message="Settings updated successfully",
        message_code=get_response_code("notification.preference_updated"),
        settings=NotificationSettingsResponse(
            id=settings.id,
            organization_id=settings.organization_id,
            email_enabled=settings.email_enabled,
            sms_enabled=settings.sms_enabled,
            whatsapp_enabled=settings.whatsapp_enabled,
            in_app_enabled=settings.in_app_enabled,
            web_push_enabled=settings.web_push_enabled,
            sms_provider=settings.sms_provider,
            whatsapp_provider=settings.whatsapp_provider,
            notification_retention_days=settings.notification_retention_days,
            sms_rate_limit=settings.sms_rate_limit,
            whatsapp_rate_limit=settings.whatsapp_rate_limit,
            email_sender_name=settings.email_sender_name,
            sms_sender_id=settings.sms_sender_id,
            created_time=settings.created_time,
            updated_time=settings.updated_time,
        ),
    )


# =============================================================================
# User Preferences Endpoints (Authenticated Users)
# =============================================================================


@router.get("/preferences", response_model=UserNotificationPreferenceResponse)
async def get_user_preferences(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get current user's notification preferences.

    Returns default preferences if user hasn't set any.
    """
    organization_id = current_user.organization_id
    user_id = current_user.id

    preference = await get_or_create_user_preference(
        session=session,
        user_id=user_id,
        organization_id=organization_id,
    )

    return UserNotificationPreferenceResponse(
        id=preference.id,
        user_id=preference.user_id,
        organization_id=preference.organization_id,
        email_enabled=preference.email_enabled,
        sms_enabled=preference.sms_enabled,
        whatsapp_enabled=preference.whatsapp_enabled,
        in_app_enabled=preference.in_app_enabled,
        web_push_enabled=preference.web_push_enabled,
        quiet_hours_enabled=preference.quiet_hours_enabled,
        quiet_hours_start=(
            preference.quiet_hours_start.strftime("%H:%M")
            if preference.quiet_hours_start
            else None
        ),
        quiet_hours_end=(
            preference.quiet_hours_end.strftime("%H:%M")
            if preference.quiet_hours_end
            else None
        ),
        quiet_hours_timezone=preference.quiet_hours_timezone,
        created_time=preference.created_time,
        updated_time=preference.updated_time,
    )


@router.put("/preferences", response_model=UpdateUserPreferenceResponse)
async def update_user_preferences(
    request: UpdateUserPreferenceRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update current user's notification preferences.

    Allows users to manage their channel preferences and quiet hours.
    """
    from datetime import time as dt_time

    organization_id = current_user.organization_id
    user_id = current_user.id

    # Convert request to dict, handling time fields
    preference_data = request.model_dump(exclude_unset=True)

    # Parse time strings to time objects
    if "quiet_hours_start" in preference_data and preference_data["quiet_hours_start"]:
        try:
            parts = preference_data["quiet_hours_start"].split(":")
            preference_data["quiet_hours_start"] = dt_time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="quiet_hours_start must be in HH:MM format",
                detail_code="common.validation_error",
            )

    if "quiet_hours_end" in preference_data and preference_data["quiet_hours_end"]:
        try:
            parts = preference_data["quiet_hours_end"].split(":")
            preference_data["quiet_hours_end"] = dt_time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="quiet_hours_end must be in HH:MM format",
                detail_code="common.validation_error",
            )

    preference = await update_user_preference(
        session=session,
        user_id=user_id,
        organization_id=organization_id,
        preference_data=preference_data,
    )

    return UpdateUserPreferenceResponse(
        message="Preferences updated successfully",
        message_code=get_response_code("notification.preference_updated"),
        preferences=UserNotificationPreferenceResponse(
            id=preference.id,
            user_id=preference.user_id,
            organization_id=preference.organization_id,
            email_enabled=preference.email_enabled,
            sms_enabled=preference.sms_enabled,
            whatsapp_enabled=preference.whatsapp_enabled,
            in_app_enabled=preference.in_app_enabled,
            web_push_enabled=preference.web_push_enabled,
            quiet_hours_enabled=preference.quiet_hours_enabled,
            quiet_hours_start=(
                preference.quiet_hours_start.strftime("%H:%M")
                if preference.quiet_hours_start
                else None
            ),
            quiet_hours_end=(
                preference.quiet_hours_end.strftime("%H:%M")
                if preference.quiet_hours_end
                else None
            ),
            quiet_hours_timezone=preference.quiet_hours_timezone,
            created_time=preference.created_time,
            updated_time=preference.updated_time,
        ),
    )


@router.get("/preferences/categories", response_model=CategoryPreferencesResponse)
async def get_category_preferences(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    List all notification categories with user's preferences.

    Returns categories ordered by display_order, with the user's current
    preference settings for each channel.
    """
    organization_id = current_user.organization_id
    user_id = current_user.id

    categories_with_prefs = await get_categories_with_preferences(
        session=session,
        user_id=user_id,
        organization_id=organization_id,
    )

    items = []
    for item in categories_with_prefs:
        cat = item["category"]
        items.append(
            CategoryWithPreferenceResponse(
                category=CategoryResponse(
                    id=cat.id,
                    organization_id=cat.organization_id,
                    code=cat.code,
                    name=cat.name,
                    description=cat.description,
                    default_enabled=cat.default_enabled,
                    user_configurable=cat.user_configurable,
                    display_order=cat.display_order,
                    created_time=cat.created_time,
                ),
                email_enabled=item["email_enabled"],
                sms_enabled=item["sms_enabled"],
                whatsapp_enabled=item["whatsapp_enabled"],
                in_app_enabled=item["in_app_enabled"],
                web_push_enabled=item["web_push_enabled"],
            )
        )

    return CategoryPreferencesResponse(items=items)


@router.put(
    "/preferences/categories/{category_id}",
    response_model=UpdateCategoryPreferenceResponse,
)
async def update_category_preference(
    category_id: UUID,
    request: UpdateCategoryPreferenceRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update user's preference for a specific notification category.

    Only works for categories where user_configurable=True.
    """
    organization_id = current_user.organization_id
    user_id = current_user.id

    try:
        preference = await update_user_category_preference(
            session=session,
            user_id=user_id,
            category_id=str(category_id),
            organization_id=organization_id,
            preference_data=request.model_dump(exclude_unset=True),
        )

        return UpdateCategoryPreferenceResponse(
            message="Category preference updated successfully",
            message_code=get_response_code("notification.preference_updated"),
            category_id=preference.category_id,
            email_enabled=preference.email_enabled,
            sms_enabled=preference.sms_enabled,
            whatsapp_enabled=preference.whatsapp_enabled,
            in_app_enabled=preference.in_app_enabled,
            web_push_enabled=preference.web_push_enabled,
        )
    except ValueError:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid category preference data",
            detail_code="common.validation_error",
        )


# =============================================================================
# Category Endpoints (Org Admin)
# =============================================================================


@router.get("/categories", response_model=CategoryListResponse)
async def list_categories(
    request: Request,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notification_categories:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    include_system: bool = Query(True, description="Include system categories"),
):
    """
    List notification categories with SDL sorting and pagination.

    Requires notification_categories:read permission. Returns both system and organization-specific categories.

    **Sort:** `sort=display_order:asc` or `sort=name:asc`

    **Pagination:** `limit=50&offset=0`
    """
    organization_id = current_user.organization_id

    # Parse SDL parameters
    sorts = parse_sort(
        request.query_params.get("sort"),
        allowed_fields=CATEGORY_ALLOWED_SORTS,
        default_sort="display_order:asc",
    )
    limit, offset = get_pagination_params(request)

    categories, total = await get_categories(
        session=session,
        organization_id=organization_id,
        sorts=sorts,
        limit=limit,
        offset=offset,
    )

    items = [
        CategoryResponse(
            id=cat.id,
            organization_id=cat.organization_id,
            code=cat.code,
            name=cat.name,
            description=cat.description,
            default_enabled=cat.default_enabled,
            user_configurable=cat.user_configurable,
            display_order=cat.display_order,
            created_time=cat.created_time,
        )
        for cat in categories
    ]

    return CategoryListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/categories",
    response_model=CreateCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    request: CreateCategoryRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notification_categories:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a custom notification category.

    Requires notification_categories:write permission. Category code must be unique within the organization.
    """
    organization_id = current_user.organization_id

    try:
        category = await crud_create_category(
            session=session,
            organization_id=organization_id,
            category_data=request.model_dump(),
        )

        return CreateCategoryResponse(
            message="Category created successfully",
            message_code=get_response_code("notification.template_created"),
            category=CategoryResponse(
                id=category.id,
                organization_id=category.organization_id,
                code=category.code,
                name=category.name,
                description=category.description,
                default_enabled=category.default_enabled,
                user_configurable=category.user_configurable,
                display_order=category.display_order,
                created_time=category.created_time,
            ),
        )
    except ValueError:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid category data",
            detail_code="common.validation_error",
        )


@router.put("/categories/{category_id}", response_model=UpdateCategoryResponse)
async def update_category(
    category_id: UUID,
    request: UpdateCategoryRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notification_categories:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update a custom notification category.

    Requires notification_categories:write permission. Only organization-specific categories can be updated.
    """
    organization_id = current_user.organization_id

    try:
        category = await crud_update_category(
            session=session,
            category_id=str(category_id),
            organization_id=organization_id,
            category_data=request.model_dump(exclude_unset=True),
        )

        if not category:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
                detail_code="common.not_found",
            )

        return UpdateCategoryResponse(
            message="Category updated successfully",
            message_code=get_response_code("notification.template_updated"),
            category=CategoryResponse(
                id=category.id,
                organization_id=category.organization_id,
                code=category.code,
                name=category.name,
                description=category.description,
                default_enabled=category.default_enabled,
                user_configurable=category.user_configurable,
                display_order=category.display_order,
                created_time=category.created_time,
            ),
        )
    except ValueError:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid category update data",
            detail_code="common.validation_error",
        )


@router.delete("/categories/{category_id}", response_model=DeleteCategoryResponse)
async def delete_category(
    category_id: UUID,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notification_categories:delete"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Delete a custom notification category.

    Requires notification_categories:delete permission. Only organization-specific categories can be deleted.
    """
    organization_id = current_user.organization_id

    try:
        category = await crud_delete_category(
            session=session,
            category_id=str(category_id),
            organization_id=organization_id,
        )

        if not category:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
                detail_code="common.not_found",
            )

        return DeleteCategoryResponse(
            message="Category deleted successfully",
            message_code=get_response_code("notification.template_deleted"),
            category_id=category.id,
        )
    except ValueError:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete category",
            detail_code="common.validation_error",
        )


# =============================================================================
# Unsubscribe Endpoints (Public, Token-Based)
# =============================================================================


@router.get("/unsubscribe", response_model=UnsubscribeInfoResponse)
async def get_unsubscribe_info(
    session: Annotated[AsyncSession, Depends(get_session)],
    token: str = Query(..., description="Unsubscribe token from email link"),
):
    """
    Get unsubscribe information for rendering the unsubscribe page.

    This endpoint is public and uses a signed token for authentication.
    Returns information about what the user is unsubscribing from.
    """
    from sqlalchemy import select

    from src.models.notification_category import NotificationCategory
    from src.models.organization import Organization
    from src.models.user import User

    # Validate token
    payload = unsubscribe_service.validate_token(token)
    if not payload:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired unsubscribe token",
            detail_code="auth.invalid_token",
        )

    user_id = payload["user_id"]
    organization_id = payload["organization_id"]
    category_code = payload.get("category_code")
    channel = payload.get("channel", "email")

    # Get user info - include organization_id filter for tenant isolation
    user_result = await session.execute(
        select(User).where(
            User.id == UUID(user_id),
            User.organization_id == UUID(organization_id),
            User.deleted_time.is_(None),
        )
    )
    user = user_result.scalar_one_or_none()

    if not user:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            detail_code="user.not_found",
        )

    # Get organization info
    org_result = await session.execute(
        select(Organization).where(
            Organization.id == UUID(organization_id),
            Organization.deleted_time.is_(None),
        )
    )
    org = org_result.scalar_one_or_none()

    if not org:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
            detail_code="organization.not_found",
        )

    # Get category name if provided - include organization scope for tenant isolation
    category_name = None
    if category_code:
        cat_result = await session.execute(
            select(NotificationCategory).where(
                NotificationCategory.code == category_code,
                NotificationCategory.organization_id == UUID(organization_id),
                NotificationCategory.deleted_time.is_(None),
            )
        )
        category = cat_result.scalar_one_or_none()
        if category:
            category_name = category.name

    # Check if already unsubscribed
    user_pref = await get_or_create_user_preference(
        session=session,
        user_id=str(user.id),
        organization_id=organization_id,
    )

    is_unsubscribed = False
    if channel == "email":
        is_unsubscribed = not user_pref.email_enabled
    elif channel == "sms":
        is_unsubscribed = not user_pref.sms_enabled
    elif channel == "whatsapp":
        is_unsubscribed = not user_pref.whatsapp_enabled

    # Mask email to prevent information disclosure
    masked_email = _mask_email(user.email or "")

    return UnsubscribeInfoResponse(
        user_email=masked_email,
        organization_name=org.name,
        category_name=category_name,
        channel=channel,
        is_already_unsubscribed=is_unsubscribed,
    )


async def _apply_unsubscribe(session: AsyncSession, payload: dict[str, Any]) -> str:
    """Turn an already-validated unsubscribe token payload into a preference change.

    Shared by the human unsubscribe page (POST /unsubscribe) and the RFC 8058
    one-click endpoint (POST /unsubscribe/one-click) so the two can never drift
    into opting a user out of different things.

    Returns the channel that was disabled.
    """
    user_id = payload["user_id"]
    organization_id = payload["organization_id"]
    category_code = payload.get("category_code")
    channel = payload.get("channel", "email")

    # Build preference update data based on channel
    preference_data = {}
    if channel == "email":
        preference_data["email_enabled"] = False
    elif channel == "sms":
        preference_data["sms_enabled"] = False
    elif channel == "whatsapp":
        preference_data["whatsapp_enabled"] = False

    # If there's a category code, update category-specific preference instead
    if category_code:
        # Update category preference
        from src.crud.notification_category import get_category_by_code

        category = await get_category_by_code(
            session=session,
            code=category_code,
            organization_id=organization_id,
        )

        if category and category.user_configurable:
            await update_user_category_preference(
                session=session,
                user_id=user_id,
                category_id=str(category.id),
                organization_id=organization_id,
                preference_data=preference_data,
            )
        else:
            # Fall back to updating global channel preference
            await update_user_preference(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                preference_data=preference_data,
            )
    else:
        # Update global channel preference
        await update_user_preference(
            session=session,
            user_id=user_id,
            organization_id=organization_id,
            preference_data=preference_data,
        )

    return channel


@router.post("/unsubscribe", response_model=UnsubscribeResponse)
async def process_unsubscribe(
    request: UnsubscribeRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Process an unsubscribe request.

    This endpoint is public and uses a signed token for authentication.
    Updates user preferences to disable the specified channel/category.
    """
    # Validate token
    payload = unsubscribe_service.validate_token(request.token)
    if not payload:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired unsubscribe token",
            detail_code="auth.invalid_token",
        )

    channel = await _apply_unsubscribe(session, payload)

    return UnsubscribeResponse(
        message=f"Successfully unsubscribed from {channel} notifications",
        message_code=get_response_code("notification.preference_updated"),
        success=True,
    )


@router.post(
    "/unsubscribe/one-click",
    response_model=UnsubscribeResponse,
    status_code=status.HTTP_200_OK,
)
async def one_click_unsubscribe(
    session: Annotated[AsyncSession, Depends(get_session)],
    token: str = Query(..., description="Unsubscribe token from the email header"),
):
    """RFC 8058 one-click unsubscribe, POSTed by the mailbox provider.

    This is the URL advertised in ``List-Unsubscribe`` alongside
    ``List-Unsubscribe-Post: List-Unsubscribe=One-Click``. Gmail and Yahoo
    require it on bulk mail and they grade it: a one-click unsubscribe that
    fails counts against sending-domain reputation, so the contract here is
    narrow and deliberate.

    * The token is read from the QUERY STRING. The provider owns the request
      body (it posts ``List-Unsubscribe=One-Click`` as form data), so nothing
      here reads or validates the body.
    * It ALWAYS answers 200, including for a token that is expired, forged or
      malformed. A provider does not follow redirects, does not read error
      bodies and does not show the recipient an error - it records a failed
      unsubscribe against the sending domain. There is also nothing for an
      unauthenticated caller to learn from the difference, and a token that
      does not validate cannot identify anyone to opt out anyway.
    * Disabling a channel twice is the same end state, so no extra idempotency
      guard is needed.

    Rate limiting: this route is public and writes to the database on a valid
    token. It carries exactly the same protection as the other public
    /unsubscribe routes - the global per-IP ``RATE_LIMIT_DEFAULT`` applied to
    every route by ``SlowAPIMiddleware`` (main.py). No per-route override, so
    a provider retrying an unsubscribe is never treated more harshly than a
    user clicking the footer link.
    """
    payload = unsubscribe_service.validate_token(token)
    channel = "email"
    if payload:
        channel = await _apply_unsubscribe(session, payload)
    else:
        # Deliberately not surfaced to the caller (see docstring).
        logger.info("One-click unsubscribe presented an invalid or expired token")

    return UnsubscribeResponse(
        message=f"Successfully unsubscribed from {channel} notifications",
        message_code=get_response_code("notification.preference_updated"),
        success=True,
    )


# =============================================================================
# Notification History Endpoints
# =============================================================================
# NOTE: These routes MUST come AFTER specific routes like /templates, /categories,
# /settings, /preferences to avoid route conflicts with /{notification_id}


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    request: Request,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notifications:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    List notification history for the organization with SDL filtering, sorting, and pagination.

    Requires notifications:read permission. Results are ordered by creation time (newest first).

    **Filter examples:**
    - `filter[channel]=email` - exact match on channel
    - `filter[status]=sent` - filter by status
    - `filter[user_id]=<uuid>` - filter by recipient user ID
    - `filter[created_time][gte]=2024-01-01T00:00:00Z` - date range start
    - `filter[created_time][lte]=2024-12-31T23:59:59Z` - date range end

    **Sort:** `sort=created_time:desc` or `sort=status:asc`

    **Pagination:** `limit=50&offset=0`
    """
    organization_id = current_user.organization_id

    # Parse SDL parameters
    filters = parse_filters(request, allowed_fields=NOTIFICATION_ALLOWED_FILTERS)
    sorts = parse_sort(
        request.query_params.get("sort"),
        allowed_fields=NOTIFICATION_ALLOWED_SORTS,
        default_sort="created_time:desc",
    )
    limit, offset = get_pagination_params(request)

    notifications, total = await get_notifications(
        session=session,
        organization_id=organization_id,
        filters=filters,
        sorts=sorts,
        limit=limit,
        offset=offset,
    )

    items = [
        NotificationDetailResponse(
            id=notif.id,
            channel=notif.channel,
            provider=notif.provider,
            recipient=notif.recipient,
            user_id=notif.user_id,
            template_id=notif.template_id,
            subject=notif.subject,
            body_preview=notif.body_preview,
            status=notif.status,
            provider_message_id=notif.provider_message_id,
            error_message=notif.error_message,
            retry_count=notif.retry_count or 0,
            bulk_notification_id=notif.bulk_notification_id,
            metadata=notif.extra_data,
            created_time=notif.created_time,
            updated_time=notif.updated_time,
        )
        for notif in notifications
    ]

    return NotificationListResponse(
        items=items, total=total, limit=limit, offset=offset
    )


@router.get("/{notification_id}", response_model=NotificationDetailResponse)
async def get_notification(
    notification_id: UUID,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notifications:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get details of a specific notification.

    Requires notifications:read permission.
    """
    organization_id = current_user.organization_id

    notification = await get_notification_by_id(
        session=session,
        notification_id=str(notification_id),
        organization_id=organization_id,
    )

    if not notification:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
            detail_code="notification.not_found",
        )

    return NotificationDetailResponse(
        id=notification.id,
        channel=notification.channel,
        provider=notification.provider,
        recipient=notification.recipient,
        user_id=notification.user_id,
        template_id=notification.template_id,
        subject=notification.subject,
        body_preview=notification.body_preview,
        status=notification.status,
        provider_message_id=notification.provider_message_id,
        error_message=notification.error_message,
        retry_count=notification.retry_count or 0,
        bulk_notification_id=notification.bulk_notification_id,
        metadata=notification.extra_data,
        created_time=notification.created_time,
        updated_time=notification.updated_time,
    )
