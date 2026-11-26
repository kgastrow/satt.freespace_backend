"""
API tests for request log endpoints.

Tests verify:
- List request logs (super admin)
- Filter and search
- Log details
- Configuration management
- Cleanup operations
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from httpx import AsyncClient
import pytest

from src.models.request_log import RequestLog


# ============================================================================
# Fixtures for Request Log Testing
# ============================================================================


@pytest.fixture
async def test_request_log(async_session, test_organization, test_user):
    """Create a test request log entry."""

    log = RequestLog(
        organization_id=test_organization.id,
        user_id=test_user.id,
        method="GET",
        path="/api/v1/users",
        status_code=200,
        duration_ms=150,
        ip_address="127.0.0.1",
        user_agent="Test-Agent/1.0",
    )
    async_session.add(log)
    await async_session.commit()
    await async_session.refresh(log)
    return log


@pytest.fixture
async def test_request_log_error(async_session, test_organization, test_user):
    """Create a test request log entry with error status."""
    log = RequestLog(
        organization_id=test_organization.id,
        user_id=test_user.id,
        method="POST",
        path="/api/v1/users",
        status_code=500,
        duration_ms=50,
        ip_address="127.0.0.1",
        user_agent="Test-Agent/1.0",
        error_traceback="Traceback: Error occurred...",
    )
    async_session.add(log)
    await async_session.commit()
    await async_session.refresh(log)
    return log


@pytest.fixture
async def test_request_log_unauthenticated(async_session):
    """Create a test request log entry for an unauthenticated request."""
    log = RequestLog(
        organization_id=None,
        user_id=None,
        method="POST",
        path="/api/v1/auth/login",
        status_code=200,
        duration_ms=100,
        ip_address="192.168.1.1",
        user_agent="Mozilla/5.0",
    )
    async_session.add(log)
    await async_session.commit()
    await async_session.refresh(log)
    return log


@pytest.fixture
async def multiple_request_logs(async_session, test_organization, test_user):
    """Create multiple request log entries for testing."""
    logs = []
    methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
    paths = [
        "/api/v1/users",
        "/api/v1/organizations",
        "/api/v1/roles",
        "/api/v1/files",
        "/api/v1/notifications",
    ]
    status_codes = [200, 201, 400, 404, 500]

    for i in range(5):
        log = RequestLog(
            organization_id=test_organization.id,
            user_id=test_user.id,
            method=methods[i],
            path=paths[i],
            status_code=status_codes[i],
            duration_ms=50 + (i * 25),
            ip_address=f"192.168.1.{i + 1}",
            user_agent=f"Test-Agent/{i}.0",
        )
        async_session.add(log)
        logs.append(log)
    await async_session.commit()
    for log in logs:
        await async_session.refresh(log)
    return logs


# ============================================================================
# Access Control Tests
# ============================================================================


class TestRequestLogsAccessControl:
    """Tests for request log endpoint access control."""

    @pytest.mark.asyncio
    async def test_list_request_logs_requires_super_admin(
        self, client: AsyncClient, test_jwt_token
    ):
        """Test that listing request logs requires super admin."""
        response = await client.get(
            "/api/v1/admin/request-logs",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_list_request_logs_as_super_admin(
        self, client: AsyncClient, test_super_admin_token, test_request_log
    ):
        """Test listing request logs as super admin."""
        response = await client.get(
            "/api/v1/admin/request-logs",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    @pytest.mark.asyncio
    async def test_list_request_logs_unauthenticated(self, client: AsyncClient):
        """Test that listing request logs requires authentication."""
        response = await client.get("/api/v1/admin/request-logs")
        assert response.status_code == 401


# ============================================================================
# List Endpoint Tests
# ============================================================================


class TestListRequestLogs:
    """Tests for the list request logs endpoint."""

    @pytest.mark.asyncio
    async def test_list_request_logs_returns_items(
        self, client: AsyncClient, test_super_admin_token, test_request_log
    ):
        """Test that list endpoint returns items."""
        response = await client.get(
            "/api/v1/admin/request-logs",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1

    @pytest.mark.asyncio
    async def test_list_request_logs_pagination(
        self, client: AsyncClient, test_super_admin_token, multiple_request_logs
    ):
        """Test pagination for request logs list."""
        response = await client.get(
            "/api/v1/admin/request-logs?limit=2",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 2
        assert data["limit"] == 2

    @pytest.mark.asyncio
    async def test_list_request_logs_has_more_flag(
        self, client: AsyncClient, test_super_admin_token, multiple_request_logs
    ):
        """Test that has_more flag is present in response."""
        response = await client.get(
            "/api/v1/admin/request-logs?limit=2",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "has_more" in data

    @pytest.mark.asyncio
    async def test_list_request_logs_cursor_pagination(
        self, client: AsyncClient, test_super_admin_token, multiple_request_logs
    ):
        """Test cursor-based pagination."""
        # Get first page
        response = await client.get(
            "/api/v1/admin/request-logs?limit=2",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()

        if data.get("next_cursor"):
            # Get second page using cursor
            response2 = await client.get(
                f"/api/v1/admin/request-logs?limit=2&cursor={data['next_cursor']}",
                headers={"Authorization": test_super_admin_token},
            )
            assert response2.status_code == 200


# ============================================================================
# Filter Tests
# ============================================================================


class TestRequestLogsFilters:
    """Tests for request log filtering."""

    @pytest.mark.asyncio
    async def test_filter_by_method(
        self, client: AsyncClient, test_super_admin_token, multiple_request_logs
    ):
        """Test filtering request logs by HTTP method."""
        response = await client.get(
            "/api/v1/admin/request-logs?method=GET",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        for log in data["items"]:
            assert log["method"] == "GET"

    @pytest.mark.asyncio
    async def test_filter_by_path(
        self, client: AsyncClient, test_super_admin_token, test_request_log
    ):
        """Test filtering request logs by path."""
        response = await client.get(
            "/api/v1/admin/request-logs?path=/api/v1/users",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        for log in data["items"]:
            assert "/api/v1/users" in log["path"]

    @pytest.mark.asyncio
    async def test_filter_by_status_code_min(
        self, client: AsyncClient, test_super_admin_token, multiple_request_logs
    ):
        """Test filtering by minimum status code."""
        response = await client.get(
            "/api/v1/admin/request-logs?status_code_min=400",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        for log in data["items"]:
            assert log["status_code"] >= 400

    @pytest.mark.asyncio
    async def test_filter_by_status_code_max(
        self, client: AsyncClient, test_super_admin_token, multiple_request_logs
    ):
        """Test filtering by maximum status code."""
        response = await client.get(
            "/api/v1/admin/request-logs?status_code_max=299",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        for log in data["items"]:
            assert log["status_code"] <= 299

    @pytest.mark.asyncio
    async def test_filter_by_organization_id(
        self,
        client: AsyncClient,
        test_super_admin_token,
        test_request_log,
        test_organization,
    ):
        """Test filtering by organization ID."""
        response = await client.get(
            f"/api/v1/admin/request-logs?organization_id={test_organization.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        for log in data["items"]:
            assert log["organization_id"] == str(test_organization.id)

    @pytest.mark.asyncio
    async def test_filter_by_user_id(
        self, client: AsyncClient, test_super_admin_token, test_request_log, test_user
    ):
        """Test filtering by user ID."""
        response = await client.get(
            f"/api/v1/admin/request-logs?user_id={test_user.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        for log in data["items"]:
            assert log["user_id"] == str(test_user.id)


# ============================================================================
# Get Single Log Tests
# ============================================================================


class TestGetRequestLog:
    """Tests for getting a single request log by ID."""

    @pytest.mark.asyncio
    async def test_get_request_log_by_id(
        self, client: AsyncClient, test_super_admin_token, test_request_log
    ):
        """Test getting a request log by ID."""
        response = await client.get(
            f"/api/v1/admin/request-logs/{test_request_log.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_request_log.id)
        assert data["method"] == test_request_log.method

    @pytest.mark.asyncio
    async def test_get_request_log_not_found(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test getting non-existent request log."""
        fake_id = str(uuid4())
        response = await client.get(
            f"/api/v1/admin/request-logs/{fake_id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_request_log_invalid_id(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test getting request log with invalid ID format."""
        response = await client.get(
            "/api/v1/admin/request-logs/not-a-valid-uuid",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code in [400, 422]


# ============================================================================
# Config Endpoint Tests
# ============================================================================


class TestRequestLogsConfig:
    """Tests for request logs configuration endpoints."""

    @pytest.mark.asyncio
    async def test_get_logging_config(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test getting request logging configuration."""
        response = await client.get(
            "/api/v1/admin/request-logs/config",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "db_enabled" in data
        assert "max_body_size" in data
        assert "retention_days" in data

    @pytest.mark.asyncio
    async def test_get_logging_config_requires_super_admin(
        self, client: AsyncClient, test_jwt_token
    ):
        """Test that getting config requires super admin."""
        response = await client.get(
            "/api/v1/admin/request-logs/config",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_update_logging_config(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test updating request logging configuration."""
        from dataclasses import dataclass

        @dataclass
        class MockConfig:
            enabled: bool = True
            db_enabled: bool = True
            max_body_size: int = 50000
            retention_days: int = 60

        with patch(
            "src.services.config_cache.update_request_logging_config",
            new_callable=AsyncMock,
        ) as mock_update:
            mock_update.return_value = MockConfig()

            request_data = {
                "enabled": True,
                "db_enabled": True,
                "max_body_size": 50000,
                "retention_days": 60,
            }
            response = await client.put(
                "/api/v1/admin/request-logs/config",
                json=request_data,
                headers={"Authorization": test_super_admin_token},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["max_body_size"] == 50000
            assert data["retention_days"] == 60

    @pytest.mark.asyncio
    async def test_update_logging_config_all_fields_required(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test that all fields are required when updating config."""
        # Only partial fields - should fail validation
        request_data = {"retention_days": 45}
        response = await client.put(
            "/api/v1/admin/request-logs/config",
            json=request_data,
            headers={"Authorization": test_super_admin_token},
        )
        # 422 because all fields are required
        assert response.status_code == 422


# ============================================================================
# Cleanup Endpoint Tests
# ============================================================================


class TestRequestLogsCleanup:
    """Tests for request logs cleanup endpoint."""

    @pytest.mark.asyncio
    async def test_trigger_cleanup(self, client: AsyncClient, test_super_admin_token):
        """Test triggering cleanup of old request logs."""
        response = await client.post(
            "/api/v1/admin/request-logs/cleanup",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 202
        data = response.json()
        assert "message" in data
        assert "job_id" in data

    @pytest.mark.asyncio
    async def test_trigger_cleanup_requires_super_admin(
        self, client: AsyncClient, test_jwt_token
    ):
        """Test that cleanup requires super admin."""
        response = await client.post(
            "/api/v1/admin/request-logs/cleanup",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_trigger_cleanup_unauthenticated(self, client: AsyncClient):
        """Test that cleanup requires authentication."""
        response = await client.post("/api/v1/admin/request-logs/cleanup")
        assert response.status_code == 401


# ============================================================================
# Response Field Tests
# ============================================================================


class TestRequestLogResponseFields:
    """Tests for request log response field structure."""

    @pytest.mark.asyncio
    async def test_request_log_response_fields(
        self, client: AsyncClient, test_super_admin_token, test_request_log
    ):
        """Test that request log response contains expected fields."""
        response = await client.get(
            f"/api/v1/admin/request-logs/{test_request_log.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        # Check required fields
        assert "id" in data
        assert "method" in data
        assert "path" in data
        assert "status_code" in data
        assert "duration_ms" in data

    @pytest.mark.asyncio
    async def test_request_log_list_response_fields(
        self, client: AsyncClient, test_super_admin_token, test_request_log
    ):
        """Test that request log list response contains expected fields."""
        response = await client.get(
            "/api/v1/admin/request-logs",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "has_more" in data
        assert "limit" in data

    @pytest.mark.asyncio
    async def test_request_log_includes_user_info(
        self, client: AsyncClient, test_super_admin_token, test_request_log
    ):
        """Test that request log includes user information."""
        response = await client.get(
            f"/api/v1/admin/request-logs/{test_request_log.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert "organization_id" in data

    @pytest.mark.asyncio
    async def test_request_log_error_includes_traceback(
        self, client: AsyncClient, test_super_admin_token, test_request_log_error
    ):
        """Test that error request logs include traceback."""
        response = await client.get(
            f"/api/v1/admin/request-logs/{test_request_log_error.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status_code"] == 500
        assert "error_traceback" in data


# ============================================================================
# Unauthenticated Request Log Tests
# ============================================================================


class TestUnauthenticatedRequestLogs:
    """Tests for handling unauthenticated request logs."""

    @pytest.mark.asyncio
    async def test_list_includes_unauthenticated_logs(
        self,
        client: AsyncClient,
        test_super_admin_token,
        test_request_log_unauthenticated,
    ):
        """Test that listing includes logs from unauthenticated requests."""
        response = await client.get(
            "/api/v1/admin/request-logs",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        # Should have at least the unauthenticated log
        assert len(data["items"]) >= 1

    @pytest.mark.asyncio
    async def test_get_unauthenticated_log_by_id(
        self,
        client: AsyncClient,
        test_super_admin_token,
        test_request_log_unauthenticated,
    ):
        """Test getting an unauthenticated request log by ID."""
        response = await client.get(
            f"/api/v1/admin/request-logs/{test_request_log_unauthenticated.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] is None
        assert data["organization_id"] is None
