"""
Unit tests for role_permission CRUD operations.
Tests the many-to-many relationship between global roles and global permissions.
"""

from unittest.mock import AsyncMock, patch
import uuid as uuid_module

import pytest

from src.crud.permission import create_permission
from src.crud.role import create_role
from src.crud.role_permission import (
    get_permission_matrix,
    get_role_permissions,
    get_user_permissions,
    grant_permission_to_role,
    revoke_permission_from_role,
    user_has_permission,
)
from src.models.user_role import UserRole


@pytest.mark.asyncio
async def test_grant_permission_to_role(async_session, test_user):
    """Test granting a permission to a global role."""
    # Create role and permission
    role = await create_role(
        async_session,
        {"name": f"test_role_{uuid_module.uuid4().hex[:8]}", "description": "Test"},
    )
    permission = await create_permission(
        async_session, code="users:read", name="Read Users"
    )

    # Mock cache service to prevent cache operations
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        role_permission = await grant_permission_to_role(
            async_session, str(role.id), str(permission.id), str(test_user.id)
        )

    assert role_permission.role_id == role.id
    assert role_permission.permission_id == permission.id
    assert role_permission.granted_by == test_user.id
    assert role_permission.deleted_time is None


@pytest.mark.asyncio
async def test_grant_permission_to_role_duplicate(async_session, test_user):
    """Test that granting duplicate permission raises error."""
    role = await create_role(
        async_session,
        {"name": f"test_role_{uuid_module.uuid4().hex[:8]}", "description": "Test"},
    )
    permission = await create_permission(
        async_session, code="users:read_dup", name="Read Users"
    )

    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        await grant_permission_to_role(
            async_session, str(role.id), str(permission.id), str(test_user.id)
        )

        with pytest.raises(ValueError, match="already granted"):
            await grant_permission_to_role(
                async_session, str(role.id), str(permission.id), str(test_user.id)
            )


@pytest.mark.asyncio
async def test_grant_permission_role_not_found(async_session, test_user):
    """Test granting permission to non-existent role raises error."""
    permission = await create_permission(
        async_session, code="users:read_notfound", name="Read Users"
    )

    with pytest.raises(ValueError, match="Role with id .* not found"):
        await grant_permission_to_role(
            async_session,
            str(uuid_module.uuid4()),
            str(permission.id),
            str(test_user.id),
        )


@pytest.mark.asyncio
async def test_grant_permission_permission_not_found(async_session, test_user):
    """Test granting non-existent permission raises error."""
    role = await create_role(
        async_session,
        {"name": f"test_role_{uuid_module.uuid4().hex[:8]}", "description": "Test"},
    )

    with pytest.raises(ValueError, match="Permission with id .* not found"):
        await grant_permission_to_role(
            async_session, str(role.id), str(uuid_module.uuid4()), str(test_user.id)
        )


@pytest.mark.asyncio
async def test_revoke_permission_from_role(async_session, test_user):
    """Test revoking a permission from a global role."""
    role = await create_role(
        async_session,
        {"name": f"test_role_{uuid_module.uuid4().hex[:8]}", "description": "Test"},
    )
    permission = await create_permission(
        async_session, code="users:read_revoke", name="Read Users"
    )

    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        # First grant
        await grant_permission_to_role(
            async_session, str(role.id), str(permission.id), str(test_user.id)
        )

        # Then revoke
        revoked = await revoke_permission_from_role(
            async_session, str(role.id), str(permission.id)
        )

    assert revoked.deleted_time is not None


@pytest.mark.asyncio
async def test_revoke_permission_not_granted(async_session, test_user):
    """Test revoking a permission that was never granted raises error."""
    role = await create_role(
        async_session,
        {"name": f"test_role_{uuid_module.uuid4().hex[:8]}", "description": "Test"},
    )
    permission = await create_permission(
        async_session, code="users:read_notgranted", name="Read Users"
    )

    with pytest.raises(ValueError, match="Permission grant not found"):
        await revoke_permission_from_role(
            async_session, str(role.id), str(permission.id)
        )


@pytest.mark.asyncio
async def test_get_role_permissions(async_session, test_user):
    """Test getting all permissions for a global role."""
    role = await create_role(
        async_session,
        {"name": f"test_role_{uuid_module.uuid4().hex[:8]}", "description": "Test"},
    )
    perm1 = await create_permission(
        async_session, code="users:read_getrp", name="Read Users"
    )
    perm2 = await create_permission(
        async_session, code="users:write_getrp", name="Write Users"
    )

    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        await grant_permission_to_role(
            async_session, str(role.id), str(perm1.id), str(test_user.id)
        )
        await grant_permission_to_role(
            async_session, str(role.id), str(perm2.id), str(test_user.id)
        )

    permissions = await get_role_permissions(async_session, str(role.id))

    assert len(permissions) == 2
    codes = [p.code for p in permissions]
    assert "users:read_getrp" in codes
    assert "users:write_getrp" in codes


@pytest.mark.asyncio
async def test_get_user_permissions(async_session, test_organization, test_user):
    """Test getting all permissions for a user through their roles."""
    role = await create_role(
        async_session,
        {"name": f"test_role_{uuid_module.uuid4().hex[:8]}", "description": "Test"},
    )
    perm1 = await create_permission(
        async_session, code="users:read_getup", name="Read Users"
    )
    perm2 = await create_permission(
        async_session, code="roles:read_getup", name="Read Roles"
    )

    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=None)  # Cache miss
        mock_cache.set_user_permissions = AsyncMock()
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        # Grant permissions to role
        await grant_permission_to_role(
            async_session, str(role.id), str(perm1.id), str(test_user.id)
        )
        await grant_permission_to_role(
            async_session, str(role.id), str(perm2.id), str(test_user.id)
        )

        # Assign role to user
        user_role = UserRole(
            user_id=test_user.id, role_id=role.id, organization_id=test_organization.id
        )
        async_session.add(user_role)
        await async_session.commit()

        # Get user permissions
        permissions = await get_user_permissions(
            async_session, str(test_user.id), str(test_organization.id)
        )

    assert len(permissions) == 2
    assert "users:read_getup" in permissions
    assert "roles:read_getup" in permissions


@pytest.mark.asyncio
async def test_get_user_permissions_cached(async_session, test_organization, test_user):
    """Test that cached permissions are returned without DB query."""
    cached_perms = ["users:read", "roles:read"]

    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=cached_perms)

        permissions = await get_user_permissions(
            async_session, str(test_user.id), str(test_organization.id)
        )

    assert permissions == cached_perms
    mock_cache.get_user_permissions.assert_called_once()


@pytest.mark.asyncio
async def test_get_user_permissions_multiple_roles(
    async_session, test_organization, test_user
):
    """Test user permissions aggregated from multiple roles."""
    role1 = await create_role(
        async_session,
        {"name": f"role1_{uuid_module.uuid4().hex[:8]}", "description": "Role 1"},
    )
    role2 = await create_role(
        async_session,
        {"name": f"role2_{uuid_module.uuid4().hex[:8]}", "description": "Role 2"},
    )
    perm1 = await create_permission(
        async_session, code="users:read_multi", name="Read Users"
    )
    perm2 = await create_permission(
        async_session, code="roles:read_multi", name="Read Roles"
    )
    perm3 = await create_permission(
        async_session, code="audit_logs:read_multi", name="Read Audit Logs"
    )

    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=None)
        mock_cache.set_user_permissions = AsyncMock()
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        # Grant different permissions to each role
        await grant_permission_to_role(
            async_session, str(role1.id), str(perm1.id), str(test_user.id)
        )
        await grant_permission_to_role(
            async_session, str(role1.id), str(perm2.id), str(test_user.id)
        )
        await grant_permission_to_role(
            async_session, str(role2.id), str(perm2.id), str(test_user.id)
        )
        await grant_permission_to_role(
            async_session, str(role2.id), str(perm3.id), str(test_user.id)
        )

        # Assign both roles to user
        user_role1 = UserRole(
            user_id=test_user.id, role_id=role1.id, organization_id=test_organization.id
        )
        user_role2 = UserRole(
            user_id=test_user.id, role_id=role2.id, organization_id=test_organization.id
        )
        async_session.add(user_role1)
        async_session.add(user_role2)
        await async_session.commit()

        permissions = await get_user_permissions(
            async_session, str(test_user.id), str(test_organization.id)
        )

    # Should have 3 unique permissions (not 4, since roles:read is in both)
    assert len(permissions) == 3
    assert "users:read_multi" in permissions
    assert "roles:read_multi" in permissions
    assert "audit_logs:read_multi" in permissions


@pytest.mark.asyncio
async def test_user_has_permission_true(async_session, test_organization, test_user):
    """Test user_has_permission returns True when user has the permission."""
    role = await create_role(
        async_session,
        {"name": f"test_role_{uuid_module.uuid4().hex[:8]}", "description": "Test"},
    )
    perm = await create_permission(
        async_session, code="users:read_hasperm", name="Read Users"
    )

    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=None)
        mock_cache.set_user_permissions = AsyncMock()
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        await grant_permission_to_role(
            async_session, str(role.id), str(perm.id), str(test_user.id)
        )

        user_role = UserRole(
            user_id=test_user.id, role_id=role.id, organization_id=test_organization.id
        )
        async_session.add(user_role)
        await async_session.commit()

        has_perm = await user_has_permission(
            async_session,
            str(test_user.id),
            str(test_organization.id),
            "users:read_hasperm",
        )

    assert has_perm is True


@pytest.mark.asyncio
async def test_user_has_permission_false(async_session, test_organization, test_user):
    """Test user_has_permission returns False when user lacks the permission."""
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=None)
        mock_cache.set_user_permissions = AsyncMock()

        has_perm = await user_has_permission(
            async_session,
            str(test_user.id),
            str(test_organization.id),
            "users:read_noperm",
        )

    assert has_perm is False


@pytest.mark.asyncio
async def test_get_permission_matrix(async_session, test_user):
    """Test getting the global permission matrix."""
    # Create global roles
    role1 = await create_role(
        async_session,
        {"name": f"admin_{uuid_module.uuid4().hex[:8]}", "description": "Admin"},
    )
    role2 = await create_role(
        async_session,
        {"name": f"member_{uuid_module.uuid4().hex[:8]}", "description": "Member"},
    )

    # Create permissions
    perm1 = await create_permission(
        async_session, code="users:read_matrix", name="Read Users"
    )
    perm2 = await create_permission(
        async_session, code="users:write_matrix", name="Write Users"
    )

    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        # Grant permissions
        await grant_permission_to_role(
            async_session, str(role1.id), str(perm1.id), str(test_user.id)
        )
        await grant_permission_to_role(
            async_session, str(role1.id), str(perm2.id), str(test_user.id)
        )
        await grant_permission_to_role(
            async_session, str(role2.id), str(perm1.id), str(test_user.id)
        )

    matrix = await get_permission_matrix(async_session)

    assert "permissions" in matrix
    assert "roles" in matrix
    assert len(matrix["permissions"]) >= 2
    assert len(matrix["roles"]) >= 2


@pytest.mark.asyncio
async def test_user_permissions_isolation_between_orgs(
    async_session, test_organization, second_organization, test_user, second_org_user
):
    """Test that user permissions are isolated based on org context even with global roles."""
    # Create a global role
    role = await create_role(
        async_session,
        {
            "name": f"shared_role_{uuid_module.uuid4().hex[:8]}",
            "description": "Shared Role",
        },
    )

    # Create global permission
    perm = await create_permission(
        async_session, code="users:read_iso", name="Read Users"
    )

    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=None)
        mock_cache.set_user_permissions = AsyncMock()
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        # Grant permission to the global role
        await grant_permission_to_role(
            async_session, str(role.id), str(perm.id), str(test_user.id)
        )

        # Assign role to user in org 1 only
        user_role = UserRole(
            user_id=test_user.id, role_id=role.id, organization_id=test_organization.id
        )
        async_session.add(user_role)
        await async_session.commit()

        # User in org 1 should have permission
        perms_org1 = await get_user_permissions(
            async_session, str(test_user.id), str(test_organization.id)
        )
        assert "users:read_iso" in perms_org1

        # User in org 2 should NOT have permission (role not assigned in org 2 context)
        perms_org2 = await get_user_permissions(
            async_session, str(second_org_user.id), str(second_organization.id)
        )
        assert "users:read_iso" not in perms_org2
