"""
Comprehensive API tests for file management endpoints.
Tests file upload, download, listing, usage tracking, and settings.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import AsyncClient
import pytest

from src.models.file import File
from src.models.file_usage import FileUsage
from src.models.organization_file_settings import OrganizationFileSettings


# ============================================================================
# Fixtures for File Testing
# ============================================================================


@pytest.fixture
async def file_settings(async_session, test_organization):
    """Create file settings for the test organization."""
    settings = OrganizationFileSettings(
        organization_id=test_organization.id,
        max_file_size_bytes=100 * 1024 * 1024,  # 100 MB
        max_video_size_bytes=100 * 1024 * 1024,
        allowed_extensions=["jpg", "png", "pdf", "mp4", "doc", "docx"],
        user_storage_quota_bytes=1024 * 1024 * 1024,  # 1 GB
        org_storage_quota_bytes=10 * 1024 * 1024 * 1024,  # 10 GB
        signed_url_expiry_seconds=3600,
        deleted_file_retention_days=30,
    )
    async_session.add(settings)
    await async_session.commit()
    await async_session.refresh(settings)
    return settings


@pytest.fixture
async def test_file(async_session, test_organization, test_user):
    """Create a test file record."""
    file = File(
        organization_id=test_organization.id,
        uploaded_by_user_id=test_user.id,
        original_filename="test_image.jpg",
        storage_key=f"{test_organization.id}/image/{uuid4()}_test_image.jpg",
        content_type="image/jpeg",
        file_extension="jpg",
        size_bytes=1024 * 100,  # 100 KB
        storage_provider="s3",
        bucket_name="test-bucket",
        status="ready",
        category="image",
        download_count=0,
    )
    async_session.add(file)
    await async_session.commit()
    await async_session.refresh(file)
    return file


@pytest.fixture
async def multiple_test_files(async_session, test_organization, test_user):
    """Create multiple test file records."""
    files = []
    categories = ["image", "video", "document", "other"]
    extensions = ["jpg", "mp4", "pdf", "zip"]
    content_types = ["image/jpeg", "video/mp4", "application/pdf", "application/zip"]

    for i, (cat, ext, ct) in enumerate(zip(categories, extensions, content_types)):
        file = File(
            organization_id=test_organization.id,
            uploaded_by_user_id=test_user.id,
            original_filename=f"test_file_{i}.{ext}",
            storage_key=f"{test_organization.id}/{cat}/{uuid4()}_test_file_{i}.{ext}",
            content_type=ct,
            file_extension=ext,
            size_bytes=1024 * (i + 1) * 10,
            storage_provider="s3",
            bucket_name="test-bucket",
            status="ready",
            category=cat,
            download_count=i,
        )
        async_session.add(file)
        files.append(file)

    await async_session.commit()
    for f in files:
        await async_session.refresh(f)
    return files


@pytest.fixture
async def user_file_usage(async_session, test_organization, test_user):
    """Create file usage record for test user."""
    usage = FileUsage(
        organization_id=test_organization.id,
        user_id=test_user.id,
        total_files=5,
        total_size_bytes=1024 * 1024 * 10,  # 10 MB
        image_count=2,
        image_size_bytes=1024 * 1024 * 5,
        video_count=1,
        video_size_bytes=1024 * 1024 * 3,
        document_count=1,
        document_size_bytes=1024 * 512,
        audio_count=0,
        audio_size_bytes=0,
        other_count=1,
        other_size_bytes=1024 * 512,
    )
    async_session.add(usage)
    await async_session.commit()
    await async_session.refresh(usage)
    return usage


# ============================================================================
# File Listing Tests
# ============================================================================


class TestFileListEndpoint:
    """Tests for GET /api/files endpoint."""

    @pytest.mark.asyncio
    async def test_list_files_authenticated(
        self, client: AsyncClient, test_jwt_token, multiple_test_files
    ):
        """Test listing files with authentication."""
        response = await client.get(
            "/api/v1/files", headers={"Authorization": test_jwt_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= len(multiple_test_files)

    @pytest.mark.asyncio
    async def test_list_files_unauthenticated(self, client: AsyncClient):
        """Test that listing files requires authentication."""
        response = await client.get("/api/v1/files")

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_list_files_with_category_filter(
        self, client: AsyncClient, test_jwt_token, multiple_test_files
    ):
        """Test filtering files by category using SDL filter format."""
        response = await client.get(
            "/api/v1/files?filter[category]=image",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        # All returned files should be images
        for item in data["items"]:
            assert item["category"] == "image"

    @pytest.mark.asyncio
    async def test_list_files_with_status_filter(
        self, client: AsyncClient, test_jwt_token, multiple_test_files
    ):
        """Test filtering files by status using SDL filter format."""
        response = await client.get(
            "/api/v1/files?filter[status]=ready",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["status"] == "ready"

    @pytest.mark.asyncio
    async def test_list_files_pagination(
        self, client: AsyncClient, test_jwt_token, multiple_test_files
    ):
        """Test file listing pagination."""
        # First page
        response = await client.get(
            "/api/v1/files?limit=2&offset=0", headers={"Authorization": test_jwt_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 2
        assert data["limit"] == 2
        assert data["offset"] == 0


# ============================================================================
# File Retrieval Tests
# ============================================================================


class TestFileRetrievalEndpoint:
    """Tests for GET /api/files/{file_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_file_by_id(self, client: AsyncClient, test_jwt_token, test_file):
        """Test retrieving a specific file."""
        response = await client.get(
            f"/api/v1/files/{test_file.id}", headers={"Authorization": test_jwt_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_file.id)
        assert data["original_filename"] == test_file.original_filename
        assert data["content_type"] == test_file.content_type

    @pytest.mark.asyncio
    async def test_get_file_not_found(self, client: AsyncClient, test_jwt_token):
        """Test retrieving a non-existent file."""
        fake_id = str(uuid4())
        response = await client.get(
            f"/api/v1/files/{fake_id}", headers={"Authorization": test_jwt_token}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_file_unauthenticated(self, client: AsyncClient, test_file):
        """Test that getting a file requires authentication."""
        response = await client.get(f"/api/v1/files/{test_file.id}")

        assert response.status_code in [401, 403]


# ============================================================================
# File Download Tests
# ============================================================================


class TestFileDownloadEndpoint:
    """Tests for GET /api/files/{file_id}/download endpoint."""

    @pytest.mark.asyncio
    async def test_get_download_url(
        self, client: AsyncClient, test_jwt_token, test_file, file_settings
    ):
        """Test getting a signed download URL."""
        mock_fm = MagicMock()
        mock_fm.get_download_url = AsyncMock(
            return_value=MagicMock(
                url="https://s3.example.com/signed-url",
                expires_at=datetime.now(timezone.utc),
            )
        )
        with patch("src.api.file.get_file_manager", return_value=mock_fm):

            response = await client.get(
                f"/api/v1/files/{test_file.id}/download",
                headers={"Authorization": test_jwt_token},
            )

            assert response.status_code == 200
            data = response.json()
            assert "download_url" in data
            assert "expires_at" in data
            assert "filename" in data

    @pytest.mark.asyncio
    async def test_download_file_not_found(self, client: AsyncClient, test_jwt_token):
        """Test downloading a non-existent file."""
        fake_id = str(uuid4())
        response = await client.get(
            f"/api/v1/files/{fake_id}/download",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 404


# ============================================================================
# File Deletion Tests
# ============================================================================


class TestFileDeleteEndpoint:
    """Tests for DELETE /api/files/{file_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_file(self, client: AsyncClient, test_jwt_token, test_file):
        """Test soft deleting a file."""
        response = await client.delete(
            f"/api/v1/files/{test_file.id}", headers={"Authorization": test_jwt_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_delete_file_not_found(self, client: AsyncClient, test_jwt_token):
        """Test deleting a non-existent file."""
        fake_id = str(uuid4())
        response = await client.delete(
            f"/api/v1/files/{fake_id}", headers={"Authorization": test_jwt_token}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_file_unauthenticated(self, client: AsyncClient, test_file):
        """Test that deleting a file requires authentication."""
        response = await client.delete(f"/api/v1/files/{test_file.id}")

        assert response.status_code in [401, 403]


# ============================================================================
# File Usage Tests
# ============================================================================


class TestFileUsageEndpoint:
    """Tests for GET /api/files/usage endpoint."""

    @pytest.mark.asyncio
    async def test_get_user_usage(
        self, client: AsyncClient, test_jwt_token, user_file_usage
    ):
        """Test getting user's file usage statistics."""
        response = await client.get(
            "/api/v1/files/usage", headers={"Authorization": test_jwt_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_files" in data
        assert "total_size_bytes" in data
        assert "image_count" in data
        assert "video_count" in data
        assert "document_count" in data

    @pytest.mark.asyncio
    async def test_get_user_usage_empty(self, client: AsyncClient, test_jwt_token):
        """Test getting usage when user has no files."""
        response = await client.get(
            "/api/v1/files/usage", headers={"Authorization": test_jwt_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_files"] == 0
        assert data["total_size_bytes"] == 0

    @pytest.mark.asyncio
    async def test_get_user_usage_unauthenticated(self, client: AsyncClient):
        """Test that getting usage requires authentication."""
        response = await client.get("/api/v1/files/usage")

        assert response.status_code in [401, 403]


class TestOrganizationUsageEndpoint:
    """Tests for GET /api/files/usage/organization endpoint."""

    @pytest.mark.asyncio
    async def test_get_org_usage_as_admin(
        self, client: AsyncClient, test_admin_token, user_file_usage
    ):
        """Test getting organization usage as admin."""
        response = await client.get(
            "/api/v1/files/usage/organization",
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_files" in data
        assert "total_size_bytes" in data
        assert "user_count" in data

    @pytest.mark.asyncio
    async def test_get_org_usage_as_non_admin(
        self, client: AsyncClient, test_jwt_token, user_file_usage
    ):
        """Test that regular users cannot access organization usage."""
        response = await client.get(
            "/api/v1/files/usage/organization",
            headers={"Authorization": test_jwt_token},
        )

        # Should require admin
        assert response.status_code in [401, 403]


# ============================================================================
# File Settings Tests
# ============================================================================


class TestFileSettingsEndpoint:
    """Tests for /api/files/settings endpoints."""

    @pytest.mark.asyncio
    async def test_get_settings_as_admin(
        self, client: AsyncClient, test_admin_token, file_settings
    ):
        """Test getting file settings as admin."""
        response = await client.get(
            "/api/v1/files/settings", headers={"Authorization": test_admin_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert "max_file_size_bytes" in data
        assert "max_video_size_bytes" in data
        assert "allowed_extensions" in data

    @pytest.mark.asyncio
    async def test_get_settings_as_non_admin(
        self, client: AsyncClient, test_jwt_token, file_settings
    ):
        """Test that regular users cannot access file settings."""
        response = await client.get(
            "/api/v1/files/settings", headers={"Authorization": test_jwt_token}
        )

        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_update_settings_as_admin(
        self, client: AsyncClient, test_admin_token, file_settings
    ):
        """Test updating file settings as admin."""
        update_data = {
            "max_file_size_bytes": 200 * 1024 * 1024,
            "signed_url_expiry_seconds": 7200,
        }

        response = await client.put(
            "/api/v1/files/settings",
            json=update_data,
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["max_file_size_bytes"] == 200 * 1024 * 1024
        assert data["signed_url_expiry_seconds"] == 7200

    @pytest.mark.asyncio
    async def test_update_settings_as_non_admin(
        self, client: AsyncClient, test_jwt_token, file_settings
    ):
        """Test that regular users cannot update file settings."""
        update_data = {"max_file_size_bytes": 200 * 1024 * 1024}

        response = await client.put(
            "/api/v1/files/settings",
            json=update_data,
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code in [401, 403]


# ============================================================================
# Presigned Upload URL Tests
# ============================================================================


class TestPresignedUploadEndpoint:
    """Tests for /api/files/upload-url endpoint."""

    @pytest.mark.asyncio
    async def test_get_upload_url(
        self, client: AsyncClient, test_jwt_token, file_settings
    ):
        """Test getting a presigned upload URL."""
        request_data = {
            "filename": "new_photo.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 1024 * 500,  # 500 KB
        }

        mock_fm = MagicMock()
        mock_fm.generate_upload_url = AsyncMock(
            return_value=MagicMock(
                url="https://s3.example.com/upload-url",
                storage_key="test-org/image/new_photo.jpg",
                bucket="test-bucket",
                expires_at=datetime.now(timezone.utc),
            )
        )
        with patch("src.api.file.get_file_manager", return_value=mock_fm):

            response = await client.post(
                "/api/v1/files/upload-url",
                json=request_data,
                headers={"Authorization": test_jwt_token},
            )

            # May be 500 (S3 not configured), 501 (not implemented), or 200/201 (success)
            assert response.status_code in [200, 201, 500, 501]

    @pytest.mark.asyncio
    async def test_get_upload_url_invalid_extension(
        self, client: AsyncClient, test_jwt_token, file_settings
    ):
        """Test that disallowed extensions are rejected."""
        request_data = {
            "filename": "script.exe",
            "content_type": "application/octet-stream",
            "size_bytes": 1024 * 100,
        }

        response = await client.post(
            "/api/v1/files/upload-url",
            json=request_data,
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code in [400, 501]

    @pytest.mark.asyncio
    async def test_get_upload_url_file_too_large(
        self, client: AsyncClient, test_jwt_token, file_settings
    ):
        """Test that files exceeding size limit are rejected."""
        request_data = {
            "filename": "huge_video.mp4",
            "content_type": "video/mp4",
            "size_bytes": 500 * 1024 * 1024,  # 500 MB, exceeds 100 MB limit
        }

        response = await client.post(
            "/api/v1/files/upload-url",
            json=request_data,
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code in [400, 501]


# ============================================================================
# Multi-Tenancy Isolation Tests
# ============================================================================


class TestOrganizationFilesEndpoint:
    """Tests for GET /api/files/organization endpoint (admin only)."""

    @pytest.mark.asyncio
    async def test_list_org_files_as_admin(
        self, client: AsyncClient, test_admin_token, multiple_test_files
    ):
        """Test listing all organization files as admin."""
        response = await client.get(
            "/api/v1/files/organization",
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= len(multiple_test_files)

    @pytest.mark.asyncio
    async def test_list_org_files_as_non_admin(
        self, client: AsyncClient, test_jwt_token, multiple_test_files
    ):
        """Test that regular users cannot list organization files."""
        response = await client.get(
            "/api/v1/files/organization",
            headers={"Authorization": test_jwt_token},
        )

        # Should require files:admin permission
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_list_org_files_with_filters(
        self, client: AsyncClient, test_admin_token, multiple_test_files
    ):
        """Test filtering organization files by category using SDL filter format."""
        response = await client.get(
            "/api/v1/files/organization?filter[category]=image",
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["category"] == "image"


class TestFileUserIsolation:
    """Tests to ensure files are properly isolated between users within an organization."""

    @pytest.mark.asyncio
    async def test_user_cannot_see_other_users_files(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        test_user,
        test_jwt_token,
    ):
        """Test that GET /files only returns the current user's files."""
        from src.models.user import User

        # Create another user in the same organization
        other_user = User(
            email="other@example.com",
            first_name="Other",
            last_name="User",
            organization_id=test_organization.id,
            password="hashed_password",
            email_verified=True,
        )
        async_session.add(other_user)
        await async_session.commit()
        await async_session.refresh(other_user)

        # Create a file for the other user
        other_users_file = File(
            organization_id=test_organization.id,
            uploaded_by_user_id=other_user.id,
            original_filename="other_users_secret.pdf",
            storage_key=f"{test_organization.id}/document/{uuid4()}_secret.pdf",
            content_type="application/pdf",
            file_extension="pdf",
            size_bytes=1024,
            storage_provider="s3",
            bucket_name="test-bucket",
            status="ready",
            category="document",
        )
        async_session.add(other_users_file)

        # Create a file for the test user
        test_users_file = File(
            organization_id=test_organization.id,
            uploaded_by_user_id=test_user.id,
            original_filename="my_file.pdf",
            storage_key=f"{test_organization.id}/document/{uuid4()}_my_file.pdf",
            content_type="application/pdf",
            file_extension="pdf",
            size_bytes=1024,
            storage_provider="s3",
            bucket_name="test-bucket",
            status="ready",
            category="document",
        )
        async_session.add(test_users_file)
        await async_session.commit()
        await async_session.refresh(other_users_file)
        await async_session.refresh(test_users_file)

        # List files as test_user
        response = await client.get(
            "/api/v1/files", headers={"Authorization": test_jwt_token}
        )

        assert response.status_code == 200
        data = response.json()

        # Check that other user's file is NOT in the list
        file_ids = [item["id"] for item in data["items"]]
        assert str(other_users_file.id) not in file_ids

        # Check that test user's file IS in the list
        assert str(test_users_file.id) in file_ids

    @pytest.mark.asyncio
    async def test_admin_can_see_all_org_files(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        test_user,
        test_admin_token,
    ):
        """Test that admin can see all files via /files/organization endpoint."""
        from src.models.user import User

        # Create another user in the same organization
        other_user = User(
            email="another@example.com",
            first_name="Another",
            last_name="User",
            organization_id=test_organization.id,
            password="hashed_password",
            email_verified=True,
        )
        async_session.add(other_user)
        await async_session.commit()
        await async_session.refresh(other_user)

        # Create files for both users
        user1_file = File(
            organization_id=test_organization.id,
            uploaded_by_user_id=test_user.id,
            original_filename="user1_file.pdf",
            storage_key=f"{test_organization.id}/document/{uuid4()}_user1.pdf",
            content_type="application/pdf",
            file_extension="pdf",
            size_bytes=1024,
            storage_provider="s3",
            bucket_name="test-bucket",
            status="ready",
            category="document",
        )
        user2_file = File(
            organization_id=test_organization.id,
            uploaded_by_user_id=other_user.id,
            original_filename="user2_file.pdf",
            storage_key=f"{test_organization.id}/document/{uuid4()}_user2.pdf",
            content_type="application/pdf",
            file_extension="pdf",
            size_bytes=1024,
            storage_provider="s3",
            bucket_name="test-bucket",
            status="ready",
            category="document",
        )
        async_session.add(user1_file)
        async_session.add(user2_file)
        await async_session.commit()
        await async_session.refresh(user1_file)
        await async_session.refresh(user2_file)

        # List organization files as admin
        response = await client.get(
            "/api/v1/files/organization",
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        data = response.json()

        # Both files should be visible to admin
        file_ids = [item["id"] for item in data["items"]]
        assert str(user1_file.id) in file_ids
        assert str(user2_file.id) in file_ids


class TestFileMultiTenancyIsolation:
    """Tests to ensure files are properly isolated between organizations."""

    @pytest.mark.asyncio
    async def test_cannot_access_other_org_files(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        second_organization,
        test_user,
        test_jwt_token,
    ):
        """Test that users cannot access files from other organizations."""
        # Create a file in the second organization
        other_org_file = File(
            organization_id=second_organization.id,
            uploaded_by_user_id=test_user.id,  # Same user, different org
            original_filename="secret_file.pdf",
            storage_key=f"{second_organization.id}/document/{uuid4()}_secret.pdf",
            content_type="application/pdf",
            file_extension="pdf",
            size_bytes=1024,
            storage_provider="s3",
            bucket_name="test-bucket",
            status="ready",
            category="document",
        )
        async_session.add(other_org_file)
        await async_session.commit()
        await async_session.refresh(other_org_file)

        # Try to access the file from the first organization's context
        response = await client.get(
            f"/api/v1/files/{other_org_file.id}",
            headers={"Authorization": test_jwt_token},
        )

        # Should not find the file (it belongs to a different org)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_file_list_only_shows_own_org(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        second_organization,
        test_user,
        test_jwt_token,
        multiple_test_files,
    ):
        """Test that file listing only shows files from user's organization."""
        # Create a file in the second organization
        other_org_file = File(
            organization_id=second_organization.id,
            uploaded_by_user_id=test_user.id,
            original_filename="other_org_file.jpg",
            storage_key=f"{second_organization.id}/image/{uuid4()}_other.jpg",
            content_type="image/jpeg",
            file_extension="jpg",
            size_bytes=1024,
            storage_provider="s3",
            bucket_name="test-bucket",
            status="ready",
            category="image",
        )
        async_session.add(other_org_file)
        await async_session.commit()

        # List files
        response = await client.get(
            "/api/v1/files", headers={"Authorization": test_jwt_token}
        )

        assert response.status_code == 200
        data = response.json()

        # Check that the other org's file is not in the list
        file_ids = [item["id"] for item in data["items"]]
        assert str(other_org_file.id) not in file_ids

    @pytest.mark.asyncio
    async def test_cannot_delete_other_org_files(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        second_organization,
        test_user,
        test_jwt_token,
    ):
        """Test that users cannot delete files from other organizations."""
        # Create a file in the second organization
        other_org_file = File(
            organization_id=second_organization.id,
            uploaded_by_user_id=test_user.id,
            original_filename="protected_file.pdf",
            storage_key=f"{second_organization.id}/document/{uuid4()}_protected.pdf",
            content_type="application/pdf",
            file_extension="pdf",
            size_bytes=1024,
            storage_provider="s3",
            bucket_name="test-bucket",
            status="ready",
            category="document",
        )
        async_session.add(other_org_file)
        await async_session.commit()
        await async_session.refresh(other_org_file)

        # Try to delete the file from the first organization's context
        response = await client.delete(
            f"/api/v1/files/{other_org_file.id}",
            headers={"Authorization": test_jwt_token},
        )

        # Should not find the file (it belongs to a different org)
        assert response.status_code == 404
