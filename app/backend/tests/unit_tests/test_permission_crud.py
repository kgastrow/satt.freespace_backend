"""
Unit tests for permission CRUD operations.
Permissions are global (no organization_id) and follow the format 'resource:action'.
"""

import pytest

from src.crud.permission import (
    PERMISSION_CODE_PATTERN,
    create_permission,
    delete_permission,
    get_all_permissions,
    get_distinct_resources,
    get_permission_by_code,
    get_permission_by_id,
    update_permission,
)


@pytest.mark.asyncio
async def test_create_permission(async_session):
    """Test creating a permission."""
    permission = await create_permission(
        async_session,
        code="users:read",
        name="Read Users",
        description="View users in the organization",
    )

    assert permission.code == "users:read"
    assert permission.name == "Read Users"
    assert permission.resource == "users"
    assert permission.action == "read"
    assert permission.deleted_time is None


@pytest.mark.asyncio
async def test_create_permission_with_display_order(async_session):
    """Test creating a permission with custom display order."""
    permission = await create_permission(
        async_session,
        code="users:write",
        name="Write Users",
        description="Create/update users",
        display_order=10,
    )

    assert permission.display_order == 10


@pytest.mark.asyncio
async def test_create_permission_invalid_format(async_session):
    """Test that invalid permission code format raises error."""
    with pytest.raises(ValueError, match="Invalid permission code format"):
        await create_permission(
            async_session, code="invalid_format", name="Invalid"  # Missing colon
        )


@pytest.mark.asyncio
async def test_create_permission_invalid_format_uppercase(async_session):
    """Test that uppercase letters in code raise error."""
    with pytest.raises(ValueError, match="Invalid permission code format"):
        await create_permission(
            async_session, code="Users:Read", name="Invalid"  # Uppercase not allowed
        )


@pytest.mark.asyncio
async def test_create_permission_invalid_format_special_chars(async_session):
    """Test that special characters in code raise error."""
    with pytest.raises(ValueError, match="Invalid permission code format"):
        await create_permission(
            async_session, code="users-mgmt:read", name="Invalid"  # Hyphens not allowed
        )


@pytest.mark.asyncio
async def test_create_duplicate_permission(async_session):
    """Test creating a duplicate permission raises error."""
    await create_permission(async_session, code="users:read", name="Read Users")

    with pytest.raises(ValueError, match="already exists"):
        await create_permission(
            async_session, code="users:read", name="Read Users Again"
        )


@pytest.mark.asyncio
async def test_get_permission_by_code(async_session):
    """Test getting a permission by code."""
    created = await create_permission(
        async_session, code="roles:read", name="Read Roles"
    )

    permission = await get_permission_by_code(async_session, "roles:read")

    assert permission is not None
    assert permission.id == created.id
    assert permission.code == "roles:read"


@pytest.mark.asyncio
async def test_get_permission_by_code_not_found(async_session):
    """Test getting a non-existent permission by code."""
    permission = await get_permission_by_code(async_session, "nonexistent:code")

    assert permission is None


@pytest.mark.asyncio
async def test_get_permission_by_id(async_session):
    """Test getting a permission by ID."""
    created = await create_permission(
        async_session, code="users:delete", name="Delete Users"
    )

    permission = await get_permission_by_id(async_session, str(created.id))

    assert permission is not None
    assert permission.code == "users:delete"


@pytest.mark.asyncio
async def test_get_permission_by_id_not_found(async_session):
    """Test getting a non-existent permission by ID."""
    import uuid

    permission = await get_permission_by_id(async_session, str(uuid.uuid4()))

    assert permission is None


@pytest.mark.asyncio
async def test_get_all_permissions(async_session):
    """Test listing all permissions."""
    await create_permission(async_session, code="users:read", name="Read Users")
    await create_permission(async_session, code="users:write", name="Write Users")
    await create_permission(async_session, code="roles:read", name="Read Roles")

    permissions, total = await get_all_permissions(async_session)

    assert total == 3
    assert len(permissions) == 3


@pytest.mark.asyncio
async def test_get_all_permissions_filter_by_resource(async_session):
    """Test listing permissions filtered by resource."""
    await create_permission(async_session, code="users:read", name="Read Users")
    await create_permission(async_session, code="users:write", name="Write Users")
    await create_permission(async_session, code="roles:read", name="Read Roles")

    permissions, total = await get_all_permissions(async_session, resource="users")

    assert total == 2
    assert all(p.resource == "users" for p in permissions)


@pytest.mark.asyncio
async def test_get_all_permissions_pagination(async_session):
    """Test pagination of permissions list."""
    resources = ["alpha", "beta", "gamma", "delta", "epsilon"]
    for resource in resources:
        await create_permission(
            async_session, code=f"{resource}:read", name=f"Read {resource.title()}"
        )

    permissions, total = await get_all_permissions(async_session, limit=2, offset=0)
    assert total == 5
    assert len(permissions) == 2

    permissions2, total2 = await get_all_permissions(async_session, limit=2, offset=2)
    assert total2 == 5
    assert len(permissions2) == 2


@pytest.mark.asyncio
async def test_update_permission(async_session):
    """Test updating a permission."""
    permission = await create_permission(
        async_session,
        code="users:read",
        name="Read Users",
        description="Original description",
    )

    updated = await update_permission(
        async_session,
        str(permission.id),
        name="Updated Name",
        description="Updated description",
        display_order=5,
    )

    assert updated.name == "Updated Name"
    assert updated.description == "Updated description"
    assert updated.display_order == 5
    # Code should remain unchanged
    assert updated.code == "users:read"


@pytest.mark.asyncio
async def test_update_permission_not_found(async_session):
    """Test updating a non-existent permission raises error."""
    import uuid

    with pytest.raises(ValueError, match="not found"):
        await update_permission(async_session, str(uuid.uuid4()), name="New Name")


@pytest.mark.asyncio
async def test_delete_permission(async_session):
    """Test soft deleting a permission."""
    permission = await create_permission(
        async_session, code="users:read", name="Read Users"
    )

    deleted = await delete_permission(async_session, str(permission.id))

    assert deleted.deleted_time is not None

    # Verify soft delete - should not be found
    found = await get_permission_by_code(async_session, "users:read")
    assert found is None


@pytest.mark.asyncio
async def test_delete_permission_not_found(async_session):
    """Test deleting a non-existent permission raises error."""
    import uuid

    with pytest.raises(ValueError, match="not found"):
        await delete_permission(async_session, str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_get_distinct_resources(async_session):
    """Test getting distinct resource names."""
    await create_permission(async_session, code="users:read", name="Read Users")
    await create_permission(async_session, code="users:write", name="Write Users")
    await create_permission(async_session, code="roles:read", name="Read Roles")
    await create_permission(
        async_session, code="audit_logs:read", name="Read Audit Logs"
    )

    resources = await get_distinct_resources(async_session)

    assert len(resources) == 3
    assert "users" in resources
    assert "roles" in resources
    assert "audit_logs" in resources


@pytest.mark.asyncio
async def test_permission_code_pattern():
    """Test the permission code regex pattern."""
    # Valid patterns
    assert PERMISSION_CODE_PATTERN.match("users:read")
    assert PERMISSION_CODE_PATTERN.match("audit_logs:read")
    assert PERMISSION_CODE_PATTERN.match("user_roles:assign")
    assert PERMISSION_CODE_PATTERN.match("a:b")

    # Invalid patterns
    assert not PERMISSION_CODE_PATTERN.match("Users:read")  # uppercase
    assert not PERMISSION_CODE_PATTERN.match("users-read")  # no colon
    assert not PERMISSION_CODE_PATTERN.match("users:Read")  # uppercase action
    assert not PERMISSION_CODE_PATTERN.match("users:read:extra")  # extra colon
    assert not PERMISSION_CODE_PATTERN.match(":read")  # empty resource
    assert not PERMISSION_CODE_PATTERN.match("users:")  # empty action


@pytest.mark.asyncio
async def test_permissions_ordered_by_resource_and_display_order(async_session):
    """Test that permissions are ordered by resource, display_order, and action."""
    # Create permissions in non-alphabetical order with varying display orders
    await create_permission(
        async_session, code="roles:write", name="Write Roles", display_order=1
    )
    await create_permission(
        async_session, code="users:delete", name="Delete Users", display_order=2
    )
    await create_permission(
        async_session, code="roles:read", name="Read Roles", display_order=0
    )
    await create_permission(
        async_session, code="users:read", name="Read Users", display_order=0
    )

    permissions, _ = await get_all_permissions(async_session)

    # Should be ordered by resource, then display_order, then action
    codes = [p.code for p in permissions]
    # roles:read (roles, 0), roles:write (roles, 1), users:read (users, 0), users:delete (users, 2)
    assert codes[0] == "roles:read"
    assert codes[1] == "roles:write"
    assert codes[2] == "users:read"
    assert codes[3] == "users:delete"
