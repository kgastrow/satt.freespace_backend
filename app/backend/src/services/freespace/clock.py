"""
Injectable clock for all Freespace code (D8, BF-85).

RULE: no Freespace service, crud or api module may call ``datetime.now(`` or
``datetime.utcnow(``. Time comes from a ``Clock`` passed in (or an explicit
``now`` argument). ``tests/freespace/test_foundation_clock.py`` greps for
violations. This module is the only allowed caller.

Usage
-----
* FastAPI endpoints: ``clock: Annotated[Clock, Depends(get_clock)]``.
* Worker tasks / services without a request: ``clock = await get_clock()``.
* Pure core functions take ``now: datetime`` and never a clock.

Mock mode (BF-84): when ``settings.FREESPACE_MOCK_MODE`` is on, ``get_clock``
returns a ``SystemClock`` shifted by the offset stored in Redis under
``REDIS_MOCK_CLOCK_OFFSET_KEY`` so every API worker and the ARQ worker agree
on simulated time. ``POST /mock/clock`` (M10) calls ``advance_mock_offset``.

Tests: ``set_clock_override(FixedClock(...))`` makes ``get_clock`` return that
clock everywhere (API dependency and worker code alike); the shared
``fixed_clock`` fixture in ``tests/freespace/conftest.py`` does this.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

from src.constants.freespace import REDIS_MOCK_CLOCK_OFFSET_KEY
from src.core.config import settings
from src.logger.logger import Logger as logger
from src.services.freespace.redis_client import get_redis


@runtime_checkable
class Clock(Protocol):
    """Source of the current time. ``now()`` is always timezone-aware UTC."""

    def now(self) -> datetime: ...


def ensure_utc(value: datetime) -> datetime:
    """Return ``value`` as an aware UTC datetime.

    Naive values are assumed to be UTC (SQLite returns naive datetimes from
    ``DateTime(timezone=True)`` columns in tests).
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class SystemClock:
    """Wall clock, optionally shifted by a fixed offset (mock mode)."""

    def __init__(self, offset: timedelta | None = None) -> None:
        self.offset = offset or timedelta(0)

    def now(self) -> datetime:
        return datetime.now(timezone.utc) + self.offset

    def __repr__(self) -> str:
        return f"SystemClock(offset={self.offset!r})"


class FixedClock:
    """A clock that only moves when told to. For tests and simulations."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = ensure_utc(
            start or datetime(2026, 11, 24, 5, 45, 0, tzinfo=timezone.utc)
        )

    def now(self) -> datetime:
        return self._now

    def advance(
        self, seconds: float = 0, *, delta: timedelta | None = None
    ) -> datetime:
        """Move forward by ``seconds`` (and/or ``delta``); return the new now."""
        step = timedelta(seconds=seconds) + (delta or timedelta(0))
        if step < timedelta(0):
            raise ValueError("FixedClock cannot move backwards; use set()")
        self._now = self._now + step
        return self._now

    def set(self, value: datetime) -> datetime:
        """Jump to ``value`` (may move backwards); return it."""
        self._now = ensure_utc(value)
        return self._now

    def __repr__(self) -> str:
        return f"FixedClock({self._now.isoformat()})"


_override: Clock | None = None


def set_clock_override(clock: Clock | None) -> None:
    """Make ``get_clock`` return ``clock`` until reset with ``None``. Tests only."""
    global _override
    _override = clock


def get_clock_override() -> Clock | None:
    """The clock set by ``set_clock_override``, if any."""
    return _override


async def get_mock_offset_seconds() -> float:
    """Mock-clock offset in seconds stored in Redis; 0.0 when unset/unavailable."""
    redis = get_redis()
    if redis is None:
        return 0.0
    try:
        raw = await redis.get(REDIS_MOCK_CLOCK_OFFSET_KEY)
    except Exception as exc:  # Redis is optional here: fail open to real time
        logger.warning(f"Freespace mock clock: Redis read failed: {exc}")
        return 0.0
    if raw is None:
        return 0.0
    try:
        return float(raw.decode() if isinstance(raw, bytes) else raw)
    except (TypeError, ValueError):
        logger.warning(f"Freespace mock clock: ignoring invalid offset {raw!r}")
        return 0.0


async def set_mock_offset_seconds(seconds: float) -> None:
    """Store the absolute mock-clock offset (no TTL). Raises if Redis is
    unavailable, because mock mode cannot share time across workers without it."""
    redis = get_redis()
    if redis is None:
        raise RuntimeError("Redis is required to set the mock clock offset")
    await redis.set(REDIS_MOCK_CLOCK_OFFSET_KEY, repr(float(seconds)))


async def advance_mock_offset(seconds: float) -> float:
    """Add ``seconds`` (must be >= 0) to the mock offset; return the new offset."""
    if seconds < 0:
        raise ValueError("The mock clock can only move forward")
    new_offset = await get_mock_offset_seconds() + seconds
    await set_mock_offset_seconds(new_offset)
    return new_offset


async def reset_mock_offset() -> None:
    """Remove the mock-clock offset (back to real time)."""
    redis = get_redis()
    if redis is not None:
        await redis.delete(REDIS_MOCK_CLOCK_OFFSET_KEY)


async def get_clock() -> Clock:
    """FastAPI dependency and module accessor for the Freespace clock.

    Override (tests) > mock-mode offset clock > plain system clock.
    """
    if _override is not None:
        return _override
    if settings.FREESPACE_MOCK_MODE:
        return SystemClock(timedelta(seconds=await get_mock_offset_seconds()))
    return SystemClock()
