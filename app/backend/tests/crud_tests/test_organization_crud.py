"""
Unit tests for organization CRUD operations.
Tests organization creation, retrieval, update, deletion, and related features.
"""

from uuid import uuid4

import pytest

from src.crud.organization import (
    cancel_organization_deletion_request,
    create_organization,
    delete_organization,
    get_organization_by_id,
    get_organization_by_slug,
    get_organization_deletion_request,
    get_organization_details,
    get_organizations,
    request_organization_deletion,
    update_organization,
    update_organization_details,
)


# ============================================================================
# CREATE ORGANIZATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_organization_success(async_session):
    """Test creating an organization with valid data."""
    org = await create_organization(
        async_session,
        {"name": "Test Org", "slug": "test-org-new"},
    )

    assert org.id is not None
    assert org.name == "Test Org"
    assert org.slug == "test-org-new"
    assert org.is_active is True
    assert org.deleted_time is None


@pytest.mark.asyncio
async def test_create_organization_with_all_fields(async_session):
    """Test creating an organization with all optional fields."""
    org = await create_organization(
        async_session,
        {
            "name": "Full Org",
            "slug": "full-org",
            "display_name": "Full Organization Display",
            "physical_address_line1": "123 Main St",
            "physical_address_line2": "Suite 100",
            "city": "San Francisco",
            "state_province": "CA",
            "postal_code": "94102",
            "country": "USA",
            "contact_email": "contact@fullorg.com",
            "contact_phone": "+14155551234",
        },
    )

    assert org.name == "Full Org"
    assert org.display_name == "Full Organization Display"
    assert org.physical_address_line1 == "123 Main St"
    assert org.physical_address_line2 == "Suite 100"
    assert org.city == "San Francisco"
    assert org.state_province == "CA"
    assert org.postal_code == "94102"
    assert org.country == "USA"
    assert org.contact_email == "contact@fullorg.com"
    assert org.contact_phone == "+14155551234"


@pytest.mark.asyncio
async def test_create_organization_creates_sso_settings(async_session):
    """Test that creating an organization also creates default SSO settings."""
    from sqlalchemy import select

    from src.models.organization_sso_settings import OrganizationSSOSettings

    org = await create_organization(
        async_session,
        {"name": "SSO Test Org", "slug": "sso-test-org"},
    )

    # Check SSO settings were created
    result = await async_session.execute(
        select(OrganizationSSOSettings).where(
            OrganizationSSOSettings.organization_id == org.id
        )
    )
    sso_settings = result.scalars().first()

    assert sso_settings is not None
    assert sso_settings.sso_allowed is False
    assert sso_settings.google_enabled is False


@pytest.mark.asyncio
async def test_create_organization_creates_2fa_settings(async_session):
    """Test that creating an organization also creates default 2FA settings."""
    from sqlalchemy import select

    from src.models.organization_two_factor_settings import (
        OrganizationTwoFactorSettings,
    )

    org = await create_organization(
        async_session,
        {"name": "2FA Test Org", "slug": "2fa-test-org"},
    )

    # Check 2FA settings were created
    result = await async_session.execute(
        select(OrganizationTwoFactorSettings).where(
            OrganizationTwoFactorSettings.organization_id == org.id
        )
    )
    two_factor_settings = result.scalars().first()

    assert two_factor_settings is not None
    assert two_factor_settings.two_factor_allowed is False


@pytest.mark.asyncio
async def test_create_organization_duplicate_slug_fails(async_session):
    """Test creating an organization with duplicate slug fails."""
    await create_organization(
        async_session,
        {"name": "First Org", "slug": "duplicate-slug"},
    )

    with pytest.raises(ValueError, match="already exists"):
        await create_organization(
            async_session,
            {"name": "Second Org", "slug": "duplicate-slug"},
        )


@pytest.mark.asyncio
async def test_create_organization_invalid_slug(async_session):
    """Test creating an organization with invalid slug fails validation."""
    # Slug with spaces should fail
    with pytest.raises(Exception):
        await create_organization(
            async_session,
            {"name": "Invalid Org", "slug": "invalid slug"},
        )


@pytest.mark.asyncio
async def test_create_organization_short_slug(async_session):
    """Test creating an organization with too short slug fails."""
    with pytest.raises(Exception):
        await create_organization(
            async_session,
            {"name": "Short Org", "slug": "ab"},  # Less than 3 chars
        )


# ============================================================================
# GET ORGANIZATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_organization_by_id_success(async_session):
    """Test retrieving an organization by ID."""
    created_org = await create_organization(
        async_session,
        {"name": "Find By ID", "slug": "find-by-id"},
    )

    found_org = await get_organization_by_id(async_session, str(created_org.id))

    assert found_org is not None
    assert found_org.id == created_org.id
    assert found_org.name == "Find By ID"


@pytest.mark.asyncio
async def test_get_organization_by_id_not_found(async_session):
    """Test retrieving a non-existent organization returns None."""
    fake_id = str(uuid4())

    result = await get_organization_by_id(async_session, fake_id)
    assert result is None


@pytest.mark.asyncio
async def test_get_organization_by_slug_success(async_session):
    """Test retrieving an organization by slug."""
    created_org = await create_organization(
        async_session,
        {"name": "Find By Slug", "slug": "find-by-slug"},
    )

    found_org = await get_organization_by_slug(async_session, "find-by-slug")

    assert found_org is not None
    assert found_org.id == created_org.id
    assert found_org.slug == "find-by-slug"


@pytest.mark.asyncio
async def test_get_organization_by_slug_not_found(async_session):
    """Test retrieving a non-existent slug returns None."""
    result = await get_organization_by_slug(async_session, "nonexistent-slug")
    assert result is None


@pytest.mark.asyncio
async def test_get_organization_by_id_excludes_deleted(async_session):
    """Test that get by ID excludes soft-deleted organizations."""
    org = await create_organization(
        async_session,
        {"name": "To Delete", "slug": "to-delete"},
    )

    # Delete the organization
    await delete_organization(async_session, str(org.id))

    # Should not find it anymore
    result = await get_organization_by_id(async_session, str(org.id))
    assert result is None


@pytest.mark.asyncio
async def test_get_organization_by_slug_excludes_deleted(async_session):
    """Test that get by slug excludes soft-deleted organizations."""
    org = await create_organization(
        async_session,
        {"name": "To Delete Slug", "slug": "to-delete-slug"},
    )

    # Delete the organization
    await delete_organization(async_session, str(org.id))

    # Should not find it anymore
    result = await get_organization_by_slug(async_session, "to-delete-slug")
    assert result is None


# ============================================================================
# LIST ORGANIZATIONS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_organizations_pagination(async_session):
    """Test listing organizations with pagination."""
    # Create 5 organizations
    for i in range(5):
        await create_organization(
            async_session,
            {"name": f"List Org {i}", "slug": f"list-org-{i}"},
        )

    # Get first page
    orgs, total = await get_organizations(async_session, limit=2, offset=0)

    assert total == 5
    assert len(orgs) == 2

    # Get second page
    orgs2, total2 = await get_organizations(async_session, limit=2, offset=2)

    assert total2 == 5
    assert len(orgs2) == 2

    # Ensure different orgs on different pages
    page1_ids = {o.id for o in orgs}
    page2_ids = {o.id for o in orgs2}
    assert page1_ids.isdisjoint(page2_ids)


@pytest.mark.asyncio
async def test_get_organizations_excludes_deleted(async_session):
    """Test that listing excludes soft-deleted organizations."""
    org1 = await create_organization(
        async_session,
        {"name": "Active Org", "slug": "active-org"},
    )
    org2 = await create_organization(
        async_session,
        {"name": "Deleted Org", "slug": "deleted-org"},
    )

    # Delete one organization
    await delete_organization(async_session, str(org2.id))

    # List should only return active org
    orgs, total = await get_organizations(async_session)
    assert total == 1
    assert orgs[0].id == org1.id


# ============================================================================
# UPDATE ORGANIZATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_update_organization_name(async_session):
    """Test updating organization name."""
    org = await create_organization(
        async_session,
        {"name": "Original Name", "slug": "original-slug"},
    )

    updated = await update_organization(
        async_session,
        {
            "id": str(org.id),
            "name": "Updated Name",
        },
    )

    assert updated.name == "Updated Name"
    assert updated.slug == "original-slug"  # Unchanged


@pytest.mark.asyncio
async def test_update_organization_slug(async_session):
    """Test updating organization slug."""
    org = await create_organization(
        async_session,
        {"name": "Slug Update", "slug": "old-slug"},
    )

    updated = await update_organization(
        async_session,
        {
            "id": str(org.id),
            "slug": "new-slug",
        },
    )

    assert updated.slug == "new-slug"


@pytest.mark.asyncio
async def test_update_organization_slug_duplicate_fails(async_session):
    """Test updating slug to one that already exists fails."""
    await create_organization(
        async_session,
        {"name": "First Org", "slug": "existing-slug"},
    )
    org2 = await create_organization(
        async_session,
        {"name": "Second Org", "slug": "second-slug"},
    )

    with pytest.raises(ValueError, match="already exists"):
        await update_organization(
            async_session,
            {
                "id": str(org2.id),
                "slug": "existing-slug",
            },
        )


@pytest.mark.asyncio
async def test_update_organization_is_active(async_session):
    """Test updating organization active status."""
    org = await create_organization(
        async_session,
        {"name": "Active Org", "slug": "active-org-update"},
    )

    updated = await update_organization(
        async_session,
        {
            "id": str(org.id),
            "is_active": False,
        },
    )

    assert updated.is_active is False


@pytest.mark.asyncio
async def test_update_organization_not_found(async_session):
    """Test updating a non-existent organization fails."""
    fake_id = str(uuid4())

    with pytest.raises(ValueError, match="not found"):
        await update_organization(
            async_session,
            {
                "id": fake_id,
                "name": "Ghost Org",
            },
        )


# ============================================================================
# DELETE ORGANIZATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_delete_organization_soft_delete(async_session):
    """Test that organization deletion is soft delete."""
    org = await create_organization(
        async_session,
        {"name": "Delete Me", "slug": "delete-me"},
    )

    deleted_org = await delete_organization(async_session, str(org.id))

    assert deleted_org.deleted_time is not None
    assert deleted_org.id == org.id

    # Organization should no longer appear in normal queries
    result = await get_organization_by_id(async_session, str(org.id))
    assert result is None


@pytest.mark.asyncio
async def test_delete_organization_not_found(async_session):
    """Test deleting a non-existent organization fails."""
    fake_id = str(uuid4())

    with pytest.raises(ValueError, match="not found"):
        await delete_organization(async_session, fake_id)


@pytest.mark.asyncio
async def test_delete_organization_cascade_soft_deletes_users(async_session):
    """Test that deleting an organization also soft-deletes its users."""
    from src.crud.user import create_user, get_user_by_id

    org = await create_organization(
        async_session,
        {"name": "Cascade Org", "slug": "cascade-org"},
    )
    org_id = str(org.id)

    # Create a user in the organization
    user = await create_user(
        async_session,
        {"email": "cascade@test.com", "password": "Password123!"},
        org_id,
    )

    # Delete the organization
    await delete_organization(async_session, org_id)

    # User should no longer be accessible
    result = await get_user_by_id(async_session, str(user.id), org_id)
    assert result is None


@pytest.mark.asyncio
@pytest.mark.skip(
    reason="SQLite doesn't support partial unique indexes. "
    "This works in PostgreSQL where deleted_time IS NULL constraint allows slug reuse."
)
async def test_deleted_slug_can_be_reused(async_session):
    """Test that a slug can be reused after organization is deleted.

    Note: This test is skipped because SQLite (used in tests) doesn't support
    partial unique indexes. In PostgreSQL, the partial unique index on slug
    (WHERE deleted_time IS NULL) allows reusing slugs for soft-deleted orgs.
    """
    org = await create_organization(
        async_session,
        {"name": "Reusable Slug", "slug": "reusable-slug"},
    )

    # Delete the organization
    await delete_organization(async_session, str(org.id))

    # Should be able to create new org with same slug
    new_org = await create_organization(
        async_session,
        {"name": "New Org Same Slug", "slug": "reusable-slug"},
    )

    assert new_org.id != org.id
    assert new_org.slug == "reusable-slug"


# ============================================================================
# DELETION REQUEST TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_request_organization_deletion(async_session):
    """Test requesting organization deletion."""
    from src.crud.user import create_user

    org = await create_organization(
        async_session,
        {"name": "Request Delete", "slug": "request-delete"},
    )
    org_id = str(org.id)

    user = await create_user(
        async_session,
        {"email": "requester@test.com", "password": "Password123!"},
        org_id,
    )

    deletion_request = await request_organization_deletion(
        async_session, org_id, str(user.id)
    )

    assert deletion_request is not None
    assert deletion_request.organization_id == org.id
    assert deletion_request.requested_by_id == user.id


@pytest.mark.asyncio
async def test_request_organization_deletion_duplicate_fails(async_session):
    """Test that duplicate deletion requests fail."""
    from src.crud.user import create_user

    org = await create_organization(
        async_session,
        {"name": "Duplicate Delete", "slug": "duplicate-delete"},
    )
    org_id = str(org.id)

    user = await create_user(
        async_session,
        {"email": "dupe@test.com", "password": "Password123!"},
        org_id,
    )

    # First request should succeed
    await request_organization_deletion(async_session, org_id, str(user.id))

    # Second request should fail
    with pytest.raises(ValueError, match="already been requested"):
        await request_organization_deletion(async_session, org_id, str(user.id))


@pytest.mark.asyncio
async def test_request_organization_deletion_not_found(async_session):
    """Test requesting deletion for non-existent org fails."""
    fake_id = str(uuid4())
    fake_user_id = str(uuid4())

    with pytest.raises(ValueError, match="not found"):
        await request_organization_deletion(async_session, fake_id, fake_user_id)


@pytest.mark.asyncio
async def test_cancel_organization_deletion_request(async_session):
    """Test canceling a deletion request."""
    from src.crud.user import create_user

    org = await create_organization(
        async_session,
        {"name": "Cancel Delete", "slug": "cancel-delete"},
    )
    org_id = str(org.id)

    user = await create_user(
        async_session,
        {"email": "canceler@test.com", "password": "Password123!"},
        org_id,
    )

    # Request deletion
    await request_organization_deletion(async_session, org_id, str(user.id))

    # Cancel the request
    result = await cancel_organization_deletion_request(async_session, org_id)

    assert result is not None
    assert result.id == org.id

    # Verify request was deleted
    deletion_req = await get_organization_deletion_request(async_session, org_id)
    assert deletion_req is None


@pytest.mark.asyncio
async def test_cancel_organization_deletion_no_request(async_session):
    """Test canceling when no deletion request exists fails."""
    org = await create_organization(
        async_session,
        {"name": "No Request", "slug": "no-request"},
    )

    with pytest.raises(ValueError, match="No deletion request exists"):
        await cancel_organization_deletion_request(async_session, str(org.id))


@pytest.mark.asyncio
async def test_get_organization_deletion_request(async_session):
    """Test getting a deletion request."""
    from src.crud.user import create_user

    org = await create_organization(
        async_session,
        {"name": "Get Delete Request", "slug": "get-delete-request"},
    )
    org_id = str(org.id)

    user = await create_user(
        async_session,
        {"email": "getter@test.com", "password": "Password123!"},
        org_id,
    )

    # No request initially
    result = await get_organization_deletion_request(async_session, org_id)
    assert result is None

    # Create request
    await request_organization_deletion(async_session, org_id, str(user.id))

    # Now should find it
    result = await get_organization_deletion_request(async_session, org_id)
    assert result is not None
    assert result.organization_id == org.id


# ============================================================================
# ORGANIZATION DETAILS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_organization_details(async_session):
    """Test getting organization details."""
    org = await create_organization(
        async_session,
        {
            "name": "Details Org",
            "slug": "details-org",
            "display_name": "Details Organization",
            "city": "New York",
            "country": "USA",
        },
    )

    details = await get_organization_details(async_session, str(org.id))

    assert details is not None
    assert details.name == "Details Org"
    assert details.display_name == "Details Organization"
    assert details.city == "New York"
    assert details.country == "USA"


@pytest.mark.asyncio
async def test_get_organization_details_not_found(async_session):
    """Test getting details for non-existent org fails."""
    fake_id = str(uuid4())

    with pytest.raises(ValueError, match="not found"):
        await get_organization_details(async_session, fake_id)


@pytest.mark.asyncio
async def test_update_organization_details(async_session):
    """Test updating organization details."""
    org = await create_organization(
        async_session,
        {"name": "Update Details", "slug": "update-details"},
    )

    updated = await update_organization_details(
        async_session,
        str(org.id),
        {
            "display_name": "New Display Name",
            "city": "Los Angeles",
            "state_province": "CA",
            "contact_email": "new@contact.com",
        },
    )

    assert updated.display_name == "New Display Name"
    assert updated.city == "Los Angeles"
    assert updated.state_province == "CA"
    assert updated.contact_email == "new@contact.com"


@pytest.mark.asyncio
async def test_update_organization_details_not_found(async_session):
    """Test updating details for non-existent org fails."""
    fake_id = str(uuid4())

    with pytest.raises(ValueError, match="not found"):
        await update_organization_details(
            async_session,
            fake_id,
            {"display_name": "Ghost"},
        )


@pytest.mark.asyncio
async def test_update_organization_details_partial(async_session):
    """Test partial update only changes specified fields."""
    org = await create_organization(
        async_session,
        {
            "name": "Partial Update",
            "slug": "partial-update",
            "city": "Original City",
            "country": "Original Country",
        },
    )

    # Only update city
    updated = await update_organization_details(
        async_session,
        str(org.id),
        {"city": "New City"},
    )

    assert updated.city == "New City"
    assert updated.country == "Original Country"  # Unchanged
