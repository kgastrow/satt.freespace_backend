"""The SSO callback must present the second factor, not skip it.

``GET /sso/{provider}/callback`` used to mint a full session for a 2FA-enrolled
user without ever asking for a code: "Sign in with Google" was a password-less
bypass of the organization's 2FA policy. The challenge round-trip lived behind
``SSO_TWO_FACTOR_CHALLENGE_ENABLED`` until the frontend OAuth callback page
learned to handle a ``requires_2fa`` response; it is now on.

The case these tests exist to protect is the one that kept the gate shut: an
**SSO-only** account (``password is None``) enrolled in 2FA has no password
login to fall back on, so if the challenge cannot be completed the account is
locked out for good. ``test_sso_only_2fa_account_completes_full_login`` walks
that account from the OAuth callback to a usable session.

Gate ordering matters too: suspension and organization-active must be reported
*ahead* of the second factor, so a suspended or dormant-org account never even
receives a challenge token.
"""

from datetime import datetime, timedelta, timezone
import secrets
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
from httpx import AsyncClient
import jwt
import pyotp
import pytest
import pytest_asyncio

from src.core.config import settings
from src.core.encryption import encrypt_field
from src.core.security import hash_password
from src.models.organization import Organization
from src.models.organization_sso_settings import OrganizationSSOSettings
from src.models.user import CreatedVia, SuspensionStatus, User
from src.models.user_two_factor import UserTwoFactor
from src.services.auth_session import (
    SSO_TWO_FACTOR_CHALLENGE_ENABLED,
    TWO_FACTOR_CHALLENGE_PURPOSE,
)
from src.services.cache import cache_service


SSO_EMAIL = "sso_2fa@example.com"
TOTP_SECRET = "JBSWY3DPEHPK3PXP"


# ============================================================================
# FIXTURES / HELPERS
# ============================================================================


@pytest_asyncio.fixture
async def nonce_store():
    """A working (fake) Redis - the SSO state nonce guard fails CLOSED without it."""
    previous = cache_service._redis
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache_service._redis = fake
    try:
        yield fake
    finally:
        cache_service._redis = previous
        await fake.aclose()


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


def _state_token(org_id, nonce: str) -> str:
    return jwt.encode(
        {
            "state": nonce,
            "org_id": str(org_id),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )


def _mock_google(email: str = SSO_EMAIL, provider_user_id: str = "google-2fa-1"):
    provider = AsyncMock()
    provider.exchange_code_for_tokens = AsyncMock(
        return_value={"access_token": "mock-access-token"}
    )
    provider.get_user_info = AsyncMock(
        return_value={"email": email, "name": "T", "id": provider_user_id}
    )
    return patch("src.api.sso.SSOProviderFactory.get_provider", return_value=provider)


async def _sso_callback(client: AsyncClient, nonce_store, org_id, *, email=SSO_EMAIL):
    """Run one full SSO callback, minting and burning a fresh state nonce."""
    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_state:{nonce}", 600, str(org_id))
    with _mock_google(email=email):
        return await client.get(
            f"/api/v1/sso/google/callback"
            f"?code=test-code&state={_state_token(org_id, nonce)}"
        )


def _detail_code(response) -> str:
    body = response.json()
    detail = body.get("detail")
    if isinstance(detail, dict):
        return detail.get("detail_code", "")
    return body.get("detail_code", "")


async def _enrol_in_2fa(async_session, user, organization_id) -> None:
    async_session.add(
        UserTwoFactor(
            user_id=user.id,
            organization_id=organization_id,
            secret=encrypt_field(TOTP_SECRET),
            is_enabled=True,
            verified_at=datetime.now(timezone.utc),
        )
    )
    await async_session.commit()


async def _make_sso_user(
    async_session,
    organization_id,
    *,
    password: str | None = None,
    suspension_status: str | None = None,
    email: str = SSO_EMAIL,
) -> User:
    """A user whose origin is Google, so the callback auto-links rather than
    asking to confirm a link."""
    kwargs = {}
    if suspension_status is not None:
        kwargs["suspension_status"] = suspension_status
    user = User(
        email=email,
        password=hash_password(password) if password else None,
        email_verified=True,
        organization_id=organization_id,
        created_via=CreatedVia.GOOGLE,
        **kwargs,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


# ============================================================================
# The flag itself
# ============================================================================


def test_sso_two_factor_challenge_is_enabled():
    """A regression guard: turning this back off silently drops the second
    factor for every SSO login."""
    assert SSO_TWO_FACTOR_CHALLENGE_ENABLED is True


# ============================================================================
# Challenge instead of session
# ============================================================================


@pytest.mark.asyncio
async def test_sso_login_with_2fa_returns_challenge_not_session(
    client: AsyncClient, async_session, sso_enabled_org, nonce_store
):
    """A 2FA-enrolled user must be challenged, not signed straight in."""
    user = await _make_sso_user(async_session, sso_enabled_org.id)
    await _enrol_in_2fa(async_session, user, sso_enabled_org.id)

    response = await _sso_callback(client, nonce_store, sso_enabled_org.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requires_2fa"] is True
    assert body["two_factor_token"]
    # No session was issued: no bearer token...
    assert "access_token" not in body
    # ...and no refresh cookie either.
    assert "refresh_token=" not in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_sso_challenge_token_is_a_2fa_verification_token(
    client: AsyncClient, async_session, sso_enabled_org, nonce_store
):
    """The challenge token must carry the purpose claim /auth/verify-2fa
    requires, scoped to the right user and tenant - it is not a session token."""
    user = await _make_sso_user(async_session, sso_enabled_org.id)
    await _enrol_in_2fa(async_session, user, sso_enabled_org.id)

    response = await _sso_callback(client, nonce_store, sso_enabled_org.id)
    token = response.json()["two_factor_token"]

    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    assert payload["purpose"] == TWO_FACTOR_CHALLENGE_PURPOSE
    assert payload["user_id"] == str(user.id)
    assert payload["organization_id"] == str(sso_enabled_org.id)


@pytest.mark.asyncio
async def test_sso_challenge_completes_with_valid_totp(
    client: AsyncClient, async_session, sso_enabled_org, nonce_store
):
    """The challenge handed back by SSO is completed by the ordinary
    /auth/verify-2fa round-trip."""
    user = await _make_sso_user(
        async_session, sso_enabled_org.id, password="Password123!"
    )
    await _enrol_in_2fa(async_session, user, sso_enabled_org.id)

    callback = await _sso_callback(client, nonce_store, sso_enabled_org.id)
    two_factor_token = callback.json()["two_factor_token"]

    verify = await client.post(
        "/api/v1/auth/verify-2fa",
        json={
            "two_factor_token": two_factor_token,
            "code": pyotp.TOTP(TOTP_SECRET).now(),
        },
    )

    assert verify.status_code == 200, verify.text
    assert verify.json()["access_token"]


@pytest.mark.asyncio
async def test_sso_challenge_rejects_invalid_code(
    client: AsyncClient, async_session, sso_enabled_org, nonce_store
):
    """A wrong code must not turn the challenge into a session."""
    user = await _make_sso_user(async_session, sso_enabled_org.id)
    await _enrol_in_2fa(async_session, user, sso_enabled_org.id)

    callback = await _sso_callback(client, nonce_store, sso_enabled_org.id)
    two_factor_token = callback.json()["two_factor_token"]

    verify = await client.post(
        "/api/v1/auth/verify-2fa",
        json={"two_factor_token": two_factor_token, "code": "000000"},
    )

    assert verify.status_code == 401
    assert "access_token" not in verify.json()


# ============================================================================
# The case the gate was protecting: an SSO-ONLY 2FA account
# ============================================================================


@pytest.mark.asyncio
async def test_sso_only_2fa_account_completes_full_login(
    client: AsyncClient, async_session, sso_enabled_org, nonce_store
):
    """END TO END for the lockout case.

    ``password is None`` -- there is no password login to fall back on, so this
    account is reachable *only* through the SSO callback. It must be able to go
    OAuth callback -> challenge -> verify -> working session. If any link in
    that chain breaks, the account is locked out permanently.
    """
    user = await _make_sso_user(async_session, sso_enabled_org.id, password=None)
    assert user.password is None, "this test is meaningless with a password set"
    await _enrol_in_2fa(async_session, user, sso_enabled_org.id)

    # 1. OAuth callback -> challenge, no session.
    callback = await _sso_callback(client, nonce_store, sso_enabled_org.id)
    assert callback.status_code == 200, callback.text
    assert callback.json()["requires_2fa"] is True
    assert "access_token" not in callback.json()

    # 2. Complete the second factor.
    verify = await client.post(
        "/api/v1/auth/verify-2fa",
        json={
            "two_factor_token": callback.json()["two_factor_token"],
            "code": pyotp.TOTP(TOTP_SECRET).now(),
        },
    )
    assert verify.status_code == 200, verify.text
    access_token = verify.json()["access_token"]
    assert access_token

    # 3. The session actually works - the user is signed in, not just handed a
    #    string. A refresh cookie was set too, so the session can be renewed.
    assert "refresh_token=" in verify.headers.get("set-cookie", "")
    me = await client.get(
        "/api/v1/user/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert me.status_code == 200, me.text
    assert me.json()["email"] == SSO_EMAIL


# ============================================================================
# Users without 2FA are unaffected
# ============================================================================


@pytest.mark.asyncio
async def test_sso_login_without_2fa_still_issues_a_session(
    client: AsyncClient, async_session, sso_enabled_org, nonce_store
):
    """Control: a user not enrolled in 2FA signs in exactly as before."""
    await _make_sso_user(async_session, sso_enabled_org.id)

    response = await _sso_callback(client, nonce_store, sso_enabled_org.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_token"]
    assert "requires_2fa" not in body
    assert "refresh_token=" in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_sso_login_ignores_a_disabled_2fa_record(
    client: AsyncClient, async_session, sso_enabled_org, nonce_store
):
    """A half-finished enrolment (``is_enabled=False``) is not an enrolment and
    must not challenge - that would strand a user mid-setup."""
    user = await _make_sso_user(async_session, sso_enabled_org.id)
    async_session.add(
        UserTwoFactor(
            user_id=user.id,
            organization_id=sso_enabled_org.id,
            secret=encrypt_field(TOTP_SECRET),
            is_enabled=False,
        )
    )
    await async_session.commit()

    response = await _sso_callback(client, nonce_store, sso_enabled_org.id)

    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


# ============================================================================
# Gate ordering: suspension / org-active fire AHEAD of the second factor
# ============================================================================


@pytest.mark.asyncio
async def test_suspension_is_reported_before_the_2fa_challenge(
    client: AsyncClient, async_session, sso_enabled_org, nonce_store
):
    """A suspended account must be refused outright, never handed a challenge
    token it could complete."""
    user = await _make_sso_user(
        async_session,
        sso_enabled_org.id,
        suspension_status=SuspensionStatus.SUSPENDED,
    )
    await _enrol_in_2fa(async_session, user, sso_enabled_org.id)

    response = await _sso_callback(client, nonce_store, sso_enabled_org.id)

    assert response.status_code == 403
    assert _detail_code(response) == "user.suspended"
    assert "two_factor_token" not in response.text


@pytest.mark.asyncio
async def test_inactive_organization_is_reported_before_the_2fa_challenge(
    client: AsyncClient, async_session, nonce_store
):
    """A dormant org must be refused before any challenge is minted."""
    org = Organization(name="Dormant", slug="dormant-sso-2fa", is_active=False)
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
    await async_session.commit()

    user = await _make_sso_user(async_session, org.id)
    await _enrol_in_2fa(async_session, user, org.id)

    response = await _sso_callback(client, nonce_store, org.id)

    assert response.status_code == 403
    assert _detail_code(response) == "auth.organization_not_active"
    assert "two_factor_token" not in response.text
