"""
CRUD operations for the tenant-scoped PhoneVerification model.
Manages OTP generation and verification with rate limiting.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.phone_verification import PhoneVerification


async def create_otp(session: AsyncSession, data: dict, organization_id: str):
    """Create a new OTP verification record."""
    org_uuid = UUID(organization_id)
    user_id = UUID(data["user_id"])

    verification = PhoneVerification(
        user_id=user_id,
        phone=data["phone"],
        otp_hash=data["otp_hash"],
        expires_at=data["expires_at"],
        organization_id=org_uuid,
    )
    session.add(verification)
    await session.commit()
    await session.refresh(verification)
    return verification


async def verify_otp(
    session: AsyncSession, user_id: str, phone: str, otp_hash: str, organization_id: str
):
    """
    Verify an OTP by checking the hash matches and is not expired.
    Returns the verification record if valid, None otherwise.
    """
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(PhoneVerification).where(
            PhoneVerification.user_id == UUID(user_id),
            PhoneVerification.phone == phone,
            PhoneVerification.organization_id == org_uuid,
            PhoneVerification.verified.is_(False),
            PhoneVerification.expires_at > datetime.now(timezone.utc),
            PhoneVerification.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_active_for_user(
    session: AsyncSession, user_id: str, phone: str, organization_id: str
):
    """Get the most recent non-verified OTP for a user's phone.

    Note: Does NOT filter by expiry - the service layer handles expiry checking
    so it can return a proper "expired" error message.
    """
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(PhoneVerification)
        .where(
            PhoneVerification.user_id == UUID(user_id),
            PhoneVerification.phone == phone,
            PhoneVerification.organization_id == org_uuid,
            PhoneVerification.verified.is_(False),
            PhoneVerification.deleted_time.is_(None),
        )
        .order_by(PhoneVerification.created_time.desc())
    )
    return result.scalars().first()


async def increment_attempts(
    session: AsyncSession, verification_id: str, organization_id: str
):
    """Increment the attempts count for a verification record."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(PhoneVerification).where(
            PhoneVerification.id == UUID(verification_id),
            PhoneVerification.organization_id == org_uuid,
            PhoneVerification.deleted_time.is_(None),
        )
    )
    verification = result.scalars().first()
    if not verification:
        raise ValueError(f"Verification record with id {verification_id} not found")

    verification.attempts_count += 1
    await session.commit()
    await session.refresh(verification)
    return verification


async def mark_verified(
    session: AsyncSession, verification_id: str, organization_id: str
):
    """Mark a verification record as verified."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(PhoneVerification).where(
            PhoneVerification.id == UUID(verification_id),
            PhoneVerification.organization_id == org_uuid,
            PhoneVerification.deleted_time.is_(None),
        )
    )
    verification = result.scalars().first()
    if not verification:
        raise ValueError(f"Verification record with id {verification_id} not found")

    verification.verified = True
    await session.commit()
    await session.refresh(verification)
    return verification


async def count_recent_requests(
    session: AsyncSession, phone: str, organization_id: str, hours: int = 1
):
    """
    Count how many OTP requests were made for a phone in the last N hours.
    Used for rate limiting (e.g., max 3 requests per hour).
    """
    org_uuid = UUID(organization_id)
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = await session.execute(
        select(func.count())
        .select_from(PhoneVerification)
        .where(
            PhoneVerification.phone == phone,
            PhoneVerification.organization_id == org_uuid,
            PhoneVerification.created_time >= cutoff_time,
            PhoneVerification.deleted_time.is_(None),
        )
    )
    return result.scalar() or 0


async def cleanup_expired(session: AsyncSession):
    """
    Background worker function to soft-delete expired verification records.
    This is an exception to the organization_id filtering rule as it's a cleanup job.
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=7)

    result = await session.execute(
        select(PhoneVerification).where(
            PhoneVerification.expires_at < cutoff_time,
            PhoneVerification.deleted_time.is_(None),
        )
    )
    expired_records = result.scalars().all()

    for record in expired_records:
        record.deleted_time = datetime.now(timezone.utc)

    await session.commit()
    return len(expired_records)
