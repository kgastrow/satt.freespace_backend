"""
Regression tests for notification hardening fixes.

Covers:
- N4: notification metadata / provider_message_id / error_message persistence,
      plus redaction of credential-shaped metadata values.
- N9: email must not silently bypass the configured provider.
- N8: template placeholder syntax is single-brace; unresolved placeholders warn.
- N7: notification categories are seeded for every dispatched category_code.
"""

from pathlib import Path
import re
from unittest.mock import AsyncMock, patch

import pytest

from src.crud.notification import (
    BODY_PREVIEW_MAX_LENGTH,
    REDACTED_MARKER,
    create_notification,
    get_notification_by_id,
    prepare_body_preview,
    redact_notification_metadata,
    scrub_credential_text,
)
from src.crud.organization_email_settings import EmailConfig
from src.services.notifications.dispatcher import (
    NotificationResult,
    notification_dispatcher,
)
from src.services.notifications.email_provider import EmailProvider
from src.services.notifications.preference_checker import (
    PreferenceCheckResult,
    preference_checker,
)
from src.services.notifications.template_renderer import TemplateRenderer
from src.services.organization_seeding import (
    DEFAULT_NOTIFICATION_CATEGORIES,
    get_default_notification_category_codes,
    seed_default_notification_categories,
)


# ---------------------------------------------------------------------------
# N4 - metadata / provider_message_id / error_message persistence + redaction
# ---------------------------------------------------------------------------


class TestNotificationFieldPersistence:
    """create_notification must persist every field the dispatcher passes."""

    @pytest.mark.asyncio
    async def test_round_trip_persists_extra_data_message_id_and_error(
        self, async_session, test_organization, test_user
    ):
        """extra_data, provider_message_id and error_message all survive a write."""
        notification = await create_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            channel="email",
            recipient="user@example.com",
            data={
                "provider": "sendgrid",
                "subject": "Hello",
                "body_preview": "Hello there",
                "status": "failed",
                "provider_message_id": "sg-message-123",
                "error_message": "550 mailbox unavailable",
                "metadata": {"campaign": "spring", "attempt": 2},
            },
        )

        # Re-read from the DB so we assert on the column, not an instance attribute.
        async_session.expunge_all()

        stored = await get_notification_by_id(
            session=async_session,
            notification_id=str(notification.id),
            organization_id=str(test_organization.id),
        )

        assert stored is not None
        assert stored.extra_data == {"campaign": "spring", "attempt": 2}
        assert stored.provider_message_id == "sg-message-123"
        assert stored.error_message == "550 mailbox unavailable"
        assert stored.status == "failed"

    @pytest.mark.asyncio
    async def test_metadata_is_not_written_to_shadowed_metadata_attribute(
        self, async_session, test_organization, test_user
    ):
        """The value lands on extra_data (the column), never on `metadata`."""
        notification = await create_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            channel="in_app",
            recipient="user@example.com",
            data={"metadata": {"source": "unit-test"}},
        )

        assert notification.extra_data == {"source": "unit-test"}
        # `metadata` on a declarative class is SQLAlchemy's MetaData object.
        assert not isinstance(notification.metadata, dict)

    @pytest.mark.asyncio
    async def test_no_metadata_leaves_extra_data_null(
        self, async_session, test_organization, test_user
    ):
        notification = await create_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            channel="email",
            recipient="user@example.com",
            data={},
        )
        assert notification.extra_data is None


# A password reset token is `secrets.token_urlsafe(24)` - 32 URL-safe chars.
LIVE_RESET_TOKEN = "xLp2Qw9zAbCdEfGhIjKlMnOpQrStUvWx"
LIVE_RESET_URL = (
    f"https://app.example.com/reset-password?token={LIVE_RESET_TOKEN}&org=acme"
)
# The exact body every OTP path in this repo sends (src/api/user_otp.py,
# src/api/user.py) - a 6-digit code split with a hyphen.
LIVE_OTP = "483920"
LIVE_OTP_BODY = (
    "Your verification code is: 483-920\n\nThis code will expire in 10 minutes."
)


class TestNotificationMetadataRedaction:
    """Credential-shaped metadata must never reach the queryable column."""

    @pytest.mark.asyncio
    async def test_reset_token_is_stored_redacted(
        self, async_session, test_organization, test_user
    ):
        """A password-reset token in template vars is redacted before persisting.

        The link values here are REALISTIC: `src/api/auth.py` builds
        `{PUBLIC_URL_FRONTEND}/reset-password?token={reset_token}&org=...`, so a
        reset link always carries the live token. An earlier version of this
        test used a token-free `https://app.example.com/reset`, which passed
        while a live token would have been stored in cleartext.
        """
        secret = "eyJhbGciOi.super-secret-reset-token.signature"

        notification = await create_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            channel="email",
            recipient="user@example.com",
            data={
                "status": "sent",
                "metadata": {
                    "first_name": "Ada",
                    "reset_token": secret,
                    "reset_link": LIVE_RESET_URL,
                    # An innocuously named key is the interesting case: no key
                    # denylist can anticipate every fork's naming, so the value
                    # itself has to be scrubbed.
                    "action_url": LIVE_RESET_URL,
                },
            },
        )

        async_session.expunge_all()

        stored = await get_notification_by_id(
            session=async_session,
            notification_id=str(notification.id),
            organization_id=str(test_organization.id),
        )

        assert stored is not None
        assert stored.extra_data is not None
        assert stored.extra_data["reset_token"] == REDACTED_MARKER
        assert secret not in str(stored.extra_data)
        # The live token must not survive under ANY key, whatever its name.
        assert LIVE_RESET_TOKEN not in str(stored.extra_data)
        # ...while the non-secret part of the link stays diagnosable.
        assert stored.extra_data["action_url"].startswith(
            "https://app.example.com/reset-password?token="
        )
        # Non-sensitive diagnostics are preserved.
        assert stored.extra_data["first_name"] == "Ada"

    @pytest.mark.parametrize(
        "key",
        [
            "reset_token",
            "otp",
            "otp_code",
            "verification_code",
            "password",
            "temp_password",
            "api_key",
            "sendgrid_api_key",
            "client_secret",
            "pin",
            "Authorization",
            "session_id",
            "signature",
            # Near-misses the original denylist let through.
            "sig",
            "hmac",
            "jwt",
            "assertion",
            "saml_response",
            "mfa",
            "2fa",
            "two_factor_code",
            "provisioning_uri",
            "seed_phrase",
            "recovery",
            "qr",
            "backup_codes",
            "magic_link",
            "invite_url",
            "verification_link",
            "activation_url",
        ],
    )
    def test_sensitive_keys_are_redacted(self, key):
        result = redact_notification_metadata({key: "sensitive-value"})
        assert result[key] == REDACTED_MARKER

    @pytest.mark.parametrize(
        "key",
        ["first_name", "org_name", "campaign", "attempt", "status_callback"],
    )
    def test_benign_keys_are_preserved(self, key):
        result = redact_notification_metadata({key: "value"})
        assert result[key] == "value"

    def test_benign_url_keys_keep_the_url_but_lose_the_credential(self):
        """Generic link keys are scrubbed, not dropped.

        The previous version of this test asserted that a key containing
        "link" was PRESERVED, using a deliberately token-free URL. That is the
        bug: `{link}` is exactly the template variable a password-reset email
        renders, and it carries a live token. The key is still not on the
        denylist - dropping every URL would destroy the audit trail - but the
        VALUE is scrubbed, so the credential cannot survive.
        """
        result = redact_notification_metadata(
            {"link": LIVE_RESET_URL, "action_url": LIVE_RESET_URL}
        )

        for key in ("link", "action_url"):
            assert LIVE_RESET_TOKEN not in result[key]
            assert REDACTED_MARKER in result[key]
            assert result[key].startswith("https://app.example.com/reset-password")

    def test_nested_structures_are_redacted(self):
        """WhatsApp content_variables and other nested dicts are walked."""
        payload = {
            "content_sid": "HX123",
            "content_variables": {"1": "Ada", "otp_code": "483920"},
            "recipients": [{"email": "a@example.com", "auth_token": "abc"}],
        }
        result = redact_notification_metadata(payload)

        assert result["content_variables"]["otp_code"] == REDACTED_MARKER
        assert result["content_variables"]["1"] == "Ada"
        assert result["recipients"][0]["auth_token"] == REDACTED_MARKER
        assert result["recipients"][0]["email"] == "a@example.com"
        assert "483920" not in str(result)

    def test_input_is_not_mutated(self):
        original = {"reset_token": "abc"}
        redact_notification_metadata(original)
        assert original == {"reset_token": "abc"}

    def test_non_dict_metadata_passes_through(self):
        assert redact_notification_metadata(None) is None
        assert redact_notification_metadata("plain") == "plain"

    def test_depth_guard_replaces_structures_below_the_limit(self):
        """A structure nested past the guard is replaced wholesale, not walked."""
        payload: dict = {"secret_value": LIVE_RESET_TOKEN}
        for _ in range(12):
            payload = {"nested": payload}

        result = redact_notification_metadata(payload)

        assert LIVE_RESET_TOKEN not in str(result)
        assert REDACTED_MARKER in str(result)

    def test_depth_guard_still_walks_structures_within_the_limit(self):
        payload = {"a": {"b": {"c": {"otp_code": LIVE_OTP, "name": "Ada"}}}}
        result = redact_notification_metadata(payload)

        assert result["a"]["b"]["c"]["otp_code"] == REDACTED_MARKER
        assert result["a"]["b"]["c"]["name"] == "Ada"


class TestCredentialValueScrubbing:
    """Value-level scrubbing: the credential's SHAPE, not its key name."""

    @pytest.mark.parametrize(
        "text,secret",
        [
            # The literal OTP body every OTP path in this repo sends.
            (LIVE_OTP_BODY, "483-920"),
            ("Your verification code is: 483920", LIVE_OTP),
            ("OTP: 123456", "123456"),
            ("one-time code 987654", "987654"),
            ("Your temporary password: Tmp9xQ2z", "Tmp9xQ2z"),
            # Reset / magic links.
            (f"Click {LIVE_RESET_URL} to continue", LIVE_RESET_TOKEN),
            (
                "https://app/verify?verification_code=889213",
                "889213",
            ),
            # Auth material that can end up in an exception string.
            (
                "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc123",
                "eyJhbGciOiJIUzI1NiJ9",
            ),
            ("Bearer sk-live-9f8e7d6c5b4a3210zzz", "sk-live-9f8e7d6c5b4a3210zzz"),
            (
                "token is eyJhbGciOi.super-secret-reset-token.signature",
                "super-secret-reset-token",
            ),
            # A bare high-entropy blob with no query-string structure at all.
            (
                f"Your link: https://app.example.com/magic/{LIVE_RESET_TOKEN}",
                LIVE_RESET_TOKEN,
            ),
        ],
    )
    def test_credential_shapes_are_scrubbed(self, text, secret):
        scrubbed = scrub_credential_text(text)
        assert secret not in scrubbed, f"credential survived: {scrubbed!r}"
        assert REDACTED_MARKER in scrubbed

    @pytest.mark.parametrize(
        "text",
        [
            # Guard against over-aggressive scrubbing. Every one of these is
            # something an operator needs to be able to read.
            "550 mailbox unavailable",
            "SMTP error code: 550",
            "Twilio error code 21610: message blocked",
            "No provider available for channel: email",
            "Skipped: user_preference_disabled",
            "authentication token is invalid",
            "Your order #12345 has shipped.",
            "Hello Ada, welcome to Acme.",
            "Connection refused to mail.example.com:587",
            "Welcome! Visit https://app.example.com/dashboard to get started.",
            "Your organization has enabled mandatory Two-Factor Authentication (2FA).",
            "Notification 550e8400-e29b-41d4-a716-446655440000 not found",
            "enforcement_start_time missing from settings",
            "code=550",
            "retry=true&status=failed",
        ],
    )
    def test_ordinary_text_passes_through_unmangled(self, text):
        assert scrub_credential_text(text) == text
        assert scrub_credential_text(text, preserve_identifiers=True) == text

    def test_provider_message_ids_survive_in_diagnostic_mode(self):
        """error_message keeps provider identifiers: they ARE the diagnostic.

        A Twilio SID is 34 opaque characters and would otherwise trip the
        high-entropy backstop, so error_message opts out of that one rule while
        keeping every structural pattern.
        """
        text = "Message SM32b1e8f0a94b4c8d9e0f1a2b3c4d5e6f permanently failed"
        assert scrub_credential_text(text, preserve_identifiers=True) == text

    def test_structural_patterns_still_apply_in_diagnostic_mode(self):
        text = f"provider rejected callback {LIVE_RESET_URL}"
        scrubbed = scrub_credential_text(text, preserve_identifiers=True)
        assert LIVE_RESET_TOKEN not in scrubbed

    def test_empty_and_none_pass_through(self):
        assert scrub_credential_text(None) is None
        assert scrub_credential_text("") == ""


class TestBodyPreviewPersistence:
    """body_preview is the column that actually carries live OTPs today."""

    @pytest.mark.asyncio
    async def test_otp_body_is_not_stored_in_body_preview(
        self, async_session, test_organization, test_user
    ):
        notification = await create_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            channel="email",
            recipient="user@example.com",
            data={
                "subject": "Your Verification Code",
                "body_preview": LIVE_OTP_BODY,
                "status": "sent",
            },
        )

        async_session.expunge_all()
        stored = await get_notification_by_id(
            session=async_session,
            notification_id=str(notification.id),
            organization_id=str(test_organization.id),
        )

        assert stored is not None
        assert stored.body_preview is not None
        assert LIVE_OTP not in stored.body_preview
        assert "483-920" not in stored.body_preview
        assert REDACTED_MARKER in stored.body_preview
        # Still identifiable as the verification-code message.
        assert "verification code" in stored.body_preview

    @pytest.mark.asyncio
    async def test_reset_link_is_not_stored_in_body_preview(
        self, async_session, test_organization, test_user
    ):
        notification = await create_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            channel="email",
            recipient="user@example.com",
            data={
                "body_preview": f"Reset your password: {LIVE_RESET_URL}",
                "status": "sent",
            },
        )

        async_session.expunge_all()
        stored = await get_notification_by_id(
            session=async_session,
            notification_id=str(notification.id),
            organization_id=str(test_organization.id),
        )

        assert stored is not None
        assert stored.body_preview is not None
        assert LIVE_RESET_TOKEN not in stored.body_preview

    def test_preview_is_scrubbed_before_it_is_truncated(self):
        """Truncating first could sever a token and leave a usable prefix."""
        padding = "x" * (BODY_PREVIEW_MAX_LENGTH - 10)
        preview = prepare_body_preview(f"{padding} {LIVE_RESET_URL}")

        assert preview is not None
        assert LIVE_RESET_TOKEN[:12] not in preview

    def test_preview_is_bounded(self):
        preview = prepare_body_preview("a" * 5000)
        assert preview is not None
        assert len(preview) <= BODY_PREVIEW_MAX_LENGTH

    @pytest.mark.asyncio
    async def test_ordinary_body_preview_is_stored_intact(
        self, async_session, test_organization, test_user
    ):
        body = "Hello Ada, your export is ready. Visit the Files page to download it."
        notification = await create_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            channel="email",
            recipient="user@example.com",
            data={"body_preview": body, "subject": "Export ready", "status": "sent"},
        )

        assert notification.body_preview == body
        assert notification.subject == "Export ready"


class TestSubjectAndErrorMessagePersistence:
    """subject and error_message are served by the same API as body_preview."""

    @pytest.mark.asyncio
    async def test_credential_in_subject_is_scrubbed(
        self, async_session, test_organization, test_user
    ):
        notification = await create_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            channel="email",
            recipient="user@example.com",
            data={"subject": f"Your verification code is {LIVE_OTP}", "status": "sent"},
        )

        async_session.expunge_all()
        stored = await get_notification_by_id(
            session=async_session,
            notification_id=str(notification.id),
            organization_id=str(test_organization.id),
        )

        assert stored is not None
        assert stored.subject is not None
        assert LIVE_OTP not in stored.subject

    @pytest.mark.asyncio
    async def test_credential_echoed_in_error_message_is_scrubbed(
        self, async_session, test_organization, test_user
    ):
        """dispatcher passes `str(e)`, which can echo the outgoing content."""
        error = (
            "SMTPDataError: 550 rejected body "
            f"'Your verification code is: 483-920' for {LIVE_RESET_URL}"
        )
        notification = await create_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            channel="email",
            recipient="user@example.com",
            data={"error_message": error, "status": "failed"},
        )

        async_session.expunge_all()
        stored = await get_notification_by_id(
            session=async_session,
            notification_id=str(notification.id),
            organization_id=str(test_organization.id),
        )

        assert stored is not None
        assert stored.error_message is not None
        assert "483-920" not in stored.error_message
        assert LIVE_RESET_TOKEN not in stored.error_message
        # The provider diagnostic itself must remain readable.
        assert "550 rejected body" in stored.error_message

    @pytest.mark.asyncio
    async def test_ordinary_error_message_is_stored_intact(
        self, async_session, test_organization, test_user
    ):
        notification = await create_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            channel="email",
            recipient="user@example.com",
            data={"error_message": "550 mailbox unavailable", "status": "failed"},
        )
        assert notification.error_message == "550 mailbox unavailable"

    @pytest.mark.asyncio
    async def test_status_update_scrubs_error_message(
        self, async_session, test_organization, test_user
    ):
        from src.crud.notification import (
            update_notification_status,
            update_notification_status_by_provider_id,
        )

        notification = await create_notification(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            channel="email",
            recipient="user@example.com",
            data={"status": "sent", "provider_message_id": "sg-abc-1"},
        )

        updated = await update_notification_status(
            session=async_session,
            notification_id=str(notification.id),
            status="failed",
            error=f"bounced while delivering {LIVE_RESET_URL}",
        )
        assert updated is not None
        assert updated.error_message is not None
        assert LIVE_RESET_TOKEN not in updated.error_message

        webhook_updated = await update_notification_status_by_provider_id(
            session=async_session,
            provider_message_id="sg-abc-1",
            status="failed",
            error=f"callback rejected {LIVE_RESET_URL}",
        )
        assert webhook_updated is not None
        assert webhook_updated.error_message is not None
        assert LIVE_RESET_TOKEN not in webhook_updated.error_message


class TestRedactionIsPersistPathOnly:
    """The provider must keep receiving the real content, or nothing delivers."""

    @pytest.mark.asyncio
    async def test_provider_receives_unredacted_content_row_does_not(
        self, async_session, test_organization, test_user
    ):
        sent: dict[str, object] = {}

        class RecordingProvider:
            provider_name = "recording"

            async def send(
                self,
                recipient,
                message,
                subject=None,
                html_message=None,
                metadata=None,
            ):
                sent["message"] = message
                sent["subject"] = subject
                sent["metadata"] = metadata
                return NotificationResult(
                    success=True, provider_message_id="rec-1", status="sent"
                )

        await notification_dispatcher._ensure_initialized()
        original = notification_dispatcher._providers.get("sms")
        notification_dispatcher._providers["sms"] = RecordingProvider()

        try:
            with patch.object(
                preference_checker,
                "check_can_send",
                new=AsyncMock(return_value=PreferenceCheckResult(allowed=True)),
            ):
                record = await notification_dispatcher.send_notification(
                    session=async_session,
                    user_id=str(test_user.id),
                    organization_id=str(test_organization.id),
                    channel="sms",
                    recipient="+15550000000",
                    content=LIVE_OTP_BODY,
                    subject="Your Verification Code",
                    metadata={"reset_link": LIVE_RESET_URL},
                )
        finally:
            if original is not None:
                notification_dispatcher._providers["sms"] = original
            else:
                notification_dispatcher._providers.pop("sms", None)

        # The provider got the real message - delivery is unaffected.
        assert sent["message"] == LIVE_OTP_BODY
        assert "483-920" in str(sent["message"])
        assert sent["metadata"]["reset_link"] == LIVE_RESET_URL

        # The persisted row did not.
        assert record is not None
        async_session.expunge_all()
        stored = await get_notification_by_id(
            session=async_session,
            notification_id=record["id"],
            organization_id=str(test_organization.id),
        )
        assert stored is not None
        assert stored.body_preview is not None
        assert "483-920" not in stored.body_preview
        assert LIVE_OTP not in stored.body_preview
        assert LIVE_RESET_TOKEN not in str(stored.extra_data)


# ---------------------------------------------------------------------------
# N9 - email must not silently bypass the configured provider
# ---------------------------------------------------------------------------


class TestEmailProviderBypass:
    """Neither path may downgrade to unconfigured/global SMTP."""

    @pytest.mark.asyncio
    async def test_email_provider_without_config_refuses_to_send(self):
        """No org config -> failed result, and the global singleton is untouched."""
        service = AsyncMock()
        provider = EmailProvider(email_svc=service, email_config=None)

        result = await provider.send(
            recipient="user@example.com",
            message="Hello",
            subject="Subject",
        )

        assert result.success is False
        assert result.status == "failed"
        assert result.error_message
        service.send_email.assert_not_called()
        service.send_with_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_email_provider_with_config_uses_send_with_config(self):
        service = AsyncMock()
        service.send_with_config.return_value = True
        config = EmailConfig(provider="smtp", smtp_host="mail.example.com")
        provider = EmailProvider(email_svc=service, email_config=config)

        result = await provider.send(recipient="user@example.com", message="Hello")

        assert result.success is True
        service.send_with_config.assert_awaited_once()
        service.send_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_sendgrid_without_key_returns_none_instead_of_smtp(
        self, async_session, test_organization
    ):
        """Configured provider is sendgrid but the key is missing/undecryptable."""
        broken_config = EmailConfig(
            provider="sendgrid",
            sendgrid_api_key=None,
            smtp_host="mail.example.com",
            sender_email="noreply@example.com",
        )

        with patch(
            "src.services.notifications.dispatcher.get_effective_email_config",
            new=AsyncMock(return_value=broken_config),
        ):
            provider = await notification_dispatcher.get_email_provider(
                async_session, str(test_organization.id)
            )

        assert (
            provider is None
        ), "sendgrid without a usable key must not silently downgrade to SMTP"

    @pytest.mark.asyncio
    async def test_sendgrid_with_key_returns_sendgrid_provider(
        self, async_session, test_organization
    ):
        config = EmailConfig(
            provider="sendgrid",
            sendgrid_api_key="SG.test-key",
            sender_email="noreply@example.com",
        )

        with patch(
            "src.services.notifications.dispatcher.get_effective_email_config",
            new=AsyncMock(return_value=config),
        ):
            provider = await notification_dispatcher.get_email_provider(
                async_session, str(test_organization.id)
            )

        assert provider is not None
        assert provider.provider_name == "sendgrid"

    @pytest.mark.asyncio
    async def test_smtp_config_still_returns_smtp_provider(
        self, async_session, test_organization
    ):
        config = EmailConfig(provider="smtp", smtp_host="mail.example.com")

        with patch(
            "src.services.notifications.dispatcher.get_effective_email_config",
            new=AsyncMock(return_value=config),
        ):
            provider = await notification_dispatcher.get_email_provider(
                async_session, str(test_organization.id)
            )

        assert provider is not None
        assert provider.provider_name == "smtp"


# ---------------------------------------------------------------------------
# N8 - template placeholder syntax
# ---------------------------------------------------------------------------


_BRACE_PAIR = re.compile(r"\{[^{}]*\}")


class TestTemplatePlaceholderSyntax:
    """The documented syntax and the implemented syntax must agree."""

    def test_render_leaves_no_unresolved_braces_for_declared_variables(self):
        """Guard: a template rendered with its declared variables is clean."""
        renderer = TemplateRenderer()
        template = (
            "Hello {first_name} {last_name},\n"
            "Your order {order_id} from {org_name} is ready."
        )
        declared = renderer.extract_variables(template)
        variables = {name: f"value-{name}" for name in declared}

        rendered = renderer.render(template, variables)

        assert (
            _BRACE_PAIR.search(rendered) is None
        ), f"unresolved placeholder left in output: {rendered!r}"

    def test_render_html_leaves_no_unresolved_braces_for_declared_variables(self):
        renderer = TemplateRenderer()
        template = "<p>Hello {first_name}, visit {link}</p>"
        declared = renderer.extract_variables(template)
        variables = {name: f"value-{name}" for name in declared}

        rendered = renderer.render_html(template, variables)

        assert rendered is not None
        assert _BRACE_PAIR.search(rendered) is None

    def test_double_braces_are_not_supported_and_leave_stray_braces(self):
        """Documents the actual behaviour the model docstring now describes."""
        renderer = TemplateRenderer()
        rendered = renderer.render("Hello {{name}}!", {"name": "Ada"})
        assert rendered == "Hello {Ada}!"

    def test_unresolved_placeholder_logs_warning(self):
        renderer = TemplateRenderer()
        with patch(
            "src.services.notifications.template_renderer.logger"
        ) as mock_logger:
            rendered = renderer.render("Hello {name} from {city}!", {"name": "Ada"})

        assert "{city}" in rendered
        mock_logger.warning.assert_called_once()
        message = mock_logger.warning.call_args[0][0]
        assert "city" in message

    def test_fully_resolved_template_logs_no_warning(self):
        renderer = TemplateRenderer()
        with patch(
            "src.services.notifications.template_renderer.logger"
        ) as mock_logger:
            renderer.render("Hello {name}!", {"name": "Ada"})

        mock_logger.warning.assert_not_called()

    def test_double_brace_warning_mentions_the_syntax(self):
        renderer = TemplateRenderer()
        with patch(
            "src.services.notifications.template_renderer.logger"
        ) as mock_logger:
            renderer.render("Hello {{name}}!", {})

        mock_logger.warning.assert_called_once()
        message = mock_logger.warning.call_args[0][0]
        assert "single-brace" in message

    def test_model_docstring_matches_implementation(self):
        """The admin-facing docstring must not advertise {{variable}}."""
        from src.models.notification_template import NotificationTemplate

        doc = NotificationTemplate.__doc__ or ""
        assert "{variable_name}" in doc
        assert "NOT a placeholder" in doc or "SINGLE-brace" in doc


# ---------------------------------------------------------------------------
# N7 - notification category seeding
# ---------------------------------------------------------------------------


_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
_CATEGORY_CODE_LITERAL = re.compile(
    r"""category_code\s*=\s*["']([a-z_][a-z0-9_]*)["']"""
)


def _dispatched_category_codes() -> set[str]:
    """Every literal `category_code="..."` value used anywhere under src/."""
    codes: set[str] = set()
    for path in _SRC_ROOT.rglob("*.py"):
        for match in _CATEGORY_CODE_LITERAL.finditer(path.read_text(encoding="utf-8")):
            codes.add(match.group(1))
    return codes


class TestNotificationCategorySeeding:
    """Every category the app dispatches under must actually exist."""

    def test_every_dispatched_category_code_is_seeded(self):
        """Guard: no `category_code=` literal may resolve to a missing category."""
        seeded = set(get_default_notification_category_codes())
        dispatched = _dispatched_category_codes()

        assert dispatched, "expected to find category_code= literals under src/"
        missing = dispatched - seeded
        assert not missing, (
            f"category_code literal(s) {sorted(missing)} are dispatched from src/ "
            "but are not seeded in DEFAULT_NOTIFICATION_CATEGORIES. "
            "preference_checker._get_category() returns None for these, which "
            "disables both the mandatory bypass and the per-category guard."
        )

    @pytest.mark.asyncio
    async def test_seeding_creates_system_categories(self, async_session):
        created = await seed_default_notification_categories(async_session)

        assert len(created) == len(DEFAULT_NOTIFICATION_CATEGORIES)
        by_code = {category.code: category for category in created}
        assert set(by_code) == set(get_default_notification_category_codes())
        for category in created:
            assert category.organization_id is None, "must be system-scoped"

    @pytest.mark.asyncio
    async def test_transactional_categories_are_mandatory(self, async_session):
        created = await seed_default_notification_categories(async_session)
        by_code = {category.code: category for category in created}

        assert by_code["account"].user_configurable is False
        assert by_code["phone_verification"].user_configurable is False
        assert by_code["marketing"].user_configurable is True
        assert by_code["onboarding"].user_configurable is True

    @pytest.mark.asyncio
    async def test_seeding_is_idempotent(self, async_session):
        first = await seed_default_notification_categories(async_session)
        second = await seed_default_notification_categories(async_session)

        assert len(first) == len(DEFAULT_NOTIFICATION_CATEGORIES)
        assert second == []

    @pytest.mark.asyncio
    async def test_seeded_categories_resolve_for_an_organization(
        self, async_session, test_organization
    ):
        """The crud system-category fallback finds them for any org."""
        from src.crud.notification_category import get_category_by_code

        await seed_default_notification_categories(async_session)

        for code in get_default_notification_category_codes():
            category = await get_category_by_code(
                async_session, str(test_organization.id), code
            )
            assert category is not None, f"category '{code}' not resolvable"
