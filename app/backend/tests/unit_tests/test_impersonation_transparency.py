"""
Unit tests for impersonation transparency and audit trail features.

Tests that audit logs correctly capture impersonation context when actions
are performed by a super admin impersonating another user. Also tests
impersonation notifications to target users.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.crud.audit_log import create_audit_log, get_audit_log_by_id, get_audit_logs
from src.models.audit_log import AuditAction
from src.services.audit import audit_service
from src.services.notifications.impersonation_notifier import (
    format_duration,
    impersonation_notifier,
)


class TestAuditLogImpersonationContext:
    """Tests for recording impersonation context in audit logs."""

    @pytest.mark.asyncio
    async def test_create_audit_log_with_impersonated_by(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test creating an audit log entry with impersonated_by field."""
        audit_log = await create_audit_log(
            session=async_session,
            organization_id=str(test_organization.id),
            action=AuditAction.CREATE,
            resource_type="User",
            resource_id=str(test_user.id),
            actor_id=str(test_user.id),
            changes={"email": {"old": None, "new": "test@example.com"}},
            ip_address="127.0.0.1",
            user_agent="Mozilla/5.0",
            impersonated_by=str(test_admin_user.id),
        )

        assert audit_log.id is not None
        assert str(audit_log.organization_id) == str(test_organization.id)
        assert audit_log.action == "CREATE"
        assert str(audit_log.actor_id) == str(test_user.id)
        assert str(audit_log.impersonated_by) == str(test_admin_user.id)

    @pytest.mark.asyncio
    async def test_create_audit_log_without_impersonated_by(
        self, async_session, test_organization, test_user
    ):
        """Test that impersonated_by is null when not impersonating."""
        audit_log = await create_audit_log(
            session=async_session,
            organization_id=str(test_organization.id),
            action=AuditAction.UPDATE,
            resource_type="User",
            resource_id=str(test_user.id),
            actor_id=str(test_user.id),
            changes={"email": {"old": "old@test.com", "new": "new@test.com"}},
        )

        assert audit_log.id is not None
        assert audit_log.impersonated_by is None

    @pytest.mark.asyncio
    async def test_get_audit_logs_includes_impersonator_relationship(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test that fetching audit logs eagerly loads impersonator relationship."""
        await create_audit_log(
            session=async_session,
            organization_id=str(test_organization.id),
            action=AuditAction.CREATE,
            resource_type="User",
            resource_id=str(test_user.id),
            actor_id=str(test_user.id),
            impersonated_by=str(test_admin_user.id),
        )

        logs, total = await get_audit_logs(
            session=async_session,
            organization_id=str(test_organization.id),
        )

        assert total == 1
        assert logs[0].impersonated_by == test_admin_user.id
        # Verify impersonator relationship is loaded
        assert logs[0].impersonator is not None
        assert logs[0].impersonator.email == test_admin_user.email

    @pytest.mark.asyncio
    async def test_get_audit_log_by_id_includes_impersonator(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test that fetching a single audit log includes impersonator."""
        created_log = await create_audit_log(
            session=async_session,
            organization_id=str(test_organization.id),
            action=AuditAction.DELETE,
            resource_type="User",
            resource_id=str(test_user.id),
            actor_id=str(test_user.id),
            impersonated_by=str(test_admin_user.id),
        )

        fetched_log = await get_audit_log_by_id(
            session=async_session,
            audit_log_id=str(created_log.id),
            organization_id=str(test_organization.id),
        )

        assert fetched_log is not None
        assert str(fetched_log.impersonated_by) == str(test_admin_user.id)
        assert fetched_log.impersonator is not None
        assert fetched_log.impersonator.email == test_admin_user.email


class TestAuditServiceImpersonationContext:
    """Tests for audit service methods with impersonation context."""

    @pytest.mark.asyncio
    async def test_audit_service_log_create_with_impersonation(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test audit service log_create captures impersonation context."""
        await audit_service.log_create(
            session=async_session,
            organization_id=str(test_organization.id),
            resource_type="User",
            resource_id=str(test_user.id),
            actor_id=str(test_user.id),
            ip_address="192.168.1.1",
            resource_data={"email": "newuser@test.com"},
            impersonated_by=str(test_admin_user.id),
        )

        logs, total = await get_audit_logs(
            session=async_session,
            organization_id=str(test_organization.id),
        )

        assert total == 1
        assert logs[0].action == "CREATE"
        assert str(logs[0].impersonated_by) == str(test_admin_user.id)

    @pytest.mark.asyncio
    async def test_audit_service_log_update_with_impersonation(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test audit service log_update captures impersonation context."""
        await audit_service.log_update(
            session=async_session,
            organization_id=str(test_organization.id),
            resource_type="User",
            resource_id=str(test_user.id),
            old_values={"email": "old@test.com"},
            new_values={"email": "new@test.com"},
            actor_id=str(test_user.id),
            impersonated_by=str(test_admin_user.id),
        )

        logs, total = await get_audit_logs(
            session=async_session,
            organization_id=str(test_organization.id),
        )

        assert total == 1
        assert logs[0].action == "UPDATE"
        assert str(logs[0].impersonated_by) == str(test_admin_user.id)

    @pytest.mark.asyncio
    async def test_audit_service_log_delete_with_impersonation(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test audit service log_delete captures impersonation context."""
        await audit_service.log_delete(
            session=async_session,
            organization_id=str(test_organization.id),
            resource_type="User",
            resource_id=str(test_user.id),
            actor_id=str(test_user.id),
            resource_data={"email": "deleted@test.com"},
            impersonated_by=str(test_admin_user.id),
        )

        logs, total = await get_audit_logs(
            session=async_session,
            organization_id=str(test_organization.id),
        )

        assert total == 1
        assert logs[0].action == "DELETE"
        assert str(logs[0].impersonated_by) == str(test_admin_user.id)

    @pytest.mark.asyncio
    async def test_audit_service_log_action_with_impersonation(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test audit service log_action captures impersonation context."""
        await audit_service.log_action(
            session=async_session,
            organization_id=str(test_organization.id),
            action=AuditAction.CREATE,
            resource_type="Role",
            resource_id=str(test_user.id),
            actor_id=str(test_user.id),
            changes={"name": {"old": None, "new": "New Role"}},
            impersonated_by=str(test_admin_user.id),
        )

        logs, total = await get_audit_logs(
            session=async_session,
            organization_id=str(test_organization.id),
        )

        assert total == 1
        assert str(logs[0].impersonated_by) == str(test_admin_user.id)


class TestAuditLogImpersonationDistinction:
    """Tests to verify impersonation actions are distinguishable from regular actions."""

    @pytest.mark.asyncio
    async def test_can_distinguish_impersonated_actions(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test that impersonated actions can be distinguished from regular actions."""
        # Create a regular action (no impersonation)
        await create_audit_log(
            session=async_session,
            organization_id=str(test_organization.id),
            action=AuditAction.CREATE,
            resource_type="User",
            resource_id=str(test_user.id),
            actor_id=str(test_user.id),
        )

        # Create an impersonated action
        await create_audit_log(
            session=async_session,
            organization_id=str(test_organization.id),
            action=AuditAction.UPDATE,
            resource_type="User",
            resource_id=str(test_user.id),
            actor_id=str(test_user.id),
            impersonated_by=str(test_admin_user.id),
        )

        logs, total = await get_audit_logs(
            session=async_session,
            organization_id=str(test_organization.id),
        )

        assert total == 2

        # Find the regular action (no impersonation)
        regular_actions = [log for log in logs if log.impersonated_by is None]
        assert len(regular_actions) == 1
        assert regular_actions[0].action == "CREATE"

        # Find the impersonated action
        impersonated_actions = [log for log in logs if log.impersonated_by is not None]
        assert len(impersonated_actions) == 1
        assert impersonated_actions[0].action == "UPDATE"
        assert str(impersonated_actions[0].impersonated_by) == str(test_admin_user.id)

    @pytest.mark.asyncio
    async def test_multiple_impersonated_actions_by_same_admin(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test tracking multiple actions by the same impersonator."""
        # Create multiple actions during impersonation session
        for action in [AuditAction.CREATE, AuditAction.UPDATE, AuditAction.DELETE]:
            await create_audit_log(
                session=async_session,
                organization_id=str(test_organization.id),
                action=action,
                resource_type="User",
                resource_id=str(test_user.id),
                actor_id=str(test_user.id),
                impersonated_by=str(test_admin_user.id),
            )

        logs, total = await get_audit_logs(
            session=async_session,
            organization_id=str(test_organization.id),
        )

        assert total == 3
        # All actions should have the same impersonator
        for log in logs:
            assert str(log.impersonated_by) == str(test_admin_user.id)


class TestFormatDuration:
    """Tests for the format_duration helper function."""

    def test_format_seconds(self):
        """Test formatting durations less than a minute."""
        assert format_duration(1) == "1 second"
        assert format_duration(30) == "30 seconds"
        assert format_duration(59) == "59 seconds"

    def test_format_minutes(self):
        """Test formatting durations in minutes."""
        assert format_duration(60) == "1 minute"
        assert format_duration(120) == "2 minutes"
        assert format_duration(300) == "5 minutes"
        assert format_duration(3540) == "59 minutes"

    def test_format_hours(self):
        """Test formatting durations in hours."""
        assert format_duration(3600) == "1 hour"
        assert format_duration(7200) == "2 hours"

    def test_format_hours_and_minutes(self):
        """Test formatting durations with hours and minutes."""
        assert format_duration(3660) == "1 hour 1 minute"
        assert format_duration(3720) == "1 hour 2 minutes"
        assert format_duration(7260) == "2 hours 1 minute"
        assert format_duration(5400) == "1 hour 30 minutes"


class TestImpersonationNotifier:
    """Tests for the ImpersonationNotifier service."""

    @pytest.mark.asyncio
    async def test_notify_start_sends_email_and_in_app(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test that notify_start sends both email and in-app notifications."""
        started_at = datetime.now(timezone.utc)

        with patch.object(
            impersonation_notifier, "_get_user", new_callable=AsyncMock
        ) as mock_get_user:
            mock_get_user.return_value = test_admin_user

            with patch(
                "src.services.notifications.impersonation_notifier.notification_dispatcher"
            ) as mock_dispatcher:
                mock_dispatcher.send_to_user = AsyncMock(
                    return_value={"id": "email-123", "status": "sent"}
                )
                mock_dispatcher.send_in_app_notification = AsyncMock(
                    return_value={"id": "in-app-123", "status": "sent"}
                )

                result = await impersonation_notifier.notify_start(
                    session=async_session,
                    target_user_id=str(test_user.id),
                    target_organization_id=str(test_organization.id),
                    impersonator_id=str(test_admin_user.id),
                    started_at=started_at,
                )

                # Verify email was sent
                mock_dispatcher.send_to_user.assert_called_once()
                email_call = mock_dispatcher.send_to_user.call_args
                assert email_call.kwargs["channel"] == "email"
                assert email_call.kwargs["user_id"] == str(test_user.id)
                assert email_call.kwargs["organization_id"] == str(test_organization.id)
                assert email_call.kwargs["is_urgent"] is True
                assert "Account Access Notification" in email_call.kwargs["subject"]

                # Verify in-app notification was sent
                mock_dispatcher.send_in_app_notification.assert_called_once()
                in_app_call = mock_dispatcher.send_in_app_notification.call_args
                assert in_app_call.kwargs["user_id"] == str(test_user.id)
                assert "Account Access Started" in in_app_call.kwargs["title"]

                # Verify result contains both notifications
                assert "email" in result
                assert "in_app" in result

    @pytest.mark.asyncio
    async def test_notify_end_sends_email_and_in_app_with_duration(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test that notify_end sends notifications with session duration."""
        started_at = datetime.now(timezone.utc) - timedelta(hours=1, minutes=30)
        ended_at = datetime.now(timezone.utc)

        with patch.object(
            impersonation_notifier, "_get_user", new_callable=AsyncMock
        ) as mock_get_user:
            mock_get_user.return_value = test_admin_user

            with patch(
                "src.services.notifications.impersonation_notifier.notification_dispatcher"
            ) as mock_dispatcher:
                mock_dispatcher.send_to_user = AsyncMock(
                    return_value={"id": "email-123", "status": "sent"}
                )
                mock_dispatcher.send_in_app_notification = AsyncMock(
                    return_value={"id": "in-app-123", "status": "sent"}
                )

                result = await impersonation_notifier.notify_end(
                    session=async_session,
                    target_user_id=str(test_user.id),
                    target_organization_id=str(test_organization.id),
                    impersonator_id=str(test_admin_user.id),
                    started_at=started_at,
                    ended_at=ended_at,
                )

                # Verify email was sent with duration
                mock_dispatcher.send_to_user.assert_called_once()
                email_call = mock_dispatcher.send_to_user.call_args
                assert email_call.kwargs["channel"] == "email"
                assert "Account Access Ended" in email_call.kwargs["subject"]
                assert "hour" in email_call.kwargs["content"]  # Duration mentioned
                assert "30 minute" in email_call.kwargs["content"]

                # Verify in-app notification includes duration
                mock_dispatcher.send_in_app_notification.assert_called_once()
                in_app_call = mock_dispatcher.send_in_app_notification.call_args
                assert "Duration" in in_app_call.kwargs["body"]

                assert "email" in result
                assert "in_app" in result

    @pytest.mark.asyncio
    async def test_notify_start_handles_missing_impersonator(
        self, async_session, test_organization, test_user
    ):
        """Test that notify_start handles case when impersonator not found."""
        started_at = datetime.now(timezone.utc)

        with patch.object(
            impersonation_notifier, "_get_user", new_callable=AsyncMock
        ) as mock_get_user:
            mock_get_user.return_value = None

            result = await impersonation_notifier.notify_start(
                session=async_session,
                target_user_id=str(test_user.id),
                target_organization_id=str(test_organization.id),
                impersonator_id="00000000-0000-0000-0000-000000000000",
                started_at=started_at,
            )

            assert result.get("error") == "Impersonator not found"
            assert result.get("email") is None
            assert result.get("in_app") is None

    @pytest.mark.asyncio
    async def test_notify_end_handles_missing_impersonator(
        self, async_session, test_organization, test_user
    ):
        """Test that notify_end handles case when impersonator not found."""
        started_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        ended_at = datetime.now(timezone.utc)

        with patch.object(
            impersonation_notifier, "_get_user", new_callable=AsyncMock
        ) as mock_get_user:
            mock_get_user.return_value = None

            result = await impersonation_notifier.notify_end(
                session=async_session,
                target_user_id=str(test_user.id),
                target_organization_id=str(test_organization.id),
                impersonator_id="00000000-0000-0000-0000-000000000000",
                started_at=started_at,
                ended_at=ended_at,
            )

            assert result.get("error") == "Impersonator not found"

    @pytest.mark.asyncio
    async def test_notify_start_includes_impersonator_name(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test that start notification includes impersonator's name."""
        started_at = datetime.now(timezone.utc)

        with patch.object(
            impersonation_notifier, "_get_user", new_callable=AsyncMock
        ) as mock_get_user:
            # Set up admin user with name
            test_admin_user.first_name = "Admin"
            test_admin_user.last_name = "User"
            mock_get_user.return_value = test_admin_user

            with patch(
                "src.services.notifications.impersonation_notifier.notification_dispatcher"
            ) as mock_dispatcher:
                mock_dispatcher.send_to_user = AsyncMock(return_value={"id": "123"})
                mock_dispatcher.send_in_app_notification = AsyncMock(
                    return_value={"id": "456"}
                )

                await impersonation_notifier.notify_start(
                    session=async_session,
                    target_user_id=str(test_user.id),
                    target_organization_id=str(test_organization.id),
                    impersonator_id=str(test_admin_user.id),
                    started_at=started_at,
                )

                # Verify impersonator name is in the email content
                email_call = mock_dispatcher.send_to_user.call_args
                assert "Admin User" in email_call.kwargs["content"]

                # Verify impersonator name is in in-app body
                in_app_call = mock_dispatcher.send_in_app_notification.call_args
                assert "Admin User" in in_app_call.kwargs["body"]

    @pytest.mark.asyncio
    async def test_notify_handles_notification_errors_gracefully(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test that notification errors are handled without raising exceptions."""
        started_at = datetime.now(timezone.utc)

        with patch.object(
            impersonation_notifier, "_get_user", new_callable=AsyncMock
        ) as mock_get_user:
            mock_get_user.return_value = test_admin_user

            with patch(
                "src.services.notifications.impersonation_notifier.notification_dispatcher"
            ) as mock_dispatcher:
                # Simulate email failure
                mock_dispatcher.send_to_user = AsyncMock(
                    side_effect=Exception("Email service unavailable")
                )
                mock_dispatcher.send_in_app_notification = AsyncMock(
                    return_value={"id": "in-app-123", "status": "sent"}
                )

                # Should not raise, but return error info
                result = await impersonation_notifier.notify_start(
                    session=async_session,
                    target_user_id=str(test_user.id),
                    target_organization_id=str(test_organization.id),
                    impersonator_id=str(test_admin_user.id),
                    started_at=started_at,
                )

                # Email failed but in-app succeeded
                assert "error" in result["email"]
                assert result["in_app"] is not None


class TestMyImpersonationHistoryCrud:
    """Tests for the get_my_impersonation_history CRUD function."""

    @pytest.mark.asyncio
    async def test_get_my_impersonation_history_returns_ended_sessions(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test that only ended sessions are returned."""
        from src.crud.impersonation_session import (
            create_session,
            end_session,
            get_my_impersonation_history,
        )

        # Create a completed session
        session1 = await create_session(
            session=async_session,
            impersonator_id=str(test_admin_user.id),
            target_user_id=str(test_user.id),
            target_organization_id=str(test_organization.id),
            ip_address="192.168.1.1",
        )
        await end_session(async_session, str(session1.id))

        # Create an active session (not ended)
        await create_session(
            session=async_session,
            impersonator_id=str(test_admin_user.id),
            target_user_id=str(test_user.id),
            target_organization_id=str(test_organization.id),
            ip_address="192.168.1.2",
        )

        # Get history - should only return ended session
        sessions, total = await get_my_impersonation_history(
            session=async_session,
            target_user_id=str(test_user.id),
            organization_id=str(test_organization.id),
        )

        assert total == 1
        assert len(sessions) == 1
        assert sessions[0].id == session1.id
        assert sessions[0].ended_time is not None

    @pytest.mark.asyncio
    async def test_get_my_impersonation_history_filters_by_target_user(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test that only sessions for the specified target user are returned."""
        import uuid

        from src.crud.impersonation_session import (
            create_session,
            end_session,
            get_my_impersonation_history,
        )
        from src.models.user import User

        # Create another user in the same organization
        other_user = User(
            id=uuid.uuid4(),
            email="other-user@test.com",
            password="hashed_password_value",
            organization_id=test_organization.id,
            first_name="Other",
            last_name="User",
        )
        async_session.add(other_user)
        await async_session.commit()

        # Create a completed session for test_user
        session_for_test_user = await create_session(
            session=async_session,
            impersonator_id=str(test_admin_user.id),
            target_user_id=str(test_user.id),
            target_organization_id=str(test_organization.id),
        )
        await end_session(async_session, str(session_for_test_user.id))

        # Create a completed session for other_user
        session_for_other_user = await create_session(
            session=async_session,
            impersonator_id=str(test_admin_user.id),
            target_user_id=str(other_user.id),
            target_organization_id=str(test_organization.id),
        )
        await end_session(async_session, str(session_for_other_user.id))

        # Get history for test_user - should only return their session
        sessions, total = await get_my_impersonation_history(
            session=async_session,
            target_user_id=str(test_user.id),
            organization_id=str(test_organization.id),
        )

        assert total == 1
        assert len(sessions) == 1
        assert sessions[0].id == session_for_test_user.id

        # Get history for other_user - should only return their session
        sessions2, total2 = await get_my_impersonation_history(
            session=async_session,
            target_user_id=str(other_user.id),
            organization_id=str(test_organization.id),
        )

        assert total2 == 1
        assert len(sessions2) == 1
        assert sessions2[0].id == session_for_other_user.id

    @pytest.mark.asyncio
    async def test_get_my_impersonation_history_filters_by_organization(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test multi-tenancy: only sessions in same org are returned."""
        import uuid

        from src.crud.impersonation_session import (
            create_session,
            end_session,
            get_my_impersonation_history,
        )
        from src.models.organization import Organization

        # Create a different organization
        other_org = Organization(
            id=uuid.uuid4(),
            name="Other Org",
            slug="other-org",
            is_active=True,
        )
        async_session.add(other_org)
        await async_session.commit()

        # Create session in user's org
        session1 = await create_session(
            session=async_session,
            impersonator_id=str(test_admin_user.id),
            target_user_id=str(test_user.id),
            target_organization_id=str(test_organization.id),
        )
        await end_session(async_session, str(session1.id))

        # Create session in different org (shouldn't happen in practice but test isolation)
        session2 = await create_session(
            session=async_session,
            impersonator_id=str(test_admin_user.id),
            target_user_id=str(test_user.id),
            target_organization_id=str(other_org.id),
        )
        await end_session(async_session, str(session2.id))

        # Get history for user's org - should only return session in that org
        sessions, total = await get_my_impersonation_history(
            session=async_session,
            target_user_id=str(test_user.id),
            organization_id=str(test_organization.id),
        )

        assert total == 1
        assert len(sessions) == 1
        assert sessions[0].id == session1.id

    @pytest.mark.asyncio
    async def test_get_my_impersonation_history_includes_impersonator_relationship(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test that impersonator relationship is eagerly loaded."""
        from src.crud.impersonation_session import (
            create_session,
            end_session,
            get_my_impersonation_history,
        )

        session1 = await create_session(
            session=async_session,
            impersonator_id=str(test_admin_user.id),
            target_user_id=str(test_user.id),
            target_organization_id=str(test_organization.id),
        )
        await end_session(async_session, str(session1.id))

        sessions, total = await get_my_impersonation_history(
            session=async_session,
            target_user_id=str(test_user.id),
            organization_id=str(test_organization.id),
        )

        assert total == 1
        assert sessions[0].impersonator is not None
        assert sessions[0].impersonator.id == test_admin_user.id
        assert sessions[0].impersonator.email == test_admin_user.email

    @pytest.mark.asyncio
    async def test_get_my_impersonation_history_pagination(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test pagination works correctly."""
        from src.crud.impersonation_session import (
            create_session,
            end_session,
            get_my_impersonation_history,
        )

        # Create 5 completed sessions
        for _ in range(5):
            s = await create_session(
                session=async_session,
                impersonator_id=str(test_admin_user.id),
                target_user_id=str(test_user.id),
                target_organization_id=str(test_organization.id),
            )
            await end_session(async_session, str(s.id))

        # Get first page (limit 2)
        sessions, total = await get_my_impersonation_history(
            session=async_session,
            target_user_id=str(test_user.id),
            organization_id=str(test_organization.id),
            limit=2,
            offset=0,
        )

        assert total == 5
        assert len(sessions) == 2

        # Get second page
        sessions2, total2 = await get_my_impersonation_history(
            session=async_session,
            target_user_id=str(test_user.id),
            organization_id=str(test_organization.id),
            limit=2,
            offset=2,
        )

        assert total2 == 5
        assert len(sessions2) == 2

    @pytest.mark.asyncio
    async def test_get_my_impersonation_history_empty_result(
        self, async_session, test_organization, test_user
    ):
        """Test that empty result returns correctly."""
        from src.crud.impersonation_session import get_my_impersonation_history

        sessions, total = await get_my_impersonation_history(
            session=async_session,
            target_user_id=str(test_user.id),
            organization_id=str(test_organization.id),
        )

        assert total == 0
        assert len(sessions) == 0

    @pytest.mark.asyncio
    async def test_get_my_impersonation_history_ordered_by_created_time_desc(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test that sessions are ordered by created_time descending (most recent first)."""
        import asyncio

        from src.crud.impersonation_session import (
            create_session,
            end_session,
            get_my_impersonation_history,
        )

        # Create sessions with small delay to ensure different timestamps
        session_ids = []
        for _ in range(3):
            s = await create_session(
                session=async_session,
                impersonator_id=str(test_admin_user.id),
                target_user_id=str(test_user.id),
                target_organization_id=str(test_organization.id),
            )
            await end_session(async_session, str(s.id))
            session_ids.append(s.id)
            await asyncio.sleep(0.01)  # Small delay for timestamp difference

        sessions, _ = await get_my_impersonation_history(
            session=async_session,
            target_user_id=str(test_user.id),
            organization_id=str(test_organization.id),
        )

        # Most recent should be first (last created)
        assert sessions[0].id == session_ids[2]
        assert sessions[2].id == session_ids[0]


class TestMyImpersonationHistorySerializer:
    """Tests for impersonation history serializers."""

    def test_my_impersonation_history_item_duration_seconds(self):
        """Test that duration_seconds property calculates correctly."""
        import uuid

        from src.serialisers.impersonation_session import (
            ImpersonatorInfo,
            MyImpersonationHistoryItem,
        )

        started_at = datetime.now(timezone.utc) - timedelta(hours=1, minutes=30)
        ended_at = datetime.now(timezone.utc)

        item = MyImpersonationHistoryItem(
            id=uuid.uuid4(),
            created_time=started_at,
            ended_time=ended_at,
            impersonator=ImpersonatorInfo(
                id=uuid.uuid4(),
                email="admin@test.com",
                first_name="Admin",
                last_name="User",
            ),
        )

        # Duration should be approximately 1 hour 30 minutes = 5400 seconds
        assert 5399 <= item.duration_seconds <= 5401

    def test_impersonator_info_from_attributes(self):
        """Test ImpersonatorInfo can be created from ORM attributes."""
        import uuid

        from src.serialisers.impersonation_session import ImpersonatorInfo

        # Simulate an ORM object with required attributes
        class MockUser:
            id = uuid.uuid4()
            email = "admin@example.com"
            first_name = "John"
            last_name = "Doe"

        user = MockUser()
        info = ImpersonatorInfo.model_validate(user)

        assert info.id == user.id
        assert info.email == "admin@example.com"
        assert info.first_name == "John"
        assert info.last_name == "Doe"

    def test_impersonator_info_optional_names(self):
        """Test ImpersonatorInfo handles optional name fields."""
        import uuid

        from src.serialisers.impersonation_session import ImpersonatorInfo

        info = ImpersonatorInfo(
            id=uuid.uuid4(),
            email="admin@example.com",
        )

        assert info.first_name is None
        assert info.last_name is None
