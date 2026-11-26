"""Foundation: injectable clock (D8, BF-85) and the no-datetime.now rule."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

import pytest

from src.constants.freespace import REDIS_MOCK_CLOCK_OFFSET_KEY
from src.services.freespace import clock as clock_module
from src.services.freespace.clock import (
    Clock,
    FixedClock,
    SystemClock,
    advance_mock_offset,
    ensure_utc,
    get_clock,
    get_mock_offset_seconds,
    reset_mock_offset,
    set_mock_offset_seconds,
)


BACKEND_ROOT = Path(__file__).resolve().parents[2]
SRC = BACKEND_ROOT / "src"

# Files subject to the clock rule. New Freespace files that follow the naming
# pattern are picked up automatically.
CLOCK_RULE_GLOBS = (
    "services/freespace/**/*.py",
    "api/freespace_*.py",
    "api/freespace_public/**/*.py",
    "crud/freespace_*.py",
    "serialisers/freespace_*.py",
    "workers/freespace_*.py",
)
CLOCK_RULE_EXEMPT = {SRC / "services" / "freespace" / "clock.py"}
FORBIDDEN = re.compile(
    r"\bdatetime\.now\(|\.utcnow\(|\bdate\.today\(|\bdatetime\.today\("
)


class TestFixedClock:
    def test_now_is_fixed_and_aware(self):
        clock = FixedClock(datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc))
        assert clock.now() == clock.now()
        assert clock.now().tzinfo is not None

    def test_advance(self):
        clock = FixedClock(datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc))
        assert clock.advance(90) == datetime(2026, 1, 1, 8, 1, 30, tzinfo=timezone.utc)
        clock.advance(delta=timedelta(minutes=4))
        assert clock.now() == datetime(2026, 1, 1, 8, 5, 30, tzinfo=timezone.utc)

    def test_advance_backwards_rejected_set_allowed(self):
        clock = FixedClock(datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc))
        with pytest.raises(ValueError):
            clock.advance(-1)
        clock.set(datetime(2025, 1, 1))  # naive -> UTC
        assert clock.now() == datetime(2025, 1, 1, tzinfo=timezone.utc)

    def test_naive_start_is_utc(self):
        assert FixedClock(datetime(2026, 1, 1)).now().tzinfo == timezone.utc

    def test_is_a_clock(self):
        assert isinstance(FixedClock(), Clock)
        assert isinstance(SystemClock(), Clock)


class TestSystemClock:
    def test_aware_utc(self):
        now = SystemClock().now()
        assert now.tzinfo is not None and now.utcoffset() == timedelta(0)

    def test_offset(self):
        plain = SystemClock().now()
        shifted = SystemClock(timedelta(hours=1)).now()
        assert timedelta(minutes=59) < shifted - plain < timedelta(minutes=61)


def test_ensure_utc_converts_other_zones():
    sast = timezone(timedelta(hours=2))
    assert ensure_utc(datetime(2026, 1, 1, 10, 0, tzinfo=sast)) == datetime(
        2026, 1, 1, 8, 0, tzinfo=timezone.utc
    )


class TestGetClock:
    async def test_returns_override(self, fixed_clock):
        assert await get_clock() is fixed_clock

    async def test_system_clock_without_override(self):
        clock_module.set_clock_override(None)
        clock = await get_clock()
        assert isinstance(clock, SystemClock)
        assert clock.offset == timedelta(0)

    async def test_mock_mode_uses_redis_offset(self, monkeypatch, fs_redis):
        clock_module.set_clock_override(None)
        monkeypatch.setattr(clock_module.settings, "FREESPACE_MOCK_MODE", True)
        await set_mock_offset_seconds(300)
        clock = await get_clock()
        assert isinstance(clock, SystemClock)
        assert clock.offset == timedelta(seconds=300)

    async def test_offset_ignored_when_mock_mode_off(self, fs_redis):
        clock_module.set_clock_override(None)
        await set_mock_offset_seconds(300)
        clock = await get_clock()
        assert isinstance(clock, SystemClock) and clock.offset == timedelta(0)


class TestMockOffset:
    async def test_default_zero(self):
        assert await get_mock_offset_seconds() == 0.0

    async def test_advance_accumulates_and_reset(self, fs_redis):
        assert await advance_mock_offset(60) == 60.0
        assert await advance_mock_offset(30.5) == 90.5
        assert await get_mock_offset_seconds() == 90.5
        await reset_mock_offset()
        assert await fs_redis.get(REDIS_MOCK_CLOCK_OFFSET_KEY) is None

    async def test_cannot_move_backwards(self):
        with pytest.raises(ValueError):
            await advance_mock_offset(-1)

    async def test_invalid_stored_value_is_zero(self, fs_redis):
        await fs_redis.set(REDIS_MOCK_CLOCK_OFFSET_KEY, "not-a-number")
        assert await get_mock_offset_seconds() == 0.0

    async def test_no_redis_fails_open(self):
        from src.services.freespace import redis_client

        # Under pytest neither the shared pool nor the cache client exist;
        # the fs_redis teardown restores its override afterwards.
        redis_client.set_redis_override(None)
        assert await get_mock_offset_seconds() == 0.0
        with pytest.raises(RuntimeError):
            await set_mock_offset_seconds(10)


def _clock_rule_files() -> list[Path]:
    files: set[Path] = set()
    for pattern in CLOCK_RULE_GLOBS:
        files.update(SRC.glob(pattern))
    return sorted(f for f in files if f not in CLOCK_RULE_EXEMPT)


def test_clock_rule_covers_foundation_files():
    names = {f.relative_to(SRC).as_posix() for f in _clock_rule_files()}
    assert "services/freespace/evaluator.py" in names
    assert "api/freespace_deps.py" in names
    assert "crud/freespace_keys.py" in names
    assert "workers/freespace_tasks.py" in names


def test_no_wall_clock_calls_in_freespace_code():
    """D8: Freespace code reads time only from the injected clock."""
    offenders = []
    for path in _clock_rule_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if FORBIDDEN.search(code):
                offenders.append(
                    f"{path.relative_to(BACKEND_ROOT)}:{lineno}: {line.strip()}"
                )
    assert not offenders, (
        "Use the Freespace clock (src/services/freespace/clock.py) instead of "
        "the wall clock:\n" + "\n".join(offenders)
    )
