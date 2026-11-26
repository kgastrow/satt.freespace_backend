"""OTP-related cron handlers."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger as logger


async def cleanup_expired_otps_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Clean up expired OTP codes from the database.
    Uses soft delete (sets deleted_time) for expired OTPs.

    Parameters:
        batch_size (int): Number of records to process per batch (default: 1000)

    Returns:
        dict with deleted_count
    """
    from src.models.user_otp import UserOTP

    batch_size = parameters.get("batch_size", 1000)
    total_deleted = 0
    now = datetime.now(timezone.utc)

    try:
        # Process in batches to prevent OOM
        while True:
            # Find a batch of expired OTPs
            result = await session.execute(
                select(UserOTP.id)
                .where(UserOTP.expires_at < now, UserOTP.deleted_time.is_(None))
                .limit(batch_size)
            )
            otp_ids = [row[0] for row in result.all()]

            if not otp_ids:
                break

            # Bulk update to soft delete
            await session.execute(
                update(UserOTP).where(UserOTP.id.in_(otp_ids)).values(deleted_time=now)
            )
            await session.commit()

            total_deleted += len(otp_ids)

            # If we got fewer than batch size, we're done
            if len(otp_ids) < batch_size:
                break

        logger.info(f"Cleaned up {total_deleted} expired OTP codes")
        return {"status": "completed", "deleted_count": total_deleted}

    except Exception as exc:
        await session.rollback()
        logger.error(f"Failed to cleanup expired OTPs: {exc}")
        return {"status": "error", "reason": str(exc), "deleted_count": total_deleted}


__all__ = ["cleanup_expired_otps_handler"]
