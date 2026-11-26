"""
``GET /health`` check (BF-80). OWNER: M9.

Status only: whether the database answers and how old the last engine tick is.
No version, host, error text or configuration is ever returned, so the
unauthenticated endpoint tells an attacker nothing.

The tick time is read from Redis (``REDIS_ENGINE_TICK_KEY``, written by the
tick); when Redis has none the newest ``site_engine_state.last_evaluated_at``
stands in. With neither, the service is healthy for ``STARTUP_GRACE_S`` after
the first check this process answered ("no_tick_yet"), then unhealthy.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import func, select, text

from src.constants.freespace import REDIS_ENGINE_TICK_KEY
from src.logger.logger import Logger as logger
from src.models.site_engine_state import SiteEngineState
from src.services.freespace.clock import Clock, ensure_utc
from src.services.freespace.redis_client import get_redis


TICK_STALE_AFTER_S: Final = 180  # three missed minutes
STARTUP_GRACE_S: Final = 300
DB_CHECK_TIMEOUT_S: Final = 3.0

ENGINE_OK: Final = "ok"
ENGINE_STALE: Final = "stale"
ENGINE_NO_TICK_YET: Final = "no_tick_yet"


@dataclass
class StartupGrace:
    """When this process answered its first health check (start of the
    ``STARTUP_GRACE_S`` window). Process-global by default; injectable and
    resettable so callers / tests get a definite verdict."""

    first_check_at: datetime | None = None


_grace = StartupGrace()


def reset_health_state(first_check_at: datetime | None = None) -> None:
    """Restart the grace window. ``first_check_at`` None = it starts at the
    next check; a datetime pins it (e.g. long ago to test "grace over")."""
    _grace.first_check_at = ensure_utc(first_check_at) if first_check_at else None


@dataclass(frozen=True)
class HealthReport:
    healthy: bool
    database_ok: bool
    engine_status: str
    tick_age_s: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self.healthy else "unhealthy",
            "database": "ok" if self.database_ok else "unreachable",
            "engine": {
                "status": self.engine_status,
                "lastTickAgeSeconds": self.tick_age_s,
            },
        }


async def _database_ok(session_factory: Any) -> bool:
    async def probe() -> None:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(probe(), timeout=DB_CHECK_TIMEOUT_S)
        return True
    except Exception as exc:
        logger.error(f"Health: database check failed: {type(exc).__name__}")
        return False


async def _last_tick(session_factory: Any) -> datetime | None:
    redis = get_redis()
    if redis is not None:
        try:
            raw = await redis.get(REDIS_ENGINE_TICK_KEY)
            if raw:
                if isinstance(raw, bytes):
                    raw = raw.decode()
                return ensure_utc(datetime.fromisoformat(str(raw)))
        except Exception as exc:
            logger.warning(f"Health: cannot read tick time: {type(exc).__name__}")
    try:
        async with session_factory() as session:
            newest = (
                await session.execute(
                    select(func.max(SiteEngineState.last_evaluated_at))
                )
            ).scalar_one_or_none()
        return ensure_utc(newest) if newest else None
    except Exception:
        return None


async def check_health(
    session_factory: Any, clock: Clock, *, grace: StartupGrace | None = None
) -> HealthReport:
    """Cheap, unauthenticated-safe health verdict. Never raises.

    ``session_factory`` is a zero-argument callable returning an async session
    context manager (``AsyncSessionLocal``). ``grace`` defaults to the
    process-global start-up window.
    """
    state = grace if grace is not None else _grace
    now = ensure_utc(clock.now())
    if state.first_check_at is None:
        state.first_check_at = now
    database_ok = await _database_ok(session_factory)
    last_tick = await _last_tick(session_factory) if database_ok else None
    if last_tick is None:
        within_grace = (now - state.first_check_at).total_seconds() < STARTUP_GRACE_S
        engine = ENGINE_NO_TICK_YET if within_grace else ENGINE_STALE
        return HealthReport(
            healthy=database_ok and within_grace,
            database_ok=database_ok,
            engine_status=engine,
            tick_age_s=None,
        )
    age = max(0, int((now - last_tick).total_seconds()))
    fresh = age <= TICK_STALE_AFTER_S
    return HealthReport(
        healthy=database_ok and fresh,
        database_ok=database_ok,
        engine_status=ENGINE_OK if fresh else ENGINE_STALE,
        tick_age_s=age,
    )
