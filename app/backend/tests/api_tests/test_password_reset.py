"""
Tests for password reset functionality.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
import pytest

from src.core.security import verify_password
from src.models.user_otp import OTPType, UserOTP


class TestPasswordResetRequest:
    """Tests for POST /api/auth/password-reset/request"""

    @pytest.mark.asyncio
    async def test_password_reset_request_success(
        self, client: AsyncClient, test_user, test_organization, async_session
    ):
        """Test successful password reset request."""
        # Mock the task queue to avoid Redis connection
        with patch(
            "src.services.tasks.TaskQueue.enqueue_password_reset_email",
            new_callable=AsyncMock,
        ) as mock_enqueue:
            mock_enqueue.return_value = "mock-job-id"

            response = await client.post(
                "/api/v1/auth/password-reset/request",
                json={
                    "email": test_user.email,
                    "organization_slug": test_organization.slug,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert "password reset link has been sent" in data["message"]

            # Verify email task was enqueued
            mock_enqueue.assert_called_once()
            call_kwargs = mock_enqueue.call_args.kwargs
            assert call_kwargs["to"] == test_user.email
            assert "reset_token" in call_kwargs
            assert "reset_url" in call_kwargs

        # Verify token was created in database
        from sqlalchemy import select

        result = await async_session.execute(
            select(UserOTP).where(
                UserOTP.user_id == test_user.id,
                UserOTP.otp_type == OTPType.PASSWORD_RESET.value,
                UserOTP.is_used == False,  # noqa: E712
            )
        )
        otp = result.scalars().first()
        assert otp is not None
        assert len(otp.otp_code) > 20  # Should be a long token, not 4-digit OTP

    @pytest.mark.asyncio
    async def test_password_reset_request_nonexistent_email(
        self, client: AsyncClient, test_organization
    ):
        """Test password reset with nonexistent email returns success (security)."""
        response = await client.post(
            "/api/v1/auth/password-reset/request",
            json={
                "email": "nonexistent@test.com",
                "organization_slug": test_organization.slug,
            },
        )
        # Should return success for security (don't reveal if email exists)
        assert response.status_code == 200
        data = response.json()
        assert "password reset link has been sent" in data["message"]

    @pytest.mark.asyncio
    async def test_password_reset_request_nonexistent_org(
        self, client: AsyncClient, test_user
    ):
        """Test password reset with nonexistent organization returns success (security)."""
        response = await client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": test_user.email, "organization_slug": "nonexistent-org"},
        )
        # Should return success for security (don't reveal if org exists)
        assert response.status_code == 200
        data = response.json()
        assert "password reset link has been sent" in data["message"]

    @pytest.mark.asyncio
    async def test_password_reset_request_unverified_email(
        self, client: AsyncClient, test_organization, async_session
    ):
        """Test password reset for unverified email returns success but doesn't send email."""
        from src.core.security import hash_password
        from src.models.user import User

        # Create unverified user
        unverified_user = User(
            email="unverified@test.com",
            password=hash_password("Password123!"),
            email_verified=False,
            organization_id=test_organization.id,
        )
        async_session.add(unverified_user)
        await async_session.commit()

        response = await client.post(
            "/api/v1/auth/password-reset/request",
            json={
                "email": "unverified@test.com",
                "organization_slug": test_organization.slug,
            },
        )
        # Should return success for security
        assert response.status_code == 200

        # But no token should be created
        from sqlalchemy import select

        result = await async_session.execute(
            select(UserOTP).where(
                UserOTP.user_id == unverified_user.id,
                UserOTP.otp_type == OTPType.PASSWORD_RESET.value,
            )
        )
        otp = result.scalars().first()
        assert otp is None


class TestPasswordResetConfirm:
    """Tests for POST /api/auth/password-reset/confirm"""

    @pytest.mark.asyncio
    async def test_password_reset_confirm_success(
        self, client: AsyncClient, test_user, test_organization, async_session
    ):
        """Test successful password reset confirmation."""
        # First, create a password reset token
        from src.crud.user_otp import create_password_reset_token

        token = await create_password_reset_token(
            session=async_session,
            user_id=test_user.id,
            organization_id=str(test_organization.id),
        )

        # Now confirm the reset
        new_password = "NewSecurePassword123!"
        response = await client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "token": token,
                "new_password": new_password,
                "organization_slug": test_organization.slug,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "successfully" in data["message"]

        # Verify password was changed
        await async_session.refresh(test_user)
        assert verify_password(new_password, test_user.password)

    @pytest.mark.asyncio
    async def test_password_reset_confirm_invalid_token(
        self, client: AsyncClient, test_organization
    ):
        """Test password reset with invalid token."""
        response = await client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "token": "invalid-token-12345",
                "new_password": "NewPassword123!",
                "organization_slug": test_organization.slug,
            },
        )
        assert response.status_code == 400
        assert "Invalid or expired" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_password_reset_confirm_expired_token(
        self, client: AsyncClient, test_user, test_organization, async_session
    ):
        """Test password reset with expired token."""
        # Create an expired token
        expired_token = UserOTP(
            user_id=test_user.id,
            organization_id=test_organization.id,
            otp_code="expired-token-12345",
            otp_type=OTPType.PASSWORD_RESET.value,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=2),  # Expired
            is_used=False,
        )
        async_session.add(expired_token)
        await async_session.commit()

        response = await client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "token": "expired-token-12345",
                "new_password": "NewPassword123!",
                "organization_slug": test_organization.slug,
            },
        )
        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_password_reset_confirm_used_token(
        self, client: AsyncClient, test_user, test_organization, async_session
    ):
        """Test password reset with already used token."""
        # Create a used token
        used_token = UserOTP(
            user_id=test_user.id,
            organization_id=test_organization.id,
            otp_code="used-token-12345",
            otp_type=OTPType.PASSWORD_RESET.value,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            is_used=True,  # Already used
        )
        async_session.add(used_token)
        await async_session.commit()

        response = await client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "token": "used-token-12345",
                "new_password": "NewPassword123!",
                "organization_slug": test_organization.slug,
            },
        )
        assert response.status_code == 400
        assert "Invalid or expired" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_password_reset_confirm_short_password(
        self, client: AsyncClient, test_user, test_organization, async_session
    ):
        """Test password reset with too short password."""
        from src.crud.user_otp import create_password_reset_token

        token = await create_password_reset_token(
            session=async_session,
            user_id=test_user.id,
            organization_id=str(test_organization.id),
        )

        response = await client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "token": token,
                "new_password": "short",  # Too short
                "organization_slug": test_organization.slug,
            },
        )
        # Pydantic validation returns 422 for min_length constraint
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any("8" in str(err) for err in errors)

    @pytest.mark.asyncio
    async def test_password_reset_invalidates_sessions(
        self, client: AsyncClient, test_user, test_organization, async_session
    ):
        """Test that password reset invalidates all refresh tokens."""
        from sqlalchemy import select

        from src.crud.user_otp import create_password_reset_token
        from src.models.refresh_token import RefreshToken

        # Create some refresh tokens for the user
        for i in range(3):
            token = RefreshToken(
                user_id=test_user.id,
                organization_id=test_organization.id,
                token=f"refresh-token-{i}",
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
            async_session.add(token)
        await async_session.commit()

        # Create password reset token and confirm
        reset_token = await create_password_reset_token(
            session=async_session,
            user_id=test_user.id,
            organization_id=str(test_organization.id),
        )

        response = await client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "token": reset_token,
                "new_password": "NewSecurePassword123!",
                "organization_slug": test_organization.slug,
            },
        )
        assert response.status_code == 200

        # Verify all refresh tokens are soft-deleted
        result = await async_session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == test_user.id,
                RefreshToken.deleted_time.is_(None),
            )
        )
        tokens = result.scalars().all()
        assert len(tokens) == 0


class TestPasswordResetMultiTenancy:
    """Tests for password reset multi-tenancy isolation."""

    @pytest.mark.asyncio
    async def test_password_reset_token_org_isolation(
        self,
        client: AsyncClient,
        test_user,
        test_organization,
        second_organization,
        async_session,
    ):
        """Test that password reset token from one org can't be used in another."""
        from src.crud.user_otp import create_password_reset_token

        # Create token for test_organization
        token = await create_password_reset_token(
            session=async_session,
            user_id=test_user.id,
            organization_id=str(test_organization.id),
        )

        # Try to use token with different organization
        response = await client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "token": token,
                "new_password": "NewPassword123!",
                "organization_slug": second_organization.slug,  # Wrong org
            },
        )
        assert response.status_code == 400
        assert "Invalid or expired" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_password_reset_wrong_org_user(
        self,
        client: AsyncClient,
        test_user,
        test_organization,
        second_organization,
        second_org_user,
        async_session,
    ):
        """Test that user can't reset password through wrong organization."""
        # Request reset with user email but wrong organization
        response = await client.post(
            "/api/v1/auth/password-reset/request",
            json={
                "email": test_user.email,  # User in test_organization
                "organization_slug": second_organization.slug,  # Different org
            },
        )
        # Should return success for security
        assert response.status_code == 200

        # But no token should be created (user not in that org)
        from sqlalchemy import select

        result = await async_session.execute(
            select(UserOTP).where(
                UserOTP.user_id == test_user.id,
                UserOTP.otp_type == OTPType.PASSWORD_RESET.value,
                UserOTP.organization_id == second_organization.id,
            )
        )
        otp = result.scalars().first()
        assert otp is None
