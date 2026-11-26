"""
Multitenancy Test Template

This template provides reusable patterns for testing tenant isolation in the
application. All tenant-scoped features MUST include these types of tests to
ensure proper data isolation between organizations.

Key Principles:
1. Users in one organization should NEVER be able to access data from another
2. Cross-tenant access attempts should return 404 (not 403) to avoid revealing
   the existence of data in other tenants
3. Same-tenant access should work correctly when the user has proper permissions
4. Super admins (is_admin=True) can bypass tenant restrictions

Available Fixtures (from tests/conftest.py):
- async_session: Database session for all DB operations
- client: AsyncClient for API tests
- test_organization: Primary test organization (slug: "test-org")
- second_organization: Secondary organization for isolation tests
- test_user: Regular user in test_organization
- second_org_user: User in second_organization
- test_jwt_token: Token for test_user (includes "Bearer " prefix)
- second_org_user_token: Token for user in different org

IMPORTANT: Token fixtures already include "Bearer " prefix - use directly in headers:
    headers={"Authorization": test_jwt_token}  # Correct
    headers={"Authorization": f"Bearer {test_jwt_token}"}  # WRONG - will double prefix
"""

import pytest
from httpx import AsyncClient


# =============================================================================
# TEMPLATE 1: CRUD-Level Tenant Isolation Tests
# =============================================================================
# Use these patterns when testing CRUD functions directly (unit_tests/ or crud_tests/)


class TestResourceTenantIsolationCRUD:
    """
    Template for testing tenant isolation at the CRUD level.

    Replace 'Resource' with your actual entity name (e.g., Project, Document, etc.)
    Replace the CRUD function imports with your actual CRUD module.
    """

    @pytest.mark.asyncio
    async def test_create_resource_assigns_organization(
        self, async_session, test_organization
    ):
        """
        Test that creating a resource correctly assigns the organization_id.

        This ensures the resource is properly scoped to a tenant from creation.
        """
        # Replace with actual CRUD import and function
        # from src.crud.resource import create_resource

        org_id = str(test_organization.id)

        # Create resource with organization context
        # resource = await create_resource(
        #     async_session,
        #     data={"name": "Test Resource", ...},
        #     organization_id=org_id
        # )

        # Verify organization_id is set correctly
        # assert resource.organization_id == test_organization.id
        # assert resource.name == "Test Resource"
        pass  # Remove this and uncomment above when using template

    @pytest.mark.asyncio
    async def test_get_resource_requires_organization_id(
        self, async_session, test_organization, second_organization
    ):
        """
        Test that getting a resource requires the correct organization_id.

        A resource created in one organization should NOT be retrievable
        when queried with a different organization_id.
        """
        # from src.crud.resource import create_resource, get_resource_by_id

        org1_id = str(test_organization.id)
        org2_id = str(second_organization.id)

        # Create resource in org1
        # resource = await create_resource(
        #     async_session,
        #     data={"name": "Org1 Resource"},
        #     organization_id=org1_id
        # )

        # Should be retrievable with correct org_id
        # result = await get_resource_by_id(
        #     async_session, str(resource.id), org1_id
        # )
        # assert result is not None
        # assert result.id == resource.id

        # Should NOT be retrievable with different org_id (cross-tenant access denied)
        # result = await get_resource_by_id(
        #     async_session, str(resource.id), org2_id
        # )
        # assert result is None  # Returns None, not the resource
        pass  # Remove this and uncomment above when using template

    @pytest.mark.asyncio
    async def test_list_resources_returns_only_same_org(
        self, async_session, test_organization, second_organization
    ):
        """
        Test that listing resources only returns items from the specified organization.

        Resources from other organizations should never appear in list results.
        """
        # from src.crud.resource import create_resource, list_resources

        org1_id = str(test_organization.id)
        org2_id = str(second_organization.id)

        # Create resources in org1
        # resource1 = await create_resource(async_session, {"name": "Org1 A"}, org1_id)
        # resource2 = await create_resource(async_session, {"name": "Org1 B"}, org1_id)

        # Create resource in org2
        # resource3 = await create_resource(async_session, {"name": "Org2 A"}, org2_id)

        # List resources for org1 - should only see org1 resources
        # results, total = await list_resources(async_session, org1_id)
        # assert total == 2
        # result_ids = [r.id for r in results]
        # assert resource1.id in result_ids
        # assert resource2.id in result_ids
        # assert resource3.id not in result_ids  # Org2's resource should NOT appear

        # List resources for org2 - should only see org2 resources
        # results, total = await list_resources(async_session, org2_id)
        # assert total == 1
        # assert results[0].id == resource3.id
        pass  # Remove this and uncomment above when using template

    @pytest.mark.asyncio
    async def test_update_resource_requires_same_org(
        self, async_session, test_organization, second_organization
    ):
        """
        Test that updating a resource requires matching organization_id.

        Attempting to update with wrong org_id should fail.
        """
        # from src.crud.resource import create_resource, update_resource

        org1_id = str(test_organization.id)
        org2_id = str(second_organization.id)

        # Create resource in org1
        # resource = await create_resource(async_session, {"name": "Original"}, org1_id)

        # Update with correct org_id should work
        # updated = await update_resource(
        #     async_session,
        #     resource_id=str(resource.id),
        #     organization_id=org1_id,
        #     data={"name": "Updated"}
        # )
        # assert updated.name == "Updated"

        # Update with wrong org_id should fail (raise ValueError or return None)
        # with pytest.raises(ValueError, match="not found"):
        #     await update_resource(
        #         async_session,
        #         resource_id=str(resource.id),
        #         organization_id=org2_id,  # Wrong org
        #         data={"name": "Should Fail"}
        #     )
        pass  # Remove this and uncomment above when using template

    @pytest.mark.asyncio
    async def test_delete_resource_requires_same_org(
        self, async_session, test_organization, second_organization
    ):
        """
        Test that deleting a resource requires matching organization_id.

        Cross-tenant deletion should be denied.
        """
        # from src.crud.resource import create_resource, delete_resource, get_resource_by_id

        org1_id = str(test_organization.id)
        org2_id = str(second_organization.id)

        # Create resource in org1
        # resource = await create_resource(async_session, {"name": "To Delete"}, org1_id)

        # Delete with wrong org_id should fail
        # with pytest.raises(ValueError, match="not found"):
        #     await delete_resource(async_session, str(resource.id), org2_id)

        # Resource should still exist
        # result = await get_resource_by_id(async_session, str(resource.id), org1_id)
        # assert result is not None

        # Delete with correct org_id should work (soft delete)
        # deleted = await delete_resource(async_session, str(resource.id), org1_id)
        # assert deleted.deleted_time is not None
        pass  # Remove this and uncomment above when using template


# =============================================================================
# TEMPLATE 2: API-Level Tenant Isolation Tests
# =============================================================================
# Use these patterns when testing API endpoints (api_tests/)


class TestResourceTenantIsolationAPI:
    """
    Template for testing tenant isolation at the API level.

    Replace '/api/v1/resources' with your actual endpoint path.
    These tests verify that the HTTP layer correctly enforces tenant isolation.
    """

    @pytest.mark.asyncio
    async def test_cannot_access_other_org_resource_returns_404(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        second_organization,
        test_jwt_token,  # Token for test_organization user
    ):
        """
        Test that accessing another org's resource returns 404.

        IMPORTANT: Returns 404 (not 403) to avoid revealing that the resource
        exists in another tenant. This is a security best practice.
        """
        # Create resource in second_organization
        # from src.crud.resource import create_resource
        # resource = await create_resource(
        #     async_session,
        #     {"name": "Other Org Resource"},
        #     str(second_organization.id)
        # )

        # Try to access with test_organization token
        # response = await client.get(
        #     f"/api/v1/resources/{resource.id}",
        #     headers={"Authorization": test_jwt_token}
        # )

        # Should return 404, NOT 403
        # assert response.status_code == 404
        pass  # Remove this and uncomment above when using template

    @pytest.mark.asyncio
    async def test_can_access_same_org_resource(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        test_jwt_token,
    ):
        """
        Test that accessing own organization's resource works correctly.
        """
        # Create resource in test_organization
        # from src.crud.resource import create_resource
        # resource = await create_resource(
        #     async_session,
        #     {"name": "My Org Resource"},
        #     str(test_organization.id)
        # )

        # Access with same org token should work
        # response = await client.get(
        #     f"/api/v1/resources/{resource.id}",
        #     headers={"Authorization": test_jwt_token}
        # )

        # assert response.status_code == 200
        # data = response.json()
        # assert data["name"] == "My Org Resource"
        pass  # Remove this and uncomment above when using template

    @pytest.mark.asyncio
    async def test_list_only_shows_same_org_resources(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        second_organization,
        test_jwt_token,
    ):
        """
        Test that listing resources only shows current organization's items.
        """
        # from src.crud.resource import create_resource

        # Create resources in both orgs
        # my_resource = await create_resource(
        #     async_session, {"name": "My Resource"}, str(test_organization.id)
        # )
        # other_resource = await create_resource(
        #     async_session, {"name": "Other Resource"}, str(second_organization.id)
        # )

        # List resources
        # response = await client.get(
        #     "/api/v1/resources",
        #     headers={"Authorization": test_jwt_token}
        # )

        # assert response.status_code == 200
        # data = response.json()

        # Should only contain our organization's resources
        # resource_ids = [r["id"] for r in data["items"]]
        # assert str(my_resource.id) in resource_ids
        # assert str(other_resource.id) not in resource_ids
        pass  # Remove this and uncomment above when using template

    @pytest.mark.asyncio
    async def test_cannot_update_other_org_resource(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        second_organization,
        test_jwt_token,
    ):
        """
        Test that updating another org's resource fails with 404.
        """
        # from src.crud.resource import create_resource

        # Create resource in second_organization
        # resource = await create_resource(
        #     async_session, {"name": "Other Resource"}, str(second_organization.id)
        # )

        # Try to update with test_organization token
        # response = await client.put(
        #     f"/api/v1/resources/{resource.id}",
        #     headers={"Authorization": test_jwt_token},
        #     json={"name": "Hacked Name"}
        # )

        # assert response.status_code == 404
        pass  # Remove this and uncomment above when using template

    @pytest.mark.asyncio
    async def test_cannot_delete_other_org_resource(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        second_organization,
        test_jwt_token,
    ):
        """
        Test that deleting another org's resource fails with 404.
        """
        # from src.crud.resource import create_resource, get_resource_by_id

        # Create resource in second_organization
        # resource = await create_resource(
        #     async_session, {"name": "Other Resource"}, str(second_organization.id)
        # )

        # Try to delete with test_organization token
        # response = await client.delete(
        #     f"/api/v1/resources/{resource.id}",
        #     headers={"Authorization": test_jwt_token}
        # )

        # assert response.status_code == 404

        # Verify resource still exists in the other org
        # result = await get_resource_by_id(
        #     async_session, str(resource.id), str(second_organization.id)
        # )
        # assert result is not None
        # assert result.deleted_time is None  # Not deleted
        pass  # Remove this and uncomment above when using template


# =============================================================================
# TEMPLATE 3: Super Admin Access Tests
# =============================================================================
# Use when testing features that super admins (is_admin=True) should access


class TestResourceSuperAdminAccess:
    """
    Template for testing super admin cross-tenant access.

    Super admins (is_admin=True) can bypass tenant restrictions for
    administrative purposes.
    """

    @pytest.mark.asyncio
    async def test_super_admin_can_access_any_org_resource(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        second_organization,
        test_admin_token,  # Token for user with is_admin=True
    ):
        """
        Test that super admins can access resources across all organizations.
        """
        # from src.crud.resource import create_resource

        # Create resource in second_organization
        # resource = await create_resource(
        #     async_session, {"name": "Any Org Resource"}, str(second_organization.id)
        # )

        # Super admin should be able to access it
        # response = await client.get(
        #     f"/api/v1/resources/{resource.id}",
        #     headers={"Authorization": test_admin_token}
        # )

        # assert response.status_code == 200
        pass  # Remove this and uncomment above when using template

    @pytest.mark.asyncio
    async def test_super_admin_can_list_all_org_resources(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        second_organization,
        test_admin_token,
    ):
        """
        Test that super admins can list resources from all organizations.

        Note: Implementation may vary - some endpoints filter by org even for
        admins (using query params), others show all. Test based on your design.
        """
        # Implementation depends on endpoint design
        pass


# =============================================================================
# TEMPLATE 4: Mixed-Scope Resource Tests
# =============================================================================
# Use for resources that can be both org-specific and system-wide (org_id NULL)


class TestMixedScopeResourceIsolation:
    """
    Template for testing mixed-scope resources (like NotificationTemplate).

    Mixed-scope resources have:
    - organization_id = NULL: System-wide, available to all tenants
    - organization_id = UUID: Org-specific, only available to that tenant
    """

    @pytest.mark.asyncio
    async def test_org_specific_resource_not_visible_to_other_orgs(
        self, async_session, test_organization, second_organization
    ):
        """
        Test that org-specific mixed-scope resources are properly isolated.
        """
        # from src.crud.template import create_template, get_template

        # Create org-specific template
        # template = await create_template(
        #     async_session,
        #     {"code": "welcome", "body": "Custom Welcome"},
        #     organization_id=str(test_organization.id)
        # )

        # Should be visible to same org
        # result = await get_template(async_session, "welcome", str(test_organization.id))
        # assert result is not None
        # assert result.body == "Custom Welcome"

        # Should NOT be visible to other org
        # result = await get_template(async_session, "welcome", str(second_organization.id))
        # assert result is None  # or returns system template instead
        pass  # Remove this and uncomment above when using template

    @pytest.mark.asyncio
    async def test_system_wide_resource_visible_to_all_orgs(
        self, async_session, test_organization, second_organization
    ):
        """
        Test that system-wide (NULL org_id) resources are visible to all tenants.
        """
        # from src.crud.template import create_template, get_template

        # Create system-wide template (no organization_id)
        # template = await create_template(
        #     async_session,
        #     {"code": "system_notice", "body": "System Notice"},
        #     organization_id=None  # System-wide
        # )

        # Should be visible to org1
        # result = await get_template(async_session, "system_notice", str(test_organization.id))
        # assert result is not None

        # Should be visible to org2
        # result = await get_template(async_session, "system_notice", str(second_organization.id))
        # assert result is not None
        pass  # Remove this and uncomment above when using template

    @pytest.mark.asyncio
    async def test_org_specific_overrides_system_wide(
        self, async_session, test_organization, second_organization
    ):
        """
        Test that org-specific resources take precedence over system-wide.

        Common pattern: Try org-specific first, fall back to system-wide.
        """
        # from src.crud.template import create_template, get_effective_template

        # Create system-wide template
        # await create_template(
        #     async_session,
        #     {"code": "greeting", "body": "Default Greeting"},
        #     organization_id=None
        # )

        # Create org-specific override for org1
        # await create_template(
        #     async_session,
        #     {"code": "greeting", "body": "Custom Org1 Greeting"},
        #     organization_id=str(test_organization.id)
        # )

        # Org1 should get custom version
        # result = await get_effective_template(async_session, "greeting", str(test_organization.id))
        # assert result.body == "Custom Org1 Greeting"

        # Org2 should get system default
        # result = await get_effective_template(async_session, "greeting", str(second_organization.id))
        # assert result.body == "Default Greeting"
        pass  # Remove this and uncomment above when using template


# =============================================================================
# QUICK REFERENCE: Common Assertions
# =============================================================================
#
# Cross-tenant access denied (CRUD level):
#     result = await get_resource(session, resource_id, other_org_id)
#     assert result is None
#
# Cross-tenant access denied (API level):
#     response = await client.get(f"/api/v1/resources/{id}", headers={"Authorization": token})
#     assert response.status_code == 404  # NOT 403 - don't reveal existence
#
# Same-tenant access works:
#     response = await client.get(f"/api/v1/resources/{id}", headers={"Authorization": token})
#     assert response.status_code == 200
#
# Soft delete verification:
#     deleted = await delete_resource(session, resource_id, org_id)
#     assert deleted.deleted_time is not None
#
# List isolation:
#     results, total = await list_resources(session, org_id)
#     assert all(r.organization_id == UUID(org_id) for r in results)
#
# =============================================================================
