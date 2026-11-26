"""
CRUD operations for NotificationProvider model.

Notification providers are global (no organization scope) and managed by super admins.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notification_provider import NotificationProvider


async def get_notification_providers(
    session: AsyncSession,
    channel: Optional[str] = None,
    include_inactive: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[NotificationProvider], int]:
    """
    Get all notification providers.

    Args:
        session: Database session
        channel: Optional filter by channel (sms, whatsapp, email)
        include_inactive: Include inactive providers
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of providers, total count)
    """
    conditions: list[ColumnElement[bool]] = [
        NotificationProvider.deleted_time.is_(None)
    ]

    if channel:
        conditions.append(NotificationProvider.channel == channel)

    if not include_inactive:
        conditions.append(NotificationProvider.is_active.is_(True))

    base_query = select(NotificationProvider).where(*conditions)

    # Count query
    count_query = select(func.count()).select_from(base_query.subquery())
    count_result = await session.execute(count_query)
    total_count = count_result.scalar() or 0

    # Data query
    data_query = (
        base_query.order_by(
            NotificationProvider.channel.asc(),
            NotificationProvider.is_default.desc(),
            NotificationProvider.name.asc(),
        )
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(data_query)
    providers = result.scalars().all()

    return list(providers), total_count


async def get_notification_provider_by_id(
    session: AsyncSession,
    provider_id: str,
) -> Optional[NotificationProvider]:
    """
    Get a notification provider by ID.

    Args:
        session: Database session
        provider_id: Provider UUID string

    Returns:
        NotificationProvider or None if not found
    """
    provider_uuid = UUID(provider_id)

    result = await session.execute(
        select(NotificationProvider).where(
            NotificationProvider.id == provider_uuid,
            NotificationProvider.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_default_provider(
    session: AsyncSession,
    channel: str,
) -> Optional[NotificationProvider]:
    """
    Get the default provider for a channel.

    Args:
        session: Database session
        channel: Channel type (sms, whatsapp, email)

    Returns:
        Default NotificationProvider or None
    """
    result = await session.execute(
        select(NotificationProvider).where(
            NotificationProvider.channel == channel,
            NotificationProvider.is_default.is_(True),
            NotificationProvider.is_active.is_(True),
            NotificationProvider.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def create_notification_provider(
    session: AsyncSession,
    provider_data: dict[str, Any],
) -> NotificationProvider:
    """
    Create a new notification provider.

    Args:
        session: Database session
        provider_data: Provider data including:
            - name: Provider name (required)
            - channel: Channel type (required)
            - config: Provider configuration (required)
            - is_active: Whether active (default: True)
            - is_default: Whether default for channel (default: False)

    Returns:
        The created NotificationProvider

    Raises:
        ValueError: If provider with same name and channel exists
    """
    # Check for existing provider with same name and channel
    existing_result = await session.execute(
        select(NotificationProvider).where(
            NotificationProvider.name == provider_data["name"],
            NotificationProvider.channel == provider_data["channel"],
            NotificationProvider.deleted_time.is_(None),
        )
    )
    existing = existing_result.scalars().first()

    if existing:
        raise ValueError(
            f"Provider '{provider_data['name']}' for channel '{provider_data['channel']}' already exists"
        )

    provider = NotificationProvider(
        name=provider_data["name"],
        channel=provider_data["channel"],
        config=provider_data["config"],
        is_active=provider_data.get("is_active", True),
        is_default=provider_data.get("is_default", False),
    )

    # If this is set as default, unset any existing default for this channel
    if provider.is_default:
        await _unset_channel_default(session, provider.channel)

    session.add(provider)

    try:
        await session.commit()
        await session.refresh(provider)
    except Exception as e:
        await session.rollback()
        raise e

    return provider


async def update_notification_provider(
    session: AsyncSession,
    provider_id: str,
    provider_data: dict[str, Any],
) -> Optional[NotificationProvider]:
    """
    Update a notification provider.

    Args:
        session: Database session
        provider_id: Provider UUID string
        provider_data: Fields to update

    Returns:
        The updated NotificationProvider or None if not found
    """
    provider = await get_notification_provider_by_id(session, provider_id)

    if not provider:
        return None

    updatable_fields = ["name", "config", "is_active", "is_default"]

    for field in updatable_fields:
        if field in provider_data:
            setattr(provider, field, provider_data[field])

    # If setting as default, unset any existing default
    if provider_data.get("is_default"):
        await _unset_channel_default(session, provider.channel, exclude_id=provider.id)

    try:
        await session.commit()
        await session.refresh(provider)
    except Exception as e:
        await session.rollback()
        raise e

    return provider


async def deactivate_notification_provider(
    session: AsyncSession,
    provider_id: str,
) -> Optional[NotificationProvider]:
    """
    Soft delete a notification provider.

    Args:
        session: Database session
        provider_id: Provider UUID string

    Returns:
        The deactivated NotificationProvider or None if not found
    """
    provider = await get_notification_provider_by_id(session, provider_id)

    if not provider:
        return None

    provider.deleted_time = datetime.now(timezone.utc)
    provider.is_active = False
    provider.is_default = False

    try:
        await session.commit()
        await session.refresh(provider)
    except Exception as e:
        await session.rollback()
        raise e

    return provider


async def _unset_channel_default(
    session: AsyncSession,
    channel: str,
    exclude_id: Optional[UUID] = None,
) -> None:
    """
    Unset the default flag for all providers of a channel.

    Args:
        session: Database session
        channel: Channel type
        exclude_id: Optional provider ID to exclude from update
    """
    conditions: list[ColumnElement[bool]] = [
        NotificationProvider.channel == channel,
        NotificationProvider.is_default.is_(True),
        NotificationProvider.deleted_time.is_(None),
    ]

    if exclude_id:
        conditions.append(NotificationProvider.id != exclude_id)

    result = await session.execute(select(NotificationProvider).where(*conditions))
    providers = result.scalars().all()

    for provider in providers:
        provider.is_default = False
