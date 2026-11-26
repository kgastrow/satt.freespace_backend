"""
User Invitation API endpoints.
Allows organization admins to invite users by email, optionally pre-assigning
roles and user types. Invited users bypass the onboarding wizard for pre-assigned types.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_session, require_permission
from src.core.config import settings
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.crud import audit_log as audit_log_crud
from src.crud.user_invitation import (
    create_invitation,
    get_invitation_by_token,
    list_pending_invitations,
    revoke_invitation,
)
from src.logger.logger import Logger
from src.serialisers.invitation import (
    CreateInvitationRequest,
    CreateInvitationResponse,
    InvitationResponse,
    ListInvitationsResponse,
    RevokeInvitationResponse,
    ValidateInvitationResponse,
)
from src.services.audit import get_client_ip, get_user_agent


router = APIRouter(prefix="/invitations", tags=["invitations"])


@router.post(
    "", response_model=CreateInvitationResponse, status_code=status.HTTP_201_CREATED
)
async def create_invitation_endpoint(
    request: Request,
    body: CreateInvitationRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(require_permission("users:write"))],
):
    """
    Create and send a user invitation.

    Sends an email to the specified address with a link to register.
    Optionally pre-assigns roles and user types (bypasses onboarding wizard for those types).
    """
    from src.crud.organization import get_organization_by_id
    from src.services.tasks import task_queue

    organization = await get_organization_by_id(session, current_user.organization_id)
    if not organization:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
            detail_code="organization.not_found",
        )

    role_ids = [str(r) for r in body.role_ids] if body.role_ids else None
    user_type_ids = (
        [str(ut) for ut in body.user_type_ids] if body.user_type_ids else None
    )

    try:
        invitation = await create_invitation(
            session=session,
            organization_id=current_user.organization_id,
            email=str(body.email),
            invited_by_user_id=current_user.id,
            role_ids=role_ids,
            user_type_ids=user_type_ids,
        )
    except ValueError as exc:
        raise create_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
            detail_code="invitation.already_pending",
        )

    await session.commit()
    await session.refresh(invitation, attribute_names=["invited_by"])

    # Build registration URL
    org_slug = organization.slug
    # SPA route (app/frontend/src/router.tsx), so the FRONTEND origin.
    registration_url = (
        f"{settings.PUBLIC_URL_FRONTEND}/register"
        f"?invite_token={invitation.token}&org={org_slug}"
    )

    # Determine invited-by display name
    invited_by_name = current_user.org_name or current_user.email
    # Try to use actual user name from session context
    invited_by_display = invited_by_name or "Your organization administrator"

    # Queue invitation email asynchronously
    await task_queue.enqueue_invitation_email(
        to=str(body.email),
        organization_name=organization.name,
        registration_url=registration_url,
        invited_by_name=invited_by_display,
        organization_id=current_user.organization_id,
    )

    # Audit log
    try:
        await audit_log_crud.create_audit_log(
            session=session,
            organization_id=current_user.organization_id,
            actor_user_id=current_user.id,
            action="invitation.created",
            resource_type="user_invitation",
            resource_id=str(invitation.id),
            metadata={"email": str(body.email)},
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )
        await session.commit()
    except Exception as exc:
        Logger.warning(f"Failed to write audit log for invitation: {exc}")

    return CreateInvitationResponse(
        message="Invitation sent successfully",
        message_code=get_response_code("invitation.created"),
        invitation=InvitationResponse.from_orm(invitation),
    )


@router.get("", response_model=ListInvitationsResponse)
async def list_invitations_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(require_permission("users:read"))],
):
    """
    List all pending (not accepted, not revoked, not expired) invitations for the organization.
    """
    invitations = await list_pending_invitations(
        session=session,
        organization_id=current_user.organization_id,
    )
    return ListInvitationsResponse(
        items=[InvitationResponse.from_orm(inv) for inv in invitations],
        total=len(invitations),
    )


# NOTE: this /validate/{token} route must come BEFORE /{invitation_id} to avoid conflicts
@router.get("/validate/{token}", response_model=ValidateInvitationResponse)
async def validate_invitation_token_endpoint(
    token: str,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Public endpoint: Validate an invitation token and return email + org slug.
    Used by the registration page to pre-fill form fields.
    Does NOT require authentication.
    """
    invitation = await get_invitation_by_token(session, token)
    if not invitation:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found, expired, or already accepted",
            detail_code="invitation.invalid_token",
        )

    return ValidateInvitationResponse(
        email=invitation.email,
        organization_slug=invitation.organization.slug,
        expires_at=invitation.expires_at,
    )


@router.delete("/{invitation_id}", response_model=RevokeInvitationResponse)
async def revoke_invitation_endpoint(
    request: Request,
    invitation_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(require_permission("users:write"))],
):
    """
    Revoke (soft-delete) a pending invitation.
    """
    invitation = await revoke_invitation(
        session=session,
        invitation_id=invitation_id,
        organization_id=current_user.organization_id,
    )
    if not invitation:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
            detail_code="invitation.not_found",
        )

    await session.commit()

    # Audit log
    try:
        await audit_log_crud.create_audit_log(
            session=session,
            organization_id=current_user.organization_id,
            actor_user_id=current_user.id,
            action="invitation.revoked",
            resource_type="user_invitation",
            resource_id=invitation_id,
            metadata={"email": invitation.email},
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )
        await session.commit()
    except Exception as exc:
        Logger.warning(f"Failed to write audit log for invitation revocation: {exc}")

    return RevokeInvitationResponse(
        message="Invitation revoked successfully",
        message_code=get_response_code("invitation.revoked"),
    )
