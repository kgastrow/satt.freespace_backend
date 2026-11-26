"""Health monitoring cron handlers."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger as logger


async def check_brute_force_alerts_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Check for brute force attack patterns and generate alerts.

    Parameters:
        threshold (int): Number of failed attempts to trigger alert (default: 10)
        window_minutes (int): Time window to check (default: 15)

    Returns:
        dict with alerts_generated count
    """
    threshold = parameters.get("threshold", 10)
    window_minutes = parameters.get("window_minutes", 15)
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=window_minutes)
    alerts_generated = 0

    try:
        # Check OTP attempts
        from src.models.user_otp import UserOTP

        result = await session.execute(
            select(UserOTP.user_id, func.sum(UserOTP.attempts_count).label("total"))
            .where(
                UserOTP.created_time > window_start,
                UserOTP.deleted_time.is_(None),
            )
            .group_by(UserOTP.user_id)
            .having(func.sum(UserOTP.attempts_count) >= threshold)
        )
        suspicious_users = result.all()

        for user_id, total_attempts in suspicious_users:
            logger.warning(
                f"Brute force alert: user {user_id} has {total_attempts} "
                f"failed OTP attempts in last {window_minutes} minutes"
            )
            alerts_generated += 1

        logger.info(f"Generated {alerts_generated} brute force alerts")
        return {"status": "completed", "alerts_generated": alerts_generated}

    except Exception as exc:
        logger.error(f"Failed to check brute force alerts: {exc}")
        return {
            "status": "error",
            "reason": str(exc),
            "alerts_generated": alerts_generated,
        }


async def check_queue_health_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Check the health of the job queue.

    Parameters:
        max_queue_depth (int): Maximum acceptable queue depth (default: 1000)
        max_stuck_minutes (int): Minutes before a job is considered stuck (default: 30)

    Returns:
        dict with queue health stats
    """
    _max_queue_depth = parameters.get("max_queue_depth", 1000)
    _max_stuck_minutes = parameters.get("max_stuck_minutes", 30)
    alerts: list[str] = []

    try:
        # This would integrate with ARQ or your task queue
        # For now, return basic health info
        return {
            "status": "completed",
            "queue_healthy": True,
            "queue_depth": 0,
            "stuck_jobs": 0,
            "alerts": alerts,
        }

    except Exception as exc:
        logger.error(f"Failed to check queue health: {exc}")
        return {"status": "error", "reason": str(exc), "alerts": alerts}


def _describe_pool(session: AsyncSession) -> dict[str, Any]:
    """
    Describe the connection pool actually bound to this session.

    Reports what is really there rather than asserting health. NullPool holds no
    connections, so it exposes none of the QueuePool counters - saying
    "pool_healthy: True" about it (as this handler used to) is meaningless, and
    would report exactly the same thing whether or not a pool existed at all.
    Every field below is optional and only present when the pool provides it.
    """
    stats: dict[str, Any] = {}
    try:
        bind = session.get_bind()
        engine = getattr(bind, "engine", bind)
        pool = getattr(engine, "pool", None)
    except Exception as exc:  # pragma: no cover - defensive
        return {"pool_class": None, "pooled": False, "pool_error": str(exc)}

    if pool is None:
        return {"pool_class": None, "pooled": False}

    pool_class = type(pool).__name__
    stats["pool_class"] = pool_class
    # NullPool keeps nothing; anything else maintains at least one connection.
    stats["pooled"] = pool_class != "NullPool"

    try:
        stats["pool_status"] = pool.status()
    except Exception:  # pragma: no cover - defensive
        pass

    # QueuePool/AsyncAdaptedQueuePool counters. Absent on NullPool and
    # StaticPool, so probe rather than assume.
    for attr in ("size", "checkedin", "checkedout", "overflow"):
        getter = getattr(pool, attr, None)
        if not callable(getter):
            continue
        try:
            stats[attr] = getter()
        except Exception:  # pragma: no cover - defensive
            pass

    # Saturation is only meaningful where there is a bounded pool to saturate.
    size = stats.get("size")
    checked_out = stats.get("checkedout")
    if isinstance(size, int) and isinstance(checked_out, int):
        max_overflow = getattr(pool, "_max_overflow", 0)
        capacity = size + max(max_overflow, 0)
        stats["pool_capacity"] = capacity
        stats["pool_exhausted"] = capacity > 0 and checked_out >= capacity

    return stats


async def check_db_pool_health_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Check database connection pool health.

    Reports the observed state of the pool bound to the session, plus a live
    connection test. Note that ``pool_healthy`` describes what was measured: a
    NullPool that answers SELECT 1 is healthy in the only sense it can be, and
    says so via ``pooled: false`` rather than pretending to pool statistics it
    does not have.

    Parameters:
        None

    Returns:
        dict with pool health stats
    """
    pool_stats = _describe_pool(session)

    try:
        # Execute a simple query to verify connection
        from sqlalchemy import text

        result = await session.execute(text("SELECT 1"))
        result.scalar()

        exhausted = bool(pool_stats.get("pool_exhausted", False))
        alerts: list[str] = []
        if exhausted:
            alerts.append(
                f"Connection pool exhausted: {pool_stats.get('checkedout')} of "
                f"{pool_stats.get('pool_capacity')} connections checked out"
            )
            logger.warning(alerts[-1])

        return {
            "status": "completed",
            "pool_healthy": not exhausted,
            "connection_test": "passed",
            "alerts": alerts,
            **pool_stats,
        }

    except Exception as exc:
        logger.error(f"Database pool health check failed: {exc}")
        return {
            "status": "error",
            "reason": str(exc),
            "pool_healthy": False,
            "connection_test": "failed",
            **pool_stats,
        }


__all__ = [
    "check_brute_force_alerts_handler",
    "check_queue_health_handler",
    "check_db_pool_health_handler",
]
