"""
Tests for the PUBLIC_URL_FRONTEND / PUBLIC_URL_BACKEND split.

`public_url` used to mean the frontend origin in some call sites (emailed links
to SPA routes) and the backend origin in others (Twilio webhook signature
reconstruction). Splitting it must (a) send each kind of URL to the right
origin, and (b) leave an existing single-origin deployment behaving exactly as
it did, with a warning rather than a silent re-point.
"""

import json
import logging
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import Settings
from src.services.notifications.unsubscribe import UnsubscribeService


DEPRECATION_MARKER = "PUBLIC_URL_FRONTEND"


# ============================================================================
# Settings defaults
# ============================================================================


class TestPublicUrlDefaults:
    def test_frontend_default_is_the_vite_dev_server(self):
        """app/frontend/vite.config.ts falls back to port 5173."""
        assert Settings().PUBLIC_URL_FRONTEND == "http://localhost:5173"

    def test_backend_default_matches_the_server_port(self):
        settings = Settings()
        assert settings.PUBLIC_URL_BACKEND == "http://localhost:8000"
        assert str(settings.SERVER_PORT) in settings.PUBLIC_URL_BACKEND

    def test_the_two_defaults_differ(self):
        """The whole point: in local dev the SPA is not on the API port."""
        settings = Settings()
        assert settings.PUBLIC_URL_FRONTEND != settings.PUBLIC_URL_BACKEND


# ============================================================================
# Deprecated `public_url` alias
# ============================================================================


class TestDeprecatedPublicUrlAlias:
    def test_legacy_value_populates_both_origins(self, caplog):
        """A pre-split config keeps its exact previous behaviour."""
        with caplog.at_level(logging.WARNING, logger="src.core.config"):
            settings = Settings(PUBLIC_URL="https://one.example.com")

        assert settings.PUBLIC_URL_FRONTEND == "https://one.example.com"
        assert settings.PUBLIC_URL_BACKEND == "https://one.example.com"

    def test_legacy_value_logs_a_deprecation_warning_naming_both_new_keys(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.core.config"):
            Settings(PUBLIC_URL="https://one.example.com")

        records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert records, "no warning emitted for the deprecated public_url key"
        message = records[-1].getMessage()
        assert "DEPRECATED" in message
        assert "PUBLIC_URL_FRONTEND" in message
        assert "PUBLIC_URL_BACKEND" in message

    def test_explicit_keys_win_over_the_legacy_one(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.core.config"):
            settings = Settings(
                PUBLIC_URL="https://legacy.example.com",
                PUBLIC_URL_FRONTEND="https://app.example.com",
                PUBLIC_URL_BACKEND="https://api.example.com",
            )

        assert settings.PUBLIC_URL_FRONTEND == "https://app.example.com"
        assert settings.PUBLIC_URL_BACKEND == "https://api.example.com"
        assert not [r for r in caplog.records if r.levelno == logging.WARNING]

    def test_legacy_fills_only_the_gap_when_one_new_key_is_set(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.core.config"):
            settings = Settings(
                PUBLIC_URL="https://legacy.example.com",
                PUBLIC_URL_FRONTEND="https://app.example.com",
            )

        assert settings.PUBLIC_URL_FRONTEND == "https://app.example.com"
        assert settings.PUBLIC_URL_BACKEND == "https://legacy.example.com"
        assert [r for r in caplog.records if r.levelno == logging.WARNING]

    def test_no_warning_when_the_legacy_key_is_absent(self, caplog):
        with caplog.at_level(logging.WARNING, logger="src.core.config"):
            Settings(
                PUBLIC_URL_FRONTEND="https://app.example.com",
                PUBLIC_URL_BACKEND="https://api.example.com",
            )

        assert not [r for r in caplog.records if r.levelno == logging.WARNING]

    def test_legacy_field_resolves_to_the_backend_origin(self):
        """Any straggling reader of PUBLIC_URL builds an /api/v1 path."""
        settings = Settings(
            PUBLIC_URL_FRONTEND="https://app.example.com",
            PUBLIC_URL_BACKEND="https://api.example.com",
        )
        assert settings.PUBLIC_URL == "https://api.example.com"


# ============================================================================
# config.json loading + .ports.env fixup
# ============================================================================


def _write_config(tmp_path, payload, backend_port=None):
    """Lay out config.json where from_json_file expects it.

    The loader looks for .ports.env two directories above config.json.
    """
    root = tmp_path / "repo"
    config_dir = root / "app" / "backend"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.json"
    config_path.write_text(json.dumps(payload))
    if backend_port is not None:
        (root / ".ports.env").write_text(f"BACKEND_PORT={backend_port}\n")
    return str(config_path)


class TestConfigJsonLoading:
    def test_split_keys_are_read_from_config_json(self, tmp_path):
        path = _write_config(
            tmp_path,
            {
                "public_url_frontend": "https://app.example.com",
                "public_url_backend": "https://api.example.com",
            },
        )
        settings = Settings.from_json_file(path)

        assert settings.PUBLIC_URL_FRONTEND == "https://app.example.com"
        assert settings.PUBLIC_URL_BACKEND == "https://api.example.com"

    def test_legacy_key_in_config_json_populates_both(self, tmp_path, caplog):
        path = _write_config(tmp_path, {"public_url": "https://one.example.com"})
        with caplog.at_level(logging.WARNING, logger="src.core.config"):
            settings = Settings.from_json_file(path)

        assert settings.PUBLIC_URL_FRONTEND == "https://one.example.com"
        assert settings.PUBLIC_URL_BACKEND == "https://one.example.com"
        assert [r for r in caplog.records if r.levelno == logging.WARNING]


class TestPortsEnvFixup:
    def test_backend_port_rewrites_the_backend_origin(self, tmp_path):
        path = _write_config(
            tmp_path,
            {
                "public_url_frontend": "http://localhost:5173",
                "public_url_backend": "http://localhost:8000",
            },
            backend_port=9123,
        )
        settings = Settings.from_json_file(path)

        assert settings.SERVER_PORT == 9123
        assert settings.PUBLIC_URL_BACKEND == "http://localhost:9123"

    def test_backend_port_does_not_touch_the_frontend_origin(self, tmp_path):
        """A frontend legitimately served on :8000 must not be rewritten."""
        path = _write_config(
            tmp_path,
            {
                "public_url_frontend": "http://localhost:8000",
                "public_url_backend": "http://localhost:8000",
            },
            backend_port=9123,
        )
        settings = Settings.from_json_file(path)

        assert settings.PUBLIC_URL_BACKEND == "http://localhost:9123"
        assert settings.PUBLIC_URL_FRONTEND == "http://localhost:8000"

    def test_fixup_still_applies_through_the_deprecated_key(self, tmp_path, caplog):
        """A pre-split config.json must keep working in a port-shifted worktree."""
        path = _write_config(
            tmp_path, {"public_url": "http://localhost:8000"}, backend_port=9123
        )
        with caplog.at_level(logging.WARNING, logger="src.core.config"):
            settings = Settings.from_json_file(path)

        assert settings.PUBLIC_URL_BACKEND == "http://localhost:9123"
        assert settings.PUBLIC_URL_FRONTEND == "http://localhost:9123"


# ============================================================================
# Unsubscribe: the human page and the machine endpoint use different origins
# ============================================================================


class TestUnsubscribeOrigins:
    @pytest.fixture
    def split_settings(self):
        with patch("src.services.notifications.unsubscribe.settings") as mock_settings:
            mock_settings.JWT_SECRET = "test-secret"
            mock_settings.PUBLIC_URL_FRONTEND = "https://app.example.com"
            mock_settings.PUBLIC_URL_BACKEND = "https://api.example.com"
            yield mock_settings

    def test_footer_page_link_uses_the_frontend_origin(self, split_settings):
        service = UnsubscribeService(secret_key="test-secret")
        url = service.get_unsubscribe_url(
            user_id="11111111-1111-1111-1111-111111111111",
            organization_id="22222222-2222-2222-2222-222222222222",
        )
        assert url.startswith("https://app.example.com/unsubscribe?token=")

    def test_one_click_endpoint_uses_the_backend_origin(self, split_settings):
        service = UnsubscribeService(secret_key="test-secret")
        url = service.get_one_click_unsubscribe_url(
            user_id="11111111-1111-1111-1111-111111111111",
            organization_id="22222222-2222-2222-2222-222222222222",
        )
        assert url.startswith(
            "https://api.example.com/api/v1/notifications/unsubscribe/one-click?token="
        )

    def test_list_unsubscribe_header_uses_the_backend_origin(self, split_settings):
        service = UnsubscribeService(secret_key="test-secret")
        headers = service.get_list_unsubscribe_headers(
            user_id="11111111-1111-1111-1111-111111111111",
            organization_id="22222222-2222-2222-2222-222222222222",
        )
        assert headers["List-Unsubscribe"].startswith(
            "<https://api.example.com/api/v1/"
        )

    def test_single_base_url_argument_still_drives_both(self, split_settings):
        """One-host deployments (and existing tests) pass a single origin."""
        service = UnsubscribeService(
            secret_key="test-secret", base_url="https://one.example.com"
        )
        assert service.frontend_base_url == "https://one.example.com"
        assert service.backend_base_url == "https://one.example.com"

    def test_per_origin_arguments_override_the_single_one(self, split_settings):
        service = UnsubscribeService(
            secret_key="test-secret",
            base_url="https://one.example.com",
            backend_base_url="https://api.example.com",
        )
        assert service.frontend_base_url == "https://one.example.com"
        assert service.backend_base_url == "https://api.example.com"


# ============================================================================
# Twilio status_callback -> BACKEND origin
# ============================================================================


class TestTwilioStatusCallbackOrigin:
    """The URL handed to Twilio is the one Twilio HMACs on the way back.

    webhooks_notifications.py rebuilds it from the same setting to verify the
    signature, so if these two ever name different origins every SMS status
    callback is rejected.
    """

    @pytest.mark.asyncio
    async def test_status_callback_is_built_from_the_backend_origin(self):
        from src.core.config import settings as live_settings
        from src.services.notifications import dispatcher as dispatcher_module

        sent = {}

        class _FakeResult:
            success = True
            status = "sent"
            error_message = None
            provider_message_id = "SM-fake"

        class _FakeProvider:
            provider_name = "fake-twilio"

            async def send(self, **kwargs):
                sent.update(kwargs)
                return _FakeResult()

        class _Allowed:
            allowed = True
            skip_reason = None

        dispatcher = dispatcher_module.NotificationDispatcher()

        with patch.object(
            live_settings, "PUBLIC_URL_BACKEND", "https://api.example.com"
        ), patch.object(
            live_settings, "PUBLIC_URL_FRONTEND", "https://app.example.com"
        ), patch.object(
            dispatcher, "_ensure_initialized", new=AsyncMock(return_value=None)
        ), patch.object(
            dispatcher, "_get_provider", return_value=_FakeProvider()
        ), patch.object(
            dispatcher, "_record_notification", new=AsyncMock(return_value={})
        ), patch.object(
            dispatcher_module.preference_checker,
            "check_can_send",
            new=AsyncMock(return_value=_Allowed()),
        ):
            await dispatcher.send_notification(
                session=None,
                user_id="11111111-1111-1111-1111-111111111111",
                organization_id="22222222-2222-2222-2222-222222222222",
                channel="sms",
                recipient="+15550000001",
                content="hello",
            )

        assert sent["metadata"]["status_callback"] == (
            "https://api.example.com/api/v1/webhooks/notifications/twilio/sms-status"
        )
