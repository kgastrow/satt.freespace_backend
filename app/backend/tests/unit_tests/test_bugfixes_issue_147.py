"""
Unit tests for bug fixes in issue #147.

This file contains tests for multiple independent bug fixes:
1. Impersonation session endpoint returning 404 -> return 200 with {active: false}
"""

from datetime import datetime, timezone
from uuid import uuid4

from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, create_impersonation_token
from src.models.impersonation_session import ImpersonationSession


class TestImpersonationSessionNoReturn404:
    """Tests for impersonation session endpoint returning 200 with active status."""

    @pytest.mark.asyncio
    async def test_get_session_returns_inactive_when_not_impersonating(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_admin_user,
    ):
        """Test that GET /session returns 200 with active: false when not impersonating."""
        # Create a normal access token for the admin (not impersonating)
        admin_token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        response = await client.get(
            "/api/v1/admin/impersonate/session",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False
        assert data["session"] is None

    @pytest.mark.asyncio
    async def test_get_session_returns_active_when_impersonating(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_admin_user,
        test_user,
        test_organization,
    ):
        """Test that GET /session returns 200 with active: true and session details when impersonating."""
        # Create an impersonation session
        session_id = uuid4()
        impersonation_session = ImpersonationSession(
            id=session_id,
            impersonator_id=test_admin_user.id,
            target_user_id=test_user.id,
            target_organization_id=test_organization.id,
            created_time=datetime.now(timezone.utc),
            ended_time=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )
        async_session.add(impersonation_session)
        await async_session.commit()

        # Create an impersonation token
        impersonation_token = create_impersonation_token(
            user_id=str(test_user.id),
            organization_id=str(test_organization.id),
            impersonator_id=str(test_admin_user.id),
            impersonation_session_id=str(session_id),
        )

        response = await client.get(
            "/api/v1/admin/impersonate/session",
            headers={"Authorization": f"Bearer {impersonation_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["active"] is True
        assert data["session"] is not None
        assert data["session"]["id"] == str(session_id)
        assert data["session"]["target_user_id"] == str(test_user.id)
        assert data["session"]["impersonator_id"] == str(test_admin_user.id)
        assert data["session"]["ended_time"] is None

    @pytest.mark.asyncio
    async def test_get_session_returns_inactive_for_ended_session(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_admin_user,
        test_user,
        test_organization,
    ):
        """Test that GET /session returns 401 when session has ended.

        Security: Impersonation tokens with ended sessions are rejected at auth level
        to prevent any actions with stale impersonation claims.
        """
        # Create an ended impersonation session
        session_id = uuid4()
        impersonation_session = ImpersonationSession(
            id=session_id,
            impersonator_id=test_admin_user.id,
            target_user_id=test_user.id,
            target_organization_id=test_organization.id,
            created_time=datetime.now(timezone.utc),
            ended_time=datetime.now(timezone.utc),  # Session has ended
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )
        async_session.add(impersonation_session)
        await async_session.commit()

        # Create an impersonation token (still valid but session is ended)
        impersonation_token = create_impersonation_token(
            user_id=str(test_user.id),
            organization_id=str(test_organization.id),
            impersonator_id=str(test_admin_user.id),
            impersonation_session_id=str(session_id),
        )

        response = await client.get(
            "/api/v1/admin/impersonate/session",
            headers={"Authorization": f"Bearer {impersonation_token}"},
        )

        # Security: Auth layer rejects tokens with ended impersonation sessions
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_session_returns_inactive_for_nonexistent_session(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_admin_user,
        test_user,
        test_organization,
    ):
        """Test that GET /session returns 401 when session doesn't exist in DB.

        Security: Impersonation tokens with non-existent sessions are rejected at auth level
        to prevent any actions with invalid impersonation claims.
        """
        # Create an impersonation token with a session ID that doesn't exist
        nonexistent_session_id = uuid4()
        impersonation_token = create_impersonation_token(
            user_id=str(test_user.id),
            organization_id=str(test_organization.id),
            impersonator_id=str(test_admin_user.id),
            impersonation_session_id=str(nonexistent_session_id),
        )

        response = await client.get(
            "/api/v1/admin/impersonate/session",
            headers={"Authorization": f"Bearer {impersonation_token}"},
        )

        # Security: Auth layer rejects tokens with invalid impersonation sessions
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_session_with_regular_user_token(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user,
    ):
        """Test that GET /session returns 200 with active: false for regular non-admin users."""
        # Create a normal access token for a regular user
        user_token = create_access_token(
            user_id=str(test_user.id),
            organization_id=str(test_user.organization_id),
        )

        response = await client.get(
            "/api/v1/admin/impersonate/session",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False
        assert data["session"] is None


class TestUserMeOrganizationDetails:
    """Tests for /user/me endpoint including organization details."""

    @pytest.mark.asyncio
    async def test_user_me_includes_organization_details(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user,
        test_organization,
    ):
        """Test that GET /user/me returns organization details including id, name, and slug."""
        from src.core.security import create_access_token

        # Create access token for test user
        user_token = create_access_token(
            user_id=str(test_user.id),
            organization_id=str(test_user.organization_id),
        )

        response = await client.get(
            "/api/v1/user/me",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify user data
        assert data["id"] == str(test_user.id)
        assert data["email"] == test_user.email
        assert data["organization_id"] == str(test_organization.id)

        # Verify organization details are present
        assert "organization" in data
        assert data["organization"] is not None
        assert data["organization"]["id"] == str(test_organization.id)
        assert data["organization"]["name"] == test_organization.name
        assert data["organization"]["slug"] == test_organization.slug

    @pytest.mark.asyncio
    async def test_user_me_organization_id_and_details_match(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user,
        test_organization,
    ):
        """Test that organization_id and organization.id in /user/me response match."""
        from src.core.security import create_access_token

        user_token = create_access_token(
            user_id=str(test_user.id),
            organization_id=str(test_user.organization_id),
        )

        response = await client.get(
            "/api/v1/user/me",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        assert response.status_code == 200
        data = response.json()

        # organization_id and organization.id must match
        assert data["organization_id"] == data["organization"]["id"]


class TestApiKeyPermissionCodes:
    """Tests for API key permission codes validation."""

    @pytest.mark.asyncio
    async def test_create_api_key_with_permission_codes(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_admin_user,
        standard_permissions,
    ):
        """Test that API key creation accepts permission codes (strings like 'users:read')."""
        from src.core.security import create_access_token

        # Create access token for admin user (has api_keys:write permission)
        admin_token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        # Create API key with permission codes
        response = await client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Test API Key",
                "permissions": ["users:read", "users:write"],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test API Key"
        assert "key" in data
        assert set(data["permissions"]) == {"users:read", "users:write"}

    @pytest.mark.asyncio
    async def test_create_api_key_rejects_empty_permissions(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_admin_user,
    ):
        """Test that API key creation rejects empty permissions list."""
        from src.core.security import create_access_token

        # Create access token for admin user
        admin_token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        # Try to create API key with empty permissions
        response = await client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Test API Key",
                "permissions": [],
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "permission" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_api_key_rejects_no_permissions_field(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_admin_user,
    ):
        """Test that API key creation rejects missing permissions field."""
        from src.core.security import create_access_token

        # Create access token for admin user
        admin_token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        # Try to create API key without permissions field (defaults to empty list)
        response = await client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Test API Key",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "permission" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_list_api_keys_returns_permission_codes(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_admin_user,
        standard_permissions,
    ):
        """Test that API key listing returns permission codes (not UUIDs)."""
        from src.core.security import create_access_token

        # Create access token for admin user
        admin_token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        # Create an API key
        create_response = await client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Test API Key",
                "permissions": ["users:read"],
            },
        )
        assert create_response.status_code == 201

        # List API keys
        list_response = await client.get(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert list_response.status_code == 200
        data = list_response.json()
        assert len(data["items"]) > 0

        # Find our created key
        created_key = next(
            (k for k in data["items"] if k["name"] == "Test API Key"), None
        )
        assert created_key is not None
        assert "users:read" in created_key["permissions"]
        # Verify permissions are strings (codes), not UUIDs
        for perm in created_key["permissions"]:
            assert isinstance(perm, str)
            assert ":" in perm  # Permission codes have format "resource:action"
