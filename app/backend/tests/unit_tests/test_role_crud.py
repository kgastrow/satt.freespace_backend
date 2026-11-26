"""
Unit tests for global role CRUD operations.
Roles are now system-wide and not scoped to organizations.
"""

import pytest

from src.crud.role import (
    create_role,
    delete_role,
    get_role_by_id,
    get_role_by_name,
    list_roles,
    update_role,
)


@pytest.mark.asyncio
async def test_create_role(async_session):
    """Test creating a global role."""
    role_data = {"name": "test_role", "description": "Test role description"}

    role = await create_role(async_session, role_data)

    assert role.name == "test_role"
    assert role.description == "Test role description"
    assert role.deleted_time is None


@pytest.mark.asyncio
async def test_create_duplicate_role(async_session):
    """Test creating a duplicate global role raises error."""
    role_data = {"name": "test_role_dup", "description": "Test"}

    await create_role(async_session, role_data)

    with pytest.raises(ValueError, match="already exists"):
        await create_role(async_session, role_data)


@pytest.mark.asyncio
async def test_get_role_by_id(async_session):
    """Test getting a global role by ID."""
    role_data = {"name": "test_role_by_id", "description": "Test"}
    created_role = await create_role(async_session, role_data)

    role = await get_role_by_id(async_session, str(created_role.id))

    assert role.id == created_role.id
    assert role.name == "test_role_by_id"


@pytest.mark.asyncio
async def test_get_role_by_name(async_session):
    """Test getting a global role by name."""
    role_data = {"name": "test_role_by_name", "description": "Test"}
    await create_role(async_session, role_data)

    role = await get_role_by_name(async_session, "test_role_by_name")

    assert role.name == "test_role_by_name"


@pytest.mark.asyncio
async def test_list_roles(async_session):
    """Test listing global roles."""
    await create_role(async_session, {"name": "role1_list", "description": "Role 1"})
    await create_role(async_session, {"name": "role2_list", "description": "Role 2"})

    roles, total = await list_roles(async_session)

    assert total >= 2
    assert any(r.name == "role1_list" for r in roles)
    assert any(r.name == "role2_list" for r in roles)


@pytest.mark.asyncio
async def test_update_role(async_session):
    """Test updating a global role."""
    role_data = {"name": "test_role_update", "description": "Original"}
    role = await create_role(async_session, role_data)

    update_data = {"name": "updated_role_name", "description": "Updated"}
    updated_role = await update_role(async_session, str(role.id), update_data)

    assert updated_role.name == "updated_role_name"
    assert updated_role.description == "Updated"


@pytest.mark.asyncio
async def test_delete_role(async_session):
    """Test deleting a global role."""
    role_data = {"name": "test_role_delete", "description": "Test"}
    role = await create_role(async_session, role_data)

    deleted_role = await delete_role(async_session, str(role.id))

    assert deleted_role.deleted_time is not None

    # Verify soft delete
    role_check = await get_role_by_id(async_session, str(role.id))
    assert role_check is None


@pytest.mark.asyncio
async def test_get_role_by_id_not_found(async_session):
    """Test getting a non-existent global role by ID."""
    import uuid

    role = await get_role_by_id(async_session, str(uuid.uuid4()))

    assert role is None


@pytest.mark.asyncio
async def test_global_role_name_uniqueness(async_session):
    """Test that global role names must be unique across the system."""
    # Create a role with a specific name
    await create_role(
        async_session, {"name": "unique_global_role", "description": "First"}
    )

    # Trying to create another role with the same name should fail
    with pytest.raises(ValueError, match="already exists"):
        await create_role(
            async_session, {"name": "unique_global_role", "description": "Second"}
        )
