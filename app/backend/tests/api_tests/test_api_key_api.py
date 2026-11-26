"""
Test cases for API key management endpoints.
Tests CRUD operations, authentication, and tenant isolation.
"""

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
import pytest

from src.models.permission import Permission
from src.models.role import Role
from src.models.role_permission import RolePermission
from src.models.user_role import UserRole


# ============================================================================
# API KEY CRUD TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_api_key(
    client: AsyncClient, test_user, test_jwt_token, async_session, api_keys_feature_flag
):
    """Test creating a new API key."""
    from src.crud.user import get_user_by_id

    # Get the test user
    user = await get_user_by_id(
        async_session, str(test_user.id), str(test_user.organization_id)
    )
    assert user is not None

    # Create permission for the user's role
    perm = Permission(
        code="api_keys:write",
        name="API Keys Write",
        resource="api_keys",
        action="write",
        display_order=0,
    )
    async_session.add(perm)

    # Create role
    role = Role(name="api_key_manager", description="API Key Manager")
    async_session.add(role)
    await async_session.commit()
    await async_session.refresh(perm)
    await async_session.refresh(role)

    # Link permission to role
    role_perm = RolePermission(role_id=role.id, permission_id=perm.id)
    async_session.add(role_perm)

    # Assign role to user
    user_role = UserRole(
        user_id=user.id, role_id=role.id, organization_id=user.organization_id
    )
    async_session.add(user_role)
    await async_session.commit()

    # Create permissions that will be assigned to the API key
    users_read_perm = Permission(
        code="users:read",
        name="Read Users",
        resource="users",
        action="read",
        display_order=0,
    )
    users_write_perm = Permission(
        code="users:write",
        name="Write Users",
        resource="users",
        action="write",
        display_order=0,
    )
    async_session.add(users_read_perm)
    async_session.add(users_write_perm)
    await async_session.commit()
    await async_session.refresh(users_read_perm)
    await async_session.refresh(users_write_perm)

    # Grant these permissions to the user's role (required for permission validation)
    role_perm_read = RolePermission(role_id=role.id, permission_id=users_read_perm.id)
    role_perm_write = RolePermission(role_id=role.id, permission_id=users_write_perm.id)
    async_session.add(role_perm_read)
    async_session.add(role_perm_write)
    await async_session.commit()

    # Create API key
    api_key_data = {
        "name": "Test API Key",
        "permissions": ["users:read", "users:write"],
    }

    response = await client.post(
        "/api/v1/api-keys",
        json=api_key_data,
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert "key" in data  # Full key returned only once
    assert "prefix" in data
    assert "scope" in data
    assert data["scope"] == "user"  # Created through user endpoint
    assert data["name"] == "Test API Key"
    assert len(data["permissions"]) == 2
    assert "message" in data


@pytest.mark.asyncio
async def test_create_api_key_with_expiration(
    client: AsyncClient, test_user, test_jwt_token, async_session, api_keys_feature_flag
):
    """Test creating an API key with expiration date."""
    # Setup permissions for the user's role
    perm = Permission(
        code="api_keys:write",
        name="API Keys Write",
        resource="api_keys",
        action="write",
        display_order=0,
    )
    async_session.add(perm)

    role = Role(name="api_key_manager2", description="API Key Manager 2")
    async_session.add(role)
    await async_session.commit()
    await async_session.refresh(perm)
    await async_session.refresh(role)

    role_perm = RolePermission(role_id=role.id, permission_id=perm.id)
    async_session.add(role_perm)

    user_role = UserRole(
        user_id=test_user.id,
        role_id=role.id,
        organization_id=test_user.organization_id,
    )
    async_session.add(user_role)
    await async_session.commit()

    # Create permission that will be assigned to the API key
    users_read_perm = Permission(
        code="users:read",
        name="Read Users",
        resource="users",
        action="read",
        display_order=0,
    )
    async_session.add(users_read_perm)
    await async_session.commit()
    await async_session.refresh(users_read_perm)

    # Grant this permission to the user's role (required for permission validation)
    role_perm_read = RolePermission(role_id=role.id, permission_id=users_read_perm.id)
    async_session.add(role_perm_read)
    await async_session.commit()

    # Create API key with expiration
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    api_key_data = {
        "name": "Expiring API Key",
        "expires_at": expires_at,
        "permissions": ["users:read"],
    }

    response = await client.post(
        "/api/v1/api-keys",
        json=api_key_data,
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["expires_at"] is not None


@pytest.mark.asyncio
async def test_list_api_keys(
    client: AsyncClient, test_user, test_jwt_token, async_session, api_keys_feature_flag
):
    """Test listing API keys for an organization."""
    from src.crud.api_key import create_api_key

    # Setup permissions
    perm = Permission(
        code="api_keys:read",
        name="API Keys Read",
        resource="api_keys",
        action="read",
        display_order=0,
    )
    async_session.add(perm)

    role = Role(name="api_key_reader", description="API Key Reader")
    async_session.add(role)
    await async_session.commit()
    await async_session.refresh(perm)
    await async_session.refresh(role)

    role_perm = RolePermission(role_id=role.id, permission_id=perm.id)
    async_session.add(role_perm)

    user_role = UserRole(
        user_id=test_user.id,
        role_id=role.id,
        organization_id=test_user.organization_id,
    )
    async_session.add(user_role)
    await async_session.commit()

    # Create a couple of API keys
    await create_api_key(
        async_session,
        "Key 1",
        str(test_user.organization_id),
        str(test_user.id),
    )
    await create_api_key(
        async_session,
        "Key 2",
        str(test_user.organization_id),
        str(test_user.id),
    )

    # List API keys
    response = await client.get(
        "/api/v1/api-keys",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_get_api_key_by_id(
    client: AsyncClient, test_user, test_jwt_token, async_session, api_keys_feature_flag
):
    """Test getting a specific API key by ID."""
    from src.crud.api_key import create_api_key

    # Setup permissions
    perm = Permission(
        code="api_keys:read",
        name="API Keys Read",
        resource="api_keys",
        action="read",
        display_order=0,
    )
    async_session.add(perm)

    role = Role(name="api_key_reader2", description="API Key Reader 2")
    async_session.add(role)
    await async_session.commit()
    await async_session.refresh(perm)
    await async_session.refresh(role)

    role_perm = RolePermission(role_id=role.id, permission_id=perm.id)
    async_session.add(role_perm)

    user_role = UserRole(
        user_id=test_user.id,
        role_id=role.id,
        organization_id=test_user.organization_id,
    )
    async_session.add(user_role)
    await async_session.commit()

    # Create an API key
    api_key, _ = await create_api_key(
        async_session,
        "Test Key",
        str(test_user.organization_id),
        str(test_user.id),
    )

    # Get the API key
    response = await client.get(
        f"/api/v1/api-keys/{api_key.id}",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(api_key.id)
    assert data["name"] == "Test Key"
    assert "key" not in data  # Full key not returned


@pytest.mark.asyncio
async def test_update_api_key(
    client: AsyncClient, test_user, test_jwt_token, async_session, api_keys_feature_flag
):
    """Test updating an API key (name only - expiration cannot be modified after creation)."""
    from src.crud.api_key import create_api_key

    # Setup permissions
    perm = Permission(
        code="api_keys:write",
        name="API Keys Write",
        resource="api_keys",
        action="write",
        display_order=0,
    )
    async_session.add(perm)

    role = Role(name="api_key_updater", description="API Key Updater")
    async_session.add(role)
    await async_session.commit()
    await async_session.refresh(perm)
    await async_session.refresh(role)

    role_perm = RolePermission(role_id=role.id, permission_id=perm.id)
    async_session.add(role_perm)

    user_role = UserRole(
        user_id=test_user.id,
        role_id=role.id,
        organization_id=test_user.organization_id,
    )
    async_session.add(user_role)
    await async_session.commit()

    # Create an API key
    api_key, _ = await create_api_key(
        async_session,
        "Original Name",
        str(test_user.organization_id),
        str(test_user.id),
    )

    # Update the API key
    update_data = {"name": "Updated Name"}

    response = await client.patch(
        f"/api/v1/api-keys/{api_key.id}",
        json=update_data,
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_delete_api_key(
    client: AsyncClient, test_user, test_jwt_token, async_session, api_keys_feature_flag
):
    """Test deleting (revoking) an API key."""
    from src.crud.api_key import create_api_key

    # Setup permissions
    perm = Permission(
        code="api_keys:delete",
        name="API Keys Delete",
        resource="api_keys",
        action="delete",
        display_order=0,
    )
    async_session.add(perm)

    role = Role(name="api_key_deleter", description="API Key Deleter")
    async_session.add(role)
    await async_session.commit()
    await async_session.refresh(perm)
    await async_session.refresh(role)

    role_perm = RolePermission(role_id=role.id, permission_id=perm.id)
    async_session.add(role_perm)

    user_role = UserRole(
        user_id=test_user.id,
        role_id=role.id,
        organization_id=test_user.organization_id,
    )
    async_session.add(user_role)
    await async_session.commit()

    # Create an API key
    api_key, _ = await create_api_key(
        async_session,
        "To Be Deleted",
        str(test_user.organization_id),
        str(test_user.id),
    )

    # Delete the API key
    response = await client.delete(
        f"/api/v1/api-keys/{api_key.id}",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "message" in data


# NOTE: test_assign_permissions_to_api_key was removed because the
# POST /{api_key_id}/permissions endpoint no longer exists.
# Per spec, API key permissions are read-only after creation.


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_api_key_authentication(client: AsyncClient, test_user, async_session):
    """Test authenticating with an API key."""
    from src.crud.api_key import create_api_key

    # Create an API key
    api_key, full_key = await create_api_key(
        async_session,
        "Auth Test Key",
        str(test_user.organization_id),
        str(test_user.id),
    )

    # Validate the key through the dependency
    from src.api.deps import get_current_api_key

    # Mock header extraction
    api_key_context = await get_current_api_key(
        api_key=full_key,
        session=async_session,
    )

    assert api_key_context is not None
    assert api_key_context.api_key_id == str(api_key.id)
    assert api_key_context.organization_id == str(test_user.organization_id)


# ============================================================================
# AUTHORIZATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_api_key_without_permission(
    client: AsyncClient, test_user, test_jwt_token, api_keys_feature_flag
):
    """Test that creating an API key without permission fails."""
    api_key_data = {"name": "Test API Key", "permissions": []}

    response = await client.post(
        "/api/v1/api-keys",
        json=api_key_data,
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_api_keys_without_permission(
    client: AsyncClient, test_jwt_token, api_keys_feature_flag
):
    """Test that listing API keys without permission fails."""
    response = await client.get(
        "/api/v1/api-keys",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403


# ============================================================================
# TENANT ISOLATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_cannot_access_other_org_api_keys(
    client: AsyncClient,
    test_user,
    test_jwt_token,
    second_organization,
    async_session,
    api_keys_feature_flag,
):
    """Test that users cannot access API keys from other organizations."""
    from src.core.security import hash_password
    from src.crud.api_key import create_api_key
    from src.models.user import User

    # Setup permissions for test user
    perm = Permission(
        code="api_keys:read",
        name="API Keys Read",
        resource="api_keys",
        action="read",
        display_order=0,
    )
    async_session.add(perm)

    role = Role(name="api_key_iso_reader", description="API Key ISO Reader")
    async_session.add(role)
    await async_session.commit()
    await async_session.refresh(perm)
    await async_session.refresh(role)

    role_perm = RolePermission(role_id=role.id, permission_id=perm.id)
    async_session.add(role_perm)

    user_role = UserRole(
        user_id=test_user.id,
        role_id=role.id,
        organization_id=test_user.organization_id,
    )
    async_session.add(user_role)
    await async_session.commit()

    # Create user in second organization
    second_user = User(
        email="second@test.com",
        password=hash_password("Password123!"),
        email_verified=True,
        organization_id=second_organization.id,
    )
    async_session.add(second_user)
    await async_session.commit()
    await async_session.refresh(second_user)

    # Create API key in second organization
    api_key, _ = await create_api_key(
        async_session,
        "Other Org Key",
        str(second_organization.id),
        str(second_user.id),
    )

    # Try to access the API key from first organization
    response = await client.get(
        f"/api/v1/api-keys/{api_key.id}",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 404  # Should not be able to access
