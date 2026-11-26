"""
End-to-end checks that each kind of URL is built from the right public origin.

`public_url` used to serve as both the SPA origin (for links mailed to people)
and the API origin (for URLs a third-party system calls or signs). These tests
pin the two apart by giving them deliberately different hosts, so a regression
that swaps them cannot pass.
"""

from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

from httpx import AsyncClient
import pytest
import pytest_asyncio

from src.models.organization_sso_settings import OrganizationSSOSettings
from src.services.cache import cache_service


FRONTEND = "https://app.example.com"
BACKEND = "https://api.example.com"


@pytest.fixture
def split_origins():
    """Pin the two public origins to distinguishable hosts."""
    with patch("src.core.config.settings.PUBLIC_URL_FRONTEND", FRONTEND), patch(
        "src.core.config.settings.PUBLIC_URL_BACKEND", BACKEND
    ):
        yield


# ============================================================================
# Emailed links -> FRONTEND origin
# ============================================================================


@pytest.mark.asyncio
async def test_password_reset_link_uses_the_frontend_origin(
    client: AsyncClient, test_user, test_organization, split_origins
):
    """/reset-password is an SPA route, not an API route."""
    with patch(
        "src.services.tasks.TaskQueue.enqueue_password_reset_email",
        new_callable=AsyncMock,
    ) as mock_enqueue:
        mock_enqueue.return_value = "mock-job-id"
        response = await client.post(
            "/api/v1/auth/password-reset/request",
            json={
                "email": test_user.email,
                "organization_slug": test_organization.slug,
            },
        )

    assert response.status_code == 200
    reset_url = mock_enqueue.call_args.kwargs["reset_url"]
    assert reset_url.startswith(f"{FRONTEND}/reset-password?token=")
    assert BACKEND not in reset_url


@pytest.mark.asyncio
async def test_admin_triggered_reset_link_uses_the_frontend_origin(
    client: AsyncClient, test_user, test_admin_token, split_origins
):
    """The admin-initiated reset in api/users.py builds the same SPA route."""
    with patch(
        "src.services.tasks.TaskQueue.enqueue_password_reset_email",
        new_callable=AsyncMock,
    ) as mock_enqueue:
        mock_enqueue.return_value = "mock-job-id"
        response = await client.post(
            f"/api/v1/users/{test_user.id}/password-reset",
            headers={"Authorization": test_admin_token},
        )

    assert response.status_code == 200, response.text
    reset_url = mock_enqueue.call_args.kwargs["reset_url"]
    assert reset_url.startswith(f"{FRONTEND}/reset-password?token=")
    assert BACKEND not in reset_url


@pytest.mark.asyncio
async def test_invitation_link_uses_the_frontend_origin(
    client: AsyncClient, test_organization, test_admin_token, split_origins
):
    """/register is an SPA route, not an API route."""
    with patch(
        "src.services.tasks.task_queue.enqueue_invitation_email",
        new_callable=AsyncMock,
    ) as mock_email:
        response = await client.post(
            "/api/v1/invitations",
            json={"email": "split-origin-invite@example.com"},
            headers={"Authorization": test_admin_token},
        )

    assert response.status_code == 201, response.text
    registration_url = mock_email.call_args.kwargs["registration_url"]
    assert registration_url.startswith(f"{FRONTEND}/register?invite_token=")
    assert BACKEND not in registration_url


# ============================================================================
# Twilio webhook signature -> BACKEND origin
# ============================================================================


class TestTwilioSignatureOrigin:
    """Twilio HMACs the exact URL string, so the origin must be the API's."""

    PATH = "/api/v1/webhooks/notifications/twilio/sms-status"
    PARAMS = {
        "MessageSid": "SM00000000000000000000000000000001",
        "MessageStatus": "delivered",
        "To": "+15550000001",
        "From": "+15550000002",
    }

    @staticmethod
    def _sign(url, params, token):
        from twilio.request_validator import RequestValidator

        return RequestValidator(token).compute_signature(url, params)

    @pytest.mark.asyncio
    async def test_signature_over_the_backend_origin_is_accepted(
        self, client: AsyncClient, split_origins
    ):
        token = "twilio-test-auth-token"
        signature = self._sign(f"{BACKEND}{self.PATH}", self.PARAMS, token)

        with patch("src.core.config.settings.TWILIO_AUTH_TOKEN", token):
            response = await client.post(
                self.PATH,
                data=self.PARAMS,
                headers={"X-Twilio-Signature": signature},
            )

        assert response.status_code != 403, response.text

    @pytest.mark.asyncio
    async def test_signature_over_the_frontend_origin_is_rejected(
        self, client: AsyncClient, split_origins
    ):
        """Proof the receiver is not silently falling back to the SPA origin."""
        token = "twilio-test-auth-token"
        signature = self._sign(f"{FRONTEND}{self.PATH}", self.PARAMS, token)

        with patch("src.core.config.settings.TWILIO_AUTH_TOKEN", token):
            response = await client.post(
                self.PATH,
                data=self.PARAMS,
                headers={"X-Twilio-Signature": signature},
            )

        assert response.status_code == 403


# ============================================================================
# SSO redirect_uri -> FRONTEND origin, /oauth/callback
# ============================================================================


@pytest_asyncio.fixture
async def sso_nonce_store():
    """Give ``cache_service`` a fake Redis so the state nonce can be stored."""
    import fakeredis.aioredis

    previous = cache_service._redis
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache_service._redis = fake
    try:
        yield fake
    finally:
        cache_service._redis = previous
        await fake.aclose()


@pytest.mark.asyncio
async def test_sso_redirect_uri_falls_back_to_the_frontend_oauth_callback(
    client: AsyncClient,
    async_session,
    test_organization,
    split_origins,
    sso_nonce_store,
):
    """The provider redirects a BROWSER, which lands on the SPA page.

    app/frontend/src/router.tsx registers ``path: 'oauth/callback'``; that page
    then calls GET /api/v1/sso/{provider}/callback with the code. The previous
    fallback, ``{PUBLIC_URL}/sso/{provider}/callback``, matched no route on
    either origin.
    """
    async_session.add(
        OrganizationSSOSettings(
            organization_id=test_organization.id,
            google_enabled=True,
            google_client_id="test-client-id",
            google_client_secret="test-client-secret",
        )
    )
    await async_session.commit()

    with patch("src.core.config.settings.GOOGLE_CLIENT_ID", "test-client-id"), patch(
        "src.core.config.settings.GOOGLE_CLIENT_SECRET", "test-client-secret"
    ), patch("src.core.config.settings.GOOGLE_REDIRECT_URI", ""):
        response = await client.get(
            f"/api/v1/sso/google/authorize?org_slug={test_organization.slug}"
        )

    assert response.status_code == 200, response.text
    query = parse_qs(urlparse(response.json()["authorization_url"]).query)
    assert query["redirect_uri"] == [f"{FRONTEND}/oauth/callback"]
