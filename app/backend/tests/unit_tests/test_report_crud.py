"""
Unit tests for report CRUD operations.
Tests report creation, retrieval, status updates, and tenant isolation.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.core.query_params import FilterOperator, FilterSpec
from src.crud.report import (
    create_report,
    get_report_by_id,
    get_reports_list,
    soft_delete_report,
    update_report_status,
)
from src.models.report import ReportStatus


@pytest.mark.asyncio
async def test_create_report(async_session, test_organization, test_user):
    """Test creating a report record."""
    report = await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Monthly Users Report",
        generated_by_user_id=str(test_user.id),
        description="Report of all users in the organization",
        parameters={"include_suspended": True},
    )

    assert report.id is not None
    assert str(report.organization_id) == str(test_organization.id)
    assert report.report_type == "users_report"
    assert report.name == "Monthly Users Report"
    assert str(report.generated_by_user_id) == str(test_user.id)
    assert report.description == "Report of all users in the organization"
    assert report.parameters == {"include_suspended": True}
    assert report.status == ReportStatus.PENDING.value


@pytest.mark.asyncio
async def test_create_report_without_user(async_session, test_organization):
    """Test creating a report without a user (system generated)."""
    report = await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="System Generated Report",
        generated_by_user_id=None,
    )

    assert report.id is not None
    assert report.generated_by_user_id is None
    assert report.status == ReportStatus.PENDING.value


@pytest.mark.asyncio
async def test_create_report_minimal(async_session, test_organization):
    """Test creating a report with minimal required fields."""
    report = await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Basic Report",
    )

    assert report.id is not None
    assert report.description is None
    assert report.parameters is None


@pytest.mark.asyncio
async def test_get_report_by_id(async_session, test_organization, test_user):
    """Test retrieving a report by ID."""
    created_report = await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Test Report",
        generated_by_user_id=str(test_user.id),
    )

    fetched_report = await get_report_by_id(
        session=async_session,
        report_id=str(created_report.id),
        organization_id=str(test_organization.id),
    )

    assert fetched_report is not None
    assert fetched_report.id == created_report.id
    assert fetched_report.name == "Test Report"


@pytest.mark.asyncio
async def test_get_report_by_id_not_found(async_session, test_organization):
    """Test that get_report_by_id returns None for non-existent report."""
    fetched_report = await get_report_by_id(
        session=async_session,
        report_id=str(uuid4()),
        organization_id=str(test_organization.id),
    )

    assert fetched_report is None


@pytest.mark.asyncio
async def test_get_report_by_id_wrong_org(
    async_session, test_organization, second_organization
):
    """Test that reports are isolated by organization."""
    created_report = await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Org 1 Report",
    )

    # Try to fetch with wrong organization
    fetched_report = await get_report_by_id(
        session=async_session,
        report_id=str(created_report.id),
        organization_id=str(second_organization.id),
    )

    assert fetched_report is None


@pytest.mark.asyncio
async def test_get_reports_list(async_session, test_organization):
    """Test retrieving a list of reports with pagination."""
    # Create multiple reports
    for i in range(5):
        await create_report(
            session=async_session,
            organization_id=str(test_organization.id),
            report_type="users_report",
            name=f"Report {i}",
        )

    reports, total = await get_reports_list(
        session=async_session,
        organization_id=str(test_organization.id),
        limit=3,
        offset=0,
    )

    assert len(reports) == 3
    assert total == 5


@pytest.mark.asyncio
async def test_get_reports_list_filter_by_type(async_session, test_organization):
    """Test filtering reports by type."""
    await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Users Report 1",
    )
    await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="activity_report",
        name="Activity Report 1",
    )

    reports, total = await get_reports_list(
        session=async_session,
        organization_id=str(test_organization.id),
        filters=[
            FilterSpec(
                field="report_type", operator=FilterOperator.EQ, value="users_report"
            )
        ],
    )

    assert total == 1
    assert all(r.report_type == "users_report" for r in reports)


@pytest.mark.asyncio
async def test_get_reports_list_filter_by_status(async_session, test_organization):
    """Test filtering reports by status."""
    report1 = await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Report 1",
    )
    await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Report 2",
    )

    # Update one report to completed status
    await update_report_status(
        session=async_session,
        report_id=str(report1.id),
        organization_id=str(test_organization.id),
        status=ReportStatus.COMPLETED.value,
    )

    reports, total = await get_reports_list(
        session=async_session,
        organization_id=str(test_organization.id),
        filters=[
            FilterSpec(field="status", operator=FilterOperator.EQ, value="completed")
        ],
    )

    assert total == 1
    assert reports[0].status == "completed"


@pytest.mark.asyncio
async def test_get_reports_list_ordered_by_created_time(
    async_session, test_organization
):
    """Test that reports are ordered by created_time descending by default."""
    report1 = await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Report 1",
    )
    report2 = await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Report 2",
    )
    report3 = await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Report 3",
    )

    reports, _ = await get_reports_list(
        session=async_session,
        organization_id=str(test_organization.id),
    )

    # Most recent should be first
    assert reports[0].id == report3.id
    assert reports[1].id == report2.id
    assert reports[2].id == report1.id


@pytest.mark.asyncio
async def test_update_report_status_to_processing(async_session, test_organization):
    """Test updating report status to processing."""
    report = await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Test Report",
    )

    started = datetime.now(timezone.utc)
    updated_report = await update_report_status(
        session=async_session,
        report_id=str(report.id),
        organization_id=str(test_organization.id),
        status=ReportStatus.PROCESSING.value,
        started_at=started,
    )

    assert updated_report is not None
    assert updated_report.status == "processing"
    assert updated_report.started_at is not None


@pytest.mark.asyncio
async def test_update_report_status_to_completed(async_session, test_organization):
    """Test updating report status to completed with file and row count."""
    report = await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Test Report",
    )

    completed_time = datetime.now(timezone.utc)
    file_id = str(uuid4())

    updated_report = await update_report_status(
        session=async_session,
        report_id=str(report.id),
        organization_id=str(test_organization.id),
        status=ReportStatus.COMPLETED.value,
        file_id=file_id,
        row_count=150,
        completed_at=completed_time,
    )

    assert updated_report is not None
    assert updated_report.status == "completed"
    assert str(updated_report.file_id) == file_id
    assert updated_report.row_count == 150
    assert updated_report.completed_at is not None


@pytest.mark.asyncio
async def test_update_report_status_to_failed(async_session, test_organization):
    """Test updating report status to failed with error message."""
    report = await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Test Report",
    )

    updated_report = await update_report_status(
        session=async_session,
        report_id=str(report.id),
        organization_id=str(test_organization.id),
        status=ReportStatus.FAILED.value,
        error_message="Database connection timeout",
        completed_at=datetime.now(timezone.utc),
    )

    assert updated_report is not None
    assert updated_report.status == "failed"
    assert updated_report.error_message == "Database connection timeout"


@pytest.mark.asyncio
async def test_update_report_status_not_found(async_session, test_organization):
    """Test updating status of non-existent report."""
    result = await update_report_status(
        session=async_session,
        report_id=str(uuid4()),
        organization_id=str(test_organization.id),
        status=ReportStatus.COMPLETED.value,
    )

    assert result is None


@pytest.mark.asyncio
async def test_update_report_status_wrong_org(
    async_session, test_organization, second_organization
):
    """Test that status update respects tenant isolation."""
    report = await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Test Report",
    )

    # Try to update with wrong organization
    result = await update_report_status(
        session=async_session,
        report_id=str(report.id),
        organization_id=str(second_organization.id),
        status=ReportStatus.COMPLETED.value,
    )

    assert result is None


@pytest.mark.asyncio
async def test_soft_delete_report(async_session, test_organization):
    """Test soft deleting a report."""
    report = await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Test Report",
    )

    deleted_report = await soft_delete_report(
        session=async_session,
        report_id=str(report.id),
        organization_id=str(test_organization.id),
    )

    assert deleted_report is not None
    assert deleted_report.deleted_time is not None

    # Report should not be retrievable after soft delete
    fetched_report = await get_report_by_id(
        session=async_session,
        report_id=str(report.id),
        organization_id=str(test_organization.id),
    )
    assert fetched_report is None


@pytest.mark.asyncio
async def test_soft_delete_report_not_found(async_session, test_organization):
    """Test soft deleting a non-existent report."""
    result = await soft_delete_report(
        session=async_session,
        report_id=str(uuid4()),
        organization_id=str(test_organization.id),
    )

    assert result is None


@pytest.mark.asyncio
async def test_soft_delete_report_wrong_org(
    async_session, test_organization, second_organization
):
    """Test that soft delete respects tenant isolation."""
    report = await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Test Report",
    )

    # Try to delete with wrong organization
    result = await soft_delete_report(
        session=async_session,
        report_id=str(report.id),
        organization_id=str(second_organization.id),
    )

    assert result is None

    # Report should still exist
    fetched_report = await get_report_by_id(
        session=async_session,
        report_id=str(report.id),
        organization_id=str(test_organization.id),
    )
    assert fetched_report is not None


@pytest.mark.asyncio
async def test_deleted_reports_excluded_from_list(async_session, test_organization):
    """Test that soft deleted reports are excluded from list queries."""
    # Create two reports
    report1 = await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Report 1",
    )
    await create_report(
        session=async_session,
        organization_id=str(test_organization.id),
        report_type="users_report",
        name="Report 2",
    )

    # Soft delete first report
    await soft_delete_report(
        session=async_session,
        report_id=str(report1.id),
        organization_id=str(test_organization.id),
    )

    # List should only show non-deleted report
    reports, total = await get_reports_list(
        session=async_session,
        organization_id=str(test_organization.id),
    )

    assert total == 1
    assert all(r.deleted_time is None for r in reports)
