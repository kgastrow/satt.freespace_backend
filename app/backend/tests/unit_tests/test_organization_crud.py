"""
Unit tests for organization CRUD operations.
Migrated to async patterns for FastAPI/SQLAlchemy.
"""

import uuid

import pytest

from src.crud.organization import (
    create_organization,
    delete_organization,
    get_organization_by_id,
    get_organization_by_slug,
    get_organizations,
    update_organization,
)


@pytest.mark.asyncio
async def test_create_organization(async_session):
    """Test creating an organization."""
    org_data = {"name": "Test Organization", "slug": "test-org-new"}

    org = await create_organization(async_session, org_data)

    assert org.name == "Test Organization"
    assert org.slug == "test-org-new"
    assert org.is_active is True
    assert org.deleted_time is None


@pytest.mark.asyncio
async def test_create_organization_duplicate_slug(async_session):
    """Test creating an organization with duplicate slug raises error."""
    org_data = {"name": "Test Organization", "slug": "test-org-dup"}

    await create_organization(async_session, org_data)

    # Try to create another organization with the same slug
    duplicate_org_data = {"name": "Another Organization", "slug": "test-org-dup"}

    with pytest.raises(ValueError, match="already exists"):
        await create_organization(async_session, duplicate_org_data)


@pytest.mark.asyncio
async def test_get_organization_by_id(async_session):
    """Test retrieving an organization by ID."""
    org_data = {"name": "Test Organization", "slug": "test-org-byid"}
    created_org = await create_organization(async_session, org_data)

    org = await get_organization_by_id(async_session, str(created_org.id))

    assert org is not None
    assert org.id == created_org.id
    assert org.name == "Test Organization"
    assert org.slug == "test-org-byid"


@pytest.mark.asyncio
async def test_get_organization_by_id_not_found(async_session):
    """Test retrieving a non-existent organization by ID returns None."""
    org = await get_organization_by_id(async_session, str(uuid.uuid4()))

    assert org is None


@pytest.mark.asyncio
async def test_get_organization_by_slug(async_session):
    """Test retrieving an organization by slug."""
    org_data = {"name": "Test Organization", "slug": "test-org-byslug"}
    await create_organization(async_session, org_data)

    org = await get_organization_by_slug(async_session, "test-org-byslug")

    assert org is not None
    assert org.name == "Test Organization"
    assert org.slug == "test-org-byslug"


@pytest.mark.asyncio
async def test_get_organization_by_slug_not_found(async_session):
    """Test retrieving a non-existent organization by slug returns None."""
    org = await get_organization_by_slug(async_session, "non-existent-slug")

    assert org is None


@pytest.mark.asyncio
async def test_get_organizations(async_session):
    """Test listing all organizations."""
    # Create multiple organizations
    await create_organization(async_session, {"name": "Org 1", "slug": "org-list-1"})
    await create_organization(async_session, {"name": "Org 2", "slug": "org-list-2"})
    await create_organization(async_session, {"name": "Org 3", "slug": "org-list-3"})

    organizations, total_count = await get_organizations(async_session)

    assert total_count >= 3
    assert len(organizations) >= 3


@pytest.mark.asyncio
async def test_get_organizations_with_pagination(async_session):
    """Test listing organizations with pagination."""
    # Create multiple organizations
    for i in range(5):
        await create_organization(
            async_session, {"name": f"Org Pag {i}", "slug": f"org-pag-{i}"}
        )

    # Get first page
    organizations, total_count = await get_organizations(
        async_session, limit=2, offset=0
    )
    assert len(organizations) == 2

    # Get second page
    organizations, total_count = await get_organizations(
        async_session, limit=2, offset=2
    )
    assert len(organizations) == 2


@pytest.mark.asyncio
async def test_update_organization(async_session):
    """Test updating an organization."""
    org_data = {"name": "Original Name", "slug": "original-slug-upd"}
    org = await create_organization(async_session, org_data)

    update_data = {
        "id": str(org.id),
        "name": "Updated Name",
        "slug": "updated-slug-upd",
        "is_active": False,
    }
    updated_org = await update_organization(async_session, update_data)

    assert updated_org.name == "Updated Name"
    assert updated_org.slug == "updated-slug-upd"
    assert updated_org.is_active is False


@pytest.mark.asyncio
async def test_update_organization_partial(async_session):
    """Test partially updating an organization."""
    org_data = {"name": "Original Name", "slug": "original-slug-partial"}
    org = await create_organization(async_session, org_data)

    # Update only the name
    update_data = {"id": str(org.id), "name": "Updated Name"}
    updated_org = await update_organization(async_session, update_data)

    assert updated_org.name == "Updated Name"
    assert updated_org.slug == "original-slug-partial"  # slug should remain unchanged
    assert updated_org.is_active is True  # is_active should remain unchanged


@pytest.mark.asyncio
async def test_update_organization_duplicate_slug(async_session):
    """Test updating an organization with duplicate slug raises error."""
    # Create two organizations
    await create_organization(async_session, {"name": "Org 1", "slug": "org-dup-1"})
    org2 = await create_organization(
        async_session, {"name": "Org 2", "slug": "org-dup-2"}
    )

    # Try to update org2 with org1's slug
    update_data = {"id": str(org2.id), "slug": "org-dup-1"}

    with pytest.raises(ValueError, match="already exists"):
        await update_organization(async_session, update_data)


@pytest.mark.asyncio
async def test_update_organization_not_found(async_session):
    """Test updating a non-existent organization raises error."""
    update_data = {"id": str(uuid.uuid4()), "name": "Updated Name"}

    with pytest.raises(ValueError, match="not found"):
        await update_organization(async_session, update_data)


@pytest.mark.asyncio
async def test_delete_organization(async_session):
    """Test soft deleting an organization."""
    org_data = {"name": "Test Organization", "slug": "test-org-del"}
    org = await create_organization(async_session, org_data)

    deleted_org = await delete_organization(async_session, str(org.id))

    assert deleted_org.deleted_time is not None

    # Verify soft delete - organization should not be retrievable
    org_check = await get_organization_by_id(async_session, str(org.id))
    assert org_check is None


@pytest.mark.asyncio
async def test_delete_organization_not_found(async_session):
    """Test deleting a non-existent organization raises error."""
    with pytest.raises(ValueError, match="not found"):
        await delete_organization(async_session, str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_get_organizations_excludes_deleted(async_session):
    """Test that get_organizations does not return soft-deleted organizations."""
    # Create organizations
    await create_organization(async_session, {"name": "Org 1", "slug": "org-excl-1"})
    org2 = await create_organization(
        async_session, {"name": "Org 2", "slug": "org-excl-2"}
    )
    await create_organization(async_session, {"name": "Org 3", "slug": "org-excl-3"})

    # Delete one organization
    await delete_organization(async_session, str(org2.id))

    # Get all organizations
    organizations, total_count = await get_organizations(async_session)

    org_slugs = [org.slug for org in organizations]
    assert "org-excl-1" in org_slugs
    assert "org-excl-3" in org_slugs
    assert "org-excl-2" not in org_slugs
