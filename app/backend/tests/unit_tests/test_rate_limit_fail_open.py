"""
Tests for the fail-open rate limiter (src/core/rate_limit.py).

SlowAPIMiddleware runs on EVERY request, not only decorated routes, so a
limiter that raises on a storage error turns a Redis blip into a total API
outage. These tests pin the fail-open behaviour and the slowapi contract it
depends on.
"""

import threading

import pytest
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from src.core import rate_limit as rate_limit_module
from src.core.rate_limit import (
    STORAGE_OPTIONS,
    FailOpenLimiter,
    limiter,
)


# ==================== The slowapi contract this depends on ====================


def test_slowapi_private_method_still_exists():
    """FailOpenLimiter overrides a PRIVATE slowapi method.

    requirements.txt pins slowapi==0.1.9. If that pin is ever moved and
    ``_check_request_limit`` is renamed or removed, the override would silently
    stop being called: rate limiting would either fail closed again (500s on a
    Redis blip) or stop being enforced, with no error anywhere. Fail here
    instead, at the upgrade.
    """
    assert hasattr(Limiter, "_check_request_limit"), (
        "slowapi.Limiter._check_request_limit is gone. FailOpenLimiter in "
        "src/core/rate_limit.py overrides it; re-point the override at the new "
        "method before shipping this slowapi version."
    )
    assert callable(Limiter._check_request_limit)


def test_slowapi_storage_dead_flag_still_exists():
    """The fail-open bookkeeping reads Limiter._storage_dead."""
    assert hasattr(limiter, "_storage_dead")


def test_limiter_is_fail_open():
    assert isinstance(limiter, FailOpenLimiter)


# ==================== Constructor hardening ====================


def test_socket_timeouts_are_configured():
    """Without these, redis.from_url gets socket_timeout=None and a Redis that
    accepts connections but stops answering blocks the event loop forever."""
    assert STORAGE_OPTIONS["socket_timeout"] > 0
    assert STORAGE_OPTIONS["socket_connect_timeout"] > 0


def test_in_memory_fallback_and_swallow_errors_enabled():
    assert limiter._in_memory_fallback_enabled is True
    assert limiter._swallow_errors is True


# ==================== Fail-open behaviour ====================


class _Boom(Exception):
    pass


class _FakeState:
    pass


class _FakeRequest:
    def __init__(self):
        self.state = _FakeState()


def _build_limiter(monkeypatch, side_effect):
    """A FailOpenLimiter whose super() call does whatever we tell it to."""
    test_limiter = FailOpenLimiter(key_func=lambda request: "k", enabled=False)

    calls = []

    def fake_super(self, request, endpoint_func, in_middleware=True):
        calls.append((request, endpoint_func, in_middleware))
        if side_effect is not None:
            raise side_effect

    monkeypatch.setattr(Limiter, "_check_request_limit", fake_super)
    return test_limiter, calls


def test_storage_error_does_not_propagate(monkeypatch):
    """A Redis failure must allow the request, not 500 it."""
    test_limiter, calls = _build_limiter(monkeypatch, _Boom("redis down"))
    request = _FakeRequest()

    test_limiter._check_request_limit(request, None, True)

    assert len(calls) == 1


def test_storage_error_sets_view_rate_limit_to_none(monkeypatch):
    """SlowAPIMiddleware reads request.state.view_rate_limit unconditionally
    after a check it believes succeeded. Leaving it unset raises AttributeError
    and reinstates the 500 we just avoided."""
    test_limiter, _ = _build_limiter(monkeypatch, _Boom("redis down"))
    request = _FakeRequest()

    test_limiter._check_request_limit(request, None, True)

    assert request.state.view_rate_limit is None


def test_rate_limit_exceeded_is_re_raised(monkeypatch):
    """A limit being hit is the limiter working, not failing."""
    from limits import parse

    class _FakeLimit:
        error_message = None
        limit = parse("1/minute")

    test_limiter, _ = _build_limiter(monkeypatch, RateLimitExceeded(_FakeLimit()))
    request = _FakeRequest()

    with pytest.raises(RateLimitExceeded):
        test_limiter._check_request_limit(request, None, True)


def test_storage_error_records_metric_once(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        rate_limit_module, "_record_storage_error", lambda: recorded.append(1)
    )
    test_limiter, _ = _build_limiter(monkeypatch, _Boom("redis down"))

    test_limiter._check_request_limit(_FakeRequest(), None, True)

    assert len(recorded) == 1


def test_successful_check_records_nothing(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        rate_limit_module, "_record_storage_error", lambda: recorded.append(1)
    )
    test_limiter, _ = _build_limiter(monkeypatch, None)

    test_limiter._check_request_limit(_FakeRequest(), None, True)

    assert recorded == []


def test_reentry_guard_lets_slowapis_own_fallback_run_bare(monkeypatch):
    """slowapi re-enters this method from its own except handler when it flips
    to the in-memory fallback. The inner call must not book a second error."""
    recorded = []
    monkeypatch.setattr(
        rate_limit_module, "_record_storage_error", lambda: recorded.append(1)
    )
    test_limiter = FailOpenLimiter(key_func=lambda request: "k", enabled=False)

    depth = {"n": 0}

    def fake_super(self, request, endpoint_func, in_middleware=True):
        depth["n"] += 1
        if depth["n"] == 1:
            # Re-enter, the way slowapi's fallback path does.
            test_limiter._check_request_limit(request, endpoint_func, in_middleware)
            raise _Boom("outer failure after fallback")

    monkeypatch.setattr(Limiter, "_check_request_limit", fake_super)

    test_limiter._check_request_limit(_FakeRequest(), None, True)

    assert depth["n"] == 2
    # One error for the outer call only.
    assert len(recorded) == 1


def test_reentry_guard_is_thread_local(monkeypatch):
    """A *sync* endpoint decorated with @limiter.limit runs in a threadpool, so
    two requests can be inside this method on different threads at once. A
    shared flag would let one mistake the other for slowapi's re-entry and skip
    the fail-open wrapper entirely."""
    recorded = []
    monkeypatch.setattr(
        rate_limit_module, "_record_storage_error", lambda: recorded.append(1)
    )
    test_limiter = FailOpenLimiter(key_func=lambda request: "k", enabled=False)

    both_inside = threading.Barrier(2, timeout=5)

    def fake_super(self, request, endpoint_func, in_middleware=True):
        both_inside.wait()
        raise _Boom("redis down")

    monkeypatch.setattr(Limiter, "_check_request_limit", fake_super)

    errors: list[BaseException] = []

    def run():
        try:
            test_limiter._check_request_limit(_FakeRequest(), None, True)
        except BaseException as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert errors == []
    # Both threads took the fail-open path; neither was mistaken for a re-entry.
    assert len(recorded) == 2


def test_storage_error_log_is_throttled(monkeypatch):
    """One line per request across every worker would bury the incident in its
    own noise."""
    monkeypatch.setattr(rate_limit_module, "_record_storage_error", lambda: None)
    test_limiter, _ = _build_limiter(monkeypatch, _Boom("redis down"))

    warnings = []
    monkeypatch.setattr(
        rate_limit_module.logger, "warning", lambda *a, **k: warnings.append(a)
    )

    for _ in range(5):
        test_limiter._check_request_limit(_FakeRequest(), None, True)

    assert len(warnings) == 1
