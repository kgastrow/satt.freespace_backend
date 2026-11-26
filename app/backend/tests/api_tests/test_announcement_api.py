"""
API tests for announcement endpoints.

Tests verify:
- CRUD operations
- Dismissal
- Non-dismissible announcements
- Platform-wide (super admin only)
- Tenant isolation
"""

from datetime import datetime, timezone
from uuid import uuid4

from httpx import AsyncClient
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, hash_password
from src.models.announcement import Announcement
from src.models.announcement_dismissal import AnnouncementDismissal
from src.models.permission import Permission
from src.models.role_permission import RolePermission
from src.models.user import User
from src.models.user_role import UserRole


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="function")
async def announcements_read_permission(async_session: AsyncSession):
    """Create announcements:read permission."""
    permission = Permission(
        code="announcements:read",
        name="Read Announcements",
        description="View announcements in the organization",
        resource="announcements",
        action="read",
        display_order=0,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)
    return permission


@pytest_asyncio.fixture(scope="function")
async def announcements_write_permission(async_session: AsyncSession):
    """Create announcements:write permission."""
    permission = Permission(
        code="announcements:write",
        name="Write Announcements",
        description="Create and update announcements",
        resource="announcements",
        action="write",
        display_order=1,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)
    return permission


@pytest_asyncio.fixture(scope="function")
async def announcements_delete_permission(async_session: AsyncSession):
    """Create announcements:delete permission."""
    permission = Permission(
        code="announcements:delete",
        name="Delete Announcements",
        description="Delete announcements",
        resource="announcements",
        action="delete",
        display_order=2,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)
    return permission


@pytest_asyncio.fixture(scope="function")
async def user_with_announcement_permissions(
    async_session: AsyncSession,
    test_organization,
    test_role,
    announcements_read_permission,
    announcements_write_permission,
    announcements_delete_permission,
    test_user,
):
    """Create a user with all announcement permissions through a role."""
    # Grant permissions to the role
    for perm in [
        announcements_read_permission,
        announcements_write_permission,
        announcements_delete_permission,
    ]:
        role_permission = RolePermission(
            role_id=test_role.id,
            permission_id=perm.id,
            granted_by=test_user.id,
        )
        async_session.add(role_permission)
    await async_session.commit()

    # Create user with the role
    user = User(
        email="announcementuser@test.com",
        password=hash_password("AnnouncementUser123!"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    # Assign role to user
    user_role = UserRole(
        user_id=user.id, role_id=test_role.id, organization_id=test_organization.id
    )
    async_session.add(user_role)
    await async_session.commit()

    return user


@pytest.fixture
def user_with_announcement_token(
    user_with_announcement_permissions, test_organization
) -> str:
    """Create a JWT token for user with announcement permissions."""
    token = create_access_token(
        user_id=str(user_with_announcement_permissions.id),
        organization_id=str(test_organization.id),
    )
    return f"Bearer {token}"


@pytest_asyncio.fixture(scope="function")
async def test_announcement(async_session, test_organization, test_admin_user):
    """Create a test announcement."""
    announcement = Announcement(
        organization_id=test_organization.id,
        title="Test Announcement",
        body="Test announcement body",
        priority="normal",
        is_dismissible=True,
        created_by_id=test_admin_user.id,
    )
    async_session.add(announcement)
    await async_session.commit()
    await async_session.refresh(announcement)
    return announcement


@pytest_asyncio.fixture(scope="function")
async def non_dismissible_announcement(
    async_session, test_organization, test_admin_user
):
    """Create a non-dismissible announcement."""
    announcement = Announcement(
        organization_id=test_organization.id,
        title="Important Announcement",
        body="This cannot be dismissed",
        priority="critical",
        is_dismissible=False,
        created_by_id=test_admin_user.id,
    )
    async_session.add(announcement)
    await async_session.commit()
    await async_session.refresh(announcement)
    return announcement


@pytest_asyncio.fixture(scope="function")
async def second_org_announcement(async_session, second_organization, test_admin_user):
    """Create an announcement in second org."""
    announcement = Announcement(
        organization_id=second_organization.id,
        title="Second Org Announcement",
        body="Second org announcement body",
        priority="high",
        is_dismissible=True,
        created_by_id=test_admin_user.id,
    )
    async_session.add(announcement)
    await async_session.commit()
    await async_session.refresh(announcement)
    return announcement


@pytest_asyncio.fixture(scope="function")
async def platform_announcement(async_session, test_admin_user):
    """Create a platform-wide announcement."""
    announcement = Announcement(
        organization_id=None,
        title="Platform Announcement",
        body="Platform-wide announcement body",
        priority="high",
        is_dismissible=True,
        created_by_id=test_admin_user.id,
    )
    async_session.add(announcement)
    await async_session.commit()
    await async_session.refresh(announcement)
    return announcement


# ─────────────────────────────────────────────────────────────
# User Endpoint Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_active_announcements_requires_auth(client: AsyncClient):
    """Test that getting announcements requires authentication."""
    response = await client.get("/api/v1/announcements/active")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_active_announcements(
    client: AsyncClient,
    test_jwt_token,
    test_announcement,
):
    """Test getting active announcements."""
    response = await client.get(
        "/api/v1/announcements/active",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "announcements" in data


@pytest.mark.asyncio
async def test_get_active_announcements_includes_announcement(
    client: AsyncClient,
    test_jwt_token,
    test_announcement,
):
    """Test that active announcements include created announcement."""
    response = await client.get(
        "/api/v1/announcements/active",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    announcement_ids = [str(a["id"]) for a in data["announcements"]]
    assert str(test_announcement.id) in announcement_ids


@pytest.mark.asyncio
async def test_dismiss_announcement(
    client: AsyncClient,
    test_jwt_token,
    test_announcement,
):
    """Test dismissing an announcement."""
    response = await client.post(
        f"/api/v1/announcements/{test_announcement.id}/dismiss",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["message_code"] == "announcement.dismissed"
    assert data["announcement_id"] == str(test_announcement.id)


@pytest.mark.asyncio
async def test_dismiss_non_dismissible_announcement(
    client: AsyncClient,
    test_jwt_token,
    non_dismissible_announcement,
):
    """Test that non-dismissible announcements cannot be dismissed."""
    response = await client.post(
        f"/api/v1/announcements/{non_dismissible_announcement.id}/dismiss",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail_code"] == "announcement.not_dismissible"


@pytest.mark.asyncio
async def test_dismiss_announcement_not_found(
    client: AsyncClient,
    test_jwt_token,
):
    """Test dismissing non-existent announcement returns 404."""
    response = await client.post(
        f"/api/v1/announcements/{uuid4()}/dismiss",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dismiss_already_dismissed_announcement(
    client: AsyncClient,
    async_session,
    test_jwt_token,
    test_announcement,
    test_user,
):
    """Test that dismissing already dismissed announcement returns 409."""
    # Create dismissal record
    dismissal = AnnouncementDismissal(
        announcement_id=test_announcement.id,
        user_id=test_user.id,
    )
    async_session.add(dismissal)
    await async_session.commit()

    response = await client.post(
        f"/api/v1/announcements/{test_announcement.id}/dismiss",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 409
    data = response.json()
    assert data["detail_code"] == "announcement.already_dismissed"


@pytest.mark.asyncio
async def test_dismissed_announcement_not_shown(
    client: AsyncClient,
    async_session,
    test_jwt_token,
    test_announcement,
    test_user,
):
    """Test that dismissed announcements are not returned in active list."""
    # Create dismissal record
    dismissal = AnnouncementDismissal(
        announcement_id=test_announcement.id,
        user_id=test_user.id,
    )
    async_session.add(dismissal)
    await async_session.commit()

    response = await client.get(
        "/api/v1/announcements/active",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    announcement_ids = [str(a["id"]) for a in data["announcements"]]
    assert str(test_announcement.id) not in announcement_ids


# ─────────────────────────────────────────────────────────────
# Admin Endpoint Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_announcement_requires_permission(
    client: AsyncClient,
    test_jwt_token,
):
    """Test that creating announcements requires announcements:write permission."""
    response = await client.post(
        "/api/v1/announcements",
        json={
            "title": "New Announcement",
            "body": "Content",
            "priority": "normal",
        },
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_announcement_as_admin(
    client: AsyncClient,
    user_with_announcement_token,
):
    """Test creating an announcement with permission."""
    response = await client.post(
        "/api/v1/announcements",
        json={
            "title": "New Announcement",
            "body": "Content",
            "priority": "normal",
            "is_dismissible": True,
        },
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "New Announcement"
    assert data["priority"] == "normal"
    assert data["is_dismissible"] is True


@pytest.mark.asyncio
async def test_create_announcement_with_cta(
    client: AsyncClient,
    user_with_announcement_token,
):
    """Test creating announcement with call-to-action."""
    response = await client.post(
        "/api/v1/announcements",
        json={
            "title": "CTA Announcement",
            "body": "Check this out!",
            "priority": "high",
            "cta_text": "Learn More",
            "cta_url": "https://example.com",
            "cta_dismisses": True,
        },
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["cta_text"] == "Learn More"
    assert data["cta_url"] == "https://example.com"


@pytest.mark.asyncio
async def test_create_announcement_invalid_priority(
    client: AsyncClient,
    user_with_announcement_token,
):
    """Test creating announcement with invalid priority."""
    response = await client.post(
        "/api/v1/announcements",
        json={
            "title": "New Announcement",
            "body": "Content",
            "priority": "invalid",
        },
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_announcement_missing_required_fields(
    client: AsyncClient,
    user_with_announcement_token,
):
    """Test creating announcement with missing required fields."""
    response = await client.post(
        "/api/v1/announcements",
        json={
            "title": "New Announcement",
            # Missing body
        },
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_announcement_by_id(
    client: AsyncClient,
    user_with_announcement_token,
    test_announcement,
):
    """Test getting a specific announcement by ID."""
    response = await client.get(
        f"/api/v1/announcements/{test_announcement.id}",
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_announcement.id)
    assert data["title"] == test_announcement.title


@pytest.mark.asyncio
async def test_get_announcement_not_found(
    client: AsyncClient,
    user_with_announcement_token,
):
    """Test getting non-existent announcement returns 404."""
    response = await client.get(
        f"/api/v1/announcements/{uuid4()}",
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_announcements(
    client: AsyncClient,
    user_with_announcement_token,
    test_announcement,
):
    """Test listing announcements."""
    response = await client.get(
        "/api/v1/announcements",
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_list_announcements_pagination(
    client: AsyncClient,
    user_with_announcement_token,
    test_announcement,
):
    """Test that pagination parameters are applied."""
    response = await client.get(
        "/api/v1/announcements?limit=10&offset=0",
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 10
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_update_announcement(
    client: AsyncClient,
    user_with_announcement_token,
    test_announcement,
):
    """Test updating an announcement."""
    response = await client.put(
        f"/api/v1/announcements/{test_announcement.id}",
        json={"title": "Updated Title"},
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_update_announcement_no_fields(
    client: AsyncClient,
    user_with_announcement_token,
    test_announcement,
):
    """Test updating announcement with no fields returns 400."""
    response = await client.put(
        f"/api/v1/announcements/{test_announcement.id}",
        json={},
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail_code"] == "announcement.no_fields_provided"


@pytest.mark.asyncio
async def test_update_announcement_not_found(
    client: AsyncClient,
    user_with_announcement_token,
):
    """Test updating non-existent announcement returns 404."""
    response = await client.put(
        f"/api/v1/announcements/{uuid4()}",
        json={"title": "Updated"},
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_announcement(
    client: AsyncClient,
    user_with_announcement_token,
    test_announcement,
):
    """Test deleting an announcement."""
    response = await client.delete(
        f"/api/v1/announcements/{test_announcement.id}",
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_announcement_not_found(
    client: AsyncClient,
    user_with_announcement_token,
):
    """Test deleting non-existent announcement returns 404."""
    response = await client.delete(
        f"/api/v1/announcements/{uuid4()}",
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_announcement_requires_permission(
    client: AsyncClient,
    test_jwt_token,
    test_announcement,
):
    """Test that deleting announcement requires announcements:delete permission."""
    response = await client.delete(
        f"/api/v1/announcements/{test_announcement.id}",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 403


# ─────────────────────────────────────────────────────────────
# Platform-wide Announcement Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_platform_announcement_requires_super_admin(
    client: AsyncClient,
    user_with_announcement_token,
):
    """Test that creating platform-wide announcement requires super admin."""
    response = await client.post(
        "/api/v1/announcements",
        json={
            "title": "Platform Announcement",
            "body": "Content",
            "priority": "high",
            "is_platform_wide": True,
        },
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 403
    data = response.json()
    assert data["detail_code"] == "announcement.platform_wide_forbidden"


@pytest.mark.asyncio
async def test_platform_announcement_visible_to_all_orgs(
    client: AsyncClient,
    test_jwt_token,
    platform_announcement,
):
    """Test that platform-wide announcement is visible to all users."""
    response = await client.get(
        "/api/v1/announcements/active",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    announcement_ids = [str(a["id"]) for a in data["announcements"]]
    assert str(platform_announcement.id) in announcement_ids


@pytest.mark.asyncio
async def test_platform_announcement_is_platform_wide_flag(
    client: AsyncClient,
    test_jwt_token,
    platform_announcement,
):
    """Test that platform-wide announcement has is_platform_wide=True."""
    response = await client.get(
        "/api/v1/announcements/active",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    for announcement in data["announcements"]:
        if str(announcement["id"]) == str(platform_announcement.id):
            assert announcement["is_platform_wide"] is True
            break


# ─────────────────────────────────────────────────────────────
# Tenant Isolation Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cannot_dismiss_other_org_announcement(
    client: AsyncClient,
    test_jwt_token,
    second_org_announcement,
):
    """Test that user cannot dismiss other org's announcement."""
    response = await client.post(
        f"/api/v1/announcements/{second_org_announcement.id}/dismiss",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_announcements_list_excludes_other_orgs(
    client: AsyncClient,
    test_jwt_token,
    test_announcement,
    second_org_announcement,
):
    """Test that announcement list excludes other org's announcements."""
    response = await client.get(
        "/api/v1/announcements/active",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    announcement_ids = [str(a["id"]) for a in data["announcements"]]
    assert str(second_org_announcement.id) not in announcement_ids


@pytest.mark.asyncio
async def test_cannot_get_other_org_announcement(
    client: AsyncClient,
    user_with_announcement_token,
    second_org_announcement,
):
    """Test that user cannot get other org's announcement by ID."""
    response = await client.get(
        f"/api/v1/announcements/{second_org_announcement.id}",
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_update_other_org_announcement(
    client: AsyncClient,
    user_with_announcement_token,
    second_org_announcement,
):
    """Test that user cannot update other org's announcement."""
    response = await client.put(
        f"/api/v1/announcements/{second_org_announcement.id}",
        json={"title": "Hacked Title"},
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_delete_other_org_announcement(
    client: AsyncClient,
    user_with_announcement_token,
    second_org_announcement,
):
    """Test that user cannot delete other org's announcement."""
    response = await client.delete(
        f"/api/v1/announcements/{second_org_announcement.id}",
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 404


# ─────────────────────────────────────────────────────────────
# Scheduling Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_announcement_with_schedule(
    client: AsyncClient,
    user_with_announcement_token,
):
    """Test creating announcement with start and end times."""
    start = datetime.now(timezone.utc).isoformat()
    response = await client.post(
        "/api/v1/announcements",
        json={
            "title": "Scheduled Announcement",
            "body": "Scheduled content",
            "priority": "normal",
            "start_time": start,
        },
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["start_time"] is not None


# ─────────────────────────────────────────────────────────────
# Styling Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_announcement_with_styling(
    client: AsyncClient,
    user_with_announcement_token,
):
    """Test creating announcement with custom styling."""
    response = await client.post(
        "/api/v1/announcements",
        json={
            "title": "Styled Announcement",
            "body": "Styled content",
            "priority": "high",
            "background_color": "#ff0000",
            "text_color": "#ffffff",
        },
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["background_color"] == "#ff0000"
    assert data["text_color"] == "#ffffff"


# ─────────────────────────────────────────────────────────────
# URL Validation Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_announcement_with_relative_url(
    client: AsyncClient,
    user_with_announcement_token,
):
    """Test creating announcement with relative CTA URL."""
    response = await client.post(
        "/api/v1/announcements",
        json={
            "title": "Announcement",
            "body": "Content",
            "priority": "normal",
            "cta_text": "Go",
            "cta_url": "/dashboard",
        },
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_create_announcement_rejects_javascript_url(
    client: AsyncClient,
    user_with_announcement_token,
):
    """Test that javascript: URLs are rejected."""
    response = await client.post(
        "/api/v1/announcements",
        json={
            "title": "Announcement",
            "body": "Content",
            "priority": "normal",
            "cta_url": "javascript:alert(1)",
        },
        headers={"Authorization": user_with_announcement_token},
    )
    assert response.status_code == 422
