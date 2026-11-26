"""
Unit tests for API key rate limit CRUD operations.
Rate limits are global (no organization_id) and define rate limits per permission type.
"""

import pytest

from src.crud.api_key_rate_limit import (
    create_rate_limit,
    delete_rate_limit,
    get_all_rate_limits,
    get_rate_limit_by_permission,
    update_rate_limit,
)


@pytest.mark.asyncio
async def test_create_rate_limit(async_session):
    """Test creating a rate limit."""
    rate_limit = await create_rate_limit(
        async_session,
        permission_code="users:read",
        requests_per_minute=100,
        burst_limit=20,
    )

    assert rate_limit.permission_code == "users:read"
    assert rate_limit.requests_per_minute == 100
    assert rate_limit.burst_limit == 20
    assert rate_limit.deleted_time is None


@pytest.mark.asyncio
async def test_create_rate_limit_invalid_requests_per_minute(async_session):
    """Test creating rate limit with invalid requests_per_minute raises error."""
    with pytest.raises(ValueError, match="requests_per_minute must be greater than 0"):
        await create_rate_limit(
            async_session,
            permission_code="users:read",
            requests_per_minute=0,
            burst_limit=20,
        )

    with pytest.raises(ValueError, match="requests_per_minute must be greater than 0"):
        await create_rate_limit(
            async_session,
            permission_code="users:read",
            requests_per_minute=-10,
            burst_limit=20,
        )


@pytest.mark.asyncio
async def test_create_rate_limit_invalid_burst_limit(async_session):
    """Test creating rate limit with invalid burst_limit raises error."""
    with pytest.raises(ValueError, match="burst_limit must be greater than 0"):
        await create_rate_limit(
            async_session,
            permission_code="users:read",
            requests_per_minute=100,
            burst_limit=0,
        )

    with pytest.raises(ValueError, match="burst_limit must be greater than 0"):
        await create_rate_limit(
            async_session,
            permission_code="users:read",
            requests_per_minute=100,
            burst_limit=-5,
        )


@pytest.mark.asyncio
async def test_create_duplicate_rate_limit(async_session):
    """Test creating a duplicate rate limit raises error."""
    await create_rate_limit(
        async_session,
        permission_code="users:read",
        requests_per_minute=100,
        burst_limit=20,
    )

    with pytest.raises(ValueError, match="already exists"):
        await create_rate_limit(
            async_session,
            permission_code="users:read",
            requests_per_minute=200,
            burst_limit=30,
        )


@pytest.mark.asyncio
async def test_get_rate_limit_by_permission(async_session):
    """Test getting a rate limit by permission code."""
    created = await create_rate_limit(
        async_session,
        permission_code="roles:read",
        requests_per_minute=50,
        burst_limit=10,
    )

    rate_limit = await get_rate_limit_by_permission(async_session, "roles:read")

    assert rate_limit is not None
    assert rate_limit.id == created.id
    assert rate_limit.permission_code == "roles:read"
    assert rate_limit.requests_per_minute == 50
    assert rate_limit.burst_limit == 10


@pytest.mark.asyncio
async def test_get_rate_limit_by_permission_not_found(async_session):
    """Test getting a non-existent rate limit by permission code."""
    rate_limit = await get_rate_limit_by_permission(async_session, "nonexistent:code")

    assert rate_limit is None


@pytest.mark.asyncio
async def test_get_all_rate_limits(async_session):
    """Test listing all rate limits."""
    await create_rate_limit(
        async_session,
        permission_code="users:read",
        requests_per_minute=100,
        burst_limit=20,
    )
    await create_rate_limit(
        async_session,
        permission_code="users:write",
        requests_per_minute=50,
        burst_limit=10,
    )
    await create_rate_limit(
        async_session,
        permission_code="roles:read",
        requests_per_minute=200,
        burst_limit=40,
    )

    rate_limits, total = await get_all_rate_limits(async_session)

    assert total == 3
    assert len(rate_limits) == 3


@pytest.mark.asyncio
async def test_get_all_rate_limits_pagination(async_session):
    """Test pagination of rate limits list."""
    permissions = [
        "alpha:read",
        "beta:read",
        "gamma:read",
        "delta:read",
        "epsilon:read",
    ]
    for perm in permissions:
        await create_rate_limit(
            async_session,
            permission_code=perm,
            requests_per_minute=100,
            burst_limit=20,
        )

    rate_limits, total = await get_all_rate_limits(async_session, limit=2, offset=0)
    assert total == 5
    assert len(rate_limits) == 2

    rate_limits2, total2 = await get_all_rate_limits(async_session, limit=2, offset=2)
    assert total2 == 5
    assert len(rate_limits2) == 2


@pytest.mark.asyncio
async def test_update_rate_limit(async_session):
    """Test updating a rate limit."""
    rate_limit = await create_rate_limit(
        async_session,
        permission_code="users:read",
        requests_per_minute=100,
        burst_limit=20,
    )

    updated = await update_rate_limit(
        async_session,
        str(rate_limit.id),
        requests_per_minute=150,
        burst_limit=30,
    )

    assert updated.requests_per_minute == 150
    assert updated.burst_limit == 30
    # Permission code should remain unchanged
    assert updated.permission_code == "users:read"


@pytest.mark.asyncio
async def test_update_rate_limit_partial(async_session):
    """Test updating only requests_per_minute."""
    rate_limit = await create_rate_limit(
        async_session,
        permission_code="users:read",
        requests_per_minute=100,
        burst_limit=20,
    )

    updated = await update_rate_limit(
        async_session,
        str(rate_limit.id),
        requests_per_minute=200,
    )

    assert updated.requests_per_minute == 200
    assert updated.burst_limit == 20  # Should remain unchanged


@pytest.mark.asyncio
async def test_update_rate_limit_invalid_values(async_session):
    """Test updating with invalid values raises error."""
    rate_limit = await create_rate_limit(
        async_session,
        permission_code="users:read",
        requests_per_minute=100,
        burst_limit=20,
    )

    with pytest.raises(ValueError, match="requests_per_minute must be greater than 0"):
        await update_rate_limit(
            async_session,
            str(rate_limit.id),
            requests_per_minute=0,
        )

    with pytest.raises(ValueError, match="burst_limit must be greater than 0"):
        await update_rate_limit(
            async_session,
            str(rate_limit.id),
            burst_limit=-5,
        )


@pytest.mark.asyncio
async def test_update_rate_limit_not_found(async_session):
    """Test updating a non-existent rate limit raises error."""
    import uuid

    with pytest.raises(ValueError, match="not found"):
        await update_rate_limit(
            async_session, str(uuid.uuid4()), requests_per_minute=100
        )


@pytest.mark.asyncio
async def test_delete_rate_limit(async_session):
    """Test soft deleting a rate limit."""
    rate_limit = await create_rate_limit(
        async_session,
        permission_code="users:read",
        requests_per_minute=100,
        burst_limit=20,
    )

    deleted = await delete_rate_limit(async_session, str(rate_limit.id))

    assert deleted.deleted_time is not None

    # Verify soft delete - should not be found
    found = await get_rate_limit_by_permission(async_session, "users:read")
    assert found is None


@pytest.mark.asyncio
async def test_delete_rate_limit_not_found(async_session):
    """Test deleting a non-existent rate limit raises error."""
    import uuid

    with pytest.raises(ValueError, match="not found"):
        await delete_rate_limit(async_session, str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_rate_limits_ordered_by_permission_code(async_session):
    """Test that rate limits are ordered by permission_code."""
    # Create rate limits in non-alphabetical order
    await create_rate_limit(
        async_session,
        permission_code="users:write",
        requests_per_minute=50,
        burst_limit=10,
    )
    await create_rate_limit(
        async_session,
        permission_code="roles:read",
        requests_per_minute=100,
        burst_limit=20,
    )
    await create_rate_limit(
        async_session,
        permission_code="users:read",
        requests_per_minute=200,
        burst_limit=40,
    )

    rate_limits, _ = await get_all_rate_limits(async_session)

    # Should be ordered by permission_code alphabetically
    codes = [rl.permission_code for rl in rate_limits]
    assert codes == ["roles:read", "users:read", "users:write"]


# ============================================================================
# API Endpoint Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_rate_limit_api(client, test_admin_token):
    """Test creating a rate limit via API."""
    response = await client.post(
        "/api/v1/admin/api-key-rate-limits",
        headers={"Authorization": test_admin_token},
        json={
            "permission_code": "users:read",
            "requests_per_minute": 100,
            "burst_limit": 20,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message_code"] == "rate_limit.created"
    assert data["rate_limit"]["permission_code"] == "users:read"
    assert data["rate_limit"]["requests_per_minute"] == 100
    assert data["rate_limit"]["burst_limit"] == 20


@pytest.mark.asyncio
async def test_create_rate_limit_api_non_admin(client, test_jwt_token):
    """Test that non-admin users cannot create rate limits."""
    response = await client.post(
        "/api/v1/admin/api-key-rate-limits",
        headers={"Authorization": test_jwt_token},
        json={
            "permission_code": "users:read",
            "requests_per_minute": 100,
            "burst_limit": 20,
        },
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_rate_limit_api_invalid_values(client, test_admin_token):
    """Test creating rate limit with invalid values fails."""
    response = await client.post(
        "/api/v1/admin/api-key-rate-limits",
        headers={"Authorization": test_admin_token},
        json={
            "permission_code": "users:read",
            "requests_per_minute": 0,
            "burst_limit": 20,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_rate_limits_api(client, test_admin_token, async_session):
    """Test listing rate limits via API."""
    # Create some rate limits
    await create_rate_limit(
        async_session,
        permission_code="users:read",
        requests_per_minute=100,
        burst_limit=20,
    )
    await create_rate_limit(
        async_session,
        permission_code="users:write",
        requests_per_minute=50,
        burst_limit=10,
    )

    response = await client.get(
        "/api/v1/admin/api-key-rate-limits", headers={"Authorization": test_admin_token}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_list_rate_limits_api_pagination(client, test_admin_token, async_session):
    """Test pagination of rate limits list."""
    # Create multiple rate limits
    for i in range(5):
        await create_rate_limit(
            async_session,
            permission_code=f"perm{i}:read",
            requests_per_minute=100,
            burst_limit=20,
        )

    response = await client.get(
        "/api/v1/admin/api-key-rate-limits?limit=2&offset=0",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_list_rate_limits_api_non_admin(client, test_jwt_token):
    """Test that non-admin users cannot list rate limits."""
    response = await client.get(
        "/api/v1/admin/api-key-rate-limits", headers={"Authorization": test_jwt_token}
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_rate_limit_api(client, test_admin_token, async_session):
    """Test updating a rate limit via API."""
    rate_limit = await create_rate_limit(
        async_session,
        permission_code="users:read",
        requests_per_minute=100,
        burst_limit=20,
    )

    response = await client.patch(
        f"/api/v1/admin/api-key-rate-limits/{rate_limit.id}",
        headers={"Authorization": test_admin_token},
        json={"requests_per_minute": 150, "burst_limit": 30},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message_code"] == "rate_limit.updated"
    assert data["rate_limit"]["requests_per_minute"] == 150
    assert data["rate_limit"]["burst_limit"] == 30


@pytest.mark.asyncio
async def test_update_rate_limit_api_partial(client, test_admin_token, async_session):
    """Test partial update of a rate limit."""
    rate_limit = await create_rate_limit(
        async_session,
        permission_code="users:read",
        requests_per_minute=100,
        burst_limit=20,
    )

    response = await client.patch(
        f"/api/v1/admin/api-key-rate-limits/{rate_limit.id}",
        headers={"Authorization": test_admin_token},
        json={"requests_per_minute": 200},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["rate_limit"]["requests_per_minute"] == 200
    assert data["rate_limit"]["burst_limit"] == 20


@pytest.mark.asyncio
async def test_update_rate_limit_api_non_admin(client, test_jwt_token, async_session):
    """Test that non-admin users cannot update rate limits."""
    rate_limit = await create_rate_limit(
        async_session,
        permission_code="users:read",
        requests_per_minute=100,
        burst_limit=20,
    )

    response = await client.patch(
        f"/api/v1/admin/api-key-rate-limits/{rate_limit.id}",
        headers={"Authorization": test_jwt_token},
        json={"requests_per_minute": 150},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_rate_limit_api_not_found(client, test_admin_token):
    """Test updating a non-existent rate limit."""
    import uuid

    response = await client.patch(
        f"/api/v1/admin/api-key-rate-limits/{uuid.uuid4()}",
        headers={"Authorization": test_admin_token},
        json={"requests_per_minute": 150},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_delete_rate_limit_api(client, test_admin_token, async_session):
    """Test deleting a rate limit via API."""
    rate_limit = await create_rate_limit(
        async_session,
        permission_code="users:read",
        requests_per_minute=100,
        burst_limit=20,
    )

    response = await client.delete(
        f"/api/v1/admin/api-key-rate-limits/{rate_limit.id}",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message_code"] == "rate_limit.deleted"

    # Verify soft delete
    found = await get_rate_limit_by_permission(async_session, "users:read")
    assert found is None


@pytest.mark.asyncio
async def test_delete_rate_limit_api_non_admin(client, test_jwt_token, async_session):
    """Test that non-admin users cannot delete rate limits."""
    rate_limit = await create_rate_limit(
        async_session,
        permission_code="users:read",
        requests_per_minute=100,
        burst_limit=20,
    )

    response = await client.delete(
        f"/api/v1/admin/api-key-rate-limits/{rate_limit.id}",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_rate_limit_api_not_found(client, test_admin_token):
    """Test deleting a non-existent rate limit."""
    import uuid

    response = await client.delete(
        f"/api/v1/admin/api-key-rate-limits/{uuid.uuid4()}",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 400


# ============================================================================
# API Key Permission Validation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_assignable_permissions_super_admin(
    client, test_admin_token, users_read_permission, users_write_permission
):
    """Test that super admins can see all permissions."""
    response = await client.get(
        "/api/v1/api-keys/assignable-permissions",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "permissions" in data
    # Super admin should see all system permissions (at least the ones we created)
    assert len(data["permissions"]) >= 2
    # Permissions are now returned as PermissionResponse objects with code field
    permission_codes = [p["code"] for p in data["permissions"]]
    assert "users:read" in permission_codes
    assert "users:write" in permission_codes


@pytest.mark.asyncio
async def test_get_assignable_permissions_regular_user(
    client,
    async_session,
    test_organization,
    test_role,
    users_read_permission,
    users_write_permission,
):
    """Test that regular users only see their own permissions."""
    from src.core.security import create_access_token
    from src.crud.role_permission import grant_permission_to_role
    from src.crud.user import create_user
    from src.crud.user_role import assign_role
    from src.models.feature_flag import FeatureFlag

    # Enable the api_keys feature flag for the test organization
    api_keys_flag = FeatureFlag(
        key="api_keys",
        name="API Keys",
        description="Enable API key management",
        default_enabled=True,
    )
    async_session.add(api_keys_flag)
    await async_session.commit()

    # Create a user with specific permissions
    user = await create_user(
        async_session,
        {
            "email": "limited@test.com",
            "password": "Test123!",
            "first_name": "Limited",
            "last_name": "User",
            "email_verified": True,
        },
        str(test_organization.id),
    )

    # Assign role to user
    await assign_role(
        async_session,
        {"user_id": str(user.id), "role_id": str(test_role.id)},
        str(user.id),
        str(test_organization.id),
    )

    # Grant specific permissions to the role
    await grant_permission_to_role(
        async_session, str(test_role.id), str(users_read_permission.id), str(user.id)
    )
    await grant_permission_to_role(
        async_session, str(test_role.id), str(users_write_permission.id), str(user.id)
    )

    # Create token for this user
    token = create_access_token(str(user.id), str(test_organization.id))

    response = await client.get(
        "/api/v1/api-keys/assignable-permissions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "permissions" in data
    # User should only see their permissions
    # Permissions are now returned as PermissionResponse objects with code field
    permission_codes = [p["code"] for p in data["permissions"]]
    assert "users:read" in permission_codes
    assert "users:write" in permission_codes


@pytest.mark.asyncio
async def test_create_api_key_with_valid_permissions_super_admin(
    client,
    test_admin_token,
    test_organization,
    async_session,
    users_read_permission,
    users_write_permission,
):
    """Test that super admins can create API keys with any permissions."""
    # Create a roles:read permission for testing
    from src.models.permission import Permission

    roles_read_perm = Permission(
        code="roles:read",
        name="Read Roles",
        description="Read roles permission",
        resource="roles",
        action="read",
        display_order=0,
    )
    async_session.add(roles_read_perm)
    await async_session.commit()

    response = await client.post(
        "/api/v1/api-keys",
        headers={"Authorization": test_admin_token},
        json={
            "name": "Test Key with Permissions",
            "permissions": ["users:read", "users:write", "roles:read"],
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Key with Permissions"
    assert set(data["permissions"]) == {"users:read", "users:write", "roles:read"}


@pytest.mark.asyncio
async def test_create_api_key_with_valid_permissions_regular_user(
    client, async_session, test_organization, test_role, users_read_permission
):
    """Test that regular users can create API keys with their own permissions."""
    from src.core.security import create_access_token
    from src.crud.role_permission import grant_permission_to_role
    from src.crud.user import create_user
    from src.crud.user_role import assign_role
    from src.models.feature_flag import FeatureFlag
    from src.models.permission import Permission

    # Enable the api_keys feature flag for the test organization
    api_keys_flag = FeatureFlag(
        key="api_keys",
        name="API Keys",
        description="Enable API key management",
        default_enabled=True,
    )
    async_session.add(api_keys_flag)
    await async_session.commit()

    # Create api_keys:write permission
    api_keys_write_perm = Permission(
        code="api_keys:write",
        name="Write API Keys",
        description="Create API keys",
        resource="api_keys",
        action="write",
        display_order=0,
    )
    async_session.add(api_keys_write_perm)
    await async_session.commit()
    await async_session.refresh(api_keys_write_perm)

    # Create a user with specific permissions
    user = await create_user(
        async_session,
        {
            "email": "apikey@test.com",
            "password": "Test123!",
            "first_name": "APIKey",
            "last_name": "User",
            "email_verified": True,
        },
        str(test_organization.id),
    )

    # Assign role to user
    await assign_role(
        async_session,
        {"user_id": str(user.id), "role_id": str(test_role.id)},
        str(user.id),
        str(test_organization.id),
    )

    # Grant api_keys:write and users:read permissions
    await grant_permission_to_role(
        async_session, str(test_role.id), str(api_keys_write_perm.id), str(user.id)
    )
    await grant_permission_to_role(
        async_session, str(test_role.id), str(users_read_permission.id), str(user.id)
    )

    # Create token for this user
    token = create_access_token(str(user.id), str(test_organization.id))

    # User should be able to create API key with their own permission
    response = await client.post(
        "/api/v1/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "User API Key",
            "permissions": ["users:read"],
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "User API Key"
    assert data["permissions"] == ["users:read"]


@pytest.mark.asyncio
async def test_create_api_key_with_invalid_permissions_regular_user(
    client, async_session, test_organization, test_role, users_read_permission
):
    """Test that regular users cannot create API keys with permissions they don't have."""
    from src.core.security import create_access_token
    from src.crud.role_permission import grant_permission_to_role
    from src.crud.user import create_user
    from src.crud.user_role import assign_role
    from src.models.feature_flag import FeatureFlag
    from src.models.permission import Permission

    # Enable the api_keys feature flag for the test organization
    api_keys_flag = FeatureFlag(
        key="api_keys",
        name="API Keys",
        description="Enable API key management",
        default_enabled=True,
    )
    async_session.add(api_keys_flag)
    await async_session.commit()

    # Create api_keys:write and roles:write permissions
    api_keys_write_perm = Permission(
        code="api_keys:write",
        name="Write API Keys",
        description="Create API keys",
        resource="api_keys",
        action="write",
        display_order=0,
    )
    roles_write_perm = Permission(
        code="roles:write",
        name="Write Roles",
        description="Write roles permission",
        resource="roles",
        action="write",
        display_order=0,
    )
    async_session.add(api_keys_write_perm)
    async_session.add(roles_write_perm)
    await async_session.commit()
    await async_session.refresh(api_keys_write_perm)
    await async_session.refresh(roles_write_perm)

    # Create a user with limited permissions
    user = await create_user(
        async_session,
        {
            "email": "limited2@test.com",
            "password": "Test123!",
            "first_name": "Limited2",
            "last_name": "User",
            "email_verified": True,
        },
        str(test_organization.id),
    )

    # Assign role to user
    await assign_role(
        async_session,
        {"user_id": str(user.id), "role_id": str(test_role.id)},
        str(user.id),
        str(test_organization.id),
    )

    # Grant only api_keys:write and users:read permissions (NOT roles:write)
    await grant_permission_to_role(
        async_session, str(test_role.id), str(api_keys_write_perm.id), str(user.id)
    )
    await grant_permission_to_role(
        async_session, str(test_role.id), str(users_read_permission.id), str(user.id)
    )

    # Create token for this user
    token = create_access_token(str(user.id), str(test_organization.id))

    # User should NOT be able to create API key with permissions they don't have
    response = await client.post(
        "/api/v1/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Unauthorized API Key",
            "permissions": ["users:read", "roles:write"],  # roles:write not granted
        },
    )

    assert response.status_code == 403
    data = response.json()
    assert "detail_code" in data
    assert data["detail_code"] == "api_key.permission_denied"


@pytest.mark.asyncio
async def test_assign_permissions_endpoint_removed(
    client,
    test_admin_token,
    async_session,
    users_read_permission,
    users_write_permission,
):
    """Test that the assign permissions endpoint has been removed."""
    # First create an API key
    create_response = await client.post(
        "/api/v1/api-keys",
        headers={"Authorization": test_admin_token},
        json={
            "name": "Test Key",
            "permissions": ["users:read"],
        },
    )
    assert create_response.status_code == 201
    api_key_id = create_response.json()["id"]

    # Attempt to assign permissions after creation should fail (404 - endpoint removed)
    response = await client.post(
        f"/api/v1/api-keys/{api_key_id}/permissions",
        headers={"Authorization": test_admin_token},
        json={"permissions": ["users:write"]},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_remove_permissions_endpoint_removed(
    client,
    test_admin_token,
    async_session,
    users_read_permission,
    users_write_permission,
):
    """Test that the remove permissions endpoint has been removed."""
    # First create an API key with permissions
    create_response = await client.post(
        "/api/v1/api-keys",
        headers={"Authorization": test_admin_token},
        json={
            "name": "Test Key 2",
            "permissions": ["users:read", "users:write"],
        },
    )
    assert create_response.status_code == 201
    api_key_id = create_response.json()["id"]

    # Attempt to remove permissions after creation should fail (404 - endpoint removed)
    response = await client.delete(
        f"/api/v1/api-keys/{api_key_id}/permissions",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 404


# ============================================================================
# API Key Rate Limit Enforcement Tests
# ============================================================================


@pytest.mark.asyncio
async def test_api_key_rate_limit_enforcement(async_session):
    """Test that API key rate limiting logic works correctly."""
    from src.crud.api_key_rate_limit import create_rate_limit

    # Create rate limit for test permission (very restrictive for testing)
    await create_rate_limit(
        async_session,
        permission_code="test:read",
        requests_per_minute=2,
        burst_limit=1,
    )

    # Initialize rate limiter
    import uuid

    from src.core.api_key_rate_limit import (
        api_key_rate_limiter,
        enforce_api_key_rate_limit,
    )
    from src.crud.api_key_rate_limit import get_rate_limit_by_permission

    await api_key_rate_limiter.connect()

    # Test API key ID
    api_key_id = str(uuid.uuid4())

    # Load rate limits
    rate_limit = await get_rate_limit_by_permission(async_session, "test:read")
    rate_limits_cache = {
        "test:read": (rate_limit.requests_per_minute, rate_limit.burst_limit)
    }

    # Make requests up to the limit (2 + 1 = 3 total)
    for i in range(3):
        # Should not raise exception
        await enforce_api_key_rate_limit(
            api_key_id=api_key_id,
            api_key_permissions=["test:read"],
            rate_limits_cache=rate_limits_cache,
            is_admin=False,
        )

    # Fourth request should be rate limited
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await enforce_api_key_rate_limit(
            api_key_id=api_key_id,
            api_key_permissions=["test:read"],
            rate_limits_cache=rate_limits_cache,
            is_admin=False,
        )

    assert exc_info.value.status_code == 429
    assert "X-RateLimit-Limit" in exc_info.value.headers

    # Cleanup
    await api_key_rate_limiter.disconnect()


@pytest.mark.asyncio
async def test_api_key_rate_limit_fallback_to_default(async_session):
    """Test that API keys use default rate limits when no specific limit is configured."""
    import uuid

    from src.core.api_key_rate_limit import (
        api_key_rate_limiter,
        enforce_api_key_rate_limit,
    )

    await api_key_rate_limiter.connect()

    # Test API key with permission that has no rate limit configured
    api_key_id = str(uuid.uuid4())
    rate_limits_cache = {}  # Empty cache means default limits will be used

    # Should be able to make many requests with default limits (60 + 10 = 70)
    # We'll just test a few to verify it's not immediately blocked
    for i in range(10):
        # Should not raise exception with default limits
        await enforce_api_key_rate_limit(
            api_key_id=api_key_id,
            api_key_permissions=["unconfigured:permission"],
            rate_limits_cache=rate_limits_cache,
            is_admin=False,
        )

    await api_key_rate_limiter.disconnect()


@pytest.mark.asyncio
async def test_api_key_rate_limit_uses_most_restrictive(async_session):
    """Test that API keys with multiple permissions use the most restrictive rate limit."""
    import uuid

    from fastapi import HTTPException

    from src.core.api_key_rate_limit import (
        api_key_rate_limiter,
        enforce_api_key_rate_limit,
    )
    from src.crud.api_key_rate_limit import (
        create_rate_limit,
        get_rate_limit_by_permission,
    )

    # Create rate limits: fast allows more, slow allows less
    await create_rate_limit(
        async_session,
        permission_code="fast:action",
        requests_per_minute=100,
        burst_limit=20,
    )
    await create_rate_limit(
        async_session,
        permission_code="slow:action",
        requests_per_minute=2,
        burst_limit=1,
    )

    await api_key_rate_limiter.connect()

    # Test API key ID
    api_key_id = str(uuid.uuid4())

    # Load rate limits for both permissions
    fast_limit = await get_rate_limit_by_permission(async_session, "fast:action")
    slow_limit = await get_rate_limit_by_permission(async_session, "slow:action")
    rate_limits_cache = {
        "fast:action": (fast_limit.requests_per_minute, fast_limit.burst_limit),
        "slow:action": (slow_limit.requests_per_minute, slow_limit.burst_limit),
    }

    # Make requests - should be limited by the slow permission (2 + 1 = 3)
    for i in range(3):
        await enforce_api_key_rate_limit(
            api_key_id=api_key_id,
            api_key_permissions=["fast:action", "slow:action"],
            rate_limits_cache=rate_limits_cache,
            is_admin=False,
        )

    # Fourth request should be rate limited
    with pytest.raises(HTTPException) as exc_info:
        await enforce_api_key_rate_limit(
            api_key_id=api_key_id,
            api_key_permissions=["fast:action", "slow:action"],
            rate_limits_cache=rate_limits_cache,
            is_admin=False,
        )

    assert exc_info.value.status_code == 429

    await api_key_rate_limiter.disconnect()
