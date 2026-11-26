"""
Role hierarchy enforcement on the revoke endpoint.

Holding `user_roles:revoke` is not enough: a user may only revoke roles at or
below their own privilege level. Without this an org admin (level 4) could strip
the `owner` role (level 5) from the organization owner while being correctly
blocked from granting it.

Super admins (is_admin=True) bypass the hierarchy check.
"""

from httpx import AsyncClient
import pytest


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def revoke_permission(async_session):
    """Create the user_roles:revoke permission."""
    from src.models.permission import Permission

    permission = Permission(
        code="user_roles:revoke",
        name="Revoke User Roles",
        description="Revoke roles from users",
        resource="user_roles",
        action="revoke",
        display_order=0,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)
    return permission


@pytest.fixture
async def admin_role_can_revoke(
    async_session, admin_role, revoke_permission, test_admin_user
):
    """Grant user_roles:revoke to the admin role (mirrors seeded permissions)."""
    from src.models.role_permission import RolePermission

    role_permission = RolePermission(
        role_id=admin_role.id,
        permission_id=revoke_permission.id,
        granted_by=test_admin_user.id,
    )
    async_session.add(role_permission)
    await async_session.commit()
    return role_permission


@pytest.fixture
async def owner_role_can_revoke(
    async_session, owner_role, revoke_permission, test_admin_user
):
    """Grant user_roles:revoke to the owner role."""
    from src.models.role_permission import RolePermission

    role_permission = RolePermission(
        role_id=owner_role.id,
        permission_id=revoke_permission.id,
        granted_by=test_admin_user.id,
    )
    async_session.add(role_permission)
    await async_session.commit()
    return role_permission


async def _create_user_with_role(async_session, organization, role, email):
    """Create a user in `organization` holding `role`."""
    from src.core.security import hash_password
    from src.models.user import User
    from src.models.user_role import UserRole

    user = User(
        email=email,
        password=hash_password("Password123!"),
        email_verified=True,
        organization_id=organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    user_role = UserRole(
        user_id=user.id,
        role_id=role.id,
        organization_id=organization.id,
    )
    async_session.add(user_role)
    await async_session.commit()
    await async_session.refresh(user_role)

    return user, user_role


def _token(user, organization) -> str:
    from src.core.security import create_access_token

    return f"Bearer {create_access_token(user_id=str(user.id), organization_id=str(organization.id))}"


# ============================================================================
# Hierarchy tests
# ============================================================================


class TestRevokeRoleHierarchy:
    """Revoke must apply the same hierarchy rules as assign."""

    @pytest.mark.asyncio
    async def test_admin_cannot_revoke_owner_role(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        admin_role,
        owner_role,
        admin_role_can_revoke,
    ):
        """An org admin (level 4) cannot revoke owner (level 5)."""
        acting_admin, _ = await _create_user_with_role(
            async_session, test_organization, admin_role, "hierarchy_admin@test.com"
        )
        # Two owners so the "last owner" guard cannot be what blocks the call
        owner_one, owner_one_role = await _create_user_with_role(
            async_session, test_organization, owner_role, "hierarchy_owner1@test.com"
        )
        await _create_user_with_role(
            async_session, test_organization, owner_role, "hierarchy_owner2@test.com"
        )

        response = await client.post(
            "/api/v1/user-roles/revoke",
            json={"user_id": str(owner_one.id), "role_id": str(owner_role.id)},
            headers={"Authorization": _token(acting_admin, test_organization)},
        )

        assert response.status_code == 403
        assert response.json()["detail_code"] == "user_role.hierarchy_violation"

        await async_session.refresh(owner_one_role)
        assert owner_one_role.deleted_time is None

    @pytest.mark.asyncio
    async def test_owner_can_revoke_admin_role(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        admin_role,
        owner_role,
        owner_role_can_revoke,
    ):
        """An owner (level 5) can revoke admin (level 4)."""
        acting_owner, _ = await _create_user_with_role(
            async_session, test_organization, owner_role, "revoking_owner@test.com"
        )
        target_admin, target_admin_role = await _create_user_with_role(
            async_session, test_organization, admin_role, "target_admin@test.com"
        )

        response = await client.post(
            "/api/v1/user-roles/revoke",
            json={"user_id": str(target_admin.id), "role_id": str(admin_role.id)},
            headers={"Authorization": _token(acting_owner, test_organization)},
        )

        assert response.status_code == 200
        assert response.json()["user_role"]["deleted_time"] is not None

        await async_session.refresh(target_admin_role)
        assert target_admin_role.deleted_time is not None

    @pytest.mark.asyncio
    async def test_super_admin_can_revoke_owner_role(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        test_admin_token,
        owner_role,
    ):
        """Super admins bypass the hierarchy check."""
        owner_one, owner_one_role = await _create_user_with_role(
            async_session, test_organization, owner_role, "sa_owner1@test.com"
        )
        await _create_user_with_role(
            async_session, test_organization, owner_role, "sa_owner2@test.com"
        )

        response = await client.post(
            "/api/v1/user-roles/revoke",
            json={"user_id": str(owner_one.id), "role_id": str(owner_role.id)},
            headers={"Authorization": test_admin_token},
        )

        assert response.status_code == 200
        await async_session.refresh(owner_one_role)
        assert owner_one_role.deleted_time is not None


class TestRevokeRoleTenantIsolation:
    """Revoke must never reach a user in another organization."""

    @pytest.mark.asyncio
    async def test_cannot_revoke_role_of_user_in_another_organization(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        second_organization,
        owner_role,
        member_role,
        owner_role_can_revoke,
    ):
        """An owner in org A cannot revoke a role held in org B."""
        acting_owner, _ = await _create_user_with_role(
            async_session, test_organization, owner_role, "iso_owner@test.com"
        )
        foreign_user, foreign_user_role = await _create_user_with_role(
            async_session, second_organization, member_role, "iso_foreign@test.com"
        )

        response = await client.post(
            "/api/v1/user-roles/revoke",
            json={"user_id": str(foreign_user.id), "role_id": str(member_role.id)},
            headers={"Authorization": _token(acting_owner, test_organization)},
        )

        assert response.status_code == 400

        # The other organization's assignment must still be active
        await async_session.refresh(foreign_user_role)
        assert foreign_user_role.deleted_time is None
