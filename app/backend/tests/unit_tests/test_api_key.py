"""
Unit tests for API key CRUD operations.

Tests cover:
- API key creation with secure random generation
- Retrieval operations
- Update operations (name only - expiration cannot be modified after creation)
- Soft delete (revocation)
- Key validation with hash verification
- Permission assignment and removal
- Multi-tenancy isolation (cannot access other org's keys)
- Scope field (user, organization, platform)
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.crud.api_key import (
    assign_permissions,
    create_api_key,
    delete_api_key,
    get_api_key_by_id,
    get_api_key_permissions,
    get_api_keys_by_organization,
    remove_permissions,
    update_api_key,
    validate_api_key,
)


@pytest.mark.asyncio
async def test_create_api_key(async_session, test_organization, test_user):
    """Test creating an API key."""
    name = "Test API Key"
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    api_key, full_key = await create_api_key(
        session=async_session,
        name=name,
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
        expires_at=expires_at,
    )

    assert api_key.name == name
    assert api_key.organization_id == test_organization.id
    assert api_key.created_by == test_user.id
    # SQLite doesn't preserve timezone info, so compare without tzinfo
    assert api_key.expires_at.replace(tzinfo=None) == expires_at.replace(tzinfo=None)
    assert api_key.prefix == full_key[:8]
    assert len(full_key) > 40  # Should be a long secure key
    assert api_key.key_hash is not None
    assert api_key.deleted_time is None
    assert api_key.last_used_at is None
    assert api_key.scope == "user"  # Default scope


@pytest.mark.asyncio
async def test_create_api_key_without_expiration(
    async_session, test_organization, test_user
):
    """Test creating an API key without expiration."""
    api_key, full_key = await create_api_key(
        session=async_session,
        name="Never Expires",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
        expires_at=None,
    )

    assert api_key.name == "Never Expires"
    assert api_key.expires_at is None


@pytest.mark.asyncio
async def test_create_api_key_duplicate_name(
    async_session, test_organization, test_user
):
    """Test creating an API key with duplicate name raises error."""
    name = "Duplicate Key"

    await create_api_key(
        session=async_session,
        name=name,
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    # Try to create another key with the same name
    with pytest.raises(ValueError, match="already exists"):
        await create_api_key(
            session=async_session,
            name=name,
            organization_id=str(test_organization.id),
            created_by=str(test_user.id),
        )


@pytest.mark.asyncio
async def test_create_api_key_with_scope(async_session, test_organization, test_user):
    """Test creating API keys with different scopes."""
    from src.models.api_key import ApiKeyScope

    # Create API key with user scope (default)
    api_key_user, _ = await create_api_key(
        session=async_session,
        name="User Scope Key",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
        scope=ApiKeyScope.USER,
    )
    assert api_key_user.scope == "user"

    # Create API key with organization scope
    api_key_org, _ = await create_api_key(
        session=async_session,
        name="Organization Scope Key",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
        scope=ApiKeyScope.ORGANIZATION,
    )
    assert api_key_org.scope == "organization"

    # Create API key with platform scope
    api_key_platform, _ = await create_api_key(
        session=async_session,
        name="Platform Scope Key",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
        scope=ApiKeyScope.PLATFORM,
    )
    assert api_key_platform.scope == "platform"


@pytest.mark.asyncio
async def test_get_api_key_by_id(async_session, test_organization, test_user):
    """Test retrieving an API key by ID."""
    api_key, _ = await create_api_key(
        session=async_session,
        name="Get By ID Test",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    retrieved_key = await get_api_key_by_id(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_organization.id),
    )

    assert retrieved_key is not None
    assert retrieved_key.id == api_key.id
    assert retrieved_key.name == "Get By ID Test"


@pytest.mark.asyncio
async def test_get_api_key_by_id_not_found(async_session, test_organization):
    """Test retrieving a non-existent API key returns None."""
    import uuid

    retrieved_key = await get_api_key_by_id(
        session=async_session,
        api_key_id=str(uuid.uuid4()),
        organization_id=str(test_organization.id),
    )

    assert retrieved_key is None


@pytest.mark.asyncio
async def test_get_api_keys_by_organization(
    async_session, test_organization, test_user
):
    """Test listing all API keys for an organization."""
    # Create multiple API keys
    await create_api_key(
        session=async_session,
        name="Key 1",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )
    await create_api_key(
        session=async_session,
        name="Key 2",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )
    await create_api_key(
        session=async_session,
        name="Key 3",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    keys, total = await get_api_keys_by_organization(
        session=async_session,
        organization_id=str(test_organization.id),
    )

    assert total == 3
    assert len(keys) == 3
    key_names = {k.name for k in keys}
    assert "Key 1" in key_names
    assert "Key 2" in key_names
    assert "Key 3" in key_names


@pytest.mark.asyncio
async def test_get_api_keys_pagination(async_session, test_organization, test_user):
    """Test pagination of API keys."""
    # Create 5 keys
    for i in range(5):
        await create_api_key(
            session=async_session,
            name=f"Pag Key {i}",
            organization_id=str(test_organization.id),
            created_by=str(test_user.id),
        )

    # Get first page
    keys, total = await get_api_keys_by_organization(
        session=async_session,
        organization_id=str(test_organization.id),
        limit=2,
        offset=0,
    )
    assert len(keys) == 2
    assert total == 5

    # Get second page
    keys, total = await get_api_keys_by_organization(
        session=async_session,
        organization_id=str(test_organization.id),
        limit=2,
        offset=2,
    )
    assert len(keys) == 2
    assert total == 5


@pytest.mark.asyncio
async def test_update_api_key_name(async_session, test_organization, test_user):
    """Test updating an API key's name."""
    api_key, _ = await create_api_key(
        session=async_session,
        name="Original Name",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    updated_key = await update_api_key(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_organization.id),
        name="Updated Name",
    )

    assert updated_key.name == "Updated Name"


@pytest.mark.asyncio
async def test_update_api_key_duplicate_name(
    async_session, test_organization, test_user
):
    """Test updating an API key to a duplicate name raises error."""
    await create_api_key(
        session=async_session,
        name="Existing Name",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    api_key, _ = await create_api_key(
        session=async_session,
        name="Other Name",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    with pytest.raises(ValueError, match="already exists"):
        await update_api_key(
            session=async_session,
            api_key_id=str(api_key.id),
            organization_id=str(test_organization.id),
            name="Existing Name",
        )


@pytest.mark.asyncio
async def test_delete_api_key(async_session, test_organization, test_user):
    """Test soft deleting (revoking) an API key."""
    api_key, _ = await create_api_key(
        session=async_session,
        name="To Delete",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    deleted_key = await delete_api_key(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_organization.id),
    )

    assert deleted_key.deleted_time is not None

    # Verify it's not retrievable after deletion
    retrieved = await get_api_key_by_id(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_organization.id),
    )
    assert retrieved is None


@pytest.mark.asyncio
async def test_delete_api_key_not_found(async_session, test_organization):
    """Test deleting a non-existent API key raises error."""
    import uuid

    with pytest.raises(ValueError, match="not found"):
        await delete_api_key(
            session=async_session,
            api_key_id=str(uuid.uuid4()),
            organization_id=str(test_organization.id),
        )


@pytest.mark.asyncio
async def test_validate_api_key_success(async_session, test_organization, test_user):
    """Test validating a valid API key."""
    api_key, full_key = await create_api_key(
        session=async_session,
        name="Valid Key",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )

    validated_key = await validate_api_key(
        session=async_session,
        full_key=full_key,
    )

    assert validated_key is not None
    assert validated_key.id == api_key.id
    assert validated_key.last_used_at is not None


@pytest.mark.asyncio
async def test_validate_api_key_invalid_key(async_session):
    """Test validating an invalid API key returns None."""
    validated_key = await validate_api_key(
        session=async_session,
        full_key="invalid_key_that_does_not_exist",
    )

    assert validated_key is None


@pytest.mark.asyncio
async def test_validate_api_key_expired(async_session, test_organization, test_user):
    """Test validating an expired API key returns None."""
    api_key, full_key = await create_api_key(
        session=async_session,
        name="Expired Key",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),  # Expired
    )

    validated_key = await validate_api_key(
        session=async_session,
        full_key=full_key,
    )

    assert validated_key is None


@pytest.mark.asyncio
async def test_validate_api_key_revoked(async_session, test_organization, test_user):
    """Test validating a revoked API key returns None."""
    api_key, full_key = await create_api_key(
        session=async_session,
        name="Revoked Key",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    # Revoke the key
    await delete_api_key(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_organization.id),
    )

    # Try to validate
    validated_key = await validate_api_key(
        session=async_session,
        full_key=full_key,
    )

    assert validated_key is None


@pytest.mark.asyncio
async def test_assign_permissions(
    async_session, test_organization, test_user, standard_permissions
):
    """Test assigning permissions to an API key."""
    api_key, _ = await create_api_key(
        session=async_session,
        name="Key with Perms",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    permissions = ["users:read", "users:write", "files:read"]

    created_perms = await assign_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_organization.id),
        permissions=permissions,
    )

    assert len(created_perms) == 3

    # Verify permissions are assigned
    assigned_perms = await get_api_key_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_organization.id),
    )

    assert set(assigned_perms) == set(permissions)


@pytest.mark.asyncio
async def test_assign_permissions_skip_duplicates(
    async_session, test_organization, test_user, standard_permissions
):
    """Test assigning permissions skips already assigned permissions."""
    api_key, _ = await create_api_key(
        session=async_session,
        name="Key Dup Perms",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    # Assign initial permissions
    await assign_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_organization.id),
        permissions=["users:read", "users:write"],
    )

    # Assign overlapping permissions
    created_perms = await assign_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_organization.id),
        permissions=["users:read", "files:read"],  # users:read already exists
    )

    # Should only create files:read
    assert len(created_perms) == 1
    # Verify the created permission references the files:read permission
    assert created_perms[0].permission_id == standard_permissions["files:read"].id

    # Verify all permissions
    assigned_perms = await get_api_key_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_organization.id),
    )

    assert set(assigned_perms) == {"users:read", "users:write", "files:read"}


@pytest.mark.asyncio
async def test_remove_permissions(
    async_session, test_organization, test_user, standard_permissions
):
    """Test removing permissions from an API key."""
    api_key, _ = await create_api_key(
        session=async_session,
        name="Key Remove Perms",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    # Assign permissions
    await assign_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_organization.id),
        permissions=["users:read", "users:write", "files:read"],
    )

    # Remove some permissions
    removed_count = await remove_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_organization.id),
        permissions=["users:write", "files:read"],
    )

    assert removed_count == 2

    # Verify remaining permissions
    assigned_perms = await get_api_key_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_organization.id),
    )

    assert assigned_perms == ["users:read"]


@pytest.mark.asyncio
async def test_get_api_key_permissions_empty(
    async_session, test_organization, test_user
):
    """Test getting permissions for an API key with no permissions."""
    api_key, _ = await create_api_key(
        session=async_session,
        name="Key No Perms",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    permissions = await get_api_key_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_organization.id),
    )

    assert permissions == []


@pytest.mark.asyncio
async def test_assign_permissions_invalid_code(
    async_session, test_organization, test_user
):
    """Test that assigning non-existent permission codes raises error."""
    api_key, _ = await create_api_key(
        session=async_session,
        name="Key Invalid Perms",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    # Try to assign a permission that doesn't exist in the database
    with pytest.raises(ValueError, match="Permission codes not found"):
        await assign_permissions(
            session=async_session,
            api_key_id=str(api_key.id),
            organization_id=str(test_organization.id),
            permissions=["nonexistent:permission"],
        )


@pytest.mark.asyncio
async def test_permissions_use_fk_relationship(
    async_session, test_organization, test_user, standard_permissions
):
    """Test that ApiKeyPermission correctly references Permission table via FK."""
    from sqlalchemy import select

    from src.models.api_key_permission import ApiKeyPermission

    api_key, _ = await create_api_key(
        session=async_session,
        name="Key FK Test",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    # Assign permissions
    await assign_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_organization.id),
        permissions=["users:read", "files:read"],
    )

    # Query ApiKeyPermission records directly
    result = await async_session.execute(
        select(ApiKeyPermission).where(
            ApiKeyPermission.api_key_id == api_key.id,
            ApiKeyPermission.deleted_time.is_(None),
        )
    )
    api_key_perms = result.scalars().all()

    assert len(api_key_perms) == 2

    # Verify each record has a valid permission_id FK
    permission_ids = {p.permission_id for p in api_key_perms}
    expected_ids = {
        standard_permissions["users:read"].id,
        standard_permissions["files:read"].id,
    }
    assert permission_ids == expected_ids

    # Verify the relationship loads correctly
    for akp in api_key_perms:
        await async_session.refresh(akp, ["permission"])
        assert akp.permission is not None
        assert akp.permission.code in ["users:read", "files:read"]


# ============================================================================
# MULTI-TENANCY ISOLATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_api_key_isolation_different_orgs(
    async_session, test_organization, second_organization, test_user, second_org_user
):
    """Test that API keys are isolated between organizations."""
    # Create key in first org
    api_key_org1, _ = await create_api_key(
        session=async_session,
        name="Org 1 Key",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    # Create key in second org
    api_key_org2, _ = await create_api_key(
        session=async_session,
        name="Org 2 Key",
        organization_id=str(second_organization.id),
        created_by=str(second_org_user.id),
    )

    # Try to access org1 key from org2 context
    retrieved = await get_api_key_by_id(
        session=async_session,
        api_key_id=str(api_key_org1.id),
        organization_id=str(second_organization.id),
    )
    assert retrieved is None

    # Try to access org2 key from org1 context
    retrieved = await get_api_key_by_id(
        session=async_session,
        api_key_id=str(api_key_org2.id),
        organization_id=str(test_organization.id),
    )
    assert retrieved is None


@pytest.mark.asyncio
async def test_list_keys_only_shows_own_org(
    async_session, test_organization, second_organization, test_user, second_org_user
):
    """Test that listing API keys only returns keys from own organization."""
    # Create keys in first org
    await create_api_key(
        session=async_session,
        name="Org 1 Key A",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )
    await create_api_key(
        session=async_session,
        name="Org 1 Key B",
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    # Create keys in second org
    await create_api_key(
        session=async_session,
        name="Org 2 Key A",
        organization_id=str(second_organization.id),
        created_by=str(second_org_user.id),
    )

    # List keys for org 1
    keys_org1, total_org1 = await get_api_keys_by_organization(
        session=async_session,
        organization_id=str(test_organization.id),
    )
    assert total_org1 == 2
    key_names_org1 = {k.name for k in keys_org1}
    assert "Org 1 Key A" in key_names_org1
    assert "Org 1 Key B" in key_names_org1
    assert "Org 2 Key A" not in key_names_org1

    # List keys for org 2
    keys_org2, total_org2 = await get_api_keys_by_organization(
        session=async_session,
        organization_id=str(second_organization.id),
    )
    assert total_org2 == 1
    key_names_org2 = {k.name for k in keys_org2}
    assert "Org 2 Key A" in key_names_org2
    assert "Org 1 Key A" not in key_names_org2


@pytest.mark.asyncio
async def test_cannot_update_other_org_key(
    async_session, test_organization, second_organization, test_user, second_org_user
):
    """Test that you cannot update an API key from another organization."""
    # Create key in org 2
    api_key_org2, _ = await create_api_key(
        session=async_session,
        name="Org 2 Key",
        organization_id=str(second_organization.id),
        created_by=str(second_org_user.id),
    )

    # Try to update from org 1 context
    with pytest.raises(ValueError, match="not found"):
        await update_api_key(
            session=async_session,
            api_key_id=str(api_key_org2.id),
            organization_id=str(test_organization.id),
            name="Hacked Name",
        )


@pytest.mark.asyncio
async def test_cannot_delete_other_org_key(
    async_session, test_organization, second_organization, test_user, second_org_user
):
    """Test that you cannot delete an API key from another organization."""
    # Create key in org 2
    api_key_org2, _ = await create_api_key(
        session=async_session,
        name="Org 2 Key",
        organization_id=str(second_organization.id),
        created_by=str(second_org_user.id),
    )

    # Try to delete from org 1 context
    with pytest.raises(ValueError, match="not found"):
        await delete_api_key(
            session=async_session,
            api_key_id=str(api_key_org2.id),
            organization_id=str(test_organization.id),
        )


@pytest.mark.asyncio
async def test_cannot_assign_permissions_to_other_org_key(
    async_session,
    test_organization,
    second_organization,
    test_user,
    second_org_user,
    standard_permissions,
):
    """Test that you cannot assign permissions to an API key from another organization."""
    # Create key in org 2
    api_key_org2, _ = await create_api_key(
        session=async_session,
        name="Org 2 Key",
        organization_id=str(second_organization.id),
        created_by=str(second_org_user.id),
    )

    # Try to assign permissions from org 1 context
    with pytest.raises(ValueError, match="not found"):
        await assign_permissions(
            session=async_session,
            api_key_id=str(api_key_org2.id),
            organization_id=str(test_organization.id),
            permissions=["users:read"],
        )


@pytest.mark.asyncio
async def test_same_name_allowed_in_different_orgs(
    async_session, test_organization, second_organization, test_user, second_org_user
):
    """Test that the same API key name can exist in different organizations."""
    name = "Shared Name Key"

    # Create key with same name in both orgs
    api_key_org1, _ = await create_api_key(
        session=async_session,
        name=name,
        organization_id=str(test_organization.id),
        created_by=str(test_user.id),
    )

    api_key_org2, _ = await create_api_key(
        session=async_session,
        name=name,
        organization_id=str(second_organization.id),
        created_by=str(second_org_user.id),
    )

    assert api_key_org1.name == name
    assert api_key_org2.name == name
    assert api_key_org1.id != api_key_org2.id
    assert api_key_org1.organization_id != api_key_org2.organization_id
