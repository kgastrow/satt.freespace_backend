"""
API tests for report management endpoints.
Tests report creation, listing, retrieval, and deletion with permissions.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from httpx import AsyncClient
import pytest

from src.models.report import Report, ReportStatus
from src.models.report_schedule import ReportSchedule


# ============================================================================
# Fixtures for Report Testing
# ============================================================================


@pytest.fixture
async def test_report(async_session, test_organization, test_user):
    """Create a test report record."""
    report = Report(
        organization_id=test_organization.id,
        generated_by_user_id=test_user.id,
        report_type="users_report",
        name="Test Users Report",
        description="A test report",
        status=ReportStatus.COMPLETED.value,
        row_count=100,
    )
    async_session.add(report)
    await async_session.commit()
    await async_session.refresh(report)
    return report


@pytest.fixture
async def multiple_test_reports(async_session, test_organization, test_user):
    """Create multiple test report records."""
    reports = []
    statuses = [
        ReportStatus.PENDING.value,
        ReportStatus.PROCESSING.value,
        ReportStatus.COMPLETED.value,
        ReportStatus.FAILED.value,
    ]

    for i, status in enumerate(statuses):
        report = Report(
            organization_id=test_organization.id,
            generated_by_user_id=test_user.id,
            report_type="users_report" if i % 2 == 0 else "activity_report",
            name=f"Report {i + 1}",
            status=status,
            row_count=i * 10 if status == ReportStatus.COMPLETED.value else None,
        )
        async_session.add(report)
        reports.append(report)

    await async_session.commit()
    for r in reports:
        await async_session.refresh(r)
    return reports


@pytest.fixture
async def test_report_schedule(async_session, test_organization, test_user):
    """Create a test report schedule record."""
    from datetime import datetime, timedelta, timezone

    schedule = ReportSchedule(
        organization_id=test_organization.id,
        created_by_user_id=test_user.id,
        report_type="users_report",
        name="Weekly Users Report",
        schedule_expression="0 8 * * 1",
        recipients=["admin@example.com"],
        is_active=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(days=1),
    )
    async_session.add(schedule)
    await async_session.commit()
    await async_session.refresh(schedule)
    return schedule


# ============================================================================
# User with Permissions Fixtures
# ============================================================================


@pytest.fixture
async def user_with_reports_read(
    async_session, test_organization, test_user, test_role
):
    """Create a user with reports:read permission."""
    from sqlalchemy import select

    from src.models.permission import Permission
    from src.models.role_permission import RolePermission
    from src.models.user_role import UserRole

    # Find or create reports:read permission
    result = await async_session.execute(
        select(Permission).where(Permission.code == "reports:read")
    )
    reports_read = result.scalars().first()
    if not reports_read:
        reports_read = Permission(
            code="reports:read",
            name="View Reports",
            resource="reports",
            action="read",
        )
        async_session.add(reports_read)
        await async_session.flush()

    # Check if role permission already exists
    result = await async_session.execute(
        select(RolePermission).where(
            RolePermission.role_id == test_role.id,
            RolePermission.permission_id == reports_read.id,
        )
    )
    if not result.scalars().first():
        role_perm = RolePermission(
            role_id=test_role.id,
            permission_id=reports_read.id,
        )
        async_session.add(role_perm)

    # Check if user role already exists
    result = await async_session.execute(
        select(UserRole).where(
            UserRole.user_id == test_user.id,
            UserRole.role_id == test_role.id,
            UserRole.organization_id == test_organization.id,
        )
    )
    if not result.scalars().first():
        user_role = UserRole(
            user_id=test_user.id,
            role_id=test_role.id,
            organization_id=test_organization.id,
        )
        async_session.add(user_role)

    await async_session.commit()
    return test_user


@pytest.fixture
def user_with_reports_read_token(user_with_reports_read, test_organization) -> str:
    """Create a JWT token for user with reports:read permission."""
    from src.core.security import create_access_token

    return f"Bearer {create_access_token(str(user_with_reports_read.id), str(test_organization.id))}"


@pytest.fixture
async def user_with_reports_write(
    async_session, test_organization, test_user, test_role
):
    """Create a user with reports:write permission."""
    from sqlalchemy import select

    from src.models.permission import Permission
    from src.models.role_permission import RolePermission
    from src.models.user_role import UserRole

    # Find or create reports:write permission
    result = await async_session.execute(
        select(Permission).where(Permission.code == "reports:write")
    )
    reports_write = result.scalars().first()
    if not reports_write:
        reports_write = Permission(
            code="reports:write",
            name="Generate Reports",
            resource="reports",
            action="write",
        )
        async_session.add(reports_write)
        await async_session.flush()

    # Check if role permission already exists
    result = await async_session.execute(
        select(RolePermission).where(
            RolePermission.role_id == test_role.id,
            RolePermission.permission_id == reports_write.id,
        )
    )
    if not result.scalars().first():
        role_perm = RolePermission(
            role_id=test_role.id,
            permission_id=reports_write.id,
        )
        async_session.add(role_perm)

    # Check if user role already exists
    result = await async_session.execute(
        select(UserRole).where(
            UserRole.user_id == test_user.id,
            UserRole.role_id == test_role.id,
            UserRole.organization_id == test_organization.id,
        )
    )
    if not result.scalars().first():
        user_role = UserRole(
            user_id=test_user.id,
            role_id=test_role.id,
            organization_id=test_organization.id,
        )
        async_session.add(user_role)

    await async_session.commit()
    return test_user


@pytest.fixture
def user_with_reports_write_token(user_with_reports_write, test_organization) -> str:
    """Create a JWT token for user with reports:write permission."""
    from src.core.security import create_access_token

    return f"Bearer {create_access_token(str(user_with_reports_write.id), str(test_organization.id))}"


@pytest.fixture
async def user_with_reports_delete(
    async_session, test_organization, test_user, test_role
):
    """Create a user with reports:delete permission."""
    from sqlalchemy import select

    from src.models.permission import Permission
    from src.models.role_permission import RolePermission
    from src.models.user_role import UserRole

    # Find or create reports:delete permission
    result = await async_session.execute(
        select(Permission).where(Permission.code == "reports:delete")
    )
    reports_delete = result.scalars().first()
    if not reports_delete:
        reports_delete = Permission(
            code="reports:delete",
            name="Delete Reports",
            resource="reports",
            action="delete",
        )
        async_session.add(reports_delete)
        await async_session.flush()

    # Check if role permission already exists
    result = await async_session.execute(
        select(RolePermission).where(
            RolePermission.role_id == test_role.id,
            RolePermission.permission_id == reports_delete.id,
        )
    )
    if not result.scalars().first():
        role_perm = RolePermission(
            role_id=test_role.id,
            permission_id=reports_delete.id,
        )
        async_session.add(role_perm)

    # Check if user role already exists
    result = await async_session.execute(
        select(UserRole).where(
            UserRole.user_id == test_user.id,
            UserRole.role_id == test_role.id,
            UserRole.organization_id == test_organization.id,
        )
    )
    if not result.scalars().first():
        user_role = UserRole(
            user_id=test_user.id,
            role_id=test_role.id,
            organization_id=test_organization.id,
        )
        async_session.add(user_role)

    await async_session.commit()
    return test_user


@pytest.fixture
def user_with_reports_delete_token(user_with_reports_delete, test_organization) -> str:
    """Create a JWT token for user with reports:delete permission."""
    from src.core.security import create_access_token

    return f"Bearer {create_access_token(str(user_with_reports_delete.id), str(test_organization.id))}"


# ============================================================================
# Report Types Endpoint Tests
# ============================================================================


class TestReportTypesEndpoint:
    """Tests for GET /api/v1/reports/types endpoint."""

    @pytest.mark.asyncio
    async def test_list_report_types_authenticated(
        self, client: AsyncClient, user_with_reports_read_token
    ):
        """Test listing report types with authentication."""
        response = await client.get(
            "/api/v1/reports/types",
            headers={"Authorization": user_with_reports_read_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) > 0

        # Check structure of report type
        item = data["items"][0]
        assert "code" in item
        assert "name" in item
        assert "description" in item

    @pytest.mark.asyncio
    async def test_list_report_types_unauthenticated(self, client: AsyncClient):
        """Test that listing report types requires authentication."""
        response = await client.get("/api/v1/reports/types")

        assert response.status_code in [401, 403]


# ============================================================================
# Reports List Endpoint Tests
# ============================================================================


class TestReportsListEndpoint:
    """Tests for GET /api/v1/reports endpoint."""

    @pytest.mark.asyncio
    async def test_list_reports_authenticated(
        self, client: AsyncClient, user_with_reports_read_token, multiple_test_reports
    ):
        """Test listing reports with authentication."""
        response = await client.get(
            "/api/v1/reports",
            headers={"Authorization": user_with_reports_read_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert data["total"] >= len(multiple_test_reports)

    @pytest.mark.asyncio
    async def test_list_reports_unauthenticated(self, client: AsyncClient):
        """Test that listing reports requires authentication."""
        response = await client.get("/api/v1/reports")

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_list_reports_pagination(
        self, client: AsyncClient, user_with_reports_read_token, multiple_test_reports
    ):
        """Test pagination of reports list."""
        response = await client.get(
            "/api/v1/reports?limit=2&offset=0",
            headers={"Authorization": user_with_reports_read_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 2
        assert data["limit"] == 2
        assert data["offset"] == 0

    @pytest.mark.asyncio
    async def test_list_reports_filter_by_status(
        self, client: AsyncClient, user_with_reports_read_token, multiple_test_reports
    ):
        """Test filtering reports by status."""
        response = await client.get(
            "/api/v1/reports?filter[status]=completed",
            headers={"Authorization": user_with_reports_read_token},
        )

        assert response.status_code == 200
        data = response.json()

        # All returned reports should have completed status
        for item in data["items"]:
            assert item["status"] == "completed"

    @pytest.mark.asyncio
    async def test_list_reports_filter_by_type(
        self, client: AsyncClient, user_with_reports_read_token, multiple_test_reports
    ):
        """Test filtering reports by type."""
        response = await client.get(
            "/api/v1/reports?filter[report_type]=users_report",
            headers={"Authorization": user_with_reports_read_token},
        )

        assert response.status_code == 200
        data = response.json()

        # All returned reports should have users_report type
        for item in data["items"]:
            assert item["report_type"] == "users_report"


# ============================================================================
# Create Report Endpoint Tests
# ============================================================================


class TestCreateReportEndpoint:
    """Tests for POST /api/v1/reports endpoint."""

    @pytest.mark.asyncio
    async def test_create_report_success(
        self, client: AsyncClient, user_with_reports_write_token
    ):
        """Test creating a report successfully."""
        # Mock the file manager to avoid actual file operations
        with patch("src.services.reports.report_service.get_file_manager") as mock_fm:
            mock_file_manager = AsyncMock()
            mock_file_manager.upload_file.return_value = AsyncMock(
                id=uuid4(), storage_key="test/report.csv"
            )
            mock_fm.return_value = mock_file_manager

            response = await client.post(
                "/api/v1/reports",
                json={
                    "report_type": "users_report",
                    "name": "New Users Report",
                    "description": "A new report",
                },
                headers={"Authorization": user_with_reports_write_token},
            )

        assert response.status_code == 201
        data = response.json()
        assert "message" in data
        assert "report" in data
        assert data["report"]["name"] == "New Users Report"
        assert data["report"]["report_type"] == "users_report"

    @pytest.mark.asyncio
    async def test_create_report_invalid_type(
        self, client: AsyncClient, user_with_reports_write_token
    ):
        """Test creating a report with invalid type."""
        response = await client.post(
            "/api/v1/reports",
            json={
                "report_type": "invalid_report_type",
                "name": "Invalid Report",
            },
            headers={"Authorization": user_with_reports_write_token},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_report_unauthenticated(self, client: AsyncClient):
        """Test that creating reports requires authentication."""
        response = await client.post(
            "/api/v1/reports",
            json={
                "report_type": "users_report",
                "name": "Test Report",
            },
        )

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_create_report_missing_fields(
        self, client: AsyncClient, user_with_reports_write_token
    ):
        """Test creating a report with missing required fields."""
        response = await client.post(
            "/api/v1/reports",
            json={
                "report_type": "users_report",
                # Missing name
            },
            headers={"Authorization": user_with_reports_write_token},
        )

        assert response.status_code == 422


# ============================================================================
# Get Report Endpoint Tests
# ============================================================================


class TestGetReportEndpoint:
    """Tests for GET /api/v1/reports/{report_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_report_success(
        self, client: AsyncClient, user_with_reports_read_token, test_report
    ):
        """Test getting a report by ID."""
        response = await client.get(
            f"/api/v1/reports/{test_report.id}",
            headers={"Authorization": user_with_reports_read_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_report.id)
        assert data["name"] == test_report.name
        assert data["report_type"] == test_report.report_type

    @pytest.mark.asyncio
    async def test_get_report_not_found(
        self, client: AsyncClient, user_with_reports_read_token
    ):
        """Test getting a non-existent report."""
        response = await client.get(
            f"/api/v1/reports/{uuid4()}",
            headers={"Authorization": user_with_reports_read_token},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_report_unauthenticated(self, client: AsyncClient, test_report):
        """Test that getting a report requires authentication."""
        response = await client.get(f"/api/v1/reports/{test_report.id}")

        assert response.status_code in [401, 403]


# ============================================================================
# Delete Report Endpoint Tests
# ============================================================================


class TestDeleteReportEndpoint:
    """Tests for DELETE /api/v1/reports/{report_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_report_success(
        self, client: AsyncClient, user_with_reports_delete_token, test_report
    ):
        """Test deleting a report."""
        response = await client.delete(
            f"/api/v1/reports/{test_report.id}",
            headers={"Authorization": user_with_reports_delete_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["report_id"] == str(test_report.id)

        # Verify report is no longer accessible
        get_response = await client.get(
            f"/api/v1/reports/{test_report.id}",
            headers={"Authorization": user_with_reports_delete_token},
        )
        assert get_response.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_delete_report_not_found(
        self, client: AsyncClient, user_with_reports_delete_token
    ):
        """Test deleting a non-existent report."""
        response = await client.delete(
            f"/api/v1/reports/{uuid4()}",
            headers={"Authorization": user_with_reports_delete_token},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_report_unauthenticated(
        self, client: AsyncClient, test_report
    ):
        """Test that deleting a report requires authentication."""
        response = await client.delete(f"/api/v1/reports/{test_report.id}")

        assert response.status_code in [401, 403]


# ============================================================================
# Tenant Isolation Tests
# ============================================================================


class TestReportsTenantIsolation:
    """Tests for tenant isolation of reports."""

    @pytest.mark.asyncio
    async def test_cannot_access_other_org_report(
        self,
        client: AsyncClient,
        second_org_user_token,
        test_report,
    ):
        """Test that users cannot access reports from other organizations."""
        response = await client.get(
            f"/api/v1/reports/{test_report.id}",
            headers={"Authorization": second_org_user_token},
        )

        # Should be 404 (not found in their org) or 403
        assert response.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_list_reports_only_shows_own_org(
        self,
        client: AsyncClient,
        second_org_user_token,
        multiple_test_reports,
    ):
        """Test that listing reports only shows reports from user's organization."""
        response = await client.get(
            "/api/v1/reports",
            headers={"Authorization": second_org_user_token},
        )

        # May be 403 if user doesn't have permission, or 200 with empty/different reports
        if response.status_code == 200:
            data = response.json()
            # None of the test reports should appear
            test_report_ids = {str(r.id) for r in multiple_test_reports}
            returned_ids = {item["id"] for item in data["items"]}
            assert not test_report_ids.intersection(returned_ids)
