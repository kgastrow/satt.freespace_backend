"""
API tests for SSO endpoints.

Tests OAuth authorization flow and callback handling.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
from httpx import AsyncClient
import jwt
import pytest
import pytest_asyncio

from src.core.config import settings
from src.core.security import hash_password
from src.models.organization_sso_settings import OrganizationSSOSettings
from src.services.cache import cache_service


# The single-use nonce guards for the OAuth ``state`` parameter and the SSO link
# token now fail CLOSED: with no nonce store they return 503 rather than
# silently skipping replay/CSRF protection. Tests therefore need a real store.


@pytest_asyncio.fixture(autouse=True)
async def sso_nonce_store():
    """Give ``cache_service`` a fake Redis so the nonce guards can run."""
    previous = cache_service._redis
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache_service._redis = fake
    try:
        yield fake
    finally:
        cache_service._redis = previous
        await fake.aclose()


async def _seed_state_nonce(nonce: str, org_id: str) -> None:
    await cache_service._redis.setex(f"sso_state:{nonce}", 600, org_id)


async def _seed_link_nonce(nonce: str, user_id: str) -> None:
    await cache_service._redis.setex(f"sso_link:{nonce}", 300, user_id)


# ==================== SSO Authorization Tests ====================


@pytest.mark.asyncio
async def test_sso_authorize_success(
    client: AsyncClient, async_session, test_organization
):
    """Test successful SSO authorization URL generation."""
    # Create SSO settings
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=True,
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
    )
    async_session.add(sso_settings)
    await async_session.commit()

    with patch("src.core.config.settings.GOOGLE_CLIENT_ID", "test-client-id"):
        with patch(
            "src.core.config.settings.GOOGLE_CLIENT_SECRET", "test-client-secret"
        ):
            response = await client.get(
                f"/api/v1/sso/google/authorize?org_slug={test_organization.slug}"
            )

    assert response.status_code == 200
    data = response.json()
    assert "authorization_url" in data
    assert "https://accounts.google.com/o/oauth2/v2/auth" in data["authorization_url"]
    assert "client_id=" in data["authorization_url"]
    assert "state=" in data["authorization_url"]


@pytest.mark.asyncio
async def test_sso_authorize_organization_not_found(client: AsyncClient):
    """Test SSO authorization with non-existent organization."""
    response = await client.get("/api/v1/sso/google/authorize?org_slug=nonexistent")

    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found"


@pytest.mark.asyncio
async def test_sso_authorize_organization_inactive(client: AsyncClient, async_session):
    """Test SSO authorization with inactive organization."""
    from src.models.organization import Organization

    inactive_org = Organization(
        name="Inactive Org", slug="inactive-sso-org", is_active=False
    )
    async_session.add(inactive_org)
    await async_session.commit()

    response = await client.get(
        "/api/v1/sso/google/authorize?org_slug=inactive-sso-org"
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Organization is not active"


@pytest.mark.asyncio
async def test_sso_authorize_sso_not_configured(client: AsyncClient, test_organization):
    """Test SSO authorization when SSO settings don't exist."""
    response = await client.get(
        f"/api/v1/sso/google/authorize?org_slug={test_organization.slug}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "SSO not configured for this organization"


@pytest.mark.asyncio
async def test_sso_authorize_provider_not_enabled(
    client: AsyncClient, async_session, test_organization
):
    """Test SSO authorization when provider is not enabled."""
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=False,
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
    )
    async_session.add(sso_settings)
    await async_session.commit()

    response = await client.get(
        f"/api/v1/sso/google/authorize?org_slug={test_organization.slug}"
    )

    assert response.status_code == 403
    assert (
        response.json()["detail"] == "Google SSO is not enabled for this organization"
    )


@pytest.mark.asyncio
async def test_sso_authorize_unknown_provider(
    client: AsyncClient, async_session, test_organization
):
    """Test SSO authorization with unknown provider."""
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=True,
    )
    async_session.add(sso_settings)
    await async_session.commit()

    response = await client.get(
        f"/api/v1/sso/microsoft/authorize?org_slug={test_organization.slug}"
    )

    assert response.status_code == 400
    assert "Unknown or unsupported SSO provider" in response.json()["detail"]


# ==================== SSO Callback Tests ====================


@pytest.mark.asyncio
async def test_sso_callback_create_new_user(
    client: AsyncClient, async_session, test_organization
):
    """Test SSO callback that creates a new user with identity."""
    from src.crud.user_identity import get_by_user_id
    from src.models.user import CreatedVia

    # Create SSO settings
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=True,
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
    )
    async_session.add(sso_settings)
    await async_session.commit()

    # Create state token
    state_data = {
        "state": "test-state",
        "org_id": str(test_organization.id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    state_token = jwt.encode(state_data, settings.JWT_SECRET, algorithm="HS256")
    await _seed_state_nonce("test-state", str(test_organization.id))

    # Mock SSO provider - must include 'id' for provider_user_id
    mock_provider = AsyncMock()
    mock_provider.exchange_code_for_tokens = AsyncMock(
        return_value={"access_token": "mock-access-token"}
    )
    mock_provider.get_user_info = AsyncMock(
        return_value={
            "email": "newuser@example.com",
            "name": "New User",
            "id": "google-user-123",
        }
    )

    with patch("src.core.config.settings.GOOGLE_CLIENT_ID", "test-client-id"):
        with patch(
            "src.core.config.settings.GOOGLE_CLIENT_SECRET", "test-client-secret"
        ):
            with patch(
                "src.api.sso.SSOProviderFactory.get_provider",
                return_value=mock_provider,
            ):
                response = await client.get(
                    f"/api/v1/sso/google/callback?code=test-code&state={state_token}"
                )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" not in data  # Refresh token is in httpOnly cookie
    assert "refresh_token=" in response.headers.get("set-cookie", "")

    # Verify user was created with correct created_via
    from src.crud.user import get_user_by_email

    user = await get_user_by_email(
        async_session, "newuser@example.com", str(test_organization.id)
    )
    assert user is not None
    assert user.email == "newuser@example.com"
    assert user.email_verified is True
    assert user.created_via == CreatedVia.GOOGLE
    assert user.password is None  # SSO users have no password

    # Verify identity was created
    identities = await get_by_user_id(
        async_session, str(user.id), str(test_organization.id)
    )
    assert len(identities) == 1
    assert identities[0].provider == "google"
    assert identities[0].provider_user_id == "google-user-123"


@pytest.mark.asyncio
async def test_sso_callback_requires_linking_for_email_user(
    client: AsyncClient, async_session, test_organization
):
    """Test SSO callback returns linking required for existing email user."""
    from src.models.user import User

    # Create existing user created via email (the default)
    existing_user = User(
        email="existing@example.com",
        password=hash_password("password123"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(existing_user)

    # Create SSO settings
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=True,
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
    )
    async_session.add(sso_settings)
    await async_session.commit()

    # Create state token
    state_data = {
        "state": "test-state",
        "org_id": str(test_organization.id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    state_token = jwt.encode(state_data, settings.JWT_SECRET, algorithm="HS256")
    await _seed_state_nonce("test-state", str(test_organization.id))

    # Mock SSO provider - must include 'id' for provider_user_id
    mock_provider = AsyncMock()
    mock_provider.exchange_code_for_tokens = AsyncMock(
        return_value={"access_token": "mock-access-token"}
    )
    mock_provider.get_user_info = AsyncMock(
        return_value={
            "email": "existing@example.com",
            "name": "Existing User",
            "id": "google-user-456",
        }
    )

    with patch("src.core.config.settings.GOOGLE_CLIENT_ID", "test-client-id"):
        with patch(
            "src.core.config.settings.GOOGLE_CLIENT_SECRET", "test-client-secret"
        ):
            with patch(
                "src.api.sso.SSOProviderFactory.get_provider",
                return_value=mock_provider,
            ):
                response = await client.get(
                    f"/api/v1/sso/google/callback?code=test-code&state={state_token}"
                )

    # Should return linking required response
    assert response.status_code == 200
    data = response.json()
    assert data["requires_linking"] is True
    assert "link_token" in data
    assert data["email"] == "existing@example.com"
    assert data["provider"] == "google"


@pytest.mark.asyncio
async def test_sso_callback_auto_links_same_provider_user(
    client: AsyncClient, async_session, test_organization
):
    """Test SSO callback auto-links user created via same provider (legacy migration)."""
    from src.crud.user_identity import get_by_user_id
    from src.models.user import CreatedVia, User

    # Create existing user created via GOOGLE (legacy user without identity)
    existing_user = User(
        email="google_user@example.com",
        password=None,  # SSO users have no password
        email_verified=True,
        organization_id=test_organization.id,
        created_via=CreatedVia.GOOGLE,
    )
    async_session.add(existing_user)

    # Create SSO settings
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=True,
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
    )
    async_session.add(sso_settings)
    await async_session.commit()
    await async_session.refresh(existing_user)

    # Create state token
    state_data = {
        "state": "test-state",
        "org_id": str(test_organization.id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    state_token = jwt.encode(state_data, settings.JWT_SECRET, algorithm="HS256")
    await _seed_state_nonce("test-state", str(test_organization.id))

    # Mock SSO provider
    mock_provider = AsyncMock()
    mock_provider.exchange_code_for_tokens = AsyncMock(
        return_value={"access_token": "mock-access-token"}
    )
    mock_provider.get_user_info = AsyncMock(
        return_value={
            "email": "google_user@example.com",
            "name": "Google User",
            "id": "google-user-789",
        }
    )

    with patch("src.core.config.settings.GOOGLE_CLIENT_ID", "test-client-id"):
        with patch(
            "src.core.config.settings.GOOGLE_CLIENT_SECRET", "test-client-secret"
        ):
            with patch(
                "src.api.sso.SSOProviderFactory.get_provider",
                return_value=mock_provider,
            ):
                response = await client.get(
                    f"/api/v1/sso/google/callback?code=test-code&state={state_token}"
                )

    # Should auto-link and return tokens
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" not in data  # Refresh token is in httpOnly cookie
    assert "refresh_token=" in response.headers.get("set-cookie", "")

    # Verify identity was created
    identities = await get_by_user_id(
        async_session, str(existing_user.id), str(test_organization.id)
    )
    assert len(identities) == 1
    assert identities[0].provider == "google"
    assert identities[0].provider_user_id == "google-user-789"


@pytest.mark.asyncio
async def test_sso_callback_login_with_existing_identity(
    client: AsyncClient, async_session, test_organization
):
    """Test SSO callback logs in directly when identity already exists."""
    from src.models.user import CreatedVia, User
    from src.models.user_identity import UserIdentity

    # Create user with existing identity
    existing_user = User(
        email="linked_user@example.com",
        password=None,
        email_verified=True,
        organization_id=test_organization.id,
        created_via=CreatedVia.GOOGLE,
    )
    async_session.add(existing_user)
    await async_session.flush()

    # Create identity record
    identity = UserIdentity(
        organization_id=test_organization.id,
        user_id=existing_user.id,
        provider="google",
        provider_user_id="google-user-existing",
        provider_email="linked_user@example.com",
    )
    async_session.add(identity)

    # Create SSO settings
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=True,
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
    )
    async_session.add(sso_settings)
    await async_session.commit()

    # Create state token
    state_data = {
        "state": "test-state",
        "org_id": str(test_organization.id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    state_token = jwt.encode(state_data, settings.JWT_SECRET, algorithm="HS256")
    await _seed_state_nonce("test-state", str(test_organization.id))

    # Mock SSO provider returning same provider_user_id
    mock_provider = AsyncMock()
    mock_provider.exchange_code_for_tokens = AsyncMock(
        return_value={"access_token": "mock-access-token"}
    )
    mock_provider.get_user_info = AsyncMock(
        return_value={
            "email": "linked_user@example.com",
            "name": "Linked User",
            "id": "google-user-existing",  # Same as identity
        }
    )

    with patch("src.core.config.settings.GOOGLE_CLIENT_ID", "test-client-id"):
        with patch(
            "src.core.config.settings.GOOGLE_CLIENT_SECRET", "test-client-secret"
        ):
            with patch(
                "src.api.sso.SSOProviderFactory.get_provider",
                return_value=mock_provider,
            ):
                response = await client.get(
                    f"/api/v1/sso/google/callback?code=test-code&state={state_token}"
                )

    # Should log in directly
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" not in data  # Refresh token is in httpOnly cookie
    assert "refresh_token=" in response.headers.get("set-cookie", "")
    assert "requires_linking" not in data


@pytest.mark.asyncio
async def test_sso_callback_invalid_state(client: AsyncClient):
    """Test SSO callback with invalid state token."""
    response = await client.get(
        "/api/v1/sso/google/callback?code=test-code&state=invalid-state"
    )

    assert response.status_code == 400
    assert "Invalid state parameter" in response.json()["detail"]


@pytest.mark.asyncio
async def test_sso_callback_expired_state(client: AsyncClient, test_organization):
    """Test SSO callback with expired state token."""
    # Create expired state token
    state_data = {
        "state": "test-state",
        "org_id": str(test_organization.id),
        "exp": datetime.now(timezone.utc) - timedelta(minutes=10),  # Expired
    }
    state_token = jwt.encode(state_data, settings.JWT_SECRET, algorithm="HS256")
    await _seed_state_nonce("test-state", str(test_organization.id))

    response = await client.get(
        f"/api/v1/sso/google/callback?code=test-code&state={state_token}"
    )

    assert response.status_code == 400
    assert "State parameter expired" in response.json()["detail"]


@pytest.mark.asyncio
async def test_sso_callback_inactive_organization(client: AsyncClient, async_session):
    """Test SSO callback with inactive organization."""
    from src.models.organization import Organization

    inactive_org = Organization(
        name="Inactive Org", slug="inactive-callback-org", is_active=False
    )
    async_session.add(inactive_org)
    await async_session.commit()

    # Create state token
    state_data = {
        "state": "test-state",
        "org_id": str(inactive_org.id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    state_token = jwt.encode(state_data, settings.JWT_SECRET, algorithm="HS256")
    await _seed_state_nonce("test-state", str(inactive_org.id))

    response = await client.get(
        f"/api/v1/sso/google/callback?code=test-code&state={state_token}"
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Organization is not active"


@pytest.mark.asyncio
async def test_sso_callback_no_email_from_provider(
    client: AsyncClient, async_session, test_organization
):
    """Test SSO callback when provider doesn't return email."""
    # Create SSO settings
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=True,
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
    )
    async_session.add(sso_settings)
    await async_session.commit()

    # Create state token
    state_data = {
        "state": "test-state",
        "org_id": str(test_organization.id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    state_token = jwt.encode(state_data, settings.JWT_SECRET, algorithm="HS256")
    await _seed_state_nonce("test-state", str(test_organization.id))

    # Mock SSO provider without email
    mock_provider = AsyncMock()
    mock_provider.exchange_code_for_tokens = AsyncMock(
        return_value={"access_token": "mock-access-token"}
    )
    mock_provider.get_user_info = AsyncMock(
        return_value={"name": "User Without Email", "id": "google-123"}  # No email
    )

    with patch("src.core.config.settings.GOOGLE_CLIENT_ID", "test-client-id"):
        with patch(
            "src.core.config.settings.GOOGLE_CLIENT_SECRET", "test-client-secret"
        ):
            with patch(
                "src.api.sso.SSOProviderFactory.get_provider",
                return_value=mock_provider,
            ):
                response = await client.get(
                    f"/api/v1/sso/google/callback?code=test-code&state={state_token}"
                )

    assert response.status_code == 400
    assert "Email not provided" in response.json()["detail"]


@pytest.mark.asyncio
async def test_sso_callback_no_provider_user_id(
    client: AsyncClient, async_session, test_organization
):
    """Test SSO callback when provider doesn't return user ID."""
    # Create SSO settings
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=True,
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
    )
    async_session.add(sso_settings)
    await async_session.commit()

    # Create state token
    state_data = {
        "state": "test-state",
        "org_id": str(test_organization.id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    state_token = jwt.encode(state_data, settings.JWT_SECRET, algorithm="HS256")
    await _seed_state_nonce("test-state", str(test_organization.id))

    # Mock SSO provider without user ID
    mock_provider = AsyncMock()
    mock_provider.exchange_code_for_tokens = AsyncMock(
        return_value={"access_token": "mock-access-token"}
    )
    mock_provider.get_user_info = AsyncMock(
        return_value={"email": "user@example.com", "name": "User Without ID"}  # No id
    )

    with patch("src.core.config.settings.GOOGLE_CLIENT_ID", "test-client-id"):
        with patch(
            "src.core.config.settings.GOOGLE_CLIENT_SECRET", "test-client-secret"
        ):
            with patch(
                "src.api.sso.SSOProviderFactory.get_provider",
                return_value=mock_provider,
            ):
                response = await client.get(
                    f"/api/v1/sso/google/callback?code=test-code&state={state_token}"
                )

    assert response.status_code == 400
    assert "User ID not provided" in response.json()["detail"]


# ==================== Multi-Tenancy Isolation Tests ====================


@pytest.mark.asyncio
async def test_sso_callback_tenant_isolation(
    client: AsyncClient, async_session, test_organization
):
    """Test that SSO callback respects tenant isolation."""
    from src.models.organization import Organization
    from src.models.user import CreatedVia, User

    # Create second organization
    org2 = Organization(name="Org 2", slug="org2", is_active=True)
    async_session.add(org2)
    await async_session.commit()
    await async_session.refresh(org2)

    # Create user in org2
    user_in_org2 = User(
        email="user@example.com",
        password=hash_password("password123"),
        email_verified=True,
        organization_id=org2.id,
    )
    async_session.add(user_in_org2)

    # Create SSO settings for test_organization
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=True,
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
    )
    async_session.add(sso_settings)
    await async_session.commit()

    # Create state token for test_organization
    state_data = {
        "state": "test-state",
        "org_id": str(test_organization.id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    state_token = jwt.encode(state_data, settings.JWT_SECRET, algorithm="HS256")
    await _seed_state_nonce("test-state", str(test_organization.id))

    # Mock SSO provider returning same email but different org
    mock_provider = AsyncMock()
    mock_provider.exchange_code_for_tokens = AsyncMock(
        return_value={"access_token": "mock-access-token"}
    )
    mock_provider.get_user_info = AsyncMock(
        return_value={
            "email": "user@example.com",
            "name": "Test User",
            "id": "google-tenant-isolation-test",
        }
    )

    with patch("src.core.config.settings.GOOGLE_CLIENT_ID", "test-client-id"):
        with patch(
            "src.core.config.settings.GOOGLE_CLIENT_SECRET", "test-client-secret"
        ):
            with patch(
                "src.api.sso.SSOProviderFactory.get_provider",
                return_value=mock_provider,
            ):
                response = await client.get(
                    f"/api/v1/sso/google/callback?code=test-code&state={state_token}"
                )

    assert response.status_code == 200

    # Verify a new user was created in test_organization (not linked to org2 user)
    from src.crud.user import get_user_by_email

    user_in_test_org = await get_user_by_email(
        async_session, "user@example.com", str(test_organization.id)
    )
    assert user_in_test_org is not None
    assert user_in_test_org.id != user_in_org2.id
    assert user_in_test_org.organization_id == test_organization.id
    assert user_in_test_org.created_via == CreatedVia.GOOGLE


# ==================== Account Linking Tests ====================


@pytest.mark.asyncio
async def test_confirm_account_link_success(
    client: AsyncClient, async_session, test_organization
):
    """Test successful account linking confirmation."""
    import secrets

    from src.crud.user_identity import get_by_user_id
    from src.models.user import User

    # Create existing user
    existing_user = User(
        email="link_test@example.com",
        password=hash_password("password123"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(existing_user)
    await async_session.commit()
    await async_session.refresh(existing_user)

    # Create link token
    link_nonce = secrets.token_urlsafe(32)
    link_token = jwt.encode(
        {
            "user_id": str(existing_user.id),
            "provider": "google",
            "provider_user_id": "google-link-test-123",
            "provider_email": "link_test@example.com",
            "org_id": str(test_organization.id),
            "nonce": link_nonce,
            "purpose": "sso_link",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )

    # The link endpoint now requires proof of control over the existing
    # account (a session for that user, or its password) and burns the nonce
    # only after the proof passes.
    await _seed_link_nonce(link_nonce, str(existing_user.id))

    response = await client.post(
        "/api/v1/auth/sso/link",
        json={"link_token": link_token, "password": "password123"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" not in data  # Refresh token is in httpOnly cookie
    assert "refresh_token=" in response.headers.get("set-cookie", "")

    # Verify identity was created
    identities = await get_by_user_id(
        async_session, str(existing_user.id), str(test_organization.id)
    )
    assert len(identities) == 1
    assert identities[0].provider == "google"
    assert identities[0].provider_user_id == "google-link-test-123"


@pytest.mark.asyncio
async def test_confirm_account_link_expired_token(
    client: AsyncClient, async_session, test_organization
):
    """Test account linking with expired token."""
    import secrets

    from src.models.user import User

    existing_user = User(
        email="expired_link@example.com",
        password=hash_password("password123"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(existing_user)
    await async_session.commit()
    await async_session.refresh(existing_user)

    # Create expired link token
    link_nonce = secrets.token_urlsafe(32)
    link_token = jwt.encode(
        {
            "user_id": str(existing_user.id),
            "provider": "google",
            "provider_user_id": "google-expired-123",
            "provider_email": "expired_link@example.com",
            "org_id": str(test_organization.id),
            "nonce": link_nonce,
            "purpose": "sso_link",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=10),  # Expired
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )

    response = await client.post(
        "/api/v1/auth/sso/link",
        json={"link_token": link_token},
    )

    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_confirm_account_link_invalid_token(client: AsyncClient):
    """Test account linking with invalid token."""
    response = await client.post(
        "/api/v1/auth/sso/link",
        json={"link_token": "invalid-token"},
    )

    assert response.status_code == 400
    assert "Invalid link token" in response.json()["detail"]


@pytest.mark.asyncio
async def test_confirm_account_link_wrong_purpose(
    client: AsyncClient, async_session, test_organization
):
    """Test account linking with token that has wrong purpose."""
    import secrets

    from src.models.user import User

    existing_user = User(
        email="wrong_purpose@example.com",
        password=hash_password("password123"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(existing_user)
    await async_session.commit()
    await async_session.refresh(existing_user)

    # Create token with wrong purpose
    link_nonce = secrets.token_urlsafe(32)
    link_token = jwt.encode(
        {
            "user_id": str(existing_user.id),
            "provider": "google",
            "provider_user_id": "google-wrong-purpose",
            "org_id": str(test_organization.id),
            "nonce": link_nonce,
            "purpose": "wrong_purpose",  # Wrong purpose
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )

    response = await client.post(
        "/api/v1/auth/sso/link",
        json={"link_token": link_token},
    )

    assert response.status_code == 400
    assert "Invalid link token" in response.json()["detail"]
