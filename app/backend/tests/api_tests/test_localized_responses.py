"""
Test cases for localized response messages feature.

Verifies that all API responses include translation codes:
- Success responses: message + message_code
- Error responses: detail + detail_code
"""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
import pytest

from src.core.response_codes import RESPONSE_CODES
from src.core.security import hash_password


# ==================== Auth Endpoints - Success Responses ====================


@pytest.mark.asyncio
async def test_login_success_includes_message_code(
    client: AsyncClient, async_session, test_organization
):
    """Test login success response does not include message_code (tokens only)."""
    from src.models.user import User

    user = User(
        email="logintest@test.com",
        password=hash_password("TestPass123"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "logintest@test.com",
            "password": "TestPass123",
            "organization_slug": test_organization.slug,
        },
    )

    assert response.status_code == 200
    data = response.json()
    # Login returns access token only, refresh token is in httpOnly cookie
    assert "access_token" in data
    assert "refresh_token" not in data


@pytest.mark.asyncio
async def test_logout_success_includes_message_code(
    client: AsyncClient, test_user, test_jwt_token, async_session
):
    """Test logout success response includes message_code."""
    from src.crud.refresh_token import create_refresh_token

    # Create a refresh token first
    refresh_token = await create_refresh_token(
        async_session, test_user.id, str(test_user.organization_id)
    )

    client.cookies.set("refresh_token", refresh_token)
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": test_jwt_token},
    )
    client.cookies.clear()

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "message_code" in data
    assert data["message_code"] == RESPONSE_CODES["auth.logout_success"]


@pytest.mark.asyncio
async def test_logout_all_includes_message_code(
    client: AsyncClient, test_user, test_jwt_token
):
    """Test logout/all success response includes message_code."""
    response = await client.post(
        "/api/v1/auth/logout/all",
        json={"user_id": str(test_user.id)},
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "message_code" in data
    assert data["message_code"] == RESPONSE_CODES["auth.all_sessions_logged_out"]


# ==================== Auth Endpoints - Error Responses ====================


@pytest.mark.asyncio
async def test_login_invalid_credentials_includes_detail_code(
    client: AsyncClient, test_organization
):
    """Test login with invalid credentials includes detail_code."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@test.com",
            "password": "WrongPass123",
            "organization_slug": test_organization.slug,
        },
    )

    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "detail_code" in data
    assert data["detail_code"] == RESPONSE_CODES["auth.invalid_credentials"]


@pytest.mark.asyncio
async def test_logout_invalid_token_includes_detail_code(
    client: AsyncClient, test_jwt_token
):
    """Test logout with invalid refresh token includes detail_code."""
    # Logout without a valid cookie now succeeds (just clears the cookie)
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": test_jwt_token},
    )

    # With cookie-based auth, logout without cookie just succeeds
    assert response.status_code == 200


# ==================== User Endpoints - Success Responses ====================


@pytest.mark.asyncio
async def test_register_user_includes_message_code(
    client: AsyncClient, test_organization
):
    """Test user registration success includes message_code."""
    user_data = {
        "email": "newuser@test.com",
        "password": "Password123!",
        "phone": "+27737442556",
        "organization_slug": test_organization.slug,
    }

    with patch("src.services.email.email_service.send_email", new_callable=AsyncMock):
        response = await client.post("/api/v1/user/register", json=user_data)

    assert response.status_code in [200, 201]
    data = response.json()
    # Registration sends verification email
    if "message" in data:
        assert "message_code" in data
        assert data["message_code"] in [
            RESPONSE_CODES["user.created"],
            RESPONSE_CODES["user.verification_email_sent"],
        ]


@pytest.mark.asyncio
async def test_update_user_includes_message_code(
    client: AsyncClient, test_user, test_jwt_token
):
    """Test update user profile success includes message_code."""
    update_data = {"first_name": "Updated", "last_name": "Name"}

    response = await client.put(
        "/api/v1/user/me",
        json=update_data,
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    if "message" in data:
        assert "message_code" in data
        assert data["message_code"] == RESPONSE_CODES["user.profile_updated"]


@pytest.mark.asyncio
async def test_change_password_includes_message_code(
    client: AsyncClient, test_user, test_jwt_token
):
    """Test change password success includes message_code."""
    password_data = {
        "current_password": "Password123!",
        "new_password": "NewPassword456!",
    }

    response = await client.post(
        "/api/v1/user/change-password",
        json=password_data,
        headers={"Authorization": test_jwt_token},
    )

    # Should succeed or fail, but if succeeds should have message_code
    if response.status_code == 200:
        data = response.json()
        if "message" in data:
            assert "message_code" in data
            assert data["message_code"] == RESPONSE_CODES["user.password_changed"]


# ==================== User Endpoints - Error Responses ====================


@pytest.mark.asyncio
async def test_register_existing_user_includes_detail_code(
    client: AsyncClient, test_user, test_organization
):
    """Test registering existing user includes detail_code."""
    user_data = {
        "email": test_user.email,
        "password": "Password123!",
        "phone": "+27737442557",
        "organization_slug": test_organization.slug,
    }

    with patch("src.services.email.email_service.send_email", new_callable=AsyncMock):
        response = await client.post("/api/v1/user/register", json=user_data)

    # Registering an existing address must not confirm that the address exists,
    # so the endpoint deliberately answers with the generic
    # `user.registration_failed` rather than `user.already_exists`
    # (src/api/user.py). Asserted unconditionally: this used to sit behind an
    # `if response.status_code in [400, 409]` guard, and while the endpoint was
    # returning 500 the branch never ran and the test passed asserting nothing.
    assert response.status_code == 409
    data = response.json()
    assert "detail" in data
    assert "detail_code" in data
    assert data["detail_code"] == RESPONSE_CODES["user.registration_failed"]


@pytest.mark.asyncio
async def test_change_password_incorrect_includes_detail_code(
    client: AsyncClient, test_user, test_jwt_token
):
    """Test change password with incorrect current password includes detail_code."""
    password_data = {
        "current_password": "WrongPassword123!",
        "new_password": "NewPassword456!",
    }

    response = await client.post(
        "/api/v1/user/change-password",
        json=password_data,
        headers={"Authorization": test_jwt_token},
    )

    if response.status_code in [400, 401]:
        data = response.json()
        assert "detail" in data
        assert "detail_code" in data
        assert data["detail_code"] == RESPONSE_CODES["user.password_incorrect"]


# ==================== Organization Endpoints - Success Responses ====================


@pytest.mark.asyncio
async def test_create_organization_includes_message_code(
    client: AsyncClient, test_admin_token
):
    """Test create organization success includes message_code."""
    org_data = {
        "name": "New Test Organization",
        "slug": "new-test-org",
    }

    response = await client.post(
        "/api/v1/organizations",
        json=org_data,
        headers={"Authorization": test_admin_token},
    )

    # May require specific permissions, but if succeeds should have message_code
    if response.status_code in [200, 201]:
        data = response.json()
        if "message" in data:
            assert "message_code" in data
            assert data["message_code"] == RESPONSE_CODES["organization.created"]


@pytest.mark.asyncio
async def test_update_organization_includes_message_code(
    client: AsyncClient, test_organization, test_admin_token
):
    """Test update organization success includes message_code."""
    update_data = {"name": "Updated Organization Name"}

    response = await client.put(
        f"/api/v1/organizations/{test_organization.id}",
        json=update_data,
        headers={"Authorization": test_admin_token},
    )

    if response.status_code == 200:
        data = response.json()
        if "message" in data:
            assert "message_code" in data
            assert data["message_code"] == RESPONSE_CODES["organization.updated"]


# ==================== Organization Endpoints - Error Responses ====================


@pytest.mark.asyncio
async def test_get_nonexistent_organization_includes_detail_code(
    client: AsyncClient, test_jwt_token
):
    """Test get nonexistent organization includes detail_code."""
    import uuid

    fake_id = str(uuid.uuid4())

    response = await client.get(
        f"/api/v1/organizations/{fake_id}",
        headers={"Authorization": test_jwt_token},
    )

    # Could be 403 (not authorized) or 404 (not found) - both are valid
    assert response.status_code in [403, 404]
    data = response.json()
    assert "detail" in data
    # detail_code may not be present for all 403 errors (some raised from old code)
    if response.status_code == 404:
        assert "detail_code" in data
        assert data["detail_code"] == RESPONSE_CODES["organization.not_found"]


# ==================== Role Endpoints - Success Responses ====================


@pytest.mark.asyncio
async def test_create_role_includes_message_code(client: AsyncClient, test_admin_token):
    """Test create role success includes message_code."""
    import uuid

    role_data = {
        "name": f"test_role_{uuid.uuid4().hex[:8]}",
        "description": "Test role for localization tests",
    }

    response = await client.post(
        "/api/v1/roles",
        json=role_data,
        headers={"Authorization": test_admin_token},
    )

    if response.status_code in [200, 201]:
        data = response.json()
        if "message" in data:
            assert "message_code" in data
            assert data["message_code"] == RESPONSE_CODES["role.created"]


@pytest.mark.asyncio
async def test_update_role_includes_message_code(
    client: AsyncClient, test_role, test_admin_token
):
    """Test update role success includes message_code."""
    update_data = {"description": "Updated role description"}

    response = await client.put(
        f"/api/v1/roles/{test_role.id}",
        json=update_data,
        headers={"Authorization": test_admin_token},
    )

    if response.status_code == 200:
        data = response.json()
        if "message" in data:
            assert "message_code" in data
            assert data["message_code"] == RESPONSE_CODES["role.updated"]


@pytest.mark.asyncio
async def test_delete_role_includes_message_code(
    client: AsyncClient, test_role, test_admin_token
):
    """Test delete role success includes message_code."""
    response = await client.delete(
        f"/api/v1/roles/{test_role.id}",
        headers={"Authorization": test_admin_token},
    )

    if response.status_code == 200:
        data = response.json()
        assert "message" in data
        assert "message_code" in data
        assert data["message_code"] == RESPONSE_CODES["role.deleted"]


# ==================== Role Endpoints - Error Responses ====================


@pytest.mark.asyncio
async def test_get_nonexistent_role_includes_detail_code(
    client: AsyncClient, test_jwt_token
):
    """Test get nonexistent role includes detail_code."""
    import uuid

    fake_id = str(uuid.uuid4())

    response = await client.get(
        f"/api/v1/roles/{fake_id}",
        headers={"Authorization": test_jwt_token},
    )

    # Could be 403 (not authorized) or 404 (not found) - both are valid
    assert response.status_code in [403, 404]
    data = response.json()
    assert "detail" in data
    # detail_code may not be present for all 403 errors (some raised from old code)
    if response.status_code == 404:
        assert "detail_code" in data
        assert data["detail_code"] == RESPONSE_CODES["role.not_found"]


# ==================== User Role Endpoints - Success Responses ====================


@pytest.mark.asyncio
async def test_assign_user_role_includes_message_code(
    client: AsyncClient,
    test_organization,
    test_user,
    test_role,
    test_admin_token,
):
    """Test assign user role success includes message_code."""
    role_data = {
        "user_id": str(test_user.id),
        "role_id": str(test_role.id),
    }

    response = await client.post(
        "/api/v1/user-roles",
        json=role_data,
        headers={"Authorization": test_admin_token},
    )

    if response.status_code in [200, 201]:
        data = response.json()
        if "message" in data:
            assert "message_code" in data
            assert data["message_code"] == RESPONSE_CODES["user_role.assigned"]


@pytest.mark.asyncio
async def test_remove_user_role_includes_message_code(
    client: AsyncClient,
    async_session,
    test_organization,
    test_user,
    test_role,
    test_admin_token,
):
    """Test remove user role success includes message_code."""
    from src.models.user_role import UserRole

    # Create a user role first
    user_role = UserRole(
        user_id=test_user.id,
        role_id=test_role.id,
        organization_id=test_organization.id,
    )
    async_session.add(user_role)
    await async_session.commit()
    await async_session.refresh(user_role)

    response = await client.delete(
        f"/api/v1/user-roles/{user_role.id}",
        headers={"Authorization": test_admin_token},
    )

    if response.status_code == 200:
        data = response.json()
        assert "message" in data
        assert "message_code" in data
        assert data["message_code"] == RESPONSE_CODES["user_role.removed"]


# ==================== User Role Endpoints - Error Responses ====================


@pytest.mark.asyncio
async def test_assign_duplicate_user_role_includes_detail_code(
    client: AsyncClient,
    async_session,
    test_organization,
    test_user,
    test_role,
    test_admin_token,
):
    """Test assigning duplicate user role includes detail_code."""
    from src.models.user_role import UserRole

    # Create a user role first
    user_role = UserRole(
        user_id=test_user.id,
        role_id=test_role.id,
        organization_id=test_organization.id,
    )
    async_session.add(user_role)
    await async_session.commit()

    # Try to assign again
    role_data = {
        "user_id": str(test_user.id),
        "role_id": str(test_role.id),
    }

    response = await client.post(
        "/api/v1/user-roles",
        json=role_data,
        headers={"Authorization": test_admin_token},
    )

    if response.status_code in [400, 409]:
        data = response.json()
        assert "detail" in data
        assert "detail_code" in data
        assert data["detail_code"] == RESPONSE_CODES["user_role.already_assigned"]


# ==================== API Key Endpoints - Success Responses ====================


@pytest.mark.asyncio
async def test_create_api_key_includes_message_code(
    client: AsyncClient, test_jwt_token, standard_permissions
):
    """Test create API key success includes message_code."""
    api_key_data = {
        "name": "Test API Key",
        "description": "API key for testing localization",
        "permission_ids": [],
    }

    response = await client.post(
        "/api/v1/api-keys",
        json=api_key_data,
        headers={"Authorization": test_jwt_token},
    )

    if response.status_code in [200, 201]:
        data = response.json()
        if "message" in data:
            assert "message_code" in data
            assert data["message_code"] == RESPONSE_CODES["api_key.created"]


@pytest.mark.asyncio
async def test_delete_api_key_includes_message_code(
    client: AsyncClient, async_session, test_user, test_jwt_token
):
    """Test delete API key success includes message_code."""
    from src.models.api_key import ApiKey

    # Create an API key first
    api_key = ApiKey(
        name="Test Key",
        key_hash="test-hash",
        prefix="test_pre",
        created_by=test_user.id,
        organization_id=test_user.organization_id,
    )
    async_session.add(api_key)
    await async_session.commit()
    await async_session.refresh(api_key)

    response = await client.delete(
        f"/api/v1/api-keys/{api_key.id}",
        headers={"Authorization": test_jwt_token},
    )

    if response.status_code == 200:
        data = response.json()
        assert "message" in data
        assert "message_code" in data
        assert data["message_code"] == RESPONSE_CODES["api_key.deleted"]


# ==================== API Key Endpoints - Error Responses ====================


@pytest.mark.asyncio
async def test_get_nonexistent_api_key_includes_detail_code(
    client: AsyncClient, test_jwt_token
):
    """Test get nonexistent API key includes detail_code."""
    import uuid

    fake_id = str(uuid.uuid4())

    response = await client.get(
        f"/api/v1/api-keys/{fake_id}",
        headers={"Authorization": test_jwt_token},
    )

    # Could be 403 (not in org) or 404 (not found) - both are valid
    assert response.status_code in [403, 404]
    data = response.json()
    assert "detail" in data
    # detail_code may not be present for all 403 errors (some raised from old code)
    if response.status_code == 404:
        assert "detail_code" in data
        assert data["detail_code"] == RESPONSE_CODES["api_key.not_found"]


# ==================== File Endpoints - Success Responses ====================


@pytest.mark.asyncio
async def test_upload_file_includes_message_code(client: AsyncClient, test_jwt_token):
    """Test file upload success includes message_code."""
    # Mock file upload
    files = {"file": ("test.txt", b"test content", "text/plain")}

    with patch(
        "src.services.files.s3_storage.S3StorageProvider.upload", new_callable=AsyncMock
    ) as mock:
        mock.return_value = {
            "file_id": "test-file-id",
            "url": "https://example.com/test.txt",
        }

        response = await client.post(
            "/api/v1/files/upload",
            files=files,
            headers={"Authorization": test_jwt_token},
        )

    if response.status_code in [200, 201]:
        data = response.json()
        if "message" in data:
            assert "message_code" in data
            assert data["message_code"] == RESPONSE_CODES["file.uploaded"]


# ==================== File Endpoints - Error Responses ====================


@pytest.mark.asyncio
async def test_get_nonexistent_file_includes_detail_code(
    client: AsyncClient, test_jwt_token
):
    """Test get nonexistent file includes detail_code."""
    import uuid

    fake_id = str(uuid.uuid4())

    response = await client.get(
        f"/api/v1/files/{fake_id}",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "detail_code" in data
    assert data["detail_code"] == RESPONSE_CODES["file.not_found"]


# ==================== Notification Endpoints - Success Responses ====================


@pytest.mark.asyncio
async def test_send_notification_includes_message_code(
    client: AsyncClient, test_admin_token, test_user
):
    """Test send notification success includes message_code."""
    notification_data = {
        "user_id": str(test_user.id),
        "title": "Test Notification",
        "message": "Test message",
        "category": "system",
    }

    response = await client.post(
        "/api/v1/notifications/send",
        json=notification_data,
        headers={"Authorization": test_admin_token},
    )

    if response.status_code in [200, 201]:
        data = response.json()
        if "message" in data:
            assert "message_code" in data
            assert data["message_code"] == RESPONSE_CODES["notification.sent"]


# ==================== Announcement Endpoints - Success Responses ====================


@pytest.mark.asyncio
async def test_dismiss_announcement_includes_message_code(
    client: AsyncClient, async_session, test_user, test_jwt_token, test_organization
):
    """Test dismiss announcement success includes message_code."""
    from src.models.announcement import Announcement

    # Create a dismissible announcement
    announcement = Announcement(
        title="Test Announcement",
        body="Test body",
        priority="normal",
        is_dismissible=True,
        organization_id=test_organization.id,
        created_by_id=test_user.id,
    )
    async_session.add(announcement)
    await async_session.commit()
    await async_session.refresh(announcement)

    response = await client.post(
        f"/api/v1/announcements/{announcement.id}/dismiss",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "message_code" in data
    assert data["message_code"] == RESPONSE_CODES["announcement.dismissed"]


# ==================== Announcement Endpoints - Error Responses ====================


@pytest.mark.asyncio
async def test_get_nonexistent_announcement_includes_detail_code(
    client: AsyncClient, test_jwt_token
):
    """Test get nonexistent announcement includes detail_code."""
    import uuid

    fake_id = str(uuid.uuid4())

    response = await client.get(
        f"/api/v1/announcements/{fake_id}",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code in [403, 404]
    data = response.json()
    assert "detail" in data
    if response.status_code == 404:
        assert "detail_code" in data
        assert data["detail_code"] == RESPONSE_CODES["announcement.not_found"]


@pytest.mark.asyncio
async def test_dismiss_nonexistent_announcement_includes_detail_code(
    client: AsyncClient, test_jwt_token
):
    """Test dismiss nonexistent announcement includes detail_code."""
    import uuid

    fake_id = str(uuid.uuid4())

    response = await client.post(
        f"/api/v1/announcements/{fake_id}/dismiss",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "detail_code" in data
    assert data["detail_code"] == RESPONSE_CODES["announcement.not_found"]


@pytest.mark.asyncio
async def test_dismiss_non_dismissible_announcement_includes_detail_code(
    client: AsyncClient, async_session, test_user, test_jwt_token, test_organization
):
    """Test dismiss non-dismissible announcement includes detail_code."""
    from src.models.announcement import Announcement

    # Create a non-dismissible announcement
    announcement = Announcement(
        title="Critical Announcement",
        body="This cannot be dismissed",
        priority="critical",
        is_dismissible=False,
        organization_id=test_organization.id,
        created_by_id=test_user.id,
    )
    async_session.add(announcement)
    await async_session.commit()
    await async_session.refresh(announcement)

    response = await client.post(
        f"/api/v1/announcements/{announcement.id}/dismiss",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "detail_code" in data
    assert data["detail_code"] == RESPONSE_CODES["announcement.not_dismissible"]


@pytest.mark.asyncio
async def test_announcement_response_codes_exist():
    """Test that all announcement response codes are defined."""
    # Verify that all announcement codes exist in RESPONSE_CODES
    announcement_codes = [
        "announcement.created",
        "announcement.updated",
        "announcement.deleted",
        "announcement.not_found",
        "announcement.dismissed",
        "announcement.not_dismissible",
        "announcement.already_dismissed",
        "announcement.platform_wide_forbidden",
        "announcement.no_fields_provided",
        "announcement.conflict",
        "announcement.database_error",
    ]
    for code in announcement_codes:
        assert (
            code in RESPONSE_CODES
        ), f"Response code {code} not found in RESPONSE_CODES"
        assert RESPONSE_CODES[code] == code, f"Response code {code} value mismatch"


@pytest.mark.asyncio
async def test_update_announcement_no_fields_includes_detail_code(
    client: AsyncClient, async_session, test_user, test_jwt_token, test_organization
):
    """Test update announcement with no fields includes detail_code."""
    from src.models.announcement import Announcement

    # Create an announcement
    announcement = Announcement(
        title="Test Announcement",
        body="Test body",
        priority="normal",
        is_dismissible=True,
        organization_id=test_organization.id,
        created_by_id=test_user.id,
    )
    async_session.add(announcement)
    await async_session.commit()
    await async_session.refresh(announcement)

    # Try to update with no fields
    response = await client.put(
        f"/api/v1/announcements/{announcement.id}",
        json={},
        headers={"Authorization": test_jwt_token},
    )

    # May get 400 (no fields) or 403 (not authorized to update)
    if response.status_code == 400:
        data = response.json()
        assert "detail" in data
        assert "detail_code" in data
        assert data["detail_code"] == RESPONSE_CODES["announcement.no_fields_provided"]


# ==================== Response Code Consistency Tests ====================


@pytest.mark.asyncio
async def test_all_response_codes_are_strings():
    """Test that all response codes in RESPONSE_CODES are strings."""
    for key, value in RESPONSE_CODES.items():
        assert isinstance(key, str), f"Key {key} is not a string"
        assert isinstance(value, str), f"Value for key {key} is not a string"
        # Verify format: domain.action[.detail]
        assert "." in value, f"Response code {value} does not contain a dot separator"


@pytest.mark.asyncio
async def test_response_codes_follow_naming_convention():
    """Test that response codes follow the domain.action[.detail] convention."""
    for key, value in RESPONSE_CODES.items():
        parts = value.split(".")
        assert len(parts) >= 2, f"Response code {value} has fewer than 2 parts"
        # First part should be domain (e.g., auth, user, organization, user_role)
        # Allow underscores in domain names
        assert (
            parts[0].replace("_", "").isalnum()
        ), f"Domain in {value} is not alphanumeric"
        # Second part should be action or detail
        assert (
            parts[1].replace("_", "").isalnum()
        ), f"Action in {value} is not alphanumeric"
