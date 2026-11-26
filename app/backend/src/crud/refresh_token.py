from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.models import RefreshToken
from src.services.session_metadata import get_location_from_ip


async def create_refresh_token(
    session: AsyncSession, user_id: str, organization_id: str
):
    new_token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.REFRESH_TOKEN_EXPIRE_SECONDS
    )

    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )

    refresh_token = RefreshToken(
        user_id=user_uuid,
        token=new_token,
        expires_at=expires_at,
        organization_id=org_uuid,
    )
    session.add(refresh_token)
    await session.commit()
    await session.refresh(refresh_token)

    return new_token


async def get_refresh_token(
    session: AsyncSession, token: str, organization_id: Optional[str] = None
) -> Optional[RefreshToken]:
    """Get refresh token. organization_id is optional for token lookup during refresh flow."""
    query = select(RefreshToken).where(
        RefreshToken.token == token, RefreshToken.deleted_time.is_(None)
    )
    if organization_id:
        org_uuid = (
            UUID(organization_id)
            if isinstance(organization_id, str)
            else organization_id
        )
        query = query.where(RefreshToken.organization_id == org_uuid)

    result = await session.execute(query)
    return result.scalars().first()


async def delete_refresh_token(
    session: AsyncSession, token: str, organization_id: str
) -> bool:
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )
    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.token == token, RefreshToken.organization_id == org_uuid
        )
    )
    refresh_token = result.scalars().first()

    if refresh_token:
        # Soft delete
        refresh_token.deleted_time = datetime.now(timezone.utc)
        await session.commit()
        return True
    return False


async def delete_all_refresh_tokens_for_user(
    session: AsyncSession, user_id: str, organization_id: str
) -> int:
    """
    Soft delete all refresh tokens for a user.

    Args:
        session: Database session
        user_id: User UUID string
        organization_id: Organization UUID string

    Returns:
        Number of tokens invalidated
    """
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id

    # Get all active refresh tokens for the user
    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_uuid,
            RefreshToken.organization_id == org_uuid,
            RefreshToken.deleted_time.is_(None),
        )
    )
    tokens = result.scalars().all()

    # Soft delete all tokens
    count = 0
    for token in tokens:
        token.deleted_time = datetime.now(timezone.utc)
        count += 1

    await session.commit()
    return count


async def create_refresh_token_with_metadata(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    auth_provider: Optional[str] = None,
) -> str:
    """
    Create a new refresh token with session metadata.

    Args:
        session: Database session
        user_id: User UUID string
        organization_id: Organization UUID string
        ip_address: Client IP address
        user_agent: Client user-agent string
        auth_provider: Authentication provider (email, google, etc.)

    Returns:
        The new refresh token string
    """
    new_token = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.REFRESH_TOKEN_EXPIRE_SECONDS)

    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )

    # Get location from IP
    city, country, country_code = get_location_from_ip(ip_address)

    refresh_token = RefreshToken(
        user_id=user_uuid,
        token=new_token,
        expires_at=expires_at,
        organization_id=org_uuid,
        auth_provider=auth_provider,
        ip_address=ip_address,
        user_agent=user_agent,
        city=city,
        country=country,
        country_code=country_code,
        created_time=now,
        updated_time=now,
    )
    session.add(refresh_token)
    await session.commit()
    await session.refresh(refresh_token)

    return new_token


async def get_active_sessions_for_user(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[RefreshToken], int]:
    """
    Get all active (non-deleted, non-expired) sessions for a user.

    Args:
        session: Database session
        user_id: User UUID string
        organization_id: Organization UUID string
        limit: Maximum number of sessions to return
        offset: Number of sessions to skip

    Returns:
        Tuple of (list of RefreshToken objects, total count)
    """
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    now = datetime.now(timezone.utc)

    # Base filter for active sessions
    base_filter = [
        RefreshToken.user_id == user_uuid,
        RefreshToken.organization_id == org_uuid,
        RefreshToken.deleted_time.is_(None),
        RefreshToken.expires_at > now,
    ]

    # Count total active sessions
    count_query = select(func.count()).select_from(RefreshToken).where(*base_filter)
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    # Get sessions ordered by updated_time descending
    query = (
        select(RefreshToken)
        .where(*base_filter)
        .order_by(RefreshToken.updated_time.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(query)
    sessions_list = list(result.scalars().all())

    return sessions_list, total


async def get_session_by_id(
    session: AsyncSession,
    session_id: str,
    user_id: str,
    organization_id: str,
) -> Optional[RefreshToken]:
    """
    Get a specific session by ID, validating it belongs to the user.

    Args:
        session: Database session
        session_id: Session (RefreshToken) ID
        user_id: User UUID string
        organization_id: Organization UUID string

    Returns:
        RefreshToken object or None if not found
    """
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id

    query = select(RefreshToken).where(
        RefreshToken.id == session_id,
        RefreshToken.user_id == user_uuid,
        RefreshToken.organization_id == org_uuid,
        RefreshToken.deleted_time.is_(None),
    )
    result = await session.execute(query)
    return result.scalars().first()


async def delete_session(
    session: AsyncSession,
    session_id: str,
    user_id: str,
    organization_id: str,
) -> bool:
    """
    Soft delete a specific session.

    Args:
        session: Database session
        session_id: Session (RefreshToken) ID
        user_id: User UUID string
        organization_id: Organization UUID string

    Returns:
        True if session was deleted, False if not found
    """
    refresh_token = await get_session_by_id(
        session, session_id, user_id, organization_id
    )

    if refresh_token:
        refresh_token.deleted_time = datetime.now(timezone.utc)
        await session.commit()
        return True
    return False


async def delete_other_sessions(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
    exclude_token: str,
) -> int:
    """
    Soft delete all sessions for a user except the one with the given token.

    Args:
        session: Database session
        user_id: User UUID string
        organization_id: Organization UUID string
        exclude_token: Token string to exclude from deletion (current session)

    Returns:
        Number of sessions deleted
    """
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id

    # Get all active tokens except the current one
    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_uuid,
            RefreshToken.organization_id == org_uuid,
            RefreshToken.deleted_time.is_(None),
            RefreshToken.token != exclude_token,
        )
    )
    tokens = result.scalars().all()

    # Soft delete
    count = 0
    now = datetime.now(timezone.utc)
    for token in tokens:
        token.deleted_time = now
        count += 1

    await session.commit()
    return count


async def update_last_active(
    session: AsyncSession,
    token: str,
) -> bool:
    """
    Update the updated_time timestamp for a refresh token.

    Args:
        session: Database session
        token: Refresh token string

    Returns:
        True if updated, False if token not found
    """
    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.token == token,
            RefreshToken.deleted_time.is_(None),
        )
    )
    refresh_token = result.scalars().first()

    if refresh_token:
        refresh_token.updated_time = datetime.now(timezone.utc)
        await session.commit()
        return True
    return False
