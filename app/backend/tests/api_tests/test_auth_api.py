"""
API tests for authentication endpoints.
Tests login, refresh, logout, and logout/all endpoints.
"""

from httpx import AsyncClient
import pytest

from src.core.security import hash_password
from src.crud.refresh_token import create_refresh_token


# ==================== Login Endpoint Tests ====================


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, async_session, test_organization):
    """Test successful login."""
    from src.models.user import User

    # Create a verified user
    user = User(
        email="logintest@test.com",
        password=hash_password("TestPass123"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "logintest@test.com",
            "password": "TestPass123",
            "organization_slug": test_organization.slug,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" not in data  # Refresh token is in httpOnly cookie
    assert len(data["access_token"]) > 0

    # Verify refresh token is set as httpOnly cookie
    set_cookie = response.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "path=/api/v1" in set_cookie.lower()


@pytest.mark.asyncio
async def test_login_invalid_email(client: AsyncClient, test_organization):
    """Test login with non-existent email."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@test.com",
            "password": "TestPass123",
            "organization_slug": test_organization.slug,
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_invalid_password(
    client: AsyncClient, async_session, test_organization
):
    """Test login with wrong password."""
    from src.models.user import User

    user = User(
        email="wrongpass@test.com",
        password=hash_password("CorrectPass123"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrongpass@test.com",
            "password": "WrongPass123",
            "organization_slug": test_organization.slug,
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_invalid_organization(
    client: AsyncClient, async_session, test_organization
):
    """Test login with non-existent organization."""
    from src.models.user import User

    user = User(
        email="orgtest@test.com",
        password=hash_password("TestPass123"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "orgtest@test.com",
            "password": "TestPass123",
            "organization_slug": "non-existent-org",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_inactive_organization(client: AsyncClient, async_session):
    """Test login with inactive organization."""
    from src.models.organization import Organization
    from src.models.user import User

    # Create inactive organization
    inactive_org = Organization(
        name="Inactive Org", slug="inactive-org", is_active=False
    )
    async_session.add(inactive_org)
    await async_session.commit()
    await async_session.refresh(inactive_org)

    user = User(
        email="inactive@test.com",
        password=hash_password("TestPass123"),
        email_verified=True,
        organization_id=inactive_org.id,
    )
    async_session.add(user)
    await async_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "inactive@test.com",
            "password": "TestPass123",
            "organization_slug": "inactive-org",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Organization is not active"


@pytest.mark.asyncio
async def test_login_user_in_different_org(
    client: AsyncClient, async_session, test_organization, second_organization
):
    """Test login fails when user exists in different org."""
    from src.models.user import User

    # Create user in second org
    user = User(
        email="difforg@test.com",
        password=hash_password("TestPass123"),
        email_verified=True,
        organization_id=second_organization.id,
    )
    async_session.add(user)
    await async_session.commit()

    # Try to login with first org's slug
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "difforg@test.com",
            "password": "TestPass123",
            "organization_slug": test_organization.slug,
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_invalid_email_format(client: AsyncClient, test_organization):
    """Test login with invalid email format."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "not-an-email",
            "password": "TestPass123",
            "organization_slug": test_organization.slug,
        },
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_login_sso_only_account(
    client: AsyncClient, async_session, test_organization
):
    """Test login fails for SSO-only accounts (null password)."""
    from src.models.user import CreatedVia, User

    # Create SSO-only user (no password)
    sso_user = User(
        email="ssoonly@test.com",
        password=None,  # SSO users have no password
        email_verified=True,
        organization_id=test_organization.id,
        created_via=CreatedVia.GOOGLE,
    )
    async_session.add(sso_user)
    await async_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "ssoonly@test.com",
            "password": "AnyPassword123!",
            "organization_slug": test_organization.slug,
        },
    )

    assert response.status_code == 400
    assert "SSO" in response.json()["detail"]
    assert response.json()["detail_code"] == "auth.sso_only_account"


@pytest.mark.asyncio
async def test_login_missing_fields(client: AsyncClient):
    """Test login with missing required fields."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@test.com"
            # Missing password and organization_slug
        },
    )

    assert response.status_code == 422


# ==================== Refresh Endpoint Tests ====================


@pytest.mark.asyncio
async def test_refresh_success(
    client: AsyncClient, async_session, test_user, test_organization
):
    """Test successful token refresh."""
    org_id = str(test_organization.id)

    # Create a refresh token
    refresh_token = await create_refresh_token(async_session, test_user.id, org_id)

    # Send refresh token as cookie
    client.cookies.set("refresh_token", refresh_token)
    response = await client.post("/api/v1/auth/refresh")
    client.cookies.clear()

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert len(data["access_token"]) > 0


@pytest.mark.asyncio
async def test_refresh_invalid_token(client: AsyncClient):
    """Test refresh with invalid token."""
    client.cookies.set("refresh_token", "invalid-token")
    response = await client.post("/api/v1/auth/refresh")
    client.cookies.clear()

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired refresh token"


@pytest.mark.asyncio
async def test_refresh_no_cookie(client: AsyncClient):
    """Test refresh with no cookie."""
    response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 401
    assert response.json()["detail"] == "No refresh token provided"


@pytest.mark.asyncio
async def test_refresh_deleted_token(
    client: AsyncClient, async_session, test_user, test_organization
):
    """Test refresh with deleted token."""
    from src.crud.refresh_token import delete_refresh_token

    org_id = str(test_organization.id)

    # Create and then delete a refresh token
    refresh_token = await create_refresh_token(async_session, test_user.id, org_id)
    await delete_refresh_token(async_session, refresh_token, org_id)

    client.cookies.set("refresh_token", refresh_token)
    response = await client.post("/api/v1/auth/refresh")
    client.cookies.clear()

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired refresh token"


@pytest.mark.asyncio
async def test_refresh_inactive_organization(client: AsyncClient, async_session):
    """Test refresh when organization becomes inactive."""
    from src.models.organization import Organization
    from src.models.user import User

    # Create organization
    org = Organization(name="Soon Inactive", slug="soon-inactive", is_active=True)
    async_session.add(org)
    await async_session.commit()
    await async_session.refresh(org)

    # Create user
    user = User(
        email="sooninactive@test.com",
        password=hash_password("TestPass123"),
        email_verified=True,
        organization_id=org.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    # Create refresh token
    refresh_token = await create_refresh_token(async_session, user.id, str(org.id))

    # Deactivate organization
    org.is_active = False
    await async_session.commit()

    # Try to refresh
    client.cookies.set("refresh_token", refresh_token)
    response = await client.post("/api/v1/auth/refresh")
    client.cookies.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "Organization is not active"


# ==================== Logout Endpoint Tests ====================


@pytest.mark.asyncio
async def test_logout_success(
    client: AsyncClient, async_session, test_user, test_organization, test_jwt_token
):
    """Test successful logout."""
    org_id = str(test_organization.id)

    # Create a refresh token
    refresh_token = await create_refresh_token(async_session, test_user.id, org_id)

    client.cookies.set("refresh_token", refresh_token)
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": test_jwt_token},
    )
    client.cookies.clear()

    assert response.status_code == 200
    assert response.json()["message"] == "Logged out successfully"

    # Verify token is invalidated
    from src.crud.refresh_token import get_refresh_token

    stored = await get_refresh_token(async_session, refresh_token)
    assert stored is None

    # Verify cookie is cleared
    set_cookie = response.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie
    assert "max-age=0" in set_cookie.lower() or '="";' in set_cookie


@pytest.mark.asyncio
async def test_logout_no_cookie(
    client: AsyncClient, async_session, test_user, test_organization, test_jwt_token
):
    """Test logout without refresh token cookie still succeeds (clears cookie)."""
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": test_jwt_token},
    )

    # Logout succeeds even without a cookie - it just clears any cookie
    assert response.status_code == 200
    assert response.json()["message"] == "Logged out successfully"


@pytest.mark.asyncio
async def test_logout_unauthenticated(
    client: AsyncClient, async_session, test_user, test_organization
):
    """Test logout without authentication."""
    org_id = str(test_organization.id)
    refresh_token = await create_refresh_token(async_session, test_user.id, org_id)

    client.cookies.set("refresh_token", refresh_token)
    response = await client.post("/api/v1/auth/logout")
    client.cookies.clear()

    assert response.status_code == 401


# ==================== Logout All Endpoint Tests ====================


@pytest.mark.asyncio
async def test_logout_all_success(
    client: AsyncClient, async_session, test_user, test_organization, test_jwt_token
):
    """Test logout from all devices."""
    org_id = str(test_organization.id)

    # Create multiple refresh tokens
    token1 = await create_refresh_token(async_session, test_user.id, org_id)
    token2 = await create_refresh_token(async_session, test_user.id, org_id)
    token3 = await create_refresh_token(async_session, test_user.id, org_id)

    response = await client.post(
        "/api/v1/auth/logout/all",
        json={"user_id": str(test_user.id)},
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Logged out from all devices"

    # Verify all tokens are invalidated
    from src.crud.refresh_token import get_refresh_token

    assert await get_refresh_token(async_session, token1) is None
    assert await get_refresh_token(async_session, token2) is None
    assert await get_refresh_token(async_session, token3) is None


@pytest.mark.asyncio
async def test_logout_all_unauthenticated(client: AsyncClient, test_user):
    """Test logout all without authentication."""
    response = await client.post(
        "/api/v1/auth/logout/all", json={"user_id": str(test_user.id)}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_all_preserves_other_users(
    client: AsyncClient,
    async_session,
    test_user,
    test_admin_user,
    test_organization,
    test_jwt_token,
):
    """Test that logout all only affects the specified user."""
    org_id = str(test_organization.id)

    # Create tokens for test_user
    user_token = await create_refresh_token(async_session, test_user.id, org_id)

    # Create tokens for admin_user
    admin_token = await create_refresh_token(async_session, test_admin_user.id, org_id)

    # Logout all for test_user
    response = await client.post(
        "/api/v1/auth/logout/all",
        json={"user_id": str(test_user.id)},
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200

    # Verify test_user's token is gone
    from src.crud.refresh_token import get_refresh_token

    assert await get_refresh_token(async_session, user_token) is None

    # Verify admin's token is still valid
    assert await get_refresh_token(async_session, admin_token) is not None


# ==================== Edge Cases ====================


@pytest.mark.asyncio
async def test_multiple_login_creates_multiple_tokens(
    client: AsyncClient, async_session, test_organization
):
    """Test that logging in multiple times creates multiple refresh tokens."""
    from src.models.user import User

    user = User(
        email="multilogin@test.com",
        password=hash_password("TestPass123"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    # Login multiple times
    cookie_tokens = []
    for _ in range(3):
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "multilogin@test.com",
                "password": "TestPass123",
                "organization_slug": test_organization.slug,
            },
        )
        assert response.status_code == 200
        # Extract refresh token from Set-Cookie header
        set_cookie = response.headers.get("set-cookie", "")
        assert "refresh_token=" in set_cookie
        # Parse token value from cookie header
        token_start = set_cookie.index("refresh_token=") + len("refresh_token=")
        token_end = set_cookie.index(";", token_start)
        cookie_tokens.append(set_cookie[token_start:token_end])

    # All tokens should be unique
    assert len(set(cookie_tokens)) == 3

    # All tokens should be valid
    for token in cookie_tokens:
        from src.crud.refresh_token import get_refresh_token

        stored = await get_refresh_token(async_session, token)
        assert stored is not None


# ==================== Check Email Endpoint Tests ====================


@pytest.mark.asyncio
async def test_check_email_user_with_password(
    client: AsyncClient, async_session, test_organization
):
    """Test check-email returns password auth method for user with password."""
    from src.models.user import User

    user = User(
        email="passworduser@test.com",
        password=hash_password("TestPass123"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()

    response = await client.post(
        "/api/v1/auth/check-email",
        json={
            "email": "passworduser@test.com",
            "organization_slug": test_organization.slug,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is True
    assert "password" in data["auth_methods"]


@pytest.mark.asyncio
async def test_check_email_sso_only_user(
    client: AsyncClient, async_session, test_organization
):
    """Test check-email returns SSO auth method for SSO-only user."""
    from src.crud.user_identity import create as create_identity
    from src.models.user import CreatedVia, User

    # Create SSO-only user (no password)
    user = User(
        email="ssouser@test.com",
        password=None,
        email_verified=True,
        organization_id=test_organization.id,
        created_via=CreatedVia.GOOGLE,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    # Create identity record
    await create_identity(
        async_session,
        user_id=str(user.id),
        provider="google",
        provider_user_id="google-123",
        organization_id=str(test_organization.id),
        provider_email="ssouser@test.com",
    )

    response = await client.post(
        "/api/v1/auth/check-email",
        json={
            "email": "ssouser@test.com",
            "organization_slug": test_organization.slug,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is True
    assert "google" in data["auth_methods"]
    assert "password" not in data["auth_methods"]


@pytest.mark.asyncio
async def test_check_email_user_with_both_methods(
    client: AsyncClient, async_session, test_organization
):
    """Test check-email returns both auth methods for user with password and SSO."""
    from src.crud.user_identity import create as create_identity
    from src.models.user import User

    # Create user with password
    user = User(
        email="bothuser@test.com",
        password=hash_password("TestPass123"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    # Link Google identity
    await create_identity(
        async_session,
        user_id=str(user.id),
        provider="google",
        provider_user_id="google-456",
        organization_id=str(test_organization.id),
        provider_email="bothuser@test.com",
    )

    response = await client.post(
        "/api/v1/auth/check-email",
        json={
            "email": "bothuser@test.com",
            "organization_slug": test_organization.slug,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is True
    assert "password" in data["auth_methods"]
    assert "google" in data["auth_methods"]


@pytest.mark.asyncio
async def test_check_email_nonexistent_user(client: AsyncClient, test_organization):
    """Test check-email returns exists=False for nonexistent user."""
    response = await client.post(
        "/api/v1/auth/check-email",
        json={
            "email": "nonexistent@test.com",
            "organization_slug": test_organization.slug,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is False
    assert data["auth_methods"] == []


@pytest.mark.asyncio
async def test_check_email_invalid_organization(client: AsyncClient):
    """Test check-email returns exists=False for invalid organization."""
    response = await client.post(
        "/api/v1/auth/check-email",
        json={
            "email": "anyone@test.com",
            "organization_slug": "nonexistent-org",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is False
    assert data["auth_methods"] == []
