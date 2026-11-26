"""
Test cases for enhanced user API endpoints.
Tests for enhanced user list, user detail, and session invalidation.
"""

from uuid import uuid4

from httpx import AsyncClient
import pytest


# ============================================================================
# ENHANCED USER LIST TESTS (/api/v1/users)
# ============================================================================


@pytest.mark.asyncio
async def test_get_enhanced_users_list(
    client: AsyncClient, async_session, test_organization, test_admin_token
):
    """Test the enhanced users list endpoint."""
    response = await client.get(
        "/api/v1/users",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data


@pytest.mark.asyncio
async def test_get_enhanced_users_with_pagination(
    client: AsyncClient, async_session, test_organization, test_admin_token
):
    """Test enhanced users list with pagination parameters."""
    response = await client.get(
        "/api/v1/users?limit=5&offset=0",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 5
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_get_enhanced_users_with_sparse_fields(
    client: AsyncClient, async_session, test_organization, test_admin_token
):
    """Test enhanced users list with sparse fieldsets."""
    response = await client.get(
        "/api/v1/users?fields=id,email,first_name,last_name",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    # Items should have requested fields
    if data["items"]:
        item = data["items"][0]
        assert "id" in item
        assert "email" in item


@pytest.mark.asyncio
async def test_get_enhanced_users_with_status_filter(
    client: AsyncClient, async_session, test_organization, test_admin_token
):
    """Test enhanced users list filtered by status."""
    response = await client.get(
        "/api/v1/users?filter[status]=active",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    # All returned users should be active (not suspended)
    for item in data["items"]:
        assert item.get("suspension_status") in [None, "active"]


@pytest.mark.asyncio
async def test_get_enhanced_users_with_search(
    client: AsyncClient, async_session, test_organization, test_admin_token, test_user
):
    """Test enhanced users list with search query."""
    # Search for the test user
    response = await client.get(
        f"/api/v1/users?q={test_user.email[:5]}",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_get_enhanced_users_with_sort(
    client: AsyncClient, async_session, test_organization, test_admin_token
):
    """Test enhanced users list with sorting."""
    response = await client.get(
        "/api/v1/users?sort=created_time:desc",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    # Verify sorting order (most recent first)
    if len(data["items"]) >= 2:
        first_time = data["items"][0].get("created_time")
        second_time = data["items"][1].get("created_time")
        if first_time and second_time:
            assert first_time >= second_time


@pytest.mark.asyncio
async def test_get_enhanced_users_requires_auth(
    client: AsyncClient, async_session, test_organization
):
    """Test that enhanced users list requires authentication."""
    response = await client.get("/api/v1/users")

    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_get_enhanced_users_requires_admin(
    client: AsyncClient, async_session, test_organization, test_jwt_token
):
    """Test that enhanced users list requires admin permissions."""
    response = await client.get(
        "/api/v1/users",
        headers={"Authorization": test_jwt_token},
    )

    # Regular user should be denied
    assert response.status_code in [401, 403]


# ============================================================================
# USER DETAIL TESTS (/api/v1/users/{id}/detail)
# ============================================================================


@pytest.mark.asyncio
async def test_get_user_detail(
    client: AsyncClient, async_session, test_organization, test_admin_token, test_user
):
    """Test the user detail endpoint."""
    response = await client.get(
        f"/api/v1/users/{test_user.id}/detail",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()

    # Check required fields
    assert "id" in data
    assert "email" in data
    assert "roles" in data
    assert "user_types" in data
    assert "sessions" in data
    assert "two_factor" in data


@pytest.mark.asyncio
async def test_get_user_detail_includes_sessions(
    client: AsyncClient, async_session, test_organization, test_admin_token, test_user
):
    """Test that user detail includes session information."""
    response = await client.get(
        f"/api/v1/users/{test_user.id}/detail",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data
    assert isinstance(data["sessions"], list)


@pytest.mark.asyncio
async def test_get_user_detail_includes_two_factor(
    client: AsyncClient, async_session, test_organization, test_admin_token, test_user
):
    """Test that user detail includes 2FA status."""
    response = await client.get(
        f"/api/v1/users/{test_user.id}/detail",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "two_factor" in data
    assert "is_enabled" in data["two_factor"]
    assert "backup_codes_remaining" in data["two_factor"]


@pytest.mark.asyncio
async def test_get_user_detail_not_found(
    client: AsyncClient, async_session, test_organization, test_admin_token
):
    """Test user detail for non-existent user."""
    fake_id = str(uuid4())
    response = await client.get(
        f"/api/v1/users/{fake_id}/detail",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_user_detail_requires_auth(
    client: AsyncClient, async_session, test_organization, test_user
):
    """Test that user detail requires authentication."""
    response = await client.get(f"/api/v1/users/{test_user.id}/detail")

    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_get_user_detail_requires_admin(
    client: AsyncClient, async_session, test_organization, test_jwt_token, test_user
):
    """Test that user detail requires admin permissions."""
    response = await client.get(
        f"/api/v1/users/{test_user.id}/detail",
        headers={"Authorization": test_jwt_token},
    )

    # Regular user should be denied
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_get_user_detail_tenant_isolation(
    client: AsyncClient, async_session, test_organization, test_admin_token
):
    """Test that user detail respects tenant isolation."""
    from src.crud.user import create_user
    from src.models.organization import Organization

    # Create a different organization
    other_org = Organization(
        name="Other Org",
        slug="other-org",
        is_active=True,
    )
    async_session.add(other_org)
    await async_session.commit()

    # Create user in the other organization
    other_user = await create_user(
        async_session,
        {
            "email": "other@otherorg.com",
            "password": "Password123!",
            "email_verified": True,
        },
        str(other_org.id),
    )

    # Try to access user from another organization
    response = await client.get(
        f"/api/v1/users/{other_user.id}/detail",
        headers={"Authorization": test_admin_token},
    )

    # Should either return 404 or 403 (not found due to tenant isolation)
    assert response.status_code in [403, 404]


# ============================================================================
# SESSION INVALIDATION TESTS (/api/v1/users/{id}/sessions/{session_id})
# ============================================================================


@pytest.mark.asyncio
async def test_invalidate_session_not_found(
    client: AsyncClient, async_session, test_organization, test_admin_token, test_user
):
    """Test invalidating a non-existent session."""
    fake_session_id = str(uuid4())
    response = await client.delete(
        f"/api/v1/users/{test_user.id}/sessions/{fake_session_id}",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_invalidate_session_user_not_found(
    client: AsyncClient, async_session, test_organization, test_admin_token
):
    """Test invalidating session for non-existent user."""
    fake_user_id = str(uuid4())
    fake_session_id = str(uuid4())
    response = await client.delete(
        f"/api/v1/users/{fake_user_id}/sessions/{fake_session_id}",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_invalidate_session_requires_auth(
    client: AsyncClient, async_session, test_organization, test_user
):
    """Test that session invalidation requires authentication."""
    fake_session_id = str(uuid4())
    response = await client.delete(
        f"/api/v1/users/{test_user.id}/sessions/{fake_session_id}"
    )

    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_invalidate_session_requires_admin(
    client: AsyncClient, async_session, test_organization, test_jwt_token, test_user
):
    """Test that session invalidation requires admin permissions."""
    fake_session_id = str(uuid4())
    response = await client.delete(
        f"/api/v1/users/{test_user.id}/sessions/{fake_session_id}",
        headers={"Authorization": test_jwt_token},
    )

    # Regular user should be denied
    assert response.status_code in [401, 403]


# ============================================================================
# COMBINED TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_enhanced_users_filtering_combined(
    client: AsyncClient, async_session, test_organization, test_admin_token
):
    """Test enhanced users with multiple filters combined."""
    response = await client.get(
        "/api/v1/users?filter[status]=active&filter[email_verified]=true&limit=10",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["limit"] == 10
