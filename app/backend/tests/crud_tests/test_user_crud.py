"""
Unit tests for user CRUD operations.
Tests user creation, retrieval, update, deletion, and tenant isolation.
"""

from uuid import uuid4

import pytest

from src.crud.user import (
    count_super_admins,
    create_user,
    delete_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_phone,
    get_users,
    get_users_cursor,
    get_users_enhanced,
    suspend_user,
    unsuspend_user,
    update_user,
    update_user_avatar,
)
from src.models.user import SuspensionStatus


# ============================================================================
# CREATE USER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_create_user_success(async_session, test_organization):
    """Test creating a user with valid data."""
    org_id = str(test_organization.id)

    user = await create_user(
        async_session,
        {"email": "newuser@test.com", "password": "Password123!"},
        org_id,
    )

    assert user.id is not None
    assert user.email == "newuser@test.com"
    assert user.organization_id == test_organization.id
    assert user.deleted_time is None
    assert user.suspension_status == SuspensionStatus.ACTIVE


@pytest.mark.asyncio
async def test_create_user_with_all_fields(async_session, test_organization):
    """Test creating a user with all optional fields."""
    org_id = str(test_organization.id)

    user = await create_user(
        async_session,
        {
            "email": "fulluser@test.com",
            "password": "Password123!",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "+12025551234",
            "is_admin": True,
            "email_verified": True,
            "phone_verified": True,
        },
        org_id,
    )

    assert user.email == "fulluser@test.com"
    assert user.first_name == "John"
    assert user.last_name == "Doe"
    assert user.phone == "+12025551234"
    assert user.is_admin is True
    assert user.email_verified is True
    assert user.phone_verified is True


@pytest.mark.asyncio
async def test_create_user_sso_no_password(async_session, test_organization):
    """Test creating an SSO user without password."""
    org_id = str(test_organization.id)

    user = await create_user(
        async_session,
        {
            "email": "ssouser@test.com",
            "password": None,
            "created_via": "google",
            "email_verified": True,
        },
        org_id,
    )

    assert user.email == "ssouser@test.com"
    assert user.password is None
    assert user.created_via.value == "google"


@pytest.mark.asyncio
async def test_create_user_duplicate_email_fails(async_session, test_organization):
    """Test creating a user with duplicate email in same organization fails."""
    org_id = str(test_organization.id)

    # Create first user
    await create_user(
        async_session,
        {"email": "duplicate@test.com", "password": "Password123!"},
        org_id,
    )

    # Try to create another user with same email
    with pytest.raises(ValueError, match="user with this email already exists"):
        await create_user(
            async_session,
            {"email": "duplicate@test.com", "password": "Password123!"},
            org_id,
        )


@pytest.mark.asyncio
async def test_create_user_normalizes_email_case(async_session, test_organization):
    """Email is stored lowercased/stripped so identity is case-insensitive."""
    org_id = str(test_organization.id)

    user = await create_user(
        async_session,
        {"email": "  MixedCase@Example.COM ", "password": "Password123!"},
        org_id,
    )

    assert user.email == "mixedcase@example.com"


@pytest.mark.asyncio
async def test_create_user_duplicate_email_case_insensitive(
    async_session, test_organization
):
    """A differently-cased duplicate of an existing email is rejected."""
    org_id = str(test_organization.id)

    await create_user(
        async_session,
        {"email": "person@test.com", "password": "Password123!"},
        org_id,
    )

    with pytest.raises(ValueError, match="user with this email already exists"):
        await create_user(
            async_session,
            {"email": "Person@Test.com", "password": "Password123!"},
            org_id,
        )


@pytest.mark.asyncio
async def test_get_user_by_email_case_insensitive(async_session, test_organization):
    """Lookups resolve regardless of the case used at registration or login."""
    org_id = str(test_organization.id)

    created = await create_user(
        async_session,
        {"email": "lookup@test.com", "password": "Password123!"},
        org_id,
    )

    found = await get_user_by_email(async_session, "LOOKUP@Test.COM", org_id)

    assert found is not None
    assert found.id == created.id


@pytest.mark.asyncio
async def test_create_user_same_email_different_org(
    async_session, test_organization, second_organization
):
    """Test creating users with same email in different organizations succeeds."""
    org1_id = str(test_organization.id)
    org2_id = str(second_organization.id)

    # Create user in first org
    user1 = await create_user(
        async_session,
        {"email": "shared@test.com", "password": "Password123!"},
        org1_id,
    )

    # Create user with same email in second org
    user2 = await create_user(
        async_session,
        {"email": "shared@test.com", "password": "Password123!"},
        org2_id,
    )

    assert user1.id != user2.id
    assert user1.organization_id == test_organization.id
    assert user2.organization_id == second_organization.id


@pytest.mark.asyncio
async def test_create_user_invalid_email(async_session, test_organization):
    """Test creating a user with invalid email fails validation."""
    org_id = str(test_organization.id)

    with pytest.raises(ValueError, match="Invalid input"):
        await create_user(
            async_session,
            {"email": "not-an-email", "password": "Password123!"},
            org_id,
        )


@pytest.mark.asyncio
async def test_create_user_weak_password(async_session, test_organization):
    """Test creating a user with weak password fails validation."""
    org_id = str(test_organization.id)

    with pytest.raises(ValueError, match="Invalid input"):
        await create_user(
            async_session,
            {"email": "user@test.com", "password": "weak"},
            org_id,
        )


# ============================================================================
# GET USER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_user_by_id_success(async_session, test_organization):
    """Test retrieving a user by ID."""
    org_id = str(test_organization.id)

    created_user = await create_user(
        async_session,
        {"email": "findme@test.com", "password": "Password123!"},
        org_id,
    )

    found_user = await get_user_by_id(async_session, str(created_user.id), org_id)

    assert found_user is not None
    assert found_user.id == created_user.id
    assert found_user.email == "findme@test.com"


@pytest.mark.asyncio
async def test_get_user_by_id_tenant_isolation(
    async_session, test_organization, second_organization
):
    """Test that users cannot be accessed across tenant boundaries."""
    org1_id = str(test_organization.id)
    org2_id = str(second_organization.id)

    # Create user in first org
    user = await create_user(
        async_session,
        {"email": "isolated@test.com", "password": "Password123!"},
        org1_id,
    )

    # Try to get user from second org - should return None
    result = await get_user_by_id(async_session, str(user.id), org2_id)
    assert result is None

    # Getting from correct org should work
    result = await get_user_by_id(async_session, str(user.id), org1_id)
    assert result is not None
    assert result.id == user.id


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(async_session, test_organization):
    """Test retrieving a non-existent user returns None."""
    org_id = str(test_organization.id)
    fake_id = str(uuid4())

    result = await get_user_by_id(async_session, fake_id, org_id)
    assert result is None


@pytest.mark.asyncio
async def test_get_user_by_email_success(async_session, test_organization):
    """Test retrieving a user by email."""
    org_id = str(test_organization.id)

    await create_user(
        async_session,
        {"email": "emailuser@test.com", "password": "Password123!"},
        org_id,
    )

    found_user = await get_user_by_email(async_session, "emailuser@test.com", org_id)

    assert found_user is not None
    assert found_user.email == "emailuser@test.com"


@pytest.mark.asyncio
async def test_get_user_by_email_tenant_isolation(
    async_session, test_organization, second_organization
):
    """Test that email lookup respects tenant isolation."""
    org1_id = str(test_organization.id)
    org2_id = str(second_organization.id)

    # Create user in first org
    await create_user(
        async_session,
        {"email": "emailiso@test.com", "password": "Password123!"},
        org1_id,
    )

    # Should not find in second org
    result = await get_user_by_email(async_session, "emailiso@test.com", org2_id)
    assert result is None

    # Should find in correct org
    result = await get_user_by_email(async_session, "emailiso@test.com", org1_id)
    assert result is not None


@pytest.mark.asyncio
async def test_get_user_by_phone_success(async_session, test_organization):
    """Test retrieving a user by phone number."""
    org_id = str(test_organization.id)

    await create_user(
        async_session,
        {
            "email": "phoneuser@test.com",
            "password": "Password123!",
            "phone": "+12025551234",
        },
        org_id,
    )

    found_user = await get_user_by_phone(async_session, "+12025551234", org_id)

    assert found_user is not None
    assert found_user.phone == "+12025551234"


@pytest.mark.asyncio
async def test_get_user_by_phone_exclude_user(async_session, test_organization):
    """Test phone lookup can exclude a specific user."""
    org_id = str(test_organization.id)

    user = await create_user(
        async_session,
        {
            "email": "phoneexclude@test.com",
            "password": "Password123!",
            "phone": "+12025559999",
        },
        org_id,
    )

    # Without exclusion, should find the user
    result = await get_user_by_phone(async_session, "+12025559999", org_id)
    assert result is not None

    # With exclusion, should not find any user
    result = await get_user_by_phone(
        async_session, "+12025559999", org_id, exclude_user_id=str(user.id)
    )
    assert result is None


# ============================================================================
# LIST USERS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_users_pagination(async_session, test_organization):
    """Test listing users with pagination."""
    org_id = str(test_organization.id)

    # Create 5 users
    for i in range(5):
        await create_user(
            async_session,
            {"email": f"listuser{i}@test.com", "password": "Password123!"},
            org_id,
        )

    # Get first page
    users, total = await get_users(async_session, org_id, limit=2, offset=0)

    assert total == 5
    assert len(users) == 2

    # Get second page
    users2, total2 = await get_users(async_session, org_id, limit=2, offset=2)

    assert total2 == 5
    assert len(users2) == 2

    # Ensure different users on different pages
    page1_ids = {u.id for u in users}
    page2_ids = {u.id for u in users2}
    assert page1_ids.isdisjoint(page2_ids)


@pytest.mark.asyncio
async def test_get_users_tenant_isolation(
    async_session, test_organization, second_organization
):
    """Test that listing users respects tenant boundaries."""
    org1_id = str(test_organization.id)
    org2_id = str(second_organization.id)

    # Create users in both orgs
    await create_user(
        async_session,
        {"email": "org1user@test.com", "password": "Password123!"},
        org1_id,
    )
    await create_user(
        async_session,
        {"email": "org2user@test.com", "password": "Password123!"},
        org2_id,
    )

    # List users in org1
    org1_users, org1_total = await get_users(async_session, org1_id)
    assert org1_total == 1
    assert all(u.organization_id == test_organization.id for u in org1_users)

    # List users in org2
    org2_users, org2_total = await get_users(async_session, org2_id)
    assert org2_total == 1
    assert all(u.organization_id == second_organization.id for u in org2_users)


@pytest.mark.asyncio
async def test_get_users_excludes_deleted(async_session, test_organization):
    """Test that listing users excludes soft-deleted users."""
    org_id = str(test_organization.id)

    # Create users
    user1 = await create_user(
        async_session,
        {"email": "active@test.com", "password": "Password123!"},
        org_id,
    )
    user2 = await create_user(
        async_session,
        {"email": "deleted@test.com", "password": "Password123!"},
        org_id,
    )

    # Delete one user
    await delete_user(async_session, str(user2.id), org_id)

    # List should only return active user
    users, total = await get_users(async_session, org_id)
    assert total == 1
    assert users[0].id == user1.id


# ============================================================================
# UPDATE USER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_update_user_success(async_session, test_organization):
    """Test updating a user."""
    org_id = str(test_organization.id)

    user = await create_user(
        async_session,
        {"email": "updateme@test.com", "password": "Password123!"},
        org_id,
    )

    updated = await update_user(
        async_session,
        {
            "id": str(user.id),
            "first_name": "Updated",
            "last_name": "Name",
        },
        org_id,
    )

    assert updated.first_name == "Updated"
    assert updated.last_name == "Name"


@pytest.mark.asyncio
async def test_update_user_password(async_session, test_organization):
    """Test updating user password."""
    org_id = str(test_organization.id)

    user = await create_user(
        async_session,
        {"email": "passwordupdate@test.com", "password": "Password123!"},
        org_id,
    )

    old_password = user.password

    updated = await update_user(
        async_session,
        {
            "id": str(user.id),
            "password": "NewPassword456!",
        },
        org_id,
    )

    assert updated.password != old_password


@pytest.mark.asyncio
async def test_update_user_tenant_isolation(
    async_session, test_organization, second_organization
):
    """Test that user updates respect tenant boundaries."""
    org1_id = str(test_organization.id)
    org2_id = str(second_organization.id)

    # Create user in first org
    user = await create_user(
        async_session,
        {"email": "updateiso@test.com", "password": "Password123!"},
        org1_id,
    )

    # Try to update from second org - should fail
    with pytest.raises(ValueError, match="not found"):
        await update_user(
            async_session,
            {
                "id": str(user.id),
                "first_name": "Hacked",
            },
            org2_id,
        )


@pytest.mark.asyncio
async def test_update_user_not_found(async_session, test_organization):
    """Test updating a non-existent user fails."""
    org_id = str(test_organization.id)
    fake_id = str(uuid4())

    with pytest.raises(ValueError, match="not found"):
        await update_user(
            async_session,
            {
                "id": fake_id,
                "first_name": "Ghost",
            },
            org_id,
        )


# ============================================================================
# DELETE USER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_delete_user_soft_delete(async_session, test_organization):
    """Test that user deletion is soft delete."""
    org_id = str(test_organization.id)

    user = await create_user(
        async_session,
        {"email": "deleteme@test.com", "password": "Password123!"},
        org_id,
    )

    deleted_user = await delete_user(async_session, str(user.id), org_id)

    assert deleted_user.deleted_time is not None
    assert deleted_user.id == user.id

    # User should no longer appear in normal queries
    result = await get_user_by_id(async_session, str(user.id), org_id)
    assert result is None


@pytest.mark.asyncio
async def test_delete_user_tenant_isolation(
    async_session, test_organization, second_organization
):
    """Test that user deletion respects tenant boundaries."""
    org1_id = str(test_organization.id)
    org2_id = str(second_organization.id)

    # Create user in first org
    user = await create_user(
        async_session,
        {"email": "deleteiso@test.com", "password": "Password123!"},
        org1_id,
    )

    # Try to delete from second org - should fail
    with pytest.raises(ValueError, match="not found"):
        await delete_user(async_session, str(user.id), org2_id)

    # User should still exist
    result = await get_user_by_id(async_session, str(user.id), org1_id)
    assert result is not None


@pytest.mark.asyncio
async def test_delete_user_not_found(async_session, test_organization):
    """Test deleting a non-existent user fails."""
    org_id = str(test_organization.id)
    fake_id = str(uuid4())

    with pytest.raises(ValueError, match="not found"):
        await delete_user(async_session, fake_id, org_id)


# ============================================================================
# SUSPEND/UNSUSPEND USER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_suspend_user_success(async_session, test_organization):
    """Test suspending a user."""
    org_id = str(test_organization.id)

    admin = await create_user(
        async_session,
        {"email": "admin@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )
    user = await create_user(
        async_session,
        {"email": "tosuspend@test.com", "password": "Password123!"},
        org_id,
    )

    suspended = await suspend_user(
        async_session,
        str(user.id),
        org_id,
        str(admin.id),
        reason="Policy violation",
    )

    assert suspended.suspension_status == SuspensionStatus.SUSPENDED
    assert suspended.suspended_time is not None
    assert suspended.suspended_by == admin.id
    assert suspended.suspension_reason == "Policy violation"


@pytest.mark.asyncio
async def test_suspend_user_tenant_isolation(
    async_session, test_organization, second_organization
):
    """Test that user suspension respects tenant boundaries."""
    org1_id = str(test_organization.id)
    org2_id = str(second_organization.id)

    admin = await create_user(
        async_session,
        {"email": "admin@test.com", "password": "Password123!", "is_admin": True},
        org1_id,
    )
    user = await create_user(
        async_session,
        {"email": "suspendiso@test.com", "password": "Password123!"},
        org1_id,
    )

    # Try to suspend from second org - should fail
    with pytest.raises(ValueError, match="not found"):
        await suspend_user(
            async_session,
            str(user.id),
            org2_id,
            str(admin.id),
        )


@pytest.mark.asyncio
async def test_unsuspend_user_success(async_session, test_organization):
    """Test unsuspending a user."""
    org_id = str(test_organization.id)

    admin = await create_user(
        async_session,
        {"email": "admin2@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )
    user = await create_user(
        async_session,
        {"email": "tounsuspend@test.com", "password": "Password123!"},
        org_id,
    )

    # Suspend first
    await suspend_user(async_session, str(user.id), org_id, str(admin.id))

    # Unsuspend
    unsuspended = await unsuspend_user(async_session, str(user.id), org_id)

    assert unsuspended.suspension_status == SuspensionStatus.ACTIVE
    assert unsuspended.suspended_time is None
    assert unsuspended.suspended_by is None
    assert unsuspended.suspension_reason is None


# ============================================================================
# AVATAR TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_update_user_avatar(async_session, test_organization):
    """Test updating user avatar."""
    org_id = str(test_organization.id)

    user = await create_user(
        async_session,
        {"email": "avatar@test.com", "password": "Password123!"},
        org_id,
    )

    # Update avatar (using a random UUID for testing - normally would be a File ID)
    avatar_id = str(uuid4())
    updated = await update_user_avatar(async_session, str(user.id), org_id, avatar_id)

    assert str(updated.avatar_file_id) == avatar_id


@pytest.mark.asyncio
async def test_update_user_avatar_to_none(async_session, test_organization):
    """Test removing user avatar."""
    org_id = str(test_organization.id)

    user = await create_user(
        async_session,
        {"email": "noavatar@test.com", "password": "Password123!"},
        org_id,
    )

    # First set an avatar
    avatar_id = str(uuid4())
    await update_user_avatar(async_session, str(user.id), org_id, avatar_id)

    # Then remove it
    updated = await update_user_avatar(async_session, str(user.id), org_id, None)

    assert updated.avatar_file_id is None


# ============================================================================
# COUNT SUPER ADMINS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_count_super_admins(async_session, test_organization):
    """Test counting super admins in organization."""
    org_id = str(test_organization.id)

    # Create regular user and admin
    await create_user(
        async_session,
        {"email": "regular@test.com", "password": "Password123!"},
        org_id,
    )
    await create_user(
        async_session,
        {"email": "superadmin1@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )
    await create_user(
        async_session,
        {"email": "superadmin2@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )

    count = await count_super_admins(async_session, org_id)
    assert count == 2


@pytest.mark.asyncio
async def test_count_super_admins_exclude_user(async_session, test_organization):
    """Test counting super admins with exclusion."""
    org_id = str(test_organization.id)

    admin1 = await create_user(
        async_session,
        {"email": "admin1exc@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )
    await create_user(
        async_session,
        {"email": "admin2exc@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )

    # Count excluding admin1
    count = await count_super_admins(
        async_session, org_id, exclude_user_id=str(admin1.id)
    )
    assert count == 1


# ============================================================================
# ENHANCED LISTING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_users_enhanced_with_filters(async_session, test_organization):
    """Test enhanced user listing with filters."""
    org_id = str(test_organization.id)

    # Create users with different statuses
    await create_user(
        async_session,
        {"email": "active1@test.com", "password": "Password123!"},
        org_id,
    )
    user2 = await create_user(
        async_session,
        {"email": "tosuspend2@test.com", "password": "Password123!"},
        org_id,
    )
    admin = await create_user(
        async_session,
        {"email": "admin3@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )

    # Suspend user2
    await suspend_user(async_session, str(user2.id), org_id, str(admin.id))

    # Filter by active status
    users, total, _, _, _ = await get_users_enhanced(
        async_session,
        org_id,
        filter_status="active",
    )

    assert total == 2  # active1 and admin3


@pytest.mark.asyncio
async def test_get_users_enhanced_with_search(async_session, test_organization):
    """Test enhanced user listing with search."""
    org_id = str(test_organization.id)

    await create_user(
        async_session,
        {
            "email": "john.doe@test.com",
            "password": "Password123!",
            "first_name": "John",
            "last_name": "Doe",
        },
        org_id,
    )
    await create_user(
        async_session,
        {
            "email": "jane.smith@test.com",
            "password": "Password123!",
            "first_name": "Jane",
            "last_name": "Smith",
        },
        org_id,
    )

    # Search for "john"
    users, total, _, _, _ = await get_users_enhanced(
        async_session,
        org_id,
        search="john",
    )

    assert total == 1
    assert users[0].first_name == "John"


@pytest.mark.asyncio
async def test_get_users_enhanced_with_sort(async_session, test_organization):
    """Test enhanced user listing with sorting."""
    org_id = str(test_organization.id)

    await create_user(
        async_session,
        {"email": "zuser@test.com", "password": "Password123!"},
        org_id,
    )
    await create_user(
        async_session,
        {"email": "auser@test.com", "password": "Password123!"},
        org_id,
    )

    # Sort by email ascending
    users, _, _, _, _ = await get_users_enhanced(
        async_session,
        org_id,
        sort="email:asc",
    )

    assert users[0].email == "auser@test.com"
    assert users[1].email == "zuser@test.com"


@pytest.mark.asyncio
async def test_get_users_cursor_pagination(async_session, test_organization):
    """Test cursor-based user pagination."""
    org_id = str(test_organization.id)

    # Create users
    for i in range(5):
        await create_user(
            async_session,
            {"email": f"cursoruser{i}@test.com", "password": "Password123!"},
            org_id,
        )

    # Get first page
    users, total, _, _, _, next_cursor = await get_users_cursor(
        async_session,
        org_id,
        limit=2,
    )

    assert total == 5
    assert len(users) == 2
    assert next_cursor is not None

    # Get second page using cursor
    users2, _, _, _, _, _ = await get_users_cursor(
        async_session,
        org_id,
        limit=2,
        cursor=next_cursor,
    )

    assert len(users2) == 2

    # Ensure different users on different pages
    page1_ids = {u.id for u in users}
    page2_ids = {u.id for u in users2}
    assert page1_ids.isdisjoint(page2_ids)
