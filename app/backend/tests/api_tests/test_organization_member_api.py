"""
Test cases for organization member management API endpoints.
Migrated to FastAPI with async/await patterns.
"""

import uuid

from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_list_organization_members_as_admin(
    client: AsyncClient, async_session, test_organization, admin_token
):
    """Test that admin can list members of their organization."""
    from src.crud.user import create_user

    # Create additional users in the organization
    await create_user(
        async_session,
        {"email": "user2@test.com", "password": "Password123!", "email_verified": True},
        str(test_organization.id),
    )
    await create_user(
        async_session,
        {"email": "user3@test.com", "password": "Password123!", "email_verified": True},
        str(test_organization.id),
    )

    # List members
    response = await client.get(
        f"/api/v1/organizations/{test_organization.id}/members",
        headers={"Authorization": admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 3  # At least the 3 users we created

    # Check that all members belong to the organization
    member_emails = [m["email"] for m in data["items"]]
    assert "user2@test.com" in member_emails
    assert "user3@test.com" in member_emails


@pytest.mark.asyncio
async def test_list_organization_members_as_super_admin(
    client: AsyncClient,
    async_session,
    test_organization,
    second_organization,
    test_admin_token,
):
    """Test that super admin can list members of any organization."""
    from src.crud.user import create_user

    # Create user in second organization
    await create_user(
        async_session,
        {
            "email": "user_org2@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        str(second_organization.id),
    )

    # Super admin lists members of second organization
    response = await client.get(
        f"/api/v1/organizations/{second_organization.id}/members",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_list_organization_members_as_regular_user(
    client: AsyncClient, test_organization, test_jwt_token
):
    """Test that regular user (without admin role) cannot list members."""
    # Regular user tries to list members
    response = await client.get(
        f"/api/v1/organizations/{test_organization.id}/members",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_organization_members_different_org(
    client: AsyncClient, second_organization, admin_token
):
    """Test that admin cannot list members of different organization."""
    # admin from test_organization tries to list members of second_organization
    response = await client.get(
        f"/api/v1/organizations/{second_organization.id}/members",
        headers={"Authorization": admin_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_organization_members_with_pagination(
    client: AsyncClient, async_session, test_organization, admin_token
):
    """Test pagination of organization members list."""
    from src.crud.user import create_user

    # Create 5 additional users
    for i in range(5):
        await create_user(
            async_session,
            {
                "email": f"user{i}@test.com",
                "password": "Password123!",
                "email_verified": True,
            },
            str(test_organization.id),
        )

    # Get first page with limit=2
    response = await client.get(
        f"/api/v1/organizations/{test_organization.id}/members?limit=2&offset=0",
        headers={"Authorization": admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] >= 6  # At least 6 users (1 from fixture + 5 created)


@pytest.mark.asyncio
async def test_remove_organization_member_as_admin(
    client: AsyncClient,
    async_session,
    test_organization,
    admin_token,
    admin_user,
    admin_role,
):
    """Test that admin can remove a member from their organization."""
    from src.crud.user import create_user
    from src.models.permission import Permission
    from src.models.role_permission import RolePermission

    org_id = str(test_organization.id)

    # Grant users:delete permission to admin role
    perm = Permission(
        code="users:delete",
        name="Delete Users",
        resource="users",
        action="delete",
        display_order=0,
    )
    async_session.add(perm)
    await async_session.commit()
    await async_session.refresh(perm)

    role_perm = RolePermission(role_id=admin_role.id, permission_id=perm.id)
    async_session.add(role_perm)
    await async_session.commit()

    # Create a user to remove
    user_to_remove = await create_user(
        async_session,
        {
            "email": "toremove@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        org_id,
    )

    user_to_remove_id = str(user_to_remove.id)

    # Remove the user
    response = await client.delete(
        f"/api/v1/organizations/{org_id}/members/{user_to_remove_id}",
        headers={"Authorization": admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "message" in data

    # Verify user is soft deleted
    from src.crud.user import get_user_by_id

    removed_user = await get_user_by_id(async_session, user_to_remove_id, org_id)
    assert removed_user is None  # Should not be found (soft deleted)


@pytest.mark.asyncio
async def test_remove_organization_member_as_super_admin(
    client: AsyncClient, async_session, second_organization, test_admin_token
):
    """Test that super admin can remove a member from any organization."""
    from src.crud.user import create_user

    # Create a user in second organization
    user_to_remove = await create_user(
        async_session,
        {
            "email": "toremove2@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        str(second_organization.id),
    )

    # Super admin removes the user
    response = await client.delete(
        f"/api/v1/organizations/{second_organization.id}/members/{user_to_remove.id}",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "message" in data


@pytest.mark.asyncio
async def test_remove_organization_member_as_regular_user(
    client: AsyncClient, async_session, test_organization, test_user, test_jwt_token
):
    """Test that regular user cannot remove members."""
    from src.crud.user import create_user

    # Create another user
    other_user = await create_user(
        async_session,
        {"email": "other@test.com", "password": "Password123!", "email_verified": True},
        str(test_organization.id),
    )

    # Regular user tries to remove another user
    response = await client.delete(
        f"/api/v1/organizations/{test_organization.id}/members/{other_user.id}",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_remove_nonexistent_member(
    client: AsyncClient, async_session, test_organization, admin_token, admin_role
):
    """Test removing a member that doesn't exist."""
    from src.models.permission import Permission
    from src.models.role_permission import RolePermission

    # Grant users:delete permission to admin role
    perm = Permission(
        code="users:delete",
        name="Delete Users",
        resource="users",
        action="delete",
        display_order=0,
    )
    async_session.add(perm)
    await async_session.commit()
    await async_session.refresh(perm)

    role_perm = RolePermission(role_id=admin_role.id, permission_id=perm.id)
    async_session.add(role_perm)
    await async_session.commit()

    fake_user_id = str(uuid.uuid4())

    response = await client.delete(
        f"/api/v1/organizations/{test_organization.id}/members/{fake_user_id}",
        headers={"Authorization": admin_token},
    )

    assert response.status_code == 400 or response.status_code == 404


@pytest.mark.asyncio
async def test_get_organization_member_count_as_member(
    client: AsyncClient, async_session, test_organization, test_user, test_jwt_token
):
    """Test that organization members can get member count."""
    from src.crud.user import create_user

    # Create additional users
    for i in range(3):
        await create_user(
            async_session,
            {
                "email": f"count{i}@test.com",
                "password": "Password123!",
                "email_verified": True,
            },
            str(test_organization.id),
        )

    # Get member count
    response = await client.get(
        f"/api/v1/organizations/{test_organization.id}/members/count",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "member_count" in data
    assert "organization_id" in data
    assert data["member_count"] >= 4  # At least 4 users (test_user + 3 created)


@pytest.mark.asyncio
async def test_get_organization_member_count_as_super_admin(
    client: AsyncClient, async_session, second_organization, test_admin_token
):
    """Test that super admin can get member count of any organization."""
    from src.crud.user import create_user

    # Create user in second organization
    await create_user(
        async_session,
        {
            "email": "count_org2@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        str(second_organization.id),
    )

    # Super admin gets count of second organization
    response = await client.get(
        f"/api/v1/organizations/{second_organization.id}/members/count",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["member_count"] >= 1


@pytest.mark.asyncio
async def test_get_organization_member_count_different_org(
    client: AsyncClient, second_organization, test_jwt_token
):
    """Test that user cannot get member count of different organization."""
    # User from test_organization tries to get count of second_organization
    response = await client.get(
        f"/api/v1/organizations/{second_organization.id}/members/count",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_members_without_authentication(
    client: AsyncClient, test_organization
):
    """Test that listing members requires authentication."""
    response = await client.get(f"/api/v1/organizations/{test_organization.id}/members")

    assert response.status_code == 401 or response.status_code == 403


@pytest.mark.asyncio
async def test_remove_member_without_authentication(
    client: AsyncClient, test_organization
):
    """Test that removing members requires authentication."""
    fake_user_id = str(uuid.uuid4())

    response = await client.delete(
        f"/api/v1/organizations/{test_organization.id}/members/{fake_user_id}"
    )

    assert response.status_code == 401 or response.status_code == 403


@pytest.mark.asyncio
async def test_cannot_remove_organization_owner(
    client: AsyncClient,
    async_session,
    test_organization,
    admin_token,
    owner_role,
    admin_role,
):
    """Test that organization owner cannot be removed via member removal endpoint."""
    from src.crud.user import create_user
    from src.models.permission import Permission
    from src.models.role_permission import RolePermission
    from src.models.user_role import UserRole

    org_id = str(test_organization.id)

    # Grant users:delete permission to admin role
    perm = Permission(
        code="users:delete",
        name="Delete Users",
        resource="users",
        action="delete",
        display_order=0,
    )
    async_session.add(perm)
    await async_session.commit()
    await async_session.refresh(perm)

    role_perm = RolePermission(role_id=admin_role.id, permission_id=perm.id)
    async_session.add(role_perm)
    await async_session.commit()

    # Create a user and assign them the owner role
    owner_user = await create_user(
        async_session,
        {"email": "owner@test.com", "password": "Password123!", "email_verified": True},
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

    # Try to remove the owner
    response = await client.delete(
        f"/api/v1/organizations/{org_id}/members/{owner_user.id}",
        headers={"Authorization": admin_token},
    )

    assert response.status_code == 403
    data = response.json()
    assert "owner" in data["detail"].lower()


@pytest.mark.asyncio
async def test_super_admin_cannot_remove_organization_owner(
    client: AsyncClient, async_session, test_organization, test_admin_token, owner_role
):
    """Test that even super admin cannot remove organization owner via member endpoint."""
    from src.crud.user import create_user
    from src.models.user_role import UserRole

    org_id = str(test_organization.id)

    # Create a user and assign them the owner role
    owner_user = await create_user(
        async_session,
        {
            "email": "owner2@test.com",
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

    # Super admin tries to remove the owner
    response = await client.delete(
        f"/api/v1/organizations/{org_id}/members/{owner_user.id}",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 403
    data = response.json()
    assert "owner" in data["detail"].lower()


# ============================================================================
# ORGANIZATION DELETION REQUEST TESTS
# ============================================================================


@pytest.fixture
async def owner_user_with_token(async_session, test_organization, owner_role):
    """Create an owner user with JWT token for testing deletion requests."""
    from src.core.security import create_access_token
    from src.crud.user import create_user
    from src.models.user_role import UserRole

    org_id = str(test_organization.id)

    # Create a user
    owner_user = await create_user(
        async_session,
        {
            "email": "orgowner@test.com",
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

    # Create token
    token = create_access_token(user_id=str(owner_user.id), organization_id=org_id)

    return owner_user, f"Bearer {token}"


@pytest.mark.asyncio
async def test_owner_can_request_organization_deletion(
    client: AsyncClient, async_session, test_organization, owner_user_with_token
):
    """Test that organization owner can request deletion of their organization."""
    owner_user, owner_token = owner_user_with_token
    org_id = str(test_organization.id)

    response = await client.post(
        f"/api/v1/organizations/{org_id}/request-deletion",
        headers={"Authorization": owner_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "deletion request submitted" in data["message"].lower()
    assert data["organization_id"] == org_id
    assert "deletion_requested_time" in data


@pytest.mark.asyncio
async def test_non_owner_cannot_request_organization_deletion(
    client: AsyncClient, test_organization, test_jwt_token
):
    """Test that non-owner users cannot request organization deletion."""
    org_id = str(test_organization.id)

    response = await client.post(
        f"/api/v1/organizations/{org_id}/request-deletion",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403
    data = response.json()
    assert "owner" in data["detail"].lower()


@pytest.mark.asyncio
async def test_cannot_request_deletion_for_other_organization(
    client: AsyncClient, second_organization, owner_user_with_token
):
    """Test that owner cannot request deletion for a different organization."""
    owner_user, owner_token = owner_user_with_token
    other_org_id = str(second_organization.id)

    response = await client.post(
        f"/api/v1/organizations/{other_org_id}/request-deletion",
        headers={"Authorization": owner_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cannot_request_deletion_twice(
    client: AsyncClient, async_session, test_organization, owner_user_with_token
):
    """Test that deletion cannot be requested if already requested."""
    owner_user, owner_token = owner_user_with_token
    org_id = str(test_organization.id)

    # First request should succeed
    response1 = await client.post(
        f"/api/v1/organizations/{org_id}/request-deletion",
        headers={"Authorization": owner_token},
    )
    assert response1.status_code == 200

    # Second request should fail
    response2 = await client.post(
        f"/api/v1/organizations/{org_id}/request-deletion",
        headers={"Authorization": owner_token},
    )
    assert response2.status_code == 400
    data = response2.json()
    assert "already" in data["detail"].lower()


@pytest.mark.asyncio
async def test_owner_can_cancel_deletion_request(
    client: AsyncClient, async_session, test_organization, owner_user_with_token
):
    """Test that organization owner can cancel a pending deletion request."""
    owner_user, owner_token = owner_user_with_token
    org_id = str(test_organization.id)

    # First request deletion
    await client.post(
        f"/api/v1/organizations/{org_id}/request-deletion",
        headers={"Authorization": owner_token},
    )

    # Then cancel it
    response = await client.delete(
        f"/api/v1/organizations/{org_id}/request-deletion",
        headers={"Authorization": owner_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "cancelled" in data["message"].lower()
    assert data["organization_id"] == org_id


@pytest.mark.asyncio
async def test_super_admin_can_cancel_deletion_request(
    client: AsyncClient,
    async_session,
    test_organization,
    owner_user_with_token,
    test_admin_token,
):
    """Test that super admin can cancel a deletion request for any organization."""
    owner_user, owner_token = owner_user_with_token
    org_id = str(test_organization.id)

    # Owner requests deletion
    await client.post(
        f"/api/v1/organizations/{org_id}/request-deletion",
        headers={"Authorization": owner_token},
    )

    # Super admin cancels it
    response = await client.delete(
        f"/api/v1/organizations/{org_id}/request-deletion",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "cancelled" in data["message"].lower()


@pytest.mark.asyncio
async def test_cannot_cancel_nonexistent_deletion_request(
    client: AsyncClient, test_organization, owner_user_with_token
):
    """Test that canceling fails if no deletion request exists."""
    owner_user, owner_token = owner_user_with_token
    org_id = str(test_organization.id)

    response = await client.delete(
        f"/api/v1/organizations/{org_id}/request-deletion",
        headers={"Authorization": owner_token},
    )

    assert response.status_code == 400
    data = response.json()
    assert "no deletion request" in data["detail"].lower()


@pytest.mark.asyncio
async def test_organization_response_includes_deletion_status(
    client: AsyncClient, async_session, test_organization, owner_user_with_token
):
    """Test that organization GET response includes deletion_requested status."""
    owner_user, owner_token = owner_user_with_token
    org_id = str(test_organization.id)

    # Check initial state - no deletion requested
    response1 = await client.get(
        f"/api/v1/organizations/{org_id}", headers={"Authorization": owner_token}
    )
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["deletion_requested"] is False
    assert data1["deletion_requested_time"] is None

    # Request deletion
    await client.post(
        f"/api/v1/organizations/{org_id}/request-deletion",
        headers={"Authorization": owner_token},
    )

    # Check updated state
    response2 = await client.get(
        f"/api/v1/organizations/{org_id}", headers={"Authorization": owner_token}
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["deletion_requested"] is True
    assert data2["deletion_requested_time"] is not None
