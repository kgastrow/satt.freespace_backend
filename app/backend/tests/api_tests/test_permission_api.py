"""
API tests for permission-protected endpoints.
Tests the require_permission() dependency and permission management endpoints.
"""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
import pytest


# ============================================================================
# SUPER ADMIN BYPASS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_super_admin_bypasses_permission_check(
    client: AsyncClient, test_admin_user, test_super_admin_token
):
    """Test that super admin (is_admin=True) bypasses all permission checks."""
    # Super admin should access users endpoint without needing users:read permission
    response = await client.get(
        "/api/v1/users", headers={"Authorization": test_super_admin_token}
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_super_admin_can_access_roles(
    client: AsyncClient, test_admin_user, test_super_admin_token
):
    """Test super admin can access roles endpoint without roles:read permission."""
    response = await client.get(
        "/api/v1/roles", headers={"Authorization": test_super_admin_token}
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_super_admin_can_access_audit_logs(
    client: AsyncClient, test_admin_user, test_super_admin_token
):
    """Test super admin can access audit logs without audit_logs:read permission."""
    response = await client.get(
        "/api/v1/audit-logs", headers={"Authorization": test_super_admin_token}
    )

    assert response.status_code == 200


# ============================================================================
# PERMISSION REQUIRED TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_user_without_permission_denied(
    client: AsyncClient, test_user, test_jwt_token
):
    """Test that user without permission gets 403 Forbidden."""
    # Regular user without any permissions should be denied
    response = await client.get(
        "/api/v1/users", headers={"Authorization": test_jwt_token}
    )

    assert response.status_code == 403
    assert "Permission" in response.json().get("detail", "")


@pytest.mark.asyncio
async def test_user_with_permission_can_access(
    client: AsyncClient, user_with_permission, user_with_permission_token
):
    """Test that user with correct permission can access endpoint."""
    # user_with_permission has users:read permission
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["users:read"])

        response = await client.get(
            "/api/v1/users", headers={"Authorization": user_with_permission_token}
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_user_with_wrong_permission_denied(
    client: AsyncClient, user_with_permission, user_with_permission_token
):
    """Test that user with wrong permission is denied."""
    # User has users:read but not roles:read
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["users:read"])

        response = await client.get(
            "/api/v1/roles", headers={"Authorization": user_with_permission_token}
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_request_denied(client: AsyncClient):
    """Test that unauthenticated requests are denied."""
    response = await client.get("/api/v1/users")

    assert response.status_code in [401, 403]


# ============================================================================
# PERMISSION ADMIN ENDPOINT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_permissions_super_admin(
    client: AsyncClient, test_admin_user, test_super_admin_token
):
    """Test super admin can list permissions."""
    response = await client.get(
        "/api/v1/admin/permissions", headers={"Authorization": test_super_admin_token}
    )

    assert response.status_code == 200
    data = response.json()
    assert "permissions" in data or "items" in data or isinstance(data, list)


@pytest.mark.asyncio
async def test_list_permissions_non_super_admin_denied(
    client: AsyncClient, test_user, test_jwt_token
):
    """Test non-super admin cannot list permissions."""
    response = await client.get(
        "/api/v1/admin/permissions", headers={"Authorization": test_jwt_token}
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_permission_super_admin(
    client: AsyncClient, test_admin_user, test_super_admin_token
):
    """Test super admin can create a permission."""
    permission_data = {
        "code": "test_resource:read",
        "name": "Read Test Resource",
        "description": "Test permission for reading",
    }

    response = await client.post(
        "/api/v1/admin/permissions",
        json=permission_data,
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code in [200, 201]
    data = response.json()
    assert data.get("code") == "test_resource:read"


@pytest.mark.asyncio
async def test_create_permission_invalid_format(
    client: AsyncClient, test_admin_user, test_super_admin_token
):
    """Test creating permission with invalid code format fails."""
    permission_data = {
        "code": "InvalidFormat",  # Invalid - no colon, uppercase
        "name": "Invalid Permission",
    }

    response = await client.post(
        "/api/v1/admin/permissions",
        json=permission_data,
        headers={"Authorization": test_super_admin_token},
    )

    # Should fail validation
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_create_duplicate_permission(
    client: AsyncClient, test_permission, test_admin_user, test_super_admin_token
):
    """Test creating duplicate permission fails."""
    permission_data = {
        "code": "test:read",  # Same as test_permission fixture
        "name": "Duplicate Permission",
    }

    response = await client.post(
        "/api/v1/admin/permissions",
        json=permission_data,
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code in [400, 409]


@pytest.mark.asyncio
async def test_update_permission_super_admin(
    client: AsyncClient, test_permission, test_admin_user, test_super_admin_token
):
    """Test super admin can update a permission."""
    update_data = {
        "name": "Updated Permission Name",
        "description": "Updated description",
    }

    response = await client.put(
        f"/api/v1/admin/permissions/{test_permission.id}",
        json=update_data,
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data.get("name") == "Updated Permission Name"


@pytest.mark.asyncio
async def test_delete_permission_super_admin(
    client: AsyncClient, test_permission, test_admin_user, test_super_admin_token
):
    """Test super admin can delete a permission."""
    response = await client.delete(
        f"/api/v1/admin/permissions/{test_permission.id}",
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code in [200, 204]


# ============================================================================
# PERMISSION MATRIX TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_permission_matrix(
    client: AsyncClient, test_admin_user, test_super_admin_token
):
    """Test super admin can get global permission matrix."""
    response = await client.get(
        "/api/v1/admin/permissions/matrix",
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "permissions" in data
    assert "roles" in data


# ============================================================================
# ROLE PERMISSION ASSIGNMENT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_assign_permission_to_role(
    client: AsyncClient,
    test_role,
    test_permission,
    test_admin_user,
    test_super_admin_token,
):
    """Test super admin can assign permission to global role."""
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        response = await client.post(
            "/api/v1/admin/role-permissions/assign",
            json={
                "role_id": str(test_role.id),
                "permission_id": str(test_permission.id),
            },
            headers={"Authorization": test_super_admin_token},
        )

    assert response.status_code in [200, 201]


@pytest.mark.asyncio
async def test_revoke_permission_from_role(
    client: AsyncClient,
    test_role,
    test_permission,
    test_role_permission,
    test_admin_user,
    test_super_admin_token,
):
    """Test super admin can revoke permission from global role."""
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        response = await client.post(
            "/api/v1/admin/role-permissions/revoke",
            json={
                "role_id": str(test_role.id),
                "permission_id": str(test_permission.id),
            },
            headers={"Authorization": test_super_admin_token},
        )

    assert response.status_code in [200, 204]


# ============================================================================
# SPECIFIC ENDPOINT PERMISSION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_users_read_permission_required(
    client: AsyncClient, user_with_permission, user_with_permission_token
):
    """Test GET /users requires users:read permission."""
    # With permission
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["users:read"])
        response = await client.get(
            "/api/v1/users", headers={"Authorization": user_with_permission_token}
        )
    assert response.status_code == 200

    # Without permission
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=[])
        response = await client.get(
            "/api/v1/users", headers={"Authorization": user_with_permission_token}
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_roles_require_super_admin(
    client: AsyncClient,
    user_with_permission,
    user_with_permission_token,
    test_super_admin_token,
):
    """Test GET /roles requires super admin (is_admin=True)."""
    # Regular user without super admin - should fail
    response = await client.get(
        "/api/v1/roles", headers={"Authorization": user_with_permission_token}
    )
    assert response.status_code == 403

    # Super admin - should succeed
    response = await client.get(
        "/api/v1/roles", headers={"Authorization": test_super_admin_token}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_audit_logs_read_permission_required(
    client: AsyncClient, user_with_permission, user_with_permission_token
):
    """Test GET /audit-logs requires audit_logs:read permission."""
    # With permission
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["audit_logs:read"])
        response = await client.get(
            "/api/v1/audit-logs", headers={"Authorization": user_with_permission_token}
        )
    assert response.status_code == 200

    # Without permission
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["users:read"])
        response = await client.get(
            "/api/v1/audit-logs", headers={"Authorization": user_with_permission_token}
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_metrics_read_permission_required(
    client: AsyncClient, user_with_permission, user_with_permission_token
):
    """Test GET /metrics/summary requires metrics:read permission."""
    # With permission
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["metrics:read"])
        response = await client.get(
            "/api/v1/metrics/summary",
            headers={"Authorization": user_with_permission_token},
        )
    assert response.status_code == 200

    # Without permission
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["users:read"])
        response = await client.get(
            "/api/v1/metrics/summary",
            headers={"Authorization": user_with_permission_token},
        )
    assert response.status_code == 403
