"""
Regression tests for two notification-path bypasses.

1. The in-app inbox wrote UserNotification rows directly, never passing through
   crud.notification.create_notification, so none of the credential scrubbing
   that guards the Notification table applied. An in-app OTP or a rendered
   reset link was stored verbatim.

2. N9 was only half closed: the SMTP email wrapper in the dispatcher still fell
   back to the process-global email_service when no organization config
   resolved, so an org with a deliberate email configuration could still have
   its mail sent over the platform's SMTP, from the platform's sender.

3. The deferred 2FA send stores the full rendered body in the API-exposed
   Notification.extra_data column because the worker reads it back as the
   delivery payload. That payload must survive until delivery, and must not
   survive it.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.crud.notification import REDACTED_MARKER
from src.crud.user_notification import get_user_notifications
from src.models import OrganizationTwoFactorSettings, TwoFactorPolicy
from src.models.notification import Notification
from src.services.notifications.dispatcher import notification_dispatcher
from src.services.notifications.in_app_provider import in_app_provider
from src.services.notifications.preference_checker import PreferenceCheckResult
from src.workers.tasks import send_notification_task


# A realistic one-time code and a real-shaped reset URL. Both are exactly what
# the in-app path would receive if a fork routed OTP or password-reset
# notifications through the in-app channel.
LIVE_OTP = "483920"
LIVE_OTP_BODY = (
    f"Your verification code is: {LIVE_OTP[:3]}-{LIVE_OTP[3:]}. "
    "It expires in 10 minutes."
)
LIVE_RESET_TOKEN = "Xy7Kq2mB9tR4wZ1nP6vL0sJ3cH8dG5fA"
LIVE_RESET_URL = f"https://app.example.com/reset-password?token={LIVE_RESET_TOKEN}"
LIVE_BODY_WITH_LINK = f"Reset your password here: {LIVE_RESET_URL}"


class _RecordingProvider:
    """Stub provider that records exactly what the transport was handed."""

    provider_name = "recording"
    channel = "email"

    def __init__(self, success: bool = True):
        self.success = success
        self.calls: list[dict[str, Any]] = []

    async def send(
        self,
        recipient: str,
        message: str,
        subject: Optional[str] = None,
        html_message: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        self.calls.append(
            {
                "recipient": recipient,
                "message": message,
                "subject": subject,
                "html_message": html_message,
            }
        )

        class _Result:
            def __init__(self, success: bool):
                self.success = success
                self.status = "sent" if success else "failed"
                self.provider_message_id = "rec-1" if success else None
                self.error_message = None if success else "nope"

        return _Result(self.success)


def _mock_context(async_session: AsyncSession):
    """ARQ-style context whose session_factory yields the test session."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def session_factory():
        yield async_session

    class MockContext:
        def get(self, key):
            if key == "session_factory":
                return session_factory
            return None

    return MockContext()


# ---------------------------------------------------------------------------
# 1. In-app inbox must not persist credentials
# ---------------------------------------------------------------------------


class TestInAppPersistPathRedaction:
    """The stored row is scrubbed; the WebSocket transport still gets the truth."""

    @pytest.mark.asyncio
    async def test_otp_and_reset_url_scrubbed_in_row_but_not_in_broadcast(
        self, async_session, test_organization, test_user
    ):
        broadcast = AsyncMock(return_value=True)

        with patch(
            "src.services.notifications.in_app_provider.message_broadcaster.send_to_user",
            new=broadcast,
        ):
            result = await in_app_provider.send_in_app(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
                title=f"Your verification code: {LIVE_OTP[:3]}-{LIVE_OTP[3:]}",
                body=f"{LIVE_OTP_BODY}\n{LIVE_BODY_WITH_LINK}",
            )

        assert result.success is True

        # The transport got the real content - delivery is unaffected.
        broadcast.assert_awaited_once()
        pushed = broadcast.await_args.kwargs["payload"]["notification"]
        assert f"{LIVE_OTP[:3]}-{LIVE_OTP[3:]}" in pushed["title"]
        assert f"{LIVE_OTP[:3]}-{LIVE_OTP[3:]}" in pushed["body"]
        assert LIVE_RESET_TOKEN in pushed["body"]

        # The persisted row did not.
        async_session.expunge_all()
        rows, _ = await get_user_notifications(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            limit=5,
        )
        stored = rows[0]

        assert REDACTED_MARKER in stored.title
        assert f"{LIVE_OTP[:3]}-{LIVE_OTP[3:]}" not in stored.title

        assert stored.body is not None
        assert f"{LIVE_OTP[:3]}-{LIVE_OTP[3:]}" not in stored.body
        assert LIVE_OTP not in stored.body
        assert LIVE_RESET_TOKEN not in stored.body
        assert REDACTED_MARKER in stored.body

    @pytest.mark.asyncio
    async def test_provider_interface_send_is_also_scrubbed(
        self, async_session, test_organization, test_user
    ):
        """The generic NotificationProvider.send() entry point routes through
        the same chokepoint, so it cannot be used to sidestep the scrubbing."""
        with patch(
            "src.services.notifications.in_app_provider.message_broadcaster.send_to_user",
            new=AsyncMock(return_value=True),
        ):
            result = await in_app_provider.send(
                recipient="",
                message=LIVE_OTP_BODY,
                subject="Security",
                metadata={
                    "session": async_session,
                    "organization_id": str(test_organization.id),
                    "user_id": str(test_user.id),
                },
            )

        assert result.success is True

        async_session.expunge_all()
        rows, _ = await get_user_notifications(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            limit=5,
        )
        assert rows[0].body is not None
        assert f"{LIVE_OTP[:3]}-{LIVE_OTP[3:]}" not in rows[0].body

    @pytest.mark.asyncio
    async def test_ordinary_notification_text_survives_intact(
        self, async_session, test_organization, test_user
    ):
        """Scrubbing must not mangle the notifications that carry no secret."""
        body = "Your export finished. 42 rows were written to report.csv."

        with patch(
            "src.services.notifications.in_app_provider.message_broadcaster.send_to_user",
            new=AsyncMock(return_value=True),
        ):
            await in_app_provider.send_in_app(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
                title="Export complete",
                body=body,
                link="/exports/42",
            )

        async_session.expunge_all()
        rows, _ = await get_user_notifications(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            limit=5,
        )
        assert rows[0].title == "Export complete"
        assert rows[0].body == body
        assert rows[0].link == "/exports/42"


# ---------------------------------------------------------------------------
# 2. N9 - the second email wrapper must not fall back to platform SMTP
# ---------------------------------------------------------------------------


class TestEmailWrapperNoGlobalFallback:
    """An org email send with no resolvable config fails; it does not downgrade."""

    @pytest.mark.asyncio
    async def test_registered_email_provider_refuses_without_org_config(self):
        """dispatcher._get_provider("email") is the unconfigured instance."""
        await notification_dispatcher._ensure_initialized()
        provider = notification_dispatcher._get_provider("email")

        assert provider is not None
        assert provider.provider_name == "smtp"

        with patch(
            "src.services.notifications.email_provider.email_service"
        ) as global_service:
            result = await provider.send(
                recipient="user@example.com",
                message="Hello",
                subject="Subject",
            )

        assert result.success is False
        assert result.status == "failed"
        assert result.error_message
        global_service.send_email.assert_not_called()
        global_service.send_with_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_unresolvable_config_records_failed_notification(
        self, async_session, test_organization, test_user
    ):
        """send_notification records a failed row rather than sending as the
        platform. This is the caller check: it must not raise."""
        with patch(
            "src.services.notifications.dispatcher.get_effective_email_config",
            new=AsyncMock(side_effect=RuntimeError("settings table unavailable")),
        ), patch(
            "src.services.notifications.preference_checker.preference_checker.check_can_send",
            new=AsyncMock(return_value=PreferenceCheckResult(allowed=True)),
        ), patch(
            "src.services.notifications.email_provider.email_service"
        ) as global_service:
            record = await notification_dispatcher.send_notification(
                session=async_session,
                user_id=str(test_user.id),
                organization_id=str(test_organization.id),
                channel="email",
                recipient=test_user.email,
                content="Hello",
                subject="Subject",
            )

        assert record is not None
        assert record["status"] == "failed"
        assert record["provider"] is None
        assert "No provider available" in (record["error_message"] or "")
        global_service.send_email.assert_not_called()
        global_service.send_with_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_worker_caller_handles_failed_result_without_crashing(
        self, async_session, test_organization, test_user
    ):
        """The other caller: send_notification_task must record the failure and
        return normally rather than blowing up."""
        notification = Notification(
            organization_id=test_organization.id,
            user_id=test_user.id,
            channel="email",
            recipient=test_user.email,
            subject="Subject",
            body_preview="Hello",
            status="pending",
        )
        async_session.add(notification)
        await async_session.commit()
        await async_session.refresh(notification)

        with patch(
            "src.services.notifications.dispatcher.get_effective_email_config",
            new=AsyncMock(side_effect=RuntimeError("settings table unavailable")),
        ):
            with pytest.raises(Exception) as excinfo:
                await send_notification_task(
                    _mock_context(async_session), str(notification.id)
                )

        # It fails into the ARQ retry path, not with an unhandled error.
        assert excinfo.type.__name__ == "Retry"

        async_session.expunge_all()
        refreshed = (
            await async_session.execute(
                select(Notification).where(Notification.id == notification.id)
            )
        ).scalar_one()
        assert refreshed.status == "failed"
        assert refreshed.retry_count >= 1


# ---------------------------------------------------------------------------
# 3. The deferred 2FA send must still work end to end
# ---------------------------------------------------------------------------


class TestDeferred2FASendPayload:
    """extra_data["body"] is a delivery payload: it must survive until sent."""

    @pytest.mark.asyncio
    async def test_deferred_body_delivered_then_dropped_from_extra_data(
        self, async_session, test_organization, test_user
    ):
        import src.workers.two_factor_tasks
        from src.workers.two_factor_tasks import notify_2fa_mandatory_change

        settings = OrganizationTwoFactorSettings(
            organization_id=test_organization.id,
            two_factor_allowed=True,
            two_factor_policy=TwoFactorPolicy.MANDATORY.value,
            grace_period_days=7,
            enforcement_start_time=datetime.now(timezone.utc),
        )
        async_session.add(settings)
        await async_session.commit()

        original_enqueue_job = src.workers.two_factor_tasks.task_queue.enqueue_job

        async def _noop_enqueue(*args, **kwargs):
            return None

        src.workers.two_factor_tasks.task_queue.enqueue_job = _noop_enqueue
        try:
            await notify_2fa_mandatory_change(
                _mock_context(async_session), str(test_organization.id)
            )
        finally:
            src.workers.two_factor_tasks.task_queue.enqueue_job = original_enqueue_job

        notification = (
            await async_session.execute(
                select(Notification).where(
                    Notification.organization_id == test_organization.id,
                    Notification.user_id == test_user.id,
                )
            )
        ).scalar_one()

        # The full body is present before delivery - the worker needs it.
        assert notification.extra_data is not None
        full_body = notification.extra_data["body"]
        assert "mandatory Two-Factor Authentication" in full_body
        assert len(full_body) > len(notification.body_preview or "")

        provider = _RecordingProvider()
        with patch.object(
            notification_dispatcher,
            "get_email_provider",
            new=AsyncMock(return_value=provider),
        ):
            result = await send_notification_task(
                _mock_context(async_session), str(notification.id)
            )

        # Delivery still works, with the complete body rather than the preview.
        assert result["status"] == "sent"
        assert len(provider.calls) == 1
        assert provider.calls[0]["message"] == full_body
        assert provider.calls[0]["recipient"] == test_user.email

        # ...and the payload no longer lingers in the API-exposed column, while
        # the genuine metadata does.
        async_session.expunge_all()
        refreshed = (
            await async_session.execute(
                select(Notification).where(Notification.id == notification.id)
            )
        ).scalar_one()
        assert refreshed.status == "sent"
        assert refreshed.extra_data is not None
        assert "body" not in refreshed.extra_data
        assert refreshed.extra_data["category"] == "security"
        assert "deadline" in refreshed.extra_data
        assert refreshed.extra_data["grace_period_days"] == 7

    @pytest.mark.asyncio
    async def test_failed_send_keeps_payload_for_retry(
        self, async_session, test_organization, test_user
    ):
        notification = Notification(
            organization_id=test_organization.id,
            user_id=test_user.id,
            channel="email",
            recipient=test_user.email,
            subject="Subject",
            body_preview="preview only",
            status="pending",
            extra_data={"category": "security", "body": "the full deferred body"},
        )
        async_session.add(notification)
        await async_session.commit()
        await async_session.refresh(notification)

        provider = _RecordingProvider(success=False)
        with patch.object(
            notification_dispatcher,
            "get_email_provider",
            new=AsyncMock(return_value=provider),
        ):
            result = await send_notification_task(
                _mock_context(async_session), str(notification.id)
            )

        assert result["status"] == "failed"

        async_session.expunge_all()
        refreshed = (
            await async_session.execute(
                select(Notification).where(Notification.id == notification.id)
            )
        ).scalar_one()
        assert refreshed.extra_data["body"] == "the full deferred body"
