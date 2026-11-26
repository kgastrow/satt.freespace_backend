"""
Notification preference checker service.

Checks user preferences to determine if a notification should be sent
based on organization settings, user channel preferences, category preferences,
and quiet hours.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID

import pytz  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger as logger


class SkipReason(Enum):
    """Reasons why a notification might be skipped."""

    ORG_CHANNEL_DISABLED = "organization_channel_disabled"
    USER_CHANNEL_DISABLED = "user_channel_disabled"
    USER_CATEGORY_DISABLED = "user_category_disabled"
    QUIET_HOURS = "quiet_hours_active"


@dataclass
class PreferenceCheckResult:
    """Result of a preference check for sending a notification."""

    allowed: bool
    skip_reason: Optional[SkipReason] = None
    fallback_channel: Optional[str] = (
        None  # Suggest alternative channel if primary blocked
    )


class PreferenceChecker:
    """
    Check if a notification should be sent based on user preferences.

    Implements the preference resolution logic:
    1. Mandatory check: Is the notification category user_configurable=False? -> Always send
    2. Organization check: Is the channel enabled for the organization?
    3. User global check: Has the user disabled this channel entirely?
    4. User category check: Has the user disabled this category for this channel?
    5. Quiet hours check: Is it within quiet hours AND notification is not urgent?
    """

    async def check_can_send(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        channel: str,
        category_code: Optional[str] = None,
        is_urgent: bool = False,
    ) -> PreferenceCheckResult:
        """
        Check all preference levels to determine if notification can be sent.

        Args:
            session: Database session
            user_id: User ID to check preferences for
            organization_id: Organization ID for tenant context
            channel: Notification channel ('email', 'sms', 'whatsapp', 'in_app')
            category_code: Optional notification category code
            is_urgent: If True, bypasses quiet hours check

        Returns:
            PreferenceCheckResult with allowed=True if notification should proceed,
            or allowed=False with skip_reason explaining why it was blocked.
        """
        user_uuid = UUID(user_id)
        org_uuid = UUID(organization_id)

        # 1. Check if category is mandatory (user_configurable=False)
        if category_code:
            category = await self._get_category(session, org_uuid, category_code)
            if category and not category.user_configurable:
                return PreferenceCheckResult(allowed=True)

        # 2. Check organization channel settings
        org_settings = await self._get_org_settings(session, org_uuid)
        if org_settings and not self._is_channel_enabled_for_org(org_settings, channel):
            return PreferenceCheckResult(
                allowed=False, skip_reason=SkipReason.ORG_CHANNEL_DISABLED
            )

        # 3. Check user global channel preference
        user_pref = await self._get_user_preference(session, user_uuid, org_uuid)
        if user_pref and not self._is_channel_enabled_for_user(user_pref, channel):
            return PreferenceCheckResult(
                allowed=False,
                skip_reason=SkipReason.USER_CHANNEL_DISABLED,
                fallback_channel=self._suggest_fallback(user_pref, channel),
            )

        # 4. Check user category preference
        if category_code:
            cat_pref = await self._get_user_category_preference(
                session, user_uuid, org_uuid, category_code
            )
            if cat_pref and not self._is_channel_enabled_for_category(
                cat_pref, channel
            ):
                return PreferenceCheckResult(
                    allowed=False, skip_reason=SkipReason.USER_CATEGORY_DISABLED
                )

        # 5. Check quiet hours (skip for urgent notifications)
        if not is_urgent and user_pref and user_pref.quiet_hours_enabled:
            if self._is_within_quiet_hours(user_pref):
                return PreferenceCheckResult(
                    allowed=False, skip_reason=SkipReason.QUIET_HOURS
                )

        return PreferenceCheckResult(allowed=True)

    async def get_effective_recipient(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        channel: str,
    ) -> Optional[str]:
        """
        Get the effective recipient address from user profile.

        Args:
            session: Database session
            user_id: User ID
            organization_id: Organization ID for tenant context
            channel: Notification channel ('email', 'sms', 'whatsapp', 'in_app')

        Returns:
            Recipient address (email or phone number) or None if not available.
        """
        # Import here to avoid circular imports
        from src.models.user import User

        user_uuid = UUID(user_id)
        org_uuid = UUID(organization_id)

        # Get user profile
        result = await session.execute(
            select(User).where(
                User.id == user_uuid,
                User.organization_id == org_uuid,
                User.deleted_time.is_(None),
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        if channel == "email":
            return user.email

        elif channel in ("sms", "whatsapp"):
            return user.phone

        return None

    async def _get_category(
        self,
        session: AsyncSession,
        organization_id: UUID,
        category_code: str,
    ):
        """Get notification category by code, checking org-specific first, then system."""
        # Import here to avoid circular imports
        try:
            from src.models.notification_category import NotificationCategory
        except ImportError:
            logger.warning("NotificationCategory model not yet available")
            return None

        # Try org-specific category first
        result = await session.execute(
            select(NotificationCategory).where(
                NotificationCategory.organization_id == organization_id,
                NotificationCategory.code == category_code,
                NotificationCategory.deleted_time.is_(None),
            )
        )
        category = result.scalar_one_or_none()

        if category:
            return category

        # Fallback to system category (organization_id is NULL)
        result = await session.execute(
            select(NotificationCategory).where(
                NotificationCategory.organization_id.is_(None),
                NotificationCategory.code == category_code,
                NotificationCategory.deleted_time.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _get_org_settings(
        self,
        session: AsyncSession,
        organization_id: UUID,
    ):
        """Get organization notification settings."""
        try:
            from src.models.organization_notification_settings import (
                OrganizationNotificationSettings,
            )
        except ImportError:
            logger.warning("OrganizationNotificationSettings model not yet available")
            return None

        result = await session.execute(
            select(OrganizationNotificationSettings).where(
                OrganizationNotificationSettings.organization_id == organization_id
            )
        )
        return result.scalar_one_or_none()

    async def _get_user_preference(
        self,
        session: AsyncSession,
        user_id: UUID,
        organization_id: UUID,
    ):
        """Get user notification preferences."""
        try:
            from src.models.user_notification_preference import (
                UserNotificationPreference,
            )
        except ImportError:
            logger.warning("UserNotificationPreference model not yet available")
            return None

        result = await session.execute(
            select(UserNotificationPreference).where(
                UserNotificationPreference.user_id == user_id,
                UserNotificationPreference.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_user_category_preference(
        self,
        session: AsyncSession,
        user_id: UUID,
        organization_id: UUID,
        category_code: str,
    ):
        """Get user preference for a specific notification category."""
        try:
            from src.models.user_notification_preference import UserCategoryPreference
        except ImportError:
            logger.warning("UserCategoryPreference model not yet available")
            return None

        # First get the category
        category = await self._get_category(session, organization_id, category_code)
        if not category:
            return None

        result = await session.execute(
            select(UserCategoryPreference).where(
                UserCategoryPreference.user_id == user_id,
                UserCategoryPreference.organization_id == organization_id,
                UserCategoryPreference.category_id == category.id,
            )
        )
        return result.scalar_one_or_none()

    def _is_channel_enabled_for_org(self, org_settings, channel: str) -> bool:
        """Check if a channel is enabled at the organization level."""
        if channel == "email":
            return org_settings.email_enabled
        elif channel == "sms":
            return org_settings.sms_enabled
        elif channel == "whatsapp":
            return org_settings.whatsapp_enabled
        elif channel == "in_app":
            return org_settings.in_app_enabled
        elif channel == "web_push":
            return getattr(org_settings, "web_push_enabled", True)
        return True  # Unknown channels default to enabled

    def _is_channel_enabled_for_user(self, user_pref, channel: str) -> bool:
        """Check if a channel is enabled for the user globally."""
        if channel == "email":
            return user_pref.email_enabled
        elif channel == "sms":
            return user_pref.sms_enabled
        elif channel == "whatsapp":
            return user_pref.whatsapp_enabled
        elif channel == "in_app":
            return user_pref.in_app_enabled
        elif channel == "web_push":
            return getattr(user_pref, "web_push_enabled", True)
        return True  # Unknown channels default to enabled

    def _is_channel_enabled_for_category(self, cat_pref, channel: str) -> bool:
        """Check if a channel is enabled for a specific category."""
        if channel == "email":
            return cat_pref.email_enabled
        elif channel == "sms":
            return cat_pref.sms_enabled
        elif channel == "whatsapp":
            return cat_pref.whatsapp_enabled
        elif channel == "in_app":
            return cat_pref.in_app_enabled
        elif channel == "web_push":
            return getattr(cat_pref, "web_push_enabled", True)
        return True  # Unknown channels default to enabled

    def _suggest_fallback(self, user_pref, blocked_channel: str) -> Optional[str]:
        """Suggest an alternative channel if the primary is blocked."""
        # Priority order for fallback suggestions
        channel_priority = ["email", "sms", "whatsapp", "in_app"]

        for channel in channel_priority:
            if channel == blocked_channel:
                continue
            if self._is_channel_enabled_for_user(user_pref, channel):
                return channel

        return None

    def _is_within_quiet_hours(self, user_pref) -> bool:
        """
        Check if current time is within the user's quiet hours.

        Handles timezone conversion and overnight quiet hours
        (e.g., 22:00 to 07:00).
        """
        if not user_pref.quiet_hours_enabled:
            return False

        if not user_pref.quiet_hours_start or not user_pref.quiet_hours_end:
            return False

        # Get current time in user's timezone
        try:
            user_tz = pytz.timezone(user_pref.quiet_hours_timezone or "UTC")
        except pytz.exceptions.UnknownTimeZoneError:
            user_tz = pytz.UTC

        now = datetime.now(timezone.utc).astimezone(user_tz)
        current_time = now.time()

        start = user_pref.quiet_hours_start
        end = user_pref.quiet_hours_end

        # Handle overnight quiet hours (e.g., 22:00 to 07:00)
        if start <= end:
            # Same day quiet hours (e.g., 14:00 to 18:00)
            return start <= current_time <= end
        else:
            # Overnight quiet hours (e.g., 22:00 to 07:00)
            return current_time >= start or current_time <= end

    async def batch_load_preferences(
        self,
        session: AsyncSession,
        user_ids: list[str],
        organization_id: str,
    ) -> dict[str, "PreferenceData"]:
        """
        Batch load user notification preferences for multiple users.

        This avoids N+1 queries when processing bulk notifications by loading
        all preferences for the batch upfront.

        Args:
            session: Database session
            user_ids: List of user IDs to load preferences for
            organization_id: Organization ID for tenant context

        Returns:
            Dict mapping user_id -> PreferenceData with org_settings, user_pref
        """
        if not user_ids:
            return {}

        org_uuid = UUID(organization_id)
        user_uuids = [UUID(uid) for uid in user_ids]

        # Load organization settings (same for all users in org)
        org_settings = await self._get_org_settings(session, org_uuid)

        # Load all user preferences in one query
        try:
            from src.models.user_notification_preference import (
                UserNotificationPreference,
            )

            result = await session.execute(
                select(UserNotificationPreference).where(
                    UserNotificationPreference.user_id.in_(user_uuids),
                    UserNotificationPreference.organization_id == org_uuid,
                )
            )
            user_prefs_list = result.scalars().all()
            user_prefs_map = {str(p.user_id): p for p in user_prefs_list}
        except ImportError:
            user_prefs_map = {}

        # Build result
        result_map = {}
        for user_id in user_ids:
            result_map[user_id] = PreferenceData(
                org_settings=org_settings,
                user_pref=user_prefs_map.get(user_id),
            )

        return result_map

    def check_can_send_with_cached_prefs(
        self,
        channel: str,
        pref_data: "PreferenceData",
        category_is_mandatory: bool = False,
        is_urgent: bool = False,
    ) -> PreferenceCheckResult:
        """
        Check if notification can be sent using pre-loaded preference data.

        This is the non-async version that uses cached preferences instead of
        making database queries. Use batch_load_preferences() first.

        Args:
            channel: Notification channel ('email', 'sms', 'whatsapp', 'in_app')
            pref_data: Pre-loaded PreferenceData from batch_load_preferences
            category_is_mandatory: Whether the category is mandatory (user_configurable=False)
            is_urgent: If True, bypasses quiet hours check

        Returns:
            PreferenceCheckResult with allowed=True if notification should proceed
        """
        # 1. Mandatory categories always send
        if category_is_mandatory:
            return PreferenceCheckResult(allowed=True)

        # 2. Check organization channel settings
        if pref_data.org_settings and not self._is_channel_enabled_for_org(
            pref_data.org_settings, channel
        ):
            return PreferenceCheckResult(
                allowed=False, skip_reason=SkipReason.ORG_CHANNEL_DISABLED
            )

        # 3. Check user global channel preference
        if pref_data.user_pref and not self._is_channel_enabled_for_user(
            pref_data.user_pref, channel
        ):
            return PreferenceCheckResult(
                allowed=False,
                skip_reason=SkipReason.USER_CHANNEL_DISABLED,
                fallback_channel=self._suggest_fallback(pref_data.user_pref, channel),
            )

        # 4. Check quiet hours (skip for urgent notifications)
        if (
            not is_urgent
            and pref_data.user_pref
            and pref_data.user_pref.quiet_hours_enabled
        ):
            if self._is_within_quiet_hours(pref_data.user_pref):
                return PreferenceCheckResult(
                    allowed=False, skip_reason=SkipReason.QUIET_HOURS
                )

        return PreferenceCheckResult(allowed=True)


@dataclass
class PreferenceData:
    """Pre-loaded preference data for a user."""

    org_settings: Optional[Any] = None
    user_pref: Optional[Any] = None


# Singleton instance
preference_checker = PreferenceChecker()
