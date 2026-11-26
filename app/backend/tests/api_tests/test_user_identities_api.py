"""
API tests for user identities (connected accounts) endpoints.

Tests verify:
- List connected accounts
- Unlink account (simple flow)
- Unlink with setup (password + optional 2FA)
- Cannot unlink last auth method
- Tenant isolation
"""

from httpx import AsyncClient
import pytest

from src.models.user_identity import UserIdentity


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def test_user_identity(async_session, test_organization, test_user):
    """Create a connected identity for test user."""
    identity = UserIdentity(
        user_id=test_user.id,
        organization_id=test_organization.id,
        provider="google",
        provider_user_id="google_123456",
        provider_email=test_user.email,
    )
    async_session.add(identity)
    await async_session.commit()
    await async_session.refresh(identity)
    return identity


@pytest.fixture
async def second_user_identity(async_session, test_organization, test_user):
    """Create a second connected identity for test user."""
    identity = UserIdentity(
        user_id=test_user.id,
        organization_id=test_organization.id,
        provider="github",
        provider_user_id="github_789",
        provider_email=test_user.email,
    )
    async_session.add(identity)
    await async_session.commit()
    await async_session.refresh(identity)
    return identity


@pytest.fixture
async def other_user_identity(async_session, test_organization, test_admin_user):
    """Create an identity for another user."""
    identity = UserIdentity(
        user_id=test_admin_user.id,
        organization_id=test_organization.id,
        provider="google",
        provider_user_id="google_admin_999",
        provider_email=test_admin_user.email,
    )
    async_session.add(identity)
    await async_session.commit()
    await async_session.refresh(identity)
    return identity


@pytest.fixture
async def sso_only_user(async_session, test_organization):
    """Create a user without password (SSO-only)."""
    from src.models.user import CreatedVia, User

    user = User(
        email="ssoonly@test.com",
        password=None,  # No password - SSO only
        email_verified=True,
        organization_id=test_organization.id,
        created_via=CreatedVia.GOOGLE,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def sso_only_user_identity(async_session, test_organization, sso_only_user):
    """Create a Google identity for SSO-only user."""
    identity = UserIdentity(
        user_id=sso_only_user.id,
        organization_id=test_organization.id,
        provider="google",
        provider_user_id="google_sso_only_user",
        provider_email=sso_only_user.email,
    )
    async_session.add(identity)
    await async_session.commit()
    await async_session.refresh(identity)
    return identity


@pytest.fixture
def sso_only_user_token(sso_only_user, test_organization) -> str:
    """Create a JWT token for SSO-only user."""
    from src.core.security import create_access_token

    token = create_access_token(
        user_id=str(sso_only_user.id), organization_id=str(test_organization.id)
    )
    return f"Bearer {token}"


# ============================================================================
# List Identities Tests
# ============================================================================


class TestListIdentities:
    """Tests for GET /api/v1/user/me/identities endpoint."""

    @pytest.mark.asyncio
    async def test_list_identities_requires_auth(self, client: AsyncClient):
        """Test that listing identities requires authentication."""
        response = await client.get("/api/v1/user/me/identities")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_identities_success(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_user_identity,
    ):
        """Test listing connected accounts."""
        response = await client.get(
            "/api/v1/user/me/identities",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "identities" in data
        assert "has_password" in data
        assert "created_via" in data
        assert len(data["identities"]) >= 1

    @pytest.mark.asyncio
    async def test_list_identities_shows_metadata(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_user_identity,
    ):
        """Test that identities include metadata."""
        response = await client.get(
            "/api/v1/user/me/identities",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_password"] is True  # test_user has password
        # Check identity structure
        identity = data["identities"][0]
        assert "id" in identity
        assert "provider" in identity
        assert "provider_email" in identity
        assert "linked_at" in identity
        assert "can_unlink" in identity

    @pytest.mark.asyncio
    async def test_list_identities_empty(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test listing identities when none exist."""
        response = await client.get(
            "/api/v1/user/me/identities",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "identities" in data
        # No identities linked yet
        assert len(data["identities"]) == 0

    @pytest.mark.asyncio
    async def test_list_identities_multiple(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_user_identity,
        second_user_identity,
    ):
        """Test listing multiple identities."""
        response = await client.get(
            "/api/v1/user/me/identities",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["identities"]) == 2
        providers = [i["provider"] for i in data["identities"]]
        assert "google" in providers
        assert "github" in providers


# ============================================================================
# Unlink Identity Tests (Simple Flow)
# ============================================================================


class TestUnlinkIdentity:
    """Tests for DELETE /api/v1/user/me/identities/{provider} endpoint."""

    @pytest.mark.asyncio
    async def test_unlink_identity_requires_auth(self, client: AsyncClient):
        """Test that unlinking requires authentication."""
        response = await client.delete("/api/v1/user/me/identities/google")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unlink_identity_success(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_user_identity,
    ):
        """Test successfully unlinking an identity."""
        # User has password so can unlink
        response = await client.delete(
            "/api/v1/user/me/identities/google",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "unlinked" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_unlink_identity_not_found(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test unlinking non-existent identity."""
        response = await client.delete(
            "/api/v1/user/me/identities/nonexistent",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_unlink_requires_password(
        self,
        client: AsyncClient,
        sso_only_user_token,
        sso_only_user_identity,
    ):
        """Test that SSO-only users cannot use simple unlink."""
        response = await client.delete(
            "/api/v1/user/me/identities/google",
            headers={"Authorization": sso_only_user_token},
        )
        assert response.status_code == 400
        data = response.json()
        assert "password" in data["detail"].lower()


# ============================================================================
# Unlink with Setup Tests
# ============================================================================


class TestUnlinkIdentityWithSetup:
    """Tests for POST /api/v1/user/me/identities/{provider}/unlink-with-setup endpoint."""

    @pytest.mark.asyncio
    async def test_unlink_with_setup_requires_auth(self, client: AsyncClient):
        """Test that unlink with setup requires authentication."""
        response = await client.post(
            "/api/v1/user/me/identities/google/unlink-with-setup",
            json={"new_password": "NewPassword123!"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unlink_with_setup_success(
        self,
        client: AsyncClient,
        sso_only_user_token,
        sso_only_user_identity,
    ):
        """Test unlinking with password setup."""
        response = await client.post(
            "/api/v1/user/me/identities/google/unlink-with-setup",
            json={"new_password": "NewSecurePassword123!"},
            headers={"Authorization": sso_only_user_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "unlinked" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_unlink_with_setup_identity_not_found(
        self,
        client: AsyncClient,
        sso_only_user_token,
    ):
        """Test unlink with setup for non-existent identity."""
        response = await client.post(
            "/api/v1/user/me/identities/nonexistent/unlink-with-setup",
            json={"new_password": "NewPassword123!"},
            headers={"Authorization": sso_only_user_token},
        )
        assert response.status_code == 404


# ============================================================================
# Cannot Unlink Last Auth Method Tests
# ============================================================================


class TestCannotUnlinkLastAuthMethod:
    """Tests verifying users cannot remove their last authentication method."""

    @pytest.mark.asyncio
    async def test_cannot_unlink_only_identity_without_password(
        self,
        client: AsyncClient,
        sso_only_user_token,
        sso_only_user_identity,
    ):
        """Test that SSO-only user cannot simple-unlink their only identity."""
        response = await client.delete(
            "/api/v1/user/me/identities/google",
            headers={"Authorization": sso_only_user_token},
        )
        # Should fail because it's the last auth method and no password
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_can_unlink_reports_correctly(
        self,
        client: AsyncClient,
        sso_only_user_token,
        sso_only_user_identity,
    ):
        """Test that can_unlink is reported correctly for SSO-only user."""
        response = await client.get(
            "/api/v1/user/me/identities",
            headers={"Authorization": sso_only_user_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["requires_setup_for_unlink"] is True
        # Single identity without password should show can_unlink=False
        # (since unlinking would leave no auth method)
        identity = data["identities"][0]
        assert identity["can_unlink"] is False


# ============================================================================
# Access Control Tests
# ============================================================================


class TestIdentityAccessControl:
    """Tests for identity access controls."""

    @pytest.mark.asyncio
    async def test_cannot_see_other_user_identities(
        self,
        client: AsyncClient,
        test_jwt_token,
        other_user_identity,
    ):
        """Test that users cannot see other users' identities."""
        response = await client.get(
            "/api/v1/user/me/identities",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        identity_ids = [i["id"] for i in data["identities"]]
        # Other user's identity should not be visible
        assert str(other_user_identity.id) not in identity_ids

    @pytest.mark.asyncio
    async def test_cannot_unlink_other_user_identity(
        self,
        client: AsyncClient,
        test_jwt_token,
        other_user_identity,
    ):
        """Test that users cannot unlink other users' identities."""
        # Try to unlink using the provider name (the actual endpoint)
        # This should fail because the identity belongs to another user
        response = await client.delete(
            f"/api/v1/user/me/identities/{other_user_identity.provider}",
            headers={"Authorization": test_jwt_token},
        )
        # Should not find an identity with that provider for the current user
        assert response.status_code == 404


# ============================================================================
# Tenant Isolation Tests
# ============================================================================


class TestIdentityTenantIsolation:
    """Tests to ensure identities are properly isolated between organizations."""

    @pytest.mark.asyncio
    async def test_identities_isolated_by_organization(
        self,
        client: AsyncClient,
        async_session,
        test_jwt_token,
        second_organization,
        test_user,
    ):
        """Test that identities from other organizations are not visible."""
        # Create an identity in the second organization
        # (hypothetically, if user had access to multiple orgs)
        other_org_identity = UserIdentity(
            user_id=test_user.id,
            organization_id=second_organization.id,
            provider="microsoft",
            provider_user_id="microsoft_other_org",
            provider_email=test_user.email,
        )
        async_session.add(other_org_identity)
        await async_session.commit()
        await async_session.refresh(other_org_identity)

        # List identities - should only see ones from current organization
        response = await client.get(
            "/api/v1/user/me/identities",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        identity_ids = [i["id"] for i in data["identities"]]
        # Identity from other org should NOT be visible
        assert str(other_org_identity.id) not in identity_ids

    @pytest.mark.asyncio
    async def test_cannot_unlink_identity_from_other_org(
        self,
        client: AsyncClient,
        async_session,
        test_jwt_token,
        second_organization,
        test_user,
    ):
        """Test that user cannot unlink identity from another organization."""
        # Create an identity in the second organization
        other_org_identity = UserIdentity(
            user_id=test_user.id,
            organization_id=second_organization.id,
            provider="microsoft",
            provider_user_id="microsoft_other_org_2",
            provider_email=test_user.email,
        )
        async_session.add(other_org_identity)
        await async_session.commit()
        await async_session.refresh(other_org_identity)

        # Try to unlink - should not find it in current org context
        response = await client.delete(
            "/api/v1/user/me/identities/microsoft",
            headers={"Authorization": test_jwt_token},
        )
        # Should fail because the identity is in a different org
        assert response.status_code == 404


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestIdentityEdgeCases:
    """Tests for edge cases in identity management."""

    @pytest.mark.asyncio
    async def test_unlink_case_insensitive_provider(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_user_identity,
    ):
        """Test that provider matching is case-insensitive."""
        # Identity was created with 'google' (lowercase)
        response = await client.delete(
            "/api/v1/user/me/identities/GOOGLE",  # uppercase
            headers={"Authorization": test_jwt_token},
        )
        # Should still match and unlink
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_identities_shows_primary(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
    ):
        """Test that primary identity is marked correctly."""
        from src.core.security import create_access_token
        from src.models.user import CreatedVia, User

        # Create user who signed up via Google
        google_user = User(
            email="googleuser@test.com",
            password=None,
            email_verified=True,
            organization_id=test_organization.id,
            created_via=CreatedVia.GOOGLE,
        )
        async_session.add(google_user)
        await async_session.commit()
        await async_session.refresh(google_user)

        # Add Google identity
        google_identity = UserIdentity(
            user_id=google_user.id,
            organization_id=test_organization.id,
            provider="google",
            provider_user_id="google_primary",
            provider_email=google_user.email,
        )
        async_session.add(google_identity)
        await async_session.commit()
        await async_session.refresh(google_identity)

        token = create_access_token(
            user_id=str(google_user.id),
            organization_id=str(test_organization.id),
        )

        response = await client.get(
            "/api/v1/user/me/identities",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["created_via"] == "google"
        # Google identity should be marked as primary
        google_identity_response = next(
            (i for i in data["identities"] if i["provider"] == "google"), None
        )
        assert google_identity_response is not None
        assert google_identity_response["is_primary"] is True
