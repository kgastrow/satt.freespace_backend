"""
CRUD operations for UserIdentity model.
UserIdentity links users to their SSO provider identities.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user_identity import UserIdentity


async def get_by_provider_user_id(
    session: AsyncSession,
    provider: str,
    provider_user_id: str,
    organization_id: str,
) -> UserIdentity | None:
    """
    Find a user identity by provider and provider_user_id.

    Args:
        session: Database session
        provider: SSO provider name (e.g., 'google')
        provider_user_id: User's ID from the provider
        organization_id: Organization UUID

    Returns:
        UserIdentity if found, None otherwise
    """
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )

    result = await session.execute(
        select(UserIdentity).where(
            UserIdentity.organization_id == org_uuid,
            UserIdentity.provider == provider.lower(),
            UserIdentity.provider_user_id == provider_user_id,
            UserIdentity.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_by_user_id(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
) -> list[UserIdentity]:
    """
    Get all identities for a user.

    Args:
        session: Database session
        user_id: User UUID
        organization_id: Organization UUID

    Returns:
        List of UserIdentity records
    """
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )

    result = await session.execute(
        select(UserIdentity).where(
            UserIdentity.organization_id == org_uuid,
            UserIdentity.user_id == user_uuid,
            UserIdentity.deleted_time.is_(None),
        )
    )
    return list(result.scalars().all())


async def create(
    session: AsyncSession,
    user_id: str,
    provider: str,
    provider_user_id: str,
    organization_id: str,
    provider_email: str | None = None,
) -> UserIdentity:
    """
    Create a new user identity linking a user to an SSO provider.

    Args:
        session: Database session
        user_id: User UUID
        provider: SSO provider name (e.g., 'google')
        provider_user_id: User's ID from the provider
        organization_id: Organization UUID
        provider_email: Email from the provider (optional, for reference)

    Returns:
        Created UserIdentity
    """
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )

    identity = UserIdentity(
        user_id=user_uuid,
        organization_id=org_uuid,
        provider=provider.lower(),
        provider_user_id=provider_user_id,
        provider_email=provider_email,
    )

    session.add(identity)
    await session.commit()
    await session.refresh(identity)

    return identity


async def delete(
    session: AsyncSession,
    identity_id: str,
    organization_id: str,
) -> bool:
    """
    Soft delete a user identity.

    Args:
        session: Database session
        identity_id: UserIdentity UUID
        organization_id: Organization UUID

    Returns:
        True if deleted, False if not found
    """
    identity_uuid = UUID(identity_id) if isinstance(identity_id, str) else identity_id
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )

    result = await session.execute(
        select(UserIdentity).where(
            UserIdentity.id == identity_uuid,
            UserIdentity.organization_id == org_uuid,
            UserIdentity.deleted_time.is_(None),
        )
    )
    identity = result.scalars().first()

    if not identity:
        return False

    identity.deleted_time = datetime.now(timezone.utc)
    await session.commit()

    return True


async def user_has_provider_identity(
    session: AsyncSession,
    user_id: str,
    provider: str,
    organization_id: str,
) -> bool:
    """
    Check if a user has an identity linked to a specific provider.

    Args:
        session: Database session
        user_id: User UUID
        provider: SSO provider name (e.g., 'google')
        organization_id: Organization UUID

    Returns:
        True if identity exists, False otherwise
    """
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )

    result = await session.execute(
        select(UserIdentity).where(
            UserIdentity.organization_id == org_uuid,
            UserIdentity.user_id == user_uuid,
            UserIdentity.provider == provider.lower(),
            UserIdentity.deleted_time.is_(None),
        )
    )
    return result.scalars().first() is not None
