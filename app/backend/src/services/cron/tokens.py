"""Token management cron handlers."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger as logger


async def cleanup_expired_refresh_tokens_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Clean up expired refresh tokens from the database.
    Uses hard delete since refresh tokens don't need soft delete.

    Parameters:
        batch_size (int): Number of records to process per batch (default: 1000)

    Returns:
        dict with deleted_count
    """
    from src.models.refresh_token import RefreshToken

    batch_size = parameters.get("batch_size", 1000)
    total_deleted = 0
    now = datetime.now(timezone.utc)

    try:
        # Process in batches to prevent OOM
        while True:
            # Find a batch of expired tokens
            result = await session.execute(
                select(RefreshToken.id)
                .where(RefreshToken.expires_at < now)
                .limit(batch_size)
            )
            token_ids = [row[0] for row in result.all()]

            if not token_ids:
                break

            # Hard delete expired tokens
            await session.execute(
                delete(RefreshToken).where(RefreshToken.id.in_(token_ids))
            )
            await session.commit()

            total_deleted += len(token_ids)

            if len(token_ids) < batch_size:
                break

        logger.info(f"Cleaned up {total_deleted} expired refresh tokens")
        return {"status": "completed", "deleted_count": total_deleted}

    except Exception as exc:
        await session.rollback()
        logger.error(f"Failed to cleanup expired refresh tokens: {exc}")
        return {"status": "error", "reason": str(exc), "deleted_count": total_deleted}


async def check_api_key_expiry_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Check for expired API keys and disable them.

    Parameters:
        notify_days_before (int): Days before expiry to send notification (default: 7)

    Returns:
        dict with expired_count and notified_count
    """
    from src.models.api_key import ApiKey

    notify_days_before = parameters.get("notify_days_before", 7)
    now = datetime.now(timezone.utc)
    notification_threshold = now + timedelta(days=notify_days_before)
    expired_count = 0
    notified_count = 0

    try:
        # Count expired keys (already expired but not deleted)
        result = await session.execute(
            select(ApiKey).where(
                ApiKey.expires_at.isnot(None),
                ApiKey.expires_at < now,
                ApiKey.deleted_time.is_(None),
            )
        )
        expired_keys = result.scalars().all()
        expired_count = len(expired_keys)

        # Find keys expiring soon for notification
        result = await session.execute(
            select(ApiKey).where(
                ApiKey.expires_at.isnot(None),
                ApiKey.expires_at > now,
                ApiKey.expires_at < notification_threshold,
                ApiKey.deleted_time.is_(None),
            )
        )
        expiring_keys = result.scalars().all()
        notified_count = len(expiring_keys)

        await session.commit()

        logger.info(
            f"Disabled {expired_count} expired API keys, {notified_count} expiring soon"
        )
        return {
            "status": "completed",
            "expired_count": expired_count,
            "notified_count": notified_count,
        }

    except Exception as exc:
        await session.rollback()
        logger.error(f"Failed to check API key expiry: {exc}")
        return {
            "status": "error",
            "reason": str(exc),
            "expired_count": expired_count,
            "notified_count": notified_count,
        }


__all__ = [
    "cleanup_expired_refresh_tokens_handler",
    "check_api_key_expiry_handler",
]
