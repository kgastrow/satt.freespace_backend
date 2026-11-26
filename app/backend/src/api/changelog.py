"""
Changelog API endpoints.

Supports organization-scoped and platform-wide changelog entries.
- Admins with changelog:write can create/update/delete entries
- All authenticated users can view published entries and mark them as viewed
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
from src.crud.changelog import (
    create_changelog,
    get_changelog_by_id,
    get_unread_count,
    get_viewed_changelog_ids,
    list_changelogs,
    mark_all_as_viewed,
    mark_as_viewed,
    soft_delete_changelog,
    update_changelog,
)
from src.logger.logger import Logger
from src.serialisers.changelog import (
    ChangelogListResponse,
    ChangelogResponse,
    CreateChangelogRequest,
    UnreadCountResponse,
    UpdateChangelogRequest,
)


router = APIRouter(prefix="/changelogs", tags=["changelogs"])


# -- User endpoints --


@router.get("/published", response_model=ChangelogListResponse)
async def get_published_changelogs(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    category: Optional[str] = Query(default=None),
):
    """
    Get published changelog entries for the current user's org + platform-wide.
    Includes is_viewed flag per entry.
    """
    changelogs, total = await list_changelogs(
        session=session,
        organization_id=current_user.organization_id,
        published_only=True,
        category=category,
        limit=limit,
        offset=offset,
    )

    viewed_ids = await get_viewed_changelog_ids(
        session=session, user_id=current_user.id
    )
    unread = await get_unread_count(
        session=session,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
    )

    items = [
        ChangelogResponse.from_orm_changelog(cl, is_viewed=str(cl.id) in viewed_ids)
        for cl in changelogs
    ]

    return ChangelogListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        unread_count=unread,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get count of unread published changelog entries for the current user."""
    count = await get_unread_count(
        session=session,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    return UnreadCountResponse(count=count)


@router.post("/{changelog_id}/view", status_code=status.HTTP_200_OK)
async def mark_changelog_viewed(
    changelog_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Mark a single changelog entry as viewed by the current user."""
    changelog = await get_changelog_by_id(
        session=session,
        changelog_id=changelog_id,
        organization_id=current_user.organization_id,
    )
    if not changelog:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Changelog entry not found",
            detail_code="changelog.not_found",
        )

    await mark_as_viewed(
        session=session,
        changelog_id=changelog_id,
        user_id=current_user.id,
    )
    return {"message": "Marked as viewed", "message_code": "changelog.viewed"}


@router.post("/mark-all-viewed", status_code=status.HTTP_200_OK)
async def mark_all_changelogs_viewed(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Mark all published changelog entries as viewed for the current user."""
    count = await mark_all_as_viewed(
        session=session,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    return {
        "message": f"Marked {count} entries as viewed",
        "message_code": "changelog.all_viewed",
        "count": count,
    }


# -- Admin endpoints --


@router.post("", response_model=ChangelogResponse, status_code=status.HTTP_201_CREATED)
async def create_changelog_endpoint(
    http_request: Request,
    request: CreateChangelogRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("changelog:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a new changelog entry.
    Requires changelog:write permission.
    Super admins can create platform-wide entries by setting is_platform_wide=True.
    """
    organization_id: Optional[str] = None
    if request.is_platform_wide:
        if not current_user.is_admin:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super admins can create platform-wide changelog entries",
                detail_code="changelog.platform_wide_forbidden",
            )
        organization_id = None
    else:
        organization_id = current_user.organization_id

    try:
        changelog_data = request.model_dump(exclude={"is_platform_wide"})
        changelog = await create_changelog(
            session=session,
            changelog_data=changelog_data,
            organization_id=organization_id,
            created_by_id=current_user.id,
        )
        return ChangelogResponse.from_orm_changelog(changelog)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.errors(),
        )
    except IntegrityError as e:
        Logger.warning(f"Integrity error creating changelog: {e}")
        raise create_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            detail="Changelog entry could not be created due to a conflict",
            detail_code="changelog.conflict",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error creating changelog: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while creating changelog entry",
            detail_code="changelog.database_error",
        )


@router.put("/{changelog_id}", response_model=ChangelogResponse)
async def update_changelog_endpoint(
    changelog_id: str,
    request: UpdateChangelogRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("changelog:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update a changelog entry.
    Requires changelog:write permission.
    """
    org_id_filter = None if current_user.is_admin else current_user.organization_id

    changelog_data = request.model_dump(exclude_unset=True)
    if not changelog_data:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update",
            detail_code="changelog.no_fields_provided",
        )

    changelog = await update_changelog(
        session=session,
        changelog_id=changelog_id,
        organization_id=org_id_filter,
        changelog_data=changelog_data,
    )

    if not changelog:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Changelog entry not found or unauthorized",
            detail_code="changelog.not_found",
        )

    return ChangelogResponse.from_orm_changelog(changelog)


@router.delete("/{changelog_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_changelog_endpoint(
    changelog_id: str,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("changelog:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Soft delete a changelog entry.
    Requires changelog:write permission.
    """
    org_id_filter = None if current_user.is_admin else current_user.organization_id

    changelog = await soft_delete_changelog(
        session=session,
        changelog_id=changelog_id,
        organization_id=org_id_filter,
    )

    if not changelog:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Changelog entry not found or unauthorized",
            detail_code="changelog.not_found",
        )

    return None


@router.get("", response_model=ChangelogListResponse)
async def list_changelogs_endpoint(
    current_user: Annotated[
        CurrentUser, Depends(require_permission("changelog:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    category: Optional[str] = Query(default=None),
):
    """
    List all changelog entries (admin view, including drafts).
    Requires changelog:write permission.
    """
    org_id_filter = None if current_user.is_admin else current_user.organization_id

    changelogs, total = await list_changelogs(
        session=session,
        organization_id=org_id_filter,
        published_only=False,
        category=category,
        limit=limit,
        offset=offset,
    )

    return ChangelogListResponse(
        items=[ChangelogResponse.from_orm_changelog(cl) for cl in changelogs],
        total=total,
        limit=limit,
        offset=offset,
    )
