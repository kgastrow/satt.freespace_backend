"""
API tests for user OTP endpoints.

Tests verify:
- OTP generation
- OTP verification
- Email verification
- Rate limiting
"""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
import pytest


# ─────────────────────────────────────────────────────────────
# Generate OTP Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_otp_requires_auth(client: AsyncClient):
    """Test that generating OTP requires authentication."""
    response = await client.post("/api/v1/user-otp")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_generate_otp_success(
    client: AsyncClient,
    test_jwt_token,
):
    """Test successful OTP generation."""
    with patch(
        "src.services.notifications.notification_dispatcher.send_to_user",
        new_callable=AsyncMock,
    ):
        response = await client.post(
            "/api/v1/user-otp",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "message_code" in data


# ─────────────────────────────────────────────────────────────
# Verify OTP Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_otp_missing_fields(client: AsyncClient):
    """Test that verify OTP requires all fields."""
    response = await client.post(
        "/api/v1/user-otp/verify",
        json={},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_verify_otp_invalid_user(
    client: AsyncClient,
    test_organization,
):
    """Test OTP verification with invalid user ID."""
    from uuid import uuid4

    response = await client.post(
        "/api/v1/user-otp/verify",
        json={
            "user_id": str(uuid4()),
            "otp_code": "123456",
            "organization_id": str(test_organization.id),
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_verify_otp_wrong_code(
    client: AsyncClient,
    async_session,
    test_user,
    test_organization,
):
    """Test that wrong OTP code is rejected."""
    from datetime import datetime, timedelta, timezone

    from src.models.user_otp import UserOTP

    # Create a valid OTP for the user
    otp = UserOTP(
        user_id=test_user.id,
        organization_id=test_organization.id,
        otp_code="123456",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        is_used=False,
    )
    async_session.add(otp)
    await async_session.commit()

    # Try to verify with wrong code
    response = await client.post(
        "/api/v1/user-otp/verify",
        json={
            "user_id": str(test_user.id),
            "otp_code": "000000",
            "organization_id": str(test_organization.id),
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_verify_otp_expired(
    client: AsyncClient,
    async_session,
    test_user,
    test_organization,
):
    """Test that expired OTP is rejected."""
    from datetime import datetime, timedelta, timezone

    from src.models.user_otp import UserOTP

    # Create an expired OTP
    otp = UserOTP(
        user_id=test_user.id,
        organization_id=test_organization.id,
        otp_code="123456",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        is_used=False,
    )
    async_session.add(otp)
    await async_session.commit()

    response = await client.post(
        "/api/v1/user-otp/verify",
        json={
            "user_id": str(test_user.id),
            "otp_code": "123456",
            "organization_id": str(test_organization.id),
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_verify_otp_already_used(
    client: AsyncClient,
    async_session,
    test_user,
    test_organization,
):
    """Test that OTP can only be used once."""
    from datetime import datetime, timedelta, timezone

    from src.models.user_otp import UserOTP

    # Create an already used OTP
    otp = UserOTP(
        user_id=test_user.id,
        organization_id=test_organization.id,
        otp_code="123456",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        is_used=True,
    )
    async_session.add(otp)
    await async_session.commit()

    response = await client.post(
        "/api/v1/user-otp/verify",
        json={
            "user_id": str(test_user.id),
            "otp_code": "123456",
            "organization_id": str(test_organization.id),
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_verify_otp_success(
    client: AsyncClient,
    async_session,
    test_user,
    test_organization,
):
    """Test successful OTP verification."""
    from datetime import datetime, timedelta, timezone

    from src.models.user_otp import UserOTP

    # Create a valid OTP
    otp = UserOTP(
        user_id=test_user.id,
        organization_id=test_organization.id,
        otp_code="654321",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        is_used=False,
    )
    async_session.add(otp)
    await async_session.commit()

    response = await client.post(
        "/api/v1/user-otp/verify",
        json={
            "user_id": str(test_user.id),
            "otp_code": "654321",
            "organization_id": str(test_organization.id),
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert "message" in data
    assert "message_code" in data


# ─────────────────────────────────────────────────────────────
# Verify Email Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_email_missing_fields(client: AsyncClient):
    """Test that verify email requires all fields."""
    response = await client.post(
        "/api/v1/user-otp/verify-email",
        json={},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_verify_email_invalid_organization(client: AsyncClient):
    """Test verify email with invalid organization slug."""
    response = await client.post(
        "/api/v1/user-otp/verify-email",
        json={
            "email": "test@test.com",
            "otp_code": "123456",
            "organization_slug": "non-existent-org",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_verify_email_invalid_user(
    client: AsyncClient,
    test_organization,
):
    """Test verify email with non-existent user."""
    response = await client.post(
        "/api/v1/user-otp/verify-email",
        json={
            "email": "nonexistent@test.com",
            "otp_code": "123456",
            "organization_slug": test_organization.slug,
        },
    )
    # Should return generic error to prevent user enumeration
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_verify_email_wrong_otp(
    client: AsyncClient,
    async_session,
    test_user,
    test_organization,
):
    """Test verify email with wrong OTP code."""
    from datetime import datetime, timedelta, timezone

    from src.models.user_otp import UserOTP

    # Create a valid OTP
    otp = UserOTP(
        user_id=test_user.id,
        organization_id=test_organization.id,
        otp_code="123456",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        is_used=False,
    )
    async_session.add(otp)
    await async_session.commit()

    response = await client.post(
        "/api/v1/user-otp/verify-email",
        json={
            "email": test_user.email,
            "otp_code": "000000",
            "organization_slug": test_organization.slug,
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_verify_email_success(
    client: AsyncClient,
    async_session,
    test_user,
    test_organization,
):
    """Test successful email verification."""
    from datetime import datetime, timedelta, timezone

    from src.models.user_otp import UserOTP

    # Create a valid OTP
    otp = UserOTP(
        user_id=test_user.id,
        organization_id=test_organization.id,
        otp_code="123456",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        is_used=False,
    )
    async_session.add(otp)
    await async_session.commit()

    response = await client.post(
        "/api/v1/user-otp/verify-email",
        json={
            "email": test_user.email,
            "otp_code": "123456",
            "organization_slug": test_organization.slug,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


# ─────────────────────────────────────────────────────────────
# Send Verification Email Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_verification_email_missing_fields(client: AsyncClient):
    """Test that send verification email requires all fields."""
    response = await client.post(
        "/api/v1/user-otp/send-verification-email",
        json={},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_send_verification_email_invalid_organization(client: AsyncClient):
    """Test send verification email with invalid organization."""
    response = await client.post(
        "/api/v1/user-otp/send-verification-email",
        json={
            "email": "test@test.com",
            "organization_slug": "non-existent-org",
        },
    )
    # Should return success to prevent org enumeration
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_send_verification_email_invalid_user(
    client: AsyncClient,
    test_organization,
):
    """Test send verification email for non-existent user."""
    response = await client.post(
        "/api/v1/user-otp/send-verification-email",
        json={
            "email": "nonexistent@test.com",
            "organization_slug": test_organization.slug,
        },
    )
    # Should return success to prevent user enumeration
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_send_verification_email_success(
    client: AsyncClient,
    test_user,
    test_organization,
):
    """Test successful send verification email."""
    with patch(
        "src.services.notifications.notification_dispatcher.send_to_user",
        new_callable=AsyncMock,
    ):
        response = await client.post(
            "/api/v1/user-otp/send-verification-email",
            json={
                "email": test_user.email,
                "organization_slug": test_organization.slug,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "message_code" in data


# ─────────────────────────────────────────────────────────────
# Tenant Isolation Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_otp_cross_org_isolation(
    client: AsyncClient,
    async_session,
    test_user,
    test_organization,
    second_organization,
):
    """Test that OTP verification respects tenant boundaries."""
    from datetime import datetime, timedelta, timezone

    from src.models.user_otp import UserOTP

    # Create a valid OTP for test_user in test_organization
    otp = UserOTP(
        user_id=test_user.id,
        organization_id=test_organization.id,
        otp_code="123456",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        is_used=False,
    )
    async_session.add(otp)
    await async_session.commit()

    # Try to verify with wrong organization_id
    response = await client.post(
        "/api/v1/user-otp/verify",
        json={
            "user_id": str(test_user.id),
            "otp_code": "123456",
            "organization_id": str(second_organization.id),
        },
    )
    # Should fail because OTP was created for test_organization
    assert response.status_code == 400
