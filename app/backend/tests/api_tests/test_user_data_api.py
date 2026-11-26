"""
API tests for user data (GDPR) endpoints.

Tests verify:
- Request data export
- List exports
- Download export
- Request account deletion
- Get deletion status
- Cancel deletion
- Access controls
- Tenant isolation
"""

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
import pytest

from src.models.data_deletion_request import DataDeletionRequest, DeletionStatus
from src.models.data_export_request import DataExportRequest, ExportStatus


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def data_export_request(async_session, test_organization, test_user):
    """Create a data export request."""
    request = DataExportRequest(
        user_id=test_user.id,
        organization_id=test_organization.id,
        status=ExportStatus.COMPLETED,
        file_path="local:/tmp/exports/test_export.zip",
        file_size_bytes=1024,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        completed_at=datetime.now(timezone.utc),
    )
    async_session.add(request)
    await async_session.commit()
    await async_session.refresh(request)
    return request


@pytest.fixture
async def pending_export_request(async_session, test_organization, test_user):
    """Create a pending data export request."""
    request = DataExportRequest(
        user_id=test_user.id,
        organization_id=test_organization.id,
        status=ExportStatus.PENDING,
    )
    async_session.add(request)
    await async_session.commit()
    await async_session.refresh(request)
    return request


@pytest.fixture
async def data_deletion_request(async_session, test_organization, test_user):
    """Create a data deletion request."""
    request = DataDeletionRequest(
        user_id=test_user.id,
        organization_id=test_organization.id,
        status=DeletionStatus.PENDING,
        scheduled_hard_delete_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    async_session.add(request)
    await async_session.commit()
    await async_session.refresh(request)
    return request


@pytest.fixture
async def other_user_export(async_session, test_organization, test_admin_user):
    """Create an export request for a different user."""
    request = DataExportRequest(
        user_id=test_admin_user.id,
        organization_id=test_organization.id,
        status=ExportStatus.COMPLETED,
        file_path="local:/tmp/exports/admin_export.zip",
        file_size_bytes=2048,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        completed_at=datetime.now(timezone.utc),
    )
    async_session.add(request)
    await async_session.commit()
    await async_session.refresh(request)
    return request


@pytest.fixture
async def other_user_deletion(async_session, test_organization, test_admin_user):
    """Create a deletion request for a different user."""
    request = DataDeletionRequest(
        user_id=test_admin_user.id,
        organization_id=test_organization.id,
        status=DeletionStatus.PENDING,
        scheduled_hard_delete_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    async_session.add(request)
    await async_session.commit()
    await async_session.refresh(request)
    return request


# ============================================================================
# Data Export Tests
# ============================================================================


class TestDataExport:
    """Tests for data export endpoints."""

    @pytest.mark.asyncio
    async def test_request_data_export_requires_auth(self, client: AsyncClient):
        """Test that requesting data export requires authentication."""
        response = await client.post("/api/v1/users/me/export")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_request_data_export_success(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test requesting a data export."""
        response = await client.post(
            "/api/v1/users/me/export",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert "request_id" in data
        assert data["message_code"] == "data_export.request_created"

    @pytest.mark.asyncio
    async def test_list_data_exports_requires_auth(self, client: AsyncClient):
        """Test that listing exports requires authentication."""
        response = await client.get("/api/v1/users/me/exports")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_data_exports_success(
        self,
        client: AsyncClient,
        test_jwt_token,
        data_export_request,
    ):
        """Test listing user's data exports."""
        response = await client.get(
            "/api/v1/users/me/exports",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_data_exports_pagination(
        self,
        client: AsyncClient,
        test_jwt_token,
        data_export_request,
    ):
        """Test exports list pagination."""
        response = await client.get(
            "/api/v1/users/me/exports?limit=5&offset=0",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 5
        assert data["offset"] == 0

    @pytest.mark.asyncio
    async def test_get_export_download_url_requires_auth(
        self,
        client: AsyncClient,
        data_export_request,
    ):
        """Test that getting download URL requires authentication."""
        response = await client.get(
            f"/api/v1/users/me/exports/{data_export_request.id}/download"
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_export_download_url_not_ready(
        self,
        client: AsyncClient,
        test_jwt_token,
        pending_export_request,
    ):
        """Test getting download URL for pending export."""
        response = await client.get(
            f"/api/v1/users/me/exports/{pending_export_request.id}/download",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400
        data = response.json()
        assert "not ready" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_export_download_url_not_found(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test getting download URL for non-existent export."""
        import uuid

        fake_id = str(uuid.uuid4())
        response = await client.get(
            f"/api/v1/users/me/exports/{fake_id}/download",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 404


# ============================================================================
# Account Deletion Tests
# ============================================================================


class TestAccountDeletion:
    """Tests for account deletion endpoints."""

    @pytest.mark.asyncio
    async def test_request_account_deletion_requires_auth(self, client: AsyncClient):
        """Test that requesting deletion requires authentication."""
        response = await client.post("/api/v1/users/me/delete")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_request_account_deletion_success(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test requesting account deletion."""
        response = await client.post(
            "/api/v1/users/me/delete",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert "request_id" in data
        assert "scheduled_hard_delete_at" in data
        assert data["message_code"] == "data_deletion.request_created"

    @pytest.mark.asyncio
    async def test_request_account_deletion_already_exists(
        self,
        client: AsyncClient,
        test_jwt_token,
        data_deletion_request,
    ):
        """Test requesting deletion when one already exists."""
        response = await client.post(
            "/api/v1/users/me/delete",
            headers={"Authorization": test_jwt_token},
        )
        # Should fail because there's already an active deletion request
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_deletion_status_requires_auth(self, client: AsyncClient):
        """Test that getting deletion status requires authentication."""
        response = await client.get("/api/v1/users/me/delete")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_deletion_status_with_request(
        self,
        client: AsyncClient,
        test_jwt_token,
        data_deletion_request,
    ):
        """Test getting deletion status when request exists."""
        response = await client.get(
            "/api/v1/users/me/delete",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_active_request"] is True
        assert data["request"] is not None
        assert data["request"]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_deletion_status_no_request(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test getting deletion status when no request exists."""
        response = await client.get(
            "/api/v1/users/me/delete",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_active_request"] is False
        assert data["request"] is None

    @pytest.mark.asyncio
    async def test_cancel_deletion_requires_auth(self, client: AsyncClient):
        """Test that cancelling deletion requires authentication."""
        response = await client.post("/api/v1/users/me/delete/cancel")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_cancel_deletion_success(
        self,
        client: AsyncClient,
        test_jwt_token,
        data_deletion_request,
    ):
        """Test cancelling a deletion request."""
        response = await client.post(
            "/api/v1/users/me/delete/cancel",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message_code"] == "data_deletion.cancelled"

    @pytest.mark.asyncio
    async def test_cancel_deletion_no_request(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test cancelling when no deletion request exists."""
        response = await client.post(
            "/api/v1/users/me/delete/cancel",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 404


# ============================================================================
# Access Control Tests
# ============================================================================


class TestUserDataAccessControl:
    """Tests for user data access controls."""

    @pytest.mark.asyncio
    async def test_cannot_access_other_user_export(
        self,
        client: AsyncClient,
        test_jwt_token,
        other_user_export,
    ):
        """Test that user cannot access another user's export."""
        response = await client.get(
            f"/api/v1/users/me/exports/{other_user_export.id}/download",
            headers={"Authorization": test_jwt_token},
        )
        # Should be forbidden (403) or not found (404) for security
        assert response.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_export_list_excludes_other_users(
        self,
        client: AsyncClient,
        test_jwt_token,
        data_export_request,
        other_user_export,
    ):
        """Test that export list only shows user's own exports."""
        response = await client.get(
            "/api/v1/users/me/exports",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        export_ids = [item["id"] for item in data["items"]]
        # User's own export should be in the list
        assert str(data_export_request.id) in export_ids
        # Other user's export should NOT be in the list
        assert str(other_user_export.id) not in export_ids


# ============================================================================
# Tenant Isolation Tests
# ============================================================================


class TestUserDataTenantIsolation:
    """Tests to ensure user data is properly isolated between organizations."""

    @pytest.mark.asyncio
    async def test_exports_isolated_by_organization(
        self,
        client: AsyncClient,
        async_session,
        test_jwt_token,
        second_organization,
        test_user,
    ):
        """Test that exports from other organizations are not visible."""
        # Create an export in the second organization for the same user
        # (hypothetically, if user had access to multiple orgs)
        other_org_export = DataExportRequest(
            user_id=test_user.id,
            organization_id=second_organization.id,
            status=ExportStatus.COMPLETED,
            file_path="local:/tmp/exports/other_org_export.zip",
            file_size_bytes=1024,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        async_session.add(other_org_export)
        await async_session.commit()
        await async_session.refresh(other_org_export)

        # List exports - should only see ones from current organization
        response = await client.get(
            "/api/v1/users/me/exports",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        export_ids = [item["id"] for item in data["items"]]
        # Export from other org should NOT be visible
        assert str(other_org_export.id) not in export_ids

    @pytest.mark.asyncio
    async def test_deletions_isolated_by_organization(
        self,
        client: AsyncClient,
        async_session,
        test_jwt_token,
        second_organization,
        test_user,
    ):
        """Test that deletion requests from other organizations are not affected."""
        # Create a deletion request in the second organization
        other_org_deletion = DataDeletionRequest(
            user_id=test_user.id,
            organization_id=second_organization.id,
            status=DeletionStatus.PENDING,
            scheduled_hard_delete_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        async_session.add(other_org_deletion)
        await async_session.commit()
        await async_session.refresh(other_org_deletion)

        # Get deletion status - should not see the other org's request
        response = await client.get(
            "/api/v1/users/me/delete",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        # Should show no active request in current org
        assert data["has_active_request"] is False


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestUserDataEdgeCases:
    """Tests for edge cases in user data endpoints."""

    @pytest.mark.asyncio
    async def test_export_with_expired_status(
        self,
        client: AsyncClient,
        async_session,
        test_jwt_token,
        test_organization,
        test_user,
    ):
        """Test handling of expired export."""
        expired_export = DataExportRequest(
            user_id=test_user.id,
            organization_id=test_organization.id,
            status=ExportStatus.EXPIRED,
            file_path="local:/tmp/exports/expired_export.zip",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        async_session.add(expired_export)
        await async_session.commit()
        await async_session.refresh(expired_export)

        # Trying to download expired export should fail
        response = await client.get(
            f"/api/v1/users/me/exports/{expired_export.id}/download",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_export_with_failed_status(
        self,
        client: AsyncClient,
        async_session,
        test_jwt_token,
        test_organization,
        test_user,
    ):
        """Test handling of failed export."""
        failed_export = DataExportRequest(
            user_id=test_user.id,
            organization_id=test_organization.id,
            status=ExportStatus.FAILED,
        )
        async_session.add(failed_export)
        await async_session.commit()
        await async_session.refresh(failed_export)

        # Trying to download failed export should fail
        response = await client.get(
            f"/api/v1/users/me/exports/{failed_export.id}/download",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_cancelled_deletion_cannot_be_cancelled_again(
        self,
        client: AsyncClient,
        async_session,
        test_jwt_token,
        test_organization,
        test_user,
    ):
        """Test that a cancelled deletion request cannot be cancelled again."""
        cancelled_deletion = DataDeletionRequest(
            user_id=test_user.id,
            organization_id=test_organization.id,
            status=DeletionStatus.CANCELLED,
            scheduled_hard_delete_at=datetime.now(timezone.utc) + timedelta(days=30),
            cancelled_at=datetime.now(timezone.utc),
            cancellation_reason="User requested cancellation",
        )
        async_session.add(cancelled_deletion)
        await async_session.commit()
        await async_session.refresh(cancelled_deletion)

        # Should not find an active deletion request to cancel
        response = await client.post(
            "/api/v1/users/me/delete/cancel",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 404
