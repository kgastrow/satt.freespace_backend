"""
Announcement API endpoints.

Supports organization-scoped and platform-wide announcements.
- Organization owners/admins can create announcements for their organization
- Super admins can create announcements per organization or platform-wide
- All authenticated users can dismiss announcements and view active announcements
"""

import traceback
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from src.api.deps import (
    CurrentUser,
    get_current_user,
    get_session,
    require_permission,
)
from src.core.exceptions import create_http_exception
from src.crud.announcement import (
    create_announcement,
    get_active_announcements,
    get_announcement_by_id,
    get_announcements,
    soft_delete_announcement,
    update_announcement,
)
from src.crud.announcement_dismissal import create_dismissal
from src.logger.logger import Logger
from src.serialisers.announcement import (
    ActiveAnnouncementsResponse,
    AnnouncementCreate,
    AnnouncementListResponse,
    AnnouncementResponse,
    AnnouncementUpdate,
    DismissAnnouncementResponse,
)
from src.services.websocket.broadcaster import message_broadcaster


router = APIRouter(prefix="/announcements", tags=["announcements"])


@router.get("/active", response_model=ActiveAnnouncementsResponse)
async def get_active_announcements_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get active announcements for the current user.

    Returns org-specific and platform-wide announcements that are:
    - Currently active (within start_time and end_time)
    - Not soft-deleted
    - Not dismissed by the user (unless non-dismissible)

    Sorted by: non-dismissible first, priority, then created_time.
    """
    announcements = await get_active_announcements(
        session=session,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        exclude_dismissed=True,
    )

    return ActiveAnnouncementsResponse(
        announcements=[
            AnnouncementResponse.from_orm_announcement(ann) for ann in announcements
        ]
    )


@router.post(
    "", response_model=AnnouncementResponse, status_code=status.HTTP_201_CREATED
)
async def create_announcement_endpoint(
    http_request: Request,
    request: AnnouncementCreate,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("announcements:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a new announcement.

    Requires announcements:write permission.
    Super admins can create platform-wide announcements by setting is_platform_wide=True.
    Regular admins can only create org-specific announcements.
    """
    # Determine organization_id based on platform-wide flag and user permissions
    organization_id: Optional[str] = None
    if request.is_platform_wide:
        # Only super admins can create platform-wide announcements
        if not current_user.is_admin:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super admins can create platform-wide announcements",
                detail_code="announcement.platform_wide_forbidden",
            )
        organization_id = None
    else:
        # Regular org-scoped announcement
        organization_id = current_user.organization_id

    try:
        announcement_data = request.model_dump(exclude={"is_platform_wide"})
        announcement = await create_announcement(
            session=session,
            announcement_data=announcement_data,
            organization_id=organization_id,
            created_by_id=current_user.id,
        )
        response = AnnouncementResponse.from_orm_announcement(announcement)

        # Broadcast announcement via WebSocket
        payload = response.model_dump(mode="json")
        if announcement.organization_id:
            # Org-specific announcement - send to organization
            await message_broadcaster.send_to_organization(
                organization_id=announcement.organization_id,
                message_type="announcement_created",
                payload=payload,
            )
        else:
            # Platform-wide announcement - send to all users
            await message_broadcaster.send_to_platform(
                message_type="announcement_created",
                payload=payload,
            )

        return response
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.errors(),
        )
    except IntegrityError as e:
        Logger.warning(f"Integrity error creating announcement: {e}")
        raise create_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            detail="Announcement could not be created due to a conflict",
            detail_code="announcement.conflict",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error creating announcement: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while creating announcement",
            detail_code="announcement.database_error",
        )


@router.get("/{announcement_id}", response_model=AnnouncementResponse)
async def get_announcement_endpoint(
    announcement_id: str,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("announcements:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get a specific announcement by ID.

    Requires announcements:read permission.
    Users can see announcements from their organization or platform-wide announcements.
    Super admins can see all announcements.
    """
    # Super admins can see all announcements
    org_id_filter = None if current_user.is_admin else current_user.organization_id

    announcement = await get_announcement_by_id(
        session=session,
        announcement_id=announcement_id,
        organization_id=org_id_filter,
    )

    if not announcement:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found",
            detail_code="announcement.not_found",
        )

    return AnnouncementResponse.from_orm_announcement(announcement)


@router.get("", response_model=AnnouncementListResponse)
async def list_announcements_endpoint(
    current_user: Annotated[
        CurrentUser, Depends(require_permission("announcements:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    include_platform_wide: bool = Query(default=True),
):
    """
    List all announcements for the organization (admin view).

    Requires announcements:read permission.
    Returns paginated list with optional platform-wide announcements.
    Super admins can see all announcements across all organizations.
    """
    # Super admins can see all announcements
    org_id_filter = None if current_user.is_admin else current_user.organization_id

    announcements, total = await get_announcements(
        session=session,
        organization_id=org_id_filter,
        include_platform_wide=include_platform_wide,
        limit=limit,
        offset=offset,
    )

    return AnnouncementListResponse(
        items=[
            AnnouncementResponse.from_orm_announcement(ann) for ann in announcements
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put("/{announcement_id}", response_model=AnnouncementResponse)
async def update_announcement_endpoint(
    announcement_id: str,
    request: AnnouncementUpdate,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("announcements:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update an announcement.

    Requires announcements:write permission.
    Users can only update announcements from their organization.
    Super admins can update all announcements.
    """
    # Super admins can update all announcements
    org_id_filter = None if current_user.is_admin else current_user.organization_id

    # Only include fields that were explicitly provided in the request
    # Using exclude_unset=True allows null values to clear fields
    announcement_data = request.model_dump(exclude_unset=True)

    if not announcement_data:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update",
            detail_code="announcement.no_fields_provided",
        )

    announcement = await update_announcement(
        session=session,
        announcement_id=announcement_id,
        organization_id=org_id_filter,
        announcement_data=announcement_data,
    )

    if not announcement:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found or unauthorized",
            detail_code="announcement.not_found",
        )

    response = AnnouncementResponse.from_orm_announcement(announcement)

    # Broadcast announcement update via WebSocket
    payload = response.model_dump(mode="json")
    if announcement.organization_id:
        # Org-specific announcement - send to organization
        await message_broadcaster.send_to_organization(
            organization_id=announcement.organization_id,
            message_type="announcement_updated",
            payload=payload,
        )
    else:
        # Platform-wide announcement - send to all users
        await message_broadcaster.send_to_platform(
            message_type="announcement_updated",
            payload=payload,
        )

    return response


@router.delete("/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_announcement_endpoint(
    announcement_id: str,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("announcements:delete"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Soft delete an announcement.

    Requires announcements:delete permission.
    Users can only delete announcements from their organization.
    Super admins can delete all announcements.
    """
    # Super admins can delete all announcements
    org_id_filter = None if current_user.is_admin else current_user.organization_id

    announcement = await soft_delete_announcement(
        session=session,
        announcement_id=announcement_id,
        organization_id=org_id_filter,
    )

    if not announcement:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found or unauthorized",
            detail_code="announcement.not_found",
        )

    # Broadcast announcement deletion via WebSocket
    payload = {"id": str(announcement.id)}
    if announcement.organization_id:
        # Org-specific announcement - send to organization
        await message_broadcaster.send_to_organization(
            organization_id=announcement.organization_id,
            message_type="announcement_deleted",
            payload=payload,
        )
    else:
        # Platform-wide announcement - send to all users
        await message_broadcaster.send_to_platform(
            message_type="announcement_deleted",
            payload=payload,
        )

    return None


@router.post("/{announcement_id}/dismiss", response_model=DismissAnnouncementResponse)
async def dismiss_announcement_endpoint(
    http_request: Request,
    announcement_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Dismiss an announcement for the current user.

    Any authenticated user can dismiss announcements.
    This creates a dismissal record that persists across sessions.
    """
    # Verify announcement exists and is accessible to user
    org_id_filter = None if current_user.is_admin else current_user.organization_id
    announcement = await get_announcement_by_id(
        session=session,
        announcement_id=announcement_id,
        organization_id=org_id_filter,
    )

    if not announcement:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found",
            detail_code="announcement.not_found",
        )

    # Check if announcement is dismissible
    if not announcement.is_dismissible:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This announcement is not dismissible",
            detail_code="announcement.not_dismissible",
        )

    try:
        await create_dismissal(
            session=session,
            announcement_id=announcement_id,
            user_id=current_user.id,
        )
        return DismissAnnouncementResponse(
            message="Announcement dismissed successfully",
            message_code="announcement.dismissed",
            announcement_id=announcement.id,
        )
    except ValueError as e:
        # User already dismissed this announcement
        raise create_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
            detail_code="announcement.already_dismissed",
        )
    except IntegrityError as e:
        Logger.warning(f"Integrity error dismissing announcement: {e}")
        raise create_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            detail="Announcement already dismissed",
            detail_code="announcement.already_dismissed",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error dismissing announcement: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while dismissing announcement",
            detail_code="announcement.database_error",
        )
