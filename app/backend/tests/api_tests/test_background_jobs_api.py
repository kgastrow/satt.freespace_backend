"""
API tests for background jobs monitoring endpoints.
Tests require super admin access.
"""

from unittest.mock import patch

import pytest


class TestBackgroundJobsStatsEndpoint:
    """Tests for GET /background-jobs/stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_stats_success(self, admin_client, test_admin_user):
        """Test getting background jobs stats as super admin."""
        from src.core.security import create_access_token

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        with patch(
            "src.api.background_jobs.job_stats_service.get_all_job_stats"
        ) as mock_stats:
            mock_stats.return_value = [
                {
                    "job_type": "send_email_task",
                    "executions_24h": 100,
                    "failures_24h": 5,
                    "failure_rate": 5.0,
                    "avg_duration_ms": 150.0,
                    "last_execution": "2025-06-15T14:30:00Z",
                }
            ]

            response = await admin_client.get(
                "/api/v1/background-jobs/stats",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "job_stats" in data
        assert "total_executions_24h" in data
        assert "total_failures_24h" in data

    @pytest.mark.asyncio
    async def test_get_stats_requires_super_admin(self, admin_client, test_user):
        """Test that getting stats requires super admin."""
        from src.core.security import create_access_token

        token = create_access_token(
            user_id=str(test_user.id),
            organization_id=str(test_user.organization_id),
        )

        response = await admin_client.get(
            "/api/v1/background-jobs/stats",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_stats_unauthorized(self, client):
        """Test that getting stats requires authentication."""
        response = await client.get("/api/v1/background-jobs/stats")

        # Should return 401 Unauthorized without a token
        assert response.status_code == 401


class TestQueueHealthEndpoint:
    """Tests for GET /background-jobs/queue-health endpoint."""

    @pytest.mark.asyncio
    async def test_get_queue_health_success(self, admin_client, test_admin_user):
        """Test getting queue health as super admin."""
        from src.core.security import create_access_token

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        with patch(
            "src.api.background_jobs.queue_health_service.check_health"
        ) as mock_health:
            mock_health.return_value = {
                "is_healthy": True,
                "issues": [],
                "queue_depth": 5,
                "depth_threshold": 100,
                "stuck_jobs_count": 0,
                "stuck_jobs": [],
                "workers_online": 2,
                "workers_offline": 0,
                "total_workers": 2,
                "checked_at": "2025-06-15T14:30:00Z",
            }

            response = await admin_client.get(
                "/api/v1/background-jobs/queue-health",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["is_healthy"] is True
        assert data["workers_online"] == 2
        assert data["queue_depth"] == 5

    @pytest.mark.asyncio
    async def test_get_queue_health_with_issues(self, admin_client, test_admin_user):
        """Test getting queue health with issues."""
        from src.core.security import create_access_token

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        with patch(
            "src.api.background_jobs.queue_health_service.check_health"
        ) as mock_health:
            mock_health.return_value = {
                "is_healthy": False,
                "issues": ["Queue depth exceeds threshold", "Stuck jobs detected"],
                "queue_depth": 150,
                "depth_threshold": 100,
                "stuck_jobs_count": 2,
                "stuck_jobs": [
                    {
                        "job_id": "job-123",
                        "function": "send_email_task",
                        "start_time": "2025-06-15T14:00:00Z",
                        "duration_minutes": 35,
                    }
                ],
                "workers_online": 1,
                "workers_offline": 1,
                "total_workers": 2,
                "checked_at": "2025-06-15T14:30:00Z",
            }

            response = await admin_client.get(
                "/api/v1/background-jobs/queue-health",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["is_healthy"] is False
        assert len(data["issues"]) == 2
        assert data["stuck_jobs_count"] == 2

    @pytest.mark.asyncio
    async def test_get_queue_health_requires_super_admin(self, admin_client, test_user):
        """Test that getting queue health requires super admin."""
        from src.core.security import create_access_token

        token = create_access_token(
            user_id=str(test_user.id),
            organization_id=str(test_user.organization_id),
        )

        response = await admin_client.get(
            "/api/v1/background-jobs/queue-health",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403


class TestJobTypesListEndpoint:
    """Tests for GET /background-jobs/types endpoint."""

    @pytest.mark.asyncio
    async def test_list_job_types_success(self, admin_client, test_admin_user):
        """Test listing job types as super admin."""
        from src.core.security import create_access_token

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        response = await admin_client.get(
            "/api/v1/background-jobs/types",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) > 0

        # Verify structure
        job_type = data["items"][0]
        assert "code" in job_type
        assert "name" in job_type
        assert "description" in job_type
        assert "category" in job_type
        assert "is_cron" in job_type
        assert "enabled" in job_type

    @pytest.mark.asyncio
    async def test_list_job_types_requires_super_admin(self, admin_client, test_user):
        """Test that listing job types requires super admin."""
        from src.core.security import create_access_token

        token = create_access_token(
            user_id=str(test_user.id),
            organization_id=str(test_user.organization_id),
        )

        response = await admin_client.get(
            "/api/v1/background-jobs/types",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403


class TestToggleJobTypeEndpoint:
    """Tests for PATCH /background-jobs/types/{type}/toggle endpoint."""

    @pytest.mark.asyncio
    async def test_toggle_job_type_disable(self, admin_client, test_admin_user):
        """Test disabling a job type."""
        from src.core.security import create_access_token

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        with patch(
            "src.api.background_jobs.job_stats_service.set_job_enabled_cache"
        ) as mock_cache:
            mock_cache.return_value = None

            response = await admin_client.patch(
                "/api/v1/background-jobs/types/send_email_task/toggle",
                json={"enabled": False},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["job_type"] == "send_email_task"
        assert data["enabled"] is False
        assert "disabled" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_toggle_job_type_enable(self, admin_client, test_admin_user):
        """Test enabling a job type."""
        from src.core.security import create_access_token

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        with patch(
            "src.api.background_jobs.job_stats_service.set_job_enabled_cache"
        ) as mock_cache:
            mock_cache.return_value = None

            response = await admin_client.patch(
                "/api/v1/background-jobs/types/send_email_task/toggle",
                json={"enabled": True},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["job_type"] == "send_email_task"
        assert data["enabled"] is True
        assert "enabled" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_toggle_job_type_not_found(self, admin_client, test_admin_user):
        """Test toggling a non-existent job type."""
        from src.core.security import create_access_token

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        response = await admin_client.patch(
            "/api/v1/background-jobs/types/nonexistent_job/toggle",
            json={"enabled": False},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_toggle_job_type_requires_super_admin(self, admin_client, test_user):
        """Test that toggling job type requires super admin."""
        from src.core.security import create_access_token

        token = create_access_token(
            user_id=str(test_user.id),
            organization_id=str(test_user.organization_id),
        )

        response = await admin_client.patch(
            "/api/v1/background-jobs/types/send_email_task/toggle",
            json={"enabled": False},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_toggle_job_type_invalid_request(self, admin_client, test_admin_user):
        """Test toggling with invalid request body."""
        from src.core.security import create_access_token

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        response = await admin_client.patch(
            "/api/v1/background-jobs/types/send_email_task/toggle",
            json={},  # Missing enabled field
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 422
