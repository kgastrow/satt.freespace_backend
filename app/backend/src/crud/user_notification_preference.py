"""
CRUD operations for UserNotificationPreference and UserCategoryPreference models.

All functions filter by organization_id for multi-tenancy isolation.
"""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notification_category import NotificationCategory
from src.models.user_notification_preference import (
    UserCategoryPreference,
    UserNotificationPreference,
)


async def get_user_preference(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
) -> Optional[UserNotificationPreference]:
    """
    Get user notification preferences.

    Args:
        session: Database session
        user_id: User UUID string
        organization_id: Organization UUID string

    Returns:
        The UserNotificationPreference or None if not found
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    result = await session.execute(
        select(UserNotificationPreference).where(
            UserNotificationPreference.organization_id == org_uuid,
            UserNotificationPreference.user_id == user_uuid,
            UserNotificationPreference.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_or_create_user_preference(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
) -> UserNotificationPreference:
    """
    Get user notification preferences, creating default if not exists.

    Args:
        session: Database session
        user_id: User UUID string
        organization_id: Organization UUID string

    Returns:
        The UserNotificationPreference (existing or newly created)
    """
    preference = await get_user_preference(session, user_id, organization_id)

    if preference:
        return preference

    # Create default preferences
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    preference = UserNotificationPreference(
        organization_id=org_uuid,
        user_id=user_uuid,
        email_enabled=True,
        sms_enabled=True,
        whatsapp_enabled=True,
        in_app_enabled=True,
        # Off by default: pushing to a device the user has not subscribed
        # delivers nothing, so the account gate opens only when they opt in.
        web_push_enabled=False,
        quiet_hours_enabled=False,
        quiet_hours_timezone="UTC",
    )

    session.add(preference)
    try:
        await session.commit()
        await session.refresh(preference)
    except Exception as e:
        await session.rollback()
        raise e

    return preference


async def update_user_preference(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
    preference_data: dict[str, Any],
) -> UserNotificationPreference:
    """
    Update user notification preferences.

    Creates default preferences if they don't exist, then updates.

    Args:
        session: Database session
        user_id: User UUID string
        organization_id: Organization UUID string
        preference_data: Fields to update (all optional):
            - email_enabled, sms_enabled, whatsapp_enabled, in_app_enabled
            - quiet_hours_enabled, quiet_hours_start, quiet_hours_end, quiet_hours_timezone

    Returns:
        The updated UserNotificationPreference
    """
    # Get or create preference
    preference = await get_or_create_user_preference(session, user_id, organization_id)

    # Update allowed fields
    updatable_fields = [
        "email_enabled",
        "sms_enabled",
        "whatsapp_enabled",
        "in_app_enabled",
        "web_push_enabled",
        "quiet_hours_enabled",
        "quiet_hours_start",
        "quiet_hours_end",
        "quiet_hours_timezone",
    ]

    for field in updatable_fields:
        if field in preference_data and preference_data[field] is not None:
            setattr(preference, field, preference_data[field])

    try:
        await session.commit()
        await session.refresh(preference)
    except Exception as e:
        await session.rollback()
        raise e

    return preference


# =============================================================================
# Category Preferences
# =============================================================================


async def get_user_category_preference(
    session: AsyncSession,
    user_id: str,
    category_id: str,
    organization_id: str,
) -> Optional[UserCategoryPreference]:
    """
    Get user's preference for a specific category.

    Args:
        session: Database session
        user_id: User UUID string
        category_id: Category UUID string
        organization_id: Organization UUID string

    Returns:
        The UserCategoryPreference or None if not found
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)
    cat_uuid = UUID(category_id)

    result = await session.execute(
        select(UserCategoryPreference).where(
            UserCategoryPreference.organization_id == org_uuid,
            UserCategoryPreference.user_id == user_uuid,
            UserCategoryPreference.category_id == cat_uuid,
            UserCategoryPreference.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_user_category_preferences(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
) -> list[UserCategoryPreference]:
    """
    Get all category preferences for a user.

    Args:
        session: Database session
        user_id: User UUID string
        organization_id: Organization UUID string

    Returns:
        List of UserCategoryPreference
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    result = await session.execute(
        select(UserCategoryPreference).where(
            UserCategoryPreference.organization_id == org_uuid,
            UserCategoryPreference.user_id == user_uuid,
            UserCategoryPreference.deleted_time.is_(None),
        )
    )
    return list(result.scalars().all())


async def update_user_category_preference(
    session: AsyncSession,
    user_id: str,
    category_id: str,
    organization_id: str,
    preference_data: dict[str, Any],
) -> UserCategoryPreference:
    """
    Update user's preference for a specific category.

    Creates the preference if it doesn't exist.

    Args:
        session: Database session
        user_id: User UUID string
        category_id: Category UUID string
        organization_id: Organization UUID string
        preference_data: Fields to update:
            - email_enabled, sms_enabled, whatsapp_enabled, in_app_enabled

    Returns:
        The updated UserCategoryPreference

    Raises:
        ValueError: If category is not user_configurable
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)
    cat_uuid = UUID(category_id)

    # Verify category exists and is configurable
    from sqlalchemy import or_

    cat_result = await session.execute(
        select(NotificationCategory).where(
            NotificationCategory.id == cat_uuid,
            or_(
                NotificationCategory.organization_id == org_uuid,
                NotificationCategory.organization_id.is_(None),
            ),
            NotificationCategory.deleted_time.is_(None),
        )
    )
    category = cat_result.scalars().first()

    if not category:
        raise ValueError(f"Category with id {category_id} not found")

    if not category.user_configurable:
        raise ValueError(f"Category '{category.name}' is not user configurable")

    # Get existing preference or create new one
    preference = await get_user_category_preference(
        session, user_id, category_id, organization_id
    )

    if not preference:
        preference = UserCategoryPreference(
            organization_id=org_uuid,
            user_id=user_uuid,
            category_id=cat_uuid,
            email_enabled=category.default_enabled,
            sms_enabled=category.default_enabled,
            whatsapp_enabled=category.default_enabled,
            in_app_enabled=category.default_enabled,
            web_push_enabled=category.default_enabled,
        )
        session.add(preference)

    # Update allowed fields
    updatable_fields = [
        "email_enabled",
        "sms_enabled",
        "whatsapp_enabled",
        "in_app_enabled",
        "web_push_enabled",
    ]

    for field in updatable_fields:
        if field in preference_data and preference_data[field] is not None:
            setattr(preference, field, preference_data[field])

    try:
        await session.commit()
        await session.refresh(preference)
    except Exception as e:
        await session.rollback()
        raise e

    return preference


async def get_categories_with_preferences(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
) -> list[dict[str, Any]]:
    """
    Get all categories with user's preferences.

    Returns categories ordered by display_order, with the user's preference
    for each (or defaults if no preference set).

    Args:
        session: Database session
        user_id: User UUID string
        organization_id: Organization UUID string

    Returns:
        List of dicts with 'category' and preference fields
    """
    from sqlalchemy import or_

    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    # Get all categories available to this organization
    cat_result = await session.execute(
        select(NotificationCategory)
        .where(
            or_(
                NotificationCategory.organization_id == org_uuid,
                NotificationCategory.organization_id.is_(None),
            ),
            NotificationCategory.deleted_time.is_(None),
        )
        .order_by(
            NotificationCategory.display_order.asc(),
            NotificationCategory.name.asc(),
        )
    )
    categories = cat_result.scalars().all()

    # Get user's category preferences
    pref_result = await session.execute(
        select(UserCategoryPreference).where(
            UserCategoryPreference.organization_id == org_uuid,
            UserCategoryPreference.user_id == user_uuid,
            UserCategoryPreference.deleted_time.is_(None),
        )
    )
    user_prefs = {str(p.category_id): p for p in pref_result.scalars().all()}

    # Combine categories with preferences
    result = []
    for category in categories:
        cat_id = str(category.id)
        user_pref = user_prefs.get(cat_id)

        result.append(
            {
                "category": category,
                "email_enabled": (
                    user_pref.email_enabled if user_pref else category.default_enabled
                ),
                "sms_enabled": (
                    user_pref.sms_enabled if user_pref else category.default_enabled
                ),
                "whatsapp_enabled": (
                    user_pref.whatsapp_enabled
                    if user_pref
                    else category.default_enabled
                ),
                "in_app_enabled": (
                    user_pref.in_app_enabled if user_pref else category.default_enabled
                ),
                "web_push_enabled": (
                    user_pref.web_push_enabled
                    if user_pref
                    else category.default_enabled
                ),
            }
        )

    return result
