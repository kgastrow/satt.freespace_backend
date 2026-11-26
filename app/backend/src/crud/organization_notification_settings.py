"""
CRUD operations for OrganizationNotificationSettings model.

Each organization has exactly one notification settings record.
"""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.organization_notification_settings import (
    OrganizationNotificationSettings,
)


async def get_organization_notification_settings(
    session: AsyncSession,
    organization_id: str,
) -> Optional[OrganizationNotificationSettings]:
    """
    Get organization notification settings.

    Args:
        session: Database session
        organization_id: Organization UUID string

    Returns:
        The OrganizationNotificationSettings or None if not found
    """
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(OrganizationNotificationSettings).where(
            OrganizationNotificationSettings.organization_id == org_uuid,
            OrganizationNotificationSettings.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_or_create_organization_notification_settings(
    session: AsyncSession,
    organization_id: str,
) -> OrganizationNotificationSettings:
    """
    Get organization notification settings, creating defaults if not exists.

    Args:
        session: Database session
        organization_id: Organization UUID string

    Returns:
        The OrganizationNotificationSettings (existing or newly created)
    """
    settings = await get_organization_notification_settings(session, organization_id)

    if settings:
        return settings

    # Create default settings
    org_uuid = UUID(organization_id)

    settings = OrganizationNotificationSettings(
        organization_id=org_uuid,
        email_enabled=True,
        sms_enabled=False,
        whatsapp_enabled=False,
        in_app_enabled=True,
        # Off until a VAPID keypair exists; see docs/deploy-web-push.md.
        web_push_enabled=False,
        notification_retention_days=90,
        sms_rate_limit=1000,
        whatsapp_rate_limit=1000,
    )

    session.add(settings)
    try:
        await session.commit()
        await session.refresh(settings)
    except Exception as e:
        await session.rollback()
        raise e

    return settings


async def update_organization_notification_settings(
    session: AsyncSession,
    organization_id: str,
    settings_data: dict[str, Any],
) -> OrganizationNotificationSettings:
    """
    Update organization notification settings.

    Creates default settings if they don't exist, then updates.

    Args:
        session: Database session
        organization_id: Organization UUID string
        settings_data: Fields to update (all optional):
            - email_enabled, sms_enabled, whatsapp_enabled
            - sms_provider, whatsapp_provider
            - notification_retention_days
            - sms_rate_limit, whatsapp_rate_limit
            - email_sender_name, sms_sender_id

    Returns:
        The updated OrganizationNotificationSettings
    """
    # Get or create settings
    settings = await get_or_create_organization_notification_settings(
        session, organization_id
    )

    # Update allowed fields
    updatable_fields = [
        "email_enabled",
        "sms_enabled",
        "whatsapp_enabled",
        "in_app_enabled",
        "web_push_enabled",
        "sms_provider",
        "whatsapp_provider",
        "notification_retention_days",
        "sms_rate_limit",
        "whatsapp_rate_limit",
        "email_sender_name",
        "sms_sender_id",
    ]

    for field in updatable_fields:
        if field in settings_data and settings_data[field] is not None:
            setattr(settings, field, settings_data[field])

    try:
        await session.commit()
        await session.refresh(settings)
    except Exception as e:
        await session.rollback()
        raise e

    return settings
