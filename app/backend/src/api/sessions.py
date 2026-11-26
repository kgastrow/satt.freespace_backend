"""
Session Management API endpoints.
Allows users to view and manage their active sessions.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_user, get_session
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.crud.refresh_token import (
    delete_other_sessions,
    delete_session,
    get_active_sessions_for_user,
    get_session_by_id,
)
from src.serialisers.session import (
    RevokeOtherSessionsResponse,
    RevokeSessionResponse,
    SessionDeviceInfo,
    SessionListResponse,
    SessionLocation,
    SessionResponse,
)
from src.services.cache import cache_service
from src.services.session_metadata import mask_ip_address, parse_device_info


router = APIRouter(prefix="/sessions", tags=["sessions"])


def _build_session_response(
    refresh_token,
    current_token: str | None = None,
) -> SessionResponse:
    """
    Build a SessionResponse from a RefreshToken object.

    Args:
        refresh_token: RefreshToken model instance
        current_token: Optional current token string to determine is_current

    Returns:
        SessionResponse with parsed device info and masked IP
    """
    # Parse device info from user-agent
    device_info = parse_device_info(refresh_token.user_agent)

    return SessionResponse(
        id=refresh_token.id,
        device=SessionDeviceInfo(
            device_type=device_info["device_type"],
            browser=device_info["browser"],
            os=device_info["os"],
        ),
        location=SessionLocation(
            city=refresh_token.city,
            country=refresh_token.country,
            country_code=refresh_token.country_code,
        ),
        ip_address=mask_ip_address(refresh_token.ip_address),
        auth_provider=refresh_token.auth_provider,
        created_time=refresh_token.created_time,
        updated_time=refresh_token.updated_time,
        is_current=refresh_token.token == current_token if current_token else False,
    )


@router.get("", response_model=SessionListResponse)
async def list_sessions_endpoint(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(
        default=50, ge=1, le=100, description="Number of sessions per page"
    ),
    offset: int = Query(default=0, ge=0, description="Number of sessions to skip"),
):
    """
    List all active sessions for the current user.

    The current session is identified automatically from the httpOnly refresh
    token cookie.

    Query params:
        limit: Maximum number of sessions to return (default 50)
        offset: Number of sessions to skip for pagination
    """
    from src.core.cookies import get_refresh_token_from_cookie

    current_token = get_refresh_token_from_cookie(request)

    sessions_list, total = await get_active_sessions_for_user(
        session=session,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        limit=limit,
        offset=offset,
    )

    return SessionListResponse(
        items=[_build_session_response(s, current_token) for s in sessions_list],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/others", response_model=RevokeOtherSessionsResponse)
async def revoke_other_sessions_endpoint(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Revoke all sessions except the current one.

    The current session is identified from the httpOnly refresh token cookie.
    """
    from src.core.cookies import get_refresh_token_from_cookie

    current_token = get_refresh_token_from_cookie(request)
    if not current_token:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No current session identified",
            detail_code="session.no_current",
        )

    count = await delete_other_sessions(
        session=session,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        exclude_token=current_token,
    )

    # Invalidate JWT cache for the user (affects other sessions)
    await cache_service.invalidate_jwt_for_user(current_user.id)

    return RevokeOtherSessionsResponse(
        message=f"{count} session(s) revoked successfully",
        message_code=get_response_code("session.others_revoked"),
        revoked_count=count,
    )


@router.delete("/{session_id}", response_model=RevokeSessionResponse)
async def revoke_session_endpoint(
    session_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Revoke a specific session by ID.

    This soft-deletes the refresh token, effectively logging out that session.
    """
    # Get the session to check if it exists and belongs to user
    target_session = await get_session_by_id(
        session=session,
        session_id=session_id,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
    )

    if not target_session:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
            detail_code="session.not_found",
        )

    # Soft delete the session
    await delete_session(
        session=session,
        session_id=session_id,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
    )

    # Invalidate JWT cache for the user
    await cache_service.invalidate_jwt_for_user(current_user.id)

    return RevokeSessionResponse(
        message="Session revoked successfully",
        message_code=get_response_code("session.revoked"),
    )
