from datetime import datetime, timezone
from typing import Optional
from uuid import UUID as UUIDType

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ImpersonationSession


def _to_uuid(value: str | UUIDType) -> UUIDType:
    """Convert string to UUID if needed"""
    return UUIDType(value) if isinstance(value, str) else value


async def create_session(
    session: AsyncSession,
    impersonator_id: str,
    target_user_id: str,
    target_organization_id: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> ImpersonationSession:
    """Create a new impersonation session"""
    impersonation_session = ImpersonationSession(
        impersonator_id=_to_uuid(impersonator_id),
        target_user_id=_to_uuid(target_user_id),
        target_organization_id=_to_uuid(target_organization_id),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    session.add(impersonation_session)
    await session.commit()
    await session.refresh(impersonation_session)

    return impersonation_session


async def get_session_by_id(
    session: AsyncSession, session_id: str
) -> Optional[ImpersonationSession]:
    """Get an impersonation session by ID"""
    result = await session.execute(
        select(ImpersonationSession).where(
            ImpersonationSession.id == _to_uuid(session_id)
        )
    )
    return result.scalars().first()


async def get_active_session_by_impersonator(
    session: AsyncSession, impersonator_id: str
) -> Optional[ImpersonationSession]:
    """Get the active impersonation session for a given impersonator"""
    result = await session.execute(
        select(ImpersonationSession).where(
            ImpersonationSession.impersonator_id == _to_uuid(impersonator_id),
            ImpersonationSession.ended_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_active_sessions_for_target(
    session: AsyncSession, target_user_id: str
) -> list[ImpersonationSession]:
    """Get all active impersonation sessions for a given target user"""
    result = await session.execute(
        select(ImpersonationSession).where(
            ImpersonationSession.target_user_id == _to_uuid(target_user_id),
            ImpersonationSession.ended_time.is_(None),
        )
    )
    return list(result.scalars().all())


async def end_session(
    session: AsyncSession, session_id: str
) -> Optional[ImpersonationSession]:
    """End an active impersonation session"""
    result = await session.execute(
        select(ImpersonationSession).where(
            ImpersonationSession.id == _to_uuid(session_id),
            ImpersonationSession.ended_time.is_(None),
        )
    )
    impersonation_session = result.scalars().first()

    if impersonation_session:
        impersonation_session.ended_time = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(impersonation_session)

    return impersonation_session


async def get_session_history(
    session: AsyncSession,
    impersonator_id: Optional[str] = None,
    target_user_id: Optional[str] = None,
    target_organization_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ImpersonationSession], int]:
    """Get impersonation session history with optional filters"""
    conditions: list[ColumnElement[bool]] = []

    if impersonator_id:
        conditions.append(
            ImpersonationSession.impersonator_id == _to_uuid(impersonator_id)
        )

    if target_user_id:
        conditions.append(
            ImpersonationSession.target_user_id == _to_uuid(target_user_id)
        )

    if target_organization_id:
        conditions.append(
            ImpersonationSession.target_organization_id
            == _to_uuid(target_organization_id)
        )

    # Get count
    count_result = await session.execute(
        select(func.count()).select_from(ImpersonationSession).where(*conditions)
    )
    total = count_result.scalar() or 0

    # Get sessions ordered by created_time descending (most recent first)
    result = await session.execute(
        select(ImpersonationSession)
        .where(*conditions)
        .order_by(ImpersonationSession.created_time.desc())
        .limit(limit)
        .offset(offset)
    )
    sessions = list(result.scalars().all())

    return sessions, total


async def get_my_impersonation_history(
    session: AsyncSession,
    target_user_id: str,
    organization_id: str,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ImpersonationSession], int]:
    """
    Get impersonation history for a user (where they were the target).

    Only returns sessions where the user was impersonated and the session
    has ended (ended_time is not NULL). Filters by organization_id for
    multi-tenancy compliance.

    Args:
        session: Database session
        target_user_id: The user ID to get history for (the target)
        organization_id: Organization ID for multi-tenancy filtering
        limit: Maximum number of results to return
        offset: Number of results to skip

    Returns:
        Tuple of (list of sessions, total count)
    """
    from sqlalchemy.orm import selectinload

    conditions: list[ColumnElement[bool]] = [
        ImpersonationSession.target_user_id == _to_uuid(target_user_id),
        ImpersonationSession.target_organization_id == _to_uuid(organization_id),
        ImpersonationSession.ended_time.is_not(None),  # Only completed sessions
    ]

    # Get count
    count_result = await session.execute(
        select(func.count()).select_from(ImpersonationSession).where(*conditions)
    )
    total = count_result.scalar() or 0

    # Get sessions with impersonator relationship eagerly loaded
    result = await session.execute(
        select(ImpersonationSession)
        .options(selectinload(ImpersonationSession.impersonator))
        .where(*conditions)
        .order_by(ImpersonationSession.created_time.desc())
        .limit(limit)
        .offset(offset)
    )
    sessions = list(result.scalars().all())

    return sessions, total
