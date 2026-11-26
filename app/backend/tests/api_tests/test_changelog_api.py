"""
API tests for changelog endpoints.

Tests verify:
- User view published changelogs
- Admin CRUD operations
- View tracking
- Unread counts
- Platform-wide vs org-scoped
- Tenant isolation
"""

from datetime import datetime, timezone
from uuid import uuid4

from httpx import AsyncClient
import pytest


# ─────────────────────────────────────────────────────────────
# User Endpoint Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_published_changelogs_requires_auth(client: AsyncClient):
    """Test that getting published changelogs requires authentication."""
    response = await client.get("/api/v1/changelogs/published")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_published_changelogs(
    client: AsyncClient,
    test_jwt_token,
    test_changelog,
):
    """Test getting published changelogs."""
    response = await client.get(
        "/api/v1/changelogs/published",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "unread_count" in data


@pytest.mark.asyncio
async def test_get_published_changelogs_with_category_filter(
    client: AsyncClient,
    test_jwt_token,
    test_changelog,
):
    """Test filtering changelogs by category."""
    response = await client.get(
        "/api/v1/changelogs/published?category=feature",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["category"] == "feature"


@pytest.mark.asyncio
async def test_get_unread_count(
    client: AsyncClient,
    test_jwt_token,
    test_changelog,
):
    """Test getting unread changelog count."""
    response = await client.get(
        "/api/v1/changelogs/unread-count",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert data["count"] >= 1


@pytest.mark.asyncio
async def test_get_unread_count_requires_auth(client: AsyncClient):
    """Test that getting unread count requires authentication."""
    response = await client.get("/api/v1/changelogs/unread-count")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_mark_changelog_viewed(
    client: AsyncClient,
    test_jwt_token,
    test_changelog,
):
    """Test marking a changelog as viewed."""
    response = await client.post(
        f"/api/v1/changelogs/{test_changelog.id}/view",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["message_code"] == "changelog.viewed"


@pytest.mark.asyncio
async def test_mark_changelog_viewed_reduces_unread_count(
    client: AsyncClient,
    test_jwt_token,
    test_changelog,
):
    """Test that marking a changelog as viewed reduces unread count."""
    # Get initial unread count
    response = await client.get(
        "/api/v1/changelogs/unread-count",
        headers={"Authorization": test_jwt_token},
    )
    initial_count = response.json()["count"]

    # Mark as viewed
    await client.post(
        f"/api/v1/changelogs/{test_changelog.id}/view",
        headers={"Authorization": test_jwt_token},
    )

    # Check unread count decreased
    response = await client.get(
        "/api/v1/changelogs/unread-count",
        headers={"Authorization": test_jwt_token},
    )
    new_count = response.json()["count"]
    assert new_count < initial_count


@pytest.mark.asyncio
async def test_mark_changelog_viewed_not_found(
    client: AsyncClient,
    test_jwt_token,
):
    """Test marking non-existent changelog as viewed returns 404."""
    response = await client.post(
        f"/api/v1/changelogs/{uuid4()}/view",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_mark_all_changelogs_viewed(
    client: AsyncClient,
    test_jwt_token,
    test_changelog,
):
    """Test marking all changelogs as viewed."""
    response = await client.post(
        "/api/v1/changelogs/mark-all-viewed",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert data["message_code"] == "changelog.all_viewed"


@pytest.mark.asyncio
async def test_mark_all_changelogs_viewed_requires_auth(client: AsyncClient):
    """Test that marking all changelogs as viewed requires authentication."""
    response = await client.post("/api/v1/changelogs/mark-all-viewed")
    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────
# Admin Endpoint Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_changelogs_requires_permission(
    client: AsyncClient,
    test_jwt_token,
):
    """Test that listing all changelogs requires changelog:write permission."""
    response = await client.get(
        "/api/v1/changelogs",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_changelogs_as_admin(
    client: AsyncClient,
    user_with_changelog_token,
    test_changelog,
):
    """Test listing changelogs with permission."""
    response = await client.get(
        "/api/v1/changelogs",
        headers={"Authorization": user_with_changelog_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_list_changelogs_includes_drafts(
    client: AsyncClient,
    user_with_changelog_token,
    async_session,
    test_organization,
    test_admin_user,
):
    """Test that admin list includes draft changelogs."""
    from src.models.changelog import Changelog

    draft = Changelog(
        organization_id=test_organization.id,
        version="3.0.0",
        title="Draft Changelog",
        body="Draft content",
        category="feature",
        release_date=datetime.now(timezone.utc),
        is_published=False,
        created_by_id=test_admin_user.id,
    )
    async_session.add(draft)
    await async_session.commit()

    response = await client.get(
        "/api/v1/changelogs",
        headers={"Authorization": user_with_changelog_token},
    )
    assert response.status_code == 200
    data = response.json()
    titles = [item["title"] for item in data["items"]]
    assert "Draft Changelog" in titles


@pytest.mark.asyncio
async def test_create_changelog(
    client: AsyncClient,
    user_with_changelog_token,
):
    """Test creating a changelog entry."""
    response = await client.post(
        "/api/v1/changelogs",
        json={
            "version": "2.0.0",
            "title": "New Release",
            "body": "Release notes content",
            "category": "feature",
            "release_date": datetime.now(timezone.utc).isoformat(),
            "is_published": False,
        },
        headers={"Authorization": user_with_changelog_token},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["version"] == "2.0.0"
    assert data["title"] == "New Release"
    assert data["is_platform_wide"] is False


@pytest.mark.asyncio
async def test_create_changelog_requires_permission(
    client: AsyncClient,
    test_jwt_token,
):
    """Test that creating changelog requires changelog:write permission."""
    response = await client.post(
        "/api/v1/changelogs",
        json={
            "version": "2.0.0",
            "title": "New Release",
            "body": "Content",
            "category": "feature",
            "release_date": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_changelog_invalid_category(
    client: AsyncClient,
    user_with_changelog_token,
):
    """Test creating changelog with invalid category."""
    response = await client.post(
        "/api/v1/changelogs",
        json={
            "version": "2.0.0",
            "title": "New Release",
            "body": "Content",
            "category": "invalid_category",
            "release_date": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Authorization": user_with_changelog_token},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_changelog_missing_required_fields(
    client: AsyncClient,
    user_with_changelog_token,
):
    """Test creating changelog with missing required fields."""
    response = await client.post(
        "/api/v1/changelogs",
        json={
            "version": "2.0.0",
            # Missing title, body, release_date
        },
        headers={"Authorization": user_with_changelog_token},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_changelog(
    client: AsyncClient,
    user_with_changelog_token,
    test_changelog,
):
    """Test updating a changelog entry."""
    response = await client.put(
        f"/api/v1/changelogs/{test_changelog.id}",
        json={"title": "Updated Title"},
        headers={"Authorization": user_with_changelog_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_update_changelog_no_fields(
    client: AsyncClient,
    user_with_changelog_token,
    test_changelog,
):
    """Test updating changelog with no fields returns 400."""
    response = await client.put(
        f"/api/v1/changelogs/{test_changelog.id}",
        json={},
        headers={"Authorization": user_with_changelog_token},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail_code"] == "changelog.no_fields_provided"


@pytest.mark.asyncio
async def test_update_changelog_not_found(
    client: AsyncClient,
    user_with_changelog_token,
):
    """Test updating non-existent changelog."""
    response = await client.put(
        f"/api/v1/changelogs/{uuid4()}",
        json={"title": "Updated"},
        headers={"Authorization": user_with_changelog_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_changelog(
    client: AsyncClient,
    user_with_changelog_token,
    test_changelog,
):
    """Test soft deleting a changelog entry."""
    response = await client.delete(
        f"/api/v1/changelogs/{test_changelog.id}",
        headers={"Authorization": user_with_changelog_token},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_changelog_not_found(
    client: AsyncClient,
    user_with_changelog_token,
):
    """Test deleting non-existent changelog."""
    response = await client.delete(
        f"/api/v1/changelogs/{uuid4()}",
        headers={"Authorization": user_with_changelog_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_changelog_requires_permission(
    client: AsyncClient,
    test_jwt_token,
    test_changelog,
):
    """Test that deleting changelog requires permission."""
    response = await client.delete(
        f"/api/v1/changelogs/{test_changelog.id}",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 403


# ─────────────────────────────────────────────────────────────
# Platform-wide Changelog Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_platform_changelog_requires_super_admin(
    client: AsyncClient,
    user_with_changelog_token,
):
    """Test that creating platform-wide changelog requires super admin."""
    response = await client.post(
        "/api/v1/changelogs",
        json={
            "version": "1.0.0",
            "title": "Platform Changelog",
            "body": "Content",
            "category": "feature",
            "release_date": datetime.now(timezone.utc).isoformat(),
            "is_platform_wide": True,
        },
        headers={"Authorization": user_with_changelog_token},
    )
    assert response.status_code == 403
    data = response.json()
    assert data["detail_code"] == "changelog.platform_wide_forbidden"


@pytest.mark.asyncio
async def test_platform_changelog_visible_to_all_orgs(
    client: AsyncClient,
    test_jwt_token,
    platform_changelog,
):
    """Test that platform-wide changelog is visible to all users."""
    response = await client.get(
        "/api/v1/changelogs/published",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    changelog_ids = [str(item["id"]) for item in data["items"]]
    assert str(platform_changelog.id) in changelog_ids


@pytest.mark.asyncio
async def test_platform_changelog_is_platform_wide_flag(
    client: AsyncClient,
    test_jwt_token,
    platform_changelog,
):
    """Test that platform-wide changelog has is_platform_wide=True."""
    response = await client.get(
        "/api/v1/changelogs/published",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        if str(item["id"]) == str(platform_changelog.id):
            assert item["is_platform_wide"] is True
            break


# ─────────────────────────────────────────────────────────────
# Tenant Isolation Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cannot_view_other_org_changelog(
    client: AsyncClient,
    test_jwt_token,
    second_org_changelog,
):
    """Test that user cannot mark other org's changelog as viewed."""
    response = await client.post(
        f"/api/v1/changelogs/{second_org_changelog.id}/view",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_changelog_list_excludes_other_orgs(
    client: AsyncClient,
    test_jwt_token,
    test_changelog,
    second_org_changelog,
):
    """Test that changelog list excludes other org's changelogs."""
    response = await client.get(
        "/api/v1/changelogs/published",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    changelog_ids = [str(item["id"]) for item in data["items"]]
    assert str(second_org_changelog.id) not in changelog_ids


@pytest.mark.asyncio
async def test_cannot_update_other_org_changelog(
    client: AsyncClient,
    user_with_changelog_token,
    second_org_changelog,
):
    """Test that user cannot update other org's changelog."""
    response = await client.put(
        f"/api/v1/changelogs/{second_org_changelog.id}",
        json={"title": "Hacked Title"},
        headers={"Authorization": user_with_changelog_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_delete_other_org_changelog(
    client: AsyncClient,
    user_with_changelog_token,
    second_org_changelog,
):
    """Test that user cannot delete other org's changelog."""
    response = await client.delete(
        f"/api/v1/changelogs/{second_org_changelog.id}",
        headers={"Authorization": user_with_changelog_token},
    )
    assert response.status_code == 404


# ─────────────────────────────────────────────────────────────
# Pagination Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_published_changelogs_pagination(
    client: AsyncClient,
    test_jwt_token,
    test_changelog,
):
    """Test that pagination parameters are applied."""
    response = await client.get(
        "/api/v1/changelogs/published?limit=10&offset=0",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 10
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_published_changelogs_pagination_invalid_limit(
    client: AsyncClient,
    test_jwt_token,
):
    """Test that invalid limit returns 422."""
    response = await client.get(
        "/api/v1/changelogs/published?limit=1000",  # Max is 500
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 422
