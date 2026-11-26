"""
Unit tests for user_type_permission CRUD operations.
Tests the many-to-many relationship between global user types and global permissions.
"""

from unittest.mock import AsyncMock, patch
import uuid as uuid_module

import pytest

from src.crud.permission import create_permission
from src.crud.role import create_role
from src.crud.role_permission import get_user_permissions
from src.crud.user_type import create as create_user_type
from src.crud.user_type_permission import (
    get_extended_permission_matrix,
    get_permissions_by_user_types,
    get_user_type_permissions,
    grant_permission_to_user_type,
    revoke_permission_from_user_type,
)
from src.crud.user_user_type import create as create_user_user_type
from src.models.user_role import UserRole


@pytest.mark.asyncio
async def test_grant_permission_to_user_type(async_session, test_user):
    """Test granting a permission to a global user type."""
    # Create user type and permission
    user_type = await create_user_type(
        async_session,
        {
            "name": f"TestType_{uuid_module.uuid4().hex[:8]}",
            "code": f"test_type_{uuid_module.uuid4().hex[:8]}",
            "description": "Test user type",
        },
    )
    permission = await create_permission(
        async_session, code="reports:export_ut", name="Export Reports"
    )

    # Mock cache service to prevent cache operations
    with patch("src.crud.user_type_permission.cache_service") as mock_cache:
        mock_cache.invalidate_user_permissions = AsyncMock()

        user_type_permission = await grant_permission_to_user_type(
            async_session, str(user_type.id), str(permission.id), str(test_user.id)
        )

    assert user_type_permission.user_type_id == user_type.id
    assert user_type_permission.permission_id == permission.id
    assert user_type_permission.granted_by == test_user.id
    assert user_type_permission.deleted_time is None


@pytest.mark.asyncio
async def test_grant_permission_to_user_type_duplicate(async_session, test_user):
    """Test that granting duplicate permission raises error."""
    user_type = await create_user_type(
        async_session,
        {
            "name": f"TestType_{uuid_module.uuid4().hex[:8]}",
            "code": f"test_type_{uuid_module.uuid4().hex[:8]}",
            "description": "Test user type",
        },
    )
    permission = await create_permission(
        async_session, code="reports:export_dup", name="Export Reports"
    )

    with patch("src.crud.user_type_permission.cache_service") as mock_cache:
        mock_cache.invalidate_user_permissions = AsyncMock()

        await grant_permission_to_user_type(
            async_session, str(user_type.id), str(permission.id), str(test_user.id)
        )

        with pytest.raises(ValueError, match="already granted"):
            await grant_permission_to_user_type(
                async_session, str(user_type.id), str(permission.id), str(test_user.id)
            )


@pytest.mark.asyncio
async def test_grant_permission_user_type_not_found(async_session, test_user):
    """Test granting permission to non-existent user type raises error."""
    permission = await create_permission(
        async_session, code="reports:export_notfound", name="Export Reports"
    )

    with pytest.raises(ValueError, match="User type with id .* not found"):
        await grant_permission_to_user_type(
            async_session,
            str(uuid_module.uuid4()),
            str(permission.id),
            str(test_user.id),
        )


@pytest.mark.asyncio
async def test_grant_permission_permission_not_found(async_session, test_user):
    """Test granting non-existent permission raises error."""
    user_type = await create_user_type(
        async_session,
        {
            "name": f"TestType_{uuid_module.uuid4().hex[:8]}",
            "code": f"test_type_{uuid_module.uuid4().hex[:8]}",
            "description": "Test user type",
        },
    )

    with pytest.raises(ValueError, match="Permission with id .* not found"):
        await grant_permission_to_user_type(
            async_session,
            str(user_type.id),
            str(uuid_module.uuid4()),
            str(test_user.id),
        )


@pytest.mark.asyncio
async def test_revoke_permission_from_user_type(async_session, test_user):
    """Test revoking a permission from a global user type."""
    user_type = await create_user_type(
        async_session,
        {
            "name": f"TestType_{uuid_module.uuid4().hex[:8]}",
            "code": f"test_type_{uuid_module.uuid4().hex[:8]}",
            "description": "Test user type",
        },
    )
    permission = await create_permission(
        async_session, code="reports:export_revoke", name="Export Reports"
    )

    with patch("src.crud.user_type_permission.cache_service") as mock_cache:
        mock_cache.invalidate_user_permissions = AsyncMock()

        # First grant
        await grant_permission_to_user_type(
            async_session, str(user_type.id), str(permission.id), str(test_user.id)
        )

        # Then revoke
        revoked = await revoke_permission_from_user_type(
            async_session, str(user_type.id), str(permission.id)
        )

    assert revoked.deleted_time is not None


@pytest.mark.asyncio
async def test_revoke_permission_not_granted(async_session, test_user):
    """Test revoking a permission that was never granted raises error."""
    user_type = await create_user_type(
        async_session,
        {
            "name": f"TestType_{uuid_module.uuid4().hex[:8]}",
            "code": f"test_type_{uuid_module.uuid4().hex[:8]}",
            "description": "Test user type",
        },
    )
    permission = await create_permission(
        async_session, code="reports:export_notgranted", name="Export Reports"
    )

    with pytest.raises(ValueError, match="Permission grant not found"):
        await revoke_permission_from_user_type(
            async_session, str(user_type.id), str(permission.id)
        )


@pytest.mark.asyncio
async def test_get_user_type_permissions(async_session, test_user):
    """Test getting all permissions for a global user type."""
    user_type = await create_user_type(
        async_session,
        {
            "name": f"TestType_{uuid_module.uuid4().hex[:8]}",
            "code": f"test_type_{uuid_module.uuid4().hex[:8]}",
            "description": "Test user type",
        },
    )
    perm1 = await create_permission(
        async_session, code="reports:read_getutperm", name="Read Reports"
    )
    perm2 = await create_permission(
        async_session, code="reports:export_getutperm", name="Export Reports"
    )

    with patch("src.crud.user_type_permission.cache_service") as mock_cache:
        mock_cache.invalidate_user_permissions = AsyncMock()

        await grant_permission_to_user_type(
            async_session, str(user_type.id), str(perm1.id), str(test_user.id)
        )
        await grant_permission_to_user_type(
            async_session, str(user_type.id), str(perm2.id), str(test_user.id)
        )

    permissions = await get_user_type_permissions(async_session, str(user_type.id))

    assert len(permissions) == 2
    codes = [p.code for p in permissions]
    assert "reports:read_getutperm" in codes
    assert "reports:export_getutperm" in codes


@pytest.mark.asyncio
async def test_get_permissions_by_user_types(async_session, test_user):
    """Test getting permissions from multiple user types."""
    user_type1 = await create_user_type(
        async_session,
        {
            "name": f"Business_{uuid_module.uuid4().hex[:8]}",
            "code": f"business_{uuid_module.uuid4().hex[:8]}",
            "description": "Business user type",
        },
    )
    user_type2 = await create_user_type(
        async_session,
        {
            "name": f"Premium_{uuid_module.uuid4().hex[:8]}",
            "code": f"premium_{uuid_module.uuid4().hex[:8]}",
            "description": "Premium user type",
        },
    )
    perm1 = await create_permission(
        async_session, code="reports:read_multi_ut", name="Read Reports"
    )
    perm2 = await create_permission(
        async_session, code="reports:export_multi_ut", name="Export Reports"
    )

    with patch("src.crud.user_type_permission.cache_service") as mock_cache:
        mock_cache.invalidate_user_permissions = AsyncMock()

        await grant_permission_to_user_type(
            async_session, str(user_type1.id), str(perm1.id), str(test_user.id)
        )
        await grant_permission_to_user_type(
            async_session, str(user_type2.id), str(perm2.id), str(test_user.id)
        )

    permission_codes = await get_permissions_by_user_types(
        async_session, [str(user_type1.id), str(user_type2.id)]
    )

    assert len(permission_codes) == 2
    assert "reports:read_multi_ut" in permission_codes
    assert "reports:export_multi_ut" in permission_codes


@pytest.mark.asyncio
async def test_get_user_permissions_includes_user_type_permissions(
    async_session, test_organization, test_user
):
    """Test that get_user_permissions includes permissions from user types."""
    # Create a role and a user type
    role = await create_role(
        async_session,
        {"name": f"test_role_{uuid_module.uuid4().hex[:8]}", "description": "Test"},
    )
    user_type = await create_user_type(
        async_session,
        {
            "name": f"Business_{uuid_module.uuid4().hex[:8]}",
            "code": f"business_{uuid_module.uuid4().hex[:8]}",
            "description": "Business user type",
        },
    )

    # Create permissions - one for role, one for user type
    role_perm = await create_permission(
        async_session, code="users:read_combined", name="Read Users"
    )
    ut_perm = await create_permission(
        async_session, code="reports:export_combined", name="Export Reports"
    )

    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=None)
        mock_cache.set_user_permissions = AsyncMock()
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        with patch("src.crud.user_type_permission.cache_service") as mock_ut_cache:
            mock_ut_cache.invalidate_user_permissions = AsyncMock()

            # Grant permission to role
            from src.crud.role_permission import grant_permission_to_role

            await grant_permission_to_role(
                async_session, str(role.id), str(role_perm.id), str(test_user.id)
            )

            # Grant permission to user type
            await grant_permission_to_user_type(
                async_session, str(user_type.id), str(ut_perm.id), str(test_user.id)
            )

        # Assign role to user
        user_role = UserRole(
            user_id=test_user.id, role_id=role.id, organization_id=test_organization.id
        )
        async_session.add(user_role)
        await async_session.commit()

        with patch("src.crud.user_user_type.cache_service") as mock_uut_cache:
            mock_uut_cache.invalidate_user_permissions = AsyncMock()

            # Assign user type to user
            uut = await create_user_user_type(
                async_session,
                {"user_id": str(test_user.id), "user_type_id": str(user_type.id)},
                str(test_organization.id),
            )

        # Approve the user type assignment so get_user_permissions includes it
        from src.models.user_user_type import OnboardingStatus

        uut.onboarding_status = OnboardingStatus.APPROVED
        await async_session.commit()

        # Get user permissions - should include both role and user type permissions
        permissions = await get_user_permissions(
            async_session, str(test_user.id), str(test_organization.id)
        )

    assert len(permissions) == 2
    assert "users:read_combined" in permissions
    assert "reports:export_combined" in permissions


@pytest.mark.asyncio
async def test_get_user_permissions_deduplication(
    async_session, test_organization, test_user
):
    """Test that duplicate permissions from role and user type are deduplicated."""
    role = await create_role(
        async_session,
        {"name": f"test_role_{uuid_module.uuid4().hex[:8]}", "description": "Test"},
    )
    user_type = await create_user_type(
        async_session,
        {
            "name": f"Business_{uuid_module.uuid4().hex[:8]}",
            "code": f"business_{uuid_module.uuid4().hex[:8]}",
            "description": "Business user type",
        },
    )

    # Create a permission that will be assigned to both role and user type
    shared_perm = await create_permission(
        async_session, code="shared:permission_dedup", name="Shared Permission"
    )

    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=None)
        mock_cache.set_user_permissions = AsyncMock()
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        with patch("src.crud.user_type_permission.cache_service") as mock_ut_cache:
            mock_ut_cache.invalidate_user_permissions = AsyncMock()

            # Grant same permission to both role and user type
            from src.crud.role_permission import grant_permission_to_role

            await grant_permission_to_role(
                async_session, str(role.id), str(shared_perm.id), str(test_user.id)
            )
            await grant_permission_to_user_type(
                async_session, str(user_type.id), str(shared_perm.id), str(test_user.id)
            )

        # Assign role to user
        user_role = UserRole(
            user_id=test_user.id, role_id=role.id, organization_id=test_organization.id
        )
        async_session.add(user_role)
        await async_session.commit()

        with patch("src.crud.user_user_type.cache_service") as mock_uut_cache:
            mock_uut_cache.invalidate_user_permissions = AsyncMock()

            # Assign user type to user
            await create_user_user_type(
                async_session,
                {"user_id": str(test_user.id), "user_type_id": str(user_type.id)},
                str(test_organization.id),
            )

        # Get user permissions - should be deduplicated
        permissions = await get_user_permissions(
            async_session, str(test_user.id), str(test_organization.id)
        )

    # Should only have the permission once, not twice
    assert len(permissions) == 1
    assert "shared:permission_dedup" in permissions


@pytest.mark.asyncio
async def test_get_extended_permission_matrix(async_session, test_user):
    """Test getting the extended permission matrix including user types."""
    # Create global roles
    role = await create_role(
        async_session,
        {"name": f"admin_{uuid_module.uuid4().hex[:8]}", "description": "Admin"},
    )

    # Create user type
    user_type = await create_user_type(
        async_session,
        {
            "name": f"Business_{uuid_module.uuid4().hex[:8]}",
            "code": f"business_{uuid_module.uuid4().hex[:8]}",
            "description": "Business user type",
        },
    )

    # Create permissions
    perm1 = await create_permission(
        async_session, code="users:read_matrix_ext", name="Read Users"
    )
    perm2 = await create_permission(
        async_session, code="reports:export_matrix_ext", name="Export Reports"
    )

    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        from src.crud.role_permission import grant_permission_to_role

        await grant_permission_to_role(
            async_session, str(role.id), str(perm1.id), str(test_user.id)
        )

    with patch("src.crud.user_type_permission.cache_service") as mock_ut_cache:
        mock_ut_cache.invalidate_user_permissions = AsyncMock()

        await grant_permission_to_user_type(
            async_session, str(user_type.id), str(perm2.id), str(test_user.id)
        )

    matrix = await get_extended_permission_matrix(async_session)

    assert "permissions" in matrix
    assert "roles" in matrix
    assert "user_types" in matrix
    assert len(matrix["permissions"]) >= 2
    assert len(matrix["roles"]) >= 1
    assert len(matrix["user_types"]) >= 1

    # Verify user type has the permission
    ut_data = next(
        (ut for ut in matrix["user_types"] if ut["id"] == str(user_type.id)), None
    )
    assert ut_data is not None
    assert str(perm2.id) in ut_data["permission_ids"]


@pytest.mark.asyncio
async def test_cache_invalidation_on_user_type_assignment(
    async_session, test_organization, test_user
):
    """Test that assigning a user type invalidates the user's permission cache."""
    user_type = await create_user_type(
        async_session,
        {
            "name": f"Business_{uuid_module.uuid4().hex[:8]}",
            "code": f"business_{uuid_module.uuid4().hex[:8]}",
            "description": "Business user type",
        },
    )

    with patch("src.crud.user_user_type.cache_service") as mock_cache:
        mock_cache.invalidate_user_permissions = AsyncMock()

        await create_user_user_type(
            async_session,
            {"user_id": str(test_user.id), "user_type_id": str(user_type.id)},
            str(test_organization.id),
        )

        # Verify cache invalidation was called
        mock_cache.invalidate_user_permissions.assert_called_once_with(
            str(test_organization.id), str(test_user.id)
        )
