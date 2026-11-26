"""
API tests for email change endpoints.

Tests verify:
- Email change initiation
- Identity verification (password/2FA)
- OTP verification
- Rate limiting
- Tenant isolation
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.email_change_request import EmailChangeRequest, EmailChangeStatus


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
async def email_change_request(async_session, test_organization, test_user):
    """Create a pending email change request."""
    request = EmailChangeRequest(
        user_id=test_user.id,
        organization_id=test_organization.id,
        old_email=test_user.email,
        new_email="newemail@test.com",
        status=EmailChangeStatus.PENDING_VERIFICATION.value,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    async_session.add(request)
    await async_session.commit()
    await async_session.refresh(request)
    return request


@pytest.fixture
async def verified_email_change_request(async_session, test_organization, test_user):
    """Create an email change request with identity verified and pending OTP."""
    import bcrypt

    otp_code = "123456"
    otp_hash = bcrypt.hashpw(otp_code.encode(), bcrypt.gensalt()).decode()

    request = EmailChangeRequest(
        user_id=test_user.id,
        organization_id=test_organization.id,
        old_email=test_user.email,
        new_email="newemail@test.com",
        status=EmailChangeStatus.PENDING_OTP.value,
        identity_verified_at=datetime.now(timezone.utc),
        identity_verification_method="password",
        otp_hash=otp_hash,
        otp_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        otp_attempts=0,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    async_session.add(request)
    await async_session.commit()
    await async_session.refresh(request)
    return request


# ============================================================================
# INITIATION TESTS
# ============================================================================


class TestInitiateEmailChange:
    """Tests for POST /api/v1/users/me/email/change"""

    @pytest.mark.asyncio
    async def test_initiate_email_change_requires_auth(self, client: AsyncClient):
        """Test that initiating email change requires authentication."""
        response = await client.post(
            "/api/v1/users/me/email/change",
            json={"new_email": "new@test.com"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_initiate_email_change_success(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_user,
        test_organization,
    ):
        """Test successful email change initiation."""
        response = await client.post(
            "/api/v1/users/me/email/change",
            json={"new_email": "newemail@test.com"},
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data
        assert data["status"] == EmailChangeStatus.PENDING_VERIFICATION.value
        assert "message" in data

    @pytest.mark.asyncio
    async def test_initiate_email_change_validates_email(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test that invalid email format is rejected."""
        response = await client.post(
            "/api/v1/users/me/email/change",
            json={"new_email": "not-a-valid-email"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_initiate_email_change_rejects_same_email(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_user,
    ):
        """Test that changing to current email is rejected."""
        response = await client.post(
            "/api/v1/users/me/email/change",
            json={"new_email": test_user.email},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400
        assert "same as current" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_initiate_email_change_rejects_existing_email(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_admin_user,
    ):
        """Test that changing to another user's email is rejected."""
        response = await client.post(
            "/api/v1/users/me/email/change",
            json={"new_email": test_admin_user.email},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 409
        assert "already registered" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_initiate_email_change_rejects_when_active_request_exists(
        self,
        client: AsyncClient,
        test_jwt_token,
        email_change_request,
    ):
        """Test that initiating fails when an active request exists."""
        response = await client.post(
            "/api/v1/users/me/email/change",
            json={"new_email": "anotheremail@test.com"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 409
        assert "already active" in response.json().get("detail", "").lower()


# ============================================================================
# IDENTITY VERIFICATION TESTS
# ============================================================================


class TestVerifyIdentity:
    """Tests for POST /api/v1/users/me/email/change/verify"""

    @pytest.mark.asyncio
    async def test_verify_identity_requires_auth(self, client: AsyncClient):
        """Test that identity verification requires authentication."""
        response = await client.post(
            "/api/v1/users/me/email/change/verify",
            json={"verification_method": "password", "verification_value": "test123"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_identity_with_password_success(
        self,
        client: AsyncClient,
        test_jwt_token,
        email_change_request,
    ):
        """Test successful identity verification with password."""
        with patch(
            "src.services.email_change.email_change_service.send_otp_to_new_email",
            new_callable=AsyncMock,
        ):
            response = await client.post(
                "/api/v1/users/me/email/change/verify",
                json={
                    "verification_method": "password",
                    "verification_value": "Password123!",
                },
                headers={"Authorization": test_jwt_token},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == EmailChangeStatus.PENDING_OTP.value
        assert "verified" in data.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_verify_identity_wrong_password_rejected(
        self,
        client: AsyncClient,
        test_jwt_token,
        email_change_request,
    ):
        """Test that wrong password is rejected."""
        response = await client.post(
            "/api/v1/users/me/email/change/verify",
            json={
                "verification_method": "password",
                "verification_value": "WrongPassword123!",
            },
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400
        assert "invalid password" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_verify_identity_no_active_request(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test that verification fails without active request."""
        response = await client.post(
            "/api/v1/users/me/email/change/verify",
            json={
                "verification_method": "password",
                "verification_value": "Password123!",
            },
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 404
        # Message is "No active email change request found"
        assert "no active" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_verify_identity_expired_request(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_jwt_token,
        email_change_request,
    ):
        """Test that verification fails for expired request."""
        # Make the request expired
        email_change_request.expires_at = datetime.now(timezone.utc) - timedelta(
            hours=1
        )
        await async_session.commit()

        response = await client.post(
            "/api/v1/users/me/email/change/verify",
            json={
                "verification_method": "password",
                "verification_value": "Password123!",
            },
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400
        assert "expired" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_verify_identity_totp_not_implemented(
        self,
        client: AsyncClient,
        test_jwt_token,
        email_change_request,
    ):
        """Test that TOTP verification returns 501 (not yet implemented)."""
        response = await client.post(
            "/api/v1/users/me/email/change/verify",
            json={"verification_method": "totp", "verification_value": "123456"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 501


# ============================================================================
# OTP VERIFICATION TESTS
# ============================================================================


class TestVerifyOTP:
    """Tests for POST /api/v1/users/me/email/change/otp"""

    @pytest.mark.asyncio
    async def test_verify_otp_requires_auth(self, client: AsyncClient):
        """Test that OTP verification requires authentication."""
        response = await client.post(
            "/api/v1/users/me/email/change/otp",
            json={"otp_code": "123456"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_otp_success(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_jwt_token,
        verified_email_change_request,
    ):
        """Test successful OTP verification completes email change."""
        with patch(
            "src.services.email_change.email_change_service.send_change_confirmation_to_old_email",
            new_callable=AsyncMock,
        ), patch(
            "src.services.email_change.email_change_service.send_change_confirmation_to_new_email",
            new_callable=AsyncMock,
        ):
            response = await client.post(
                "/api/v1/users/me/email/change/otp",
                json={"otp_code": "123456"},
                headers={"Authorization": test_jwt_token},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == EmailChangeStatus.COMPLETED.value
        assert "successfully" in data.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_verify_otp_wrong_code_rejected(
        self,
        client: AsyncClient,
        test_jwt_token,
        verified_email_change_request,
    ):
        """Test that wrong OTP code is rejected."""
        response = await client.post(
            "/api/v1/users/me/email/change/otp",
            json={"otp_code": "000000"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400
        assert "invalid otp" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_verify_otp_expired_rejected(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_jwt_token,
        verified_email_change_request,
    ):
        """Test that expired OTP is rejected."""
        # Make OTP expired
        verified_email_change_request.otp_expires_at = datetime.now(
            timezone.utc
        ) - timedelta(minutes=10)
        await async_session.commit()

        response = await client.post(
            "/api/v1/users/me/email/change/otp",
            json={"otp_code": "123456"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400
        assert "expired" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_verify_otp_max_attempts_exceeded(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_jwt_token,
        verified_email_change_request,
    ):
        """Test that max OTP attempts blocks further attempts."""
        # Set attempts to max
        verified_email_change_request.otp_attempts = 3
        await async_session.commit()

        response = await client.post(
            "/api/v1/users/me/email/change/otp",
            json={"otp_code": "123456"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400
        assert "maximum" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_verify_otp_no_active_request(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test that OTP verification fails without active request."""
        response = await client.post(
            "/api/v1/users/me/email/change/otp",
            json={"otp_code": "123456"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_verify_otp_invalid_format(
        self,
        client: AsyncClient,
        test_jwt_token,
        verified_email_change_request,
    ):
        """Test that non-numeric OTP is rejected."""
        response = await client.post(
            "/api/v1/users/me/email/change/otp",
            json={"otp_code": "abcdef"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 422


# ============================================================================
# RESEND OTP TESTS
# ============================================================================


class TestResendOTP:
    """Tests for POST /api/v1/users/me/email/change/resend"""

    @pytest.mark.asyncio
    async def test_resend_otp_requires_auth(self, client: AsyncClient):
        """Test that resending OTP requires authentication."""
        response = await client.post(
            "/api/v1/users/me/email/change/resend",
            json={},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_resend_otp_success(
        self,
        client: AsyncClient,
        test_jwt_token,
        verified_email_change_request,
    ):
        """Test successful OTP resend."""
        with patch(
            "src.services.email_change.email_change_service.send_otp_to_new_email",
            new_callable=AsyncMock,
        ):
            response = await client.post(
                "/api/v1/users/me/email/change/resend",
                json={},
                headers={"Authorization": test_jwt_token},
            )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_resend_otp_no_active_request(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test that resend fails without active request."""
        response = await client.post(
            "/api/v1/users/me/email/change/resend",
            json={},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_resend_otp_max_resends_exceeded(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_jwt_token,
        verified_email_change_request,
    ):
        """Test that max resends blocks further resend attempts."""
        # Set resend count to max
        verified_email_change_request.otp_resend_count = 3
        await async_session.commit()

        response = await client.post(
            "/api/v1/users/me/email/change/resend",
            json={},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400
        assert "maximum" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_resend_otp_wrong_status(
        self,
        client: AsyncClient,
        test_jwt_token,
        email_change_request,
    ):
        """Test that resend fails if not in pending_otp status."""
        # email_change_request is in pending_verification status
        response = await client.post(
            "/api/v1/users/me/email/change/resend",
            json={},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 400
        assert "not in otp verification" in response.json().get("detail", "").lower()


# ============================================================================
# CANCELLATION TESTS
# ============================================================================


class TestCancelEmailChange:
    """Tests for DELETE /api/v1/users/me/email/change"""

    @pytest.mark.asyncio
    async def test_cancel_email_change_requires_auth(self, client: AsyncClient):
        """Test that cancelling requires authentication."""
        response = await client.delete("/api/v1/users/me/email/change")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_cancel_email_change_success(
        self,
        client: AsyncClient,
        test_jwt_token,
        email_change_request,
    ):
        """Test successful email change cancellation."""
        response = await client.delete(
            "/api/v1/users/me/email/change",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "cancelled" in data.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_cancel_email_change_no_active_request(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test that cancellation fails without active request."""
        response = await client.delete(
            "/api/v1/users/me/email/change",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 404


# ============================================================================
# STATUS TESTS
# ============================================================================


class TestGetEmailChangeStatus:
    """Tests for GET /api/v1/users/me/email/change/status"""

    @pytest.mark.asyncio
    async def test_get_status_requires_auth(self, client: AsyncClient):
        """Test that getting status requires authentication."""
        response = await client.get("/api/v1/users/me/email/change/status")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_status_with_active_request(
        self,
        client: AsyncClient,
        test_jwt_token,
        email_change_request,
    ):
        """Test getting status when active request exists."""
        response = await client.get(
            "/api/v1/users/me/email/change/status",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_active_request"] is True
        assert data["request_id"] == str(email_change_request.id)
        assert data["old_email"] == email_change_request.old_email
        assert data["new_email"] == email_change_request.new_email
        assert data["status"] == EmailChangeStatus.PENDING_VERIFICATION.value

    @pytest.mark.asyncio
    async def test_get_status_no_active_request(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test getting status when no active request exists."""
        response = await client.get(
            "/api/v1/users/me/email/change/status",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_active_request"] is False


# ============================================================================
# TENANT ISOLATION TESTS
# ============================================================================


class TestEmailChangeTenantIsolation:
    """Tests for multi-tenancy isolation in email change."""

    @pytest.mark.asyncio
    async def test_user_cannot_see_other_org_email_change(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_organization,
        second_organization,
        test_user,
        second_org_user,
        test_jwt_token,
    ):
        """Test that user from org1 cannot see org2 email change requests."""
        # Create email change request for second org user
        from src.core.security import create_access_token

        second_org_token = f"Bearer {create_access_token(
            user_id=str(second_org_user.id),
            organization_id=str(second_organization.id),
        )}"

        other_request = EmailChangeRequest(
            user_id=second_org_user.id,
            organization_id=second_organization.id,
            old_email=second_org_user.email,
            new_email="other@test.com",
            status=EmailChangeStatus.PENDING_VERIFICATION.value,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        async_session.add(other_request)
        await async_session.commit()

        # test_user should not see second_org_user's request
        response = await client.get(
            "/api/v1/users/me/email/change/status",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_active_request"] is False

        # second_org_user should see their own request
        response = await client.get(
            "/api/v1/users/me/email/change/status",
            headers={"Authorization": second_org_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_active_request"] is True
        assert data["request_id"] == str(other_request.id)

    @pytest.mark.asyncio
    async def test_email_uniqueness_within_org(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_jwt_token,
        second_org_user,
    ):
        """Test that email uniqueness is enforced within same organization."""
        # test_admin_user is in same org as test_user
        # So using their email should fail
        # But second_org_user's email should work (different org)
        response = await client.post(
            "/api/v1/users/me/email/change",
            json={"new_email": second_org_user.email},
            headers={"Authorization": test_jwt_token},
        )
        # Should succeed because second_org_user is in a different organization
        assert response.status_code == 200
