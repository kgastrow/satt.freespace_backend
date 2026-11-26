"""
Unit tests for report schedule CRUD operations.
Tests schedule creation, retrieval, updates, and tenant isolation.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.core.query_params import FilterOperator, FilterSpec
from src.crud.report_schedule import (
    calculate_next_run_time,
    create_report_schedule,
    get_due_report_schedules,
    get_report_schedule_by_id,
    get_report_schedules_list,
    soft_delete_report_schedule,
    update_report_schedule,
    update_schedule_run_status,
)


def test_calculate_next_run_time():
    """Test that next run time is calculated correctly from cron expression."""
    # Every minute
    next_time = calculate_next_run_time("* * * * *")
    now = datetime.now(timezone.utc)
    # Should be within 2 minutes from now
    assert next_time > now
    assert next_time < now + timedelta(minutes=2)


def test_calculate_next_run_time_daily():
    """Test daily schedule next run time calculation."""
    # Every day at midnight
    next_time = calculate_next_run_time("0 0 * * *")
    now = datetime.now(timezone.utc)
    # Should be within 24 hours
    assert next_time > now
    assert next_time < now + timedelta(days=1, hours=1)


@pytest.mark.asyncio
async def test_create_report_schedule(async_session, test_organization, test_user):
    """Test creating a report schedule."""
    schedule = await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Weekly Users Report",
        schedule_expression="0 8 * * 1",  # Every Monday at 8am
        recipients=["admin@example.com", "manager@example.com"],
        created_by_user_id=str(test_user.id),
        description="Weekly report of all users",
        parameters={"include_suspended": False},
    )

    assert schedule.id is not None
    assert str(schedule.organization_id) == str(test_organization.id)
    assert schedule.report_type == "users_report"
    assert schedule.name == "Weekly Users Report"
    assert str(schedule.created_by_user_id) == str(test_user.id)
    assert schedule.schedule_expression == "0 8 * * 1"
    assert schedule.recipients == ["admin@example.com", "manager@example.com"]
    assert schedule.is_active is True
    assert schedule.next_run_time is not None


@pytest.mark.asyncio
async def test_create_report_schedule_minimal(async_session, test_organization):
    """Test creating a schedule with minimal fields."""
    schedule = await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Basic Schedule",
        schedule_expression="0 0 * * *",
        recipients=["test@example.com"],
    )

    assert schedule.id is not None
    assert schedule.created_by_user_id is None
    assert schedule.description is None
    assert schedule.parameters is None


@pytest.mark.asyncio
async def test_get_report_schedule_by_id(async_session, test_organization, test_user):
    """Test retrieving a schedule by ID."""
    created_schedule = await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Test Schedule",
        schedule_expression="0 0 * * *",
        recipients=["test@example.com"],
        created_by_user_id=str(test_user.id),
    )

    fetched_schedule = await get_report_schedule_by_id(
        session=async_session,
        schedule_id=str(created_schedule.id),
        organization_id=str(test_organization.id),
    )

    assert fetched_schedule is not None
    assert fetched_schedule.id == created_schedule.id
    assert fetched_schedule.name == "Test Schedule"


@pytest.mark.asyncio
async def test_get_report_schedule_by_id_not_found(async_session, test_organization):
    """Test that get_report_schedule_by_id returns None for non-existent schedule."""
    fetched_schedule = await get_report_schedule_by_id(
        session=async_session,
        schedule_id=str(uuid4()),
        organization_id=str(test_organization.id),
    )

    assert fetched_schedule is None


@pytest.mark.asyncio
async def test_get_report_schedule_by_id_wrong_org(
    async_session, test_organization, second_organization
):
    """Test that schedules are isolated by organization."""
    created_schedule = await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Org 1 Schedule",
        schedule_expression="0 0 * * *",
        recipients=["test@example.com"],
    )

    # Try to fetch with wrong organization
    fetched_schedule = await get_report_schedule_by_id(
        session=async_session,
        schedule_id=str(created_schedule.id),
        organization_id=str(second_organization.id),
    )

    assert fetched_schedule is None


@pytest.mark.asyncio
async def test_get_report_schedules_list(async_session, test_organization):
    """Test retrieving a list of schedules with pagination."""
    # Create multiple schedules
    for i in range(5):
        await create_report_schedule(
            session=async_session,
            organization_id=str(test_organization.id),
            report_type="users_report",
            name=f"Schedule {i}",
            schedule_expression="0 0 * * *",
            recipients=["test@example.com"],
        )

    schedules, total = await get_report_schedules_list(
        session=async_session,
        organization_id=str(test_organization.id),
        limit=3,
        offset=0,
    )

    assert len(schedules) == 3
    assert total == 5


@pytest.mark.asyncio
async def test_get_report_schedules_list_filter_by_type(
    async_session, test_organization
):
    """Test filtering schedules by type."""
    await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Users Schedule",
        schedule_expression="0 0 * * *",
        recipients=["test@example.com"],
    )
    await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="activity_report",
        name="Activity Schedule",
        schedule_expression="0 0 * * *",
        recipients=["test@example.com"],
    )

    schedules, total = await get_report_schedules_list(
        session=async_session,
        organization_id=str(test_organization.id),
        filters=[
            FilterSpec(
                field="report_type", operator=FilterOperator.EQ, value="users_report"
            )
        ],
    )

    assert total == 1
    assert all(s.report_type == "users_report" for s in schedules)


@pytest.mark.asyncio
async def test_get_report_schedules_list_filter_by_active(
    async_session, test_organization
):
    """Test filtering schedules by active status."""
    schedule1 = await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Active Schedule",
        schedule_expression="0 0 * * *",
        recipients=["test@example.com"],
    )
    schedule2 = await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Inactive Schedule",
        schedule_expression="0 0 * * *",
        recipients=["test@example.com"],
    )

    # Deactivate second schedule
    await update_report_schedule(
        session=async_session,
        schedule_id=str(schedule2.id),
        organization_id=str(test_organization.id),
        update_data={"is_active": False},
    )

    schedules, total = await get_report_schedules_list(
        session=async_session,
        organization_id=str(test_organization.id),
        filters=[FilterSpec(field="is_active", operator=FilterOperator.EQ, value=True)],
    )

    assert total == 1
    assert schedules[0].id == schedule1.id


@pytest.mark.asyncio
async def test_update_report_schedule_name(async_session, test_organization):
    """Test updating schedule name."""
    schedule = await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Original Name",
        schedule_expression="0 0 * * *",
        recipients=["test@example.com"],
    )

    updated_schedule = await update_report_schedule(
        session=async_session,
        schedule_id=str(schedule.id),
        organization_id=str(test_organization.id),
        update_data={"name": "New Name"},
    )

    assert updated_schedule is not None
    assert updated_schedule.name == "New Name"


@pytest.mark.asyncio
async def test_update_report_schedule_expression(async_session, test_organization):
    """Test updating schedule expression recalculates next_run_time."""
    schedule = await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Test Schedule",
        schedule_expression="0 0 * * *",  # Daily at midnight
        recipients=["test@example.com"],
    )

    original_next_run = schedule.next_run_time

    updated_schedule = await update_report_schedule(
        session=async_session,
        schedule_id=str(schedule.id),
        organization_id=str(test_organization.id),
        update_data={"schedule_expression": "0 12 * * *"},  # Daily at noon
    )

    assert updated_schedule is not None
    assert updated_schedule.schedule_expression == "0 12 * * *"
    # Next run time should be recalculated
    assert updated_schedule.next_run_time != original_next_run


@pytest.mark.asyncio
async def test_update_report_schedule_recipients(async_session, test_organization):
    """Test updating schedule recipients."""
    schedule = await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Test Schedule",
        schedule_expression="0 0 * * *",
        recipients=["old@example.com"],
    )

    updated_schedule = await update_report_schedule(
        session=async_session,
        schedule_id=str(schedule.id),
        organization_id=str(test_organization.id),
        update_data={"recipients": ["new@example.com", "another@example.com"]},
    )

    assert updated_schedule is not None
    assert updated_schedule.recipients == ["new@example.com", "another@example.com"]


@pytest.mark.asyncio
async def test_update_report_schedule_deactivate(async_session, test_organization):
    """Test deactivating a schedule."""
    schedule = await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Test Schedule",
        schedule_expression="0 0 * * *",
        recipients=["test@example.com"],
    )

    updated_schedule = await update_report_schedule(
        session=async_session,
        schedule_id=str(schedule.id),
        organization_id=str(test_organization.id),
        update_data={"is_active": False},
    )

    assert updated_schedule is not None
    assert updated_schedule.is_active is False


@pytest.mark.asyncio
async def test_update_report_schedule_not_found(async_session, test_organization):
    """Test updating non-existent schedule."""
    result = await update_report_schedule(
        session=async_session,
        schedule_id=str(uuid4()),
        organization_id=str(test_organization.id),
        update_data={"name": "New Name"},
    )

    assert result is None


@pytest.mark.asyncio
async def test_update_report_schedule_wrong_org(
    async_session, test_organization, second_organization
):
    """Test that update respects tenant isolation."""
    schedule = await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Test Schedule",
        schedule_expression="0 0 * * *",
        recipients=["test@example.com"],
    )

    # Try to update with wrong organization
    result = await update_report_schedule(
        session=async_session,
        schedule_id=str(schedule.id),
        organization_id=str(second_organization.id),
        update_data={"name": "Hacked Name"},
    )

    assert result is None


@pytest.mark.asyncio
async def test_soft_delete_report_schedule(async_session, test_organization):
    """Test soft deleting a schedule."""
    schedule = await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Test Schedule",
        schedule_expression="0 0 * * *",
        recipients=["test@example.com"],
    )

    deleted_schedule = await soft_delete_report_schedule(
        session=async_session,
        schedule_id=str(schedule.id),
        organization_id=str(test_organization.id),
    )

    assert deleted_schedule is not None
    assert deleted_schedule.deleted_time is not None
    assert deleted_schedule.is_active is False

    # Schedule should not be retrievable after soft delete
    fetched_schedule = await get_report_schedule_by_id(
        session=async_session,
        schedule_id=str(schedule.id),
        organization_id=str(test_organization.id),
    )
    assert fetched_schedule is None


@pytest.mark.asyncio
async def test_get_due_report_schedules(async_session, test_organization):
    """Test getting schedules that are due to run."""
    # Create a schedule with next_run_time in the past
    schedule = await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Due Schedule",
        schedule_expression="* * * * *",  # Every minute
        recipients=["test@example.com"],
    )

    # Manually set next_run_time to past
    from sqlalchemy import update

    from src.models.report_schedule import ReportSchedule

    past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    await async_session.execute(
        update(ReportSchedule)
        .where(ReportSchedule.id == schedule.id)
        .values(next_run_time=past_time)
    )
    await async_session.commit()

    # Get due schedules
    due_schedules = await get_due_report_schedules(
        session=async_session,
        current_time=datetime.now(timezone.utc),
    )

    assert len(due_schedules) >= 1
    assert any(s.id == schedule.id for s in due_schedules)


@pytest.mark.asyncio
async def test_get_due_report_schedules_excludes_inactive(
    async_session, test_organization
):
    """Test that inactive schedules are not returned as due."""
    schedule = await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Inactive Schedule",
        schedule_expression="* * * * *",
        recipients=["test@example.com"],
    )

    # Deactivate the schedule
    await update_report_schedule(
        session=async_session,
        schedule_id=str(schedule.id),
        organization_id=str(test_organization.id),
        update_data={"is_active": False},
    )

    # Manually set next_run_time to past
    from sqlalchemy import update

    from src.models.report_schedule import ReportSchedule

    past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    await async_session.execute(
        update(ReportSchedule)
        .where(ReportSchedule.id == schedule.id)
        .values(next_run_time=past_time)
    )
    await async_session.commit()

    # Get due schedules
    due_schedules = await get_due_report_schedules(
        session=async_session,
        current_time=datetime.now(timezone.utc),
    )

    assert not any(s.id == schedule.id for s in due_schedules)


@pytest.mark.asyncio
async def test_update_schedule_run_status_success(async_session, test_organization):
    """Test updating schedule run status after successful execution."""
    schedule = await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Test Schedule",
        schedule_expression="0 0 * * *",
        recipients=["test@example.com"],
    )

    updated_schedule = await update_schedule_run_status(
        session=async_session,
        schedule_id=str(schedule.id),
        status="success",
    )

    assert updated_schedule is not None
    assert updated_schedule.last_run_time is not None
    assert updated_schedule.last_run_status == "success"
    assert updated_schedule.last_run_error_message is None
    # Next run time should be set (recalculated)
    assert updated_schedule.next_run_time is not None


@pytest.mark.asyncio
async def test_update_schedule_run_status_error(async_session, test_organization):
    """Test updating schedule run status after failed execution."""
    schedule = await create_report_schedule(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Test Schedule",
        schedule_expression="0 0 * * *",
        recipients=["test@example.com"],
    )

    updated_schedule = await update_schedule_run_status(
        session=async_session,
        schedule_id=str(schedule.id),
        status="error",
        error_message="Database connection failed",
    )

    assert updated_schedule is not None
    assert updated_schedule.last_run_status == "error"
    assert updated_schedule.last_run_error_message == "Database connection failed"


@pytest.mark.asyncio
async def test_update_schedule_run_status_not_found(async_session):
    """Test updating run status of non-existent schedule."""
    result = await update_schedule_run_status(
        session=async_session,
        schedule_id=str(uuid4()),
        status="success",
    )

    assert result is None
