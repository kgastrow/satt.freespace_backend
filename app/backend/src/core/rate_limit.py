"""
Rate limiting configuration using SlowAPI with Redis backend.
Provides limiter instance for use across the application.
Uses Redis for storage to support multiple workers and horizontal scaling.

WHY THIS FILE IS MORE THAN A ``Limiter(...)`` CALL
--------------------------------------------------
slowapi 0.1.9 drives ``limits`` with a *synchronous* Redis client, called from
``SlowAPIMiddleware`` on the event loop for every request. Two consequences had
to be engineered around, both verified against the pinned packages:

1. **It failed closed, with a 500.** With no in-memory fallback and
   ``swallow_errors`` off, a storage exception propagated out of
   ``_check_request_limit``; ``slowapi/middleware.py`` then looked for a handler
   registered for ``redis.ConnectionError``, found none, and fell back to
   slowapi's ``_rate_limit_exceeded_handler``, which dereferences ``exc.detail``
   on an exception that has no such attribute. Every request became
   ``AttributeError`` -> HTTP 500. Because ``SlowAPIMiddleware`` runs on EVERY
   request, not only decorated routes, a Redis blip was a total API outage.
2. **It had no socket timeouts.** ``storage_uri`` alone means ``redis.from_url``
   is called with no options, so ``socket_timeout`` and
   ``socket_connect_timeout`` are both ``None``. A Redis that accepts the
   connection but stops answering (swap, ``maxmemory`` pressure, a network black
   hole) blocks the worker's event loop *indefinitely* -- taking down every
   coroutine in the process, not just the limiter.

WHY THE STORAGE IS STILL SYNCHRONOUS
------------------------------------
``limits`` offers ``async+redis://``, but slowapi 0.1.9 cannot use it:
``extension.py`` builds its strategy from ``limits.strategies.STRATEGIES``,
whose ``hit``/``test`` are plain synchronous methods. Handed an async storage
they would return un-awaited coroutines, and ``if not self.limiter.hit(...)``
would treat every coroutine as truthy -- silently disabling rate limiting
entirely. So the storage stays synchronous, and the blocking call is bounded by
the socket timeouts below instead.

STABILITY NOTE
--------------
``FailOpenLimiter`` overrides ``Limiter._check_request_limit``, a PRIVATE
slowapi method. requirements.txt pins ``slowapi==0.1.9``. If that pin is ever
moved and the method is renamed, this subclass would silently stop being called
and the fail-open behaviour would vanish -- so
``tests/unit_tests/test_rate_limit_fail_open.py`` asserts the method still
exists on the base class.
"""

import threading
import time
from typing import Any, Callable, Optional, cast

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from src.core.client_ip import client_ip_key
from src.core.config import settings
from src.logger.logger import Logger as logger


# Use Redis storage for rate limiting across multiple workers
# Format: redis://host:port/db
storage_uri = settings.REDIS_URL if settings.RATE_LIMIT_ENABLED else None

# Bound the blocking Redis call the limiter makes on the event loop. These are
# forwarded verbatim to ``redis.from_url`` by ``limits.storage.RedisStorage``.
RATE_LIMIT_SOCKET_TIMEOUT_SECONDS = 1.0
RATE_LIMIT_SOCKET_CONNECT_TIMEOUT_SECONDS = 1.0

# A storage outage is a sustained condition, not a per-request event. Log it at
# most this often so an outage costs a handful of lines rather than one per
# request across every worker.
STORAGE_ERROR_LOG_INTERVAL_SECONDS = 60.0

STORAGE_OPTIONS: dict[str, Any] = {
    "socket_timeout": RATE_LIMIT_SOCKET_TIMEOUT_SECONDS,
    "socket_connect_timeout": RATE_LIMIT_SOCKET_CONNECT_TIMEOUT_SECONDS,
}


def _record_storage_error() -> None:
    """Bump the Prometheus counter, importing late to avoid an import cycle.

    ``src.middleware`` imports this module, so a module-level import of anything
    under ``src.middleware`` would be circular.
    """
    try:
        from src.middleware.rate_limit_metrics import record_rate_limit_storage_error

        record_rate_limit_storage_error()
    except Exception:  # pragma: no cover - metrics must never break a request
        pass


class FailOpenLimiter(Limiter):
    """A ``Limiter`` that degrades instead of failing the request.

    Two layers, because they cover different failures:

    * ``in_memory_fallback_enabled=True`` (passed below) makes slowapi catch the
      storage exception itself, flip ``_storage_dead``, and re-run the same
      limits against a process-local ``MemoryStorage``. Limits keep being
      enforced during the outage -- per worker rather than per cluster, which is
      the right trade -- and slowapi retries Redis on an exponential backoff
      (``__should_check_backend`` / ``_storage.check()``), clearing
      ``_storage_dead`` when it answers again.
    * This subclass is the backstop for anything that mechanism does not catch,
      and the place the outage is *observed*. slowapi's own notice is a single
      ``logger.warn`` on the ``slowapi`` logger; this records a metric and an
      application WARNING on the dead/recovered transitions, throttled to
      ``STORAGE_ERROR_LOG_INTERVAL_SECONDS``.

    A ``RateLimitExceeded`` is re-raised untouched -- that is the limiter
    working, not failing.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._last_storage_error_log: float = 0.0
        # Thread-local, not a plain attribute: a *sync* endpoint decorated with
        # @limiter.limit is run by FastAPI in a threadpool, so two requests can
        # be inside this method on different threads at once. A shared flag
        # would let one of them mistake the other for slowapi's re-entry and
        # skip the fail-open wrapper entirely.
        self._reentry = threading.local()
        self.storage_error_log_interval: float = STORAGE_ERROR_LOG_INTERVAL_SECONDS

    def _log_storage_unavailable(self, reason: str) -> None:
        """WARNING at most once per ``storage_error_log_interval``.

        Deliberately not per request: a Redis outage affects every request, and
        one line each would bury the incident in its own noise across every
        worker. The metric carries the per-request volume.
        """
        now = time.monotonic()
        if (
            self._last_storage_error_log
            and now - self._last_storage_error_log < self.storage_error_log_interval
        ):
            return
        self._last_storage_error_log = now
        logger.warning(
            "Rate limit storage unavailable (%s). Limits are being enforced "
            "in-process instead of across workers; requests are NOT being "
            "rejected. Suppressing this warning for %ss.",
            reason,
            int(self.storage_error_log_interval),
        )

    def _check_request_limit(
        self,
        request: Any,
        endpoint_func: Optional[Callable[..., Any]],
        in_middleware: bool = True,
    ) -> None:
        if getattr(self._reentry, "active", False):
            # slowapi re-enters this method once, from its own except handler,
            # when it flips to the in-memory fallback. Let that inner call run
            # bare so one request does not book two storage errors.
            super()._check_request_limit(request, endpoint_func, in_middleware)
            return

        was_dead = self._storage_dead
        self._reentry.active = True
        recorded = False
        try:
            super()._check_request_limit(request, endpoint_func, in_middleware)
        except RateLimitExceeded:
            raise
        except Exception as exc:
            # slowapi's own fallback did not absorb it. Allow the request: a
            # limiter that cannot reach its storage must not become an outage.
            _record_storage_error()
            recorded = True
            self._log_storage_unavailable(f"{type(exc).__name__}: {exc}")
            # __evaluate_limits sets view_rate_limit at the END of its run, so
            # an exception part-way through leaves it unset -- and
            # SlowAPIMiddleware reads it unconditionally after a check it
            # believes succeeded, which would raise AttributeError and reinstate
            # the 500 we just avoided.
            try:
                request.state.view_rate_limit = None
            except Exception:  # pragma: no cover - defensive
                pass
        finally:
            self._reentry.active = False
            if self._storage_dead:
                # Per request, so the counter's rate shows the outage's size.
                if not recorded:
                    _record_storage_error()
                if not was_dead:
                    self._log_storage_unavailable("storage marked dead")
            elif was_dead:
                self._last_storage_error_log = 0.0
                logger.info(
                    "Rate limit storage recovered; limits are cluster-wide again"
                )


# Rate limiter - applies default limit to all endpoints per IP address.
#
# key_func is client_ip_key, NOT slowapi's get_remote_address. The latter reads
# request.client.host, which is the CDN edge address behind a CDN (so every
# visitor through one PoP shared a single bucket) and is outright forgeable when
# uvicorn runs with --forwarded-allow-ips='*'. See src/core/client_ip.py.
limiter = FailOpenLimiter(
    key_func=client_ip_key,
    enabled=settings.RATE_LIMIT_ENABLED,
    default_limits=[settings.RATE_LIMIT_DEFAULT],
    storage_uri=storage_uri,
    # slowapi types this Dict[str, str] but forwards it straight to
    # redis.from_url, which wants numbers for the timeouts.
    storage_options=cast(dict[str, str], STORAGE_OPTIONS),
    # Enabled with no explicit fallback limits: slowapi then re-evaluates the
    # SAME limits against MemoryStorage, rather than a separate weaker set.
    in_memory_fallback_enabled=True,
    # Belt to the fallback's braces: if the in-memory path itself ever raises,
    # slowapi swallows rather than 500s.
    swallow_errors=True,
)
