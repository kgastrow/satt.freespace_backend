"""
Unit tests for user avatar functionality.
Tests User model with avatar_file_id foreign key and avatar relationship.
"""

import shutil
import tempfile
from unittest.mock import patch

import pytest
from sqlalchemy import select

from src.crud.user import create_user, get_user_by_id
from src.models.file import File, MediaUse
from src.models.user import User
from src.services.files.file_manager import FileManager
from src.services.files.local_storage import LocalStorageProvider


class TestUserAvatarModel:
    """Tests for User model avatar field and relationship."""

    @pytest.mark.asyncio
    async def test_create_user_without_avatar(self, async_session, test_organization):
        """Test creating a user without avatar_file_id."""
        user_data = {
            "email": "noavatar@test.com",
            "password": "Password123!",
            "first_name": "No",
            "last_name": "Avatar",
        }

        user = await create_user(
            session=async_session,
            request=user_data,
            organization_id=str(test_organization.id),
        )

        assert user is not None
        assert user.avatar_file_id is None
        assert user.avatar is None

    @pytest.mark.asyncio
    async def test_create_user_with_avatar(
        self, async_session, test_organization, test_user
    ):
        """Test creating a user with avatar_file_id."""
        avatar_file = File(
            organization_id=test_organization.id,
            uploaded_by_user_id=test_user.id,
            original_filename="avatar.jpg",
            storage_key=f"{test_organization.id}/avatar/avatar.jpg",
            content_type="image/jpeg",
            size_bytes=50000,
            category="image",
            media_use=MediaUse.AVATAR,
            status="ready",
        )
        async_session.add(avatar_file)
        await async_session.commit()
        await async_session.refresh(avatar_file)

        user = User(
            organization_id=test_organization.id,
            email="withavatar@test.com",
            password="hashedpassword",
            first_name="With",
            last_name="Avatar",
            avatar_file_id=avatar_file.id,
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        assert user.avatar_file_id == avatar_file.id
        assert user.avatar is not None
        assert user.avatar.id == avatar_file.id

    @pytest.mark.asyncio
    async def test_avatar_relationship_loaded(
        self, async_session, test_organization, test_user
    ):
        """Test that avatar relationship is properly loaded with lazy='selectin'."""
        avatar_file = File(
            organization_id=test_organization.id,
            uploaded_by_user_id=test_user.id,
            original_filename="profile.png",
            storage_key=f"{test_organization.id}/avatar/profile.png",
            content_type="image/png",
            size_bytes=30000,
            category="image",
            media_use=MediaUse.AVATAR,
            status="ready",
        )
        async_session.add(avatar_file)
        await async_session.commit()
        await async_session.refresh(avatar_file)

        user = User(
            organization_id=test_organization.id,
            email="relationtest@test.com",
            password="hashedpassword",
            first_name="Relation",
            last_name="Test",
            avatar_file_id=avatar_file.id,
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        # Fetch user from database in new query
        result = await async_session.execute(select(User).where(User.id == user.id))
        fetched_user = result.scalar_one()

        # Avatar should be loaded due to lazy="selectin"
        assert fetched_user.avatar is not None
        assert fetched_user.avatar.id == avatar_file.id
        assert fetched_user.avatar.original_filename == "profile.png"
        assert fetched_user.avatar.media_use == MediaUse.AVATAR

    @pytest.mark.asyncio
    async def test_update_user_avatar(
        self, async_session, test_organization, test_user
    ):
        """Test updating a user's avatar_file_id."""
        # Create initial user without avatar
        user = User(
            organization_id=test_organization.id,
            email="updateavatar@test.com",
            password="hashedpassword",
            first_name="Update",
            last_name="Avatar",
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        assert user.avatar_file_id is None

        # Create avatar file
        avatar_file = File(
            organization_id=test_organization.id,
            uploaded_by_user_id=test_user.id,
            original_filename="new-avatar.jpg",
            storage_key=f"{test_organization.id}/avatar/new-avatar.jpg",
            content_type="image/jpeg",
            size_bytes=60000,
            category="image",
            media_use=MediaUse.AVATAR,
            status="ready",
        )
        async_session.add(avatar_file)
        await async_session.commit()
        await async_session.refresh(avatar_file)

        # Update user with avatar
        user.avatar_file_id = avatar_file.id
        await async_session.commit()
        await async_session.refresh(user)

        assert user.avatar_file_id == avatar_file.id
        assert user.avatar is not None
        assert user.avatar.id == avatar_file.id

    @pytest.mark.asyncio
    async def test_remove_user_avatar(
        self, async_session, test_organization, test_user
    ):
        """Test removing a user's avatar by setting avatar_file_id to None."""
        # Create avatar file
        avatar_file = File(
            organization_id=test_organization.id,
            uploaded_by_user_id=test_user.id,
            original_filename="remove.jpg",
            storage_key=f"{test_organization.id}/avatar/remove.jpg",
            content_type="image/jpeg",
            size_bytes=40000,
            category="image",
            media_use=MediaUse.AVATAR,
            status="ready",
        )
        async_session.add(avatar_file)
        await async_session.commit()
        await async_session.refresh(avatar_file)

        # Create user with avatar
        user = User(
            organization_id=test_organization.id,
            email="removeavatar@test.com",
            password="hashedpassword",
            first_name="Remove",
            last_name="Avatar",
            avatar_file_id=avatar_file.id,
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        assert user.avatar_file_id is not None

        # Remove avatar
        user.avatar_file_id = None
        await async_session.commit()
        await async_session.refresh(user)

        assert user.avatar_file_id is None
        assert user.avatar is None


@pytest.fixture
def mock_file_manager():
    """
    Create a mock file manager with local storage for avatar API tests.

    This fixture patches get_file_manager() to return a working FileManager
    instance backed by a temporary local storage directory.
    """
    temp_dir = tempfile.mkdtemp()
    try:
        # Create local storage provider
        storage = LocalStorageProvider(
            storage_path=temp_dir,
            base_url="http://test",
            enabled=True,
        )

        # Create file manager with the storage
        fm = FileManager(storage_provider=storage)

        # Patch get_file_manager to return our file manager
        with patch("src.api.user.get_file_manager", return_value=fm):
            yield fm
    finally:
        # Cleanup temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)


class TestUserAvatarAPI:
    """Tests for user avatar upload/delete API endpoints."""

    @pytest.mark.asyncio
    async def test_upload_avatar_success(
        self, client, async_session, test_user, test_jwt_token, mock_file_manager
    ):
        """Test successful avatar upload."""
        import io

        # Create a fake image file
        file_content = b"fake-image-content"
        files = {"file": ("avatar.jpg", io.BytesIO(file_content), "image/jpeg")}

        response = await client.post(
            "/api/v1/user/me/avatar",
            headers={"Authorization": test_jwt_token},
            files=files,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Avatar uploaded successfully"
        assert data["message_code"] == "avatar.uploaded"
        assert "avatar_url" in data

        # Verify user has avatar_file_id set

        user = await get_user_by_id(
            async_session, str(test_user.id), str(test_user.organization_id)
        )
        assert user.avatar_file_id is not None

    @pytest.mark.asyncio
    async def test_upload_avatar_invalid_file_type(
        self, client, test_user, test_jwt_token
    ):
        """Test avatar upload with invalid file type."""
        import io

        file_content = b"fake-pdf-content"
        files = {"file": ("document.pdf", io.BytesIO(file_content), "application/pdf")}

        response = await client.post(
            "/api/v1/user/me/avatar",
            headers={"Authorization": test_jwt_token},
            files=files,
        )

        assert response.status_code == 400
        data = response.json()
        assert "Invalid file type" in data["detail"]

    @pytest.mark.asyncio
    async def test_upload_avatar_empty_file(self, client, test_user, test_jwt_token):
        """Test avatar upload with empty file."""
        import io

        files = {"file": ("avatar.jpg", io.BytesIO(b""), "image/jpeg")}

        response = await client.post(
            "/api/v1/user/me/avatar",
            headers={"Authorization": test_jwt_token},
            files=files,
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail_code"] == "avatar.file_empty"

    @pytest.mark.asyncio
    async def test_delete_avatar_success(
        self, client, async_session, test_user, test_jwt_token, test_organization
    ):
        """Test successful avatar deletion."""
        # First create an avatar file
        avatar_file = File(
            organization_id=test_organization.id,
            uploaded_by_user_id=test_user.id,
            original_filename="avatar.jpg",
            storage_key=f"{test_organization.id}/avatar/avatar.jpg",
            content_type="image/jpeg",
            size_bytes=50000,
            category="image",
            media_use=MediaUse.AVATAR,
            status="ready",
        )
        async_session.add(avatar_file)
        await async_session.commit()
        await async_session.refresh(avatar_file)

        # Set user's avatar
        test_user.avatar_file_id = avatar_file.id
        await async_session.commit()

        # Delete avatar
        response = await client.delete(
            "/api/v1/user/me/avatar",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Avatar deleted successfully"
        assert data["message_code"] == "avatar.deleted"

        # Verify user's avatar_file_id is null

        user = await get_user_by_id(
            async_session, str(test_user.id), str(test_user.organization_id)
        )
        assert user.avatar_file_id is None

        # Verify file is soft-deleted
        from src.crud.file import get_file_by_id

        deleted_file = await get_file_by_id(
            async_session, str(avatar_file.id), str(test_organization.id)
        )
        assert deleted_file is None  # soft-deleted, so not returned

    @pytest.mark.asyncio
    async def test_delete_avatar_not_found(self, client, test_user, test_jwt_token):
        """Test deleting avatar when user has no avatar."""
        response = await client.delete(
            "/api/v1/user/me/avatar",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail_code"] == "avatar.not_found"

    @pytest.mark.asyncio
    async def test_get_user_profile_with_avatar(
        self,
        client,
        async_session,
        test_user,
        test_jwt_token,
        test_organization,
        mock_file_manager,
    ):
        """Test GET /user/me includes avatar_url when user has avatar."""
        # Use the upload endpoint to create avatar properly
        import io

        file_content = b"fake-image-content-for-profile-test"
        files = {"file": ("profile-avatar.png", io.BytesIO(file_content), "image/png")}

        upload_response = await client.post(
            "/api/v1/user/me/avatar",
            headers={"Authorization": test_jwt_token},
            files=files,
        )
        assert upload_response.status_code == 201

        # Get profile
        response = await client.get(
            "/api/v1/user/me",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "avatar_url" in data
        assert data["avatar_url"] is not None
        # Avatar URL should be a data URL (base64) or S3 URL
        assert "base64" in data["avatar_url"] or data["avatar_url"].startswith("http")

    @pytest.mark.asyncio
    async def test_get_user_profile_without_avatar(
        self, client, test_user, test_jwt_token
    ):
        """Test GET /user/me returns avatar_url=null when user has no avatar."""
        response = await client.get(
            "/api/v1/user/me",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "avatar_url" in data
        assert data["avatar_url"] is None

    @pytest.mark.asyncio
    async def test_avatar_multi_tenant_isolation(
        self,
        client,
        async_session,
        test_user,
        test_jwt_token,
        second_organization,
        second_org_user,
    ):
        """Test that users cannot manage avatars from other organizations."""
        # Create avatar for second org user
        avatar_file = File(
            organization_id=second_organization.id,
            uploaded_by_user_id=second_org_user.id,
            original_filename="other-avatar.jpg",
            storage_key=f"{second_organization.id}/avatar/other-avatar.jpg",
            content_type="image/jpeg",
            size_bytes=50000,
            category="image",
            media_use=MediaUse.AVATAR,
            status="ready",
        )
        async_session.add(avatar_file)
        await async_session.commit()
        await async_session.refresh(avatar_file)

        second_org_user.avatar_file_id = avatar_file.id
        await async_session.commit()

        # Try to delete with test_user token (different org)
        # This should succeed for test_user but not affect second_org_user
        response = await client.delete(
            "/api/v1/user/me/avatar",
            headers={"Authorization": test_jwt_token},
        )

        # Should return 404 because test_user has no avatar
        assert response.status_code == 404

        # Verify second_org_user's avatar is still there

        other_user = await get_user_by_id(
            async_session, str(second_org_user.id), str(second_organization.id)
        )
        assert other_user.avatar_file_id == avatar_file.id
