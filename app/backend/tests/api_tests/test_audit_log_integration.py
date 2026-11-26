"""
Integration tests verifying audit logs are created by API endpoints.

These tests verify that CRUD operations through API endpoints properly
create audit log entries as documented in ai_docs/backend/context/audit_logging.md.
"""

from uuid import UUID

from httpx import AsyncClient
import pytest
from sqlalchemy import select

from src.models.audit_log import AuditLog


# ============================================================================
# ROLE AUDIT LOGGING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_role_creates_audit_log(
    client: AsyncClient,
    async_session,
    test_admin_token,
    test_organization,
):
    """Test that creating a role creates an audit log entry."""
    # Create role
    response = await client.post(
        "/api/v1/roles",
        json={"name": "audit_test_role", "description": "Testing audit"},
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code in [200, 201]
    role_id = response.json()["role"]["id"]

    # Check audit log was created
    result = await async_session.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "Role",
            AuditLog.resource_id == UUID(role_id),
            AuditLog.action == "CREATE",
        )
    )
    audit_log = result.scalars().first()

    assert audit_log is not None
    assert audit_log.action == "CREATE"
    assert audit_log.resource_type == "Role"
    assert audit_log.changes is not None
    assert "name" in audit_log.changes


@pytest.mark.asyncio
async def test_update_role_creates_audit_log(
    client: AsyncClient,
    async_session,
    test_admin_token,
    test_organization,
):
    """Test that updating a role creates an audit log with changes."""
    # Create role
    create_response = await client.post(
        "/api/v1/roles",
        json={"name": "role_to_update", "description": "Original"},
        headers={"Authorization": test_admin_token},
    )
    role_id = create_response.json()["role"]["id"]

    # Update role
    await client.put(
        f"/api/v1/roles/{role_id}",
        json={"name": "role_updated", "description": "Updated"},
        headers={"Authorization": test_admin_token},
    )

    # Check audit log for UPDATE
    result = await async_session.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "Role",
            AuditLog.resource_id == UUID(role_id),
            AuditLog.action == "UPDATE",
        )
    )
    audit_log = result.scalars().first()

    assert audit_log is not None
    assert audit_log.action == "UPDATE"
    assert audit_log.changes is not None
    # Verify change tracking
    assert "name" in audit_log.changes
    assert audit_log.changes["name"]["old"] == "role_to_update"
    assert audit_log.changes["name"]["new"] == "role_updated"


@pytest.mark.asyncio
async def test_delete_role_creates_audit_log(
    client: AsyncClient,
    async_session,
    test_admin_token,
    test_organization,
):
    """Test that deleting a role creates an audit log entry."""
    # Create role
    create_response = await client.post(
        "/api/v1/roles",
        json={"name": "role_to_delete", "description": "Will be deleted"},
        headers={"Authorization": test_admin_token},
    )
    role_id = create_response.json()["role"]["id"]

    # Delete role
    await client.delete(
        f"/api/v1/roles/{role_id}", headers={"Authorization": test_admin_token}
    )

    # Check audit log for DELETE
    result = await async_session.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "Role",
            AuditLog.resource_id == UUID(role_id),
            AuditLog.action == "DELETE",
        )
    )
    audit_log = result.scalars().first()

    assert audit_log is not None
    assert audit_log.action == "DELETE"
    assert audit_log.changes is not None
    assert "name" in audit_log.changes


# ============================================================================
# USER AUDIT LOGGING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_admin_create_user_creates_audit_log(
    client: AsyncClient,
    async_session,
    test_organization,
    users_write_permission,
    admin_role,
    test_admin_user,
    test_admin_token,
):
    """Test that admin creating a user creates an audit log entry."""
    from src.models.role_permission import RolePermission
    from src.models.user_role import UserRole

    # Grant users:write permission to admin role
    rp = RolePermission(
        role_id=admin_role.id,
        permission_id=users_write_permission.id,
        granted_by=test_admin_user.id,
    )
    async_session.add(rp)

    # Assign admin role to admin user
    ur = UserRole(
        user_id=test_admin_user.id,
        role_id=admin_role.id,
        organization_id=test_organization.id,
    )
    async_session.add(ur)
    await async_session.commit()

    # Create user via API
    response = await client.post(
        "/api/v1/users",
        json={
            "email": "newuser@test.com",
            "password": "SecurePass123!",
            "first_name": "New",
            "last_name": "User",
        },
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code in [200, 201]
    user_id = response.json()["user"]["id"]

    # Check audit log was created
    result = await async_session.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "User",
            AuditLog.resource_id == UUID(user_id),
            AuditLog.action == "CREATE",
        )
    )
    audit_log = result.scalars().first()

    assert audit_log is not None
    assert audit_log.action == "CREATE"
    assert str(audit_log.organization_id) == str(test_organization.id)


# ============================================================================
# USER ROLE (ASSIGNMENT/REVOCATION) AUDIT LOGGING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_assign_role_creates_audit_log(
    client: AsyncClient,
    async_session,
    test_organization,
    test_user,
    test_role,
    test_admin_user,
    test_admin_token,
):
    """Test that assigning a role creates an audit log entry."""
    from src.models.permission import Permission
    from src.models.role import Role
    from src.models.role_permission import RolePermission
    from src.models.user_role import UserRole

    # Create user_roles:assign permission
    permission = Permission(
        code="user_roles:assign",
        name="Assign Roles",
        description="Can assign roles to users",
        resource="user_roles",
        action="assign",
        display_order=0,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)

    # Create a role to grant permission
    perm_role = Role(name="role_assigner", description="Can assign roles")
    async_session.add(perm_role)
    await async_session.commit()
    await async_session.refresh(perm_role)

    # Grant permission to role
    rp = RolePermission(
        role_id=perm_role.id, permission_id=permission.id, granted_by=test_admin_user.id
    )
    async_session.add(rp)

    # Assign role to admin user
    ur = UserRole(
        user_id=test_admin_user.id,
        role_id=perm_role.id,
        organization_id=test_organization.id,
    )
    async_session.add(ur)
    await async_session.commit()

    # Assign role to test user via API
    response = await client.post(
        "/api/v1/user-roles/assign",
        json={
            "user_id": str(test_user.id),
            "role_id": str(test_role.id),
        },
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 200
    user_role_id = response.json()["user_role"]["id"]

    # Check audit log was created
    result = await async_session.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "UserRole",
            AuditLog.resource_id == UUID(user_role_id),
            AuditLog.action == "CREATE",
        )
    )
    audit_log = result.scalars().first()

    assert audit_log is not None
    assert audit_log.action == "CREATE"
    assert audit_log.changes is not None
    assert "role_name" in audit_log.changes


# ============================================================================
# ORGANIZATION AUDIT LOGGING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_organization_creates_audit_log(
    client: AsyncClient,
    async_session,
    test_admin_token,
    test_organization,
):
    """Test that creating an organization creates an audit log entry."""
    response = await client.post(
        "/api/v1/organizations",
        json={"name": "Audit Test Org", "slug": "audit-test-org"},
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code in [200, 201]
    org_id = response.json()["organization"]["id"]

    # Check audit log was created
    result = await async_session.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "Organization",
            AuditLog.resource_id == UUID(org_id),
            AuditLog.action == "CREATE",
        )
    )
    audit_log = result.scalars().first()

    assert audit_log is not None
    assert audit_log.action == "CREATE"
    assert audit_log.changes is not None
    assert "name" in audit_log.changes
    assert "slug" in audit_log.changes


@pytest.mark.asyncio
async def test_update_organization_creates_audit_log(
    client: AsyncClient,
    async_session,
    test_admin_token,
    test_organization,
):
    """Test that updating an organization creates an audit log with changes."""
    # Create organization
    create_response = await client.post(
        "/api/v1/organizations",
        json={"name": "Org To Update", "slug": "org-to-update"},
        headers={"Authorization": test_admin_token},
    )
    org_id = create_response.json()["organization"]["id"]

    # Update organization
    await client.put(
        f"/api/v1/organizations/{org_id}",
        json={"name": "Org Updated"},
        headers={"Authorization": test_admin_token},
    )

    # Check audit log for UPDATE
    result = await async_session.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "Organization",
            AuditLog.resource_id == UUID(org_id),
            AuditLog.action == "UPDATE",
        )
    )
    audit_log = result.scalars().first()

    assert audit_log is not None
    assert audit_log.action == "UPDATE"
    assert audit_log.changes is not None
    assert "name" in audit_log.changes
    assert audit_log.changes["name"]["old"] == "Org To Update"
    assert audit_log.changes["name"]["new"] == "Org Updated"


@pytest.mark.asyncio
async def test_delete_organization_creates_audit_log(
    client: AsyncClient,
    async_session,
    test_admin_token,
    test_organization,
):
    """Test that deleting an organization creates an audit log entry."""
    # Create organization
    create_response = await client.post(
        "/api/v1/organizations",
        json={"name": "Org To Delete", "slug": "org-to-delete"},
        headers={"Authorization": test_admin_token},
    )
    org_id = create_response.json()["organization"]["id"]

    # Delete organization
    await client.delete(
        f"/api/v1/organizations/{org_id}", headers={"Authorization": test_admin_token}
    )

    # Check audit log for DELETE
    result = await async_session.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "Organization",
            AuditLog.resource_id == UUID(org_id),
            AuditLog.action == "DELETE",
        )
    )
    audit_log = result.scalars().first()

    assert audit_log is not None
    assert audit_log.action == "DELETE"
    assert audit_log.changes is not None
    assert "name" in audit_log.changes


# ============================================================================
# AUDIT LOG METADATA TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_audit_log_captures_actor_id(
    client: AsyncClient,
    async_session,
    test_admin_user,
    test_admin_token,
    test_organization,
):
    """Test that audit log captures the actor (user who performed action)."""
    response = await client.post(
        "/api/v1/roles",
        json={"name": "actor_test_role", "description": "Test"},
        headers={"Authorization": test_admin_token},
    )
    role_id = response.json()["role"]["id"]

    result = await async_session.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "Role",
            AuditLog.resource_id == UUID(role_id),
        )
    )
    audit_log = result.scalars().first()

    assert audit_log is not None
    assert str(audit_log.actor_id) == str(test_admin_user.id)


@pytest.mark.asyncio
async def test_audit_log_captures_organization_id(
    client: AsyncClient,
    async_session,
    test_admin_token,
    test_organization,
):
    """Test that audit log captures the organization context."""
    response = await client.post(
        "/api/v1/roles",
        json={"name": "org_test_role", "description": "Test"},
        headers={"Authorization": test_admin_token},
    )
    role_id = response.json()["role"]["id"]

    result = await async_session.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "Role",
            AuditLog.resource_id == UUID(role_id),
        )
    )
    audit_log = result.scalars().first()

    assert audit_log is not None
    assert str(audit_log.organization_id) == str(test_organization.id)


# ============================================================================
# AUDIT LOG API ENDPOINT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_audit_logs_endpoint(
    client: AsyncClient,
    async_session,
    test_admin_token,
    test_organization,
):
    """Test the audit logs list endpoint returns created logs."""
    # Create some audit logs by performing actions
    await client.post(
        "/api/v1/roles",
        json={"name": "list_test_role1", "description": "Test 1"},
        headers={"Authorization": test_admin_token},
    )
    await client.post(
        "/api/v1/roles",
        json={"name": "list_test_role2", "description": "Test 2"},
        headers={"Authorization": test_admin_token},
    )

    # Fetch audit logs
    response = await client.get(
        "/api/v1/audit-logs", headers={"Authorization": test_admin_token}
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_list_audit_logs_filter_by_resource_type(
    client: AsyncClient,
    async_session,
    test_admin_token,
    test_organization,
):
    """Test filtering audit logs by resource type."""
    # Create role (creates Role audit log)
    await client.post(
        "/api/v1/roles",
        json={"name": "filter_test_role", "description": "Test"},
        headers={"Authorization": test_admin_token},
    )

    # Create organization (creates Organization audit log)
    await client.post(
        "/api/v1/organizations",
        json={"name": "Filter Test Org", "slug": "filter-test-org"},
        headers={"Authorization": test_admin_token},
    )

    # Fetch only Role audit logs using DSL filter format
    response = await client.get(
        "/api/v1/audit-logs?filter[resource_type]=Role",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    for log in data["items"]:
        assert log["resource_type"] == "Role"
