"""
Unit tests for user CRUD operations.
Migrated to async patterns for FastAPI/SQLAlchemy.
"""

import pytest

from src.core.security import verify_password
from src.crud.user import (
    create_user,
    delete_user,
    get_user_by_email,
    get_user_by_id,
    update_user,
)


@pytest.mark.asyncio
async def test_create_user(async_session, test_organization):
    """Test creating a user."""
    org_id = str(test_organization.id)

    user_data = {
        "email": "newuser@test.com",
        "password": "Password123!",
        "email_verified": True,
        "phone": "+27737442554",
        "phone_verified": True,
        "first_name": "New",
        "last_name": "User",
        "is_admin": False,
    }

    user = await create_user(
        session=async_session, request=user_data, organization_id=org_id
    )

    assert user is not None
    assert user.email == "newuser@test.com"
    assert verify_password("Password123!", user.password)
    assert user.email_verified is True
    assert user.phone == "+27737442554"
    assert user.phone_verified is True
    assert user.first_name == "New"
    assert user.last_name == "User"
    assert user.is_admin is False
    assert str(user.organization_id) == org_id


@pytest.mark.asyncio
async def test_get_user_by_id(async_session, test_user, test_organization):
    """Test getting a user by ID."""
    org_id = str(test_organization.id)

    user = await get_user_by_id(
        session=async_session, user_id=str(test_user.id), organization_id=org_id
    )

    assert user is not None
    assert user.id == test_user.id
    assert user.email == test_user.email


@pytest.mark.asyncio
async def test_get_user_by_email(async_session, test_user, test_organization):
    """Test getting a user by email."""
    org_id = str(test_organization.id)

    user = await get_user_by_email(
        session=async_session, email=test_user.email, organization_id=org_id
    )

    assert user is not None
    assert user.id == test_user.id
    assert user.email == test_user.email


@pytest.mark.asyncio
async def test_update_user(async_session, test_user, test_organization):
    """Test updating a user."""
    org_id = str(test_organization.id)

    update_data = {
        "id": str(test_user.id),
        "first_name": "Updated",
        "last_name": "Name",
    }

    updated_user = await update_user(
        session=async_session, request=update_data, organization_id=org_id
    )

    assert updated_user is not None
    assert updated_user.id == test_user.id
    assert updated_user.first_name == "Updated"
    assert updated_user.last_name == "Name"
    assert updated_user.email == test_user.email  # Email should not change


@pytest.mark.asyncio
async def test_delete_user(async_session, test_user, test_organization):
    """Test deleting a user."""
    org_id = str(test_organization.id)

    deleted_user = await delete_user(
        session=async_session, user_id=str(test_user.id), organization_id=org_id
    )

    assert deleted_user is not None
    assert deleted_user.id == test_user.id
    assert deleted_user.deleted_time is not None

    # Try to get the user again, should return None since it's deleted
    user = await get_user_by_id(
        session=async_session, user_id=str(test_user.id), organization_id=org_id
    )
    assert user is None


@pytest.mark.asyncio
async def test_user_password_validation(async_session, test_user, test_organization):
    """Test validating a user's password."""
    org_id = str(test_organization.id)

    # Get the user
    user = await get_user_by_id(
        session=async_session, user_id=str(test_user.id), organization_id=org_id
    )

    # Check if the password is correct (the test fixture uses hash_password)
    assert verify_password("Password123!", user.password)

    # Check if an incorrect password fails
    assert not verify_password("wrong_password", user.password)


@pytest.mark.asyncio
async def test_user_email_verification(async_session, test_organization):
    """Test user email verification."""
    org_id = str(test_organization.id)

    # Create a user with unverified email
    user_data = {
        "email": "unverified@test.com",
        "password": "Password123!",
        "email_verified": False,
    }

    user = await create_user(
        session=async_session, request=user_data, organization_id=org_id
    )

    assert user is not None
    assert user.email_verified is False

    # Update the user to verify the email
    update_data = {"id": str(user.id), "email_verified": True}

    updated_user = await update_user(
        session=async_session, request=update_data, organization_id=org_id
    )

    assert updated_user is not None
    assert updated_user.email_verified is True


@pytest.mark.asyncio
async def test_user_admin_flag(async_session, test_organization):
    """Test setting a user as an admin."""
    org_id = str(test_organization.id)

    # Create a regular user
    user_data = {
        "email": "regular@test.com",
        "password": "Password123!",
        "is_admin": False,
    }

    user = await create_user(
        session=async_session, request=user_data, organization_id=org_id
    )

    assert user is not None
    assert user.is_admin is False

    # Update the user to make them an admin
    update_data = {"id": str(user.id), "is_admin": True}

    updated_user = await update_user(
        session=async_session, request=update_data, organization_id=org_id
    )

    assert updated_user is not None
    assert updated_user.is_admin is True


@pytest.mark.asyncio
async def test_create_duplicate_user(async_session, test_user, test_organization):
    """Test that creating a duplicate user fails."""
    org_id = str(test_organization.id)

    user_data = {
        "email": test_user.email,  # Same email as existing user
        "password": "Password123!",
    }

    with pytest.raises(ValueError, match="already exists"):
        await create_user(
            session=async_session, request=user_data, organization_id=org_id
        )


@pytest.mark.asyncio
async def test_get_nonexistent_user(async_session, test_organization):
    """Test getting a user that doesn't exist."""
    import uuid

    org_id = str(test_organization.id)
    fake_id = str(uuid.uuid4())

    user = await get_user_by_id(
        session=async_session, user_id=fake_id, organization_id=org_id
    )

    assert user is None
