"""
API tests for cron job management endpoints.

Tests verify:
- List jobs (super admin)
- Enable/disable jobs
- Trigger jobs manually
- Job execution history
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from httpx import AsyncClient
import pytest

from src.models.cron_job import CronJobDefinition, CronJobExecution, CronJobStatus


# ============================================================================
# Fixtures for Cron Job Testing
# ============================================================================


@pytest.fixture
async def test_cron_job(async_session, test_organization):
    """Create a test cron job for the test organization."""
    job = CronJobDefinition(
        name="Test Cleanup Job",
        description="Test cleanup job for testing",
        code="test_cleanup_job",
        schedule_expression="0 0 * * *",
        is_active=True,
        organization_id=test_organization.id,
        last_run_status=CronJobStatus.PENDING.value,
    )
    async_session.add(job)
    await async_session.commit()
    await async_session.refresh(job)
    return job


@pytest.fixture
async def platform_cron_job(async_session):
    """Create a platform-wide cron job (no organization)."""
    job = CronJobDefinition(
        name="Platform Cleanup Job",
        description="Platform-wide cleanup job",
        code="platform_cleanup_job",
        schedule_expression="0 2 * * *",
        is_active=True,
        organization_id=None,  # Platform-wide
        last_run_status=CronJobStatus.PENDING.value,
    )
    async_session.add(job)
    await async_session.commit()
    await async_session.refresh(job)
    return job


@pytest.fixture
async def inactive_cron_job(async_session, test_organization):
    """Create an inactive cron job."""
    job = CronJobDefinition(
        name="Inactive Job",
        description="An inactive job for testing",
        code="inactive_job",
        schedule_expression="0 3 * * *",
        is_active=False,
        organization_id=test_organization.id,
        last_run_status=CronJobStatus.PENDING.value,
    )
    async_session.add(job)
    await async_session.commit()
    await async_session.refresh(job)
    return job


@pytest.fixture
async def test_cron_execution(async_session, test_cron_job, test_organization):
    """Create a test cron job execution record."""
    from datetime import datetime, timezone

    execution = CronJobExecution(
        cron_job_id=test_cron_job.id,
        organization_id=test_organization.id,
        started_at=datetime.now(timezone.utc),
        status=CronJobStatus.SUCCESS.value,
        result={"items_processed": 10},
    )
    async_session.add(execution)
    await async_session.commit()
    await async_session.refresh(execution)
    return execution


@pytest.fixture
async def multiple_cron_jobs(async_session, test_organization):
    """Create multiple cron jobs for pagination testing."""
    jobs = []
    for i in range(5):
        job = CronJobDefinition(
            name=f"Test Job {i}",
            description=f"Test job {i} description",
            code=f"test_job_{i}",
            schedule_expression=f"0 {i} * * *",
            is_active=True,
            organization_id=test_organization.id,
            last_run_status=CronJobStatus.PENDING.value,
        )
        async_session.add(job)
        jobs.append(job)
    await async_session.commit()
    for job in jobs:
        await async_session.refresh(job)
    return jobs


# ============================================================================
# Access Control Tests
# ============================================================================


class TestCronJobsAccessControl:
    """Tests for cron job endpoint access control."""

    @pytest.mark.asyncio
    async def test_list_cron_jobs_requires_super_admin(
        self, client: AsyncClient, test_jwt_token
    ):
        """Test that listing cron jobs requires super admin."""
        response = await client.get(
            "/api/v1/cron-jobs",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_list_cron_jobs_as_super_admin(
        self, client: AsyncClient, test_super_admin_token, test_cron_job
    ):
        """Test listing cron jobs as super admin."""
        response = await client.get(
            "/api/v1/cron-jobs",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_cron_jobs_unauthenticated(self, client: AsyncClient):
        """Test that listing cron jobs requires authentication."""
        response = await client.get("/api/v1/cron-jobs")
        assert response.status_code == 401


# ============================================================================
# List Endpoint Tests
# ============================================================================


class TestListCronJobs:
    """Tests for the list cron jobs endpoint."""

    @pytest.mark.asyncio
    async def test_list_cron_jobs_returns_items(
        self, client: AsyncClient, test_super_admin_token, test_cron_job
    ):
        """Test that list endpoint returns items."""
        response = await client.get(
            "/api/v1/cron-jobs",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1

    @pytest.mark.asyncio
    async def test_list_cron_jobs_pagination(
        self, client: AsyncClient, test_super_admin_token, multiple_cron_jobs
    ):
        """Test pagination for cron jobs list."""
        response = await client.get(
            "/api/v1/cron-jobs?limit=2&offset=0",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 2
        assert data["limit"] == 2
        assert data["offset"] == 0

    @pytest.mark.asyncio
    async def test_list_cron_jobs_filter_by_active(
        self,
        client: AsyncClient,
        test_super_admin_token,
        test_cron_job,
        inactive_cron_job,
    ):
        """Test filtering cron jobs by active status."""
        response = await client.get(
            "/api/v1/cron-jobs?filter[is_active]=true",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        for job in data["items"]:
            assert job["is_active"] is True

    @pytest.mark.asyncio
    async def test_list_cron_jobs_includes_platform_wide(
        self, client: AsyncClient, test_super_admin_token, platform_cron_job
    ):
        """Test that listing includes platform-wide jobs."""
        response = await client.get(
            "/api/v1/cron-jobs",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        # Should include platform-wide job
        platform_jobs = [j for j in data["items"] if j["is_platform_wide"]]
        assert len(platform_jobs) >= 1


# ============================================================================
# Get Single Job Tests
# ============================================================================


class TestGetCronJob:
    """Tests for getting a single cron job by ID."""

    @pytest.mark.asyncio
    async def test_get_cron_job_by_id(
        self, client: AsyncClient, test_super_admin_token, test_cron_job
    ):
        """Test getting a cron job by ID."""
        response = await client.get(
            f"/api/v1/cron-jobs/{test_cron_job.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_cron_job.id)
        assert data["name"] == test_cron_job.name

    @pytest.mark.asyncio
    async def test_get_cron_job_not_found(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test getting non-existent cron job."""
        fake_id = str(uuid4())
        response = await client.get(
            f"/api/v1/cron-jobs/{fake_id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_cron_job_invalid_id(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test getting cron job with invalid ID format."""
        response = await client.get(
            "/api/v1/cron-jobs/not-a-valid-uuid",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code in [400, 422]


# ============================================================================
# Create Cron Job Tests
# ============================================================================


class TestCreateCronJob:
    """Tests for creating cron jobs."""

    @pytest.mark.asyncio
    async def test_create_cron_job(self, client: AsyncClient, test_super_admin_token):
        """Test creating a cron job."""
        request_data = {
            "name": "New Test Job",
            "description": "A new test job",
            "code": "new_test_job",
            "schedule_expression": "0 */6 * * *",
            "is_active": True,
        }
        response = await client.post(
            "/api/v1/cron-jobs",
            json=request_data,
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Test Job"
        assert data["code"] == "new_test_job"

    @pytest.mark.asyncio
    async def test_create_cron_job_platform_wide(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test creating a platform-wide cron job."""
        request_data = {
            "name": "Platform Job",
            "description": "A platform-wide job",
            "code": "new_platform_job",
            "schedule_expression": "0 1 * * *",
            "is_active": True,
            "is_platform_wide": True,
        }
        response = await client.post(
            "/api/v1/cron-jobs",
            json=request_data,
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["is_platform_wide"] is True

    @pytest.mark.asyncio
    async def test_create_cron_job_invalid_schedule(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test creating cron job with invalid schedule expression."""
        request_data = {
            "name": "Invalid Job",
            "code": "invalid_job",
            "schedule_expression": "not a cron expression",
        }
        response = await client.post(
            "/api/v1/cron-jobs",
            json=request_data,
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_create_cron_job_invalid_code(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test creating cron job with invalid code characters."""
        request_data = {
            "name": "Invalid Code Job",
            "code": "invalid code with spaces!",
            "schedule_expression": "0 0 * * *",
        }
        response = await client.post(
            "/api/v1/cron-jobs",
            json=request_data,
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_create_cron_job_missing_required_fields(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test creating cron job with missing required fields."""
        request_data = {
            "name": "Incomplete Job"
            # Missing code and schedule_expression
        }
        response = await client.post(
            "/api/v1/cron-jobs",
            json=request_data,
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code in [400, 422]


# ============================================================================
# Update Cron Job Tests
# ============================================================================


class TestUpdateCronJob:
    """Tests for updating cron jobs."""

    @pytest.mark.asyncio
    async def test_update_cron_job(
        self, client: AsyncClient, test_super_admin_token, test_cron_job
    ):
        """Test updating a cron job."""
        request_data = {"description": "Updated description"}
        response = await client.put(
            f"/api/v1/cron-jobs/{test_cron_job.id}",
            json=request_data,
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_update_cron_job_schedule(
        self, client: AsyncClient, test_super_admin_token, test_cron_job
    ):
        """Test updating cron job schedule expression."""
        request_data = {"schedule_expression": "0 */4 * * *"}
        response = await client.put(
            f"/api/v1/cron-jobs/{test_cron_job.id}",
            json=request_data,
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["schedule_expression"] == "0 */4 * * *"

    @pytest.mark.asyncio
    async def test_update_cron_job_not_found(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test updating non-existent cron job."""
        fake_id = str(uuid4())
        request_data = {"description": "Updated"}
        response = await client.put(
            f"/api/v1/cron-jobs/{fake_id}",
            json=request_data,
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_cron_job_invalid_schedule(
        self, client: AsyncClient, test_super_admin_token, test_cron_job
    ):
        """Test updating cron job with invalid schedule."""
        request_data = {"schedule_expression": "invalid"}
        response = await client.put(
            f"/api/v1/cron-jobs/{test_cron_job.id}",
            json=request_data,
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code in [400, 422]


# ============================================================================
# Delete Cron Job Tests
# ============================================================================


class TestDeleteCronJob:
    """Tests for deleting cron jobs."""

    @pytest.mark.asyncio
    async def test_delete_cron_job(
        self, client: AsyncClient, test_super_admin_token, test_cron_job
    ):
        """Test deleting a cron job."""
        response = await client.delete(
            f"/api/v1/cron-jobs/{test_cron_job.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data["message"].lower() or "message" in data

    @pytest.mark.asyncio
    async def test_delete_cron_job_not_found(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test deleting non-existent cron job."""
        fake_id = str(uuid4())
        response = await client.delete(
            f"/api/v1/cron-jobs/{fake_id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 404


# ============================================================================
# Toggle Cron Job Tests
# ============================================================================


class TestToggleCronJob:
    """Tests for toggling cron job active status."""

    @pytest.mark.asyncio
    async def test_toggle_cron_job_disable(
        self, client: AsyncClient, test_super_admin_token, test_cron_job
    ):
        """Test disabling a cron job."""
        request_data = {"is_active": False}
        response = await client.patch(
            f"/api/v1/cron-jobs/{test_cron_job.id}/toggle",
            json=request_data,
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_toggle_cron_job_enable(
        self, client: AsyncClient, test_super_admin_token, inactive_cron_job
    ):
        """Test enabling a cron job."""
        request_data = {"is_active": True}
        response = await client.patch(
            f"/api/v1/cron-jobs/{inactive_cron_job.id}/toggle",
            json=request_data,
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_toggle_cron_job_not_found(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test toggling non-existent cron job."""
        fake_id = str(uuid4())
        request_data = {"is_active": False}
        response = await client.patch(
            f"/api/v1/cron-jobs/{fake_id}/toggle",
            json=request_data,
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 404


# ============================================================================
# Execution History Tests
# ============================================================================


class TestCronJobExecutions:
    """Tests for cron job execution history endpoints."""

    @pytest.mark.asyncio
    async def test_get_cron_job_executions(
        self,
        client: AsyncClient,
        test_super_admin_token,
        test_cron_job,
        test_cron_execution,
    ):
        """Test getting cron job execution history."""
        response = await client.get(
            f"/api/v1/cron-jobs/{test_cron_job.id}/executions",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) >= 1

    @pytest.mark.asyncio
    async def test_get_cron_job_executions_pagination(
        self,
        client: AsyncClient,
        test_super_admin_token,
        test_cron_job,
        test_cron_execution,
    ):
        """Test pagination for cron job executions."""
        response = await client.get(
            f"/api/v1/cron-jobs/{test_cron_job.id}/executions?limit=10&offset=0",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 0

    @pytest.mark.asyncio
    async def test_get_cron_job_executions_empty(
        self, client: AsyncClient, test_super_admin_token, inactive_cron_job
    ):
        """Test getting executions for job with no history."""
        response = await client.get(
            f"/api/v1/cron-jobs/{inactive_cron_job.id}/executions",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0


# ============================================================================
# Trigger Cron Job Tests
# ============================================================================


class TestTriggerCronJob:
    """Tests for manually triggering cron jobs."""

    @pytest.mark.asyncio
    async def test_trigger_cron_job(
        self, client: AsyncClient, test_super_admin_token, test_cron_job
    ):
        """Test manually triggering a cron job."""
        with patch(
            "src.services.cron_scheduler.cron_scheduler_service"
        ) as mock_scheduler:
            mock_scheduler.register_all_handlers = lambda: None
            mock_scheduler.execute_cron_job = AsyncMock()

            response = await client.post(
                f"/api/v1/cron-jobs/{test_cron_job.id}/trigger",
                json={},
                headers={"Authorization": test_super_admin_token},
            )
            # May return 202 Accepted or 200 OK depending on implementation
            assert response.status_code in [200, 202]

    @pytest.mark.asyncio
    async def test_trigger_cron_job_not_found(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test triggering non-existent cron job."""
        fake_id = str(uuid4())
        response = await client.post(
            f"/api/v1/cron-jobs/{fake_id}/trigger",
            json={},
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 404


# ============================================================================
# Cron Job Config Tests
# ============================================================================


class TestCronJobConfig:
    """Tests for cron job configuration endpoints."""

    @pytest.mark.asyncio
    async def test_get_cron_job_config(
        self, client: AsyncClient, test_super_admin_token, test_cron_job
    ):
        """Test getting cron job configuration."""
        response = await client.get(
            f"/api/v1/cron-jobs/{test_cron_job.id}/config",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "job_code" in data
        assert "has_config" in data
        assert "config_keys" in data

    @pytest.mark.asyncio
    async def test_get_cron_job_config_not_found(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test getting config for non-existent cron job."""
        fake_id = str(uuid4())
        response = await client.get(
            f"/api/v1/cron-jobs/{fake_id}/config",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 404


# ============================================================================
# Response Field Tests
# ============================================================================


class TestCronJobResponseFields:
    """Tests for cron job response field structure."""

    @pytest.mark.asyncio
    async def test_cron_job_response_fields(
        self, client: AsyncClient, test_super_admin_token, test_cron_job
    ):
        """Test that cron job response contains expected fields."""
        response = await client.get(
            f"/api/v1/cron-jobs/{test_cron_job.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        # Check required fields
        assert "id" in data
        assert "name" in data
        assert "code" in data
        assert "schedule_expression" in data
        assert "is_active" in data
        assert "last_run_status" in data
        assert "is_platform_wide" in data

    @pytest.mark.asyncio
    async def test_cron_job_list_response_fields(
        self, client: AsyncClient, test_super_admin_token, test_cron_job
    ):
        """Test that cron job list response contains expected fields."""
        response = await client.get(
            "/api/v1/cron-jobs",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
