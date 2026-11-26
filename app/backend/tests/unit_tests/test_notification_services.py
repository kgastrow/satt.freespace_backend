"""
Unit tests for notification services.
"""

from datetime import datetime, time
from uuid import uuid4

import pytest

from src.crud.organization_notification_settings import (
    get_or_create_organization_notification_settings,
    update_organization_notification_settings,
)
from src.crud.user_notification_preference import (
    get_categories_with_preferences,
    get_or_create_user_preference,
    update_user_category_preference,
    update_user_preference,
)
from src.models.notification_category import NotificationCategory
from src.models.organization_notification_settings import (
    OrganizationNotificationSettings,
)
from src.models.user_notification_preference import (
    UserCategoryPreference,
    UserNotificationPreference,
)


class TestNotificationModels:
    """Tests for notification-related models."""

    @pytest.mark.asyncio
    async def test_create_notification_category(self, async_session, test_organization):
        """Test creating a notification category."""
        category = NotificationCategory(
            organization_id=test_organization.id,
            code="marketing",
            name="Marketing",
            description="Marketing and promotional messages",
            default_enabled=True,
            user_configurable=True,
            display_order=1,
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        assert category.id is not None
        assert category.code == "marketing"
        assert category.name == "Marketing"
        assert category.default_enabled is True
        assert category.user_configurable is True

    @pytest.mark.asyncio
    async def test_create_system_category(self, async_session):
        """Test creating a system-level category (no organization)."""
        category = NotificationCategory(
            organization_id=None,  # System category
            code="security",
            name="Security Alerts",
            description="Security-related notifications",
            default_enabled=True,
            user_configurable=False,  # Mandatory
            display_order=0,
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        assert category.id is not None
        assert category.organization_id is None
        assert category.user_configurable is False

    @pytest.mark.asyncio
    async def test_create_user_notification_preference(
        self, async_session, test_organization, test_user
    ):
        """Test creating user notification preferences."""
        pref = UserNotificationPreference(
            organization_id=test_organization.id,
            user_id=test_user.id,
            email_enabled=True,
            sms_enabled=False,
            whatsapp_enabled=True,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(7, 0),
            quiet_hours_timezone="America/New_York",
        )
        async_session.add(pref)
        await async_session.commit()
        await async_session.refresh(pref)

        assert pref.id is not None
        assert pref.email_enabled is True
        assert pref.sms_enabled is False
        assert pref.quiet_hours_enabled is True
        assert pref.quiet_hours_start == time(22, 0)
        assert pref.quiet_hours_end == time(7, 0)

    @pytest.mark.asyncio
    async def test_create_category_preference(
        self, async_session, test_organization, test_user
    ):
        """Test creating user preference for a specific category."""
        # First create a category
        category = NotificationCategory(
            organization_id=test_organization.id,
            code="announcements",
            name="Announcements",
            default_enabled=True,
            user_configurable=True,
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        # Create category preference
        cat_pref = UserCategoryPreference(
            organization_id=test_organization.id,
            user_id=test_user.id,
            category_id=category.id,
            email_enabled=True,
            sms_enabled=False,
            whatsapp_enabled=False,
        )
        async_session.add(cat_pref)
        await async_session.commit()
        await async_session.refresh(cat_pref)

        assert cat_pref.id is not None
        assert cat_pref.category_id == category.id
        assert cat_pref.email_enabled is True
        assert cat_pref.sms_enabled is False

    @pytest.mark.asyncio
    async def test_create_organization_notification_settings(
        self, async_session, test_organization
    ):
        """Test creating organization notification settings."""
        settings = OrganizationNotificationSettings(
            organization_id=test_organization.id,
            email_enabled=True,
            sms_enabled=True,
            whatsapp_enabled=False,
            sms_provider="aws_sns",
            notification_retention_days=90,
            sms_rate_limit=1000,
            whatsapp_rate_limit=500,
            email_sender_name="My Organization",
        )
        async_session.add(settings)
        await async_session.commit()
        await async_session.refresh(settings)

        assert settings.id is not None
        assert settings.email_enabled is True
        assert settings.sms_enabled is True
        assert settings.whatsapp_enabled is False
        assert settings.sms_provider == "aws_sns"
        assert settings.notification_retention_days == 90


class TestPreferenceChecker:
    """Tests for preference checking logic."""

    @pytest.mark.asyncio
    async def test_quiet_hours_during(self):
        """Test quiet hours detection."""
        from datetime import time
        from zoneinfo import ZoneInfo

        # Simulate a preference with quiet hours 22:00-07:00
        start_time = time(22, 0)
        end_time = time(7, 0)
        tz = ZoneInfo("America/New_York")

        # Check if a time is during quiet hours
        def is_in_quiet_hours(current_time: datetime, start: time, end: time) -> bool:
            """Check if current time is within quiet hours."""
            current = current_time.time()

            if start < end:
                # Same day range (e.g., 09:00-17:00)
                return start <= current <= end
            else:
                # Overnight range (e.g., 22:00-07:00)
                return current >= start or current <= end

        # 23:00 should be in quiet hours
        test_time = datetime(2025, 1, 15, 23, 0, tzinfo=tz)
        assert is_in_quiet_hours(test_time, start_time, end_time) is True

        # 06:00 should be in quiet hours
        test_time = datetime(2025, 1, 15, 6, 0, tzinfo=tz)
        assert is_in_quiet_hours(test_time, start_time, end_time) is True

        # 12:00 should NOT be in quiet hours
        test_time = datetime(2025, 1, 15, 12, 0, tzinfo=tz)
        assert is_in_quiet_hours(test_time, start_time, end_time) is False

        # 08:00 should NOT be in quiet hours
        test_time = datetime(2025, 1, 15, 8, 0, tzinfo=tz)
        assert is_in_quiet_hours(test_time, start_time, end_time) is False


class TestTemplateRenderer:
    """Tests for notification template rendering."""

    def test_simple_variable_substitution(self):
        """Test simple template variable substitution."""

        def render_template(template: str, variables: dict) -> str:
            """Simple template rendering."""
            result = template
            for key, value in variables.items():
                result = result.replace(f"{{{{{key}}}}}", str(value))
            return result

        template = "Hello {{name}}, your order #{{order_id}} is ready!"
        variables = {"name": "John", "order_id": "12345"}

        rendered = render_template(template, variables)
        assert rendered == "Hello John, your order #12345 is ready!"

    def test_missing_variable(self):
        """Test handling of missing template variables."""

        def render_template(template: str, variables: dict) -> str:
            """Simple template rendering with missing variable handling."""
            result = template
            for key, value in variables.items():
                result = result.replace(f"{{{{{key}}}}}", str(value))
            return result

        template = "Hello {{name}}, your balance is {{balance}}"
        variables = {"name": "John"}  # Missing 'balance'

        rendered = render_template(template, variables)
        # The placeholder should remain
        assert "{{balance}}" in rendered
        assert rendered == "Hello John, your balance is {{balance}}"


# =============================================================================
# User Notification Preference CRUD Tests
# =============================================================================


class TestUserNotificationPreferenceCrud:
    """Tests for user notification preference CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_or_create_user_preference_creates_new(
        self, async_session, test_organization, test_user
    ):
        """Test that get_or_create creates default preferences if none exist."""
        org_id = str(test_organization.id)
        user_id = str(test_user.id)

        preference = await get_or_create_user_preference(
            session=async_session,
            user_id=user_id,
            organization_id=org_id,
        )

        assert preference is not None
        assert preference.user_id == test_user.id
        assert preference.organization_id == test_organization.id
        # Check defaults
        assert preference.email_enabled is True
        assert preference.sms_enabled is True
        assert preference.whatsapp_enabled is True
        assert preference.quiet_hours_enabled is False
        assert preference.quiet_hours_timezone == "UTC"

    @pytest.mark.asyncio
    async def test_get_or_create_user_preference_returns_existing(
        self, async_session, test_organization, test_user
    ):
        """Test that get_or_create returns existing preferences."""
        org_id = str(test_organization.id)
        user_id = str(test_user.id)

        # Create preference first
        pref = UserNotificationPreference(
            organization_id=test_organization.id,
            user_id=test_user.id,
            email_enabled=False,
            sms_enabled=False,
            whatsapp_enabled=False,
            quiet_hours_enabled=True,
            quiet_hours_timezone="America/New_York",
        )
        async_session.add(pref)
        await async_session.commit()

        # Now get_or_create should return existing
        preference = await get_or_create_user_preference(
            session=async_session,
            user_id=user_id,
            organization_id=org_id,
        )

        assert preference.email_enabled is False
        assert preference.quiet_hours_enabled is True
        assert preference.quiet_hours_timezone == "America/New_York"

    @pytest.mark.asyncio
    async def test_update_user_preference(
        self, async_session, test_organization, test_user
    ):
        """Test updating user preferences."""
        org_id = str(test_organization.id)
        user_id = str(test_user.id)

        # Update should create if not exists
        preference = await update_user_preference(
            session=async_session,
            user_id=user_id,
            organization_id=org_id,
            preference_data={
                "email_enabled": False,
                "sms_enabled": True,
                "quiet_hours_enabled": True,
                "quiet_hours_start": time(22, 0),
                "quiet_hours_end": time(7, 0),
            },
        )

        assert preference.email_enabled is False
        assert preference.sms_enabled is True
        assert preference.quiet_hours_enabled is True
        assert preference.quiet_hours_start == time(22, 0)
        assert preference.quiet_hours_end == time(7, 0)

    @pytest.mark.asyncio
    async def test_update_user_category_preference_creates_new(
        self, async_session, test_organization, test_user
    ):
        """Test creating a new category preference."""
        org_id = str(test_organization.id)
        user_id = str(test_user.id)

        # Create a configurable category
        category = NotificationCategory(
            organization_id=test_organization.id,
            code="test_cat",
            name="Test Category",
            default_enabled=True,
            user_configurable=True,
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        preference = await update_user_category_preference(
            session=async_session,
            user_id=user_id,
            category_id=str(category.id),
            organization_id=org_id,
            preference_data={
                "email_enabled": False,
                "sms_enabled": True,
            },
        )

        assert preference.category_id == category.id
        assert preference.email_enabled is False
        assert preference.sms_enabled is True

    @pytest.mark.asyncio
    async def test_update_non_configurable_category_fails(
        self, async_session, test_organization, test_user
    ):
        """Test that updating non-configurable category raises error."""
        org_id = str(test_organization.id)
        user_id = str(test_user.id)

        # Create a non-configurable category
        category = NotificationCategory(
            organization_id=test_organization.id,
            code="mandatory_cat",
            name="Mandatory Category",
            default_enabled=True,
            user_configurable=False,  # Not configurable
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        with pytest.raises(ValueError, match="not user configurable"):
            await update_user_category_preference(
                session=async_session,
                user_id=user_id,
                category_id=str(category.id),
                organization_id=org_id,
                preference_data={"email_enabled": False},
            )

    @pytest.mark.asyncio
    async def test_update_nonexistent_category_fails(
        self, async_session, test_organization, test_user
    ):
        """Test that updating nonexistent category raises error."""
        org_id = str(test_organization.id)
        user_id = str(test_user.id)
        fake_category_id = str(uuid4())

        with pytest.raises(ValueError, match="not found"):
            await update_user_category_preference(
                session=async_session,
                user_id=user_id,
                category_id=fake_category_id,
                organization_id=org_id,
                preference_data={"email_enabled": False},
            )

    @pytest.mark.asyncio
    async def test_get_categories_with_preferences(
        self, async_session, test_organization, test_user
    ):
        """Test getting categories with user preferences."""
        org_id = str(test_organization.id)
        user_id = str(test_user.id)

        # Create categories
        cat1 = NotificationCategory(
            organization_id=test_organization.id,
            code="cat1",
            name="Category 1",
            default_enabled=True,
            user_configurable=True,
            display_order=1,
        )
        cat2 = NotificationCategory(
            organization_id=test_organization.id,
            code="cat2",
            name="Category 2",
            default_enabled=False,
            user_configurable=True,
            display_order=2,
        )
        async_session.add(cat1)
        async_session.add(cat2)
        await async_session.commit()
        await async_session.refresh(cat1)
        await async_session.refresh(cat2)

        # Create preference for cat1 only
        pref = UserCategoryPreference(
            organization_id=test_organization.id,
            user_id=test_user.id,
            category_id=cat1.id,
            email_enabled=False,
            sms_enabled=True,
            whatsapp_enabled=True,
        )
        async_session.add(pref)
        await async_session.commit()

        # Get categories with preferences
        result = await get_categories_with_preferences(
            session=async_session,
            user_id=user_id,
            organization_id=org_id,
        )

        assert len(result) >= 2

        # Find cat1 result - should have user's preference
        cat1_result = next(r for r in result if r["category"].code == "cat1")
        assert cat1_result["email_enabled"] is False  # User preference
        assert cat1_result["sms_enabled"] is True

        # Find cat2 result - should have default
        cat2_result = next(r for r in result if r["category"].code == "cat2")
        assert cat2_result["email_enabled"] is False  # Default (default_enabled=False)


# =============================================================================
# Organization Notification Settings CRUD Tests
# =============================================================================


class TestOrganizationNotificationSettingsCrud:
    """Tests for organization notification settings CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_or_create_creates_default(
        self, async_session, test_organization
    ):
        """Test that get_or_create creates default settings if none exist."""
        org_id = str(test_organization.id)

        settings = await get_or_create_organization_notification_settings(
            session=async_session,
            organization_id=org_id,
        )

        assert settings is not None
        assert settings.organization_id == test_organization.id
        # Check defaults
        assert settings.email_enabled is True
        assert settings.sms_enabled is False
        assert settings.whatsapp_enabled is False
        assert settings.notification_retention_days == 90
        assert settings.sms_rate_limit == 1000
        assert settings.whatsapp_rate_limit == 1000

    @pytest.mark.asyncio
    async def test_get_or_create_returns_existing(
        self, async_session, test_organization
    ):
        """Test that get_or_create returns existing settings."""
        org_id = str(test_organization.id)

        # Create settings first
        existing = OrganizationNotificationSettings(
            organization_id=test_organization.id,
            email_enabled=False,
            sms_enabled=True,
            whatsapp_enabled=True,
            notification_retention_days=30,
        )
        async_session.add(existing)
        await async_session.commit()

        # Now get_or_create should return existing
        settings = await get_or_create_organization_notification_settings(
            session=async_session,
            organization_id=org_id,
        )

        assert settings.email_enabled is False
        assert settings.sms_enabled is True
        assert settings.notification_retention_days == 30

    @pytest.mark.asyncio
    async def test_update_organization_settings(self, async_session, test_organization):
        """Test updating organization notification settings."""
        org_id = str(test_organization.id)

        settings = await update_organization_notification_settings(
            session=async_session,
            organization_id=org_id,
            settings_data={
                "email_enabled": False,
                "sms_enabled": True,
                "sms_provider": "twilio",
                "notification_retention_days": 60,
                "sms_rate_limit": 500,
            },
        )

        assert settings.email_enabled is False
        assert settings.sms_enabled is True
        assert settings.sms_provider == "twilio"
        assert settings.notification_retention_days == 60
        assert settings.sms_rate_limit == 500

    @pytest.mark.asyncio
    async def test_update_partial_settings(self, async_session, test_organization):
        """Test that partial updates don't affect other fields."""
        org_id = str(test_organization.id)

        # Create initial settings
        await update_organization_notification_settings(
            session=async_session,
            organization_id=org_id,
            settings_data={
                "email_enabled": True,
                "sms_enabled": True,
                "notification_retention_days": 90,
            },
        )

        # Partial update
        updated = await update_organization_notification_settings(
            session=async_session,
            organization_id=org_id,
            settings_data={
                "email_enabled": False,
            },
        )

        assert updated.email_enabled is False
        # Other fields should remain unchanged
        assert updated.sms_enabled is True
        assert updated.notification_retention_days == 90
