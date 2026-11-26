"""
Unit tests for report generators.
Tests CSV generation, filtering, and proper data formatting.
"""

import csv
import io

import pytest

from src.services.reports import (
    get_available_report_types,
    get_generator,
    is_valid_report_type,
    register_generator,
)
from src.services.reports.users_report import generate_users_report


class TestUsersReportGenerator:
    """Tests for the users report generator."""

    @pytest.mark.asyncio
    async def test_generate_users_report_basic(
        self, async_session, test_organization, test_user
    ):
        """Test generating a basic users report."""
        file_bytes, content_type, row_count = await generate_users_report(
            session=async_session,
            organization_id=str(test_organization.id),
        )

        assert content_type == "text/csv"
        assert row_count >= 1  # At least the test user

        # Parse CSV content
        csv_content = file_bytes.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)

        # Check header
        header = rows[0]
        assert "ID" in header
        assert "Email" in header
        assert "First Name" in header
        assert "Last Name" in header
        assert "Status" in header
        assert "Roles" in header

        # Check we have data rows
        assert len(rows) > 1

    @pytest.mark.asyncio
    async def test_generate_users_report_csv_format(
        self, async_session, test_organization, test_user
    ):
        """Test that CSV is properly formatted."""
        file_bytes, _, _ = await generate_users_report(
            session=async_session,
            organization_id=str(test_organization.id),
        )

        # UTF-8 with BOM for Excel compatibility
        assert file_bytes.startswith(b"\xef\xbb\xbf")

        # Should be valid CSV
        csv_content = file_bytes.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)

        # All rows should have same number of columns as header
        header_len = len(rows[0])
        for row in rows[1:]:
            assert len(row) == header_len

    @pytest.mark.asyncio
    async def test_generate_users_report_contains_user_data(
        self, async_session, test_organization, test_user
    ):
        """Test that the report contains actual user data."""
        file_bytes, _, _ = await generate_users_report(
            session=async_session,
            organization_id=str(test_organization.id),
        )

        csv_content = file_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)

        # Find our test user in the report
        user_row = None
        for row in rows:
            if row["Email"] == test_user.email:
                user_row = row
                break

        assert user_row is not None
        assert user_row["ID"] == str(test_user.id)

    @pytest.mark.asyncio
    async def test_generate_users_report_filter_email_verified(
        self, async_session, test_organization, test_user
    ):
        """Test filtering by email verification status."""
        file_bytes, _, row_count = await generate_users_report(
            session=async_session,
            organization_id=str(test_organization.id),
            parameters={"email_verified": True},
        )

        csv_content = file_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)

        # All rows should have Email Verified = Yes
        for row in rows:
            assert row["Email Verified"] == "Yes"

    @pytest.mark.asyncio
    async def test_generate_users_report_filter_suspension_status(
        self, async_session, test_organization, test_user
    ):
        """Test filtering by suspension status."""
        file_bytes, _, row_count = await generate_users_report(
            session=async_session,
            organization_id=str(test_organization.id),
            parameters={"suspension_status": "active"},
        )

        csv_content = file_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)

        # All rows should have Status = active
        for row in rows:
            assert row["Status"] == "active"

    @pytest.mark.asyncio
    async def test_generate_users_report_tenant_isolation(
        self, async_session, test_organization, second_organization, test_user
    ):
        """Test that report only includes users from the specified organization."""
        # Generate report for second organization
        file_bytes, _, row_count = await generate_users_report(
            session=async_session,
            organization_id=str(second_organization.id),
        )

        csv_content = file_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)

        # Test user from test_organization should not be in second_organization's report
        user_ids = [row["ID"] for row in rows]
        assert str(test_user.id) not in user_ids

    @pytest.mark.asyncio
    async def test_generate_users_report_empty_organization(
        self, async_session, second_organization
    ):
        """Test generating report for organization with no users."""
        file_bytes, content_type, row_count = await generate_users_report(
            session=async_session,
            organization_id=str(second_organization.id),
        )

        assert content_type == "text/csv"
        assert row_count == 0

        # Should still have header
        csv_content = file_bytes.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)
        assert len(rows) == 1  # Just header


class TestReportGeneratorRegistry:
    """Tests for the report generator registry."""

    def test_users_report_registered(self):
        """Test that users_report is registered by default."""
        assert is_valid_report_type("users_report")

    def test_get_generator_existing(self):
        """Test getting an existing generator."""
        generator = get_generator("users_report")
        assert generator is not None
        assert callable(generator)

    def test_get_generator_nonexistent(self):
        """Test getting a non-existent generator."""
        generator = get_generator("nonexistent_report")
        assert generator is None

    def test_register_generator(self):
        """Test registering a new generator."""

        async def custom_generator(session, org_id, params=None):
            return b"test", "text/csv", 0

        register_generator(
            "custom_report",
            custom_generator,
            name="Custom Report",
            description="A custom test report",
        )

        assert is_valid_report_type("custom_report")
        assert get_generator("custom_report") == custom_generator

    def test_get_available_report_types(self):
        """Test getting list of available report types."""
        report_types = get_available_report_types()

        assert isinstance(report_types, list)
        assert "users_report" in [rt.code for rt in report_types]

        # Each type should have code, name, description
        for rt in report_types:
            assert rt.code is not None
            assert rt.name is not None
            assert rt.description is not None
