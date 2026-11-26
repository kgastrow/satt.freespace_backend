"""
API tests for organization SSO settings endpoints.

Tests CRUD operations for SSO settings and tenant isolation.
"""

from httpx import AsyncClient
import pytest

from src.core.security import hash_password
from src.models.organization_sso_settings import OrganizationSSOSettings


# ==================== Get SSO Settings Tests ====================


@pytest.mark.asyncio
async def test_get_sso_settings_success(
    client: AsyncClient,
    async_session,
    test_organization,
    user_with_sso_read,
    user_with_sso_read_token,
):
    """Test successful retrieval of SSO settings with sso:read permission."""
    # Create SSO settings
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=True,
        google_client_id="test-client-id",
        google_client_secret="test-secret",
    )
    async_session.add(sso_settings)
    await async_session.commit()

    response = await client.get(
        "/api/v1/organization-sso-settings",
        headers={"Authorization": user_with_sso_read_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["google_enabled"] is True
    assert data["google_client_id"] == "test-client-id"
    assert "google_client_secret" not in data  # Secret should not be in response


@pytest.mark.asyncio
async def test_get_sso_settings_not_found(
    client: AsyncClient, user_with_sso_read, user_with_sso_read_token
):
    """Test getting SSO settings when they don't exist (with sso:read permission)."""
    response = await client.get(
        "/api/v1/organization-sso-settings",
        headers={"Authorization": user_with_sso_read_token},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "SSO settings not found for this organization"


@pytest.mark.asyncio
async def test_get_sso_settings_forbidden_without_permission(
    client: AsyncClient, test_user, test_jwt_token
):
    """Test that users without sso:read permission cannot view SSO settings."""
    response = await client.get(
        "/api/v1/organization-sso-settings", headers={"Authorization": test_jwt_token}
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_sso_settings_unauthorized(client: AsyncClient):
    """Test getting SSO settings without authentication."""
    response = await client.get("/api/v1/organization-sso-settings")

    assert response.status_code == 401


# ==================== Get Enabled Providers Tests ====================


@pytest.mark.asyncio
async def test_get_enabled_providers_success(
    client: AsyncClient, async_session, test_organization
):
    """Test successful retrieval of enabled providers (public endpoint)."""
    # Create SSO settings with Google enabled
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        sso_allowed=True,  # Must be allowed by super admin
        google_enabled=True,
    )
    async_session.add(sso_settings)
    await async_session.commit()

    response = await client.get(
        "/api/v1/organization-sso-settings/enabled-providers",
        params={"org_slug": test_organization.slug},
    )

    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    assert "google" in data["providers"]


@pytest.mark.asyncio
async def test_get_enabled_providers_none_enabled(
    client: AsyncClient, async_session, test_organization
):
    """Test getting enabled providers when none are enabled (public endpoint)."""
    # Create SSO settings with no providers enabled
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=False,
    )
    async_session.add(sso_settings)
    await async_session.commit()

    response = await client.get(
        "/api/v1/organization-sso-settings/enabled-providers",
        params={"org_slug": test_organization.slug},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["providers"] == []


@pytest.mark.asyncio
async def test_get_enabled_providers_no_settings(
    client: AsyncClient, test_organization
):
    """Test getting enabled providers when settings don't exist (public endpoint)."""
    response = await client.get(
        "/api/v1/organization-sso-settings/enabled-providers",
        params={"org_slug": test_organization.slug},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["providers"] == []


# ==================== Create SSO Settings Tests ====================


@pytest.mark.asyncio
async def test_create_sso_settings_success(
    client: AsyncClient,
    async_session,
    test_organization,
    test_admin_user,
    test_super_admin_token,
):
    """Test successful creation of SSO settings by super admin."""
    response = await client.post(
        "/api/v1/organization-sso-settings",
        json={
            "google_enabled": True,
            "google_client_id": "new-client-id",
            "google_client_secret": "new-secret",
        },
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["google_enabled"] is True
    assert data["google_client_id"] == "new-client-id"


@pytest.mark.asyncio
async def test_create_sso_settings_forbidden_non_admin(
    client: AsyncClient, test_user, test_jwt_token
):
    """Test that regular users cannot create SSO settings."""
    response = await client.post(
        "/api/v1/organization-sso-settings",
        json={
            "google_enabled": True,
            "google_client_id": "test-client-id",
        },
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_sso_settings_already_exists(
    client: AsyncClient,
    async_session,
    test_organization,
    test_admin_user,
    test_super_admin_token,
):
    """Test creating SSO settings when they already exist."""
    # Create existing settings
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=False,
    )
    async_session.add(sso_settings)
    await async_session.commit()

    response = await client.post(
        "/api/v1/organization-sso-settings",
        json={
            "google_enabled": True,
            "google_client_id": "test-client-id",
        },
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code == 400
    assert "already exist" in response.json()["detail"]


# ==================== Update SSO Settings Tests ====================


@pytest.mark.asyncio
async def test_update_sso_settings_success(
    client: AsyncClient,
    async_session,
    test_organization,
    test_admin_user,
    test_super_admin_token,
):
    """Test successful update of SSO settings by super admin."""
    # Create existing settings
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=False,
        google_client_id="old-client-id",
    )
    async_session.add(sso_settings)
    await async_session.commit()

    response = await client.put(
        "/api/v1/organization-sso-settings",
        json={
            "google_enabled": True,
            "google_client_id": "updated-client-id",
        },
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["google_enabled"] is True
    assert data["google_client_id"] == "updated-client-id"


@pytest.mark.asyncio
async def test_update_sso_settings_partial(
    client: AsyncClient,
    async_session,
    test_organization,
    test_admin_user,
    test_super_admin_token,
):
    """Test partial update of SSO settings."""
    # Create existing settings
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=False,
        google_client_id="original-id",
        google_client_secret="original-secret",
    )
    async_session.add(sso_settings)
    await async_session.commit()

    # Update only google_enabled
    response = await client.put(
        "/api/v1/organization-sso-settings",
        json={
            "google_enabled": True,
        },
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["google_enabled"] is True
    assert data["google_client_id"] == "original-id"  # Should remain unchanged


@pytest.mark.asyncio
async def test_update_sso_settings_forbidden_non_admin(
    client: AsyncClient, async_session, test_organization, test_user, test_jwt_token
):
    """Test that regular users cannot update SSO settings."""
    # Create existing settings
    sso_settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=False,
    )
    async_session.add(sso_settings)
    await async_session.commit()

    response = await client.put(
        "/api/v1/organization-sso-settings",
        json={
            "google_enabled": True,
        },
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_sso_settings_not_found(
    client: AsyncClient, test_admin_user, test_super_admin_token
):
    """Test updating SSO settings when they don't exist."""
    response = await client.put(
        "/api/v1/organization-sso-settings",
        json={
            "google_enabled": True,
        },
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ==================== Multi-Tenancy Isolation Tests ====================


@pytest.mark.asyncio
async def test_sso_settings_tenant_isolation(
    client: AsyncClient, async_session, test_organization
):
    """Test that SSO settings are properly isolated by tenant."""
    from src.models.organization import Organization
    from src.models.permission import Permission
    from src.models.role import Role
    from src.models.role_permission import RolePermission
    from src.models.user import User
    from src.models.user_role import UserRole

    # Create second organization
    org2 = Organization(name="Org 2", slug="org2", is_active=True)
    async_session.add(org2)
    await async_session.commit()
    await async_session.refresh(org2)

    # Create user in org2
    user2 = User(
        email="user2@test.com",
        password=hash_password("password123"),
        email_verified=True,
        organization_id=org2.id,
    )
    async_session.add(user2)
    await async_session.commit()
    await async_session.refresh(user2)

    # Create sso:read permission and role for user2
    sso_read_perm = Permission(
        code="sso:read",
        name="View SSO Settings",
        description="View SSO configuration",
        resource="sso",
        action="read",
        display_order=0,
    )
    async_session.add(sso_read_perm)
    await async_session.commit()
    await async_session.refresh(sso_read_perm)

    viewer_role = Role(name="viewer_org2", description="Viewer role for org2")
    async_session.add(viewer_role)
    await async_session.commit()
    await async_session.refresh(viewer_role)

    # Grant sso:read to viewer role
    role_perm = RolePermission(
        role_id=viewer_role.id,
        permission_id=sso_read_perm.id,
        granted_by=user2.id,
    )
    async_session.add(role_perm)

    # Assign viewer role to user2
    user_role = UserRole(
        user_id=user2.id,
        role_id=viewer_role.id,
        organization_id=org2.id,
    )
    async_session.add(user_role)

    # Create SSO settings for test_organization
    sso_settings1 = OrganizationSSOSettings(
        organization_id=test_organization.id,
        google_enabled=True,
        google_client_id="org1-client-id",
    )
    async_session.add(sso_settings1)

    # Create SSO settings for org2
    sso_settings2 = OrganizationSSOSettings(
        organization_id=org2.id,
        google_enabled=False,
        google_client_id="org2-client-id",
    )
    async_session.add(sso_settings2)
    await async_session.commit()

    # Login as user2
    from datetime import datetime, timedelta, timezone

    import jwt

    from src.core.config import settings

    access_token = jwt.encode(
        {
            "user_id": str(user2.id),
            "organization_id": str(org2.id),
            "exp": datetime.now(timezone.utc) + timedelta(seconds=3600),
            "type": "access",
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )

    headers = {"Authorization": f"Bearer {access_token}"}

    # Get SSO settings as user2
    response = await client.get("/api/v1/organization-sso-settings", headers=headers)

    assert response.status_code == 200
    data = response.json()
    # Should get org2's settings, not org1's
    assert data["google_enabled"] is False
    assert data["google_client_id"] == "org2-client-id"


@pytest.mark.asyncio
async def test_get_enabled_providers_tenant_isolation(
    client: AsyncClient, async_session, test_organization
):
    """Test that enabled providers are properly isolated by tenant (public endpoint)."""
    from src.models.organization import Organization

    # Create second organization
    org2 = Organization(name="Org 2", slug="org2-providers", is_active=True)
    async_session.add(org2)
    await async_session.commit()
    await async_session.refresh(org2)

    # Create SSO settings for test_organization (Google enabled)
    sso_settings1 = OrganizationSSOSettings(
        organization_id=test_organization.id,
        sso_allowed=True,  # SSO is allowed
        google_enabled=True,
    )
    async_session.add(sso_settings1)

    # Create SSO settings for org2 (SSO allowed but Google disabled)
    sso_settings2 = OrganizationSSOSettings(
        organization_id=org2.id,
        sso_allowed=True,  # SSO is allowed
        google_enabled=False,
    )
    async_session.add(sso_settings2)
    await async_session.commit()

    # Get enabled providers for org2 - should be empty (google_enabled=False)
    response = await client.get(
        "/api/v1/organization-sso-settings/enabled-providers",
        params={"org_slug": org2.slug},
    )

    assert response.status_code == 200
    data = response.json()
    # Should get org2's providers (none), not org1's
    assert data["providers"] == []

    # Get enabled providers for test_organization - should have google
    response = await client.get(
        "/api/v1/organization-sso-settings/enabled-providers",
        params={"org_slug": test_organization.slug},
    )

    assert response.status_code == 200
    data = response.json()
    assert "google" in data["providers"]
