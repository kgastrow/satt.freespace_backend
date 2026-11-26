"""
Unit tests for onboarding models.
Tests model creation and basic validation.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from src import crud
from src.models.onboarding_step import OnboardingStep
from src.models.phone_verification import PhoneVerification
from src.models.user_onboarding_progress import UserOnboardingProgress
from src.models.user_type import UserType
from src.models.user_user_type import OnboardingStatus, UserUserType
from src.services.onboarding import onboarding_service
from src.services.phone_verification import phone_verification_service


@pytest.mark.asyncio
async def test_create_user_type(async_session):
    """Test creating a UserType (global model)."""
    user_type = UserType(
        name="Individual",
        code="individual",
        description="Individual user account",
        is_active=True,
        requires_onboarding=True,
        requires_manual_review=False,
        is_default=True,
        display_order=1,
    )
    async_session.add(user_type)
    await async_session.commit()

    result = await async_session.execute(
        select(UserType).where(UserType.code == "individual")
    )
    retrieved = result.scalar_one_or_none()

    assert retrieved is not None
    assert retrieved.name == "Individual"
    assert retrieved.code == "individual"
    assert retrieved.is_active is True
    assert retrieved.requires_onboarding is True
    assert retrieved.requires_manual_review is False
    assert retrieved.is_default is True
    assert retrieved.display_order == 1
    assert retrieved.deleted_time is None


@pytest.mark.asyncio
async def test_create_user_user_type(async_session, test_organization, test_user):
    """Test creating a UserUserType (tenant-scoped junction)."""
    user_type = UserType(
        name="Business",
        code="business",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    user_user_type = UserUserType(
        organization_id=test_organization.id,
        user_id=test_user.id,
        user_type_id=user_type.id,
        onboarding_status=OnboardingStatus.PENDING,
    )
    async_session.add(user_user_type)
    await async_session.commit()

    result = await async_session.execute(
        select(UserUserType).where(
            UserUserType.user_id == test_user.id,
            UserUserType.organization_id == test_organization.id,
        )
    )
    retrieved = result.scalar_one_or_none()

    assert retrieved is not None
    assert retrieved.user_id == test_user.id
    assert retrieved.user_type_id == user_type.id
    assert retrieved.organization_id == test_organization.id
    assert retrieved.onboarding_status == OnboardingStatus.PENDING
    assert retrieved.onboarded_at is None
    assert retrieved.deleted_time is None


@pytest.mark.asyncio
async def test_create_onboarding_step(async_session):
    """Test creating an OnboardingStep (global model)."""
    user_type = UserType(
        name="Provider",
        code="provider",
        requires_onboarding=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    onboarding_step = OnboardingStep(
        user_type_id=user_type.id,
        name="Personal Information",
        code="personal_info",
        description="Provide your personal details",
        step_order=1,
        required_fields={
            "first_name": "string",
            "last_name": "string",
            "phone": "string",
        },
        validation_rules={"phone": {"pattern": "^\\+?[1-9]\\d{1,14}$"}},
        requires_verification=True,
        is_active=True,
    )
    async_session.add(onboarding_step)
    await async_session.commit()

    result = await async_session.execute(
        select(OnboardingStep).where(OnboardingStep.code == "personal_info")
    )
    retrieved = result.scalar_one_or_none()

    assert retrieved is not None
    assert retrieved.name == "Personal Information"
    assert retrieved.code == "personal_info"
    assert retrieved.user_type_id == user_type.id
    assert retrieved.step_order == 1
    assert retrieved.required_fields == {
        "first_name": "string",
        "last_name": "string",
        "phone": "string",
    }
    assert retrieved.validation_rules == {"phone": {"pattern": "^\\+?[1-9]\\d{1,14}$"}}
    assert retrieved.requires_verification is True
    assert retrieved.is_active is True
    assert retrieved.deleted_time is None


@pytest.mark.asyncio
async def test_create_user_onboarding_progress(
    async_session, test_organization, test_user
):
    """Test creating UserOnboardingProgress (tenant-scoped)."""
    user_type = UserType(name="Individual", code="individual", requires_onboarding=True)
    async_session.add(user_type)
    await async_session.commit()

    user_user_type = UserUserType(
        organization_id=test_organization.id,
        user_id=test_user.id,
        user_type_id=user_type.id,
        onboarding_status=OnboardingStatus.IN_PROGRESS,
    )
    async_session.add(user_user_type)
    await async_session.commit()

    onboarding_step = OnboardingStep(
        user_type_id=user_type.id,
        name="Basic Info",
        code="basic_info",
        step_order=1,
        required_fields={"email": "string"},
    )
    async_session.add(onboarding_step)
    await async_session.commit()

    progress = UserOnboardingProgress(
        organization_id=test_organization.id,
        user_id=test_user.id,
        user_user_type_id=user_user_type.id,
        onboarding_step_id=onboarding_step.id,
        submitted_data={"email": "test@example.com"},
        completed_time=datetime.now(timezone.utc),
    )
    async_session.add(progress)
    await async_session.commit()

    result = await async_session.execute(
        select(UserOnboardingProgress).where(
            UserOnboardingProgress.user_id == test_user.id,
            UserOnboardingProgress.organization_id == test_organization.id,
        )
    )
    retrieved = result.scalar_one_or_none()

    assert retrieved is not None
    assert retrieved.user_id == test_user.id
    assert retrieved.organization_id == test_organization.id
    assert retrieved.user_user_type_id == user_user_type.id
    assert retrieved.onboarding_step_id == onboarding_step.id
    assert retrieved.submitted_data == {"email": "test@example.com"}
    assert retrieved.completed_time is not None
    assert retrieved.deleted_time is None


@pytest.mark.asyncio
async def test_create_phone_verification(async_session, test_organization, test_user):
    """Test creating PhoneVerification (tenant-scoped)."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    phone_verification = PhoneVerification(
        organization_id=test_organization.id,
        user_id=test_user.id,
        phone="+1234567890",
        otp_hash="$2b$12$hashed_otp_value",
        expires_at=expires_at,
        verified=False,
        attempts_count=0,
    )
    async_session.add(phone_verification)
    await async_session.commit()

    result = await async_session.execute(
        select(PhoneVerification).where(
            PhoneVerification.user_id == test_user.id,
            PhoneVerification.organization_id == test_organization.id,
        )
    )
    retrieved = result.scalar_one_or_none()

    assert retrieved is not None
    assert retrieved.user_id == test_user.id
    assert retrieved.organization_id == test_organization.id
    assert retrieved.phone == "+1234567890"
    assert retrieved.otp_hash == "$2b$12$hashed_otp_value"
    assert retrieved.verified is False
    assert retrieved.attempts_count == 0
    assert retrieved.deleted_time is None


@pytest.mark.asyncio
async def test_onboarding_status_enum():
    """Test OnboardingStatus enum values."""
    assert OnboardingStatus.PENDING == "pending"
    assert OnboardingStatus.IN_PROGRESS == "in_progress"
    assert OnboardingStatus.PENDING_REVIEW == "pending_review"
    assert OnboardingStatus.APPROVED == "approved"
    assert OnboardingStatus.REJECTED == "rejected"


# CRUD Tests


@pytest.mark.asyncio
async def test_crud_user_type_create_and_get(async_session):
    """Test creating and retrieving a user type via CRUD."""
    data = {
        "name": "Test Type",
        "code": "test_type",
        "description": "A test user type",
        "is_active": True,
        "requires_onboarding": True,
        "requires_manual_review": False,
        "is_default": False,
        "display_order": 5,
    }

    user_type = await crud.create_user_type(async_session, data)
    assert user_type.code == "test_type"
    assert user_type.name == "Test Type"

    retrieved = await crud.get_user_type_by_id(async_session, str(user_type.id))
    assert retrieved is not None
    assert retrieved.id == user_type.id

    retrieved_by_code = await crud.get_user_type_by_code(async_session, "test_type")
    assert retrieved_by_code is not None
    assert retrieved_by_code.id == user_type.id


@pytest.mark.asyncio
async def test_crud_user_type_get_all(async_session):
    """Test getting all user types."""
    data1 = {"name": "Type 1", "code": "type1", "display_order": 1}
    data2 = {"name": "Type 2", "code": "type2", "display_order": 2}

    await crud.create_user_type(async_session, data1)
    await crud.create_user_type(async_session, data2)

    user_types, total = await crud.get_all_user_types(async_session, limit=10, offset=0)
    assert total >= 2
    assert len(user_types) >= 2


@pytest.mark.asyncio
async def test_crud_user_type_update(async_session):
    """Test updating a user type."""
    data = {"name": "Original", "code": "original"}
    user_type = await crud.create_user_type(async_session, data)

    update_data = {"name": "Updated Name"}
    updated = await crud.update_user_type(async_session, str(user_type.id), update_data)
    assert updated.name == "Updated Name"
    assert updated.code == "original"


@pytest.mark.asyncio
async def test_crud_user_type_soft_delete(async_session):
    """Test soft deleting a user type."""
    data = {"name": "To Delete", "code": "to_delete"}
    user_type = await crud.create_user_type(async_session, data)

    deleted = await crud.soft_delete_user_type(async_session, str(user_type.id))
    assert deleted.deleted_time is not None

    retrieved = await crud.get_user_type_by_id(async_session, str(user_type.id))
    assert retrieved is None


@pytest.mark.asyncio
async def test_crud_user_user_type_create(async_session, test_organization, test_user):
    """Test creating a user-user type association via CRUD."""
    user_type_data = {"name": "Business", "code": "business"}
    user_type = await crud.create_user_type(async_session, user_type_data)

    data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    user_user_type = await crud.create_user_user_type(
        async_session, data, str(test_organization.id)
    )

    assert user_user_type.user_id == test_user.id
    assert user_user_type.user_type_id == user_type.id
    assert user_user_type.organization_id == test_organization.id
    assert user_user_type.onboarding_status == OnboardingStatus.PENDING


@pytest.mark.asyncio
async def test_crud_user_user_type_get_by_user_and_type(
    async_session, test_organization, test_user
):
    """Test getting user-user type by user and type."""
    user_type_data = {"name": "Individual", "code": "individual"}
    user_type = await crud.create_user_type(async_session, user_type_data)

    data = {"user_id": str(test_user.id), "user_type_id": str(user_type.id)}
    created = await crud.create_user_user_type(
        async_session, data, str(test_organization.id)
    )

    retrieved = await crud.get_by_user_and_type(
        async_session,
        str(test_user.id),
        str(user_type.id),
        str(test_organization.id),
    )
    assert retrieved is not None
    assert retrieved.id == created.id


@pytest.mark.asyncio
async def test_crud_user_user_type_update_status(
    async_session, test_organization, test_user
):
    """Test updating user-user type onboarding status."""
    user_type_data = {"name": "Provider", "code": "provider"}
    user_type = await crud.create_user_type(async_session, user_type_data)

    data = {"user_id": str(test_user.id), "user_type_id": str(user_type.id)}
    user_user_type = await crud.create_user_user_type(
        async_session, data, str(test_organization.id)
    )

    updated = await crud.update_user_user_type_status(
        async_session,
        str(user_user_type.id),
        OnboardingStatus.APPROVED,
        str(test_organization.id),
        onboarded_at=datetime.now(timezone.utc),
    )
    assert updated.onboarding_status == OnboardingStatus.APPROVED
    assert updated.onboarded_at is not None


@pytest.mark.asyncio
async def test_crud_user_user_type_tenant_isolation(
    async_session, test_organization, test_user, second_organization
):
    """Test that user-user types are properly isolated by organization."""
    user_type_data = {"name": "Business", "code": "business_iso"}
    user_type = await crud.create_user_type(async_session, user_type_data)

    data = {"user_id": str(test_user.id), "user_type_id": str(user_type.id)}
    await crud.create_user_user_type(async_session, data, str(test_organization.id))

    # Try to retrieve from different organization - should return None
    retrieved = await crud.get_by_user_and_type(
        async_session,
        str(test_user.id),
        str(user_type.id),
        str(second_organization.id),
    )
    assert retrieved is None


@pytest.mark.asyncio
async def test_crud_onboarding_step_create(async_session):
    """Test creating an onboarding step via CRUD."""
    user_type_data = {"name": "Individual", "code": "individual_step"}
    user_type = await crud.create_user_type(async_session, user_type_data)

    data = {
        "user_type_id": str(user_type.id),
        "name": "Personal Info",
        "code": "personal_info",
        "step_order": 1,
        "required_fields": {"first_name": "string", "last_name": "string"},
        "validation_rules": {"first_name": {"min_length": 1}},
        "requires_verification": False,
        "is_active": True,
    }
    step = await crud.create_onboarding_step(async_session, data)
    assert step.code == "personal_info"
    assert step.step_order == 1


@pytest.mark.asyncio
async def test_crud_onboarding_step_get_all_for_user_type(async_session):
    """Test getting all steps for a user type."""
    user_type_data = {"name": "Business", "code": "business_steps"}
    user_type = await crud.create_user_type(async_session, user_type_data)

    step1_data = {
        "user_type_id": str(user_type.id),
        "name": "Step 1",
        "code": "step1",
        "step_order": 1,
    }
    step2_data = {
        "user_type_id": str(user_type.id),
        "name": "Step 2",
        "code": "step2",
        "step_order": 2,
    }
    await crud.create_onboarding_step(async_session, step1_data)
    await crud.create_onboarding_step(async_session, step2_data)

    steps = await crud.get_onboarding_steps_for_user_type(
        async_session, str(user_type.id)
    )
    assert len(steps) == 2
    assert steps[0].step_order == 1
    assert steps[1].step_order == 2


@pytest.mark.asyncio
async def test_crud_onboarding_step_update(async_session):
    """Test updating an onboarding step."""
    user_type_data = {"name": "Provider", "code": "provider_update"}
    user_type = await crud.create_user_type(async_session, user_type_data)

    data = {
        "user_type_id": str(user_type.id),
        "name": "Original Step",
        "code": "original",
        "step_order": 1,
    }
    step = await crud.create_onboarding_step(async_session, data)

    update_data = {"name": "Updated Step"}
    updated = await crud.update_onboarding_step(
        async_session, str(step.id), update_data
    )
    assert updated.name == "Updated Step"


@pytest.mark.asyncio
async def test_crud_user_onboarding_progress_create(
    async_session, test_organization, test_user
):
    """Test creating user onboarding progress via CRUD."""
    user_type_data = {"name": "Individual", "code": "individual_prog"}
    user_type = await crud.create_user_type(async_session, user_type_data)

    user_user_type_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    user_user_type = await crud.create_user_user_type(
        async_session, user_user_type_data, str(test_organization.id)
    )

    step_data = {
        "user_type_id": str(user_type.id),
        "name": "Step 1",
        "code": "step1",
        "step_order": 1,
    }
    step = await crud.create_onboarding_step(async_session, step_data)

    progress_data = {
        "user_id": str(test_user.id),
        "user_user_type_id": str(user_user_type.id),
        "onboarding_step_id": str(step.id),
        "submitted_data": {"key": "value"},
    }
    progress = await crud.create_onboarding_progress(
        async_session, progress_data, str(test_organization.id)
    )
    assert progress.submitted_data == {"key": "value"}


@pytest.mark.asyncio
async def test_crud_user_onboarding_progress_get_for_user_type(
    async_session, test_organization, test_user
):
    """Test getting all progress records for a user's onboarding."""
    user_type_data = {"name": "Business", "code": "business_prog"}
    user_type = await crud.create_user_type(async_session, user_type_data)

    user_user_type_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    user_user_type = await crud.create_user_user_type(
        async_session, user_user_type_data, str(test_organization.id)
    )

    step_data = {
        "user_type_id": str(user_type.id),
        "name": "Step 1",
        "code": "step1",
        "step_order": 1,
    }
    step = await crud.create_onboarding_step(async_session, step_data)

    progress_data = {
        "user_id": str(test_user.id),
        "user_user_type_id": str(user_user_type.id),
        "onboarding_step_id": str(step.id),
    }
    await crud.create_onboarding_progress(
        async_session, progress_data, str(test_organization.id)
    )

    progress_list = await crud.get_progress_for_user_type(
        async_session, str(user_user_type.id), str(test_organization.id)
    )
    assert len(progress_list) == 1


@pytest.mark.asyncio
async def test_crud_phone_verification_create_and_verify(
    async_session, test_organization, test_user
):
    """Test creating and verifying phone OTP via CRUD."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    data = {
        "user_id": str(test_user.id),
        "phone": "+1234567890",
        "otp_hash": "$2b$12$test_hash",
        "expires_at": expires_at,
    }
    verification = await crud.create_phone_verification_otp(
        async_session, data, str(test_organization.id)
    )
    assert verification.phone == "+1234567890"
    assert verification.verified is False

    active = await crud.get_active_phone_verification(
        async_session, str(test_user.id), "+1234567890", str(test_organization.id)
    )
    assert active is not None
    assert active.id == verification.id


@pytest.mark.asyncio
async def test_crud_phone_verification_rate_limiting(
    async_session, test_organization, test_user
):
    """Test phone verification rate limiting functionality."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    for i in range(3):
        data = {
            "user_id": str(test_user.id),
            "phone": "+9999999999",
            "otp_hash": f"$2b$12$test_hash_{i}",
            "expires_at": expires_at,
        }
        await crud.create_phone_verification_otp(
            async_session, data, str(test_organization.id)
        )

    count = await crud.count_phone_verification_requests(
        async_session, "+9999999999", str(test_organization.id), hours=1
    )
    assert count == 3


@pytest.mark.asyncio
async def test_crud_phone_verification_tenant_isolation(
    async_session, test_organization, test_user, second_organization
):
    """Test phone verification is isolated by organization."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    data = {
        "user_id": str(test_user.id),
        "phone": "+1111111111",
        "otp_hash": "$2b$12$test_hash",
        "expires_at": expires_at,
    }
    await crud.create_phone_verification_otp(
        async_session, data, str(test_organization.id)
    )

    # Try to retrieve from different organization - should return None
    active = await crud.get_active_phone_verification(
        async_session, str(test_user.id), "+1111111111", str(second_organization.id)
    )
    assert active is None


# API Tests
@pytest.mark.asyncio
async def test_api_create_user_type(client, test_admin_user, test_super_admin_token):
    """Test creating a user type via API (super admin only)."""
    response = await client.post(
        "/api/v1/admin/user-types",
        json={
            "name": "Test User Type",
            "code": "test_type",
            "description": "A test user type",
            "is_active": True,
            "requires_onboarding": True,
            "requires_manual_review": False,
            "is_default": False,
            "display_order": 1,
        },
        headers={"Authorization": test_super_admin_token},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test User Type"
    assert data["code"] == "test_type"


@pytest.mark.asyncio
async def test_api_list_user_types_admin(
    client, test_admin_user, test_super_admin_token
):
    """Test listing user types as super admin."""
    # Create a user type first
    await client.post(
        "/api/v1/admin/user-types",
        json={"name": "Type 1", "code": "type1", "display_order": 1},
        headers={"Authorization": test_super_admin_token},
    )

    response = await client.get(
        "/api/v1/admin/user-types",
        headers={"Authorization": test_super_admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_api_list_active_user_types(
    client, test_user, test_jwt_token, test_admin_user, test_super_admin_token
):
    """Test listing active user types as regular user."""
    # Create active and inactive user types as super admin
    await client.post(
        "/api/v1/admin/user-types",
        json={"name": "Active Type", "code": "active", "is_active": True},
        headers={"Authorization": test_super_admin_token},
    )
    await client.post(
        "/api/v1/admin/user-types",
        json={"name": "Inactive Type", "code": "inactive", "is_active": False},
        headers={"Authorization": test_super_admin_token},
    )

    # Regular user should only see active types
    response = await client.get(
        "/api/v1/user-types",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    codes = [ut["code"] for ut in data["items"]]
    assert "active" in codes
    assert "inactive" not in codes


@pytest.mark.asyncio
async def test_api_get_user_type(client, test_admin_user, test_super_admin_token):
    """Test getting a specific user type."""
    # Create a user type
    create_response = await client.post(
        "/api/v1/admin/user-types",
        json={"name": "Get Type", "code": "get_type"},
        headers={"Authorization": test_super_admin_token},
    )
    user_type_id = create_response.json()["id"]

    # Get the user type
    response = await client.get(
        f"/api/v1/admin/user-types/{user_type_id}",
        headers={"Authorization": test_super_admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_type_id
    assert data["code"] == "get_type"


@pytest.mark.asyncio
async def test_api_update_user_type(client, test_admin_user, test_super_admin_token):
    """Test updating a user type."""
    # Create a user type
    create_response = await client.post(
        "/api/v1/admin/user-types",
        json={"name": "Original", "code": "original"},
        headers={"Authorization": test_super_admin_token},
    )
    user_type_id = create_response.json()["id"]

    # Update the user type
    response = await client.put(
        f"/api/v1/admin/user-types/{user_type_id}",
        json={"name": "Updated"},
        headers={"Authorization": test_super_admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated"
    assert data["code"] == "original"


@pytest.mark.asyncio
async def test_api_delete_user_type(client, test_admin_user, test_super_admin_token):
    """Test soft deleting a user type."""
    # Create a user type
    create_response = await client.post(
        "/api/v1/admin/user-types",
        json={"name": "To Delete", "code": "to_delete"},
        headers={"Authorization": test_super_admin_token},
    )
    user_type_id = create_response.json()["id"]

    # Delete the user type
    response = await client.delete(
        f"/api/v1/admin/user-types/{user_type_id}",
        headers={"Authorization": test_super_admin_token},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_api_user_type_requires_super_admin(client, test_user, test_jwt_token):
    """Test that user type admin endpoints require super admin."""
    response = await client.post(
        "/api/v1/admin/user-types",
        json={"name": "Test", "code": "test"},
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_api_create_onboarding_step(
    client, test_admin_user, test_super_admin_token
):
    """Test creating an onboarding step via API."""
    # Create a user type first
    type_response = await client.post(
        "/api/v1/admin/user-types",
        json={"name": "Test Type", "code": "test_type_step"},
        headers={"Authorization": test_super_admin_token},
    )
    user_type_id = type_response.json()["id"]

    # Create an onboarding step
    response = await client.post(
        "/api/v1/admin/onboarding-steps",
        json={
            "user_type_id": user_type_id,
            "name": "Test Step",
            "code": "test_step",
            "step_order": 1,
            "required_fields": {"field1": "string"},
            "validation_rules": {"field1": {"min_length": 1}},
            "requires_verification": False,
            "is_active": True,
        },
        headers={"Authorization": test_super_admin_token},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Step"
    assert data["code"] == "test_step"


@pytest.mark.asyncio
async def test_api_list_steps_for_user_type(
    client, test_admin_user, test_super_admin_token
):
    """Test listing onboarding steps for a user type."""
    # Create a user type
    type_response = await client.post(
        "/api/v1/admin/user-types",
        json={"name": "Type For Steps", "code": "type_for_steps"},
        headers={"Authorization": test_super_admin_token},
    )
    user_type_id = type_response.json()["id"]

    # Create steps
    await client.post(
        "/api/v1/admin/onboarding-steps",
        json={
            "user_type_id": user_type_id,
            "name": "Step 1",
            "code": "step1",
            "step_order": 1,
        },
        headers={"Authorization": test_super_admin_token},
    )
    await client.post(
        "/api/v1/admin/onboarding-steps",
        json={
            "user_type_id": user_type_id,
            "name": "Step 2",
            "code": "step2",
            "step_order": 2,
        },
        headers={"Authorization": test_super_admin_token},
    )

    # List steps
    response = await client.get(
        f"/api/v1/admin/onboarding-steps/user-type/{user_type_id}",
        headers={"Authorization": test_super_admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_api_get_onboarding_step(client, test_admin_user, test_super_admin_token):
    """Test getting a specific onboarding step."""
    # Create user type and step
    type_response = await client.post(
        "/api/v1/admin/user-types",
        json={"name": "Type", "code": "type_get_step"},
        headers={"Authorization": test_super_admin_token},
    )
    user_type_id = type_response.json()["id"]

    step_response = await client.post(
        "/api/v1/admin/onboarding-steps",
        json={
            "user_type_id": user_type_id,
            "name": "Get Step",
            "code": "get_step",
            "step_order": 1,
        },
        headers={"Authorization": test_super_admin_token},
    )
    step_id = step_response.json()["id"]

    # Get the step
    response = await client.get(
        f"/api/v1/admin/onboarding-steps/{step_id}",
        headers={"Authorization": test_super_admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == step_id


@pytest.mark.asyncio
async def test_api_update_onboarding_step(
    client, test_admin_user, test_super_admin_token
):
    """Test updating an onboarding step."""
    # Create user type and step
    type_response = await client.post(
        "/api/v1/admin/user-types",
        json={"name": "Type", "code": "type_update_step"},
        headers={"Authorization": test_super_admin_token},
    )
    user_type_id = type_response.json()["id"]

    step_response = await client.post(
        "/api/v1/admin/onboarding-steps",
        json={
            "user_type_id": user_type_id,
            "name": "Original Step",
            "code": "original_step",
            "step_order": 1,
        },
        headers={"Authorization": test_super_admin_token},
    )
    step_id = step_response.json()["id"]

    # Update the step
    response = await client.put(
        f"/api/v1/admin/onboarding-steps/{step_id}",
        json={"name": "Updated Step"},
        headers={"Authorization": test_super_admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Step"


@pytest.mark.asyncio
async def test_api_delete_onboarding_step(
    client, test_admin_user, test_super_admin_token
):
    """Test soft deleting an onboarding step."""
    # Create user type and step
    type_response = await client.post(
        "/api/v1/admin/user-types",
        json={"name": "Type", "code": "type_delete_step"},
        headers={"Authorization": test_super_admin_token},
    )
    user_type_id = type_response.json()["id"]

    step_response = await client.post(
        "/api/v1/admin/onboarding-steps",
        json={
            "user_type_id": user_type_id,
            "name": "Step To Delete",
            "code": "step_to_delete",
            "step_order": 1,
        },
        headers={"Authorization": test_super_admin_token},
    )
    step_id = step_response.json()["id"]

    # Delete the step
    response = await client.delete(
        f"/api/v1/admin/onboarding-steps/{step_id}",
        headers={"Authorization": test_super_admin_token},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_api_reorder_steps(client, test_admin_user, test_super_admin_token):
    """Test reordering onboarding steps."""
    # Create user type
    type_response = await client.post(
        "/api/v1/admin/user-types",
        json={"name": "Type", "code": "type_reorder"},
        headers={"Authorization": test_super_admin_token},
    )
    user_type_id = type_response.json()["id"]

    # Create steps
    step1_response = await client.post(
        "/api/v1/admin/onboarding-steps",
        json={
            "user_type_id": user_type_id,
            "name": "Step 1",
            "code": "step1_reorder",
            "step_order": 1,
        },
        headers={"Authorization": test_super_admin_token},
    )
    step1_id = step1_response.json()["id"]

    step2_response = await client.post(
        "/api/v1/admin/onboarding-steps",
        json={
            "user_type_id": user_type_id,
            "name": "Step 2",
            "code": "step2_reorder",
            "step_order": 2,
        },
        headers={"Authorization": test_super_admin_token},
    )
    step2_id = step2_response.json()["id"]

    # Reorder steps (swap them)
    response = await client.post(
        f"/api/v1/admin/onboarding-steps/user-type/{user_type_id}/reorder",
        json={
            "steps": [
                {"id": step1_id, "step_order": 2},
                {"id": step2_id, "step_order": 1},
            ]
        },
        headers={"Authorization": test_super_admin_token},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_api_onboarding_step_requires_super_admin(
    client, test_user, test_jwt_token
):
    """Test that onboarding step endpoints require super admin."""
    response = await client.post(
        "/api/v1/admin/onboarding-steps",
        json={
            "user_type_id": "00000000-0000-0000-0000-000000000000",
            "name": "Test",
            "code": "test",
            "step_order": 1,
        },
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 403


# Service Tests


@pytest.mark.asyncio
async def test_service_start_onboarding(async_session, test_organization, test_user):
    """Test starting onboarding via service."""
    # Create a user type
    user_type_data = {
        "name": "Service Type",
        "code": "service_type",
        "requires_onboarding": True,
        "is_active": True,
        "requires_manual_review": False,
    }
    user_type = await crud.create_user_type(async_session, user_type_data)

    # Create an onboarding step
    step_data = {
        "user_type_id": str(user_type.id),
        "name": "Step 1",
        "code": "step1",
        "step_order": 1,
        "required_fields": {"field1": "string"},
        "is_active": True,
    }
    await crud.create_onboarding_step(async_session, step_data)

    # Start onboarding
    result = await onboarding_service.start_onboarding(
        async_session, str(test_user.id), str(user_type.id), str(test_organization.id)
    )

    assert result["status"] == "in_progress"
    assert "user_user_type_id" in result
    assert result["current_step"]["code"] == "step1"
    assert result["total_steps"] == 1


@pytest.mark.asyncio
async def test_service_submit_step(async_session, test_organization, test_user):
    """Test submitting a step via service."""
    # Create user type and step
    user_type_data = {
        "name": "Submit Type",
        "code": "submit_type",
        "requires_onboarding": True,
        "is_active": True,
    }
    user_type = await crud.create_user_type(async_session, user_type_data)

    step_data = {
        "user_type_id": str(user_type.id),
        "name": "Submit Step",
        "code": "submit_step",
        "step_order": 1,
        "required_fields": ["field1", "field2"],
        "is_active": True,
    }
    step = await crud.create_onboarding_step(async_session, step_data)

    # Start onboarding
    result = await onboarding_service.start_onboarding(
        async_session, str(test_user.id), str(user_type.id), str(test_organization.id)
    )
    user_user_type_id = result["user_user_type_id"]

    # Submit step
    submit_result = await onboarding_service.submit_step(
        async_session,
        str(test_user.id),
        user_user_type_id,
        str(step.id),
        {"field1": "value1", "field2": "value2"},
        str(test_organization.id),
    )

    assert submit_result["step_completed"] is True
    assert submit_result["all_steps_complete"] is True
    assert "progress_id" in submit_result


@pytest.mark.asyncio
async def test_service_get_progress(async_session, test_organization, test_user):
    """Test getting onboarding progress via service."""
    # Create user type and steps
    user_type_data = {
        "name": "Progress Type",
        "code": "progress_type",
        "requires_onboarding": True,
        "is_active": True,
    }
    user_type = await crud.create_user_type(async_session, user_type_data)

    step1_data = {
        "user_type_id": str(user_type.id),
        "name": "Step 1",
        "code": "prog_step1",
        "step_order": 1,
        "is_active": True,
    }
    step2_data = {
        "user_type_id": str(user_type.id),
        "name": "Step 2",
        "code": "prog_step2",
        "step_order": 2,
        "is_active": True,
    }
    step1 = await crud.create_onboarding_step(async_session, step1_data)
    await crud.create_onboarding_step(async_session, step2_data)

    # Start onboarding
    result = await onboarding_service.start_onboarding(
        async_session, str(test_user.id), str(user_type.id), str(test_organization.id)
    )
    user_user_type_id = result["user_user_type_id"]

    # Submit first step
    await onboarding_service.submit_step(
        async_session,
        str(test_user.id),
        user_user_type_id,
        str(step1.id),
        {},
        str(test_organization.id),
    )

    # Get progress
    progress = await onboarding_service.get_progress(
        async_session, user_user_type_id, str(test_organization.id)
    )

    assert progress["status"] == "in_progress"
    assert progress["completed_steps_count"] == 1
    assert progress["total_steps"] == 2


@pytest.mark.asyncio
async def test_service_check_completion_auto_approve(
    async_session, test_organization, test_user
):
    """Test check_completion with auto-approval (no manual review)."""
    # Create user type without manual review
    user_type_data = {
        "name": "Auto Approve",
        "code": "auto_approve",
        "requires_onboarding": True,
        "requires_manual_review": False,
        "is_active": True,
    }
    user_type = await crud.create_user_type(async_session, user_type_data)

    step_data = {
        "user_type_id": str(user_type.id),
        "name": "Step",
        "code": "auto_step",
        "step_order": 1,
        "is_active": True,
    }
    step = await crud.create_onboarding_step(async_session, step_data)

    # Start and complete onboarding
    result = await onboarding_service.start_onboarding(
        async_session, str(test_user.id), str(user_type.id), str(test_organization.id)
    )
    user_user_type_id = result["user_user_type_id"]

    await onboarding_service.submit_step(
        async_session,
        str(test_user.id),
        user_user_type_id,
        str(step.id),
        {},
        str(test_organization.id),
    )

    # Check completion
    completion = await onboarding_service.check_completion(
        async_session, user_user_type_id, str(test_organization.id)
    )

    assert completion["all_complete"] is True
    assert completion["status"] == "approved"


@pytest.mark.asyncio
async def test_service_check_completion_manual_review(
    async_session, test_organization, test_user
):
    """Test check_completion with manual review required."""
    # Create user type with manual review
    user_type_data = {
        "name": "Manual Review",
        "code": "manual_review",
        "requires_onboarding": True,
        "requires_manual_review": True,
        "is_active": True,
    }
    user_type = await crud.create_user_type(async_session, user_type_data)

    step_data = {
        "user_type_id": str(user_type.id),
        "name": "Step",
        "code": "manual_step",
        "step_order": 1,
        "is_active": True,
    }
    step = await crud.create_onboarding_step(async_session, step_data)

    # Start and complete onboarding
    result = await onboarding_service.start_onboarding(
        async_session, str(test_user.id), str(user_type.id), str(test_organization.id)
    )
    user_user_type_id = result["user_user_type_id"]

    await onboarding_service.submit_step(
        async_session,
        str(test_user.id),
        user_user_type_id,
        str(step.id),
        {},
        str(test_organization.id),
    )

    # Check completion
    completion = await onboarding_service.check_completion(
        async_session, user_user_type_id, str(test_organization.id)
    )

    assert completion["all_complete"] is True
    assert completion["status"] == "pending_review"


@pytest.mark.asyncio
async def test_service_step_validation_success(
    async_session, test_organization, test_user
):
    """Test step data validation with valid data."""
    # Create user type and step with validation rules
    user_type_data = {
        "name": "Validation Type",
        "code": "validation_type",
        "requires_onboarding": True,
        "is_active": True,
    }
    user_type = await crud.create_user_type(async_session, user_type_data)

    step_data = {
        "user_type_id": str(user_type.id),
        "name": "Validation Step",
        "code": "validation_step",
        "step_order": 1,
        "required_fields": ["name", "age"],
        "validation_rules": {
            "name": {"type": "string", "min_length": 2},
            "age": {"type": "number", "min_value": 18},
        },
        "is_active": True,
    }
    step = await crud.create_onboarding_step(async_session, step_data)

    # Start onboarding
    result = await onboarding_service.start_onboarding(
        async_session, str(test_user.id), str(user_type.id), str(test_organization.id)
    )
    user_user_type_id = result["user_user_type_id"]

    # Submit with valid data - should not raise
    submit_result = await onboarding_service.submit_step(
        async_session,
        str(test_user.id),
        user_user_type_id,
        str(step.id),
        {"name": "John Doe", "age": 25},
        str(test_organization.id),
    )

    assert submit_result["step_completed"] is True


@pytest.mark.asyncio
async def test_service_step_validation_failure(
    async_session, test_organization, test_user
):
    """Test step data validation with invalid data."""
    # Create user type and step with validation rules
    user_type_data = {
        "name": "Val Fail Type",
        "code": "val_fail_type",
        "requires_onboarding": True,
        "is_active": True,
    }
    user_type = await crud.create_user_type(async_session, user_type_data)

    step_data = {
        "user_type_id": str(user_type.id),
        "name": "Validation Step",
        "code": "val_fail_step",
        "step_order": 1,
        "required_fields": ["name", "age"],
        "validation_rules": {
            "name": {"type": "string", "min_length": 2},
            "age": {"type": "number", "min_value": 18},
        },
        "is_active": True,
    }
    step = await crud.create_onboarding_step(async_session, step_data)

    # Start onboarding
    result = await onboarding_service.start_onboarding(
        async_session, str(test_user.id), str(user_type.id), str(test_organization.id)
    )
    user_user_type_id = result["user_user_type_id"]

    # Submit with invalid data - should raise ValueError
    with pytest.raises(ValueError, match="Validation failed"):
        await onboarding_service.submit_step(
            async_session,
            str(test_user.id),
            user_user_type_id,
            str(step.id),
            {"name": "J", "age": 17},  # name too short, age too young
            str(test_organization.id),
        )


@pytest.mark.asyncio
@patch("src.services.phone_verification.notification_dispatcher")
async def test_service_send_otp(
    mock_dispatcher, async_session, test_organization, test_user
):
    """Test sending OTP via phone verification service."""
    # Mock notification dispatcher
    mock_dispatcher.send_notification = AsyncMock(return_value={"status": "sent"})

    result = await phone_verification_service.send_otp(
        async_session, str(test_user.id), "+1234567890", str(test_organization.id)
    )

    assert "verification_id" in result
    assert "expires_at" in result
    assert mock_dispatcher.send_notification.called


@pytest.mark.asyncio
async def test_service_verify_otp_success(async_session, test_organization, test_user):
    """Test verifying OTP with correct code."""
    import bcrypt

    # Create a verification record manually
    otp_code = "123456"
    otp_hash = bcrypt.hashpw(otp_code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    data = {
        "user_id": str(test_user.id),
        "phone": "+1234567890",
        "otp_hash": otp_hash,
        "expires_at": expires_at,
    }
    await crud.create_phone_verification_otp(
        async_session, data, str(test_organization.id)
    )

    # Verify OTP
    result = await phone_verification_service.verify_otp(
        async_session,
        str(test_user.id),
        "+1234567890",
        otp_code,
        str(test_organization.id),
    )

    assert result["verified"] is True
    assert result["phone"] == "+1234567890"


@pytest.mark.asyncio
async def test_service_verify_otp_failure(async_session, test_organization, test_user):
    """Test verifying OTP with incorrect code."""
    import bcrypt

    # Create a verification record
    otp_code = "123456"
    otp_hash = bcrypt.hashpw(otp_code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    data = {
        "user_id": str(test_user.id),
        "phone": "+9876543210",
        "otp_hash": otp_hash,
        "expires_at": expires_at,
    }
    await crud.create_phone_verification_otp(
        async_session, data, str(test_organization.id)
    )

    # Verify with wrong OTP
    with pytest.raises(ValueError, match="Invalid OTP code"):
        await phone_verification_service.verify_otp(
            async_session,
            str(test_user.id),
            "+9876543210",
            "000000",  # Wrong code
            str(test_organization.id),
        )


@pytest.mark.asyncio
async def test_service_otp_rate_limiting(async_session, test_organization, test_user):
    """Test OTP rate limiting - max 3 requests per hour."""
    from unittest.mock import patch

    # Mock the notification dispatcher to avoid actual SMS sending
    with patch(
        "src.services.phone_verification.notification_dispatcher.send_notification",
        new_callable=AsyncMock,
    ) as mock_send:
        mock_send.return_value = {"status": "sent"}

        phone = "+1111222233"

        # Send 3 OTPs (should succeed)
        for i in range(3):
            await phone_verification_service.send_otp(
                async_session, str(test_user.id), phone, str(test_organization.id)
            )

        # 4th attempt should fail due to rate limiting
        with pytest.raises(ValueError, match="Too many OTP requests"):
            await phone_verification_service.send_otp(
                async_session, str(test_user.id), phone, str(test_organization.id)
            )


@pytest.mark.asyncio
async def test_service_otp_max_attempts(async_session, test_organization, test_user):
    """Test OTP verification max attempts (3 attempts)."""
    import bcrypt

    # Create a verification record
    otp_code = "123456"
    otp_hash = bcrypt.hashpw(otp_code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    data = {
        "user_id": str(test_user.id),
        "phone": "+5555555555",
        "otp_hash": otp_hash,
        "expires_at": expires_at,
    }
    await crud.create_phone_verification_otp(
        async_session, data, str(test_organization.id)
    )

    # Try wrong OTP 3 times
    for i in range(3):
        try:
            await phone_verification_service.verify_otp(
                async_session,
                str(test_user.id),
                "+5555555555",
                "000000",
                str(test_organization.id),
            )
        except ValueError:
            pass

    # 4th attempt should fail with max attempts message
    with pytest.raises(ValueError, match="Maximum verification attempts exceeded"):
        await phone_verification_service.verify_otp(
            async_session,
            str(test_user.id),
            "+5555555555",
            "000000",
            str(test_organization.id),
        )


@pytest.mark.asyncio
async def test_service_send_otp_phone_already_in_use(
    async_session, test_organization, test_user
):
    """Test that send_otp fails if phone is already registered to another user."""
    from src.core.security import hash_password
    from src.models.user import User

    # Create another user in the same organization with a phone number
    existing_phone = "+27123456789"
    another_user = User(
        organization_id=test_organization.id,
        email="another_user@test.com",
        first_name="Another",
        last_name="User",
        password=hash_password("test123"),
        email_verified=True,
        phone=existing_phone,
        phone_verified=True,
    )
    async_session.add(another_user)
    await async_session.commit()

    # Try to send OTP for the same phone number from a different user
    with pytest.raises(ValueError, match="already registered"):
        await phone_verification_service.send_otp(
            async_session, str(test_user.id), existing_phone, str(test_organization.id)
        )


@pytest.mark.asyncio
async def test_service_send_otp_same_user_same_phone(
    async_session, test_organization, test_user
):
    """Test that a user can request OTP for their own already-registered phone number."""
    from unittest.mock import patch

    # Set the user's phone number
    test_user.phone = "+27987654321"
    test_user.phone_verified = True
    await async_session.commit()

    # Mock the notification dispatcher
    with patch(
        "src.services.phone_verification.notification_dispatcher.send_notification",
        new_callable=AsyncMock,
    ) as mock_send:
        mock_send.return_value = {"status": "sent"}

        # Should succeed - user can request OTP for their own phone
        result = await phone_verification_service.send_otp(
            async_session, str(test_user.id), "+27987654321", str(test_organization.id)
        )

        assert "verification_id" in result
        assert "expires_at" in result


# ============================================================================
# PHASE 5: ADMIN REVIEW & NOTIFICATIONS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_notification_service_send_submission(
    async_session, test_organization, test_user
):
    """Test sending submission notification to user."""
    import src.crud.user_user_type as crud
    from src.services.onboarding_notifications import onboarding_notification_service

    # Create user type
    user_type = UserType(
        name="Individual",
        code="individual",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user_user_type
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    user_user_type = await crud.create(
        async_session, uut_data, str(test_organization.id)
    )

    # Should not raise exception
    await onboarding_notification_service.send_submission_notification(
        async_session,
        str(test_user.id),
        str(test_organization.id),
        str(user_user_type.id),
    )


@pytest.mark.asyncio
async def test_notification_service_send_approved(
    async_session, test_organization, test_user
):
    """Test sending approval notification to user."""
    import src.crud.user_user_type as crud
    from src.services.onboarding_notifications import onboarding_notification_service

    # Create user type
    user_type = UserType(
        name="Individual",
        code="individual",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user_user_type
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    user_user_type = await crud.create(
        async_session, uut_data, str(test_organization.id)
    )

    # Should not raise exception
    await onboarding_notification_service.send_approved_notification(
        async_session,
        str(test_user.id),
        str(test_organization.id),
        str(user_user_type.id),
    )


@pytest.mark.asyncio
async def test_notification_service_send_rejected(
    async_session, test_organization, test_user
):
    """Test sending rejection notification to user with reason."""
    import src.crud.user_user_type as crud
    from src.services.onboarding_notifications import onboarding_notification_service

    # Create user type
    user_type = UserType(
        name="Individual",
        code="individual",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user_user_type
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    user_user_type = await crud.create(
        async_session, uut_data, str(test_organization.id)
    )

    # Should not raise exception
    await onboarding_notification_service.send_rejected_notification(
        async_session,
        str(test_user.id),
        str(test_organization.id),
        str(user_user_type.id),
        reason="Missing required documents",
    )


@pytest.mark.asyncio
async def test_notification_service_new_review_required(
    async_session, test_organization, test_user
):
    """Test sending new review notification to org admins."""
    import src.crud.user_user_type as crud
    from src.services.onboarding_notifications import onboarding_notification_service

    # Create user type
    user_type = UserType(
        name="Individual",
        code="individual",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user_user_type
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    user_user_type = await crud.create(
        async_session, uut_data, str(test_organization.id)
    )

    # Should not raise exception (even if no admins)
    await onboarding_notification_service.send_new_review_required_notification(
        async_session,
        str(test_user.id),
        str(test_organization.id),
        str(user_user_type.id),
    )


@pytest.mark.asyncio
async def test_service_check_completion_triggers_notifications(
    async_session, test_organization, test_user
):
    """Test that check_completion triggers notifications when status changes to pending_review."""
    from unittest.mock import AsyncMock, patch

    from src.services.onboarding import onboarding_service

    # Create user type with manual review
    user_type = UserType(
        name="Business",
        code="business",
        requires_onboarding=True,
        requires_manual_review=True,  # Important: requires manual review
        is_active=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create onboarding step
    step = OnboardingStep(
        user_type_id=user_type.id,
        name="Business Info",
        code="business_info",
        step_order=1,
        required_fields=["name", "email"],
        is_active=True,
    )
    async_session.add(step)
    await async_session.commit()

    # Start onboarding
    result = await onboarding_service.start_onboarding(
        async_session,
        str(test_user.id),
        str(user_type.id),
        str(test_organization.id),
    )
    uut_id = result["user_user_type_id"]

    # Mock the notification service methods
    with patch(
        "src.services.onboarding_notifications.onboarding_notification_service.send_submission_notification",
        new_callable=AsyncMock,
    ) as mock_submission, patch(
        "src.services.onboarding_notifications.onboarding_notification_service.send_new_review_required_notification",
        new_callable=AsyncMock,
    ) as mock_review:

        # Complete the only step
        await onboarding_service.submit_step(
            async_session,
            str(test_user.id),
            uut_id,
            str(step.id),
            {"name": "John Doe", "email": "john@example.com"},
            str(test_organization.id),
        )

        # Verify notifications were called
        mock_submission.assert_called_once()
        mock_review.assert_called_once()


@pytest.mark.asyncio
async def test_approve_onboarding_submission(
    async_session, test_organization, test_user
):
    """Test approving an onboarding submission via CRUD."""
    import src.crud.user_user_type as crud
    from src.models.user_user_type import OnboardingStatus

    # Create user type
    user_type = UserType(
        name="Individual",
        code="individual",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user_user_type with pending_review status
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    user_user_type = await crud.create(
        async_session, uut_data, str(test_organization.id)
    )

    # Set to pending_review
    await crud.update_status(
        async_session,
        str(user_user_type.id),
        OnboardingStatus.PENDING_REVIEW,
        str(test_organization.id),
    )

    # Approve
    onboarded_at = datetime.now(timezone.utc)
    updated = await crud.update_status(
        async_session,
        str(user_user_type.id),
        OnboardingStatus.APPROVED,
        str(test_organization.id),
        onboarded_at=onboarded_at,
    )

    assert updated.onboarding_status == OnboardingStatus.APPROVED
    assert updated.onboarded_at is not None


@pytest.mark.asyncio
async def test_reject_onboarding_submission(
    async_session, test_organization, test_user
):
    """Test rejecting an onboarding submission via CRUD."""
    import src.crud.user_user_type as crud
    from src.models.user_user_type import OnboardingStatus

    # Create user type
    user_type = UserType(
        name="Individual",
        code="individual",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user_user_type with pending_review status
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    user_user_type = await crud.create(
        async_session, uut_data, str(test_organization.id)
    )

    # Set to pending_review
    await crud.update_status(
        async_session,
        str(user_user_type.id),
        OnboardingStatus.PENDING_REVIEW,
        str(test_organization.id),
    )

    # Reject
    updated = await crud.update_status(
        async_session,
        str(user_user_type.id),
        OnboardingStatus.REJECTED,
        str(test_organization.id),
    )

    assert updated.onboarding_status == OnboardingStatus.REJECTED
    assert updated.onboarded_at is None


@pytest.mark.asyncio
async def test_get_pending_reviews_org_isolation(
    async_session, test_organization, test_user
):
    """Test that pending reviews are isolated by organization."""
    from sqlalchemy import select

    import src.crud.user_user_type as crud
    from src.models.organization import Organization
    from src.models.user_user_type import OnboardingStatus, UserUserType

    # Create second organization
    org2 = Organization(
        name="Test Org 2",
        slug="test-org-2",
        is_active=True,
    )
    async_session.add(org2)
    await async_session.commit()

    # Create a user in org2
    from src.crud.user import create_user

    user2_data = {
        "email": "user2@example.com",
        "password": "Password123!",
    }
    user2 = await create_user(async_session, user2_data, str(org2.id))

    # Create user type
    user_type = UserType(
        name="Individual",
        code="individual",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create pending review in org1
    uut1_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    uut1 = await crud.create(async_session, uut1_data, str(test_organization.id))
    await crud.update_status(
        async_session,
        str(uut1.id),
        OnboardingStatus.PENDING_REVIEW,
        str(test_organization.id),
    )

    # Create pending review in org2
    uut2_data = {
        "user_id": str(user2.id),
        "user_type_id": str(user_type.id),
    }
    uut2 = await crud.create(async_session, uut2_data, str(org2.id))
    await crud.update_status(
        async_session,
        str(uut2.id),
        OnboardingStatus.PENDING_REVIEW,
        str(org2.id),
    )

    # Query pending reviews for org1
    from uuid import UUID

    result = await async_session.execute(
        select(UserUserType).where(
            UserUserType.organization_id == UUID(str(test_organization.id)),
            UserUserType.onboarding_status == OnboardingStatus.PENDING_REVIEW,
            UserUserType.deleted_time.is_(None),
        )
    )
    org1_pending = result.scalars().all()

    # Should only see org1's pending review
    assert len(org1_pending) == 1
    assert org1_pending[0].id == uut1.id


# ============================================================================
# API TESTS FOR REVIEW ENDPOINTS
# ============================================================================


@pytest.mark.asyncio
async def test_api_get_pending_reviews(
    client,
    test_admin_user,
    test_admin_token,
    test_organization,
    test_user,
    async_session,
):
    """Test listing pending reviews works for admins."""
    import src.crud.user_user_type as crud
    from src.models.user_user_type import OnboardingStatus

    # Create user type
    user_type = UserType(
        name="Individual",
        code="individual_api",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create pending review submission
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    uut = await crud.create(async_session, uut_data, str(test_organization.id))
    await crud.update_status(
        async_session,
        str(uut.id),
        OnboardingStatus.PENDING_REVIEW,
        str(test_organization.id),
    )

    # List pending reviews
    response = await client.get(
        "/api/v1/onboarding/review/pending",
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["total"] >= 1
    assert any(pr["id"] == str(uut.id) for pr in data["items"])


@pytest.mark.asyncio
async def test_api_get_pending_reviews_requires_admin(
    client, test_user, test_jwt_token
):
    """Test non-admins are blocked from listing pending reviews (403)."""
    response = await client.get(
        "/api/v1/onboarding/review/pending",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_api_get_pending_reviews_org_isolation(
    client,
    test_admin_user,
    test_admin_token,
    test_organization,
    test_user,
    async_session,
    second_organization,
):
    """Test pending reviews are filtered by organization."""
    from src.crud.user import create_user
    import src.crud.user_user_type as crud
    from src.models.user_user_type import OnboardingStatus

    # Create user type
    user_type = UserType(
        name="Business",
        code="business_api_iso",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create pending review in org1 (test_organization)
    uut1_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    uut1 = await crud.create(async_session, uut1_data, str(test_organization.id))
    await crud.update_status(
        async_session,
        str(uut1.id),
        OnboardingStatus.PENDING_REVIEW,
        str(test_organization.id),
    )

    # Create user in org2
    user2_data = {
        "email": "user2_api@example.com",
        "password": "Password123!",
    }
    user2 = await create_user(async_session, user2_data, str(second_organization.id))

    # Create pending review in org2
    uut2_data = {
        "user_id": str(user2.id),
        "user_type_id": str(user_type.id),
    }
    uut2 = await crud.create(async_session, uut2_data, str(second_organization.id))
    await crud.update_status(
        async_session,
        str(uut2.id),
        OnboardingStatus.PENDING_REVIEW,
        str(second_organization.id),
    )

    # List pending reviews as admin from org1
    response = await client.get(
        "/api/v1/onboarding/review/pending",
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 200
    data = response.json()

    # Should only see org1's submission
    pending_ids = [pr["id"] for pr in data["items"]]
    assert str(uut1.id) in pending_ids
    assert str(uut2.id) not in pending_ids


@pytest.mark.asyncio
async def test_api_get_submission_details(
    client,
    test_admin_user,
    test_admin_token,
    test_organization,
    test_user,
    async_session,
):
    """Test retrieving submission details works."""
    import src.crud.user_user_type as crud
    from src.models.user_user_type import OnboardingStatus

    # Create user type and step
    user_type = UserType(
        name="Provider",
        code="provider_api",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    step = OnboardingStep(
        user_type_id=user_type.id,
        name="Personal Info",
        code="personal_info_api",
        step_order=1,
        required_fields=["name", "email"],
        is_active=True,
    )
    async_session.add(step)
    await async_session.commit()

    # Create user_user_type
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    uut = await crud.create(async_session, uut_data, str(test_organization.id))
    await crud.update_status(
        async_session,
        str(uut.id),
        OnboardingStatus.PENDING_REVIEW,
        str(test_organization.id),
    )

    # Add progress for the step
    from src.crud.user_onboarding_progress import create as create_progress

    progress_data = {
        "user_id": str(test_user.id),
        "user_user_type_id": str(uut.id),
        "onboarding_step_id": str(step.id),
        "submitted_data": {"name": "John Doe", "email": "john@example.com"},
    }
    await create_progress(async_session, progress_data, str(test_organization.id))

    # Get submission details
    response = await client.get(
        f"/api/v1/onboarding/review/{uut.id}",
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(uut.id)
    assert data["onboarding_status"] == "pending_review"
    assert len(data["steps_data"]) == 1
    assert data["steps_data"][0]["submitted_data"]["name"] == "John Doe"


@pytest.mark.asyncio
async def test_api_get_submission_details_requires_admin(
    client, test_user, test_jwt_token, test_organization, async_session
):
    """Test non-admins are blocked from retrieving submission details."""
    import src.crud.user_user_type as crud

    # Create user type
    user_type = UserType(
        name="Test",
        code="test_api_auth",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user_user_type
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    uut = await crud.create(async_session, uut_data, str(test_organization.id))

    # Try to get submission details as non-admin
    response = await client.get(
        f"/api/v1/onboarding/review/{uut.id}",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_api_get_submission_details_org_isolation(
    client,
    test_admin_user,
    test_admin_token,
    test_organization,
    test_user,
    async_session,
    second_organization,
):
    """Test cross-org access to submission details is blocked (404)."""
    from src.crud.user import create_user
    import src.crud.user_user_type as crud

    # Create user type
    user_type = UserType(
        name="Test",
        code="test_api_iso2",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user in org2
    user2_data = {
        "email": "user2_details@example.com",
        "password": "Password123!",
    }
    user2 = await create_user(async_session, user2_data, str(second_organization.id))

    # Create user_user_type in org2
    uut_data = {
        "user_id": str(user2.id),
        "user_type_id": str(user_type.id),
    }
    uut = await crud.create(async_session, uut_data, str(second_organization.id))

    # Try to get submission details from org1 admin
    response = await client.get(
        f"/api/v1/onboarding/review/{uut.id}",
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_get_submission_details_not_found(
    client, test_admin_user, test_admin_token
):
    """Test proper 404 for non-existent submission IDs."""
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = await client.get(
        f"/api/v1/onboarding/review/{fake_uuid}",
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_approve_submission(
    client,
    test_admin_user,
    test_admin_token,
    test_organization,
    test_user,
    async_session,
):
    """Test approval workflow sets status to 'approved' and onboarded_at timestamp."""
    import src.crud.user_user_type as crud
    from src.models.user_user_type import OnboardingStatus

    # Create user type
    user_type = UserType(
        name="Individual",
        code="individual_approve",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user_user_type with pending_review status
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    uut = await crud.create(async_session, uut_data, str(test_organization.id))
    await crud.update_status(
        async_session,
        str(uut.id),
        OnboardingStatus.PENDING_REVIEW,
        str(test_organization.id),
    )

    # Approve submission
    response = await client.post(
        f"/api/v1/onboarding/review/{uut.id}/approve",
        json={},
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["onboarded_at"] is not None


@pytest.mark.asyncio
async def test_api_approve_submission_requires_admin(
    client, test_user, test_jwt_token, test_organization, async_session
):
    """Test non-admins are blocked from approving submissions."""
    import src.crud.user_user_type as crud
    from src.models.user_user_type import OnboardingStatus

    # Create user type
    user_type = UserType(
        name="Test",
        code="test_approve_auth",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user_user_type
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    uut = await crud.create(async_session, uut_data, str(test_organization.id))
    await crud.update_status(
        async_session,
        str(uut.id),
        OnboardingStatus.PENDING_REVIEW,
        str(test_organization.id),
    )

    # Try to approve as non-admin
    response = await client.post(
        f"/api/v1/onboarding/review/{uut.id}/approve",
        json={},
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_api_approve_submission_org_isolation(
    client,
    test_admin_user,
    test_admin_token,
    test_organization,
    async_session,
    second_organization,
):
    """Test cross-org approval is blocked."""
    from src.crud.user import create_user
    import src.crud.user_user_type as crud
    from src.models.user_user_type import OnboardingStatus

    # Create user type
    user_type = UserType(
        name="Test",
        code="test_approve_iso",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user in org2
    user2_data = {
        "email": "user2_approve@example.com",
        "password": "Password123!",
    }
    user2 = await create_user(async_session, user2_data, str(second_organization.id))

    # Create user_user_type in org2
    uut_data = {
        "user_id": str(user2.id),
        "user_type_id": str(user_type.id),
    }
    uut = await crud.create(async_session, uut_data, str(second_organization.id))
    await crud.update_status(
        async_session,
        str(uut.id),
        OnboardingStatus.PENDING_REVIEW,
        str(second_organization.id),
    )

    # Try to approve from org1 admin
    response = await client.post(
        f"/api/v1/onboarding/review/{uut.id}/approve",
        json={},
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_approve_submission_triggers_notification(
    client,
    test_admin_user,
    test_admin_token,
    test_organization,
    test_user,
    async_session,
):
    """Test approval triggers notification service."""
    from unittest.mock import AsyncMock, patch

    import src.crud.user_user_type as crud
    from src.models.user_user_type import OnboardingStatus

    # Create user type
    user_type = UserType(
        name="Individual",
        code="individual_notify_approve",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user_user_type
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    uut = await crud.create(async_session, uut_data, str(test_organization.id))
    await crud.update_status(
        async_session,
        str(uut.id),
        OnboardingStatus.PENDING_REVIEW,
        str(test_organization.id),
    )

    # Mock notification service
    with patch(
        "src.services.onboarding_notifications.onboarding_notification_service.send_approved_notification",
        new_callable=AsyncMock,
    ) as mock_notify:
        response = await client.post(
            f"/api/v1/onboarding/review/{uut.id}/approve",
            json={},
            headers={"Authorization": test_admin_token},
        )
        assert response.status_code == 200
        mock_notify.assert_called_once()


@pytest.mark.asyncio
async def test_api_approve_submission_wrong_status(
    client,
    test_admin_user,
    test_admin_token,
    test_organization,
    test_user,
    async_session,
):
    """Test only pending_review can be approved (400)."""
    import src.crud.user_user_type as crud

    # Create user type
    user_type = UserType(
        name="Test",
        code="test_approve_status",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user_user_type with status NOT pending_review
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    uut = await crud.create(async_session, uut_data, str(test_organization.id))
    # Leave it in PENDING status (not PENDING_REVIEW)

    # Try to approve
    response = await client.post(
        f"/api/v1/onboarding/review/{uut.id}/approve",
        json={},
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_api_reject_submission(
    client,
    test_admin_user,
    test_admin_token,
    test_organization,
    test_user,
    async_session,
):
    """Test rejection workflow sets status to 'rejected'."""
    import src.crud.user_user_type as crud
    from src.models.user_user_type import OnboardingStatus

    # Create user type
    user_type = UserType(
        name="Individual",
        code="individual_reject",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user_user_type with pending_review status
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    uut = await crud.create(async_session, uut_data, str(test_organization.id))
    await crud.update_status(
        async_session,
        str(uut.id),
        OnboardingStatus.PENDING_REVIEW,
        str(test_organization.id),
    )

    # Reject submission
    response = await client.post(
        f"/api/v1/onboarding/review/{uut.id}/reject",
        json={"reason": "Missing required documents"},
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["reason"] == "Missing required documents"


@pytest.mark.asyncio
async def test_api_reject_submission_requires_admin(
    client, test_user, test_jwt_token, test_organization, async_session
):
    """Test non-admins are blocked from rejecting submissions."""
    import src.crud.user_user_type as crud
    from src.models.user_user_type import OnboardingStatus

    # Create user type
    user_type = UserType(
        name="Test",
        code="test_reject_auth",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user_user_type
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    uut = await crud.create(async_session, uut_data, str(test_organization.id))
    await crud.update_status(
        async_session,
        str(uut.id),
        OnboardingStatus.PENDING_REVIEW,
        str(test_organization.id),
    )

    # Try to reject as non-admin
    response = await client.post(
        f"/api/v1/onboarding/review/{uut.id}/reject",
        json={"reason": "Test reason"},
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_api_reject_submission_org_isolation(
    client,
    test_admin_user,
    test_admin_token,
    test_organization,
    async_session,
    second_organization,
):
    """Test cross-org rejection is blocked."""
    from src.crud.user import create_user
    import src.crud.user_user_type as crud
    from src.models.user_user_type import OnboardingStatus

    # Create user type
    user_type = UserType(
        name="Test",
        code="test_reject_iso",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user in org2
    user2_data = {
        "email": "user2_reject@example.com",
        "password": "Password123!",
    }
    user2 = await create_user(async_session, user2_data, str(second_organization.id))

    # Create user_user_type in org2
    uut_data = {
        "user_id": str(user2.id),
        "user_type_id": str(user_type.id),
    }
    uut = await crud.create(async_session, uut_data, str(second_organization.id))
    await crud.update_status(
        async_session,
        str(uut.id),
        OnboardingStatus.PENDING_REVIEW,
        str(second_organization.id),
    )

    # Try to reject from org1 admin
    response = await client.post(
        f"/api/v1/onboarding/review/{uut.id}/reject",
        json={"reason": "Test reason"},
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_reject_submission_triggers_notification(
    client,
    test_admin_user,
    test_admin_token,
    test_organization,
    test_user,
    async_session,
):
    """Test rejection triggers notification service with reason."""
    from unittest.mock import AsyncMock, patch

    import src.crud.user_user_type as crud
    from src.models.user_user_type import OnboardingStatus

    # Create user type
    user_type = UserType(
        name="Individual",
        code="individual_notify_reject",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user_user_type
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    uut = await crud.create(async_session, uut_data, str(test_organization.id))
    await crud.update_status(
        async_session,
        str(uut.id),
        OnboardingStatus.PENDING_REVIEW,
        str(test_organization.id),
    )

    # Mock notification service
    with patch(
        "src.services.onboarding_notifications.onboarding_notification_service.send_rejected_notification",
        new_callable=AsyncMock,
    ) as mock_notify:
        response = await client.post(
            f"/api/v1/onboarding/review/{uut.id}/reject",
            json={"reason": "Incomplete information"},
            headers={"Authorization": test_admin_token},
        )
        assert response.status_code == 200
        mock_notify.assert_called_once()
        # Verify reason was passed to notification
        call_kwargs = mock_notify.call_args.kwargs
        assert call_kwargs["reason"] == "Incomplete information"


@pytest.mark.asyncio
async def test_api_reject_submission_wrong_status(
    client,
    test_admin_user,
    test_admin_token,
    test_organization,
    test_user,
    async_session,
):
    """Test only pending_review can be rejected (400)."""
    import src.crud.user_user_type as crud

    # Create user type
    user_type = UserType(
        name="Test",
        code="test_reject_status",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user_user_type with status NOT pending_review
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    uut = await crud.create(async_session, uut_data, str(test_organization.id))
    # Leave it in PENDING status (not PENDING_REVIEW)

    # Try to reject
    response = await client.post(
        f"/api/v1/onboarding/review/{uut.id}/reject",
        json={"reason": "Test reason"},
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_api_reject_submission_missing_reason(
    client,
    test_admin_user,
    test_admin_token,
    test_organization,
    test_user,
    async_session,
):
    """Test rejection requires a reason (422)."""
    import src.crud.user_user_type as crud
    from src.models.user_user_type import OnboardingStatus

    # Create user type
    user_type = UserType(
        name="Test",
        code="test_reject_reason",
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()

    # Create user_user_type
    uut_data = {
        "user_id": str(test_user.id),
        "user_type_id": str(user_type.id),
    }
    uut = await crud.create(async_session, uut_data, str(test_organization.id))
    await crud.update_status(
        async_session,
        str(uut.id),
        OnboardingStatus.PENDING_REVIEW,
        str(test_organization.id),
    )

    # Try to reject without reason
    response = await client.post(
        f"/api/v1/onboarding/review/{uut.id}/reject",
        json={},
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 422
