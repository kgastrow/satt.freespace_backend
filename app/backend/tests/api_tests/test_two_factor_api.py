"""
API tests for Two-Factor Authentication endpoints.
Tests API endpoint behavior, permissions, tenant isolation, and error handling.
"""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import OrganizationTwoFactorSettings, TwoFactorPolicy, UserTwoFactor


# ============================================================================
# ORGANIZATION 2FA SETTINGS - GET TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_organization_2fa_settings_with_permission(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    user_with_permission,
    user_with_permission_token,
):
    """Test GET /api/organization-two-factor-settings with valid permission (two_factor:read)."""
    # Create 2FA settings for the organization
    settings = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=True,
        two_factor_policy=TwoFactorPolicy.OPTIONAL.value,
        grace_period_days=7,
    )
    async_session.add(settings)
    await async_session.commit()

    # Mock permission check to grant two_factor:read
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["two_factor:read"])

        response = await client.get(
            "/api/v1/organization-two-factor-settings/",
            headers={"Authorization": user_with_permission_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["two_factor_allowed"] is True
    assert data["two_factor_policy"] == TwoFactorPolicy.OPTIONAL.value
    assert data["grace_period_days"] == 7


@pytest.mark.asyncio
async def test_get_organization_2fa_settings_without_permission(
    client: AsyncClient,
    test_user,
    test_jwt_token,
):
    """Test GET /api/organization-two-factor-settings without permission returns 403."""
    # Mock permission check to deny two_factor:read
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=[])

        response = await client.get(
            "/api/v1/organization-two-factor-settings/",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 403
    assert "Permission" in response.json().get("detail", "")


@pytest.mark.asyncio
async def test_get_organization_2fa_settings_auto_creates_defaults(
    client: AsyncClient,
    user_with_permission,
    user_with_permission_token,
):
    """Test GET /api/organization-two-factor-settings auto-creates default settings if none exist."""
    # Don't create settings - endpoint should auto-create default settings

    # Mock permission check to grant two_factor:read
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["two_factor:read"])

        response = await client.get(
            "/api/v1/organization-two-factor-settings/",
            headers={"Authorization": user_with_permission_token},
        )

    # Should auto-create default settings and return 200
    assert response.status_code == 200
    data = response.json()
    # Verify default values
    assert data["two_factor_allowed"] is False
    assert data["two_factor_policy"] == "disabled"
    assert data["grace_period_days"] == 7


@pytest.mark.asyncio
async def test_super_admin_can_get_organization_2fa_settings(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    test_admin_user,
    test_super_admin_token,
):
    """Test that super admin can access organization 2FA settings without permission."""
    # Create 2FA settings
    settings = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=True,
        two_factor_policy=TwoFactorPolicy.MANDATORY.value,
    )
    async_session.add(settings)
    await async_session.commit()

    response = await client.get(
        "/api/v1/organization-two-factor-settings/",
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["two_factor_allowed"] is True
    assert data["two_factor_policy"] == TwoFactorPolicy.MANDATORY.value


# ============================================================================
# ORGANIZATION 2FA SETTINGS - PUT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_update_organization_2fa_settings_with_permission(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    user_with_permission,
    user_with_permission_token,
):
    """Test PUT /api/organization-two-factor-settings with valid permission (two_factor:write)."""
    # Create 2FA settings with 2FA allowed
    settings = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=True,
        two_factor_policy=TwoFactorPolicy.OPTIONAL.value,
        grace_period_days=7,
    )
    async_session.add(settings)
    await async_session.commit()

    update_data = {
        "two_factor_policy": TwoFactorPolicy.MANDATORY.value,
        "grace_period_days": 14,
    }

    # Mock permission check to grant two_factor:write
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["two_factor:write"])

        response = await client.put(
            "/api/v1/organization-two-factor-settings/",
            json=update_data,
            headers={"Authorization": user_with_permission_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["two_factor_policy"] == TwoFactorPolicy.MANDATORY.value
    assert data["grace_period_days"] == 14
    assert (
        data["enforcement_start_time"] is not None
    )  # Should be set when changing to MANDATORY


@pytest.mark.asyncio
async def test_update_organization_2fa_settings_without_permission(
    client: AsyncClient,
    test_user,
    test_jwt_token,
):
    """Test PUT /api/organization-two-factor-settings without permission returns 403."""
    update_data = {"two_factor_policy": TwoFactorPolicy.MANDATORY.value}

    # Mock permission check to deny two_factor:write
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=[])

        response = await client.put(
            "/api/v1/organization-two-factor-settings/",
            json=update_data,
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 403
    assert "Permission" in response.json().get("detail", "")


@pytest.mark.asyncio
async def test_update_organization_2fa_settings_when_not_allowed(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    user_with_permission,
    user_with_permission_token,
):
    """Test PUT /api/organization-two-factor-settings when 2FA not allowed returns 403."""
    # Create 2FA settings with two_factor_allowed=False
    settings = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=False,
        two_factor_policy=TwoFactorPolicy.DISABLED.value,
    )
    async_session.add(settings)
    await async_session.commit()

    update_data = {"two_factor_policy": TwoFactorPolicy.OPTIONAL.value}

    # Mock permission check to grant two_factor:write
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["two_factor:write"])

        response = await client.put(
            "/api/v1/organization-two-factor-settings/",
            json=update_data,
            headers={"Authorization": user_with_permission_token},
        )

    assert response.status_code == 403
    assert "not allowed" in response.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_update_organization_2fa_settings_not_found(
    client: AsyncClient,
    user_with_permission,
    user_with_permission_token,
):
    """Test PUT /api/organization-two-factor-settings when settings don't exist returns 404."""
    # Don't create settings - endpoint should return 404
    update_data = {"two_factor_policy": TwoFactorPolicy.OPTIONAL.value}

    # Mock permission check to grant two_factor:write
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["two_factor:write"])

        response = await client.put(
            "/api/v1/organization-two-factor-settings/",
            json=update_data,
            headers={"Authorization": user_with_permission_token},
        )

    assert response.status_code == 404
    assert "not found" in response.json().get("detail", "").lower()


# ============================================================================
# SUPER ADMIN ORGANIZATION ALLOW/DISALLOW TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_super_admin_enable_2fa_for_organization(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    test_admin_user,
    test_super_admin_token,
):
    """Test super admin enabling 2FA (two_factor_allowed=True) for an organization."""
    response = await client.put(
        f"/api/v1/organization-two-factor-settings/organization/{test_organization.id}/allow",
        json={"two_factor_allowed": True},
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["two_factor_allowed"] is True
    assert str(data["organization_id"]) == str(test_organization.id)


@pytest.mark.asyncio
async def test_super_admin_disable_2fa_for_organization(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    test_admin_user,
    test_super_admin_token,
):
    """Test super admin disabling 2FA (two_factor_allowed=False) for an organization."""
    # First enable it
    settings = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=True,
        two_factor_policy=TwoFactorPolicy.OPTIONAL.value,
    )
    async_session.add(settings)
    await async_session.commit()

    # Now disable it
    response = await client.put(
        f"/api/v1/organization-two-factor-settings/organization/{test_organization.id}/allow",
        json={"two_factor_allowed": False},
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["two_factor_allowed"] is False


@pytest.mark.asyncio
async def test_non_super_admin_cannot_update_organization_allow(
    client: AsyncClient,
    test_organization,
    user_with_permission,
    user_with_permission_token,
):
    """Test that non-super-admin cannot access organization allow endpoint."""
    response = await client.put(
        f"/api/v1/organization-two-factor-settings/organization/{test_organization.id}/allow",
        json={"two_factor_allowed": True},
        headers={"Authorization": user_with_permission_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_update_organization_allow_invalid_org_id(
    client: AsyncClient,
    test_admin_user,
    test_super_admin_token,
):
    """Test super admin endpoint with invalid organization_id returns 400."""
    invalid_org_id = "not-a-uuid"

    response = await client.put(
        f"/api/v1/organization-two-factor-settings/organization/{invalid_org_id}/allow",
        json={"two_factor_allowed": True},
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code == 400


# ============================================================================
# USER 2FA SETUP - GET TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_2fa_setup_when_allowed(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    test_user,
    test_jwt_token,
):
    """Test POST /api/two-factor/setup when 2FA is allowed for organization."""
    # Create settings with 2FA allowed
    settings = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=True,
        two_factor_policy=TwoFactorPolicy.OPTIONAL.value,
    )
    async_session.add(settings)
    await async_session.commit()

    response = await client.post(
        "/api/v1/two-factor/setup",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "secret" in data
    assert "provisioning_uri" in data
    assert "qr_code_data" in data


@pytest.mark.asyncio
async def test_get_2fa_setup_when_not_allowed(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    test_user,
    test_jwt_token,
):
    """Test POST /api/two-factor/setup when 2FA is not allowed returns 403."""
    # Create settings with 2FA not allowed
    settings = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=False,
        two_factor_policy=TwoFactorPolicy.DISABLED.value,
    )
    async_session.add(settings)
    await async_session.commit()

    response = await client.post(
        "/api/v1/two-factor/setup",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403
    assert "not enabled" in response.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_get_2fa_setup_when_already_enabled(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    test_user,
    test_jwt_token,
):
    """Test POST /api/two-factor/setup when user already has 2FA enabled returns 400."""
    # Create settings with 2FA allowed
    settings = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=True,
        two_factor_policy=TwoFactorPolicy.OPTIONAL.value,
    )
    async_session.add(settings)
    await async_session.commit()

    # Create user 2FA record
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="EXISTINGSECRET",
        is_enabled=True,
    )
    async_session.add(user_2fa)
    await async_session.commit()

    response = await client.post(
        "/api/v1/two-factor/setup",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 400
    assert "already set up" in response.json().get("detail", "").lower()


# ============================================================================
# USER 2FA SETUP - DELETE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_delete_2fa_setup(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    test_user,
    test_jwt_token,
):
    """Test DELETE /api/two-factor/setup to disable user 2FA."""
    # Create user 2FA record
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="TESTSECRET",
        is_enabled=True,
    )
    async_session.add(user_2fa)
    await async_session.commit()

    response = await client.request(
        method="DELETE",
        url="/api/v1/two-factor/setup",
        headers={"Authorization": test_jwt_token},
        json={"password": "Password123!"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "disabled" in data.get("message", "").lower()


@pytest.mark.asyncio
async def test_delete_2fa_setup_when_not_enabled(
    client: AsyncClient,
    test_user,
    test_jwt_token,
):
    """Test DELETE /api/two-factor/setup when user doesn't have 2FA returns 404."""
    # Don't create user 2FA record

    response = await client.request(
        method="DELETE",
        url="/api/v1/two-factor/setup",
        headers={"Authorization": test_jwt_token},
        json={"password": "Password123!"},
    )

    assert response.status_code == 404


# ============================================================================
# USER 2FA STATUS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_2fa_status_when_enabled(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    test_user,
    test_jwt_token,
):
    """Test GET /api/two-factor/status when user has 2FA enabled."""
    from datetime import datetime, timezone

    verified_time = datetime.now(timezone.utc)

    # Create user 2FA record
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="TESTSECRET",
        is_enabled=True,
        verified_at=verified_time,
    )
    async_session.add(user_2fa)
    await async_session.commit()

    response = await client.get(
        "/api/v1/two-factor/status",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_enabled"] is True
    assert data["verified_at"] is not None


@pytest.mark.asyncio
async def test_get_2fa_status_when_not_enabled(
    client: AsyncClient,
    test_user,
    test_jwt_token,
):
    """Test GET /api/two-factor/status when user doesn't have 2FA enabled."""
    # Don't create user 2FA record

    response = await client.get(
        "/api/v1/two-factor/status",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_enabled"] is False
    assert data["verified_at"] is None


@pytest.mark.asyncio
async def test_get_2fa_status_returns_correct_values(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    test_user,
    test_jwt_token,
):
    """Test GET /api/two-factor/status returns correct is_enabled and verified_at values."""
    from datetime import datetime, timezone

    verified_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    # Create user 2FA record with specific values
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="SPECIFICSECRET",
        is_enabled=True,
        verified_at=verified_time,
    )
    async_session.add(user_2fa)
    await async_session.commit()

    response = await client.get(
        "/api/v1/two-factor/status",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_enabled"] is True
    # Verify the timestamp is returned (exact format may vary)
    assert data["verified_at"] is not None
    assert "2024-01-15" in data["verified_at"]


# ============================================================================
# TENANT ISOLATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_org_admin_cannot_access_other_org_2fa_settings(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    second_organization,
    user_with_permission,
    user_with_permission_token,
):
    """Test that org admin from org1 cannot access org2's 2FA settings."""
    # Create 2FA settings for second organization with specific values
    settings = OrganizationTwoFactorSettings(
        organization_id=second_organization.id,
        two_factor_allowed=True,
        two_factor_policy=TwoFactorPolicy.MANDATORY.value,
    )
    async_session.add(settings)
    await async_session.commit()

    # user_with_permission belongs to test_organization, trying to access their settings
    # should not return second_organization's settings
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["two_factor:read"])

        response = await client.get(
            "/api/v1/organization-two-factor-settings/",
            headers={"Authorization": user_with_permission_token},
        )

    # Should return 200 with auto-created default settings for user's own org (test_organization)
    # NOT the second_organization's settings (which has two_factor_allowed=True, policy=MANDATORY)
    assert response.status_code == 200
    data = response.json()
    # Verify we got default settings for test_organization, not second_organization's settings
    assert data["two_factor_allowed"] is False  # Not True (second_org's value)
    assert (
        data["two_factor_policy"] == "disabled"
    )  # Not "mandatory" (second_org's value)


@pytest.mark.asyncio
async def test_user_cannot_see_other_org_user_2fa_status(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    second_organization,
    test_user,
    test_jwt_token,
    second_org_user,
):
    """Test that user from org1 cannot see user from org2's 2FA status."""
    # Create 2FA for user in second organization
    user_2fa = UserTwoFactor(
        user_id=second_org_user.id,
        organization_id=second_organization.id,
        secret="OTHERSECRET",
        is_enabled=True,
    )
    async_session.add(user_2fa)
    await async_session.commit()

    # test_user from test_organization should only see their own status (not enabled)
    response = await client.get(
        "/api/v1/two-factor/status",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_enabled"] is False  # test_user has no 2FA


@pytest.mark.asyncio
async def test_super_admin_can_access_any_organization_via_allow_endpoint(
    client: AsyncClient,
    async_session: AsyncSession,
    second_organization,
    test_admin_user,
    test_super_admin_token,
):
    """Test that super admin can access any organization's settings via allow endpoint."""
    # Super admin enabling 2FA for second_organization
    response = await client.put(
        f"/api/v1/organization-two-factor-settings/organization/{second_organization.id}/allow",
        json={"two_factor_allowed": True},
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert str(data["organization_id"]) == str(second_organization.id)
    assert data["two_factor_allowed"] is True


@pytest.mark.asyncio
async def test_2fa_settings_filtered_by_organization_id(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    second_organization,
    user_with_permission,
    user_with_permission_token,
):
    """Test that 2FA settings are properly filtered by organization_id."""
    # Create settings for both organizations
    settings1 = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=True,
        two_factor_policy=TwoFactorPolicy.OPTIONAL.value,
    )
    settings2 = OrganizationTwoFactorSettings(
        organization_id=second_organization.id,
        two_factor_allowed=False,
        two_factor_policy=TwoFactorPolicy.DISABLED.value,
    )
    async_session.add(settings1)
    async_session.add(settings2)
    await async_session.commit()

    # user_with_permission belongs to test_organization
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["two_factor:read"])

        response = await client.get(
            "/api/v1/organization-two-factor-settings/",
            headers={"Authorization": user_with_permission_token},
        )

    assert response.status_code == 200
    data = response.json()
    # Should only see test_organization's settings
    assert data["two_factor_allowed"] is True
    assert data["two_factor_policy"] == TwoFactorPolicy.OPTIONAL.value


# ============================================================================
# VERIFY 2FA SETUP AND BACKUP CODES TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_verify_2fa_setup_requires_secret_and_code(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    test_user,
    test_jwt_token,
):
    """Test POST /api/two-factor/verify-setup requires secret and code."""
    # Create settings with 2FA allowed
    settings = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=True,
        two_factor_policy=TwoFactorPolicy.OPTIONAL.value,
    )
    async_session.add(settings)
    await async_session.commit()

    # Missing required fields should fail with 422
    response = await client.post(
        "/api/v1/two-factor/verify-setup",
        json={"code": "123456"},  # Missing secret
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_backup_codes_info_requires_2fa(
    client: AsyncClient,
    test_user,
    test_jwt_token,
):
    """Test GET /api/two-factor/backup-codes returns 404 when 2FA not set up."""
    response = await client.get(
        "/api/v1/two-factor/backup-codes",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 404
    assert "not set up" in response.json().get("detail", "").lower()


# ============================================================================
# USERS WITHOUT 2FA ENDPOINT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_users_without_2fa_with_permission(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    test_user,
    user_with_permission,
    user_with_permission_token,
):
    """Test GET /api/two-factor/users-without-2fa with valid permission (two_factor:read)."""
    # Mock permission check to grant two_factor:read
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["two_factor:read"])

        response = await client.get(
            "/api/v1/two-factor/users-without-2fa",
            headers={"Authorization": user_with_permission_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert "users" in data
    assert "total" in data
    assert isinstance(data["users"], list)
    assert data["total"] >= 0


@pytest.mark.asyncio
async def test_get_users_without_2fa_without_permission(
    client: AsyncClient,
    test_user,
    test_jwt_token,
):
    """Test GET /api/two-factor/users-without-2fa without permission returns 403."""
    # Mock permission check to deny two_factor:read
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=[])

        response = await client.get(
            "/api/v1/two-factor/users-without-2fa",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 403
    assert "Permission" in response.json().get("detail", "")


@pytest.mark.asyncio
async def test_get_users_without_2fa_super_admin(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    test_user,
    test_admin_user,
    test_super_admin_token,
):
    """Test that super admin can access users-without-2fa endpoint."""
    response = await client.get(
        "/api/v1/two-factor/users-without-2fa",
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "users" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_get_users_without_2fa_excludes_users_with_2fa(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    test_user,
    user_with_permission,
    user_with_permission_token,
):
    """Test that users with 2FA enabled are excluded from the response."""
    # Create 2FA record for test_user (enabled)
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="TESTSECRET",
        is_enabled=True,
    )
    async_session.add(user_2fa)
    await async_session.commit()

    # Mock permission check to grant two_factor:read
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["two_factor:read"])

        response = await client.get(
            "/api/v1/two-factor/users-without-2fa",
            headers={"Authorization": user_with_permission_token},
        )

    assert response.status_code == 200
    data = response.json()
    # test_user should NOT be in the list since they have 2FA enabled
    user_ids = [user["id"] for user in data["users"]]
    assert str(test_user.id) not in user_ids


@pytest.mark.asyncio
async def test_get_users_without_2fa_includes_users_without_2fa(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    test_user,
    user_with_permission,
    user_with_permission_token,
):
    """Test that users without 2FA are included in the response."""
    # Don't create any 2FA record for test_user

    # Mock permission check to grant two_factor:read
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["two_factor:read"])

        response = await client.get(
            "/api/v1/two-factor/users-without-2fa",
            headers={"Authorization": user_with_permission_token},
        )

    assert response.status_code == 200
    data = response.json()
    # test_user should be in the list since they don't have 2FA
    user_ids = [user["id"] for user in data["users"]]
    assert str(test_user.id) in user_ids


@pytest.mark.asyncio
async def test_get_users_without_2fa_response_format(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    test_user,
    user_with_permission,
    user_with_permission_token,
):
    """Test that the response includes correct user fields."""
    # Mock permission check to grant two_factor:read
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["two_factor:read"])

        response = await client.get(
            "/api/v1/two-factor/users-without-2fa",
            headers={"Authorization": user_with_permission_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == len(data["users"])

    # Check that at least one user has the expected fields
    if data["users"]:
        user = data["users"][0]
        assert "id" in user
        assert "email" in user
        assert "first_name" in user
        assert "last_name" in user


@pytest.mark.asyncio
async def test_get_users_without_2fa_tenant_isolation(
    client: AsyncClient,
    async_session: AsyncSession,
    test_organization,
    second_organization,
    test_user,
    second_org_user,
    user_with_permission,
    user_with_permission_token,
):
    """Test that users from other organizations are not included."""
    # Both users don't have 2FA, but only test_user should be visible to user_with_permission

    # Mock permission check to grant two_factor:read
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["two_factor:read"])

        response = await client.get(
            "/api/v1/two-factor/users-without-2fa",
            headers={"Authorization": user_with_permission_token},
        )

    assert response.status_code == 200
    data = response.json()

    # Get all user IDs in the response
    user_ids = [user["id"] for user in data["users"]]

    # second_org_user should NOT be in the list (different organization)
    assert str(second_org_user.id) not in user_ids
