"""
CRUD operations for UserInvitation model.
All operations are tenant-scoped by organization_id.
"""

from datetime import datetime, timedelta, timezone
import json
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.user_invitation import UserInvitation


INVITATION_EXPIRY_DAYS = 7


async def create_invitation(
    session: AsyncSession,
    organization_id: str,
    email: str,
    invited_by_user_id: str,
    role_ids: list[str] | None = None,
    user_type_ids: list[str] | None = None,
) -> UserInvitation:
    """
    Create a new pending invitation.

    Raises ValueError if a pending (non-deleted, non-accepted) invitation
    already exists for this email in this organization.
    """
    org_uuid = UUID(organization_id)

    # Check for existing pending invitation
    existing = await session.execute(
        select(UserInvitation).where(
            UserInvitation.organization_id == org_uuid,
            UserInvitation.email == email.lower(),
            UserInvitation.deleted_time.is_(None),
            UserInvitation.accepted_at.is_(None),
        )
    )
    if existing.scalars().first():
        raise ValueError("A pending invitation already exists for this email.")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=INVITATION_EXPIRY_DAYS)

    invitation = UserInvitation(
        organization_id=org_uuid,
        email=email.lower(),
        token=token,
        invited_by_user_id=UUID(invited_by_user_id),
        role_ids=json.dumps(role_ids) if role_ids else None,
        user_type_ids=json.dumps(user_type_ids) if user_type_ids else None,
        expires_at=expires_at,
    )
    session.add(invitation)
    await session.flush()
    await session.refresh(invitation)
    return invitation


async def get_invitation_by_id(
    session: AsyncSession,
    invitation_id: str,
    organization_id: str,
) -> UserInvitation | None:
    """Get an invitation by ID within the organization tenant."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(UserInvitation)
        .options(selectinload(UserInvitation.invited_by))
        .where(
            UserInvitation.id == UUID(invitation_id),
            UserInvitation.organization_id == org_uuid,
            UserInvitation.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_invitation_by_token(
    session: AsyncSession,
    token: str,
) -> UserInvitation | None:
    """Get a pending, non-expired invitation by token (public endpoint use)."""
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(UserInvitation)
        .options(selectinload(UserInvitation.organization))
        .where(
            UserInvitation.token == token,
            UserInvitation.deleted_time.is_(None),
            UserInvitation.accepted_at.is_(None),
            UserInvitation.expires_at > now,
        )
    )
    return result.scalars().first()


async def list_pending_invitations(
    session: AsyncSession,
    organization_id: str,
) -> list[UserInvitation]:
    """List all pending (not accepted, not revoked, not expired) invitations for an org."""
    org_uuid = UUID(organization_id)
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(UserInvitation)
        .options(selectinload(UserInvitation.invited_by))
        .where(
            UserInvitation.organization_id == org_uuid,
            UserInvitation.deleted_time.is_(None),
            UserInvitation.accepted_at.is_(None),
            UserInvitation.expires_at > now,
        )
        .order_by(UserInvitation.created_time.desc())
    )
    return list(result.scalars().all())


async def revoke_invitation(
    session: AsyncSession,
    invitation_id: str,
    organization_id: str,
) -> UserInvitation | None:
    """Soft-delete (revoke) an invitation. Returns the invitation if found."""
    invitation = await get_invitation_by_id(session, invitation_id, organization_id)
    if not invitation:
        return None
    invitation.deleted_time = datetime.now(timezone.utc)
    await session.flush()
    return invitation


async def accept_invitation(
    session: AsyncSession,
    token: str,
) -> UserInvitation | None:
    """
    Mark an invitation as accepted. Returns the invitation or None if not found/expired.
    Also returns parsed role_ids and user_type_ids lists.
    """
    invitation = await get_invitation_by_token(session, token)
    if not invitation:
        return None
    invitation.accepted_at = datetime.now(timezone.utc)
    await session.flush()
    return invitation


def parse_invitation_ids(invitation: UserInvitation) -> tuple[list[str], list[str]]:
    """Parse JSON-encoded role_ids and user_type_ids from the invitation."""
    role_ids: list[str] = []
    user_type_ids: list[str] = []
    if invitation.role_ids:
        try:
            role_ids = json.loads(invitation.role_ids)
        except (ValueError, TypeError):
            role_ids = []
    if invitation.user_type_ids:
        try:
            user_type_ids = json.loads(invitation.user_type_ids)
        except (ValueError, TypeError):
            user_type_ids = []
    return role_ids, user_type_ids
