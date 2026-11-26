"""API tests for the Web Push subscription endpoints.

The rules these defend, in order of how badly each fails when broken:

1. Unconfigured push answers 503 ``push.not_configured`` rather than handing a
   client an empty key it would then subscribe against.
2. A push endpoint is the DEVICE identity. Re-registering one reassigns it to
   whoever is signed in now; keyed per (user, endpoint) instead, a shared
   device keeps delivering the previous user's notification bodies to the
   current one.
3. One user cannot unsubscribe another user's device.
4. An endpoint URL supplied by a client is a URL the SERVER will POST to, so it
   is allowlisted rather than trusted.
"""

from datetime import datetime, timezone

from httpx import AsyncClient
import pytest
from sqlalchemy import select

from src.models.web_push_subscription import WebPushSubscription
from src.services.notifications.web_push_config import (
    VAPID_PRIVATE_KEY,
    VAPID_PUBLIC_KEY,
)


FCM = "https://fcm.googleapis.com/fcm/send/"
ENDPOINT_A = f"{FCM}device-a-token"
ENDPOINT_B = f"{FCM}device-b-token"

BASE = "/api/v1/notifications/push"


def _payload(endpoint: str) -> dict:
    return {
        "endpoint": endpoint,
        "keys": {"p256dh": "p256dh-value", "auth": "auth-value"},
        "user_agent": "pytest",
    }


@pytest.fixture
async def configured_vapid(async_session, test_admin_user):
    """Persist a VAPID keypair the way the provider-management endpoint does."""
    from src.crud.system_config import update_system_config

    await update_system_config(
        async_session, VAPID_PUBLIC_KEY, "BTestPublicKey", updated_by_user_id=None
    )
    await update_system_config(
        async_session, VAPID_PRIVATE_KEY, "test-private-key", updated_by_user_id=None
    )
    return "BTestPublicKey"


# ============================================================================
# VAPID key - the "is push configured?" probe
# ============================================================================


async def test_vapid_key_is_503_when_unconfigured(authenticated_client: AsyncClient):
    """Unconfigured push is a documented, quiet state, not an error to surface."""
    response = await authenticated_client.get(f"{BASE}/vapid-key")

    assert response.status_code == 503
    assert response.json()["detail_code"] == "push.not_configured"


async def test_vapid_key_returns_public_key_when_configured(
    authenticated_client: AsyncClient, configured_vapid
):
    response = await authenticated_client.get(f"{BASE}/vapid-key")

    assert response.status_code == 200
    assert response.json()["public_key"] == configured_vapid


async def test_vapid_key_requires_authentication(client: AsyncClient):
    response = await client.get(f"{BASE}/vapid-key")

    assert response.status_code in (401, 403)


# ============================================================================
# Registration
# ============================================================================


async def test_register_subscription(
    authenticated_client: AsyncClient, async_session, test_user
):
    response = await authenticated_client.post(
        f"{BASE}/subscriptions", json=_payload(ENDPOINT_A)
    )

    assert response.status_code == 201
    assert response.json()["endpoint"] == ENDPOINT_A

    row = (
        await async_session.execute(
            select(WebPushSubscription).where(
                WebPushSubscription.endpoint == ENDPOINT_A
            )
        )
    ).scalar_one()
    assert row.user_id == test_user.id
    assert row.p256dh_key == "p256dh-value"
    assert row.deleted_time is None


async def test_register_is_idempotent_on_the_endpoint(
    authenticated_client: AsyncClient, async_session
):
    """A browser re-reporting its subscription must not accumulate rows."""
    await authenticated_client.post(f"{BASE}/subscriptions", json=_payload(ENDPOINT_A))

    updated = _payload(ENDPOINT_A)
    updated["keys"]["p256dh"] = "rotated-p256dh"
    response = await authenticated_client.post(f"{BASE}/subscriptions", json=updated)

    assert response.status_code == 201
    rows = (
        (
            await async_session.execute(
                select(WebPushSubscription).where(
                    WebPushSubscription.endpoint == ENDPOINT_A,
                    WebPushSubscription.deleted_time.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].p256dh_key == "rotated-p256dh"


async def test_registering_a_known_endpoint_reassigns_the_device(
    client: AsyncClient,
    async_session,
    test_jwt_token,
    test_admin_token,
    test_user,
    test_admin_user,
):
    """A shared device belongs to whoever is signed in now.

    Keyed per (user, endpoint) this produced two live rows for one browser, and
    the person who logged out kept receiving notification titles and bodies on
    the screen of the person who logged in.
    """
    client.headers["Authorization"] = test_jwt_token
    await client.post(f"{BASE}/subscriptions", json=_payload(ENDPOINT_A))

    client.headers["Authorization"] = test_admin_token
    response = await client.post(f"{BASE}/subscriptions", json=_payload(ENDPOINT_A))

    assert response.status_code == 201
    rows = (
        (
            await async_session.execute(
                select(WebPushSubscription).where(
                    WebPushSubscription.endpoint == ENDPOINT_A,
                    WebPushSubscription.deleted_time.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].user_id == test_admin_user.id
    assert rows[0].user_id != test_user.id


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/x",  # not https
        "https://127.0.0.1:6379/",  # internal address
        "https://169.254.169.254/latest/meta-data/",  # cloud metadata
        "https://evil.example.com/push",  # not a push service
        "https://fcm.googleapis.com:8080/fcm/send/x",  # surprising port
        "https://user:pw@fcm.googleapis.com/fcm/send/x",  # embedded credentials
    ],
)
async def test_register_refuses_an_endpoint_that_is_not_a_push_service(
    authenticated_client: AsyncClient, endpoint
):
    """The endpoint is a URL the server POSTs to, so it is allowlisted."""
    response = await authenticated_client.post(
        f"{BASE}/subscriptions", json=_payload(endpoint)
    )

    assert response.status_code == 400
    assert response.json()["detail_code"] == "push.invalid_endpoint"


async def test_register_requires_authentication(client: AsyncClient):
    response = await client.post(f"{BASE}/subscriptions", json=_payload(ENDPOINT_A))

    assert response.status_code in (401, 403)


# ============================================================================
# Unsubscribe
# ============================================================================


async def test_unsubscribe_soft_deletes(
    authenticated_client: AsyncClient, async_session
):
    await authenticated_client.post(f"{BASE}/subscriptions", json=_payload(ENDPOINT_A))

    response = await authenticated_client.request(
        "DELETE", f"{BASE}/subscriptions", json={"endpoint": ENDPOINT_A}
    )

    assert response.status_code == 204
    row = (
        await async_session.execute(
            select(WebPushSubscription).where(
                WebPushSubscription.endpoint == ENDPOINT_A
            )
        )
    ).scalar_one()
    assert row.deleted_time is not None


async def test_unsubscribe_cannot_reach_another_users_device(
    client: AsyncClient, async_session, test_jwt_token, test_admin_token, test_user
):
    """Knowing an endpoint must not be enough to silence someone else's device."""
    client.headers["Authorization"] = test_jwt_token
    await client.post(f"{BASE}/subscriptions", json=_payload(ENDPOINT_B))

    client.headers["Authorization"] = test_admin_token
    response = await client.request(
        "DELETE", f"{BASE}/subscriptions", json={"endpoint": ENDPOINT_B}
    )

    assert response.status_code == 404
    assert response.json()["detail_code"] == "push.subscription_not_found"

    row = (
        await async_session.execute(
            select(WebPushSubscription).where(
                WebPushSubscription.endpoint == ENDPOINT_B
            )
        )
    ).scalar_one()
    assert row.deleted_time is None
    assert row.user_id == test_user.id


async def test_unsubscribe_unknown_endpoint_is_404(authenticated_client: AsyncClient):
    response = await authenticated_client.request(
        "DELETE", f"{BASE}/subscriptions", json={"endpoint": ENDPOINT_A}
    )

    assert response.status_code == 404


@pytest.mark.skip(
    reason=(
        "The uniqueness rule is `unique(endpoint) WHERE deleted_time IS NULL`, "
        "expressed with postgresql_where. The test suite runs on SQLite, which "
        "ignores that clause and builds a full unique index, so re-registering "
        "a soft-deleted endpoint raises here and would not in production. "
        "Verify on Postgres."
    )
)
async def test_a_soft_deleted_endpoint_can_be_registered_again(
    authenticated_client: AsyncClient, async_session
):
    """The unique index is partial on `deleted_time IS NULL` for this reason."""
    await authenticated_client.post(f"{BASE}/subscriptions", json=_payload(ENDPOINT_A))
    await authenticated_client.request(
        "DELETE", f"{BASE}/subscriptions", json={"endpoint": ENDPOINT_A}
    )

    response = await authenticated_client.post(
        f"{BASE}/subscriptions", json=_payload(ENDPOINT_A)
    )

    assert response.status_code == 201
    live = (
        (
            await async_session.execute(
                select(WebPushSubscription).where(
                    WebPushSubscription.endpoint == ENDPOINT_A,
                    WebPushSubscription.deleted_time.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(live) == 1


# ============================================================================
# Device cap
# ============================================================================


async def test_active_device_cap_is_enforced(
    authenticated_client: AsyncClient, async_session, test_user
):
    """Each live row is one outbound POST per send; an unbounded count turns
    one notification into unbounded fan-out."""
    from src.services.notifications.push_endpoint import (
        MAX_ACTIVE_SUBSCRIPTIONS_PER_USER,
    )

    now = datetime.now(timezone.utc)
    for i in range(MAX_ACTIVE_SUBSCRIPTIONS_PER_USER):
        async_session.add(
            WebPushSubscription(
                user_id=test_user.id,
                endpoint=f"{FCM}filler-{i}",
                p256dh_key="p",
                auth_key="a",
                last_seen_time=now,
            )
        )
    await async_session.commit()

    response = await authenticated_client.post(
        f"{BASE}/subscriptions", json=_payload(ENDPOINT_A)
    )

    assert response.status_code == 409
    assert response.json()["detail_code"] == "push.too_many_subscriptions"


# ============================================================================
# Provider management
# ============================================================================


async def test_provider_status_never_returns_the_private_key(
    admin_client: AsyncClient, configured_vapid
):
    response = await admin_client.get(f"{BASE}/providers/web-push")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["private_key_configured"] is True
    assert body["source"] == "database"
    assert "private_key" not in body


async def test_provider_status_requires_permission(authenticated_client: AsyncClient):
    response = await authenticated_client.get(f"{BASE}/providers/web-push")

    assert response.status_code == 403


async def test_generate_returns_a_usable_keypair_without_persisting_it(
    admin_client: AsyncClient,
):
    response = await admin_client.post(f"{BASE}/providers/web-push/generate")

    assert response.status_code == 200
    body = response.json()
    # Uncompressed P-256 point, base64url, unpadded.
    assert len(body["public_key"]) == 87
    assert body["public_key"].startswith("B")
    assert len(body["private_key"]) == 43

    # Not persisted: push is still unconfigured.
    probe = await admin_client.get(f"{BASE}/vapid-key")
    assert probe.status_code == 503


async def test_set_provider_rejects_a_subject_that_is_not_a_contact_uri(
    admin_client: AsyncClient,
):
    response = await admin_client.put(
        f"{BASE}/providers/web-push",
        json={
            "public_key": "BTestPublicKey",
            "private_key": "test-private-key",
            "subject": "ops@example.com",
        },
    )

    assert response.status_code == 422


async def test_set_provider_can_purge_subscriptions(
    admin_client: AsyncClient, async_session, test_admin_user
):
    """A new keypair invalidates every existing subscription; purging stops
    them being retried forever."""
    await admin_client.post(f"{BASE}/subscriptions", json=_payload(ENDPOINT_A))

    response = await admin_client.put(
        f"{BASE}/providers/web-push",
        json={
            "public_key": "BRotatedPublicKey",
            "private_key": "rotated-private-key",
            "subject": "mailto:ops@example.com",
            "purge_subscriptions": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["active_subscriptions"] == 0

    row = (
        await async_session.execute(
            select(WebPushSubscription).where(
                WebPushSubscription.endpoint == ENDPOINT_A
            )
        )
    ).scalar_one()
    assert row.deleted_time is not None
