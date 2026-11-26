"""
CRUD operations for the tenant-scoped UserUserType model.
Links users to user types and tracks onboarding status within an organization.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user_user_type import OnboardingStatus, UserUserType
from src.services.cache import cache_service


async def get_by_user_and_type(
    session: AsyncSession, user_id: str, user_type_id: str, organization_id: str
):
    """Get a user-user type association by user and type."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(UserUserType).where(
            UserUserType.user_id == UUID(user_id),
            UserUserType.user_type_id == UUID(user_type_id),
            UserUserType.organization_id == org_uuid,
            UserUserType.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_all_for_user(session: AsyncSession, user_id: str, organization_id: str):
    """Get all user type associations for a user."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(UserUserType).where(
            UserUserType.user_id == UUID(user_id),
            UserUserType.organization_id == org_uuid,
            UserUserType.deleted_time.is_(None),
        )
    )
    return result.scalars().all()


async def create(session: AsyncSession, data: dict, organization_id: str):
    """Create a new user-user type association."""
    org_uuid = UUID(organization_id)
    user_id = UUID(data["user_id"])
    user_type_id = UUID(data["user_type_id"])

    # Check if association already exists
    existing = await session.execute(
        select(UserUserType).where(
            UserUserType.user_id == user_id,
            UserUserType.user_type_id == user_type_id,
            UserUserType.organization_id == org_uuid,
            UserUserType.deleted_time.is_(None),
        )
    )
    if existing.scalars().first():
        raise ValueError("User already has this user type assigned")

    user_user_type = UserUserType(
        user_id=user_id, user_type_id=user_type_id, organization_id=org_uuid
    )
    session.add(user_user_type)
    await session.commit()
    await session.refresh(user_user_type)

    # Invalidate user's permission cache since user type may grant permissions
    await cache_service.invalidate_user_permissions(organization_id, str(user_id))

    return user_user_type


async def update_status(
    session: AsyncSession,
    id: str,
    status: OnboardingStatus,
    organization_id: str,
    onboarded_at: Optional[datetime] = None,
    requires_admin_attention: Optional[bool] = None,
    expires_at: Optional[datetime] = None,
):
    """Update the onboarding status of a user-user type association."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(UserUserType).where(
            UserUserType.id == UUID(id),
            UserUserType.organization_id == org_uuid,
            UserUserType.deleted_time.is_(None),
        )
    )
    user_user_type = result.scalars().first()
    if not user_user_type:
        raise ValueError(f"User-user type association with id {id} not found")

    user_user_type.onboarding_status = status
    if onboarded_at:
        user_user_type.onboarded_at = onboarded_at
    if requires_admin_attention is not None:
        user_user_type.requires_admin_attention = requires_admin_attention
    if expires_at is not None:
        user_user_type.expires_at = expires_at

    await session.commit()
    await session.refresh(user_user_type)
    return user_user_type


async def set_requires_admin_attention(
    session: AsyncSession,
    id: str,
    requires_attention: bool,
    organization_id: str,
) -> UserUserType:
    """Set the requires_admin_attention flag on a user-user type association."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(UserUserType).where(
            UserUserType.id == UUID(id),
            UserUserType.organization_id == org_uuid,
            UserUserType.deleted_time.is_(None),
        )
    )
    user_user_type = result.scalars().first()
    if not user_user_type:
        raise ValueError(f"User-user type association with id {id} not found")

    user_user_type.requires_admin_attention = requires_attention

    await session.commit()
    await session.refresh(user_user_type)
    return user_user_type


async def get_by_id(
    session: AsyncSession, id: str, organization_id: str
) -> UserUserType | None:
    """Get a user-user type association by ID."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(UserUserType).where(
            UserUserType.id == UUID(id),
            UserUserType.organization_id == org_uuid,
            UserUserType.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def delete(
    session: AsyncSession, id: str, organization_id: str
) -> UserUserType | None:
    """Soft delete a user-user type association and invalidate permission cache."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(UserUserType).where(
            UserUserType.id == UUID(id),
            UserUserType.organization_id == org_uuid,
            UserUserType.deleted_time.is_(None),
        )
    )
    user_user_type = result.scalars().first()
    if not user_user_type:
        return None

    user_id = str(user_user_type.user_id)
    user_user_type.deleted_time = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(user_user_type)

    # Invalidate user's permission cache since user type may have granted permissions
    await cache_service.invalidate_user_permissions(organization_id, user_id)

    return user_user_type


async def get_expired_user_types(
    session: AsyncSession,
    now: datetime,
) -> list[UserUserType]:
    """
    Get all user type assignments that have expired but not yet been notified.

    Args:
        session: Database session
        now: Current datetime for comparison

    Returns:
        List of expired UserUserType records that need notification
    """
    result = await session.execute(
        select(UserUserType).where(
            UserUserType.expires_at <= now,
            UserUserType.expiry_notified_at.is_(None),
            UserUserType.onboarding_status == OnboardingStatus.APPROVED,
            UserUserType.deleted_time.is_(None),
        )
    )
    return list(result.scalars().all())


async def mark_expiry_notified(
    session: AsyncSession,
    id: str,
    notified_at: datetime,
) -> UserUserType | None:
    """
    Mark a user type assignment as having been notified of expiry.

    Args:
        session: Database session
        id: UserUserType UUID
        notified_at: Datetime when notification was sent

    Returns:
        Updated UserUserType or None if not found
    """
    result = await session.execute(
        select(UserUserType).where(
            UserUserType.id == UUID(id),
            UserUserType.deleted_time.is_(None),
        )
    )
    user_user_type = result.scalars().first()
    if not user_user_type:
        return None

    user_user_type.expiry_notified_at = notified_at

    await session.commit()
    await session.refresh(user_user_type)
    return user_user_type
