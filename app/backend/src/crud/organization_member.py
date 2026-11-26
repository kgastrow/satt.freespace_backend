"""
CRUD operations for managing organization members (users within an organization).
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User


async def get_organization_members(
    session: AsyncSession, organization_id: str, limit: int = 10, offset: int = 0
) -> tuple[list[User], int]:
    """
    Get all members (users) of an organization with pagination.

    Args:
        session: SQLAlchemy async session
        organization_id: UUID of the organization (as string)
        limit: Maximum number of members to return
        offset: Number of members to skip

    Returns:
        Tuple of (list of users, total count)
    """
    org_uuid = UUID(organization_id)

    # Count query
    count_result = await session.execute(
        select(func.count())
        .select_from(User)
        .where(User.organization_id == org_uuid, User.deleted_time.is_(None))
    )
    total_count = count_result.scalar()

    # Data query
    result = await session.execute(
        select(User)
        .where(User.organization_id == org_uuid, User.deleted_time.is_(None))
        .limit(limit)
        .offset(offset)
    )
    users = result.scalars().all()

    return list(users), total_count or 0


async def remove_user_from_organization(
    session: AsyncSession, user_id: str, organization_id: str
):
    """
    Remove a user from an organization (soft delete).

    Args:
        session: SQLAlchemy async session
        user_id: UUID of the user to remove
        organization_id: UUID of the organization

    Returns:
        The soft-deleted user object

    Raises:
        ValueError: If user not found or doesn't belong to organization
    """
    from datetime import datetime, timezone

    from src.crud.user import get_user_by_id

    user = await get_user_by_id(session, user_id, organization_id)

    if not user:
        raise ValueError(
            f"User with id {user_id} not found in organization {organization_id}"
        )

    # Soft delete the user
    user.deleted_time = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(user)
    return user


async def get_organization_member_count(
    session: AsyncSession, organization_id: str
) -> int:
    """
    Get the count of active members in an organization.

    Args:
        session: SQLAlchemy async session
        organization_id: UUID of the organization (as string)

    Returns:
        Count of active members
    """
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(func.count())
        .select_from(User)
        .where(User.organization_id == org_uuid, User.deleted_time.is_(None))
    )
    count = result.scalar()
    return count or 0
