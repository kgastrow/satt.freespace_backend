"""
Tests for unsubscribe link generation and the RFC 8058 one-click endpoint.

Covers the N3 defect: the generated footer link pointed at
"/api/notifications/unsubscribe" (the API is mounted under /api/v1, so it 404'd)
and the List-Unsubscribe-Post header advertised a one-click endpoint that did
not exist at all.
"""

from httpx import AsyncClient
import pytest

from src.crud.user_notification_preference import get_or_create_user_preference
from src.services.notifications.unsubscribe import UnsubscribeService


BASE = "https://app.example.com"


@pytest.fixture
def svc():
    """Unsubscribe service pinned to a known public origin."""
    return UnsubscribeService(secret_key="test-unsubscribe-secret", base_url=BASE)


# ============================================================================
# URL generation
# ============================================================================


class TestUnsubscribeUrlGeneration:
    """The two generated URLs must resolve to something that actually exists."""

    def test_footer_url_points_at_the_frontend_page_not_the_api(self, svc):
        """The human-facing link is the SPA route, not a JSON API path."""
        url = svc.get_unsubscribe_url(
            user_id="11111111-1111-1111-1111-111111111111",
            organization_id="22222222-2222-2222-2222-222222222222",
        )

        # The frontend registers `path: 'unsubscribe'` (app/frontend/src/router.tsx)
        assert url.startswith(f"{BASE}/unsubscribe?token=")
        # It must NOT be an API path: the old value was /api/notifications/...
        assert "/api/notifications/" not in url
        assert "/api/v1/" not in url

    def test_one_click_url_carries_the_api_v1_prefix(self, svc):
        """The machine-facing URL must hit the router's real mount point."""
        url = svc.get_one_click_unsubscribe_url(
            user_id="11111111-1111-1111-1111-111111111111",
            organization_id="22222222-2222-2222-2222-222222222222",
        )

        assert url.startswith(
            f"{BASE}/api/v1/notifications/unsubscribe/one-click?token="
        )
        assert "/api/v1" in url

    def test_one_click_url_puts_the_token_in_the_query_string(self, svc):
        """RFC 8058: the provider owns the body, so the token rides the URL."""
        url = svc.get_one_click_unsubscribe_url(
            user_id="11111111-1111-1111-1111-111111111111",
            organization_id="22222222-2222-2222-2222-222222222222",
        )
        token = url.split("token=", 1)[1]

        payload = svc.validate_token(token)
        assert payload is not None
        assert payload["user_id"] == "11111111-1111-1111-1111-111111111111"

    def test_list_unsubscribe_header_advertises_the_one_click_endpoint(self, svc):
        """A -Post header must accompany a URI that accepts a POST."""
        headers = svc.get_list_unsubscribe_headers(
            user_id="11111111-1111-1111-1111-111111111111",
            organization_id="22222222-2222-2222-2222-222222222222",
        )

        assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        uri = headers["List-Unsubscribe"]
        assert uri.startswith("<") and uri.endswith(">")
        assert "/api/v1/notifications/unsubscribe/one-click?token=" in uri


# ============================================================================
# POST /unsubscribe/one-click
# ============================================================================


class TestOneClickUnsubscribeEndpoint:
    """The endpoint the mail providers actually call."""

    @pytest.mark.asyncio
    async def test_route_exists_and_accepts_a_query_string_token(
        self, client: AsyncClient, test_user, test_organization
    ):
        """The advertised path resolves (it previously 404'd - it did not exist)."""
        from src.services.notifications import unsubscribe_service

        token = unsubscribe_service.generate_token(
            user_id=str(test_user.id),
            organization_id=str(test_organization.id),
        )

        response = await client.post(
            f"/api/v1/notifications/unsubscribe/one-click?token={token}"
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_valid_token_actually_disables_the_channel(
        self, client: AsyncClient, async_session, test_user, test_organization
    ):
        """A 200 has to mean the preference changed, not just that we answered."""
        from src.services.notifications import unsubscribe_service

        pref = await get_or_create_user_preference(
            session=async_session,
            user_id=str(test_user.id),
            organization_id=str(test_organization.id),
        )
        assert pref.email_enabled is True

        token = unsubscribe_service.generate_token(
            user_id=str(test_user.id),
            organization_id=str(test_organization.id),
        )

        response = await client.post(
            f"/api/v1/notifications/unsubscribe/one-click?token={token}"
        )
        assert response.status_code == 200

        await async_session.refresh(pref)
        assert pref.email_enabled is False

    @pytest.mark.asyncio
    async def test_ignores_the_rfc_8058_form_body(
        self, client: AsyncClient, async_session, test_user, test_organization
    ):
        """Providers POST 'List-Unsubscribe=One-Click' as the body; we must not choke."""
        from src.services.notifications import unsubscribe_service

        pref = await get_or_create_user_preference(
            session=async_session,
            user_id=str(test_user.id),
            organization_id=str(test_organization.id),
        )

        token = unsubscribe_service.generate_token(
            user_id=str(test_user.id),
            organization_id=str(test_organization.id),
        )

        response = await client.post(
            f"/api/v1/notifications/unsubscribe/one-click?token={token}",
            data={"List-Unsubscribe": "One-Click"},
        )

        assert response.status_code == 200
        await async_session.refresh(pref)
        assert pref.email_enabled is False

    @pytest.mark.asyncio
    async def test_invalid_token_still_returns_200(self, client: AsyncClient):
        """Never leak token validity to a mail provider - a 4xx costs reputation."""
        response = await client.post(
            "/api/v1/notifications/unsubscribe/one-click?token=not-a-real-token"
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_expired_token_still_returns_200(
        self, client: AsyncClient, test_user, test_organization
    ):
        """An old link from an old email must not produce an error for the provider."""
        from src.services.notifications import unsubscribe_service

        token = unsubscribe_service.generate_token(
            user_id=str(test_user.id),
            organization_id=str(test_organization.id),
            expiry_seconds=-3600,  # already expired
        )

        response = await client.post(
            f"/api/v1/notifications/unsubscribe/one-click?token={token}"
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_missing_token_is_a_validation_error(self, client: AsyncClient):
        """No token at all is a malformed request, not a silent success."""
        response = await client.post("/api/v1/notifications/unsubscribe/one-click")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_is_unauthenticated(
        self, client: AsyncClient, test_user, test_organization
    ):
        """Mail providers have no credentials; the signed token is the auth."""
        from src.services.notifications import unsubscribe_service

        token = unsubscribe_service.generate_token(
            user_id=str(test_user.id),
            organization_id=str(test_organization.id),
        )

        assert "Authorization" not in client.headers
        response = await client.post(
            f"/api/v1/notifications/unsubscribe/one-click?token={token}"
        )
        assert response.status_code == 200


class TestUnsubscribeRouteOrdering:
    """/unsubscribe/* must not be swallowed by the generic /{notification_id}."""

    def test_unsubscribe_routes_declared_before_notification_id(self):
        from src.api.notification import router

        paths = [getattr(r, "path", "") for r in router.routes]

        one_click = paths.index("/notifications/unsubscribe/one-click")
        generic = paths.index("/notifications/{notification_id}")

        assert one_click < generic
        assert paths.index("/notifications/unsubscribe") < generic

    @pytest.mark.asyncio
    async def test_page_endpoint_and_one_click_share_one_implementation(
        self, async_session, test_user, test_organization
    ):
        """Both routes route through _apply_unsubscribe so they cannot drift."""
        from src.api.notification import _apply_unsubscribe

        pref = await get_or_create_user_preference(
            session=async_session,
            user_id=str(test_user.id),
            organization_id=str(test_organization.id),
        )
        assert pref.sms_enabled is True

        channel = await _apply_unsubscribe(
            async_session,
            {
                "user_id": str(test_user.id),
                "organization_id": str(test_organization.id),
                "channel": "sms",
                "category_code": None,
            },
        )

        assert channel == "sms"
        await async_session.refresh(pref)
        assert pref.sms_enabled is False
