"""
Test cases for user role assignment API endpoints.
Migrated to FastAPI with async/await patterns.
"""

from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_assign_role_admin_required(
    client: AsyncClient, test_admin_token, test_jwt_token, test_user_id, test_role_id
):
    """Test that permission is required to assign roles."""
    # Test with regular user - should fail (no permission)
    response = await client.post(
        "/api/v1/user-roles/assign",
        json={"user_id": test_user_id, "role_id": test_role_id},
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 403

    # Test with super admin - should succeed (bypasses permission check)
    response = await client.post(
        "/api/v1/user-roles/assign",
        json={"user_id": test_user_id, "role_id": test_role_id},
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code in [200, 201]


@pytest.mark.asyncio
async def test_revoke_role(
    client: AsyncClient, test_admin_token, test_user_id, test_role_id
):
    """Test revoking a role from a user."""
    # First assign the role
    await client.post(
        "/api/v1/user-roles/assign",
        json={"user_id": test_user_id, "role_id": test_role_id},
        headers={"Authorization": test_admin_token},
    )

    # Then revoke it
    response = await client.post(
        "/api/v1/user-roles/revoke",
        json={"user_id": test_user_id, "role_id": test_role_id},
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user_role"]["deleted_time"] is not None


@pytest.mark.asyncio
async def test_get_user_roles(
    client: AsyncClient, test_admin_token, test_user_id, test_role_id
):
    """Test getting a user's roles."""
    # Assign a role
    await client.post(
        "/api/v1/user-roles/assign",
        json={"user_id": test_user_id, "role_id": test_role_id},
        headers={"Authorization": test_admin_token},
    )

    # Get user's roles
    response = await client.get(
        f"/api/v1/user-roles/users/{test_user_id}/roles",
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_super_admin_bypasses_admin_check(
    client: AsyncClient, test_admin_token, test_user_id, test_role_id
):
    """Test that super admin can assign/revoke roles without admin role."""
    response = await client.post(
        "/api/v1/user-roles/assign",
        json={"user_id": test_user_id, "role_id": test_role_id},
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code in [200, 201]


@pytest.mark.asyncio
async def test_assign_role_requires_authentication(
    client: AsyncClient, test_user_id, test_role_id
):
    """Test that assigning roles requires authentication."""
    response = await client.post(
        "/api/v1/user-roles/assign",
        json={"user_id": test_user_id, "role_id": test_role_id},
    )
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_get_role_history(
    client: AsyncClient, test_admin_token, test_user_id, test_role_id
):
    """Test getting a user's role history."""
    # Assign a role
    await client.post(
        "/api/v1/user-roles/assign",
        json={"user_id": test_user_id, "role_id": test_role_id},
        headers={"Authorization": test_admin_token},
    )

    # Get role history
    response = await client.get(
        f"/api/v1/user-roles/users/{test_user_id}/roles/history",
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


# ============================================================================
# OWNER ROLE PROTECTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_cannot_revoke_last_owner_role(
    client: AsyncClient, async_session, test_organization, test_admin_token, owner_role
):
    """Test that the last owner's role cannot be revoked."""
    from src.crud.user import create_user
    from src.models.user_role import UserRole

    org_id = str(test_organization.id)

    # Create a user and assign them the owner role
    owner_user = await create_user(
        async_session,
        {
            "email": "singleowner@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        org_id,
    )

    # Assign owner role
    user_role = UserRole(
        user_id=owner_user.id,
        role_id=owner_role.id,
        organization_id=test_organization.id,
    )
    async_session.add(user_role)
    await async_session.commit()

    # Try to revoke the owner role - should fail
    response = await client.post(
        "/api/v1/user-roles/revoke",
        json={"user_id": str(owner_user.id), "role_id": str(owner_role.id)},
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 400
    data = response.json()
    assert "at least one owner" in data["detail"].lower()


@pytest.mark.asyncio
async def test_can_revoke_owner_role_when_multiple_owners(
    client: AsyncClient, async_session, test_organization, test_admin_token, owner_role
):
    """Test that an owner's role can be revoked if there are multiple owners."""
    from src.crud.user import create_user
    from src.models.user_role import UserRole

    org_id = str(test_organization.id)

    # Create two users and assign them the owner role
    owner_user1 = await create_user(
        async_session,
        {
            "email": "owner1@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        org_id,
    )
    owner_user2 = await create_user(
        async_session,
        {
            "email": "owner2@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        org_id,
    )

    # Assign owner role to both users
    user_role1 = UserRole(
        user_id=owner_user1.id,
        role_id=owner_role.id,
        organization_id=test_organization.id,
    )
    user_role2 = UserRole(
        user_id=owner_user2.id,
        role_id=owner_role.id,
        organization_id=test_organization.id,
    )
    async_session.add(user_role1)
    async_session.add(user_role2)
    await async_session.commit()

    # Revoke owner role from first user - should succeed since there's another owner
    response = await client.post(
        "/api/v1/user-roles/revoke",
        json={"user_id": str(owner_user1.id), "role_id": str(owner_role.id)},
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "revoked" in data["message"].lower()


@pytest.mark.asyncio
async def test_cannot_revoke_second_to_last_owner_after_first(
    client: AsyncClient, async_session, test_organization, test_admin_token, owner_role
):
    """Test that after revoking one owner, the remaining owner's role cannot be revoked."""
    from src.crud.user import create_user
    from src.models.user_role import UserRole

    org_id = str(test_organization.id)

    # Create two users and assign them the owner role
    owner_user1 = await create_user(
        async_session,
        {
            "email": "owner_a@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        org_id,
    )
    owner_user2 = await create_user(
        async_session,
        {
            "email": "owner_b@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        org_id,
    )

    # Assign owner role to both users
    user_role1 = UserRole(
        user_id=owner_user1.id,
        role_id=owner_role.id,
        organization_id=test_organization.id,
    )
    user_role2 = UserRole(
        user_id=owner_user2.id,
        role_id=owner_role.id,
        organization_id=test_organization.id,
    )
    async_session.add(user_role1)
    async_session.add(user_role2)
    await async_session.commit()

    # Revoke owner role from first user - should succeed
    response1 = await client.post(
        "/api/v1/user-roles/revoke",
        json={"user_id": str(owner_user1.id), "role_id": str(owner_role.id)},
        headers={"Authorization": test_admin_token},
    )
    assert response1.status_code == 200

    # Try to revoke owner role from second user - should fail (last owner)
    response2 = await client.post(
        "/api/v1/user-roles/revoke",
        json={"user_id": str(owner_user2.id), "role_id": str(owner_role.id)},
        headers={"Authorization": test_admin_token},
    )
    assert response2.status_code == 400
    data = response2.json()
    assert "at least one owner" in data["detail"].lower()
