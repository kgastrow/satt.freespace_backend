"""
In-app notification API endpoints.
Provides endpoints for users to manage their in-app notifications.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_user,
    get_session,
)
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.crud.user_notification import (
    bulk_dismiss,
    get_unread_count,
    get_user_notification_by_id,
    get_user_notifications,
    mark_all_as_read,
    mark_as_read,
)
from src.serialisers.user_notification import (
    DismissNotificationsRequest,
    DismissResponse,
    InAppNotificationListResponse,
    InAppNotificationResponse,
    MarkReadResponse,
    UnreadCountResponse,
)


# =============================================================================
# Router
# =============================================================================

router = APIRouter(prefix="/notifications/in-app", tags=["in-app-notifications"])


# =============================================================================
# List Notifications
# =============================================================================


@router.get("", response_model=InAppNotificationListResponse)
async def list_in_app_notifications(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    unread_only: bool = Query(False, description="Only return unread notifications"),
    limit: int = Query(20, ge=1, le=100, description="Number of items per page"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
):
    """
    List in-app notifications for the current user.

    Returns notifications ordered by creation time (newest first).
    Users can only access their own notifications.
    """
    organization_id = str(current_user.organization_id)
    user_id = str(current_user.id)

    notifications, total = await get_user_notifications(
        session=session,
        organization_id=organization_id,
        user_id=user_id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )

    items = [
        InAppNotificationResponse(
            id=notif.id,
            title=notif.title,
            body=notif.body,
            link=notif.link,
            category_id=notif.category_id,
            read_time=notif.read_time,
            created_time=notif.created_time,
        )
        for notif in notifications
    ]

    return InAppNotificationListResponse(
        items=items, total=total, limit=limit, offset=offset
    )


# =============================================================================
# Unread Count
# =============================================================================


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_notification_count(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get the count of unread in-app notifications for the current user.

    This endpoint is optimized for frequent polling to update the notification badge.
    """
    organization_id = str(current_user.organization_id)
    user_id = str(current_user.id)

    count = await get_unread_count(
        session=session,
        organization_id=organization_id,
        user_id=user_id,
    )

    return UnreadCountResponse(unread_count=count)


# =============================================================================
# Mark as Read
# =============================================================================


@router.post("/{notification_id}/read", response_model=MarkReadResponse)
async def mark_notification_as_read(
    notification_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Mark a single notification as read.

    Users can only mark their own notifications as read.
    If the notification is already read, this is a no-op and returns success.
    """
    organization_id = str(current_user.organization_id)
    user_id = str(current_user.id)

    notification = await mark_as_read(
        session=session,
        notification_id=str(notification_id),
        organization_id=organization_id,
        user_id=user_id,
    )

    if not notification:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
            detail_code="user_notification.not_found",
        )

    return MarkReadResponse(
        message="Notification marked as read",
        message_code=get_response_code("user_notification.marked_read"),
        count=1,
    )


@router.post("/mark-all-read", response_model=MarkReadResponse)
async def mark_all_notifications_as_read(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Mark all unread notifications as read for the current user.

    This is useful for a "Mark all as read" button in the notification panel.
    """
    organization_id = str(current_user.organization_id)
    user_id = str(current_user.id)

    count = await mark_all_as_read(
        session=session,
        organization_id=organization_id,
        user_id=user_id,
    )

    return MarkReadResponse(
        message="All notifications marked as read",
        message_code=get_response_code("user_notification.all_marked_read"),
        count=count,
    )


# =============================================================================
# Dismiss Notifications
# =============================================================================


@router.post("/dismiss", response_model=DismissResponse)
async def dismiss_notifications(
    request: DismissNotificationsRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Dismiss (soft delete) multiple notifications.

    Dismissed notifications will no longer appear in the notification list.
    Users can only dismiss their own notifications.
    """
    organization_id = str(current_user.organization_id)
    user_id = str(current_user.id)

    notification_ids = [str(nid) for nid in request.notification_ids]

    count = await bulk_dismiss(
        session=session,
        organization_id=organization_id,
        user_id=user_id,
        notification_ids=notification_ids,
    )

    return DismissResponse(
        message="Notifications dismissed",
        message_code=get_response_code("user_notification.deleted"),
        count=count,
    )


# =============================================================================
# Get Single Notification
# =============================================================================


@router.get("/{notification_id}", response_model=InAppNotificationResponse)
async def get_in_app_notification(
    notification_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get a single in-app notification by ID.

    Users can only access their own notifications.
    """
    organization_id = str(current_user.organization_id)
    user_id = str(current_user.id)

    notification = await get_user_notification_by_id(
        session=session,
        notification_id=str(notification_id),
        organization_id=organization_id,
        user_id=user_id,
    )

    if not notification:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
            detail_code="user_notification.not_found",
        )

    return InAppNotificationResponse(
        id=notification.id,
        title=notification.title,
        body=notification.body,
        link=notification.link,
        category_id=notification.category_id,
        read_time=notification.read_time,
        created_time=notification.created_time,
    )
