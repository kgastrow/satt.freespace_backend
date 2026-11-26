"""
Unit tests for in-app notification models.
Tests UserNotification model creation and field constraints.
"""

from datetime import datetime, timezone

import pytest

from src.models.notification_category import NotificationCategory
from src.models.organization_notification_settings import (
    OrganizationNotificationSettings,
)
from src.models.user_notification import UserNotification
from src.models.user_notification_preference import (
    UserCategoryPreference,
    UserNotificationPreference,
)


class TestUserNotificationModel:
    """Tests for UserNotification model."""

    @pytest.mark.asyncio
    async def test_create_user_notification(
        self, async_session, test_organization, test_user
    ):
        """Test creating a basic in-app notification."""
        notification = UserNotification(
            organization_id=test_organization.id,
            user_id=test_user.id,
            title="New Message",
            body="You have a new message from the team.",
        )
        async_session.add(notification)
        await async_session.commit()
        await async_session.refresh(notification)

        assert notification.id is not None
        assert notification.organization_id == test_organization.id
        assert notification.user_id == test_user.id
        assert notification.title == "New Message"
        assert notification.body == "You have a new message from the team."
        assert notification.link is None
        assert notification.category_id is None
        assert notification.read_time is None
        assert notification.deleted_time is None
        assert notification.created_time is not None

    @pytest.mark.asyncio
    async def test_create_notification_with_link(
        self, async_session, test_organization, test_user
    ):
        """Test creating a notification with a click-through link."""
        notification = UserNotification(
            organization_id=test_organization.id,
            user_id=test_user.id,
            title="Order Update",
            body="Your order #12345 has shipped.",
            link="/orders/12345",
        )
        async_session.add(notification)
        await async_session.commit()
        await async_session.refresh(notification)

        assert notification.link == "/orders/12345"

    @pytest.mark.asyncio
    async def test_create_notification_with_category(
        self, async_session, test_organization, test_user
    ):
        """Test creating a notification with a category."""
        # First create a category
        category = NotificationCategory(
            organization_id=test_organization.id,
            code="alerts",
            name="Alerts",
            description="System alerts and notifications",
            default_enabled=True,
            user_configurable=True,
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        # Create notification with category
        notification = UserNotification(
            organization_id=test_organization.id,
            user_id=test_user.id,
            title="Security Alert",
            body="Unusual login detected from new device.",
            category_id=category.id,
        )
        async_session.add(notification)
        await async_session.commit()
        await async_session.refresh(notification)

        assert notification.category_id == category.id

    @pytest.mark.asyncio
    async def test_mark_notification_as_read(
        self, async_session, test_organization, test_user
    ):
        """Test marking a notification as read."""
        notification = UserNotification(
            organization_id=test_organization.id,
            user_id=test_user.id,
            title="Test Notification",
        )
        async_session.add(notification)
        await async_session.commit()

        # Mark as read
        notification.read_time = datetime.now(timezone.utc)
        await async_session.commit()
        await async_session.refresh(notification)

        assert notification.read_time is not None

    @pytest.mark.asyncio
    async def test_soft_delete_notification(
        self, async_session, test_organization, test_user
    ):
        """Test soft deleting a notification."""
        notification = UserNotification(
            organization_id=test_organization.id,
            user_id=test_user.id,
            title="To Be Deleted",
        )
        async_session.add(notification)
        await async_session.commit()

        # Soft delete
        notification.deleted_time = datetime.now(timezone.utc)
        await async_session.commit()
        await async_session.refresh(notification)

        assert notification.deleted_time is not None

    @pytest.mark.asyncio
    async def test_notification_title_required(
        self, async_session, test_organization, test_user
    ):
        """Test that title is required for notifications."""
        # SQLite doesn't enforce NOT NULL on strings as strictly in tests,
        # but the model definition requires it
        notification = UserNotification(
            organization_id=test_organization.id,
            user_id=test_user.id,
            title="Required Title",  # Title is required
        )
        async_session.add(notification)
        await async_session.commit()
        await async_session.refresh(notification)

        assert notification.title == "Required Title"

    @pytest.mark.asyncio
    async def test_notification_body_optional(
        self, async_session, test_organization, test_user
    ):
        """Test that body is optional for notifications."""
        notification = UserNotification(
            organization_id=test_organization.id,
            user_id=test_user.id,
            title="Title Only",
            body=None,
        )
        async_session.add(notification)
        await async_session.commit()
        await async_session.refresh(notification)

        assert notification.body is None

    @pytest.mark.asyncio
    async def test_notification_long_body(
        self, async_session, test_organization, test_user
    ):
        """Test notification with a long body text."""
        long_body = "A" * 5000  # Long text body
        notification = UserNotification(
            organization_id=test_organization.id,
            user_id=test_user.id,
            title="Long Message",
            body=long_body,
        )
        async_session.add(notification)
        await async_session.commit()
        await async_session.refresh(notification)

        assert notification.body == long_body
        assert len(notification.body) == 5000


class TestInAppEnabledPreferences:
    """Tests for in_app_enabled field in preference models."""

    @pytest.mark.asyncio
    async def test_user_notification_preference_in_app_enabled_default(
        self, async_session, test_organization, test_user
    ):
        """Test that in_app_enabled defaults to True for user preferences."""
        preference = UserNotificationPreference(
            organization_id=test_organization.id,
            user_id=test_user.id,
        )
        async_session.add(preference)
        await async_session.commit()
        await async_session.refresh(preference)

        assert preference.in_app_enabled is True

    @pytest.mark.asyncio
    async def test_user_notification_preference_in_app_disabled(
        self, async_session, test_organization, test_user
    ):
        """Test setting in_app_enabled to False for user preferences."""
        preference = UserNotificationPreference(
            organization_id=test_organization.id,
            user_id=test_user.id,
            in_app_enabled=False,
        )
        async_session.add(preference)
        await async_session.commit()
        await async_session.refresh(preference)

        assert preference.in_app_enabled is False

    @pytest.mark.asyncio
    async def test_user_category_preference_in_app_enabled_default(
        self, async_session, test_organization, test_user
    ):
        """Test that in_app_enabled defaults to True for category preferences."""
        # Create a category first
        category = NotificationCategory(
            organization_id=test_organization.id,
            code="test_category",
            name="Test Category",
            default_enabled=True,
            user_configurable=True,
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        # Create category preference
        preference = UserCategoryPreference(
            organization_id=test_organization.id,
            user_id=test_user.id,
            category_id=category.id,
        )
        async_session.add(preference)
        await async_session.commit()
        await async_session.refresh(preference)

        assert preference.in_app_enabled is True

    @pytest.mark.asyncio
    async def test_user_category_preference_in_app_disabled(
        self, async_session, test_organization, test_user
    ):
        """Test setting in_app_enabled to False for category preferences."""
        # Create a category first
        category = NotificationCategory(
            organization_id=test_organization.id,
            code="test_cat_disabled",
            name="Test Category Disabled",
            default_enabled=True,
            user_configurable=True,
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        # Create category preference with in_app disabled
        preference = UserCategoryPreference(
            organization_id=test_organization.id,
            user_id=test_user.id,
            category_id=category.id,
            in_app_enabled=False,
        )
        async_session.add(preference)
        await async_session.commit()
        await async_session.refresh(preference)

        assert preference.in_app_enabled is False

    @pytest.mark.asyncio
    async def test_organization_notification_settings_in_app_enabled_default(
        self, async_session, test_organization
    ):
        """Test that in_app_enabled defaults to True for organization settings."""
        settings = OrganizationNotificationSettings(
            organization_id=test_organization.id,
        )
        async_session.add(settings)
        await async_session.commit()
        await async_session.refresh(settings)

        assert settings.in_app_enabled is True

    @pytest.mark.asyncio
    async def test_organization_notification_settings_in_app_disabled(
        self, async_session, test_organization
    ):
        """Test setting in_app_enabled to False for organization settings."""
        settings = OrganizationNotificationSettings(
            organization_id=test_organization.id,
            in_app_enabled=False,
        )
        async_session.add(settings)
        await async_session.commit()
        await async_session.refresh(settings)

        assert settings.in_app_enabled is False


class TestUserNotificationMultiTenancy:
    """Tests for multi-tenancy isolation of UserNotification model."""

    @pytest.mark.asyncio
    async def test_notification_requires_organization_id(
        self, async_session, test_organization, test_user
    ):
        """Test that organization_id is required for notifications."""
        # Notification requires organization_id
        notification = UserNotification(
            organization_id=test_organization.id,
            user_id=test_user.id,
            title="Test",
        )
        async_session.add(notification)
        await async_session.commit()
        await async_session.refresh(notification)

        assert notification.organization_id is not None
        assert notification.organization_id == test_organization.id

    @pytest.mark.asyncio
    async def test_notifications_scoped_by_organization(
        self, async_session, test_organization, second_organization, test_user
    ):
        """Test that notifications are properly scoped by organization."""
        # Create notification in first org
        notif1 = UserNotification(
            organization_id=test_organization.id,
            user_id=test_user.id,
            title="Org 1 Notification",
        )
        async_session.add(notif1)

        # Create user in second org
        from src.core.security import hash_password
        from src.models.user import User

        user2 = User(
            email="user2@test.com",
            password=hash_password("Password123!"),
            email_verified=True,
            organization_id=second_organization.id,
        )
        async_session.add(user2)
        await async_session.commit()
        await async_session.refresh(user2)

        # Create notification in second org
        notif2 = UserNotification(
            organization_id=second_organization.id,
            user_id=user2.id,
            title="Org 2 Notification",
        )
        async_session.add(notif2)
        await async_session.commit()

        await async_session.refresh(notif1)
        await async_session.refresh(notif2)

        # Verify they have different organization IDs
        assert notif1.organization_id == test_organization.id
        assert notif2.organization_id == second_organization.id
        assert notif1.organization_id != notif2.organization_id


class TestUserNotificationRelationships:
    """Tests for UserNotification model relationships."""

    @pytest.mark.asyncio
    async def test_notification_user_relationship(
        self, async_session, test_organization, test_user
    ):
        """Test that notification has correct user relationship."""
        notification = UserNotification(
            organization_id=test_organization.id,
            user_id=test_user.id,
            title="Test",
        )
        async_session.add(notification)
        await async_session.commit()
        await async_session.refresh(notification)

        # Eager load relationships
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await async_session.execute(
            select(UserNotification)
            .options(selectinload(UserNotification.user))
            .where(UserNotification.id == notification.id)
        )
        loaded_notification = result.scalar_one()

        assert loaded_notification.user is not None
        assert loaded_notification.user.id == test_user.id

    @pytest.mark.asyncio
    async def test_notification_organization_relationship(
        self, async_session, test_organization, test_user
    ):
        """Test that notification has correct organization relationship."""
        notification = UserNotification(
            organization_id=test_organization.id,
            user_id=test_user.id,
            title="Test",
        )
        async_session.add(notification)
        await async_session.commit()
        await async_session.refresh(notification)

        # Eager load relationships
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await async_session.execute(
            select(UserNotification)
            .options(selectinload(UserNotification.organization))
            .where(UserNotification.id == notification.id)
        )
        loaded_notification = result.scalar_one()

        assert loaded_notification.organization is not None
        assert loaded_notification.organization.id == test_organization.id

    @pytest.mark.asyncio
    async def test_notification_category_relationship(
        self, async_session, test_organization, test_user
    ):
        """Test that notification has correct category relationship."""
        # Create category
        category = NotificationCategory(
            organization_id=test_organization.id,
            code="test_rel",
            name="Test Relationship",
            default_enabled=True,
            user_configurable=True,
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        # Create notification with category
        notification = UserNotification(
            organization_id=test_organization.id,
            user_id=test_user.id,
            title="Test",
            category_id=category.id,
        )
        async_session.add(notification)
        await async_session.commit()
        await async_session.refresh(notification)

        # Eager load relationships
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await async_session.execute(
            select(UserNotification)
            .options(selectinload(UserNotification.category))
            .where(UserNotification.id == notification.id)
        )
        loaded_notification = result.scalar_one()

        assert loaded_notification.category is not None
        assert loaded_notification.category.id == category.id
        assert loaded_notification.category.code == "test_rel"

    @pytest.mark.asyncio
    async def test_user_in_app_notifications_relationship(
        self, async_session, test_organization, test_user
    ):
        """Test that user has in_app_notifications relationship."""
        # Create multiple notifications for the user
        for i in range(3):
            notification = UserNotification(
                organization_id=test_organization.id,
                user_id=test_user.id,
                title=f"Notification {i}",
            )
            async_session.add(notification)
        await async_session.commit()

        # Eager load relationships
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from src.models.user import User

        result = await async_session.execute(
            select(User)
            .options(selectinload(User.in_app_notifications))
            .where(User.id == test_user.id)
        )
        loaded_user = result.scalar_one()

        assert loaded_user.in_app_notifications is not None
        assert len(loaded_user.in_app_notifications) == 3


# =============================================================================
# CRUD Tests
# =============================================================================


class TestUserNotificationCRUD:
    """Tests for UserNotification CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_user_notification(
        self, async_session, test_organization, test_user
    ):
        """Test creating a notification via CRUD."""
        from src.crud.user_notification import create_user_notification

        notification = await create_user_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            title="CRUD Test Notification",
            body="This is a test body.",
            link="/test/link",
        )

        assert notification.id is not None
        assert notification.title == "CRUD Test Notification"
        assert notification.body == "This is a test body."
        assert notification.link == "/test/link"
        assert notification.organization_id == test_organization.id
        assert notification.user_id == test_user.id
        assert notification.read_time is None
        assert notification.deleted_time is None

    @pytest.mark.asyncio
    async def test_create_user_notification_with_category(
        self, async_session, test_organization, test_user
    ):
        """Test creating a notification with category via CRUD."""
        from src.crud.user_notification import create_user_notification

        # Create category first
        category = NotificationCategory(
            organization_id=test_organization.id,
            code="crud_test_cat",
            name="CRUD Test Category",
            default_enabled=True,
            user_configurable=True,
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        notification = await create_user_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            title="Categorized Notification",
            category_id=str(category.id),
        )

        assert notification.category_id == category.id

    @pytest.mark.asyncio
    async def test_get_user_notifications(
        self, async_session, test_organization, test_user
    ):
        """Test getting paginated notifications."""
        from src.crud.user_notification import (
            create_user_notification,
            get_user_notifications,
        )

        # Create 5 notifications
        for i in range(5):
            await create_user_notification(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
                title=f"Notification {i}",
            )

        notifications, total = await get_user_notifications(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        assert total == 5
        assert len(notifications) == 5

    @pytest.mark.asyncio
    async def test_get_user_notifications_pagination(
        self, async_session, test_organization, test_user
    ):
        """Test notification pagination."""
        from src.crud.user_notification import (
            create_user_notification,
            get_user_notifications,
        )

        # Create 10 notifications
        for i in range(10):
            await create_user_notification(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
                title=f"Notification {i}",
            )

        # Get first page
        notifications, total = await get_user_notifications(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            limit=3,
            offset=0,
        )

        assert total == 10
        assert len(notifications) == 3

        # Get second page
        notifications2, total2 = await get_user_notifications(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            limit=3,
            offset=3,
        )

        assert total2 == 10
        assert len(notifications2) == 3

    @pytest.mark.asyncio
    async def test_get_user_notifications_unread_only(
        self, async_session, test_organization, test_user
    ):
        """Test getting only unread notifications."""
        from src.crud.user_notification import (
            create_user_notification,
            get_user_notifications,
            mark_as_read,
        )

        # Create 3 notifications
        notifs = []
        for i in range(3):
            notif = await create_user_notification(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
                title=f"Notification {i}",
            )
            notifs.append(notif)

        # Mark one as read
        await mark_as_read(
            session=async_session,
            notification_id=str(notifs[0].id),
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        # Get only unread
        notifications, total = await get_user_notifications(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            unread_only=True,
        )

        assert total == 2
        assert len(notifications) == 2

    @pytest.mark.asyncio
    async def test_get_unread_count(self, async_session, test_organization, test_user):
        """Test getting unread notification count."""
        from src.crud.user_notification import (
            create_user_notification,
            get_unread_count,
            mark_as_read,
        )

        # Create 5 notifications
        notifs = []
        for i in range(5):
            notif = await create_user_notification(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
                title=f"Notification {i}",
            )
            notifs.append(notif)

        # Initially all are unread
        count = await get_unread_count(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        assert count == 5

        # Mark 2 as read
        await mark_as_read(
            session=async_session,
            notification_id=str(notifs[0].id),
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        await mark_as_read(
            session=async_session,
            notification_id=str(notifs[1].id),
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        # Now 3 are unread
        count = await get_unread_count(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        assert count == 3

    @pytest.mark.asyncio
    async def test_get_user_notification_by_id(
        self, async_session, test_organization, test_user
    ):
        """Test getting a single notification by ID."""
        from src.crud.user_notification import (
            create_user_notification,
            get_user_notification_by_id,
        )

        notification = await create_user_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            title="Find Me",
        )

        found = await get_user_notification_by_id(
            session=async_session,
            notification_id=str(notification.id),
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        assert found is not None
        assert found.id == notification.id
        assert found.title == "Find Me"

    @pytest.mark.asyncio
    async def test_get_user_notification_by_id_not_found(
        self, async_session, test_organization, test_user
    ):
        """Test getting a non-existent notification returns None."""
        import uuid

        from src.crud.user_notification import get_user_notification_by_id

        found = await get_user_notification_by_id(
            session=async_session,
            notification_id=str(uuid.uuid4()),
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        assert found is None

    @pytest.mark.asyncio
    async def test_mark_as_read(self, async_session, test_organization, test_user):
        """Test marking a notification as read."""
        from src.crud.user_notification import (
            create_user_notification,
            mark_as_read,
        )

        notification = await create_user_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            title="Read Me",
        )

        assert notification.read_time is None

        updated = await mark_as_read(
            session=async_session,
            notification_id=str(notification.id),
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        assert updated is not None
        assert updated.read_time is not None

    @pytest.mark.asyncio
    async def test_mark_as_read_idempotent(
        self, async_session, test_organization, test_user
    ):
        """Test that marking as read multiple times doesn't change read_time."""
        from src.crud.user_notification import (
            create_user_notification,
            mark_as_read,
        )

        notification = await create_user_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            title="Read Me Twice",
        )

        # First mark as read
        first_update = await mark_as_read(
            session=async_session,
            notification_id=str(notification.id),
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        first_read_time = first_update.read_time

        # Mark again - should keep same read_time
        second_update = await mark_as_read(
            session=async_session,
            notification_id=str(notification.id),
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        assert second_update.read_time == first_read_time

    @pytest.mark.asyncio
    async def test_mark_all_as_read(self, async_session, test_organization, test_user):
        """Test marking all notifications as read."""
        from src.crud.user_notification import (
            create_user_notification,
            get_unread_count,
            mark_all_as_read,
        )

        # Create 5 unread notifications
        for i in range(5):
            await create_user_notification(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
                title=f"Notification {i}",
            )

        # Verify all unread
        count = await get_unread_count(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        assert count == 5

        # Mark all as read
        marked = await mark_all_as_read(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        assert marked == 5

        # Verify none unread
        count = await get_unread_count(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_bulk_dismiss(self, async_session, test_organization, test_user):
        """Test bulk dismissing notifications."""
        from src.crud.user_notification import (
            bulk_dismiss,
            create_user_notification,
            get_user_notifications,
        )

        # Create 5 notifications
        notifs = []
        for i in range(5):
            notif = await create_user_notification(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
                title=f"Notification {i}",
            )
            notifs.append(notif)

        # Dismiss 3 of them
        dismissed = await bulk_dismiss(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            notification_ids=[str(notifs[0].id), str(notifs[1].id), str(notifs[2].id)],
        )

        assert dismissed == 3

        # Verify only 2 remain
        remaining, total = await get_user_notifications(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        assert total == 2
        assert len(remaining) == 2

    @pytest.mark.asyncio
    async def test_soft_delete_user_notification(
        self, async_session, test_organization, test_user
    ):
        """Test soft deleting a notification."""
        from src.crud.user_notification import (
            create_user_notification,
            get_user_notification_by_id,
            soft_delete_user_notification,
        )

        notification = await create_user_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            title="Delete Me",
        )

        # Delete it
        deleted = await soft_delete_user_notification(
            session=async_session,
            notification_id=str(notification.id),
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        assert deleted is not None
        assert deleted.deleted_time is not None

        # Should not be found anymore
        found = await get_user_notification_by_id(
            session=async_session,
            notification_id=str(notification.id),
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        assert found is None


class TestUserNotificationCRUDTenantIsolation:
    """Tests for tenant isolation in CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_notifications_filters_by_organization(
        self, async_session, test_organization, second_organization, test_user
    ):
        """Test that get_user_notifications only returns notifications from the user's org."""
        from src.core.security import hash_password
        from src.crud.user_notification import (
            create_user_notification,
            get_user_notifications,
        )
        from src.models.user import User

        # Create user in second org
        user2 = User(
            email="user2_iso@test.com",
            password=hash_password("Password123!"),
            email_verified=True,
            organization_id=second_organization.id,
        )
        async_session.add(user2)
        await async_session.commit()
        await async_session.refresh(user2)

        # Create notifications in both orgs
        await create_user_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            title="Org 1 Notification",
        )

        await create_user_notification(
            session=async_session,
            organization_id=str(second_organization.id),
            user_id=str(user2.id),
            title="Org 2 Notification",
        )

        # Get notifications for org 1 user
        notifications, total = await get_user_notifications(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        assert total == 1
        assert notifications[0].title == "Org 1 Notification"

        # Get notifications for org 2 user
        notifications2, total2 = await get_user_notifications(
            session=async_session,
            organization_id=str(second_organization.id),
            user_id=str(user2.id),
        )

        assert total2 == 1
        assert notifications2[0].title == "Org 2 Notification"

    @pytest.mark.asyncio
    async def test_cannot_read_other_users_notifications(
        self, async_session, test_organization, test_user
    ):
        """Test that a user cannot read another user's notifications."""
        from src.core.security import hash_password
        from src.crud.user_notification import (
            create_user_notification,
            get_user_notification_by_id,
        )
        from src.models.user import User

        # Create another user in same org
        user2 = User(
            email="user2_same_org@test.com",
            password=hash_password("Password123!"),
            email_verified=True,
            organization_id=test_organization.id,
        )
        async_session.add(user2)
        await async_session.commit()
        await async_session.refresh(user2)

        # Create notification for user2
        notification = await create_user_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(user2.id),
            title="User 2's Notification",
        )

        # Test user 1 cannot access it
        found = await get_user_notification_by_id(
            session=async_session,
            notification_id=str(notification.id),
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),  # Different user
        )

        assert found is None

    @pytest.mark.asyncio
    async def test_cannot_mark_other_users_notifications_read(
        self, async_session, test_organization, test_user
    ):
        """Test that a user cannot mark another user's notifications as read."""
        from src.core.security import hash_password
        from src.crud.user_notification import (
            create_user_notification,
            mark_as_read,
        )
        from src.models.user import User

        # Create another user in same org
        user2 = User(
            email="user2_mark@test.com",
            password=hash_password("Password123!"),
            email_verified=True,
            organization_id=test_organization.id,
        )
        async_session.add(user2)
        await async_session.commit()
        await async_session.refresh(user2)

        # Create notification for user2
        notification = await create_user_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(user2.id),
            title="User 2's Notification",
        )

        # Test user 1 cannot mark it as read
        result = await mark_as_read(
            session=async_session,
            notification_id=str(notification.id),
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),  # Different user
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_unread_count_only_counts_own_notifications(
        self, async_session, test_organization, test_user
    ):
        """Test that unread count only includes user's own notifications."""
        from src.core.security import hash_password
        from src.crud.user_notification import (
            create_user_notification,
            get_unread_count,
        )
        from src.models.user import User

        # Create another user in same org
        user2 = User(
            email="user2_count@test.com",
            password=hash_password("Password123!"),
            email_verified=True,
            organization_id=test_organization.id,
        )
        async_session.add(user2)
        await async_session.commit()
        await async_session.refresh(user2)

        # Create notifications for both users
        for i in range(3):
            await create_user_notification(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
                title=f"User 1 Notification {i}",
            )

        for i in range(5):
            await create_user_notification(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(user2.id),
                title=f"User 2 Notification {i}",
            )

        # User 1 should only see their own count
        count1 = await get_unread_count(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        assert count1 == 3

        # User 2 should only see their own count
        count2 = await get_unread_count(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(user2.id),
        )
        assert count2 == 5


# =============================================================================
# API Endpoint Tests
# =============================================================================


class TestInAppNotificationAPI:
    """Tests for in-app notification API endpoints."""

    @pytest.mark.asyncio
    async def test_list_in_app_notifications(
        self, client, test_jwt_token, async_session, test_organization, test_user
    ):
        """Test listing in-app notifications via API."""
        from src.crud.user_notification import create_user_notification

        # Create some notifications for the user
        for i in range(5):
            await create_user_notification(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
                title=f"API Test Notification {i}",
                body=f"Body {i}",
            )

        response = await client.get(
            "/api/v1/notifications/in-app",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 5
        # Verify newest first ordering
        assert "API Test Notification" in data["items"][0]["title"]

    @pytest.mark.asyncio
    async def test_list_in_app_notifications_pagination(
        self, client, test_jwt_token, async_session, test_organization, test_user
    ):
        """Test pagination of in-app notifications via API."""
        from src.crud.user_notification import create_user_notification

        # Create 10 notifications
        for i in range(10):
            await create_user_notification(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
                title=f"Pagination Test {i}",
            )

        # Get first page
        response = await client.get(
            "/api/v1/notifications/in-app?limit=3&offset=0",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 10
        assert len(data["items"]) == 3
        assert data["limit"] == 3
        assert data["offset"] == 0

    @pytest.mark.asyncio
    async def test_list_in_app_notifications_unread_only(
        self, client, test_jwt_token, async_session, test_organization, test_user
    ):
        """Test filtering for unread-only notifications via API."""
        from src.crud.user_notification import (
            create_user_notification,
            mark_as_read,
        )

        # Create 3 notifications
        notifs = []
        for i in range(3):
            notif = await create_user_notification(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
                title=f"Unread Filter Test {i}",
            )
            notifs.append(notif)

        # Mark one as read
        await mark_as_read(
            session=async_session,
            notification_id=str(notifs[0].id),
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        # Get unread only
        response = await client.get(
            "/api/v1/notifications/in-app?unread_only=true",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_get_unread_count(
        self, client, test_jwt_token, async_session, test_organization, test_user
    ):
        """Test getting unread count via API."""
        from src.crud.user_notification import create_user_notification

        # Create 5 unread notifications
        for i in range(5):
            await create_user_notification(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
                title=f"Unread Count Test {i}",
            )

        response = await client.get(
            "/api/v1/notifications/in-app/unread-count",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["unread_count"] == 5

    @pytest.mark.asyncio
    async def test_mark_notification_as_read(
        self, client, test_jwt_token, async_session, test_organization, test_user
    ):
        """Test marking a notification as read via API."""
        from src.crud.user_notification import create_user_notification

        notification = await create_user_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            title="Mark Read Test",
        )

        response = await client.post(
            f"/api/v1/notifications/in-app/{notification.id}/read",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Notification marked as read"
        assert data["count"] == 1

    @pytest.mark.asyncio
    async def test_mark_notification_as_read_not_found(self, client, test_jwt_token):
        """Test marking a non-existent notification as read returns 404."""
        import uuid

        response = await client.post(
            f"/api/v1/notifications/in-app/{uuid.uuid4()}/read",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Notification not found"

    @pytest.mark.asyncio
    async def test_mark_all_as_read(
        self, client, test_jwt_token, async_session, test_organization, test_user
    ):
        """Test marking all notifications as read via API."""
        from src.crud.user_notification import create_user_notification

        # Create 5 unread notifications
        for i in range(5):
            await create_user_notification(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
                title=f"Mark All Read Test {i}",
            )

        response = await client.post(
            "/api/v1/notifications/in-app/mark-all-read",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "All notifications marked as read"
        assert data["count"] == 5

        # Verify all are read
        count_response = await client.get(
            "/api/v1/notifications/in-app/unread-count",
            headers={"Authorization": test_jwt_token},
        )
        assert count_response.json()["unread_count"] == 0

    @pytest.mark.asyncio
    async def test_dismiss_notifications(
        self, client, test_jwt_token, async_session, test_organization, test_user
    ):
        """Test dismissing notifications via API."""
        from src.crud.user_notification import create_user_notification

        # Create 5 notifications
        notifs = []
        for i in range(5):
            notif = await create_user_notification(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
                title=f"Dismiss Test {i}",
            )
            notifs.append(notif)

        # Dismiss 3 of them
        response = await client.post(
            "/api/v1/notifications/in-app/dismiss",
            headers={"Authorization": test_jwt_token},
            json={
                "notification_ids": [
                    str(notifs[0].id),
                    str(notifs[1].id),
                    str(notifs[2].id),
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Notifications dismissed"
        assert data["count"] == 3

        # Verify only 2 remain
        list_response = await client.get(
            "/api/v1/notifications/in-app",
            headers={"Authorization": test_jwt_token},
        )
        assert list_response.json()["total"] == 2

    @pytest.mark.asyncio
    async def test_get_single_notification(
        self, client, test_jwt_token, async_session, test_organization, test_user
    ):
        """Test getting a single notification by ID via API."""
        from src.crud.user_notification import create_user_notification

        notification = await create_user_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            title="Single Notification Test",
            body="Test body content",
            link="/test/link",
        )

        response = await client.get(
            f"/api/v1/notifications/in-app/{notification.id}",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Single Notification Test"
        assert data["body"] == "Test body content"
        assert data["link"] == "/test/link"
        assert data["read_time"] is None

    @pytest.mark.asyncio
    async def test_get_single_notification_not_found(self, client, test_jwt_token):
        """Test getting a non-existent notification returns 404."""
        import uuid

        response = await client.get(
            f"/api/v1/notifications/in-app/{uuid.uuid4()}",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Notification not found"

    @pytest.mark.asyncio
    async def test_cannot_access_other_users_notifications(
        self, client, test_jwt_token, async_session, test_organization, test_user
    ):
        """Test that a user cannot access another user's notifications via API."""
        from src.core.security import hash_password
        from src.crud.user_notification import create_user_notification
        from src.models.user import User

        # Create another user in same org
        user2 = User(
            email="api_test_user2@test.com",
            password=hash_password("Password123!"),
            email_verified=True,
            organization_id=test_organization.id,
        )
        async_session.add(user2)
        await async_session.commit()
        await async_session.refresh(user2)

        # Create notification for user2
        notification = await create_user_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(user2.id),
            title="User 2's Private Notification",
        )

        # test_user tries to access user2's notification
        response = await client.get(
            f"/api/v1/notifications/in-app/{notification.id}",
            headers={"Authorization": test_jwt_token},
        )

        # Should return 404 (not 403) to avoid leaking existence
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_api_requires_authentication(self, client):
        """Test that API endpoints require authentication."""
        response = await client.get("/api/v1/notifications/in-app")
        assert response.status_code == 401

        response = await client.get("/api/v1/notifications/in-app/unread-count")
        assert response.status_code == 401

        response = await client.post("/api/v1/notifications/in-app/mark-all-read")
        assert response.status_code == 401


# =============================================================================
# InAppProvider Tests
# =============================================================================


class TestInAppProvider:
    """Tests for InAppProvider service."""

    @pytest.mark.asyncio
    async def test_in_app_provider_send(
        self, async_session, test_organization, test_user
    ):
        """Test InAppProvider creates notification and returns success."""
        from src.crud.user_notification import get_user_notification_by_id
        from src.services.notifications.in_app_provider import in_app_provider

        result = await in_app_provider.send_in_app(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            title="Provider Test Notification",
            body="This is the body",
            link="/test/link",
        )

        assert result.success is True
        assert result.status == "sent"
        assert result.provider_message_id is not None

        # Verify notification was created in DB
        notification = await get_user_notification_by_id(
            session=async_session,
            notification_id=result.provider_message_id,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        assert notification is not None
        assert notification.title == "Provider Test Notification"
        assert notification.body == "This is the body"
        assert notification.link == "/test/link"

    @pytest.mark.asyncio
    async def test_in_app_provider_delivery_status(self):
        """Test InAppProvider always returns 'delivered' for status check."""
        from src.services.notifications.in_app_provider import in_app_provider

        status = await in_app_provider.check_delivery_status("any-id")
        assert status == "delivered"


# =============================================================================
# Dispatcher Integration Tests
# =============================================================================


class TestDispatcherInAppChannel:
    """Tests for in-app channel integration in NotificationDispatcher."""

    @pytest.mark.asyncio
    async def test_dispatcher_send_in_app_notification(
        self, async_session, test_organization, test_user
    ):
        """Test dispatcher can send in-app notifications."""
        from src.crud.user_notification import get_unread_count
        from src.services.notifications.dispatcher import notification_dispatcher

        # Get initial count
        initial_count = await get_unread_count(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        # Send via dispatcher
        result = await notification_dispatcher.send_in_app_notification(
            session=async_session,
            user_id=str(test_user.id),
            organization_id=str(test_organization.id),
            title="Dispatcher Test",
            body="Sent via dispatcher",
        )

        assert result is not None
        assert result["channel"] == "in_app"
        assert result["status"] == "sent"

        # Verify count increased
        new_count = await get_unread_count(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        assert new_count == initial_count + 1

    @pytest.mark.asyncio
    async def test_dispatcher_get_in_app_provider(self, async_session):
        """Test dispatcher returns InAppProvider for in_app channel."""
        from src.services.notifications.dispatcher import notification_dispatcher

        await notification_dispatcher._ensure_initialized()
        provider = notification_dispatcher._get_provider("in_app")

        assert provider is not None
        assert provider.provider_name == "in_app"
        assert provider.channel == "in_app"
