from datetime import datetime, timedelta, timezone
import secrets
import uuid
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import UserOTP
from src.models.user_otp import OTPType
from src.serialisers.user_otp import CreateUserOtpRequest


OTP_EXPIRATION_MINUTES = 10
PASSWORD_RESET_EXPIRATION_MINUTES = 60  # 1 hour
MAX_OTP_ATTEMPTS = 5  # Maximum failed verification attempts before OTP is invalidated


def generate_otp():
    """Generate a cryptographically secure 6-digit OTP code for email verification."""
    return f"{secrets.randbelow(900000) + 100000}"


def generate_password_reset_token():
    """Generate a secure 32-character token for password reset."""
    return secrets.token_urlsafe(24)  # Generates ~32 chars


async def create_otp(
    session: AsyncSession,
    user_id: UUID,
    organization_id: str,
    otp_type: OTPType = OTPType.VERIFICATION,
):
    """
    Create an OTP or password reset token for a user.

    Args:
        session: Database session
        user_id: User's UUID
        organization_id: Organization's UUID string
        otp_type: Type of OTP (VERIFICATION or PASSWORD_RESET)

    Returns:
        The generated OTP code or reset token
    """
    if otp_type == OTPType.PASSWORD_RESET:
        otp_code = generate_password_reset_token()
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=PASSWORD_RESET_EXPIRATION_MINUTES
        )
    else:
        otp_code = generate_otp()
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=OTP_EXPIRATION_MINUTES
        )

    try:
        request = CreateUserOtpRequest(
            user_id=user_id, otp_code=otp_code, expires_at=expires_at
        )
    except ValidationError as e:
        raise ValueError(f"Invalid input: {e}")

    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )

    # Soft-delete all existing OTPs of the same type for this user in this organization
    # This is done BEFORE creating the new OTP to ensure atomicity
    await session.execute(
        update(UserOTP)
        .where(
            UserOTP.user_id == user_id,
            UserOTP.organization_id == org_uuid,
            UserOTP.otp_type == otp_type.value,
            UserOTP.deleted_time.is_(None),
        )
        .values(deleted_time=datetime.now(timezone.utc))
    )

    # Create new OTP
    otp_entry = UserOTP(
        user_id=request.user_id,
        otp_code=request.otp_code,
        otp_type=otp_type.value,
        expires_at=request.expires_at,
        is_used=False,
        organization_id=org_uuid,
    )

    session.add(otp_entry)
    await session.commit()
    await session.refresh(otp_entry)

    return otp_code


async def verify_otp(
    session: AsyncSession,
    user_id: uuid.UUID,
    otp_code: str,
    organization_id: str,
    otp_type: OTPType = OTPType.VERIFICATION,
):
    """
    Verify an OTP code for a user.

    Args:
        session: Database session
        user_id: User's UUID
        otp_code: The OTP code to verify (hyphens are automatically stripped)
        organization_id: Organization's UUID string
        otp_type: Type of OTP to verify

    Returns:
        True if OTP is valid

    Raises:
        ValueError: If OTP is invalid, expired, already used, or max attempts exceeded
    """
    try:
        # Validate otp_code format only, not content
        if not otp_code or not isinstance(otp_code, str):
            raise ValueError("Invalid OTP format")
        # Normalize: strip hyphens since emails display OTP as "XXX-XXX" for readability
        otp_code = otp_code.replace("-", "").strip()
    except (ValidationError, ValueError) as e:
        raise ValueError(f"Invalid input: {e}")

    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )

    # First, get the OTP entry for this user regardless of the code
    # to check attempt counts and increment if wrong
    result = await session.execute(
        select(UserOTP).where(
            UserOTP.user_id == user_id,
            UserOTP.organization_id == org_uuid,
            UserOTP.otp_type == otp_type.value,
            UserOTP.is_used == False,  # noqa: E712
            UserOTP.deleted_time.is_(None),
        )
    )
    otp_entry = result.scalars().first()

    if not otp_entry:
        raise ValueError("Invalid or expired OTP")

    # Check if max attempts exceeded
    if otp_entry.attempts_count >= MAX_OTP_ATTEMPTS:
        raise ValueError(
            "Maximum verification attempts exceeded. Please request a new OTP."
        )

    # Handle timezone-aware vs naive datetime comparison
    expires_at = otp_entry.expires_at
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        raise ValueError("OTP has expired")

    # Check if OTP code matches
    if otp_entry.otp_code != otp_code:
        # Increment attempts count and save
        otp_entry.attempts_count += 1
        await session.commit()
        raise ValueError("Invalid OTP")

    otp_entry.is_used = True
    await session.commit()

    return True


async def create_password_reset_token(
    session: AsyncSession, user_id: uuid.UUID, organization_id: str
) -> str:
    """
    Create a password reset token for a user.

    Args:
        session: Database session
        user_id: User's UUID
        organization_id: Organization's UUID string

    Returns:
        The generated password reset token
    """
    return await create_otp(
        session=session,
        user_id=user_id,
        organization_id=organization_id,
        otp_type=OTPType.PASSWORD_RESET,
    )


async def verify_password_reset_token(
    session: AsyncSession, token: str, organization_id: str
) -> uuid.UUID:
    """
    Verify a password reset token and return the user_id.

    Args:
        session: Database session
        token: The password reset token
        organization_id: Organization's UUID string

    Returns:
        The user_id associated with the token

    Raises:
        ValueError: If token is invalid, expired, or already used
    """
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )

    result = await session.execute(
        select(UserOTP).where(
            UserOTP.otp_code == token,
            UserOTP.organization_id == org_uuid,
            UserOTP.otp_type == OTPType.PASSWORD_RESET.value,
            UserOTP.is_used == False,  # noqa: E712
            UserOTP.deleted_time.is_(None),
        )
    )
    otp_entry = result.scalars().first()

    if not otp_entry:
        raise ValueError("Invalid or expired password reset token")

    # Handle timezone-aware vs naive datetime comparison
    expires_at = otp_entry.expires_at
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        raise ValueError("Password reset token has expired")

    # Mark token as used
    otp_entry.is_used = True
    await session.commit()

    return otp_entry.user_id


async def get_user_by_reset_token(
    session: AsyncSession, token: str, organization_id: str
) -> uuid.UUID | None:
    """
    Get the user_id for a password reset token without marking it as used.
    Used to validate the token before the reset form is submitted.

    Args:
        session: Database session
        token: The password reset token
        organization_id: Organization's UUID string

    Returns:
        The user_id if token is valid, None otherwise
    """
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )

    result = await session.execute(
        select(UserOTP).where(
            UserOTP.otp_code == token,
            UserOTP.organization_id == org_uuid,
            UserOTP.otp_type == OTPType.PASSWORD_RESET.value,
            UserOTP.is_used == False,  # noqa: E712
            UserOTP.deleted_time.is_(None),
        )
    )
    otp_entry = result.scalars().first()

    if not otp_entry:
        return None

    # Check expiry
    expires_at = otp_entry.expires_at
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        return None

    return otp_entry.user_id
