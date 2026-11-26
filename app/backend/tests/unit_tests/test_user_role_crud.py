"""
Unit tests for user role CRUD operations.
Tests the assignment of global roles to users within an organization context.
"""

import uuid as uuid_module

import pytest

from src.crud.role import create_role
from src.crud.user import create_user
from src.crud.user_role import (
    assign_role,
    get_all_user_roles_history,
    get_user_roles,
    revoke_role,
    user_has_role,
)


@pytest.mark.asyncio
async def test_assign_role(async_session, test_organization):
    """Test assigning a global role to a user."""
    org_id = str(test_organization.id)

    # Create user and global role
    user = await create_user(
        async_session, {"email": "test@test.com", "password": "Password123!"}, org_id
    )
    role = await create_role(
        async_session,
        {"name": f"test_role_{uuid_module.uuid4().hex[:8]}", "description": "Test"},
    )
    admin_user = await create_user(
        async_session, {"email": "admin@test.com", "password": "Password123!"}, org_id
    )

    # Assign role
    user_role = await assign_role(
        async_session,
        {"user_id": str(user.id), "role_id": str(role.id)},
        str(admin_user.id),
        org_id,
    )

    assert user_role.user_id == user.id
    assert user_role.role_id == role.id
    assert user_role.assigned_by == admin_user.id
    assert user_role.deleted_time is None


@pytest.mark.asyncio
async def test_assign_duplicate_role(async_session, test_organization):
    """Test assigning a duplicate role raises error."""
    org_id = str(test_organization.id)

    user = await create_user(
        async_session, {"email": "test@test.com", "password": "Password123!"}, org_id
    )
    role = await create_role(
        async_session,
        {"name": f"test_role_{uuid_module.uuid4().hex[:8]}", "description": "Test"},
    )
    admin_user = await create_user(
        async_session, {"email": "admin@test.com", "password": "Password123!"}, org_id
    )

    await assign_role(
        async_session,
        {"user_id": str(user.id), "role_id": str(role.id)},
        str(admin_user.id),
        org_id,
    )

    with pytest.raises(ValueError, match="already has role"):
        await assign_role(
            async_session,
            {"user_id": str(user.id), "role_id": str(role.id)},
            str(admin_user.id),
            org_id,
        )


@pytest.mark.asyncio
async def test_revoke_role(async_session, test_organization):
    """Test revoking a role from a user."""
    org_id = str(test_organization.id)

    user = await create_user(
        async_session, {"email": "test@test.com", "password": "Password123!"}, org_id
    )
    role = await create_role(
        async_session,
        {"name": f"test_role_{uuid_module.uuid4().hex[:8]}", "description": "Test"},
    )
    admin_user = await create_user(
        async_session, {"email": "admin@test.com", "password": "Password123!"}, org_id
    )

    # Assign role first
    await assign_role(
        async_session,
        {"user_id": str(user.id), "role_id": str(role.id)},
        str(admin_user.id),
        org_id,
    )

    # Revoke role
    user_role = await revoke_role(
        async_session,
        {"user_id": str(user.id), "role_id": str(role.id)},
        org_id,
    )

    assert user_role.deleted_time is not None


@pytest.mark.asyncio
async def test_get_user_roles(async_session, test_organization):
    """Test getting a user's roles."""
    org_id = str(test_organization.id)

    user = await create_user(
        async_session, {"email": "test@test.com", "password": "Password123!"}, org_id
    )
    role1 = await create_role(
        async_session,
        {"name": f"role1_{uuid_module.uuid4().hex[:8]}", "description": "Role 1"},
    )
    role2 = await create_role(
        async_session,
        {"name": f"role2_{uuid_module.uuid4().hex[:8]}", "description": "Role 2"},
    )
    admin_user = await create_user(
        async_session, {"email": "admin@test.com", "password": "Password123!"}, org_id
    )

    await assign_role(
        async_session,
        {"user_id": str(user.id), "role_id": str(role1.id)},
        str(admin_user.id),
        org_id,
    )
    await assign_role(
        async_session,
        {"user_id": str(user.id), "role_id": str(role2.id)},
        str(admin_user.id),
        org_id,
    )

    user_roles, total = await get_user_roles(async_session, str(user.id), org_id)

    assert total == 2
    assert len(user_roles) == 2


@pytest.mark.asyncio
async def test_user_has_role(async_session, test_organization):
    """Test checking if a user has a role."""
    org_id = str(test_organization.id)
    role_name = f"test_role_{uuid_module.uuid4().hex[:8]}"

    user = await create_user(
        async_session, {"email": "test@test.com", "password": "Password123!"}, org_id
    )
    role = await create_role(async_session, {"name": role_name, "description": "Test"})
    admin_user = await create_user(
        async_session, {"email": "admin@test.com", "password": "Password123!"}, org_id
    )

    # Before assignment
    has_role = await user_has_role(async_session, str(user.id), role_name, org_id)
    assert not has_role

    # After assignment
    await assign_role(
        async_session,
        {"user_id": str(user.id), "role_id": str(role.id)},
        str(admin_user.id),
        org_id,
    )
    has_role = await user_has_role(async_session, str(user.id), role_name, org_id)
    assert has_role

    # After revocation
    await revoke_role(
        async_session,
        {"user_id": str(user.id), "role_id": str(role.id)},
        org_id,
    )
    has_role = await user_has_role(async_session, str(user.id), role_name, org_id)
    assert not has_role


@pytest.mark.asyncio
async def test_get_role_history(async_session, test_organization):
    """Test getting a user's role assignment history."""
    org_id = str(test_organization.id)

    user = await create_user(
        async_session, {"email": "test@test.com", "password": "Password123!"}, org_id
    )
    role = await create_role(
        async_session,
        {"name": f"test_role_{uuid_module.uuid4().hex[:8]}", "description": "Test"},
    )
    admin_user = await create_user(
        async_session, {"email": "admin@test.com", "password": "Password123!"}, org_id
    )

    # Assign and revoke role
    await assign_role(
        async_session,
        {"user_id": str(user.id), "role_id": str(role.id)},
        str(admin_user.id),
        org_id,
    )
    await revoke_role(
        async_session,
        {"user_id": str(user.id), "role_id": str(role.id)},
        org_id,
    )

    # Get history
    history = await get_all_user_roles_history(async_session, str(user.id), org_id)

    assert len(history) >= 1
