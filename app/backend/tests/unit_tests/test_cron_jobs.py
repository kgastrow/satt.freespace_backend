"""
Unit tests for cron job models.
Tests CronJobDefinition and CronJobExecution model creation, field constraints,
relationships, and multi-tenancy support.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from src.models.cron_job import CronJobDefinition, CronJobExecution, CronJobStatus


class TestCronJobDefinitionModel:
    """Tests for CronJobDefinition model."""

    @pytest.mark.asyncio
    async def test_create_platform_wide_cron_job(self, async_session):
        """Test creating a platform-wide cron job (NULL organization_id)."""
        cron_job = CronJobDefinition(
            organization_id=None,  # Platform-wide
            name="Cleanup Expired Tokens",
            description="Remove expired refresh tokens from the database",
            code="cleanup_expired_tokens",
            schedule_expression="0 2 * * *",  # Daily at 2 AM
            is_active=True,
            is_enabled_by_default_for_new_orgs=False,
            parameters={"retention_days": 30, "batch_size": 1000},
            last_run_status=CronJobStatus.PENDING.value,
        )
        async_session.add(cron_job)
        await async_session.commit()
        await async_session.refresh(cron_job)

        assert cron_job.id is not None
        assert cron_job.organization_id is None
        assert cron_job.name == "Cleanup Expired Tokens"
        assert cron_job.description == "Remove expired refresh tokens from the database"
        assert cron_job.code == "cleanup_expired_tokens"
        assert cron_job.schedule_expression == "0 2 * * *"
        assert cron_job.is_active is True
        assert cron_job.is_enabled_by_default_for_new_orgs is False
        assert cron_job.parameters == {"retention_days": 30, "batch_size": 1000}
        assert cron_job.last_run_status == CronJobStatus.PENDING.value
        assert cron_job.last_run_time is None
        assert cron_job.next_run_time is None
        assert cron_job.last_run_error_message is None
        assert cron_job.created_time is not None
        assert cron_job.deleted_time is None

    @pytest.mark.asyncio
    async def test_create_org_scoped_cron_job(self, async_session, test_organization):
        """Test creating an organization-scoped cron job."""
        cron_job = CronJobDefinition(
            organization_id=test_organization.id,
            name="Generate Weekly Reports",
            description="Generate and email weekly analytics reports",
            code="weekly_report_generation",
            schedule_expression="0 9 * * MON",  # Every Monday at 9 AM
            is_active=True,
            is_enabled_by_default_for_new_orgs=True,
            parameters={"report_type": "analytics", "email_template": "weekly_report"},
        )
        async_session.add(cron_job)
        await async_session.commit()
        await async_session.refresh(cron_job)

        assert cron_job.id is not None
        assert cron_job.organization_id == test_organization.id
        assert cron_job.name == "Generate Weekly Reports"
        assert cron_job.code == "weekly_report_generation"
        assert cron_job.schedule_expression == "0 9 * * MON"
        assert cron_job.is_active is True
        assert cron_job.is_enabled_by_default_for_new_orgs is True

    @pytest.mark.asyncio
    async def test_cron_job_with_execution_tracking(self, async_session):
        """Test cron job with execution tracking fields populated."""
        now = datetime.now(timezone.utc)
        next_run = now + timedelta(hours=1)

        cron_job = CronJobDefinition(
            organization_id=None,
            name="Test Job",
            code="test_job",
            schedule_expression="0 * * * *",  # Every hour
            is_active=True,
            last_run_time=now,
            next_run_time=next_run,
            last_run_status=CronJobStatus.SUCCESS.value,
        )
        async_session.add(cron_job)
        await async_session.commit()
        await async_session.refresh(cron_job)

        # SQLite may strip timezone info, compare without timezone
        assert cron_job.last_run_time.replace(tzinfo=None) == now.replace(tzinfo=None)
        assert cron_job.next_run_time.replace(tzinfo=None) == next_run.replace(
            tzinfo=None
        )
        assert cron_job.last_run_status == CronJobStatus.SUCCESS.value

    @pytest.mark.asyncio
    async def test_cron_job_with_error_status(self, async_session):
        """Test cron job with error status and error message."""
        cron_job = CronJobDefinition(
            organization_id=None,
            name="Failing Job",
            code="failing_job",
            schedule_expression="0 * * * *",
            is_active=True,
            last_run_status=CronJobStatus.ERROR.value,
            last_run_error_message="Database connection timeout",
        )
        async_session.add(cron_job)
        await async_session.commit()
        await async_session.refresh(cron_job)

        assert cron_job.last_run_status == CronJobStatus.ERROR.value
        assert cron_job.last_run_error_message == "Database connection timeout"

    @pytest.mark.asyncio
    async def test_cron_job_inactive(self, async_session):
        """Test creating an inactive cron job."""
        cron_job = CronJobDefinition(
            organization_id=None,
            name="Disabled Job",
            code="disabled_job",
            schedule_expression="0 0 * * *",
            is_active=False,
        )
        async_session.add(cron_job)
        await async_session.commit()
        await async_session.refresh(cron_job)

        assert cron_job.is_active is False

    @pytest.mark.asyncio
    async def test_cron_job_minimal_fields(self, async_session):
        """Test creating a cron job with only required fields."""
        cron_job = CronJobDefinition(
            name="Minimal Job",
            code="minimal_job",
            schedule_expression="0 0 * * *",
        )
        async_session.add(cron_job)
        await async_session.commit()
        await async_session.refresh(cron_job)

        assert cron_job.id is not None
        assert cron_job.name == "Minimal Job"
        assert cron_job.code == "minimal_job"
        assert cron_job.schedule_expression == "0 0 * * *"
        assert cron_job.is_active is True  # Default value
        assert cron_job.is_enabled_by_default_for_new_orgs is False  # Default value
        assert cron_job.last_run_status == CronJobStatus.PENDING.value  # Default


class TestCronJobExecutionModel:
    """Tests for CronJobExecution model."""

    @pytest_asyncio.fixture(scope="function")
    async def test_cron_job(self, async_session):
        """Create a test cron job for execution tests."""
        cron_job = CronJobDefinition(
            organization_id=None,
            name="Test Job",
            code="test_job",
            schedule_expression="0 * * * *",
            is_active=True,
        )
        async_session.add(cron_job)
        await async_session.commit()
        await async_session.refresh(cron_job)
        return cron_job

    @pytest.mark.asyncio
    async def test_create_execution_running(self, async_session, test_cron_job):
        """Test creating a cron job execution with running status."""
        execution = CronJobExecution(
            cron_job_id=test_cron_job.id,
            organization_id=test_cron_job.organization_id,
            status=CronJobStatus.RUNNING.value,
        )
        async_session.add(execution)
        await async_session.commit()
        await async_session.refresh(execution)

        assert execution.id is not None
        assert execution.cron_job_id == test_cron_job.id
        assert execution.organization_id is None  # Platform-wide job
        assert execution.status == CronJobStatus.RUNNING.value
        assert execution.started_at is not None
        assert execution.completed_at is None
        assert execution.result is None
        assert execution.error_message is None
        assert execution.created_time is not None

    @pytest.mark.asyncio
    async def test_create_execution_success_with_result(
        self, async_session, test_cron_job
    ):
        """Test creating a successful execution with result data."""
        completed = datetime.now(timezone.utc)
        execution = CronJobExecution(
            cron_job_id=test_cron_job.id,
            organization_id=test_cron_job.organization_id,
            status=CronJobStatus.SUCCESS.value,
            completed_at=completed,
            result={"deleted_count": 150, "processed_count": 200, "duration_ms": 523},
        )
        async_session.add(execution)
        await async_session.commit()
        await async_session.refresh(execution)

        assert execution.status == CronJobStatus.SUCCESS.value
        # SQLite may strip timezone info, compare without timezone
        assert execution.completed_at.replace(tzinfo=None) == completed.replace(
            tzinfo=None
        )
        assert execution.result == {
            "deleted_count": 150,
            "processed_count": 200,
            "duration_ms": 523,
        }
        assert execution.error_message is None

    @pytest.mark.asyncio
    async def test_create_execution_error_with_message(
        self, async_session, test_cron_job
    ):
        """Test creating a failed execution with error message."""
        completed = datetime.now(timezone.utc)
        execution = CronJobExecution(
            cron_job_id=test_cron_job.id,
            organization_id=test_cron_job.organization_id,
            status=CronJobStatus.ERROR.value,
            completed_at=completed,
            error_message="Connection timeout after 30 seconds",
        )
        async_session.add(execution)
        await async_session.commit()
        await async_session.refresh(execution)

        assert execution.status == CronJobStatus.ERROR.value
        # SQLite may strip timezone info, compare without timezone
        assert execution.completed_at.replace(tzinfo=None) == completed.replace(
            tzinfo=None
        )
        assert execution.error_message == "Connection timeout after 30 seconds"
        assert execution.result is None

    @pytest.mark.asyncio
    async def test_execution_org_scoped(self, async_session, test_organization):
        """Test execution for an org-scoped cron job."""
        cron_job = CronJobDefinition(
            organization_id=test_organization.id,
            name="Org Job",
            code="org_job",
            schedule_expression="0 * * * *",
            is_active=True,
        )
        async_session.add(cron_job)
        await async_session.commit()
        await async_session.refresh(cron_job)

        execution = CronJobExecution(
            cron_job_id=cron_job.id,
            organization_id=test_organization.id,
            status=CronJobStatus.SUCCESS.value,
        )
        async_session.add(execution)
        await async_session.commit()
        await async_session.refresh(execution)

        assert execution.organization_id == test_organization.id
        assert execution.cron_job_id == cron_job.id

    @pytest.mark.asyncio
    async def test_execution_relationship(self, async_session, test_cron_job):
        """Test relationship between execution and cron job definition."""
        execution = CronJobExecution(
            cron_job_id=test_cron_job.id,
            organization_id=test_cron_job.organization_id,
            status=CronJobStatus.SUCCESS.value,
        )
        async_session.add(execution)
        await async_session.commit()
        await async_session.refresh(execution)

        # Test relationship loading
        await async_session.refresh(execution, ["cron_job"])
        assert execution.cron_job is not None
        assert execution.cron_job.id == test_cron_job.id
        assert execution.cron_job.code == test_cron_job.code


class TestCronJobMultiTenancy:
    """Tests for multi-tenancy isolation in cron job models."""

    @pytest.mark.asyncio
    async def test_separate_org_cron_jobs(
        self, async_session, test_organization, second_organization
    ):
        """Test that different orgs can have cron jobs with same code."""
        # Create cron job for first org
        cron_job_1 = CronJobDefinition(
            organization_id=test_organization.id,
            name="Org 1 Cleanup",
            code="daily_cleanup",
            schedule_expression="0 2 * * *",
            is_active=True,
        )
        async_session.add(cron_job_1)

        # Create cron job for second org with same code
        cron_job_2 = CronJobDefinition(
            organization_id=second_organization.id,
            name="Org 2 Cleanup",
            code="daily_cleanup",
            schedule_expression="0 3 * * *",
            is_active=True,
        )
        async_session.add(cron_job_2)

        await async_session.commit()
        await async_session.refresh(cron_job_1)
        await async_session.refresh(cron_job_2)

        assert cron_job_1.organization_id == test_organization.id
        assert cron_job_2.organization_id == second_organization.id
        assert cron_job_1.code == cron_job_2.code
        assert cron_job_1.id != cron_job_2.id

    @pytest.mark.asyncio
    async def test_platform_and_org_cron_jobs_same_code(
        self, async_session, test_organization
    ):
        """Test that platform-wide and org-scoped jobs can have same code."""
        # Create platform-wide job
        platform_job = CronJobDefinition(
            organization_id=None,
            name="Platform Cleanup",
            code="cleanup_job",
            schedule_expression="0 1 * * *",
            is_active=True,
        )
        async_session.add(platform_job)

        # Create org-scoped job with same code
        org_job = CronJobDefinition(
            organization_id=test_organization.id,
            name="Org Cleanup",
            code="cleanup_job",
            schedule_expression="0 2 * * *",
            is_active=True,
        )
        async_session.add(org_job)

        await async_session.commit()
        await async_session.refresh(platform_job)
        await async_session.refresh(org_job)

        assert platform_job.organization_id is None
        assert org_job.organization_id == test_organization.id
        assert platform_job.code == org_job.code
        assert platform_job.id != org_job.id


class TestCronJobCRUD:
    """Tests for cron job CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_cron_job_crud(self, async_session):
        """Test creating a cron job via CRUD."""
        from src.crud.cron_job import create_cron_job

        job_data = {
            "name": "Test CRUD Job",
            "description": "Testing CRUD operations",
            "code": "test_crud_job",
            "schedule_expression": "0 1 * * *",
            "is_active": True,
            "is_enabled_by_default_for_new_orgs": False,
            "parameters": {"key": "value"},
        }

        job = await create_cron_job(async_session, job_data, organization_id=None)

        assert job.id is not None
        assert job.name == "Test CRUD Job"
        assert job.code == "test_crud_job"
        assert job.schedule_expression == "0 1 * * *"
        assert job.is_active is True
        assert job.parameters == {"key": "value"}
        assert job.next_run_time is not None

    @pytest.mark.asyncio
    async def test_create_cron_job_invalid_expression(self, async_session):
        """Test creating a cron job with invalid cron expression."""
        from src.crud.cron_job import create_cron_job

        job_data = {
            "name": "Bad Job",
            "code": "bad_job",
            "schedule_expression": "invalid cron",
        }

        with pytest.raises(ValueError, match="Invalid cron expression"):
            await create_cron_job(async_session, job_data, organization_id=None)

    @pytest.mark.asyncio
    async def test_create_duplicate_code(self, async_session):
        """Test creating duplicate job codes in same scope fails."""
        from src.crud.cron_job import create_cron_job

        job_data = {
            "name": "Job 1",
            "code": "duplicate_code",
            "schedule_expression": "0 1 * * *",
        }

        await create_cron_job(async_session, job_data, organization_id=None)

        job_data2 = {
            "name": "Job 2",
            "code": "duplicate_code",
            "schedule_expression": "0 2 * * *",
        }

        with pytest.raises(ValueError, match="already exists"):
            await create_cron_job(async_session, job_data2, organization_id=None)

    @pytest.mark.asyncio
    async def test_get_cron_job_by_id(self, async_session):
        """Test getting a cron job by ID."""
        from src.crud.cron_job import create_cron_job, get_cron_job_by_id

        job_data = {
            "name": "Test Job",
            "code": "test_get_job",
            "schedule_expression": "0 1 * * *",
        }
        job = await create_cron_job(async_session, job_data, organization_id=None)

        retrieved = await get_cron_job_by_id(
            async_session, str(job.id), organization_id=None
        )

        assert retrieved is not None
        assert retrieved.id == job.id
        assert retrieved.code == "test_get_job"

    @pytest.mark.asyncio
    async def test_get_cron_job_by_code(self, async_session):
        """Test getting a cron job by code."""
        from src.crud.cron_job import create_cron_job, get_cron_job_by_code

        job_data = {
            "name": "Test Job",
            "code": "test_get_by_code",
            "schedule_expression": "0 1 * * *",
        }
        await create_cron_job(async_session, job_data, organization_id=None)

        retrieved = await get_cron_job_by_code(
            async_session, "test_get_by_code", organization_id=None
        )

        assert retrieved is not None
        assert retrieved.code == "test_get_by_code"

    @pytest.mark.asyncio
    async def test_get_cron_jobs_list(self, async_session):
        """Test listing cron jobs with pagination."""
        from src.crud.cron_job import create_cron_job, get_cron_jobs

        for i in range(3):
            job_data = {
                "name": f"Job {i}",
                "code": f"job_{i}",
                "schedule_expression": "0 1 * * *",
            }
            await create_cron_job(async_session, job_data, organization_id=None)

        jobs, total = await get_cron_jobs(
            async_session, organization_id=None, limit=10, offset=0
        )

        assert len(jobs) == 3
        assert total == 3

    @pytest.mark.asyncio
    async def test_get_cron_jobs_filter_active(self, async_session):
        """Test filtering cron jobs by active status."""
        from src.crud.cron_job import create_cron_job, get_cron_jobs

        active_data = {
            "name": "Active Job",
            "code": "active_job",
            "schedule_expression": "0 1 * * *",
            "is_active": True,
        }
        await create_cron_job(async_session, active_data, organization_id=None)

        inactive_data = {
            "name": "Inactive Job",
            "code": "inactive_job",
            "schedule_expression": "0 1 * * *",
            "is_active": False,
        }
        await create_cron_job(async_session, inactive_data, organization_id=None)

        active_jobs, total = await get_cron_jobs(
            async_session, organization_id=None, is_active=True
        )

        assert len(active_jobs) == 1
        assert total == 1
        assert active_jobs[0].code == "active_job"

    @pytest.mark.asyncio
    async def test_update_cron_job(self, async_session):
        """Test updating a cron job."""
        from src.crud.cron_job import create_cron_job, update_cron_job

        job_data = {
            "name": "Original Name",
            "code": "update_test",
            "schedule_expression": "0 1 * * *",
        }
        job = await create_cron_job(async_session, job_data, organization_id=None)

        update_data = {
            "name": "Updated Name",
            "is_active": False,
        }
        updated = await update_cron_job(async_session, str(job.id), None, update_data)

        assert updated is not None
        assert updated.name == "Updated Name"
        assert updated.is_active is False
        assert updated.schedule_expression == "0 1 * * *"

    @pytest.mark.asyncio
    async def test_update_schedule_recalculates_next_run(self, async_session):
        """Test that updating schedule expression recalculates next run time."""
        from src.crud.cron_job import create_cron_job, update_cron_job

        job_data = {
            "name": "Test Job",
            "code": "schedule_update",
            "schedule_expression": "0 1 * * *",
        }
        job = await create_cron_job(async_session, job_data, organization_id=None)
        original_next_run = job.next_run_time

        update_data = {
            "schedule_expression": "0 2 * * *",
        }
        updated = await update_cron_job(async_session, str(job.id), None, update_data)

        assert updated.schedule_expression == "0 2 * * *"
        assert updated.next_run_time != original_next_run

    @pytest.mark.asyncio
    async def test_soft_delete_cron_job(self, async_session):
        """Test soft deleting a cron job."""
        from src.crud.cron_job import (
            create_cron_job,
            get_cron_job_by_id,
            soft_delete_cron_job,
        )

        job_data = {
            "name": "Delete Test",
            "code": "delete_test",
            "schedule_expression": "0 1 * * *",
        }
        job = await create_cron_job(async_session, job_data, organization_id=None)

        deleted = await soft_delete_cron_job(async_session, str(job.id), None)

        assert deleted is not None
        assert deleted.deleted_time is not None

        retrieved = await get_cron_job_by_id(
            async_session, str(job.id), organization_id=None
        )
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_get_due_cron_jobs(self, async_session):
        """Test getting cron jobs that are due to run."""
        from datetime import timedelta

        from src.crud.cron_job import get_due_cron_jobs

        now = datetime.now(timezone.utc)
        past_time = now - timedelta(hours=1)

        due_job = CronJobDefinition(
            name="Due Job",
            code="due_job",
            schedule_expression="0 * * * *",
            is_active=True,
            next_run_time=past_time,
        )
        async_session.add(due_job)

        future_time = now + timedelta(hours=1)
        not_due_job = CronJobDefinition(
            name="Not Due Job",
            code="not_due_job",
            schedule_expression="0 * * * *",
            is_active=True,
            next_run_time=future_time,
        )
        async_session.add(not_due_job)

        await async_session.commit()

        due_jobs = await get_due_cron_jobs(async_session)

        assert len(due_jobs) == 1
        assert due_jobs[0].code == "due_job"

    @pytest.mark.asyncio
    async def test_calculate_next_run_time(self):
        """Test calculating next run time from cron expression."""
        from src.crud.cron_job import calculate_next_run_time

        next_run = calculate_next_run_time("0 1 * * *")

        assert next_run is not None
        assert next_run.tzinfo is not None
        assert next_run > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_is_valid_cron_expression(self):
        """Test cron expression validation."""
        from src.crud.cron_job import is_valid_cron_expression

        assert is_valid_cron_expression("0 1 * * *") is True
        assert is_valid_cron_expression("0 */2 * * *") is True
        assert is_valid_cron_expression("invalid") is False
        assert is_valid_cron_expression("* * * * * * *") is False

    @pytest.mark.asyncio
    async def test_record_execution_start(self, async_session):
        """Test recording the start of an execution."""
        from src.crud.cron_job import create_cron_job, record_execution_start

        job_data = {
            "name": "Test Job",
            "code": "exec_test",
            "schedule_expression": "0 1 * * *",
        }
        job = await create_cron_job(async_session, job_data, organization_id=None)

        execution = await record_execution_start(async_session, str(job.id))

        assert execution is not None
        assert execution.cron_job_id == job.id
        assert execution.status == CronJobStatus.RUNNING.value
        assert execution.started_at is not None

        await async_session.refresh(job)
        assert job.last_run_status == CronJobStatus.RUNNING.value

    @pytest.mark.asyncio
    async def test_record_execution_complete_success(self, async_session):
        """Test recording successful execution completion."""
        from src.crud.cron_job import (
            create_cron_job,
            record_execution_complete,
            record_execution_start,
        )

        job_data = {
            "name": "Test Job",
            "code": "exec_complete_test",
            "schedule_expression": "0 1 * * *",
        }
        job = await create_cron_job(async_session, job_data, organization_id=None)

        execution = await record_execution_start(async_session, str(job.id))

        result_data = {"processed": 100}
        completed = await record_execution_complete(
            async_session,
            str(execution.id),
            CronJobStatus.SUCCESS,
            result=result_data,
        )

        assert completed.status == CronJobStatus.SUCCESS.value
        assert completed.result == result_data
        assert completed.completed_at is not None
        assert completed.error_message is None

        await async_session.refresh(job)
        assert job.last_run_status == CronJobStatus.SUCCESS.value

    @pytest.mark.asyncio
    async def test_record_execution_complete_error(self, async_session):
        """Test recording failed execution completion."""
        from src.crud.cron_job import (
            create_cron_job,
            record_execution_complete,
            record_execution_start,
        )

        job_data = {
            "name": "Test Job",
            "code": "exec_error_test",
            "schedule_expression": "0 1 * * *",
        }
        job = await create_cron_job(async_session, job_data, organization_id=None)

        execution = await record_execution_start(async_session, str(job.id))

        error_msg = "Test error message"
        completed = await record_execution_complete(
            async_session,
            str(execution.id),
            CronJobStatus.ERROR,
            error_message=error_msg,
        )

        assert completed.status == CronJobStatus.ERROR.value
        assert completed.error_message == error_msg
        assert completed.result is None

        await async_session.refresh(job)
        assert job.last_run_status == CronJobStatus.ERROR.value
        assert job.last_run_error_message == error_msg

    @pytest.mark.asyncio
    async def test_get_executions(self, async_session):
        """Test getting execution history for a job."""
        from src.crud.cron_job import (
            create_cron_job,
            get_executions,
            record_execution_start,
        )

        job_data = {
            "name": "Test Job",
            "code": "get_exec_test",
            "schedule_expression": "0 1 * * *",
        }
        job = await create_cron_job(async_session, job_data, organization_id=None)

        await record_execution_start(async_session, str(job.id))
        await record_execution_start(async_session, str(job.id))

        executions, total = await get_executions(
            async_session, str(job.id), organization_id=None
        )

        assert len(executions) == 2
        assert total == 2

    @pytest.mark.asyncio
    async def test_get_latest_execution(self, async_session):
        """Test getting the latest execution for a job."""
        from asyncio import sleep

        from src.crud.cron_job import (
            create_cron_job,
            get_latest_execution,
            record_execution_start,
        )

        job_data = {
            "name": "Test Job",
            "code": "latest_exec_test",
            "schedule_expression": "0 1 * * *",
        }
        job = await create_cron_job(async_session, job_data, organization_id=None)

        await record_execution_start(async_session, str(job.id))
        await sleep(0.1)
        second_exec = await record_execution_start(async_session, str(job.id))

        latest = await get_latest_execution(async_session, str(job.id))

        assert latest is not None
        assert latest.id == second_exec.id


class TestCronJobCRUDMultiTenancy:
    """Tests for multi-tenancy isolation in CRUD operations."""

    @pytest.mark.asyncio
    async def test_org_user_cannot_access_other_org_job(
        self, async_session, test_organization, second_organization
    ):
        """Test that org users cannot access other org's jobs."""
        from src.crud.cron_job import create_cron_job, get_cron_job_by_id

        job_data = {
            "name": "Org 2 Job",
            "code": "org2_job",
            "schedule_expression": "0 1 * * *",
        }
        job = await create_cron_job(
            async_session, job_data, organization_id=str(second_organization.id)
        )

        retrieved = await get_cron_job_by_id(
            async_session, str(job.id), organization_id=str(test_organization.id)
        )

        assert retrieved is None

    @pytest.mark.asyncio
    async def test_org_user_can_access_platform_wide_job(
        self, async_session, test_organization
    ):
        """Test that org users can access platform-wide jobs."""
        from src.crud.cron_job import create_cron_job, get_cron_job_by_id

        job_data = {
            "name": "Platform Job",
            "code": "platform_job",
            "schedule_expression": "0 1 * * *",
        }
        job = await create_cron_job(async_session, job_data, organization_id=None)

        retrieved = await get_cron_job_by_id(
            async_session, str(job.id), organization_id=str(test_organization.id)
        )

        assert retrieved is not None
        assert retrieved.id == job.id

    @pytest.mark.asyncio
    async def test_list_includes_org_and_platform_jobs(
        self, async_session, test_organization
    ):
        """Test that listing includes both org-specific and platform-wide jobs."""
        from src.crud.cron_job import create_cron_job, get_cron_jobs

        org_job_data = {
            "name": "Org Job",
            "code": "org_job",
            "schedule_expression": "0 1 * * *",
        }
        await create_cron_job(
            async_session, org_job_data, organization_id=str(test_organization.id)
        )

        platform_job_data = {
            "name": "Platform Job",
            "code": "platform_job",
            "schedule_expression": "0 2 * * *",
        }
        await create_cron_job(async_session, platform_job_data, organization_id=None)

        jobs, total = await get_cron_jobs(
            async_session,
            organization_id=str(test_organization.id),
            include_platform_wide=True,
        )

        assert len(jobs) == 2
        assert total == 2


class TestCronJobSerializers:
    """Tests for cron job serializers."""

    def test_create_request_valid(self):
        """Test valid create request."""
        from src.serialisers.cron_job import CreateCronJobRequest

        data = {
            "name": "Test Job",
            "description": "Test description",
            "code": "test_job",
            "schedule_expression": "0 1 * * *",
            "is_active": True,
            "is_enabled_by_default_for_new_orgs": False,
            "parameters": {"key": "value"},
            "is_platform_wide": False,
        }

        request = CreateCronJobRequest(**data)

        assert request.name == "Test Job"
        assert request.code == "test_job"
        assert request.schedule_expression == "0 1 * * *"

    def test_create_request_invalid_cron_expression(self):
        """Test create request with invalid cron expression."""
        from pydantic import ValidationError

        from src.serialisers.cron_job import CreateCronJobRequest

        data = {
            "name": "Test Job",
            "code": "test_job",
            "schedule_expression": "invalid cron",
        }

        with pytest.raises(ValidationError):
            CreateCronJobRequest(**data)

    def test_create_request_invalid_code(self):
        """Test create request with invalid code."""
        from pydantic import ValidationError

        from src.serialisers.cron_job import CreateCronJobRequest

        data = {
            "name": "Test Job",
            "code": "test job!@#",
            "schedule_expression": "0 1 * * *",
        }

        with pytest.raises(ValidationError):
            CreateCronJobRequest(**data)

    def test_update_request_valid(self):
        """Test valid update request."""
        from src.serialisers.cron_job import UpdateCronJobRequest

        data = {
            "name": "Updated Name",
            "is_active": False,
        }

        request = UpdateCronJobRequest(**data)

        assert request.name == "Updated Name"
        assert request.is_active is False

    def test_update_request_invalid_cron_expression(self):
        """Test update request with invalid cron expression."""
        from pydantic import ValidationError

        from src.serialisers.cron_job import UpdateCronJobRequest

        data = {
            "schedule_expression": "invalid cron",
        }

        with pytest.raises(ValidationError):
            UpdateCronJobRequest(**data)

    @pytest.mark.asyncio
    async def test_cron_job_response_from_orm(self, async_session):
        """Test converting ORM object to response."""
        from src.serialisers.cron_job import CronJobResponse

        job = CronJobDefinition(
            name="Test Job",
            code="test_job",
            schedule_expression="0 1 * * *",
            is_active=True,
            is_enabled_by_default_for_new_orgs=False,
            parameters={"key": "value"},
            last_run_status=CronJobStatus.PENDING.value,
        )
        async_session.add(job)
        await async_session.commit()
        await async_session.refresh(job)

        response = CronJobResponse.from_orm_cron_job(job)

        assert response.name == "Test Job"
        assert response.code == "test_job"
        assert response.is_platform_wide is True

    @pytest.mark.asyncio
    async def test_execution_response_from_orm(self, async_session):
        """Test converting execution ORM object to response."""
        from src.serialisers.cron_job import CronJobExecutionResponse

        cron_job = CronJobDefinition(
            name="Test Job",
            code="test_exec_response",
            schedule_expression="0 1 * * *",
        )
        async_session.add(cron_job)
        await async_session.commit()
        await async_session.refresh(cron_job)

        execution = CronJobExecution(
            cron_job_id=cron_job.id,
            status=CronJobStatus.SUCCESS.value,
            result={"processed": 100},
        )
        async_session.add(execution)
        await async_session.commit()
        await async_session.refresh(execution)

        response = CronJobExecutionResponse.model_validate(execution)

        assert response.status == CronJobStatus.SUCCESS.value
        assert response.result == {"processed": 100}


class TestCronJobAPI:
    """Tests for cron job API endpoints."""

    @pytest.mark.asyncio
    async def test_create_cron_job_endpoint(self, admin_client, test_admin_user):
        """Test creating a cron job via API."""
        from src.core.security import create_access_token

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        data = {
            "name": "API Test Job",
            "description": "Test cron job via API",
            "code": "api_test_job",
            "schedule_expression": "0 1 * * *",
            "is_active": True,
            "is_enabled_by_default_for_new_orgs": False,
            "parameters": {"key": "value"},
            "is_platform_wide": True,
        }

        response = await admin_client.post(
            "/api/v1/cron-jobs",
            json=data,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
        json_data = response.json()
        assert json_data["name"] == "API Test Job"
        assert json_data["code"] == "api_test_job"
        assert json_data["is_platform_wide"] is True

    @pytest.mark.asyncio
    async def test_create_cron_job_requires_super_admin(self, admin_client, test_user):
        """Test creating a cron job requires super admin."""
        from src.core.security import create_access_token

        token = create_access_token(
            user_id=str(test_user.id),
            organization_id=str(test_user.organization_id),
        )

        data = {
            "name": "Unauthorized Job",
            "code": "unauthorized_job",
            "schedule_expression": "0 1 * * *",
        }

        response = await admin_client.post(
            "/api/v1/cron-jobs",
            json=data,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_cron_job_invalid_expression(
        self, admin_client, test_admin_user
    ):
        """Test creating a cron job with invalid expression fails."""
        from src.core.security import create_access_token

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        data = {
            "name": "Bad Job",
            "code": "bad_job",
            "schedule_expression": "invalid cron",
        }

        response = await admin_client.post(
            "/api/v1/cron-jobs",
            json=data,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_cron_jobs_endpoint(
        self, admin_client, test_admin_user, async_session
    ):
        """Test listing cron jobs via API."""
        from src.core.security import create_access_token
        from src.crud.cron_job import create_cron_job

        # Create test cron jobs
        await create_cron_job(
            async_session,
            {
                "name": "Job 1",
                "code": "job_1",
                "schedule_expression": "0 1 * * *",
            },
            organization_id=None,
        )
        await create_cron_job(
            async_session,
            {
                "name": "Job 2",
                "code": "job_2",
                "schedule_expression": "0 2 * * *",
            },
            organization_id=None,
        )

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        response = await admin_client.get(
            "/api/v1/cron-jobs",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["total"] == 2
        assert len(json_data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_cron_jobs_filter_active(
        self, admin_client, test_admin_user, async_session
    ):
        """Test filtering cron jobs by active status."""
        from src.core.security import create_access_token
        from src.crud.cron_job import create_cron_job

        await create_cron_job(
            async_session,
            {
                "name": "Active Job",
                "code": "active_job",
                "schedule_expression": "0 1 * * *",
                "is_active": True,
            },
            organization_id=None,
        )
        await create_cron_job(
            async_session,
            {
                "name": "Inactive Job",
                "code": "inactive_job",
                "schedule_expression": "0 2 * * *",
                "is_active": False,
            },
            organization_id=None,
        )

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        response = await admin_client.get(
            "/api/v1/cron-jobs?filter[is_active]=true",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["total"] == 1
        assert json_data["items"][0]["code"] == "active_job"

    @pytest.mark.asyncio
    async def test_get_cron_job_by_id_endpoint(
        self, admin_client, test_admin_user, async_session
    ):
        """Test getting a cron job by ID via API."""
        from src.core.security import create_access_token
        from src.crud.cron_job import create_cron_job

        job = await create_cron_job(
            async_session,
            {
                "name": "Get Test Job",
                "code": "get_test_job",
                "schedule_expression": "0 1 * * *",
            },
            organization_id=None,
        )

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        response = await admin_client.get(
            f"/api/v1/cron-jobs/{job.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["code"] == "get_test_job"

    @pytest.mark.asyncio
    async def test_get_cron_job_not_found(self, admin_client, test_admin_user):
        """Test getting a non-existent cron job returns 404."""
        import uuid

        from src.core.security import create_access_token

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        response = await admin_client.get(
            f"/api/v1/cron-jobs/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_cron_job_endpoint(
        self, admin_client, test_admin_user, async_session
    ):
        """Test updating a cron job via API."""
        from src.core.security import create_access_token
        from src.crud.cron_job import create_cron_job

        job = await create_cron_job(
            async_session,
            {
                "name": "Original Name",
                "code": "update_job",
                "schedule_expression": "0 1 * * *",
            },
            organization_id=None,
        )

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        update_data = {
            "name": "Updated Name",
            "is_active": False,
        }

        response = await admin_client.put(
            f"/api/v1/cron-jobs/{job.id}",
            json=update_data,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["name"] == "Updated Name"
        assert json_data["is_active"] is False

    @pytest.mark.asyncio
    async def test_delete_cron_job_endpoint(
        self, admin_client, test_admin_user, async_session
    ):
        """Test deleting a cron job via API."""
        from src.core.security import create_access_token
        from src.crud.cron_job import create_cron_job

        job = await create_cron_job(
            async_session,
            {
                "name": "Delete Test Job",
                "code": "delete_test_job",
                "schedule_expression": "0 1 * * *",
            },
            organization_id=None,
        )

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        response = await admin_client.delete(
            f"/api/v1/cron-jobs/{job.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_toggle_cron_job_endpoint(
        self, admin_client, test_admin_user, async_session
    ):
        """Test toggling a cron job's active status via API."""
        from src.core.security import create_access_token
        from src.crud.cron_job import create_cron_job

        job = await create_cron_job(
            async_session,
            {
                "name": "Toggle Test Job",
                "code": "toggle_test_job",
                "schedule_expression": "0 1 * * *",
                "is_active": True,
            },
            organization_id=None,
        )

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        toggle_data = {"is_active": False}

        response = await admin_client.patch(
            f"/api/v1/cron-jobs/{job.id}/toggle",
            json=toggle_data,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["is_active"] is False

    @pytest.mark.asyncio
    async def test_trigger_cron_job_endpoint(
        self, admin_client, test_admin_user, async_session
    ):
        """Test manually triggering a cron job via API."""
        from src.core.security import create_access_token
        from src.crud.cron_job import create_cron_job
        from src.services.cron_scheduler import cron_scheduler_service

        # Register a test handler for this job
        async def test_handler(session, params):
            return {"status": "success", "message": "Test job executed"}

        cron_scheduler_service.register_job("trigger_test_job", test_handler)

        try:
            job = await create_cron_job(
                async_session,
                {
                    "name": "Trigger Test Job",
                    "code": "trigger_test_job",
                    "schedule_expression": "0 1 * * *",
                },
                organization_id=None,
            )

            token = create_access_token(
                user_id=str(test_admin_user.id),
                organization_id=str(test_admin_user.organization_id),
            )

            response = await admin_client.post(
                f"/api/v1/cron-jobs/{job.id}/trigger",
                json={},
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == 202
            json_data = response.json()
            assert "execution_id" in json_data
        finally:
            # Clean up - remove the test handler
            if "trigger_test_job" in cron_scheduler_service._job_registry:
                del cron_scheduler_service._job_registry["trigger_test_job"]

    @pytest.mark.asyncio
    async def test_get_cron_job_executions_endpoint(
        self, admin_client, test_admin_user, async_session
    ):
        """Test getting execution history for a cron job via API."""
        from src.core.security import create_access_token
        from src.crud.cron_job import create_cron_job, record_execution_start

        job = await create_cron_job(
            async_session,
            {
                "name": "Exec History Job",
                "code": "exec_history_job",
                "schedule_expression": "0 1 * * *",
            },
            organization_id=None,
        )

        await record_execution_start(async_session, str(job.id))
        await record_execution_start(async_session, str(job.id))

        token = create_access_token(
            user_id=str(test_admin_user.id),
            organization_id=str(test_admin_user.organization_id),
        )

        response = await admin_client.get(
            f"/api/v1/cron-jobs/{job.id}/executions",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["total"] == 2
        assert len(json_data["items"]) == 2


class TestCronSchedulerService:
    """Tests for CronSchedulerService."""

    @pytest.mark.asyncio
    async def test_calculate_next_run_from_expression(self):
        """Test calculating next run time from cron expression."""
        from datetime import datetime, timezone

        from src.services.cron_scheduler import cron_scheduler_service

        base_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        # Test daily at 2 AM
        next_run = cron_scheduler_service.calculate_next_run_from_expression(
            "0 2 * * *", base_time
        )
        assert next_run.hour == 2
        assert next_run.minute == 0
        assert next_run > base_time

        # Test every hour
        next_run = cron_scheduler_service.calculate_next_run_from_expression(
            "0 * * * *", base_time
        )
        assert next_run.minute == 0
        assert next_run > base_time

        # Test every 15 minutes
        next_run = cron_scheduler_service.calculate_next_run_from_expression(
            "*/15 * * * *", base_time
        )
        assert next_run.minute in [0, 15, 30, 45]
        assert next_run > base_time

    @pytest.mark.asyncio
    async def test_calculate_next_run_invalid_expression(self):
        """Test that invalid cron expression raises ValueError."""
        from src.services.cron_scheduler import cron_scheduler_service

        with pytest.raises(ValueError, match="Invalid cron expression"):
            cron_scheduler_service.calculate_next_run_from_expression("invalid")

        with pytest.raises(ValueError, match="Invalid cron expression"):
            cron_scheduler_service.calculate_next_run_from_expression("60 * * * *")

    @pytest.mark.asyncio
    async def test_register_job_handler(self):
        """Test registering a job handler."""
        from src.services.cron_scheduler import cron_scheduler_service

        async def test_handler(session, parameters):
            return {"status": "completed"}

        cron_scheduler_service.register_job("test_job", test_handler)
        assert "test_job" in cron_scheduler_service._job_registry

    @pytest.mark.asyncio
    async def test_check_and_execute_due_jobs_no_jobs(self, async_session):
        """Test scheduler when no jobs are due."""
        from src.services.cron_scheduler import cron_scheduler_service

        result = await cron_scheduler_service.check_and_execute_due_jobs(async_session)

        assert result["status"] == "completed"
        assert result["jobs_checked"] == 0
        assert result["jobs_executed"] == 0
        assert result["jobs_failed"] == 0

    @pytest.mark.asyncio
    async def test_execute_cron_job_success(self, async_session):
        """Test successful execution of a cron job."""
        from src.crud.cron_job import create_cron_job, get_latest_execution
        from src.models.cron_job import CronJobStatus
        from src.services.cron_scheduler import cron_scheduler_service

        # Register a test handler
        async def test_handler(session, parameters):
            return {"status": "completed", "items_processed": 10}

        cron_scheduler_service.register_job("test_success_job", test_handler)

        # Create a cron job
        job = await create_cron_job(
            async_session,
            {
                "name": "Test Success Job",
                "code": "test_success_job",
                "schedule_expression": "0 * * * *",
                "is_active": True,
            },
            organization_id=None,
        )

        # Execute the job
        await cron_scheduler_service.execute_cron_job(
            async_session,
            job_id=str(job.id),
            job_code=job.code,
            job_parameters=job.parameters or {},
        )

        # Check execution was recorded
        execution = await get_latest_execution(async_session, str(job.id))
        assert execution is not None
        assert execution.status == CronJobStatus.SUCCESS.value
        assert execution.result["status"] == "completed"
        assert execution.result["items_processed"] == 10
        assert execution.completed_at is not None

        # Check job was updated
        await async_session.refresh(job)
        assert job.last_run_status == CronJobStatus.SUCCESS.value
        assert job.last_run_time is not None

    @pytest.mark.asyncio
    async def test_execute_cron_job_handler_error(self, async_session):
        """Test cron job execution when handler raises error."""
        from src.crud.cron_job import create_cron_job, get_latest_execution
        from src.models.cron_job import CronJobStatus
        from src.services.cron_scheduler import cron_scheduler_service

        # Register a failing handler
        async def failing_handler(session, parameters):
            raise RuntimeError("Test error message")

        cron_scheduler_service.register_job("test_failing_job", failing_handler)

        # Create a cron job
        job = await create_cron_job(
            async_session,
            {
                "name": "Test Failing Job",
                "code": "test_failing_job",
                "schedule_expression": "0 * * * *",
                "is_active": True,
            },
            organization_id=None,
        )

        # Execute should raise error
        with pytest.raises(RuntimeError, match="Test error message"):
            await cron_scheduler_service.execute_cron_job(
                async_session,
                job_id=str(job.id),
                job_code=job.code,
                job_parameters=job.parameters or {},
            )

        # Check error was recorded
        execution = await get_latest_execution(async_session, str(job.id))
        assert execution is not None
        assert execution.status == CronJobStatus.ERROR.value
        assert "Test error message" in execution.error_message
        assert execution.completed_at is not None

        # Check job was updated with error
        await async_session.refresh(job)
        assert job.last_run_status == CronJobStatus.ERROR.value

    @pytest.mark.asyncio
    async def test_execute_cron_job_no_handler(self, async_session):
        """Test execution when no handler is registered."""
        from src.crud.cron_job import create_cron_job, get_latest_execution
        from src.models.cron_job import CronJobStatus
        from src.services.cron_scheduler import cron_scheduler_service

        # Create a cron job with unregistered code
        job = await create_cron_job(
            async_session,
            {
                "name": "Unregistered Job",
                "code": "unregistered_job_code",
                "schedule_expression": "0 * * * *",
                "is_active": True,
            },
            organization_id=None,
        )

        # Execute should not raise but record error
        await cron_scheduler_service.execute_cron_job(
            async_session,
            job_id=str(job.id),
            job_code=job.code,
            job_parameters=job.parameters or {},
        )

        # Check error was recorded
        execution = await get_latest_execution(async_session, str(job.id))
        assert execution is not None
        assert execution.status == CronJobStatus.ERROR.value
        assert "No handler registered" in execution.error_message

    @pytest.mark.asyncio
    async def test_check_and_execute_due_jobs_multiple(self, async_session):
        """Test scheduler executing multiple due jobs."""
        from datetime import datetime, timedelta, timezone

        from src.crud.cron_job import create_cron_job
        from src.services.cron_scheduler import cron_scheduler_service

        # Register handlers
        async def handler1(session, parameters):
            return {"job": "handler1"}

        async def handler2(session, parameters):
            return {"job": "handler2"}

        cron_scheduler_service.register_job("multi_job_1", handler1)
        cron_scheduler_service.register_job("multi_job_2", handler2)

        # Create jobs with next_run_time in the past
        past_time = datetime.now(timezone.utc) - timedelta(minutes=5)

        job1 = await create_cron_job(
            async_session,
            {
                "name": "Multi Job 1",
                "code": "multi_job_1",
                "schedule_expression": "0 * * * *",
                "is_active": True,
            },
            organization_id=None,
        )
        job1.next_run_time = past_time

        job2 = await create_cron_job(
            async_session,
            {
                "name": "Multi Job 2",
                "code": "multi_job_2",
                "schedule_expression": "0 * * * *",
                "is_active": True,
            },
            organization_id=None,
        )
        job2.next_run_time = past_time

        await async_session.commit()

        # Execute scheduler
        result = await cron_scheduler_service.check_and_execute_due_jobs(async_session)

        assert result["status"] == "completed"
        assert result["jobs_checked"] == 2
        assert result["jobs_executed"] == 2
        assert result["jobs_failed"] == 0


class TestCronExpressionParsing:
    """Tests for cron expression parsing and validation."""

    @pytest.mark.asyncio
    async def test_calculate_next_run_time_crud(self):
        """Test calculate_next_run_time function in CRUD."""
        from datetime import datetime, timezone

        from src.crud.cron_job import calculate_next_run_time

        # Daily at 2 AM
        next_run = calculate_next_run_time("0 2 * * *")
        assert isinstance(next_run, datetime)
        assert next_run.tzinfo is not None
        assert next_run > datetime.now(timezone.utc)

        # Every Monday at 9 AM
        next_run = calculate_next_run_time("0 9 * * MON")
        assert isinstance(next_run, datetime)
        assert next_run.weekday() == 0  # Monday

        # Every 5 minutes
        next_run = calculate_next_run_time("*/5 * * * *")
        assert isinstance(next_run, datetime)
        assert next_run.minute % 5 == 0

    @pytest.mark.asyncio
    async def test_is_valid_cron_expression(self):
        """Test cron expression validation."""
        from src.crud.cron_job import is_valid_cron_expression

        # Valid expressions
        assert is_valid_cron_expression("0 2 * * *") is True
        assert is_valid_cron_expression("0 */2 * * *") is True
        assert is_valid_cron_expression("*/5 * * * *") is True
        assert is_valid_cron_expression("0 9 * * MON") is True
        assert is_valid_cron_expression("0 0 1 * *") is True

        # Invalid expressions
        assert is_valid_cron_expression("invalid") is False
        assert is_valid_cron_expression("60 * * * *") is False
        assert is_valid_cron_expression("* * * *") is False
        assert is_valid_cron_expression("0 25 * * *") is False

    @pytest.mark.asyncio
    async def test_calculate_next_run_time_invalid(self):
        """Test calculate_next_run_time with invalid expression."""
        from src.crud.cron_job import calculate_next_run_time

        with pytest.raises(ValueError, match="Invalid cron expression"):
            calculate_next_run_time("invalid expression")

        with pytest.raises(ValueError, match="Invalid cron expression"):
            calculate_next_run_time("60 25 * * *")
