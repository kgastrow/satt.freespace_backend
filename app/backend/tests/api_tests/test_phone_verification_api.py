"""
API tests for phone verification endpoints.

Tests verify:
- OTP sending
- OTP verification
- Rate limiting
- Phone format validation
- Tenant isolation
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import bcrypt
from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.phone_verification import PhoneVerification


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_sms_notification():
    """Mock SMS notification dispatcher for sending OTPs."""
    with patch(
        "src.services.phone_verification.notification_dispatcher.send_notification",
        new_callable=AsyncMock,
        return_value={"status": "sent", "message": "OTP sent"},
    ) as mock:
        yield mock


@pytest.fixture
async def phone_verification(async_session, test_organization, test_user):
    """Create a phone verification record."""
    otp_code = "123456"
    otp_hash = bcrypt.hashpw(otp_code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    verification = PhoneVerification(
        user_id=test_user.id,
        organization_id=test_organization.id,
        phone="+12025551234",
        otp_hash=otp_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        verified=False,
        attempts_count=0,
    )
    async_session.add(verification)
    await async_session.commit()
    await async_session.refresh(verification)
    return verification


# ============================================================================
# SEND OTP TESTS
# ============================================================================


class TestSendPhoneOTP:
    """Tests for POST /api/v1/user/me/phone/send-otp"""

    @pytest.mark.asyncio
    async def test_send_phone_otp_requires_auth(self, client: AsyncClient):
        """Test that sending OTP requires authentication."""
        response = await client.post(
            "/api/v1/user/me/phone/send-otp",
            json={"phone": "+12025551234"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_send_phone_otp_success(
        self,
        client: AsyncClient,
        test_jwt_token,
        mock_sms_notification,
    ):
        """Test successful OTP sending."""
        response = await client.post(
            "/api/v1/user/me/phone/send-otp",
            json={"phone": "+12025551234"},
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "verification_id" in data
        assert "expires_at" in data
        assert "message" in data

    @pytest.mark.asyncio
    async def test_send_phone_otp_validates_phone_format(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test that invalid phone format is rejected."""
        response = await client.post(
            "/api/v1/user/me/phone/send-otp",
            json={"phone": "not-a-phone"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_send_phone_otp_rejects_too_short(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test that too short phone number is rejected."""
        response = await client.post(
            "/api/v1/user/me/phone/send-otp",
            json={"phone": "123"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_send_phone_otp_phone_already_in_use(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_admin_user,
        mock_sms_notification,
    ):
        """Test that phone already in use by another user is rejected."""
        # test_admin_user has phone="+27737442554" and phone_verified=True
        response = await client.post(
            "/api/v1/user/me/phone/send-otp",
            json={"phone": test_admin_user.phone},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 409
        assert "already" in response.json().get("detail", "").lower()


# ============================================================================
# VERIFY OTP TESTS
# ============================================================================


class TestVerifyPhoneOTP:
    """Tests for POST /api/v1/user/me/phone/verify-otp"""

    @pytest.mark.asyncio
    async def test_verify_phone_otp_requires_auth(self, client: AsyncClient):
        """Test that verifying OTP requires authentication."""
        response = await client.post(
            "/api/v1/user/me/phone/verify-otp",
            json={"phone": "+12025551234", "otp_code": "123456"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_phone_otp_success(
        self,
        client: AsyncClient,
        test_jwt_token,
        phone_verification,
    ):
        """Test successful phone verification."""
        response = await client.post(
            "/api/v1/user/me/phone/verify-otp",
            json={"phone": "+12025551234", "otp_code": "123456"},
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["verified"] is True
        assert data["phone"] == "+12025551234"

    @pytest.mark.asyncio
    async def test_verify_phone_otp_wrong_code(
        self,
        client: AsyncClient,
        test_jwt_token,
        phone_verification,
    ):
        """Test that wrong OTP is rejected."""
        response = await client.post(
            "/api/v1/user/me/phone/verify-otp",
            json={"phone": "+12025551234", "otp_code": "000000"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400
        assert "invalid" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_verify_phone_otp_expired(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_jwt_token,
        phone_verification,
    ):
        """Test that expired OTP is rejected."""
        # Make OTP expired
        phone_verification.expires_at = datetime.now(timezone.utc) - timedelta(
            minutes=10
        )
        await async_session.commit()

        response = await client.post(
            "/api/v1/user/me/phone/verify-otp",
            json={"phone": "+12025551234", "otp_code": "123456"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400
        assert "expired" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_verify_phone_otp_max_attempts(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_jwt_token,
        phone_verification,
    ):
        """Test that verification locks after max attempts."""
        # Set attempts to max (3)
        phone_verification.attempts_count = 3
        await async_session.commit()

        response = await client.post(
            "/api/v1/user/me/phone/verify-otp",
            json={"phone": "+12025551234", "otp_code": "123456"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400
        assert "maximum" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_verify_phone_otp_no_verification_found(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test that verification fails when no OTP request exists."""
        response = await client.post(
            "/api/v1/user/me/phone/verify-otp",
            json={"phone": "+12025551234", "otp_code": "123456"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400
        assert "no active verification" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_verify_phone_otp_wrong_phone(
        self,
        client: AsyncClient,
        test_jwt_token,
        phone_verification,
    ):
        """Test that verification fails with wrong phone number."""
        # Use a different phone number than the fixture (which uses +12025551234)
        response = await client.post(
            "/api/v1/user/me/phone/verify-otp",
            json={"phone": "+12025559999", "otp_code": "123456"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_verify_phone_otp_increments_attempts(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_jwt_token,
        phone_verification,
    ):
        """Test that wrong OTP attempts are counted."""
        initial_attempts = phone_verification.attempts_count

        response = await client.post(
            "/api/v1/user/me/phone/verify-otp",
            json={"phone": "+12025551234", "otp_code": "000000"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400

        # Check attempts were incremented
        await async_session.refresh(phone_verification)
        assert phone_verification.attempts_count == initial_attempts + 1


# ============================================================================
# RATE LIMITING TESTS
# ============================================================================


class TestPhoneVerificationRateLimiting:
    """Tests for rate limiting on phone verification."""

    @pytest.mark.asyncio
    async def test_rate_limiting_on_send_otp(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_jwt_token,
        test_organization,
        test_user,
    ):
        """Test rate limiting on OTP sending (max 3 per hour per phone)."""
        # Create 3 verification records (to simulate rate limit being hit)
        for i in range(3):
            verification = PhoneVerification(
                user_id=test_user.id,
                organization_id=test_organization.id,
                phone="+12025551111",
                otp_hash="hash",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                verified=False,
                attempts_count=0,
            )
            async_session.add(verification)
        await async_session.commit()

        # Next request should be rate limited
        with patch(
            "src.services.phone_verification.notification_dispatcher.send_notification",
            new_callable=AsyncMock,
        ):
            response = await client.post(
                "/api/v1/user/me/phone/send-otp",
                json={"phone": "+12025551111"},
                headers={"Authorization": test_jwt_token},
            )

        assert response.status_code == 429
        assert "too many" in response.json().get("detail", "").lower()


# ============================================================================
# TENANT ISOLATION TESTS
# ============================================================================


class TestPhoneVerificationTenantIsolation:
    """Tests for multi-tenancy isolation in phone verification."""

    @pytest.mark.asyncio
    async def test_user_cannot_verify_other_org_otp(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_organization,
        second_organization,
        test_user,
        second_org_user,
        test_jwt_token,
    ):
        """Test that user from org1 cannot verify org2 phone OTP."""
        # Create OTP for second org user
        otp_code = "654321"
        otp_hash = bcrypt.hashpw(otp_code.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

        other_verification = PhoneVerification(
            user_id=second_org_user.id,
            organization_id=second_organization.id,
            phone="+12025559876",
            otp_hash=otp_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            verified=False,
            attempts_count=0,
        )
        async_session.add(other_verification)
        await async_session.commit()

        # test_user (org1) should not be able to verify second_org_user's OTP
        response = await client.post(
            "/api/v1/user/me/phone/verify-otp",
            json={"phone": "+12025559876", "otp_code": "654321"},
            headers={"Authorization": test_jwt_token},
        )
        # Should fail because no active verification for test_user with this phone
        assert response.status_code == 400
        assert "no active verification" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_phone_uniqueness_within_org(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_admin_user,
        mock_sms_notification,
    ):
        """Test that phone number uniqueness is enforced within organization."""
        # test_admin_user has phone="+27737442554" in test_organization
        # test_user (same org) should not be able to use this phone
        response = await client.post(
            "/api/v1/user/me/phone/send-otp",
            json={"phone": "+27737442554"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 409
        assert "already" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_phone_can_be_used_in_different_org(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        second_organization,
        second_org_user,
        test_admin_user,
    ):
        """Test that same phone can be used in different organization."""
        from src.core.security import create_access_token

        # Create token for second org user
        second_org_token = f"Bearer {create_access_token(
            user_id=str(second_org_user.id),
            organization_id=str(second_organization.id),
        )}"

        # Second org user should be able to use test_admin_user's phone
        # (they are in different organizations)
        with patch(
            "src.services.phone_verification.notification_dispatcher.send_notification",
            new_callable=AsyncMock,
            return_value={"status": "sent"},
        ):
            response = await client.post(
                "/api/v1/user/me/phone/send-otp",
                json={"phone": test_admin_user.phone},
                headers={"Authorization": second_org_token},
            )

        # Should succeed because phone is only used in test_organization
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_otp_requests_isolated_by_org(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_organization,
        second_organization,
        test_user,
        second_org_user,
    ):
        """Test that OTP requests are properly isolated by organization."""
        from src.core.security import create_access_token

        shared_phone = "+12025555555"

        # Create OTP for test_user in test_organization
        otp_code = "111111"
        otp_hash = bcrypt.hashpw(otp_code.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

        test_user_verification = PhoneVerification(
            user_id=test_user.id,
            organization_id=test_organization.id,
            phone=shared_phone,
            otp_hash=otp_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            verified=False,
            attempts_count=0,
        )
        async_session.add(test_user_verification)

        # Create OTP for second_org_user in second_organization (different code)
        otp_code_2 = "222222"
        otp_hash_2 = bcrypt.hashpw(otp_code_2.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

        second_user_verification = PhoneVerification(
            user_id=second_org_user.id,
            organization_id=second_organization.id,
            phone=shared_phone,
            otp_hash=otp_hash_2,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            verified=False,
            attempts_count=0,
        )
        async_session.add(second_user_verification)
        await async_session.commit()

        # Create tokens
        test_user_token = f"Bearer {create_access_token(
            user_id=str(test_user.id),
            organization_id=str(test_organization.id),
        )}"
        second_org_token = f"Bearer {create_access_token(
            user_id=str(second_org_user.id),
            organization_id=str(second_organization.id),
        )}"

        # test_user should verify with their OTP (111111), not the other org's OTP
        response = await client.post(
            "/api/v1/user/me/phone/verify-otp",
            json={"phone": shared_phone, "otp_code": "111111"},
            headers={"Authorization": test_user_token},
        )
        assert response.status_code == 200

        # second_org_user should verify with their OTP (222222)
        response = await client.post(
            "/api/v1/user/me/phone/verify-otp",
            json={"phone": shared_phone, "otp_code": "222222"},
            headers={"Authorization": second_org_token},
        )
        assert response.status_code == 200
