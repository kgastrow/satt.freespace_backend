"""
Phone Verification Service.

Manages OTP generation, SMS sending, and verification with rate limiting.
"""

from datetime import datetime, timedelta, timezone
import secrets
from typing import Any

import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession

from src.crud import phone_verification as phone_verification_crud
from src.crud import user as user_crud
from src.logger.logger import Logger as logger
from src.services.notifications import notification_dispatcher


class PhoneVerificationService:
    """
    Service for phone number verification via SMS OTP.

    Handles OTP generation (6-digit codes), SMS delivery via the notification
    system, verification with rate limiting, and cleanup of expired records.
    """

    OTP_LENGTH = 6
    OTP_EXPIRY_MINUTES = 5
    MAX_VERIFICATION_ATTEMPTS = 3
    RATE_LIMIT_HOURS = 1
    MAX_REQUESTS_PER_HOUR = 3

    async def send_otp(
        self,
        session: AsyncSession,
        user_id: str,
        phone: str,
        organization_id: str,
    ) -> dict[str, Any]:
        """
        Generate and send an OTP to a phone number.

        Creates a 6-digit OTP, hashes it with bcrypt, stores in database with
        5-minute expiry, and sends via SMS through the notification system.

        Enforces rate limiting: max 3 OTP requests per phone per hour.

        Args:
            session: Database session
            user_id: User UUID
            phone: Phone number (E.164 format recommended)
            organization_id: Organization UUID

        Returns:
            Dict with verification_id and expiry time

        Raises:
            ValueError: If rate limit exceeded
        """
        # Check rate limit
        recent_count = await phone_verification_crud.count_recent_requests(
            session, phone, organization_id, hours=self.RATE_LIMIT_HOURS
        )

        if recent_count >= self.MAX_REQUESTS_PER_HOUR:
            logger.warning(
                f"Rate limit exceeded for phone {phone} in org {organization_id}: "
                f"{recent_count} requests in last hour"
            )
            raise ValueError(
                f"Too many OTP requests. Please try again in {self.RATE_LIMIT_HOURS} hour(s)."
            )

        # Check if phone number is already used by another user in this organization
        existing_user = await user_crud.get_user_by_phone(
            session, phone, organization_id, exclude_user_id=user_id
        )
        if existing_user:
            logger.warning(
                f"Phone number {phone} already in use by another user in org {organization_id}"
            )
            raise ValueError(
                "This phone number is already registered to another account."
            )

        # Generate 6-digit OTP
        otp_code = self._generate_otp()

        # Hash the OTP using bcrypt (same as password hashing)
        otp_hash = bcrypt.hashpw(otp_code.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

        # Calculate expiry
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.OTP_EXPIRY_MINUTES
        )

        # Create verification record
        verification = await phone_verification_crud.create_otp(
            session,
            {
                "user_id": user_id,
                "phone": phone,
                "otp_hash": otp_hash,
                "expires_at": expires_at,
            },
            organization_id,
        )

        # Send OTP via SMS through notification system
        message = f"Your verification code is: {otp_code}. Valid for {self.OTP_EXPIRY_MINUTES} minutes."

        try:
            # Send SMS notification
            # Note: SMS provider needs to be configured in the notification dispatcher
            result = await notification_dispatcher.send_notification(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                channel="sms",
                recipient=phone,
                content=message,
                category_code="phone_verification",
                is_urgent=True,  # OTPs are time-sensitive
                subject=None,
                html_content=None,
                metadata={"verification_id": str(verification.id)},
            )

            if not result or result.get("status") in ["failed", "skipped"]:
                logger.error(
                    f"Failed to send OTP SMS to {phone}: "
                    f"{result.get('error_message') if result else 'No result'}"
                )
                # Note: We don't raise an error here because the OTP was created
                # The user might be able to retry or we can handle this gracefully
                return {
                    "verification_id": str(verification.id),
                    "expires_at": expires_at.isoformat(),
                    "warning": "OTP generated but SMS delivery failed. Please contact support.",
                }

            logger.info(
                f"OTP sent to phone {phone} for user {user_id}, "
                f"verification_id: {verification.id}"
            )

        except Exception as e:
            logger.error(f"Error sending OTP SMS to {phone}: {e}")
            # Continue anyway - the OTP is stored and might be useful for debugging
            return {
                "verification_id": str(verification.id),
                "expires_at": expires_at.isoformat(),
                "warning": f"OTP generated but SMS sending encountered an error: {str(e)}",
            }

        return {
            "verification_id": str(verification.id),
            "expires_at": expires_at.isoformat(),
            "message": f"OTP sent to {phone}",
        }

    async def verify_otp(
        self,
        session: AsyncSession,
        user_id: str,
        phone: str,
        otp_code: str,
        organization_id: str,
    ) -> dict[str, Any]:
        """
        Verify an OTP code for a phone number.

        Checks if the OTP matches, is not expired, and hasn't exceeded max
        attempts (3). Marks verification as complete on success.

        Args:
            session: Database session
            user_id: User UUID
            phone: Phone number
            otp_code: 6-digit OTP code to verify
            organization_id: Organization UUID

        Returns:
            Dict with verification status

        Raises:
            ValueError: If OTP invalid, expired, or max attempts exceeded
        """
        # Get active verification record
        verification = await phone_verification_crud.get_active_for_user(
            session, user_id, phone, organization_id
        )

        if not verification:
            raise ValueError("No active verification found for this phone number")

        # Check if expired
        # Handle both timezone-aware and naive datetimes
        expires_at = verification.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at <= datetime.now(timezone.utc):
            logger.info(f"OTP expired for verification {verification.id}")
            raise ValueError("OTP has expired. Please request a new code.")

        # Check if max attempts exceeded
        if verification.attempts_count >= self.MAX_VERIFICATION_ATTEMPTS:
            logger.warning(
                f"Max verification attempts exceeded for verification {verification.id}"
            )
            raise ValueError(
                "Maximum verification attempts exceeded. Please request a new code."
            )

        # Increment attempts
        verification = await phone_verification_crud.increment_attempts(
            session, str(verification.id), organization_id
        )

        # Verify OTP using bcrypt
        otp_matches = bcrypt.checkpw(
            otp_code.encode("utf-8"), verification.otp_hash.encode("utf-8")
        )

        if not otp_matches:
            logger.info(
                f"Invalid OTP attempt for verification {verification.id}, "
                f"attempt {verification.attempts_count}/{self.MAX_VERIFICATION_ATTEMPTS}"
            )
            remaining_attempts = (
                self.MAX_VERIFICATION_ATTEMPTS - verification.attempts_count
            )
            raise ValueError(
                f"Invalid OTP code. {remaining_attempts} attempt(s) remaining."
            )

        # Mark as verified
        verification = await phone_verification_crud.mark_verified(
            session, str(verification.id), organization_id
        )

        logger.info(
            f"Phone {phone} successfully verified for user {user_id}, "
            f"verification_id: {verification.id}"
        )

        # Update user's phone_verified field if needed
        await self._update_user_phone_verified(session, user_id, phone, organization_id)

        return {
            "verified": True,
            "phone": phone,
            "message": "Phone number verified successfully",
        }

    async def check_rate_limit(
        self,
        session: AsyncSession,
        phone: str,
        organization_id: str,
    ) -> dict[str, Any]:
        """
        Check if a phone number has exceeded the OTP request rate limit.

        Args:
            session: Database session
            phone: Phone number
            organization_id: Organization UUID

        Returns:
            Dict with rate limit status
        """
        recent_count = await phone_verification_crud.count_recent_requests(
            session, phone, organization_id, hours=self.RATE_LIMIT_HOURS
        )

        remaining = max(0, self.MAX_REQUESTS_PER_HOUR - recent_count)
        is_limited = remaining == 0

        return {
            "phone": phone,
            "requests_made": recent_count,
            "max_requests": self.MAX_REQUESTS_PER_HOUR,
            "remaining_requests": remaining,
            "rate_limited": is_limited,
            "time_window_hours": self.RATE_LIMIT_HOURS,
        }

    def _generate_otp(self) -> str:
        """
        Generate a secure random 6-digit OTP code.

        Returns:
            6-digit string code
        """
        # Use secrets for cryptographically strong random number
        return str(secrets.randbelow(1000000)).zfill(self.OTP_LENGTH)

    async def _update_user_phone_verified(
        self,
        session: AsyncSession,
        user_id: str,
        phone: str,
        organization_id: str,
    ) -> None:
        """
        Update the User model's phone_verified field after successful verification.

        Args:
            session: Database session
            user_id: User UUID
            phone: Verified phone number
            organization_id: Organization UUID
        """
        from uuid import UUID

        from sqlalchemy import select

        from src.models.user import User

        user_uuid = UUID(user_id)
        org_uuid = UUID(organization_id)

        result = await session.execute(
            select(User).where(
                User.id == user_uuid,
                User.organization_id == org_uuid,
                User.deleted_time.is_(None),
            )
        )
        user = result.scalars().first()

        if user:
            # Update phone and phone_verified flag
            user.phone = phone
            user.phone_verified = True
            await session.commit()
            logger.info(f"Updated phone_verified=True for user {user_id}")
        else:
            logger.warning(f"User {user_id} not found, could not update phone_verified")


# Singleton instance
phone_verification_service = PhoneVerificationService()
