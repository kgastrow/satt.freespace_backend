"""
Test cases for user API endpoints.
Migrated to FastAPI with async/await patterns.
"""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_register_endpoint(client: AsyncClient, async_session, test_organization):
    """Test the user registration endpoint."""
    # Create a new user
    user_data = {
        "email": "newuser@test.com",
        "password": "Password123!",
        "phone": "+27737442554",
        "organization_slug": "test-org",
    }

    with patch("src.services.email.email_service.send_email", new_callable=AsyncMock):
        response = await client.post("/api/v1/user/register", json=user_data)

    assert response.status_code in [200, 201]
    data = response.json()
    assert "user" in data or "message" in data


@pytest.mark.asyncio
async def test_register_existing_unverified_user(
    client: AsyncClient, async_session, test_organization
):
    """Test registering a user that exists but hasn't verified their email."""
    from src.crud.user import create_user

    # Create a user with email_verified=False
    user_data = {
        "email": "unverified@test.com",
        "password": "Password123!",
        "email_verified": False,
        "phone": "+27737442555",
    }

    await create_user(async_session, user_data, str(test_organization.id))

    # Try to register with the same email
    register_data = {
        "email": "unverified@test.com",
        "password": "NewPassword123!",
        "phone": "+27737442555",
        "organization_slug": "test-org",
    }

    with patch("src.services.email.email_service.send_email", new_callable=AsyncMock):
        response = await client.post("/api/v1/user/register", json=register_data)

    # Should return success or specific message about verification
    assert response.status_code in [200, 201, 400]


@pytest.mark.asyncio
async def test_me_endpoint(client: AsyncClient, test_user, test_jwt_token):
    """Test the me endpoint."""
    response = await client.get(
        "/api/v1/user/me", headers={"Authorization": test_jwt_token}
    )

    assert response.status_code == 200
    data = response.json()
    assert "user" in data or "email" in data


@pytest.mark.asyncio
async def test_update_me_endpoint(client: AsyncClient, test_user, test_jwt_token):
    """Test the update me endpoint."""
    update_data = {"first_name": "Updated", "last_name": "Name"}

    response = await client.put(
        "/api/v1/user/me", json=update_data, headers={"Authorization": test_jwt_token}
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_me_endpoint_unauthenticated(client: AsyncClient):
    """Test that me endpoint requires authentication."""
    response = await client.get("/api/v1/user/me")

    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_update_me_endpoint_unauthenticated(client: AsyncClient):
    """Test that update me endpoint requires authentication."""
    update_data = {"first_name": "Updated", "last_name": "Name"}

    response = await client.put("/api/v1/user/me", json=update_data)

    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient, test_organization):
    """Test registration with invalid email format."""
    user_data = {
        "email": "invalid-email",
        "password": "Password123!",
        "organization_slug": "test-org",
    }

    response = await client.post("/api/v1/user/register", json=user_data)

    # Should return validation error
    assert response.status_code == 422


# ============================================================================
# ADMIN USER MANAGEMENT TESTS (/api/users)
# ============================================================================


@pytest.mark.asyncio
async def test_cannot_delete_organization_owner_via_users_api(
    client: AsyncClient, async_session, test_organization, test_admin_token, owner_role
):
    """Test that organization owner cannot be deleted via /api/users endpoint."""
    from src.crud.user import create_user
    from src.models.user_role import UserRole

    org_id = str(test_organization.id)

    # Create a user and assign them the owner role
    owner_user = await create_user(
        async_session,
        {
            "email": "owneruser@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        org_id,
    )

    # Assign owner role to the user
    user_role = UserRole(
        user_id=owner_user.id,
        role_id=owner_role.id,
        organization_id=test_organization.id,
    )
    async_session.add(user_role)
    await async_session.commit()

    # Super admin tries to delete the owner
    response = await client.delete(
        f"/api/v1/users/{owner_user.id}", headers={"Authorization": test_admin_token}
    )

    assert response.status_code == 403
    data = response.json()
    assert "owner" in data["detail"].lower()


@pytest.mark.asyncio
async def test_can_delete_regular_user_via_users_api(
    client: AsyncClient, async_session, test_organization, test_admin_token
):
    """Test that regular users (non-owners) can be deleted via /api/users endpoint."""
    from src.crud.user import create_user

    org_id = str(test_organization.id)

    # Create a regular user (no owner role)
    regular_user = await create_user(
        async_session,
        {
            "email": "regularuser@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        org_id,
    )

    # Super admin deletes the regular user
    response = await client.delete(
        f"/api/v1/users/{regular_user.id}", headers={"Authorization": test_admin_token}
    )

    assert response.status_code == 200
    data = response.json()
    assert "deleted" in data["message"].lower()
