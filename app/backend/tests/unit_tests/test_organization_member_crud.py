"""
Unit tests for organization member CRUD operations.
Migrated to async patterns for FastAPI/SQLAlchemy.
"""

import uuid

import pytest


@pytest.mark.asyncio
async def test_get_organization_members(async_session, test_organization):
    """Test retrieving all members of an organization."""
    from src.crud.organization_member import get_organization_members
    from src.crud.user import create_user

    org_id = str(test_organization.id)

    # Create multiple users in the organization
    await create_user(
        async_session,
        {"email": "user1@test.com", "password": "Password123!", "email_verified": True},
        org_id,
    )

    await create_user(
        async_session,
        {"email": "user2@test.com", "password": "Password123!", "email_verified": True},
        org_id,
    )

    await create_user(
        async_session,
        {"email": "user3@test.com", "password": "Password123!", "email_verified": True},
        org_id,
    )

    # Get organization members
    members, total = await get_organization_members(async_session, org_id)

    assert total == 3
    assert len(members) == 3

    member_emails = [m.email for m in members]
    assert "user1@test.com" in member_emails
    assert "user2@test.com" in member_emails
    assert "user3@test.com" in member_emails


@pytest.mark.asyncio
async def test_get_organization_members_with_pagination(
    async_session, test_organization
):
    """Test pagination when retrieving organization members."""
    from src.crud.organization_member import get_organization_members
    from src.crud.user import create_user

    org_id = str(test_organization.id)

    # Create 5 users
    for i in range(5):
        await create_user(
            async_session,
            {
                "email": f"user{i}@test.com",
                "password": "Password123!",
                "email_verified": True,
            },
            org_id,
        )

    # Get first 2 members
    members, total = await get_organization_members(
        async_session, org_id, limit=2, offset=0
    )

    assert total == 5
    assert len(members) == 2

    # Get next 2 members
    members, total = await get_organization_members(
        async_session, org_id, limit=2, offset=2
    )

    assert total == 5
    assert len(members) == 2


@pytest.mark.asyncio
async def test_get_organization_members_excludes_deleted(
    async_session, test_organization
):
    """Test that soft-deleted users are excluded from member list."""
    from src.crud.organization_member import get_organization_members
    from src.crud.user import create_user, delete_user

    org_id = str(test_organization.id)

    # Create users
    user1 = await create_user(
        async_session,
        {"email": "user1@test.com", "password": "Password123!", "email_verified": True},
        org_id,
    )

    await create_user(
        async_session,
        {"email": "user2@test.com", "password": "Password123!", "email_verified": True},
        org_id,
    )

    # Soft delete user1
    await delete_user(async_session, str(user1.id), org_id)

    # Get members
    members, total = await get_organization_members(async_session, org_id)

    assert total == 1
    assert len(members) == 1
    assert members[0].email == "user2@test.com"


@pytest.mark.asyncio
async def test_get_organization_members_only_from_org(
    async_session, test_organization, second_organization
):
    """Test that only members from specified organization are returned."""
    from src.crud.organization_member import get_organization_members
    from src.crud.user import create_user

    org1_id = str(test_organization.id)
    org2_id = str(second_organization.id)

    # Create users in org 1
    await create_user(
        async_session,
        {
            "email": "user1_org1@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        org1_id,
    )

    await create_user(
        async_session,
        {
            "email": "user2_org1@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        org1_id,
    )

    # Create users in org 2
    await create_user(
        async_session,
        {
            "email": "user1_org2@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        org2_id,
    )

    # Get org 1 members
    members_org1, total_org1 = await get_organization_members(async_session, org1_id)

    assert total_org1 == 2
    member_emails_org1 = [m.email for m in members_org1]
    assert "user1_org1@test.com" in member_emails_org1
    assert "user2_org1@test.com" in member_emails_org1
    assert "user1_org2@test.com" not in member_emails_org1

    # Get org 2 members
    members_org2, total_org2 = await get_organization_members(async_session, org2_id)

    assert total_org2 == 1
    assert members_org2[0].email == "user1_org2@test.com"


@pytest.mark.asyncio
async def test_remove_user_from_organization(async_session, test_organization):
    """Test removing a user from an organization (soft delete)."""
    from src.crud.organization_member import remove_user_from_organization
    from src.crud.user import create_user, get_user_by_id

    org_id = str(test_organization.id)

    # Create user
    user = await create_user(
        async_session,
        {
            "email": "toremove@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        org_id,
    )

    user_id = str(user.id)

    # Verify user exists
    assert await get_user_by_id(async_session, user_id, org_id) is not None

    # Remove user
    removed_user = await remove_user_from_organization(async_session, user_id, org_id)

    assert removed_user is not None
    assert removed_user.deleted_time is not None
    assert removed_user.email == "toremove@test.com"

    # Verify user is soft deleted (not found in normal queries)
    assert await get_user_by_id(async_session, user_id, org_id) is None


@pytest.mark.asyncio
async def test_remove_user_from_organization_not_found(
    async_session, test_organization
):
    """Test removing a user that doesn't exist raises ValueError."""
    from src.crud.organization_member import remove_user_from_organization

    org_id = str(test_organization.id)
    fake_user_id = str(uuid.uuid4())

    # Try to remove non-existent user
    with pytest.raises(ValueError) as exc_info:
        await remove_user_from_organization(async_session, fake_user_id, org_id)

    assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_remove_user_from_wrong_organization(
    async_session, test_organization, second_organization
):
    """Test removing a user using wrong organization_id fails."""
    from src.crud.organization_member import remove_user_from_organization
    from src.crud.user import create_user

    org1_id = str(test_organization.id)
    org2_id = str(second_organization.id)

    # Create user in org 1
    user = await create_user(
        async_session,
        {
            "email": "user_org1@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        org1_id,
    )

    # Try to remove user using org 2's id
    with pytest.raises(ValueError) as exc_info:
        await remove_user_from_organization(async_session, str(user.id), org2_id)

    assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_get_organization_member_count(async_session, test_organization):
    """Test getting the count of active members in an organization."""
    from src.crud.organization_member import get_organization_member_count
    from src.crud.user import create_user

    org_id = str(test_organization.id)

    # Initially no members
    count = await get_organization_member_count(async_session, org_id)
    assert count == 0

    # Create users
    for i in range(3):
        await create_user(
            async_session,
            {
                "email": f"user{i}@test.com",
                "password": "Password123!",
                "email_verified": True,
            },
            org_id,
        )

    # Get count
    count = await get_organization_member_count(async_session, org_id)
    assert count == 3


@pytest.mark.asyncio
async def test_get_organization_member_count_excludes_deleted(
    async_session, test_organization
):
    """Test that member count excludes soft-deleted users."""
    from src.crud.organization_member import get_organization_member_count
    from src.crud.user import create_user, delete_user

    org_id = str(test_organization.id)

    # Create users
    user1 = await create_user(
        async_session,
        {"email": "user1@test.com", "password": "Password123!", "email_verified": True},
        org_id,
    )

    await create_user(
        async_session,
        {"email": "user2@test.com", "password": "Password123!", "email_verified": True},
        org_id,
    )

    await create_user(
        async_session,
        {"email": "user3@test.com", "password": "Password123!", "email_verified": True},
        org_id,
    )

    # Count should be 3
    count = await get_organization_member_count(async_session, org_id)
    assert count == 3

    # Soft delete one user
    await delete_user(async_session, str(user1.id), org_id)

    # Count should now be 2
    count = await get_organization_member_count(async_session, org_id)
    assert count == 2


@pytest.mark.asyncio
async def test_get_organization_member_count_separate_orgs(
    async_session, test_organization, second_organization
):
    """Test that member count is correctly scoped to organization."""
    from src.crud.organization_member import get_organization_member_count
    from src.crud.user import create_user

    org1_id = str(test_organization.id)
    org2_id = str(second_organization.id)

    # Create users in org 1
    for i in range(2):
        await create_user(
            async_session,
            {
                "email": f"user{i}_org1@test.com",
                "password": "Password123!",
                "email_verified": True,
            },
            org1_id,
        )

    # Create users in org 2
    for i in range(5):
        await create_user(
            async_session,
            {
                "email": f"user{i}_org2@test.com",
                "password": "Password123!",
                "email_verified": True,
            },
            org2_id,
        )

    # Get counts
    count_org1 = await get_organization_member_count(async_session, org1_id)
    count_org2 = await get_organization_member_count(async_session, org2_id)

    assert count_org1 == 2
    assert count_org2 == 5
