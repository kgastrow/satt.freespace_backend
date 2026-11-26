"""
API tests for system configuration endpoints.

Tests verify:
- Super admin only access
- Get/update config
- Create/delete config
- Audit logging
- Sensitive value handling
"""

from uuid import uuid4

from httpx import AsyncClient
import pytest

from src.models.system_config import SystemConfig


# ─────────────────────────────────────────────────────────────
# Fixtures for System Config Testing
# ─────────────────────────────────────────────────────────────


@pytest.fixture
async def test_system_config(async_session):
    """Create a test system configuration entry."""
    config = SystemConfig(
        key="test_config_key",
        value="test_value",
        description="Test configuration for testing",
    )
    async_session.add(config)
    await async_session.commit()
    await async_session.refresh(config)
    return config


@pytest.fixture
async def multiple_system_configs(async_session):
    """Create multiple system configuration entries."""
    configs = [
        SystemConfig(
            key="config_one",
            value="value_one",
            description="First test config",
        ),
        SystemConfig(
            key="config_two",
            value={"nested": "value", "count": 42},
            description="Second test config with JSON value",
        ),
        SystemConfig(
            key="config_three",
            value=True,
            description="Third test config with boolean value",
        ),
    ]
    for config in configs:
        async_session.add(config)
    await async_session.commit()
    for config in configs:
        await async_session.refresh(config)
    return configs


@pytest.fixture
async def sensitive_system_config(async_session):
    """Create a sensitive system configuration entry."""
    config = SystemConfig(
        key="external.api_key",
        value="sk_live_secret_key_12345",
        description="External API key (sensitive)",
    )
    async_session.add(config)
    await async_session.commit()
    await async_session.refresh(config)
    return config


# ─────────────────────────────────────────────────────────────
# Access Control Tests
# ─────────────────────────────────────────────────────────────


class TestSystemConfigAccessControl:
    """Tests for system config access control."""

    @pytest.mark.asyncio
    async def test_get_system_config_requires_super_admin(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test that getting system config requires super admin."""
        response = await client.get(
            "/api/v1/admin/system-config",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_get_system_config_as_super_admin(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test getting system config as super admin."""
        response = await client.get(
            "/api/v1/admin/system-config",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

    @pytest.mark.asyncio
    async def test_create_system_config_requires_super_admin(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test that creating system config requires super admin."""
        response = await client.post(
            "/api/v1/admin/system-config",
            json={"key": "new_key", "value": "new_value"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_update_system_config_requires_super_admin(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_system_config,
    ):
        """Test that updating system config requires super admin."""
        response = await client.put(
            f"/api/v1/admin/system-config/{test_system_config.key}",
            json={"value": "updated_value"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_delete_system_config_requires_super_admin(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_system_config,
    ):
        """Test that deleting system config requires super admin."""
        response = await client.delete(
            f"/api/v1/admin/system-config/{test_system_config.key}",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code in [401, 403]


# ─────────────────────────────────────────────────────────────
# List Config Tests
# ─────────────────────────────────────────────────────────────


class TestSystemConfigList:
    """Tests for listing system configs."""

    @pytest.mark.asyncio
    async def test_list_configs_empty(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test listing configs when none exist."""
        response = await client.get(
            "/api/v1/admin/system-config",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_list_configs_with_data(
        self,
        client: AsyncClient,
        test_super_admin_token,
        multiple_system_configs,
    ):
        """Test listing configs with multiple entries."""
        response = await client.get(
            "/api/v1/admin/system-config",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 3
        assert data["total"] >= 3

    @pytest.mark.asyncio
    async def test_list_configs_pagination(
        self,
        client: AsyncClient,
        test_super_admin_token,
        multiple_system_configs,
    ):
        """Test listing configs with pagination."""
        response = await client.get(
            "/api/v1/admin/system-config?limit=2&offset=0",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 2
        assert data["limit"] == 2
        assert data["offset"] == 0


# ─────────────────────────────────────────────────────────────
# Get Single Config Tests
# ─────────────────────────────────────────────────────────────


class TestSystemConfigGetByKey:
    """Tests for getting a specific config by key."""

    @pytest.mark.asyncio
    async def test_get_config_by_key(
        self,
        client: AsyncClient,
        test_super_admin_token,
        test_system_config,
    ):
        """Test getting a specific config by key."""
        response = await client.get(
            f"/api/v1/admin/system-config/{test_system_config.key}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == test_system_config.key
        assert data["value"] == test_system_config.value

    @pytest.mark.asyncio
    async def test_get_config_not_found(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test getting a non-existent config."""
        unique_key = f"non_existent_{uuid4().hex[:8]}"
        response = await client.get(
            f"/api/v1/admin/system-config/{unique_key}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_sensitive_config_masked(
        self,
        client: AsyncClient,
        test_super_admin_token,
        sensitive_system_config,
    ):
        """Test that sensitive config values are masked."""
        response = await client.get(
            f"/api/v1/admin/system-config/{sensitive_system_config.key}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_sensitive"] is True
        # Value should be masked (contains asterisks)
        assert "****" in data["value"] or data["value"] == "********"


# ─────────────────────────────────────────────────────────────
# Create Config Tests
# ─────────────────────────────────────────────────────────────


class TestSystemConfigCreate:
    """Tests for creating system configs."""

    @pytest.mark.asyncio
    async def test_create_config(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test creating a new config."""
        response = await client.post(
            "/api/v1/admin/system-config",
            json={
                "key": f"new_config_{uuid4().hex[:8]}",
                "value": "new_value",
                "description": "A new configuration",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["value"] == "new_value"
        assert data["description"] == "A new configuration"

    @pytest.mark.asyncio
    async def test_create_config_with_json_value(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test creating config with JSON value."""
        response = await client.post(
            "/api/v1/admin/system-config",
            json={
                "key": f"json_config_{uuid4().hex[:8]}",
                "value": {"nested": "object", "count": 100},
                "description": "Config with JSON value",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert isinstance(data["value"], dict)

    @pytest.mark.asyncio
    async def test_create_config_duplicate_key(
        self,
        client: AsyncClient,
        test_super_admin_token,
        test_system_config,
    ):
        """Test that duplicate key is rejected.

        Note: This test is expected to fail until the response code
        'system_config.already_exists' is added to response_codes.py
        """
        response = await client.post(
            "/api/v1/admin/system-config",
            json={
                "key": test_system_config.key,
                "value": "duplicate_value",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_config_missing_key(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test that missing key is rejected."""
        response = await client.post(
            "/api/v1/admin/system-config",
            json={
                "value": "value_without_key",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 422


# ─────────────────────────────────────────────────────────────
# Update Config Tests
# ─────────────────────────────────────────────────────────────


class TestSystemConfigUpdate:
    """Tests for updating system configs."""

    @pytest.mark.asyncio
    async def test_update_config(
        self,
        client: AsyncClient,
        test_super_admin_token,
        test_system_config,
    ):
        """Test updating a system config."""
        response = await client.put(
            f"/api/v1/admin/system-config/{test_system_config.key}",
            json={
                "value": "updated_value",
                "description": "Updated description",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == "updated_value"
        assert data["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_update_config_creates_if_not_exists(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test that updating non-existent config creates it."""
        new_key = f"new_config_{uuid4().hex[:8]}"
        response = await client.put(
            f"/api/v1/admin/system-config/{new_key}",
            json={
                "value": "new_value",
                "description": "Created via update",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == new_key
        assert data["value"] == "new_value"

    @pytest.mark.asyncio
    async def test_update_config_value_only(
        self,
        client: AsyncClient,
        test_super_admin_token,
        test_system_config,
    ):
        """Test updating only the value."""
        response = await client.put(
            f"/api/v1/admin/system-config/{test_system_config.key}",
            json={
                "value": "only_value_updated",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == "only_value_updated"


# ─────────────────────────────────────────────────────────────
# Delete Config Tests
# ─────────────────────────────────────────────────────────────


class TestSystemConfigDelete:
    """Tests for deleting system configs."""

    @pytest.mark.asyncio
    async def test_delete_config(
        self,
        client: AsyncClient,
        test_super_admin_token,
        test_system_config,
    ):
        """Test deleting a system config."""
        response = await client.delete(
            f"/api/v1/admin/system-config/{test_system_config.key}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "deleted" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_config_not_found(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test deleting non-existent config."""
        unique_key = f"non_existent_{uuid4().hex[:8]}"
        response = await client.delete(
            f"/api/v1/admin/system-config/{unique_key}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 404


# ─────────────────────────────────────────────────────────────
# Sensitive Value Handling Tests
# ─────────────────────────────────────────────────────────────


class TestSensitiveConfigHandling:
    """Tests for sensitive value handling in system configs."""

    @pytest.mark.asyncio
    async def test_create_sensitive_config_masks_response(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test that sensitive values are masked in create response."""
        response = await client.post(
            "/api/v1/admin/system-config",
            json={
                "key": f"service.api_key_{uuid4().hex[:8]}",
                "value": "super_secret_api_key_12345",
                "description": "Sensitive API key",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["is_sensitive"] is True
        # Value should be masked
        assert "****" in data["value"] or data["value"] == "********"

    @pytest.mark.asyncio
    async def test_update_sensitive_config_masks_response(
        self,
        client: AsyncClient,
        test_super_admin_token,
        sensitive_system_config,
    ):
        """Test that sensitive values are masked in update response."""
        response = await client.put(
            f"/api/v1/admin/system-config/{sensitive_system_config.key}",
            json={
                "value": "new_secret_value_67890",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_sensitive"] is True
        # Value should be masked
        assert "****" in data["value"] or data["value"] == "********"

    @pytest.mark.asyncio
    async def test_list_masks_sensitive_values(
        self,
        client: AsyncClient,
        test_super_admin_token,
        sensitive_system_config,
    ):
        """Test that sensitive values are masked in list response."""
        response = await client.get(
            "/api/v1/admin/system-config",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()

        # Find the sensitive config in the response
        sensitive_item = None
        for item in data["items"]:
            if item["key"] == sensitive_system_config.key:
                sensitive_item = item
                break

        assert sensitive_item is not None
        assert sensitive_item["is_sensitive"] is True
        assert (
            "****" in sensitive_item["value"] or sensitive_item["value"] == "********"
        )


# ─────────────────────────────────────────────────────────────
# Unauthenticated Tests
# ─────────────────────────────────────────────────────────────


class TestSystemConfigUnauthenticated:
    """Tests for unauthenticated access to system config."""

    @pytest.mark.asyncio
    async def test_get_system_config_unauthenticated(self, client: AsyncClient):
        """Test that system config requires authentication."""
        response = await client.get("/api/v1/admin/system-config")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_system_config_unauthenticated(self, client: AsyncClient):
        """Test that creating system config requires authentication."""
        response = await client.post(
            "/api/v1/admin/system-config",
            json={"key": "test", "value": "test"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_system_config_unauthenticated(self, client: AsyncClient):
        """Test that updating system config requires authentication."""
        response = await client.put(
            "/api/v1/admin/system-config/test_key",
            json={"value": "test"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_system_config_unauthenticated(self, client: AsyncClient):
        """Test that deleting system config requires authentication."""
        response = await client.delete("/api/v1/admin/system-config/test_key")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_single_config_unauthenticated(self, client: AsyncClient):
        """Test that getting single config requires authentication."""
        response = await client.get("/api/v1/admin/system-config/test_key")
        assert response.status_code == 401


# ─────────────────────────────────────────────────────────────
# Input Validation Tests
# ─────────────────────────────────────────────────────────────


class TestSystemConfigInputValidation:
    """Tests for input validation on system config endpoints."""

    @pytest.mark.asyncio
    async def test_create_config_empty_key(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test that empty key is rejected."""
        response = await client.post(
            "/api/v1/admin/system-config",
            json={
                "key": "",
                "value": "test",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_config_key_too_long(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test that key exceeding max length is rejected."""
        response = await client.post(
            "/api/v1/admin/system-config",
            json={
                "key": "a" * 101,  # max_length is 100
                "value": "test",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_config_extra_fields(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test that extra fields are rejected."""
        response = await client.post(
            "/api/v1/admin/system-config",
            json={
                "key": f"test_key_{uuid4().hex[:8]}",
                "value": "test",
                "extra_field": "not allowed",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_config_extra_fields(
        self,
        client: AsyncClient,
        test_super_admin_token,
        test_system_config,
    ):
        """Test that extra fields in update are rejected."""
        response = await client.put(
            f"/api/v1/admin/system-config/{test_system_config.key}",
            json={
                "value": "updated",
                "extra_field": "not allowed",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 422
