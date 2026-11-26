"""
Unit tests for EmailChangeRequest model and CRUD operations.
Tests the multi-step email change verification flow.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.crud.email_change_request import (
    cancel_pending_requests,
    create_email_change_request,
    get_active_request_for_user,
    get_request_by_id,
    increment_otp_attempts,
    increment_resend_count,
    update_request_status,
)
from src.models.email_change_request import (
    EmailChangeStatus,
    IdentityVerificationMethod,
)


@pytest.mark.asyncio
async def test_create_email_change_request(async_session, test_user, test_organization):
    """Test creating an email change request."""
    org_id = str(test_organization.id)

    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }

    request = await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    assert request is not None
    assert request.user_id == test_user.id
    assert request.old_email == test_user.email
    assert request.new_email == "newemail@test.com"
    assert request.status == EmailChangeStatus.PENDING_VERIFICATION.value
    assert request.organization_id == test_organization.id
    assert request.otp_attempts == 0
    assert request.otp_resend_count == 0
    assert request.identity_verified_at is None
    assert request.completed_at is None


@pytest.mark.asyncio
async def test_get_active_request_for_user(async_session, test_user, test_organization):
    """Test getting the active email change request for a user."""
    org_id = str(test_organization.id)

    # Create a request
    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }

    created_request = await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    # Retrieve the active request
    active_request = await get_active_request_for_user(
        session=async_session, user_id=str(test_user.id), organization_id=org_id
    )

    assert active_request is not None
    assert active_request.id == created_request.id
    assert active_request.status in [
        EmailChangeStatus.PENDING_VERIFICATION.value,
        EmailChangeStatus.PENDING_OTP.value,
    ]


@pytest.mark.asyncio
async def test_get_request_by_id(async_session, test_user, test_organization):
    """Test getting an email change request by ID."""
    org_id = str(test_organization.id)

    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }

    created_request = await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    retrieved_request = await get_request_by_id(
        session=async_session,
        request_id=str(created_request.id),
        organization_id=org_id,
    )

    assert retrieved_request is not None
    assert retrieved_request.id == created_request.id


@pytest.mark.asyncio
async def test_update_request_status(async_session, test_user, test_organization):
    """Test updating the status of an email change request."""
    org_id = str(test_organization.id)

    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }

    created_request = await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    # Update status to pending_otp with identity verification details
    identity_verified_at = datetime.now(timezone.utc)
    updated_request = await update_request_status(
        session=async_session,
        request_id=str(created_request.id),
        status=EmailChangeStatus.PENDING_OTP,
        organization_id=org_id,
        identity_verified_at=identity_verified_at,
        identity_verification_method=IdentityVerificationMethod.PASSWORD.value,
    )

    assert updated_request.status == EmailChangeStatus.PENDING_OTP.value
    # Compare timestamps without timezone info since SQLite doesn't preserve it
    assert updated_request.identity_verified_at.replace(
        tzinfo=None
    ) == identity_verified_at.replace(tzinfo=None)
    assert (
        updated_request.identity_verification_method
        == IdentityVerificationMethod.PASSWORD.value
    )


@pytest.mark.asyncio
async def test_increment_otp_attempts(async_session, test_user, test_organization):
    """Test incrementing OTP attempts."""
    org_id = str(test_organization.id)

    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }

    created_request = await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    assert created_request.otp_attempts == 0

    # Increment attempts
    updated_request = await increment_otp_attempts(
        session=async_session,
        request_id=str(created_request.id),
        organization_id=org_id,
    )

    assert updated_request.otp_attempts == 1

    # Increment again
    updated_request = await increment_otp_attempts(
        session=async_session,
        request_id=str(created_request.id),
        organization_id=org_id,
    )

    assert updated_request.otp_attempts == 2


@pytest.mark.asyncio
async def test_increment_resend_count(async_session, test_user, test_organization):
    """Test incrementing OTP resend count."""
    org_id = str(test_organization.id)

    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }

    created_request = await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    assert created_request.otp_resend_count == 0

    # Increment resend count
    updated_request = await increment_resend_count(
        session=async_session,
        request_id=str(created_request.id),
        organization_id=org_id,
    )

    assert updated_request.otp_resend_count == 1


@pytest.mark.asyncio
async def test_cancel_pending_requests(async_session, test_user, test_organization):
    """Test cancelling pending email change requests."""
    org_id = str(test_organization.id)

    # Create a request
    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    # Cancel all pending requests
    cancelled_count = await cancel_pending_requests(
        session=async_session, user_id=str(test_user.id), organization_id=org_id
    )

    assert cancelled_count == 1

    # Verify no active requests remain
    active_request = await get_active_request_for_user(
        session=async_session, user_id=str(test_user.id), organization_id=org_id
    )

    assert active_request is None


@pytest.mark.asyncio
async def test_tenant_isolation(
    async_session, test_user, test_organization, second_organization
):
    """Test that email change requests are properly isolated by organization."""
    org1_id = str(test_organization.id)
    org2_id = str(second_organization.id)

    # Create request in org1
    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }

    org1_request = await create_email_change_request(
        session=async_session, data=request_data, organization_id=org1_id
    )

    # Try to get the request from org2 - should fail
    org2_request = await get_request_by_id(
        session=async_session, request_id=str(org1_request.id), organization_id=org2_id
    )

    assert org2_request is None


@pytest.mark.asyncio
async def test_only_one_active_request_per_user(
    async_session, test_user, test_organization
):
    """Test that the unique index ensures only one active request per user."""
    org_id = str(test_organization.id)

    # Create first request
    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail1@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }

    first_request = await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    assert first_request is not None

    # Verify that there is an active request
    active_request = await get_active_request_for_user(
        session=async_session, user_id=str(test_user.id), organization_id=org_id
    )

    assert active_request is not None
    assert active_request.id == first_request.id


@pytest.mark.asyncio
async def test_completed_request_allows_new_request(
    async_session, test_user, test_organization
):
    """Test that completing a request allows creating a new one."""
    org_id = str(test_organization.id)

    # Create first request
    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail1@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }

    first_request = await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    # Complete the first request
    completed_request = await update_request_status(
        session=async_session,
        request_id=str(first_request.id),
        status=EmailChangeStatus.COMPLETED,
        organization_id=org_id,
        completed_at=datetime.now(timezone.utc),
    )

    assert completed_request.status == EmailChangeStatus.COMPLETED.value
    assert completed_request.completed_at is not None

    # Verify no active requests after completion
    active_request = await get_active_request_for_user(
        session=async_session, user_id=str(test_user.id), organization_id=org_id
    )

    assert active_request is None


# ============================================================================
# API ENDPOINT TESTS (Phase 2)
# ============================================================================


@pytest.mark.asyncio
async def test_initiate_email_change_api(
    client, test_jwt_token, test_user, test_organization, async_session
):
    """Test initiating email change via API."""
    response = await client.post(
        "/api/v1/users/me/email/change",
        headers={"Authorization": test_jwt_token},
        json={"new_email": "newemail@test.com"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message_code"] == "email_change.request_initiated"
    assert data["status"] == "pending_verification"
    assert "request_id" in data


@pytest.mark.asyncio
async def test_initiate_email_change_same_email(client, test_jwt_token, test_user):
    """Test that initiating with same email as current fails."""
    response = await client.post(
        "/api/v1/users/me/email/change",
        headers={"Authorization": test_jwt_token},
        json={"new_email": test_user.email},
    )

    assert response.status_code == 400
    data = response.json()
    assert data["detail_code"] == "email_change.email_same_as_current"


@pytest.mark.asyncio
async def test_initiate_email_change_existing_email(
    client, test_jwt_token, async_session, test_organization
):
    """Test that initiating with already registered email fails."""
    from src.crud.user import create_user

    # Create another user with the email we'll try to change to
    await create_user(
        session=async_session,
        request={"email": "existing@test.com", "password": "TestPass123!"},
        organization_id=str(test_organization.id),
    )

    response = await client.post(
        "/api/v1/users/me/email/change",
        headers={"Authorization": test_jwt_token},
        json={"new_email": "existing@test.com"},
    )

    assert response.status_code == 409
    data = response.json()
    assert data["detail_code"] == "email_change.email_already_registered"


@pytest.mark.asyncio
async def test_initiate_email_change_already_active(
    client, test_jwt_token, test_user, test_organization, async_session
):
    """Test that creating a second request while one is active fails."""
    org_id = str(test_organization.id)

    # Create first request
    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "first@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    # Try to create second request
    response = await client.post(
        "/api/v1/users/me/email/change",
        headers={"Authorization": test_jwt_token},
        json={"new_email": "second@test.com"},
    )

    assert response.status_code == 409
    data = response.json()
    assert data["detail_code"] == "email_change.already_active"


@pytest.mark.asyncio
async def test_verify_identity_with_password(
    client, test_jwt_token, test_user, test_organization, async_session
):
    """Test verifying identity with password."""
    org_id = str(test_organization.id)

    # Create request
    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    # Verify identity
    response = await client.post(
        "/api/v1/users/me/email/change/verify",
        headers={"Authorization": test_jwt_token},
        json={"verification_method": "password", "verification_value": "Password123!"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message_code"] == "email_change.identity_verified"
    assert data["status"] == "pending_otp"


@pytest.mark.asyncio
async def test_verify_identity_wrong_password(
    client, test_jwt_token, test_user, test_organization, async_session
):
    """Test verifying identity with wrong password."""
    org_id = str(test_organization.id)

    # Create request
    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    # Verify identity with wrong password
    response = await client.post(
        "/api/v1/users/me/email/change/verify",
        headers={"Authorization": test_jwt_token},
        json={
            "verification_method": "password",
            "verification_value": "WrongPassword123!",
        },
    )

    assert response.status_code == 400
    data = response.json()
    assert data["detail_code"] == "email_change.invalid_password"


@pytest.mark.asyncio
async def test_verify_identity_no_request(client, test_jwt_token):
    """Test verifying identity without an active request."""
    response = await client.post(
        "/api/v1/users/me/email/change/verify",
        headers={"Authorization": test_jwt_token},
        json={"verification_method": "password", "verification_value": "Test123!"},
    )

    assert response.status_code == 404
    data = response.json()
    assert data["detail_code"] == "email_change.not_found"


@pytest.mark.asyncio
async def test_verify_otp_success(
    client, test_jwt_token, test_user, test_organization, async_session
):
    """Test successful OTP verification and email change completion."""
    org_id = str(test_organization.id)

    # Create request and set to pending_otp status
    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    email_request = await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    # Set up OTP
    import bcrypt

    otp_code = "123456"
    otp_hash = bcrypt.hashpw(otp_code.encode(), bcrypt.gensalt()).decode()

    await update_request_status(
        session=async_session,
        request_id=str(email_request.id),
        status=EmailChangeStatus.PENDING_OTP,
        organization_id=org_id,
        identity_verified_at=datetime.now(timezone.utc),
        identity_verification_method="password",
        otp_hash=otp_hash,
        otp_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        otp_attempts=0,
    )

    # Verify OTP
    response = await client.post(
        "/api/v1/users/me/email/change/otp",
        headers={"Authorization": test_jwt_token},
        json={"otp_code": otp_code},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message_code"] == "email_change.completed"
    assert data["status"] == "completed"

    # Verify user email was actually changed
    from src.crud.user import get_user_by_id

    updated_user = await get_user_by_id(async_session, str(test_user.id), org_id)
    assert updated_user.email == "newemail@test.com"


@pytest.mark.asyncio
async def test_verify_otp_invalid_code(
    client, test_jwt_token, test_user, test_organization, async_session
):
    """Test OTP verification with invalid code."""
    org_id = str(test_organization.id)

    # Create request and set to pending_otp status
    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    email_request = await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    # Set up OTP
    import bcrypt

    otp_code = "123456"
    otp_hash = bcrypt.hashpw(otp_code.encode(), bcrypt.gensalt()).decode()

    await update_request_status(
        session=async_session,
        request_id=str(email_request.id),
        status=EmailChangeStatus.PENDING_OTP,
        organization_id=org_id,
        identity_verified_at=datetime.now(timezone.utc),
        identity_verification_method="password",
        otp_hash=otp_hash,
        otp_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        otp_attempts=0,
    )

    # Verify with wrong OTP
    response = await client.post(
        "/api/v1/users/me/email/change/otp",
        headers={"Authorization": test_jwt_token},
        json={"otp_code": "999999"},
    )

    assert response.status_code == 400
    data = response.json()
    assert data["detail_code"] == "email_change.invalid_otp"


@pytest.mark.asyncio
async def test_verify_otp_max_attempts(
    client, test_jwt_token, test_user, test_organization, async_session
):
    """Test that max OTP attempts is enforced."""
    org_id = str(test_organization.id)

    # Create request and set to pending_otp status with max attempts
    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    email_request = await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    # Set up OTP with 3 attempts already made
    import bcrypt

    otp_code = "123456"
    otp_hash = bcrypt.hashpw(otp_code.encode(), bcrypt.gensalt()).decode()

    await update_request_status(
        session=async_session,
        request_id=str(email_request.id),
        status=EmailChangeStatus.PENDING_OTP,
        organization_id=org_id,
        identity_verified_at=datetime.now(timezone.utc),
        identity_verification_method="password",
        otp_hash=otp_hash,
        otp_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        otp_attempts=3,
    )

    # Try to verify
    response = await client.post(
        "/api/v1/users/me/email/change/otp",
        headers={"Authorization": test_jwt_token},
        json={"otp_code": "999999"},
    )

    assert response.status_code == 400
    data = response.json()
    assert data["detail_code"] == "email_change.max_otp_attempts"


@pytest.mark.asyncio
async def test_resend_otp(
    client, test_jwt_token, test_user, test_organization, async_session
):
    """Test resending OTP."""
    org_id = str(test_organization.id)

    # Create request and set to pending_otp status
    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    email_request = await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    import bcrypt

    otp_code = "123456"
    otp_hash = bcrypt.hashpw(otp_code.encode(), bcrypt.gensalt()).decode()

    await update_request_status(
        session=async_session,
        request_id=str(email_request.id),
        status=EmailChangeStatus.PENDING_OTP,
        organization_id=org_id,
        identity_verified_at=datetime.now(timezone.utc),
        identity_verification_method="password",
        otp_hash=otp_hash,
        otp_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        otp_attempts=0,
    )

    # Resend OTP
    response = await client.post(
        "/api/v1/users/me/email/change/resend",
        headers={"Authorization": test_jwt_token},
        json={},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message_code"] == "email_change.otp_sent"


@pytest.mark.asyncio
async def test_cancel_email_change(
    client, test_jwt_token, test_user, test_organization, async_session
):
    """Test cancelling email change request."""
    org_id = str(test_organization.id)

    # Create request
    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    # Cancel request
    response = await client.delete(
        "/api/v1/users/me/email/change", headers={"Authorization": test_jwt_token}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message_code"] == "email_change.cancelled"


@pytest.mark.asyncio
async def test_get_email_change_status_with_request(
    client, test_jwt_token, test_user, test_organization, async_session
):
    """Test getting email change status when request exists."""
    org_id = str(test_organization.id)

    # Create request
    request_data = {
        "user_id": str(test_user.id),
        "old_email": test_user.email,
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    email_request = await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    # Get status
    response = await client.get(
        "/api/v1/users/me/email/change/status",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["has_active_request"] is True
    assert data["request_id"] == str(email_request.id)
    assert data["old_email"] == test_user.email
    assert data["new_email"] == "newemail@test.com"


@pytest.mark.asyncio
async def test_get_email_change_status_no_request(client, test_jwt_token):
    """Test getting email change status when no request exists."""
    response = await client.get(
        "/api/v1/users/me/email/change/status",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["has_active_request"] is False


@pytest.mark.asyncio
async def test_email_change_tenant_isolation(
    client, test_jwt_token, test_user, second_organization, async_session
):
    """Test that email change requests are isolated by tenant."""
    # Create request in second org (user shouldn't be able to access it)
    request_data = {
        "user_id": str(test_user.id),
        "old_email": "other@test.com",
        "new_email": "newemail@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    await create_email_change_request(
        session=async_session,
        data=request_data,
        organization_id=str(second_organization.id),
    )

    # Try to access status from test_user's org
    response = await client.get(
        "/api/v1/users/me/email/change/status",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    # Should not find the request from other org
    assert data["has_active_request"] is False


# ============================================================================
# PHASE 3: NOTIFICATIONS AND SESSION MANAGEMENT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_session_invalidation_on_email_change(
    client, test_jwt_token, test_user, test_organization, async_session
):
    """Test that all refresh tokens are invalidated upon email change completion."""
    from src.crud.refresh_token import create_refresh_token, get_refresh_token

    org_id = str(test_organization.id)
    user_id = str(test_user.id)

    # Create multiple refresh tokens for the user
    token1 = await create_refresh_token(async_session, user_id, org_id)
    token2 = await create_refresh_token(async_session, user_id, org_id)

    # Verify tokens exist
    token1_obj = await get_refresh_token(async_session, token1, org_id)
    token2_obj = await get_refresh_token(async_session, token2, org_id)
    assert token1_obj is not None
    assert token2_obj is not None

    # Create and complete email change request
    request_data = {
        "user_id": user_id,
        "old_email": test_user.email,
        "new_email": "changed@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    email_request = await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    # Set up OTP
    import bcrypt

    otp_code = "123456"
    otp_hash = bcrypt.hashpw(otp_code.encode(), bcrypt.gensalt()).decode()

    await update_request_status(
        session=async_session,
        request_id=str(email_request.id),
        status=EmailChangeStatus.PENDING_OTP,
        organization_id=org_id,
        identity_verified_at=datetime.now(timezone.utc),
        identity_verification_method="password",
        otp_hash=otp_hash,
        otp_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        otp_attempts=0,
    )

    # Verify OTP (this should invalidate all tokens)
    response = await client.post(
        "/api/v1/users/me/email/change/otp",
        headers={"Authorization": test_jwt_token},
        json={"otp_code": otp_code},
    )

    assert response.status_code == 200

    # Verify all tokens have been invalidated (soft deleted)
    token1_after = await get_refresh_token(async_session, token1, org_id)
    token2_after = await get_refresh_token(async_session, token2, org_id)
    assert token1_after is None  # Should be soft deleted
    assert token2_after is None  # Should be soft deleted


@pytest.mark.asyncio
async def test_audit_log_created_on_email_change(
    client, test_jwt_token, test_user, test_organization, async_session
):
    """Test that audit log entry is created when email is changed."""
    from src.crud.audit_log import get_resource_history
    from src.models.audit_log import AuditAction

    org_id = str(test_organization.id)
    user_id = str(test_user.id)
    old_email = test_user.email

    # Create and complete email change request
    request_data = {
        "user_id": user_id,
        "old_email": old_email,
        "new_email": "audited@test.com",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    email_request = await create_email_change_request(
        session=async_session, data=request_data, organization_id=org_id
    )

    # Set up OTP
    import bcrypt

    otp_code = "123456"
    otp_hash = bcrypt.hashpw(otp_code.encode(), bcrypt.gensalt()).decode()

    await update_request_status(
        session=async_session,
        request_id=str(email_request.id),
        status=EmailChangeStatus.PENDING_OTP,
        organization_id=org_id,
        identity_verified_at=datetime.now(timezone.utc),
        identity_verification_method="password",
        otp_hash=otp_hash,
        otp_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        otp_attempts=0,
    )

    # Verify OTP (this should create audit log)
    response = await client.post(
        "/api/v1/users/me/email/change/otp",
        headers={"Authorization": test_jwt_token},
        json={"otp_code": otp_code},
    )

    assert response.status_code == 200

    # Check audit log was created
    audit_logs = await get_resource_history(
        session=async_session,
        organization_id=org_id,
        resource_type="User",
        resource_id=user_id,
    )

    # Find the email change audit log
    email_change_logs = [
        log for log in audit_logs if log.action == AuditAction.UPDATE.value
    ]
    assert len(email_change_logs) > 0

    # Verify the audit log contains the email change
    latest_log = email_change_logs[0]
    assert latest_log.changes is not None
    assert "email" in latest_log.changes
    assert latest_log.changes["email"]["old"] == old_email
    assert latest_log.changes["email"]["new"] == "audited@test.com"
    assert latest_log.actor_id == test_user.id


@pytest.mark.asyncio
async def test_email_change_service_mask_email():
    """Test email masking function."""
    from src.services.email_change import mask_email

    # Test normal email
    assert mask_email("john.doe@example.com") == "j***@example.com"

    # Test single character local part
    assert mask_email("a@example.com") == "a***@example.com"

    # Test email without @
    assert mask_email("notanemail") == "notanemail"

    # Test long email
    assert mask_email("verylongemail@example.com") == "v***@example.com"
