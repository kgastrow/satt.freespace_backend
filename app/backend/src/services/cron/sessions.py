"""Session and auth-related cron handlers."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger as logger


async def check_2fa_grace_period_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Check for organizations where the mandatory 2FA grace period has expired.
    Finds users who still haven't enabled 2FA past the deadline.

    Parameters:
        None

    Returns:
        dict with organizations_processed and total_users_affected counts
    """
    from src.models.organization_two_factor_settings import (
        OrganizationTwoFactorSettings,
    )
    from src.models.user import User
    from src.models.user_two_factor import UserTwoFactor

    now = datetime.now(timezone.utc)
    orgs_processed = 0
    total_users_affected = 0

    try:
        # Find all organizations with mandatory 2FA where enforcement has started
        settings_result = await session.execute(
            select(OrganizationTwoFactorSettings).where(
                OrganizationTwoFactorSettings.two_factor_policy == "mandatory",
                OrganizationTwoFactorSettings.enforcement_start_time.isnot(None),
                OrganizationTwoFactorSettings.deleted_time.is_(None),
            )
        )
        all_settings = settings_result.scalars().all()

        for settings in all_settings:
            # Calculate deadline
            deadline = settings.enforcement_start_time + timedelta(
                days=settings.grace_period_days
            )

            # Skip if grace period hasn't expired yet
            if now < deadline:
                continue

            # Find users without 2FA in this organization
            users_result = await session.execute(
                select(User)
                .outerjoin(
                    UserTwoFactor,
                    (UserTwoFactor.user_id == User.id)
                    & (UserTwoFactor.deleted_time.is_(None)),
                )
                .where(
                    User.organization_id == settings.organization_id,
                    User.deleted_time.is_(None),
                    (UserTwoFactor.id.is_(None) | ~UserTwoFactor.is_enabled),
                )
            )
            users_without_2fa = users_result.scalars().all()

            if users_without_2fa:
                orgs_processed += 1
                total_users_affected += len(users_without_2fa)

                logger.info(
                    f"Organization {settings.organization_id} 2FA grace period expired: "
                    f"{len(users_without_2fa)} users without 2FA"
                )

        logger.info(
            f"2FA grace period check: {orgs_processed} organizations processed, "
            f"{total_users_affected} users affected"
        )

        return {
            "status": "completed",
            "organizations_processed": orgs_processed,
            "total_users_affected": total_users_affected,
        }

    except Exception as exc:
        await session.rollback()
        logger.error(f"Failed to check 2FA grace periods: {exc}")
        return {
            "status": "error",
            "reason": str(exc),
            "organizations_processed": orgs_processed,
            "total_users_affected": total_users_affected,
        }


async def check_user_type_expiry_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Check for expired user type assignments and handle them.

    Parameters:
        None

    Returns:
        dict with expired_count
    """
    from src.models.user_user_type import OnboardingStatus, UserUserType

    now = datetime.now(timezone.utc)
    expired_count = 0

    try:
        result = await session.execute(
            select(UserUserType).where(
                UserUserType.expires_at.isnot(None),
                UserUserType.expires_at < now,
                UserUserType.onboarding_status != OnboardingStatus.EXPIRED,
                UserUserType.deleted_time.is_(None),
            )
        )
        expired_assignments = result.scalars().all()

        for assignment in expired_assignments:
            assignment.onboarding_status = OnboardingStatus.EXPIRED
            expired_count += 1

        await session.commit()

        logger.info(f"Expired {expired_count} user type assignments")
        return {"status": "completed", "expired_count": expired_count}

    except Exception as exc:
        await session.rollback()
        logger.error(f"Failed to check user type expiry: {exc}")
        return {"status": "error", "reason": str(exc), "expired_count": expired_count}


async def cleanup_old_request_logs_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Clean up old request logs past retention period.

    Parameters:
        retention_days (int): Retention period in days (default: 30)
        batch_size (int): Number of records to process per batch (default: 1000)

    Returns:
        dict with deleted_count
    """
    from src.models.request_log import RequestLog

    retention_days = parameters.get("retention_days", 30)
    batch_size = parameters.get("batch_size", 1000)
    total_deleted = 0
    now = datetime.now(timezone.utc)
    cutoff_date = now - timedelta(days=retention_days)

    try:
        while True:
            result = await session.execute(
                select(RequestLog.id)
                .where(RequestLog.created_time < cutoff_date)
                .limit(batch_size)
            )
            log_ids = [row[0] for row in result.all()]

            if not log_ids:
                break

            await session.execute(delete(RequestLog).where(RequestLog.id.in_(log_ids)))
            await session.commit()

            total_deleted += len(log_ids)

            if len(log_ids) < batch_size:
                break

        logger.info(f"Cleaned up {total_deleted} old request logs")
        return {"status": "completed", "deleted_count": total_deleted}

    except Exception as exc:
        await session.rollback()
        logger.error(f"Failed to cleanup old request logs: {exc}")
        return {"status": "error", "reason": str(exc), "deleted_count": total_deleted}


async def cleanup_old_bg_job_executions_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Clean up old background job execution records past retention period.

    Parameters:
        retention_hours (int): Hours to retain records (default: 168 = 7 days)

    Returns:
        dict with deleted_count
    """
    from src.crud.background_job import cleanup_old_bg_job_executions

    retention_hours = parameters.get("retention_hours", 168)

    try:
        deleted_count = await cleanup_old_bg_job_executions(session, retention_hours)
        logger.info(f"Cleaned up {deleted_count} old background job execution records")
        return {"status": "completed", "deleted_count": deleted_count}
    except Exception as exc:
        await session.rollback()
        logger.error(f"Failed to cleanup old bg job executions: {exc}")
        return {"status": "error", "reason": str(exc)}


__all__ = [
    "check_2fa_grace_period_handler",
    "check_user_type_expiry_handler",
    "cleanup_old_request_logs_handler",
    "cleanup_old_bg_job_executions_handler",
]
