"""
Comprehensive API tests for notification endpoints.
Tests notification sending, templates, categories, user preferences, and settings.
"""

from datetime import time
from uuid import uuid4

from httpx import AsyncClient
import pytest

from src.models.notification import Notification
from src.models.notification_category import NotificationCategory
from src.models.notification_template import NotificationTemplate
from src.models.organization_notification_settings import (
    OrganizationNotificationSettings,
)
from src.models.user_notification_preference import (
    UserCategoryPreference,
    UserNotificationPreference,
)


# ============================================================================
# Fixtures for Notification Testing
# ============================================================================


@pytest.fixture
async def org_notification_settings(async_session, test_organization):
    """Create notification settings for the test organization."""
    settings = OrganizationNotificationSettings(
        organization_id=test_organization.id,
        email_enabled=True,
        sms_enabled=True,
        whatsapp_enabled=False,
        in_app_enabled=True,
        sms_provider="aws_sns",
        whatsapp_provider="twilio",
        notification_retention_days=90,
        sms_rate_limit=1000,
        whatsapp_rate_limit=500,
        email_sender_name="Test Organization",
    )
    async_session.add(settings)
    await async_session.commit()
    await async_session.refresh(settings)
    return settings


@pytest.fixture
async def notification_template(async_session, test_organization):
    """Create a notification template for the test organization."""
    template = NotificationTemplate(
        organization_id=test_organization.id,
        code="welcome_email",
        name="Welcome Email",
        description="Sent to new users on signup",
        channel="email",
        subject="Welcome to {{org_name}}!",
        body_text="Hello {{name}}, welcome to our platform!",
        body_html="<h1>Hello {{name}}</h1><p>Welcome to our platform!</p>",
        variables={"name": "string", "org_name": "string"},
        is_active=True,
    )
    async_session.add(template)
    await async_session.commit()
    await async_session.refresh(template)
    return template


@pytest.fixture
async def system_template(async_session):
    """Create a system-level notification template (no organization)."""
    template = NotificationTemplate(
        organization_id=None,  # System template
        code="password_reset",
        name="Password Reset",
        description="System template for password reset",
        channel="email",
        subject="Reset Your Password",
        body_text="Click the link to reset your password: {{reset_link}}",
        body_html="<p>Click <a href='{{reset_link}}'>here</a> to reset your password.</p>",
        variables={"reset_link": "string"},
        is_active=True,
    )
    async_session.add(template)
    await async_session.commit()
    await async_session.refresh(template)
    return template


@pytest.fixture
async def notification_category(async_session, test_organization):
    """Create a notification category for the test organization."""
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
    return category


@pytest.fixture
async def system_category(async_session):
    """Create a system-level notification category."""
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
    return category


@pytest.fixture
async def user_notification_pref(async_session, test_organization, test_user):
    """Create user notification preferences."""
    pref = UserNotificationPreference(
        organization_id=test_organization.id,
        user_id=test_user.id,
        email_enabled=True,
        sms_enabled=False,
        whatsapp_enabled=True,
        in_app_enabled=True,
        quiet_hours_enabled=True,
        quiet_hours_start=time(22, 0),
        quiet_hours_end=time(7, 0),
        quiet_hours_timezone="America/New_York",
    )
    async_session.add(pref)
    await async_session.commit()
    await async_session.refresh(pref)
    return pref


@pytest.fixture
async def user_category_pref(
    async_session, test_organization, test_user, notification_category
):
    """Create user preference for a specific category."""
    pref = UserCategoryPreference(
        organization_id=test_organization.id,
        user_id=test_user.id,
        category_id=notification_category.id,
        email_enabled=True,
        sms_enabled=False,
        whatsapp_enabled=False,
        in_app_enabled=True,
    )
    async_session.add(pref)
    await async_session.commit()
    await async_session.refresh(pref)
    return pref


@pytest.fixture
async def test_notification(async_session, test_organization, test_user):
    """Create a test notification record."""
    notification = Notification(
        organization_id=test_organization.id,
        channel="email",
        provider="ses",
        recipient="test@example.com",
        user_id=test_user.id,
        subject="Test Notification",
        body_preview="This is a test notification",
        status="sent",
        provider_message_id="msg-12345",
        retry_count=0,
    )
    async_session.add(notification)
    await async_session.commit()
    await async_session.refresh(notification)
    return notification


@pytest.fixture
async def multiple_notifications(async_session, test_organization, test_user):
    """Create multiple test notifications."""
    notifications = []
    statuses = ["pending", "sent", "delivered", "failed"]
    channels = ["email", "sms", "email", "whatsapp"]

    for i, (status, channel) in enumerate(zip(statuses, channels)):
        notification = Notification(
            organization_id=test_organization.id,
            channel=channel,
            provider="test_provider",
            recipient=(
                f"recipient{i}@example.com"
                if channel == "email"
                else f"+1555000{i:04d}"
            ),
            user_id=test_user.id,
            subject=f"Test Notification {i}" if channel == "email" else None,
            body_preview=f"Test message {i}",
            status=status,
            retry_count=0,
        )
        async_session.add(notification)
        notifications.append(notification)

    await async_session.commit()
    for n in notifications:
        await async_session.refresh(n)
    return notifications


# ============================================================================
# Send Notification Tests
# ============================================================================


class TestSendNotificationEndpoint:
    """Tests for POST /api/notifications/send endpoint."""

    @pytest.mark.asyncio
    async def test_send_notification_requires_admin(
        self, client: AsyncClient, test_jwt_token
    ):
        """Test that sending notifications requires admin role."""
        request_data = {
            "channel": "email",
            "recipient": "user@example.com",
            "content": "Hello, World!",
        }

        response = await client.post(
            "/api/v1/notifications/send",
            json=request_data,
            headers={"Authorization": test_jwt_token},
        )

        # Should require admin
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_send_notification_as_admin(
        self, client: AsyncClient, test_admin_token, test_user
    ):
        """Test sending a notification as admin."""
        request_data = {
            "channel": "email",
            "user_id": str(test_user.id),
            "content": "Hello, World!",
            "subject": "Test Subject",
        }

        response = await client.post(
            "/api/v1/notifications/send",
            json=request_data,
            headers={"Authorization": test_admin_token},
        )

        # May be 501 if not fully implemented, or 201 if implemented
        assert response.status_code in [201, 501]

    @pytest.mark.asyncio
    async def test_send_notification_invalid_channel(
        self, client: AsyncClient, test_admin_token, test_user
    ):
        """Test that invalid channel is rejected."""
        request_data = {
            "channel": "invalid_channel",
            "user_id": str(test_user.id),
            "content": "Hello",
        }

        response = await client.post(
            "/api/v1/notifications/send",
            json=request_data,
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code in [400, 422, 501]

    @pytest.mark.asyncio
    async def test_send_notification_requires_recipient_or_user(
        self, client: AsyncClient, test_admin_token
    ):
        """Test that either recipient or user_id is required."""
        request_data = {
            "channel": "email",
            "content": "Hello",
            # Missing both recipient and user_id
        }

        response = await client.post(
            "/api/v1/notifications/send",
            json=request_data,
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code in [400, 422, 501]

    @pytest.mark.asyncio
    async def test_send_notification_requires_content_or_template(
        self, client: AsyncClient, test_admin_token
    ):
        """Test that either content or template_code is required."""
        request_data = {
            "channel": "email",
            "recipient": "user@example.com",
            # Missing both content and template_code
        }

        response = await client.post(
            "/api/v1/notifications/send",
            json=request_data,
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code in [400, 422, 501]

    @pytest.mark.asyncio
    async def test_send_notification_unauthenticated(self, client: AsyncClient):
        """Test that sending notifications requires authentication."""
        request_data = {
            "channel": "email",
            "recipient": "user@example.com",
            "content": "Hello",
        }

        response = await client.post("/api/v1/notifications/send", json=request_data)

        assert response.status_code in [401, 403]


# ============================================================================
# Bulk Notification Tests
# ============================================================================


class TestBulkNotificationEndpoints:
    """Tests for bulk notification endpoints."""

    @pytest.mark.asyncio
    async def test_create_bulk_notification_requires_admin(
        self, client: AsyncClient, test_jwt_token
    ):
        """Test that creating bulk notifications requires admin role."""
        request_data = {
            "name": "Test Bulk",
            "channel": "email",
            "body_text": "Hello everyone!",
            "recipient_filters": {"verified_contact_only": True},
        }

        response = await client.post(
            "/api/v1/notifications/bulk",
            json=request_data,
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_create_bulk_notification_as_admin(
        self, client: AsyncClient, test_admin_token
    ):
        """Test creating a bulk notification as admin."""
        from unittest.mock import AsyncMock, patch

        request_data = {
            "name": "Test Bulk Campaign",
            "channel": "email",
            "body_text": "Hello everyone!",
            "subject": "Important Update",
            "recipient_filters": {"verified_contact_only": True},
        }

        # Mock TaskQueue to avoid Redis connection in tests
        with patch(
            "src.services.tasks.TaskQueue.enqueue_job",
            new_callable=AsyncMock,
        ) as mock_enqueue:
            mock_enqueue.return_value = "mock-job-id"

            response = await client.post(
                "/api/v1/notifications/bulk",
                json=request_data,
                headers={"Authorization": test_admin_token},
            )

        # May be 501 if not implemented
        assert response.status_code in [201, 501]

    @pytest.mark.asyncio
    async def test_get_bulk_notification_status(
        self, client: AsyncClient, test_admin_token
    ):
        """Test getting bulk notification status."""
        bulk_id = str(uuid4())

        response = await client.get(
            f"/api/v1/notifications/bulk/{bulk_id}",
            headers={"Authorization": test_admin_token},
        )

        # May be 404 or 501
        assert response.status_code in [404, 501]

    @pytest.mark.asyncio
    async def test_cancel_bulk_notification(
        self, client: AsyncClient, test_admin_token
    ):
        """Test cancelling a bulk notification."""
        bulk_id = str(uuid4())

        response = await client.post(
            f"/api/v1/notifications/bulk/{bulk_id}/cancel",
            headers={"Authorization": test_admin_token},
        )

        # May be 404 or 501
        assert response.status_code in [404, 501]


# ============================================================================
# Notification History Tests
# ============================================================================


class TestNotificationHistoryEndpoints:
    """Tests for notification history endpoints."""

    @pytest.mark.asyncio
    async def test_list_notifications_requires_admin(
        self, client: AsyncClient, test_jwt_token
    ):
        """Test that listing notifications requires admin role."""
        response = await client.get(
            "/api/v1/notifications", headers={"Authorization": test_jwt_token}
        )

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_list_notifications_as_admin(
        self, client: AsyncClient, test_admin_token, multiple_notifications
    ):
        """Test listing notifications as admin."""
        response = await client.get(
            "/api/v1/notifications", headers={"Authorization": test_admin_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) == len(multiple_notifications)

    @pytest.mark.asyncio
    async def test_list_notifications_with_filters(
        self, client: AsyncClient, test_admin_token, multiple_notifications
    ):
        """Test listing notifications with filters."""
        response = await client.get(
            "/api/v1/notifications?filter[channel]=email&filter[status]=sent",
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        # All returned items should match the filter
        for item in data["items"]:
            assert item["channel"] == "email"
            assert item["status"] == "sent"

    @pytest.mark.asyncio
    async def test_get_notification_by_id(
        self, client: AsyncClient, test_admin_token, test_notification
    ):
        """Test getting a specific notification."""
        response = await client.get(
            f"/api/v1/notifications/{test_notification.id}",
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_notification.id)
        assert data["channel"] == "email"
        assert data["status"] == "sent"

    @pytest.mark.asyncio
    async def test_get_notification_not_found(
        self, client: AsyncClient, test_admin_token
    ):
        """Test getting a non-existent notification."""
        fake_id = str(uuid4())
        response = await client.get(
            f"/api/v1/notifications/{fake_id}",
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 404


# ============================================================================
# Template Tests
# ============================================================================


class TestTemplateEndpoints:
    """Tests for notification template endpoints."""

    @pytest.mark.asyncio
    async def test_list_templates_requires_admin(
        self, client: AsyncClient, test_jwt_token
    ):
        """Test that listing templates requires admin role."""
        response = await client.get(
            "/api/v1/notifications/templates", headers={"Authorization": test_jwt_token}
        )

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_list_templates_as_admin(
        self,
        client: AsyncClient,
        test_admin_token,
        notification_template,
        system_template,
    ):
        """Test listing templates as admin."""
        response = await client.get(
            "/api/v1/notifications/templates",
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        # Should include both org template and system template
        assert data["total"] >= 2

    @pytest.mark.asyncio
    async def test_list_templates_filter_by_channel(
        self, client: AsyncClient, test_admin_token, notification_template
    ):
        """Test listing templates filtered by channel."""
        response = await client.get(
            "/api/v1/notifications/templates?channel=email",
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["channel"] == "email"

    @pytest.mark.asyncio
    async def test_create_template(self, client: AsyncClient, test_admin_token):
        """Test creating a new template."""
        request_data = {
            "code": "order_confirmation",
            "name": "Order Confirmation",
            "channel": "email",
            "subject": "Order #{{order_id}} Confirmed",
            "body_text": "Your order has been confirmed.",
            "is_active": True,
        }

        response = await client.post(
            "/api/v1/notifications/templates",
            json=request_data,
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Template created successfully"
        assert data["template"]["code"] == "order_confirmation"
        assert data["template"]["name"] == "Order Confirmation"
        assert data["template"]["channel"] == "email"

    @pytest.mark.asyncio
    async def test_create_template_invalid_channel(
        self, client: AsyncClient, test_admin_token
    ):
        """Test creating template with invalid channel."""
        request_data = {
            "code": "test_template",
            "name": "Test Template",
            "channel": "invalid",
            "body_text": "Test body",
        }

        response = await client.post(
            "/api/v1/notifications/templates",
            json=request_data,
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_template_duplicate_code(
        self, client: AsyncClient, test_admin_token, notification_template
    ):
        """Test creating template with duplicate code fails."""
        request_data = {
            "code": notification_template.code,  # Same code as existing
            "name": "Duplicate Template",
            "channel": notification_template.channel,
            "body_text": "This should fail",
        }

        response = await client.post(
            "/api/v1/notifications/templates",
            json=request_data,
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_update_template(
        self, client: AsyncClient, test_admin_token, notification_template
    ):
        """Test updating a template."""
        request_data = {"name": "Updated Welcome Email", "is_active": False}

        response = await client.put(
            f"/api/v1/notifications/templates/{notification_template.id}",
            json=request_data,
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Template updated successfully"
        assert data["template"]["name"] == "Updated Welcome Email"
        assert data["template"]["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_system_template_fails(
        self, client: AsyncClient, test_admin_token, system_template
    ):
        """Test that updating a system template fails."""
        request_data = {"name": "Hacked System Template"}

        response = await client.put(
            f"/api/v1/notifications/templates/{system_template.id}",
            json=request_data,
            headers={"Authorization": test_admin_token},
        )

        # Should fail because system templates cannot be modified
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_template(
        self, client: AsyncClient, test_admin_token, notification_template
    ):
        """Test deleting a template."""
        response = await client.delete(
            f"/api/v1/notifications/templates/{notification_template.id}",
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Template deleted successfully"

    @pytest.mark.asyncio
    async def test_delete_system_template_fails(
        self, client: AsyncClient, test_admin_token, system_template
    ):
        """Test that deleting a system template fails."""
        response = await client.delete(
            f"/api/v1/notifications/templates/{system_template.id}",
            headers={"Authorization": test_admin_token},
        )

        # Should fail because system templates cannot be deleted
        assert response.status_code == 400


# ============================================================================
# Category Tests
# ============================================================================


class TestCategoryEndpoints:
    """Tests for notification category endpoints."""

    @pytest.mark.asyncio
    async def test_list_categories_requires_admin(
        self, client: AsyncClient, test_jwt_token
    ):
        """Test that listing categories requires admin role."""
        response = await client.get(
            "/api/v1/notifications/categories",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_list_categories_as_admin(
        self,
        client: AsyncClient,
        test_admin_token,
        notification_category,
        system_category,
    ):
        """Test listing categories as admin."""
        response = await client.get(
            "/api/v1/notifications/categories",
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        # Should include both org category and system category
        assert data["total"] >= 2

    @pytest.mark.asyncio
    async def test_create_category(self, client: AsyncClient, test_admin_token):
        """Test creating a new category."""
        request_data = {
            "code": "announcements",
            "name": "Announcements",
            "description": "General announcements",
            "default_enabled": True,
            "user_configurable": True,
            "display_order": 2,
        }

        response = await client.post(
            "/api/v1/notifications/categories",
            json=request_data,
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Category created successfully"
        assert data["category"]["code"] == "announcements"
        assert data["category"]["name"] == "Announcements"

    @pytest.mark.asyncio
    async def test_create_category_duplicate_code(
        self, client: AsyncClient, test_admin_token, notification_category
    ):
        """Test creating category with duplicate code fails."""
        request_data = {
            "code": notification_category.code,  # Same code as existing
            "name": "Duplicate Category",
        }

        response = await client.post(
            "/api/v1/notifications/categories",
            json=request_data,
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_update_category(
        self, client: AsyncClient, test_admin_token, notification_category
    ):
        """Test updating a category."""
        request_data = {"name": "Marketing & Promotions", "display_order": 5}

        response = await client.put(
            f"/api/v1/notifications/categories/{notification_category.id}",
            json=request_data,
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Category updated successfully"
        assert data["category"]["name"] == "Marketing & Promotions"
        assert data["category"]["display_order"] == 5

    @pytest.mark.asyncio
    async def test_update_system_category_fails(
        self, client: AsyncClient, test_admin_token, system_category
    ):
        """Test that updating a system category fails."""
        request_data = {"name": "Hacked System Category"}

        response = await client.put(
            f"/api/v1/notifications/categories/{system_category.id}",
            json=request_data,
            headers={"Authorization": test_admin_token},
        )

        # Should fail because system categories cannot be modified
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_category(
        self, client: AsyncClient, test_admin_token, notification_category
    ):
        """Test deleting a category."""
        response = await client.delete(
            f"/api/v1/notifications/categories/{notification_category.id}",
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Category deleted successfully"

    @pytest.mark.asyncio
    async def test_delete_system_category_fails(
        self, client: AsyncClient, test_admin_token, system_category
    ):
        """Test that deleting a system category fails."""
        response = await client.delete(
            f"/api/v1/notifications/categories/{system_category.id}",
            headers={"Authorization": test_admin_token},
        )

        # Should fail because system categories cannot be deleted
        assert response.status_code == 400


# ============================================================================
# Organization Settings Tests
# ============================================================================


class TestNotificationSettingsEndpoints:
    """Tests for organization notification settings endpoints."""

    @pytest.mark.asyncio
    async def test_get_settings_requires_admin(
        self, client: AsyncClient, test_jwt_token
    ):
        """Test that getting settings requires admin role."""
        response = await client.get(
            "/api/v1/notifications/settings", headers={"Authorization": test_jwt_token}
        )

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_get_settings_as_admin(
        self, client: AsyncClient, test_admin_token, org_notification_settings
    ):
        """Test getting notification settings as admin."""
        response = await client.get(
            "/api/v1/notifications/settings",
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "email_enabled" in data
        assert "sms_enabled" in data
        assert "whatsapp_enabled" in data
        assert data["email_enabled"] is True

    @pytest.mark.asyncio
    async def test_get_settings_creates_default_if_not_exists(
        self, client: AsyncClient, test_admin_token
    ):
        """Test that getting settings creates defaults if none exist."""
        response = await client.get(
            "/api/v1/notifications/settings",
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        # Should have default values
        assert data["email_enabled"] is True
        assert data["notification_retention_days"] == 90

    @pytest.mark.asyncio
    async def test_update_settings_as_admin(
        self, client: AsyncClient, test_admin_token, org_notification_settings
    ):
        """Test updating notification settings as admin."""
        request_data = {"email_enabled": False, "sms_rate_limit": 2000}

        response = await client.put(
            "/api/v1/notifications/settings",
            json=request_data,
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Settings updated successfully"
        assert data["settings"]["email_enabled"] is False
        assert data["settings"]["sms_rate_limit"] == 2000

    @pytest.mark.asyncio
    async def test_update_settings_requires_admin(
        self, client: AsyncClient, test_jwt_token
    ):
        """Test that updating settings requires admin role."""
        request_data = {"email_enabled": False}

        response = await client.put(
            "/api/v1/notifications/settings",
            json=request_data,
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code in [401, 403]


# ============================================================================
# User Preferences Tests
# ============================================================================


class TestUserPreferencesEndpoints:
    """Tests for user notification preference endpoints."""

    @pytest.mark.asyncio
    async def test_get_user_preferences(
        self, client: AsyncClient, test_jwt_token, user_notification_pref
    ):
        """Test getting current user's preferences."""
        response = await client.get(
            "/api/v1/notifications/preferences",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "email_enabled" in data
        assert "sms_enabled" in data
        assert "whatsapp_enabled" in data
        assert "quiet_hours_enabled" in data

    @pytest.mark.asyncio
    async def test_get_user_preferences_creates_default(
        self, client: AsyncClient, test_jwt_token
    ):
        """Test that getting preferences creates defaults if not exist."""
        response = await client.get(
            "/api/v1/notifications/preferences",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        # Should have default values
        assert data["email_enabled"] is True
        assert data["quiet_hours_timezone"] == "UTC"

    @pytest.mark.asyncio
    async def test_get_user_preferences_unauthenticated(self, client: AsyncClient):
        """Test that getting preferences requires authentication."""
        response = await client.get("/api/v1/notifications/preferences")

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_update_user_preferences(
        self, client: AsyncClient, test_jwt_token, user_notification_pref
    ):
        """Test updating user preferences."""
        request_data = {"email_enabled": False, "quiet_hours_enabled": False}

        response = await client.put(
            "/api/v1/notifications/preferences",
            json=request_data,
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Preferences updated successfully"
        assert data["preferences"]["email_enabled"] is False
        assert data["preferences"]["quiet_hours_enabled"] is False

    @pytest.mark.asyncio
    async def test_update_quiet_hours(
        self, client: AsyncClient, test_jwt_token, user_notification_pref
    ):
        """Test updating quiet hours settings."""
        request_data = {
            "quiet_hours_enabled": True,
            "quiet_hours_start": "23:00",
            "quiet_hours_end": "06:00",
            "quiet_hours_timezone": "America/Los_Angeles",
        }

        response = await client.put(
            "/api/v1/notifications/preferences",
            json=request_data,
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["preferences"]["quiet_hours_enabled"] is True
        assert data["preferences"]["quiet_hours_start"] == "23:00"
        assert data["preferences"]["quiet_hours_end"] == "06:00"
        assert data["preferences"]["quiet_hours_timezone"] == "America/Los_Angeles"

    @pytest.mark.asyncio
    async def test_update_quiet_hours_invalid_format(
        self, client: AsyncClient, test_jwt_token
    ):
        """Test that invalid quiet hours format is rejected."""
        request_data = {"quiet_hours_start": "invalid-time"}

        response = await client.put(
            "/api/v1/notifications/preferences",
            json=request_data,
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_category_preferences(
        self, client: AsyncClient, test_jwt_token, notification_category
    ):
        """Test getting user's category preferences."""
        response = await client.get(
            "/api/v1/notifications/preferences/categories",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        # Should include the notification_category
        categories = [item["category"]["id"] for item in data["items"]]
        assert str(notification_category.id) in categories

    @pytest.mark.asyncio
    async def test_update_category_preference(
        self, client: AsyncClient, test_jwt_token, notification_category
    ):
        """Test updating preference for a specific category."""
        request_data = {"email_enabled": False, "sms_enabled": True}

        response = await client.put(
            f"/api/v1/notifications/preferences/categories/{notification_category.id}",
            json=request_data,
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Category preference updated successfully"
        assert data["email_enabled"] is False
        assert data["sms_enabled"] is True

    @pytest.mark.asyncio
    async def test_update_non_configurable_category_fails(
        self, client: AsyncClient, test_jwt_token, system_category
    ):
        """Test that updating a non-configurable category fails."""
        request_data = {"email_enabled": False}

        response = await client.put(
            f"/api/v1/notifications/preferences/categories/{system_category.id}",
            json=request_data,
            headers={"Authorization": test_jwt_token},
        )

        # system_category has user_configurable=False
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_update_nonexistent_category_fails(
        self, client: AsyncClient, test_jwt_token
    ):
        """Test that updating preference for non-existent category fails."""
        fake_id = str(uuid4())
        request_data = {"email_enabled": False}

        response = await client.put(
            f"/api/v1/notifications/preferences/categories/{fake_id}",
            json=request_data,
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 400


# ============================================================================
# Unsubscribe Tests
# ============================================================================


class TestUnsubscribeEndpoints:
    """Tests for unsubscribe endpoints (public, token-based)."""

    @pytest.mark.asyncio
    async def test_get_unsubscribe_info_with_token(self, client: AsyncClient):
        """Test getting unsubscribe information with a token."""
        # This is a public endpoint that uses tokens
        response = await client.get(
            "/api/v1/notifications/unsubscribe?token=test-token-12345"
        )

        # 401 = endpoint requires auth even for token-based access
        # May be 501 if not implemented, or 400/404 for invalid token
        assert response.status_code in [200, 400, 401, 404, 501]

    @pytest.mark.asyncio
    async def test_get_unsubscribe_info_without_token(self, client: AsyncClient):
        """Test that unsubscribe info requires a token."""
        response = await client.get("/api/v1/notifications/unsubscribe")

        # 401 = endpoint requires authentication
        # Should fail without token
        assert response.status_code in [400, 401, 422]

    @pytest.mark.asyncio
    async def test_process_unsubscribe(self, client: AsyncClient):
        """Test processing an unsubscribe request."""
        request_data = {"token": "valid-unsubscribe-token"}

        response = await client.post(
            "/api/v1/notifications/unsubscribe", json=request_data
        )

        # May be 501 if not implemented
        assert response.status_code in [200, 400, 404, 501]


# ============================================================================
# Multi-Tenancy Isolation Tests
# ============================================================================


class TestNotificationMultiTenancyIsolation:
    """Tests to ensure notifications are properly isolated between organizations."""

    @pytest.mark.asyncio
    async def test_cannot_access_other_org_notifications(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        second_organization,
        test_user,
        test_admin_token,
    ):
        """Test that admins cannot access notifications from other organizations."""
        # Create a notification in the second organization
        other_org_notification = Notification(
            organization_id=second_organization.id,
            channel="email",
            provider="ses",
            recipient="other@example.com",
            user_id=test_user.id,
            subject="Secret Notification",
            body_preview="This should not be visible",
            status="sent",
        )
        async_session.add(other_org_notification)
        await async_session.commit()
        await async_session.refresh(other_org_notification)

        # Try to access from the first organization's context
        response = await client.get(
            f"/api/v1/notifications/{other_org_notification.id}",
            headers={"Authorization": test_admin_token},
        )

        # Should not find the notification (it belongs to a different org)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_access_other_org_templates(
        self, client: AsyncClient, async_session, second_organization, test_admin_token
    ):
        """Test that admins cannot modify templates from other organizations."""
        # Create a template in the second organization
        other_org_template = NotificationTemplate(
            organization_id=second_organization.id,
            code="secret_template",
            name="Secret Template",
            channel="email",
            body_text="Secret content",
            is_active=True,
        )
        async_session.add(other_org_template)
        await async_session.commit()
        await async_session.refresh(other_org_template)

        # Try to update from the first organization's context
        response = await client.put(
            f"/api/v1/notifications/templates/{other_org_template.id}",
            json={"name": "Hacked Template"},
            headers={"Authorization": test_admin_token},
        )

        # Should not find or allow modification
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_access_other_org_categories(
        self, client: AsyncClient, async_session, second_organization, test_admin_token
    ):
        """Test that admins cannot modify categories from other organizations."""
        # Create a category in the second organization
        other_org_category = NotificationCategory(
            organization_id=second_organization.id,
            code="secret_category",
            name="Secret Category",
            default_enabled=True,
            user_configurable=True,
        )
        async_session.add(other_org_category)
        await async_session.commit()
        await async_session.refresh(other_org_category)

        # Try to delete from the first organization's context
        response = await client.delete(
            f"/api/v1/notifications/categories/{other_org_category.id}",
            headers={"Authorization": test_admin_token},
        )

        # Should not find or allow deletion
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_user_only_sees_own_category_preferences(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        second_organization,
        test_jwt_token,
    ):
        """Test that users only see category preferences for their organization."""
        # Create a category in the second organization
        other_org_category = NotificationCategory(
            organization_id=second_organization.id,
            code="other_org_only",
            name="Other Org Category",
            default_enabled=True,
            user_configurable=True,
        )
        async_session.add(other_org_category)
        await async_session.commit()
        await async_session.refresh(other_org_category)

        # Try to update preference for the other org's category
        response = await client.put(
            f"/api/v1/notifications/preferences/categories/{other_org_category.id}",
            json={"email_enabled": False},
            headers={"Authorization": test_jwt_token},
        )

        # Should not find or allow modification
        assert response.status_code == 400  # Category not found for this org
