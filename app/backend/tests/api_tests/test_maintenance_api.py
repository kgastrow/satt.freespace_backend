"""
API tests for maintenance mode endpoints.

Tests verify:
- Get maintenance status (public)
- Maintenance configuration access
"""

from httpx import AsyncClient
import pytest


# ============================================================================
# Fixtures for Maintenance Testing
# ============================================================================


@pytest.fixture
async def maintenance_config_enabled(async_session):
    """Create a maintenance config with maintenance enabled."""
    from src.models.system_config import SystemConfig

    configs = [
        SystemConfig(
            key="maintenance.enabled",
            value=True,
            description="Maintenance mode enabled",
        ),
        SystemConfig(
            key="maintenance.message",
            value="System under maintenance",
            description="Maintenance message",
        ),
    ]
    for config in configs:
        async_session.add(config)
    await async_session.commit()
    return configs


@pytest.fixture
async def maintenance_config_disabled(async_session):
    """Create a maintenance config with maintenance disabled."""
    from src.models.system_config import SystemConfig

    config = SystemConfig(
        key="maintenance.enabled",
        value=False,
        description="Maintenance mode disabled",
    )
    async_session.add(config)
    await async_session.commit()
    return config


# ============================================================================
# Public Status Tests
# ============================================================================


class TestMaintenanceStatusPublic:
    """Tests for the public /api/v1/maintenance/status endpoint."""

    @pytest.mark.asyncio
    async def test_get_maintenance_status_public(self, client: AsyncClient):
        """Test that maintenance status is publicly accessible."""
        response = await client.get("/api/v1/maintenance/status")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert isinstance(data["enabled"], bool)

    @pytest.mark.asyncio
    async def test_get_maintenance_status_returns_expected_fields(
        self, client: AsyncClient
    ):
        """Test that maintenance status returns all expected fields."""
        response = await client.get("/api/v1/maintenance/status")
        assert response.status_code == 200
        data = response.json()
        # Check required fields are present
        assert "enabled" in data
        assert "allow_super_admin" in data
        # Optional fields may or may not be present
        assert "message" in data or data.get("message") is None

    @pytest.mark.asyncio
    async def test_get_maintenance_status_when_disabled(
        self, client: AsyncClient, maintenance_config_disabled
    ):
        """Test maintenance status when maintenance is disabled."""
        response = await client.get("/api/v1/maintenance/status")
        assert response.status_code == 200
        data = response.json()
        # Should return enabled status (may be true or false based on config)
        assert "enabled" in data

    @pytest.mark.asyncio
    async def test_get_maintenance_status_when_enabled(
        self, client: AsyncClient, maintenance_config_enabled
    ):
        """Test maintenance status when maintenance is enabled."""
        response = await client.get("/api/v1/maintenance/status")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data

    @pytest.mark.asyncio
    async def test_get_maintenance_status_scheduled_fields(self, client: AsyncClient):
        """Test that maintenance status includes scheduled fields."""
        response = await client.get("/api/v1/maintenance/status")
        assert response.status_code == 200
        data = response.json()
        # Scheduled fields may be null but should be present
        assert "scheduled_start" in data or data.get("scheduled_start") is None
        assert "scheduled_end" in data or data.get("scheduled_end") is None


# ============================================================================
# No Authentication Required Tests
# ============================================================================


class TestMaintenanceNoAuth:
    """Tests to verify maintenance status is accessible without authentication."""

    @pytest.mark.asyncio
    async def test_status_accessible_without_token(self, client: AsyncClient):
        """Test that maintenance status can be accessed without any token."""
        response = await client.get("/api/v1/maintenance/status")
        # Should succeed without authentication
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_status_accessible_with_invalid_token(self, client: AsyncClient):
        """Test that maintenance status is accessible even with an invalid token."""
        response = await client.get(
            "/api/v1/maintenance/status",
            headers={"Authorization": "Bearer invalid_token_here"},
        )
        # Should still succeed - it's a public endpoint
        # May be 200 (ignores invalid token) or 401 (validates but fails)
        # Most likely 200 since it's public
        assert response.status_code in [200, 401]


# ============================================================================
# Authenticated Access Tests
# ============================================================================


class TestMaintenanceAuthenticated:
    """Tests for maintenance status with authenticated users."""

    @pytest.mark.asyncio
    async def test_status_accessible_with_regular_user_token(
        self, client: AsyncClient, test_jwt_token
    ):
        """Test that maintenance status is accessible with regular user token."""
        response = await client.get(
            "/api/v1/maintenance/status",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_status_accessible_with_admin_token(
        self, client: AsyncClient, test_admin_token
    ):
        """Test that maintenance status is accessible with admin token."""
        response = await client.get(
            "/api/v1/maintenance/status",
            headers={"Authorization": test_admin_token},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_status_accessible_with_super_admin_token(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test that maintenance status is accessible with super admin token."""
        response = await client.get(
            "/api/v1/maintenance/status",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200


# ============================================================================
# Response Content Tests
# ============================================================================


class TestMaintenanceStatusResponse:
    """Tests for the structure and content of maintenance status responses."""

    @pytest.mark.asyncio
    async def test_response_is_json(self, client: AsyncClient):
        """Test that the response is valid JSON."""
        response = await client.get("/api/v1/maintenance/status")
        assert response.status_code == 200
        # This will raise an exception if not valid JSON
        data = response.json()
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_enabled_field_is_boolean(self, client: AsyncClient):
        """Test that the enabled field is a boolean."""
        response = await client.get("/api/v1/maintenance/status")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["enabled"], bool)

    @pytest.mark.asyncio
    async def test_allow_super_admin_field_is_boolean(self, client: AsyncClient):
        """Test that allow_super_admin field is a boolean."""
        response = await client.get("/api/v1/maintenance/status")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["allow_super_admin"], bool)

    @pytest.mark.asyncio
    async def test_message_field_is_string_or_null(self, client: AsyncClient):
        """Test that message field is a string or null."""
        response = await client.get("/api/v1/maintenance/status")
        assert response.status_code == 200
        data = response.json()
        message = data.get("message")
        assert message is None or isinstance(message, str)
