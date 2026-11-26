"""
Tests for ARQ background tasks.

Tests the business logic in task functions directly, without running the actual ARQ worker.
External services (email) are mocked; database operations use the test database.
"""

from dataclasses import dataclass
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.workers.tasks import (
    collect_metrics_task,
    send_email_task,
    send_otp_email_task,
    send_password_reset_email_task,
)


# ============================================================================
# SEND EMAIL TASK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_send_email_task_success():
    """Test successful email sending."""
    ctx = {}

    # Patch at the actual module location (import happens inside function)
    with patch("src.services.email.email_service") as mock_email:
        mock_email.send_email = AsyncMock(return_value=True)

        result = await send_email_task(
            ctx,
            to="user@example.com",
            subject="Test Subject",
            body="Test body content",
            html_body="<p>Test body content</p>",
        )

        assert result["status"] == "sent"
        assert result["to"] == "user@example.com"

        mock_email.send_email.assert_called_once_with(
            to="user@example.com",
            subject="Test Subject",
            body="Test body content",
            html_body="<p>Test body content</p>",
        )


@pytest.mark.asyncio
async def test_send_email_task_retries_on_failure():
    """Test that email task raises Retry on failure."""
    from arq import Retry

    ctx = {}

    with patch("src.services.email.email_service") as mock_email:
        mock_email.send_email = AsyncMock(return_value=False)

        with pytest.raises(Retry):
            await send_email_task(
                ctx,
                to="user@example.com",
                subject="Test Subject",
                body="Test body",
            )


@pytest.mark.asyncio
async def test_send_email_task_retries_on_exception():
    """Test that email task raises Retry on exception."""
    from arq import Retry

    ctx = {}

    with patch("src.services.email.email_service") as mock_email:
        mock_email.send_email = AsyncMock(side_effect=Exception("SMTP error"))

        with pytest.raises(Retry):
            await send_email_task(
                ctx,
                to="user@example.com",
                subject="Test Subject",
                body="Test body",
            )


# ============================================================================
# SEND EMAIL TASK WITH ORGANIZATION CONFIG TESTS
# ============================================================================


@dataclass
class _FakeEmailConfig:
    provider: str
    smtp_host: Optional[str] = "smtp.example.com"
    smtp_port: Optional[int] = 587
    smtp_username: Optional[str] = "user"
    smtp_password: Optional[str] = "pass"
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    sendgrid_api_key: Optional[str] = None
    sender_email: Optional[str] = "org@example.com"
    sender_name: Optional[str] = "Org"
    reply_to_email: Optional[str] = None


@pytest.mark.asyncio
async def test_send_email_task_uses_org_config_when_provided():
    """Test that email task resolves org email config and uses send_with_config."""
    fake_config = _FakeEmailConfig(provider="sendgrid", sendgrid_api_key="sg-key")

    mock_session = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    ctx = {"session_factory": mock_session_factory}

    with (
        patch("src.services.email.email_service") as mock_email,
        patch(
            "src.crud.organization_email_settings.get_effective_email_config",
            new_callable=AsyncMock,
            return_value=fake_config,
        ) as mock_get_config,
    ):
        mock_email.send_with_config = AsyncMock(return_value=True)

        result = await send_email_task(
            ctx,
            to="user@example.com",
            subject="Test",
            body="Body",
            html_body="<p>Body</p>",
            organization_id="org-123",
        )

        assert result["status"] == "sent"
        mock_get_config.assert_called_once_with(mock_session, "org-123")
        mock_email.send_with_config.assert_called_once_with(
            to="user@example.com",
            subject="Test",
            body="Body",
            html_body="<p>Body</p>",
            config=fake_config,
        )


@pytest.mark.asyncio
async def test_send_email_task_falls_back_without_org_id():
    """Test that email task uses global SMTP when no organization_id."""
    ctx = {}

    with patch("src.services.email.email_service") as mock_email:
        mock_email.send_email = AsyncMock(return_value=True)

        result = await send_email_task(
            ctx,
            to="user@example.com",
            subject="Test",
            body="Body",
        )

        assert result["status"] == "sent"
        mock_email.send_email.assert_called_once()
        # send_with_config should NOT have been called
        assert (
            not hasattr(mock_email.send_with_config, "call_count")
            or mock_email.send_with_config.call_count == 0
        )


# ============================================================================
# SEND OTP EMAIL TASK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_send_otp_email_task_success():
    """Test successful OTP email sending."""
    ctx = {}

    with patch("src.services.email.email_service") as mock_email:
        mock_email.send_email = AsyncMock(return_value=True)

        result = await send_otp_email_task(
            ctx,
            to="user@example.com",
            otp_code="1234",
            expires_minutes=15,
        )

        assert result["status"] == "sent"
        assert result["to"] == "user@example.com"

        # Verify email was called with correct subject
        call_args = mock_email.send_email.call_args
        assert call_args.kwargs["subject"] == "Email Verification Code"
        # OTP is formatted as "123-4" (first 3 digits, hyphen, remaining)
        assert "123-4" in call_args.kwargs["body"]
        assert "15 minutes" in call_args.kwargs["body"]


@pytest.mark.asyncio
async def test_send_otp_email_task_includes_html():
    """Test that OTP email includes HTML body."""
    ctx = {}

    with patch("src.services.email.email_service") as mock_email:
        mock_email.send_email = AsyncMock(return_value=True)

        await send_otp_email_task(
            ctx,
            to="user@example.com",
            otp_code="5678",
            expires_minutes=10,
        )

        call_args = mock_email.send_email.call_args
        html_body = call_args.kwargs["html_body"]

        assert html_body is not None
        # OTP is formatted as "567-8" (first 3 digits, hyphen, remaining)
        assert "567-8" in html_body
        assert "10 minutes" in html_body
        assert "<html>" in html_body


# ============================================================================
# SEND PASSWORD RESET EMAIL TASK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_send_password_reset_email_task_success():
    """Test successful password reset email sending."""
    ctx = {}

    with patch("src.services.email.email_service") as mock_email:
        mock_email.send_email = AsyncMock(return_value=True)

        result = await send_password_reset_email_task(
            ctx,
            to="user@example.com",
            reset_token="abc123token",
            reset_url="https://example.com/reset?token=abc123token",
        )

        assert result["status"] == "sent"
        assert result["to"] == "user@example.com"

        call_args = mock_email.send_email.call_args
        assert call_args.kwargs["subject"] == "Password Reset Request"
        assert "https://example.com/reset?token=abc123token" in call_args.kwargs["body"]


@pytest.mark.asyncio
async def test_send_password_reset_email_task_includes_html():
    """Test that password reset email includes HTML body with link."""
    ctx = {}

    with patch("src.services.email.email_service") as mock_email:
        mock_email.send_email = AsyncMock(return_value=True)

        await send_password_reset_email_task(
            ctx,
            to="user@example.com",
            reset_token="xyz789",
            reset_url="https://app.example.com/reset-password?token=xyz789",
        )

        call_args = mock_email.send_email.call_args
        html_body = call_args.kwargs["html_body"]

        assert html_body is not None
        assert "https://app.example.com/reset-password?token=xyz789" in html_body
        assert "Reset Password" in html_body
        assert "1 hour" in html_body


# ============================================================================
# COLLECT METRICS TASK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_collect_metrics_task_returns_status():
    """Test that metrics collection task runs and returns status."""
    ctx = {}

    # Mock user_activity_service to avoid import issues (import happens inside function)
    with patch("src.services.user_activity.user_activity_service") as mock_activity:
        mock_activity.update_metrics = AsyncMock()

        result = await collect_metrics_task(ctx)

        assert result["status"] == "collected"
        assert "process_memory_mb" in result
        assert "process_cpu" in result


@pytest.mark.asyncio
async def test_collect_metrics_task_handles_activity_service_error():
    """Test that metrics task continues even if activity service fails."""
    ctx = {}

    with patch("src.services.user_activity.user_activity_service") as mock_activity:
        mock_activity.update_metrics = AsyncMock(side_effect=Exception("Redis error"))

        # Should still succeed
        result = await collect_metrics_task(ctx)

        assert result["status"] == "collected"
