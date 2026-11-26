"""
Test cases for global role management API endpoints.
Roles are now system-wide and managed by super admins only.
"""

from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_create_role_super_admin_only(
    client: AsyncClient, test_admin_token, test_jwt_token
):
    """Test that only super admins can create global roles."""
    # Test with regular user - should fail
    response = await client.post(
        "/api/v1/roles",
        json={"name": "test_role_api", "description": "Test"},
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 403

    # Test with super admin - should succeed
    response = await client.post(
        "/api/v1/roles",
        json={"name": "test_role_api", "description": "Test"},
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code in [200, 201]
    data = response.json()
    assert data["role"]["name"] == "test_role_api"


@pytest.mark.asyncio
async def test_list_roles(client: AsyncClient, test_admin_token):
    """Test listing global roles."""
    # Create some roles first
    await client.post(
        "/api/v1/roles",
        json={"name": "role1_api_list", "description": "Role 1"},
        headers={"Authorization": test_admin_token},
    )
    await client.post(
        "/api/v1/roles",
        json={"name": "role2_api_list", "description": "Role 2"},
        headers={"Authorization": test_admin_token},
    )

    # List roles
    response = await client.get(
        "/api/v1/roles", headers={"Authorization": test_admin_token}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_update_role(client: AsyncClient, test_admin_token):
    """Test updating a global role."""
    # Create role
    create_response = await client.post(
        "/api/v1/roles",
        json={"name": "original_role_api", "description": "Original"},
        headers={"Authorization": test_admin_token},
    )
    role_id = create_response.json()["role"]["id"]

    # Update role
    response = await client.put(
        f"/api/v1/roles/{role_id}",
        json={"name": "updated_role_api", "description": "Updated"},
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"]["name"] == "updated_role_api"


@pytest.mark.asyncio
async def test_delete_role(client: AsyncClient, test_admin_token):
    """Test deleting a global role."""
    # Create role
    create_response = await client.post(
        "/api/v1/roles",
        json={"name": "to_delete_api", "description": "Will be deleted"},
        headers={"Authorization": test_admin_token},
    )
    role_id = create_response.json()["role"]["id"]

    # Delete role
    response = await client.delete(
        f"/api/v1/roles/{role_id}", headers={"Authorization": test_admin_token}
    )
    assert response.status_code == 200

    # Verify deletion
    get_response = await client.get(
        f"/api/v1/roles/{role_id}", headers={"Authorization": test_admin_token}
    )
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_get_role_by_id(client: AsyncClient, test_admin_token):
    """Test getting a global role by ID."""
    # Create role
    create_response = await client.post(
        "/api/v1/roles",
        json={"name": "get_role_api", "description": "Get test"},
        headers={"Authorization": test_admin_token},
    )
    role_id = create_response.json()["role"]["id"]

    # Get role
    response = await client.get(
        f"/api/v1/roles/{role_id}", headers={"Authorization": test_admin_token}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == role_id
    assert data["name"] == "get_role_api"


@pytest.mark.asyncio
async def test_create_role_requires_authentication(client: AsyncClient):
    """Test that creating global roles requires authentication."""
    response = await client.post(
        "/api/v1/roles", json={"name": "test_role_noauth", "description": "Test"}
    )
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_global_role_name_uniqueness_api(client: AsyncClient, test_admin_token):
    """Test that global role names must be unique via API."""
    # Create first role
    response1 = await client.post(
        "/api/v1/roles",
        json={"name": "unique_name_api", "description": "First"},
        headers={"Authorization": test_admin_token},
    )
    assert response1.status_code in [200, 201]

    # Try to create second role with same name - should fail
    response2 = await client.post(
        "/api/v1/roles",
        json={"name": "unique_name_api", "description": "Second"},
        headers={"Authorization": test_admin_token},
    )
    assert response2.status_code == 400
    assert "already exists" in response2.json()["detail"]
