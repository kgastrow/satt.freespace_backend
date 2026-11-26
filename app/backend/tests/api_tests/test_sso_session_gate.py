"""Security tests for the SSO login gate, nonce replay guards and link proof.

Covers three findings:

1. The SSO callback applied no suspension check and no 2FA gate, so "Sign in
   with Google" was a password-less bypass of both. Every login path now routes
   through ``src.services.auth_session.issue_session_for_user``.
2. The single-use nonce checks (OAuth ``state`` and the SSO link token) failed
   OPEN when Redis was unavailable, silently removing replay/CSRF protection.
   They now fail CLOSED with a 503.
3. ``POST /auth/sso/link`` required no proof of control over the existing
   account: possession of the link token was the whole proof and it minted a
   full session. It now requires an existing session for the same user, or the
   account's password.
"""

from datetime import datetime, timedelta, timezone
import secrets
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
from httpx import AsyncClient
import jwt
import pytest
import pytest_asyncio

from src.core.config import settings
from src.core.security import create_access_token, hash_password
from src.models.organization import Organization
from src.models.organization_sso_settings import OrganizationSSOSettings
from src.models.user import CreatedVia, SuspensionStatus, User
from src.services.cache import cache_service


PASSWORD = "LinkPassword123!"


# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def nonce_store():
    """Give ``cache_service`` a working (fake) Redis for the nonce guards.

    The nonce guards now fail CLOSED, so a test that wants the happy path must
    supply a store. Tests that want the *unavailable* behaviour simply do not
    request this fixture.
    """
    previous = cache_service._redis
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache_service._redis = fake
    try:
        yield fake
    finally:
        cache_service._redis = previous
        await fake.aclose()


@pytest_asyncio.fixture
async def no_nonce_store():
    """Simulate the nonce store being unavailable (Redis down / not configured)."""
    previous = cache_service._redis
    cache_service._redis = None
    try:
        yield
    finally:
        cache_service._redis = previous


@pytest_asyncio.fixture
async def sso_enabled_org(async_session, test_organization):
    async_session.add(
        OrganizationSSOSettings(
            organization_id=test_organization.id,
            google_enabled=True,
            google_client_id="test-client-id",
            google_client_secret="test-client-secret",
        )
    )
    await async_session.commit()
    return test_organization


def _state_token(org_id: str, nonce: str) -> str:
    return jwt.encode(
        {
            "state": nonce,
            "org_id": str(org_id),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )


def _link_token(
    user_id: str,
    org_id: str,
    nonce: str,
    *,
    provider_user_id: str = "google-link-1",
    email: str = "linkme@example.com",
) -> str:
    return jwt.encode(
        {
            "user_id": str(user_id),
            "provider": "google",
            "provider_user_id": provider_user_id,
            "provider_email": email,
            "org_id": str(org_id),
            "nonce": nonce,
            "purpose": "sso_link",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )


def _mock_google(email: str, provider_user_id: str):
    provider = AsyncMock()
    provider.exchange_code_for_tokens = AsyncMock(
        return_value={"access_token": "mock-access-token"}
    )
    provider.get_user_info = AsyncMock(
        return_value={"email": email, "name": "T", "id": provider_user_id}
    )
    return patch("src.api.sso.SSOProviderFactory.get_provider", return_value=provider)


async def _sso_callback(client: AsyncClient, state_token: str):
    with _mock_google("sso_gate@example.com", "google-gate-1"):
        return await client.get(
            f"/api/v1/sso/google/callback?code=test-code&state={state_token}"
        )


def _detail_code(response) -> str:
    body = response.json()
    detail = body.get("detail")
    if isinstance(detail, dict):
        return detail.get("detail_code", "")
    return body.get("detail_code", "")


# ============================================================================
# 1. SSO must not bypass suspension / organization-active
# ============================================================================


@pytest.mark.asyncio
async def test_sso_login_rejects_suspended_user(
    client: AsyncClient, async_session, sso_enabled_org, nonce_store
):
    """A suspended employee must not be able to log back in through SSO."""
    user = User(
        email="sso_gate@example.com",
        password=None,
        email_verified=True,
        organization_id=sso_enabled_org.id,
        created_via=CreatedVia.GOOGLE,
        suspension_status=SuspensionStatus.SUSPENDED,
    )
    async_session.add(user)
    await async_session.commit()

    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_state:{nonce}", 600, str(sso_enabled_org.id))

    response = await _sso_callback(client, _state_token(sso_enabled_org.id, nonce))

    assert response.status_code == 403
    assert _detail_code(response) == "user.suspended"


@pytest.mark.asyncio
async def test_sso_login_allows_active_user(
    client: AsyncClient, async_session, sso_enabled_org, nonce_store
):
    """Control for the test above: an active user still signs in."""
    user = User(
        email="sso_gate@example.com",
        password=None,
        email_verified=True,
        organization_id=sso_enabled_org.id,
        created_via=CreatedVia.GOOGLE,
    )
    async_session.add(user)
    await async_session.commit()

    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_state:{nonce}", 600, str(sso_enabled_org.id))

    response = await _sso_callback(client, _state_token(sso_enabled_org.id, nonce))

    assert response.status_code == 200, response.text
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_sso_login_rejects_inactive_organization(
    client: AsyncClient, async_session, nonce_store
):
    """An org that has been switched off must not be reachable through SSO."""
    org = Organization(name="Dormant", slug="dormant-sso-gate", is_active=False)
    async_session.add(org)
    await async_session.commit()
    await async_session.refresh(org)

    async_session.add(
        OrganizationSSOSettings(
            organization_id=org.id,
            google_enabled=True,
            google_client_id="test-client-id",
            google_client_secret="test-client-secret",
        )
    )
    async_session.add(
        User(
            email="sso_gate@example.com",
            password=None,
            email_verified=True,
            organization_id=org.id,
            created_via=CreatedVia.GOOGLE,
        )
    )
    await async_session.commit()

    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_state:{nonce}", 600, str(org.id))

    response = await _sso_callback(client, _state_token(org.id, nonce))

    assert response.status_code == 403
    assert _detail_code(response) == "auth.organization_not_active"


# ============================================================================
# 2. Nonce guards must fail CLOSED
# ============================================================================


@pytest.mark.asyncio
async def test_sso_state_nonce_store_unavailable_returns_503(
    client: AsyncClient, sso_enabled_org, no_nonce_store
):
    """With no nonce store the CSRF-state replay guard cannot run: refuse."""
    response = await _sso_callback(
        client, _state_token(sso_enabled_org.id, secrets.token_urlsafe(16))
    )

    assert response.status_code == 503
    assert _detail_code(response) == "sso.state_verification_unavailable"


@pytest.mark.asyncio
async def test_sso_state_nonce_is_single_use(
    client: AsyncClient, async_session, sso_enabled_org, nonce_store
):
    """A replayed state must be refused on the second use, not accepted."""
    async_session.add(
        User(
            email="sso_gate@example.com",
            password=None,
            email_verified=True,
            organization_id=sso_enabled_org.id,
            created_via=CreatedVia.GOOGLE,
        )
    )
    await async_session.commit()

    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_state:{nonce}", 600, str(sso_enabled_org.id))
    state = _state_token(sso_enabled_org.id, nonce)

    first = await _sso_callback(client, state)
    assert first.status_code == 200, first.text

    second = await _sso_callback(client, state)
    assert second.status_code == 400
    assert _detail_code(second) == "sso.state_replay"


@pytest.mark.asyncio
async def test_link_nonce_store_unavailable_returns_503(
    client: AsyncClient, async_session, test_organization, no_nonce_store
):
    """With no nonce store the link token replay guard cannot run: refuse.

    Previously this fell through to a ``Logger.warning`` and the link token
    stayed replayable for its whole 5-minute TTL.
    """
    user = User(
        email="nonce_down@example.com",
        password=hash_password(PASSWORD),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    token = _link_token(user.id, test_organization.id, secrets.token_urlsafe(16))

    response = await client.post(
        "/api/v1/auth/sso/link",
        json={"link_token": token, "password": PASSWORD},
    )

    assert response.status_code == 503
    assert _detail_code(response) == "sso.link_verification_unavailable"


# ============================================================================
# 3. Account linking requires proof of control
# ============================================================================


@pytest_asyncio.fixture
async def link_user(async_session, test_organization):
    user = User(
        email="linkme@example.com",
        password=hash_password(PASSWORD),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_link_without_any_proof_is_rejected(
    client: AsyncClient, test_organization, link_user, nonce_store
):
    """Possession of the link token alone must no longer be enough."""
    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_link:{nonce}", 300, str(link_user.id))
    token = _link_token(link_user.id, test_organization.id, nonce)

    response = await client.post("/api/v1/auth/sso/link", json={"link_token": token})

    assert response.status_code == 401
    assert _detail_code(response) == "sso.link_proof_required"
    # The token must NOT have been consumed by a refused attempt.
    assert await nonce_store.get(f"sso_link:{nonce}") == str(link_user.id)


@pytest.mark.asyncio
async def test_link_with_correct_password_is_accepted(
    client: AsyncClient, async_session, test_organization, link_user, nonce_store
):
    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_link:{nonce}", 300, str(link_user.id))
    token = _link_token(link_user.id, test_organization.id, nonce)

    response = await client.post(
        "/api/v1/auth/sso/link",
        json={"link_token": token, "password": PASSWORD},
    )

    assert response.status_code == 200, response.text
    assert "access_token" in response.json()
    assert "refresh_token=" in response.headers.get("set-cookie", "")

    from src.crud.user_identity import get_by_user_id

    identities = await get_by_user_id(
        async_session, str(link_user.id), str(test_organization.id)
    )
    assert [i.provider for i in identities] == ["google"]

    # Nonce burned exactly once.
    assert await nonce_store.get(f"sso_link:{nonce}") is None


@pytest.mark.asyncio
async def test_link_with_wrong_password_is_rejected_and_token_survives(
    client: AsyncClient, async_session, test_organization, link_user, nonce_store
):
    """A wrong password must not consume the user's single-use link token."""
    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_link:{nonce}", 300, str(link_user.id))
    token = _link_token(link_user.id, test_organization.id, nonce)

    response = await client.post(
        "/api/v1/auth/sso/link",
        json={"link_token": token, "password": "WrongPassword123!"},
    )

    # 403, not 401: `sso.link_proof_required` is the 401, so a status-only
    # client can still tell "proof rejected" from "no proof supplied".
    assert response.status_code == 403
    assert _detail_code(response) == "auth.invalid_password"
    assert await nonce_store.get(f"sso_link:{nonce}") == str(link_user.id)

    # No identity was created by the failed attempt.
    from src.crud.user_identity import get_by_user_id

    assert (
        await get_by_user_id(
            async_session, str(link_user.id), str(test_organization.id)
        )
        == []
    )

    # ...and the same token still works with the right password.
    retry = await client.post(
        "/api/v1/auth/sso/link",
        json={"link_token": token, "password": PASSWORD},
    )
    assert retry.status_code == 200, retry.text


@pytest.mark.asyncio
async def test_link_with_own_session_is_accepted(
    client: AsyncClient, test_organization, link_user, nonce_store
):
    """Being signed in as the account is proof enough - no password needed."""
    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_link:{nonce}", 300, str(link_user.id))
    token = _link_token(link_user.id, test_organization.id, nonce)

    bearer = create_access_token(
        user_id=str(link_user.id), organization_id=str(test_organization.id)
    )

    response = await client.post(
        "/api/v1/auth/sso/link",
        json={"link_token": token},
        headers={"Authorization": f"Bearer {bearer}"},
    )

    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_link_with_another_users_session_is_rejected(
    client: AsyncClient, async_session, test_organization, link_user, nonce_store
):
    """A valid session for a DIFFERENT user is not proof for this account."""
    other = User(
        email="bystander@example.com",
        password=hash_password(PASSWORD),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(other)
    await async_session.commit()
    await async_session.refresh(other)

    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_link:{nonce}", 300, str(link_user.id))
    token = _link_token(link_user.id, test_organization.id, nonce)

    bearer = create_access_token(
        user_id=str(other.id), organization_id=str(test_organization.id)
    )

    response = await client.post(
        "/api/v1/auth/sso/link",
        json={"link_token": token},
        headers={"Authorization": f"Bearer {bearer}"},
    )

    assert response.status_code == 401
    assert _detail_code(response) == "sso.link_proof_required"
    assert await nonce_store.get(f"sso_link:{nonce}") == str(link_user.id)


@pytest.mark.asyncio
async def test_link_sso_only_account_cannot_be_proved_by_password(
    client: AsyncClient, async_session, test_organization, nonce_store
):
    """An account with no password must already be signed in to link."""
    user = User(
        email="ssoonly@example.com",
        password=None,
        email_verified=True,
        organization_id=test_organization.id,
        created_via=CreatedVia.GOOGLE,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_link:{nonce}", 300, str(user.id))
    token = _link_token(user.id, test_organization.id, nonce)

    response = await client.post(
        "/api/v1/auth/sso/link",
        json={"link_token": token, "password": "anything-at-all"},
    )

    assert response.status_code == 401
    assert _detail_code(response) == "sso.link_proof_required"
    assert await nonce_store.get(f"sso_link:{nonce}") == str(user.id)


@pytest.mark.asyncio
async def test_link_rejects_suspended_account(
    client: AsyncClient, async_session, test_organization, nonce_store
):
    """The link path is a login, so the suspension gate applies there too."""
    user = User(
        email="suspended_link@example.com",
        password=hash_password(PASSWORD),
        email_verified=True,
        organization_id=test_organization.id,
        suspension_status=SuspensionStatus.SUSPENDED,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_link:{nonce}", 300, str(user.id))
    token = _link_token(user.id, test_organization.id, nonce)

    response = await client.post(
        "/api/v1/auth/sso/link",
        json={"link_token": token, "password": PASSWORD},
    )

    assert response.status_code == 403
    assert _detail_code(response) == "user.suspended"


# ============================================================================
# Tenant isolation on the link path
# ============================================================================


@pytest.mark.asyncio
async def test_link_token_cannot_cross_tenant_boundary(
    client: AsyncClient,
    async_session,
    test_organization,
    second_organization,
    link_user,
    nonce_store,
):
    """A link token naming another org must not resolve this org's user."""
    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_link:{nonce}", 300, str(link_user.id))
    # Same user_id, but org_id points at a tenant the user does not belong to.
    token = _link_token(link_user.id, second_organization.id, nonce)

    response = await client.post(
        "/api/v1/auth/sso/link",
        json={"link_token": token, "password": PASSWORD},
    )

    assert response.status_code == 400
    assert _detail_code(response) == "user.not_found"
    assert await nonce_store.get(f"sso_link:{nonce}") == str(link_user.id)


@pytest.mark.asyncio
async def test_link_proof_session_must_be_in_the_same_tenant(
    client: AsyncClient,
    async_session,
    test_organization,
    second_organization,
    link_user,
    nonce_store,
):
    """A session scoped to another org is not proof for this org's account."""
    cross_org_user = User(
        email="linkme@example.com",
        password=hash_password(PASSWORD),
        email_verified=True,
        organization_id=second_organization.id,
    )
    async_session.add(cross_org_user)
    await async_session.commit()
    await async_session.refresh(cross_org_user)

    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_link:{nonce}", 300, str(link_user.id))
    token = _link_token(link_user.id, test_organization.id, nonce)

    bearer = create_access_token(
        user_id=str(cross_org_user.id),
        organization_id=str(second_organization.id),
    )

    response = await client.post(
        "/api/v1/auth/sso/link",
        json={"link_token": token},
        headers={"Authorization": f"Bearer {bearer}"},
    )

    assert response.status_code == 401
    assert _detail_code(response) == "sso.link_proof_required"
