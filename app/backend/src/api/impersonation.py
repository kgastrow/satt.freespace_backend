"""
Impersonation API endpoints for super admin user impersonation.
Allows super admins to impersonate organization users for support purposes.
All impersonation actions are logged in the audit log with the admin as the actor.
"""

from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_super_admin,
    get_current_user,
    get_session,
)
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.core.security import create_access_token, create_impersonation_token
from src.crud.impersonation_session import (
    get_active_session_by_impersonator,
    get_my_impersonation_history,
    get_session_by_id,
    get_session_history,
)
from src.crud.organization import get_organization_by_id
from src.models.audit_log import AuditAction
from src.models.user import SuspensionStatus, User
from src.serialisers.impersonation_session import (
    EndImpersonationResponse,
    ImpersonationSessionListResponse,
    ImpersonationSessionResponse,
    ImpersonationSessionStatusResponse,
    ImpersonatorInfo,
    MyImpersonationHistoryItem,
    MyImpersonationHistoryResponse,
    StartImpersonationResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent
from src.services.impersonation import ImpersonationService
from src.services.notifications.impersonation_notifier import impersonation_notifier


router = APIRouter(prefix="/admin/impersonate", tags=["impersonation"])

# Router for user-facing impersonation endpoints (no admin prefix)
user_router = APIRouter(prefix="/impersonate", tags=["impersonation"])


# NOTE: Static routes (/end, /session, /history) MUST be defined before dynamic routes (/{user_id})
# to prevent FastAPI from matching static paths like "end" as user_id values.


@router.post(
    "/end", status_code=status.HTTP_200_OK, response_model=EndImpersonationResponse
)
async def end_impersonation(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    End the current impersonation session.

    Must be called while using an impersonation token. Returns the original admin's token.

    Args:
        request: FastAPI request object (for IP and user agent)
        current_user: The current user (should be impersonating)
        session: Database session

    Returns:
        Original admin token and ended session details

    Raises:
        HTTPException: 400 if not currently impersonating
    """
    # Verify user is impersonating
    if not current_user.is_impersonating:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not currently impersonating",
            detail_code="common.error",
        )

    if not current_user.impersonation_session_id:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active impersonation session found",
            detail_code="common.error",
        )

    # End the impersonation session
    ended_session = await ImpersonationService.end_impersonation(
        session=session,
        impersonation_session_id=current_user.impersonation_session_id,
    )

    if not ended_session:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Impersonation session not found",
            detail_code="impersonation.user_not_found",
        )

    # Validate that the impersonator_id in the token matches the session's impersonator_id
    # This prevents one admin from ending another admin's impersonation session
    if str(ended_session.impersonator_id) != current_user.impersonator_id:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot end another admin's impersonation session",
            detail_code="impersonation.unauthorized",
        )

    # Calculate session duration for audit log
    if ended_session.created_time and ended_session.ended_time:
        duration_seconds = (
            ended_session.ended_time - ended_session.created_time
        ).total_seconds()
    else:
        duration_seconds = 0

    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    # Log audit event - use impersonator's ID as the actor
    await audit_service.log_action(
        session=session,
        organization_id=str(ended_session.target_organization_id),
        action=AuditAction.IMPERSONATE_END,
        resource_type="ImpersonationSession",
        resource_id=str(ended_session.id),
        actor_id=current_user.impersonator_id,  # Use original admin's ID as actor
        changes={
            "duration_seconds": {"old": None, "new": duration_seconds},
            "ended_time": {
                "old": None,
                "new": (
                    ended_session.ended_time.isoformat()
                    if ended_session.ended_time
                    else None
                ),
            },
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # Notify target user that impersonation has ended
    # Type narrowing: ended_session is guaranteed non-None here (service raises if not found)
    # and created_time/ended_time are set by crud_end_session
    if (
        ended_session
        and current_user.impersonator_id
        and ended_session.created_time
        and ended_session.ended_time
    ):
        await impersonation_notifier.notify_end(
            session=session,
            target_user_id=str(ended_session.target_user_id),
            target_organization_id=str(ended_session.target_organization_id),
            impersonator_id=current_user.impersonator_id,
            started_at=ended_session.created_time,
            ended_at=ended_session.ended_time,
        )

    # Create original admin token (without impersonation context)
    # Fetch and validate the impersonator is still a valid super admin
    result = await session.execute(
        select(User).where(
            User.id == UUID(current_user.impersonator_id),
            User.deleted_time.is_(None),
        )
    )
    impersonator = result.scalars().first()

    if not impersonator:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impersonator user not found",
        )

    if not impersonator.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Impersonator is no longer a super admin",
        )

    # SECURITY: this hands the admin a working session back, so the account
    # gates apply here too. An impersonation session can stay open for a long
    # time, and the two gates that can flip while it is open -- the admin being
    # suspended, or the admin's own organization being deactivated -- were not
    # checked at all: only ``is_admin`` was re-validated. ``get_current_user``
    # does not cover them either, because on an impersonation token it
    # validates the TARGET user and the TARGET organization, not the admin's.
    #
    # This deliberately does NOT route through ``issue_session_for_user``:
    #   * that helper always mints a refresh token, while this endpoint issues
    #     an access token only. It restores the session the admin already had
    #     before impersonating; it does not create new persistent credential
    #     material, and it should stay that way.
    #   * the second factor was already satisfied when the admin logged in and
    #     started the impersonation, and this endpoint cannot present a TOTP
    #     challenge (no union response, no frontend branch). The helper's only
    #     options here would be to refuse every 2FA-enrolled super admin at the
    #     end of every impersonation, or to skip the factor -- neither is right
    #     for a session that was already fully gated.
    # So the two gates that CAN change are applied inline, in the same order
    # and with the same detail codes as ``issue_session_for_user``.
    admin_organization = await get_organization_by_id(
        session, str(impersonator.organization_id)
    )
    if admin_organization is None or not admin_organization.is_active:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is not active",
            detail_code="auth.organization_not_active",
        )

    if impersonator.suspension_status == SuspensionStatus.SUSPENDED:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been suspended. Please contact your administrator.",
            detail_code="user.suspended",
        )

    # Create standard access token for the admin
    admin_token = create_access_token(
        user_id=str(impersonator.id),
        organization_id=str(impersonator.organization_id),
    )

    return {
        "access_token": admin_token,
        "session": ImpersonationSessionResponse.model_validate(ended_session),
        "message": "Impersonation ended successfully",
        "message_code": get_response_code("impersonation.ended"),
    }


@router.get("/session", response_model=ImpersonationSessionStatusResponse)
async def get_current_session(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get details of the current impersonation session (if any).

    Returns 200 with active: false if not impersonating,
    or 200 with active: true and session details if impersonating.

    Args:
        current_user: The current user
        session: Database session

    Returns:
        Current impersonation session status and details (if active)
    """
    # If not impersonating, return inactive status
    if not current_user.is_impersonating:
        return ImpersonationSessionStatusResponse(active=False)

    if not current_user.impersonation_session_id:
        return ImpersonationSessionStatusResponse(active=False)

    # Get session details using the session_id from the token (more reliable than querying by impersonator_id)
    active_session = await get_session_by_id(
        session, current_user.impersonation_session_id
    )

    # If session not found or ended, return inactive status
    if not active_session or active_session.ended_time is not None:
        return ImpersonationSessionStatusResponse(active=False)

    # Return active status with session details
    return ImpersonationSessionStatusResponse(
        active=True,
        session=ImpersonationSessionResponse.model_validate(active_session),
    )


@router.get("/history", response_model=ImpersonationSessionListResponse)
async def get_impersonation_history(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    impersonator_id: Optional[UUID] = Query(
        None, description="Filter by impersonator user ID"
    ),
    target_user_id: Optional[UUID] = Query(
        None, description="Filter by target user ID"
    ),
    target_organization_id: Optional[UUID] = Query(
        None, description="Filter by target organization ID"
    ),
    limit: int = Query(50, ge=1, le=100, description="Number of results per page"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
):
    """
    Get impersonation session history with optional filters.

    Super admin only. Returns paginated list of impersonation sessions.

    Args:
        current_user: The current super admin
        session: Database session
        impersonator_id: Optional filter by impersonator user ID
        target_user_id: Optional filter by target user ID
        target_organization_id: Optional filter by target organization ID
        limit: Number of results per page (1-100)
        offset: Number of results to skip

    Returns:
        Paginated list of impersonation sessions
    """
    sessions, total = await get_session_history(
        session=session,
        impersonator_id=str(impersonator_id) if impersonator_id else None,
        target_user_id=str(target_user_id) if target_user_id else None,
        target_organization_id=(
            str(target_organization_id) if target_organization_id else None
        ),
        limit=limit,
        offset=offset,
    )

    return ImpersonationSessionListResponse(
        items=[ImpersonationSessionResponse.model_validate(s) for s in sessions],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/resume",
    status_code=status.HTTP_200_OK,
    response_model=StartImpersonationResponse,
)
async def resume_impersonation(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Re-issue impersonation token for an active session after page refresh.

    During impersonation, the admin's refresh cookie stays in the browser.
    On page refresh, /auth/refresh returns an admin token. The frontend then
    calls this endpoint to get a fresh impersonation token if there's an
    active impersonation session.

    Args:
        request: FastAPI request object
        current_user: The current super admin (restored via cookie refresh)
        session: Database session

    Returns:
        New impersonation token and session details

    Raises:
        HTTPException: 404 if no active impersonation session
    """
    active_session = await get_active_session_by_impersonator(session, current_user.id)
    if not active_session:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active impersonation session found",
            detail_code="impersonation.no_active_session",
        )

    impersonation_token = create_impersonation_token(
        user_id=str(active_session.target_user_id),
        organization_id=str(active_session.target_organization_id),
        impersonator_id=current_user.id,
        impersonation_session_id=str(active_session.id),
    )

    return {
        "impersonation_token": impersonation_token,
        "session": ImpersonationSessionResponse.model_validate(active_session),
        "message": "Impersonation resumed successfully",
        "message_code": get_response_code("impersonation.resumed"),
    }


# Dynamic route MUST be last - otherwise it will match static paths like "end" as user_id
@router.post(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=StartImpersonationResponse,
)
async def start_impersonation(
    user_id: UUID,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Start impersonating a user.

    Super admin only. Creates an impersonation session and returns an impersonation token.
    The token contains the target user's context but maintains the admin's identity for auditing.

    Args:
        user_id: UUID of the user to impersonate
        request: FastAPI request object (for IP and user agent)
        current_user: The current super admin
        session: Database session

    Returns:
        Impersonation token and session details

    Raises:
        HTTPException: 400 if validation fails, 404 if user not found, 403 if not super admin
    """
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    # Start impersonation session
    impersonation_token, impersonation_session = (
        await ImpersonationService.start_impersonation(
            session=session,
            impersonator_id=current_user.id,
            target_user_id=str(user_id),
            ip_address=ip_address,
            user_agent=user_agent,
        )
    )

    # Log audit event - use impersonator's ID as the actor
    # Note: organization_id is the TARGET user's organization, not the admin's
    await audit_service.log_action(
        session=session,
        organization_id=str(impersonation_session.target_organization_id),
        action=AuditAction.IMPERSONATE_START,
        resource_type="ImpersonationSession",
        resource_id=str(impersonation_session.id),
        actor_id=current_user.id,  # CRITICAL: Use impersonator's ID as actor
        changes={
            "target_user_id": {
                "old": None,
                "new": str(impersonation_session.target_user_id),
            },
            "target_organization_id": {
                "old": None,
                "new": str(impersonation_session.target_organization_id),
            },
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # Notify target user that impersonation has started
    if impersonation_session.created_time:
        await impersonation_notifier.notify_start(
            session=session,
            target_user_id=str(impersonation_session.target_user_id),
            target_organization_id=str(impersonation_session.target_organization_id),
            impersonator_id=current_user.id,
            started_at=impersonation_session.created_time,
        )

    return {
        "impersonation_token": impersonation_token,
        "session": ImpersonationSessionResponse.model_validate(impersonation_session),
        "message": "Impersonation started successfully",
        "message_code": get_response_code("impersonation.started"),
    }


# User-facing endpoints (on user_router, no admin prefix)


@user_router.get("/my-history", response_model=MyImpersonationHistoryResponse)
async def get_my_impersonation_history_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(50, ge=1, le=100, description="Number of results per page"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
):
    """
    Get the current user's impersonation history.

    Returns a paginated list of impersonation sessions where the current user
    was the target (i.e., when they were impersonated by a super admin).
    Only completed sessions are returned (where impersonation has ended).

    This endpoint is blocked during active impersonation to prevent admins
    from viewing other admins' impersonation history for the target user.

    Args:
        current_user: The current authenticated user
        session: Database session
        limit: Number of results per page (1-100)
        offset: Number of results to skip

    Returns:
        Paginated list of impersonation sessions with impersonator details

    Raises:
        HTTPException: 403 if currently impersonating
    """
    # Block access during active impersonation to prevent leaking
    # information about other admins who impersonated this user
    if current_user.is_impersonating:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view impersonation history while impersonating",
            detail_code="impersonation.forbidden_while_impersonating",
        )

    # Use the current user's ID and organization
    # When impersonating, current_user.id is the impersonated user (target),
    # which is correct - we want to show that user's impersonation history
    sessions, total = await get_my_impersonation_history(
        session=session,
        target_user_id=str(current_user.id),
        organization_id=str(current_user.organization_id),
        limit=limit,
        offset=offset,
    )

    # Transform sessions to response items
    items = []
    for s in sessions:
        if s.impersonator and s.created_time and s.ended_time:
            items.append(
                MyImpersonationHistoryItem(
                    id=s.id,
                    created_time=s.created_time,
                    ended_time=s.ended_time,
                    impersonator=ImpersonatorInfo(
                        id=s.impersonator.id,
                        email=s.impersonator.email,
                        first_name=s.impersonator.first_name,
                        last_name=s.impersonator.last_name,
                    ),
                )
            )

    return MyImpersonationHistoryResponse(
        sessions=items,
        total=total,
        limit=limit,
        offset=offset,
    )
