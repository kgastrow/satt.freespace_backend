"""
Redis cache metrics for Prometheus.
Provides decorators and functions to track cache operations.
"""

from functools import wraps
import time
from typing import Any, Callable

from prometheus_client import Counter, Gauge, Histogram

from src.core.config import settings


# ==================== Cache Metrics ====================

CACHE_OPERATIONS_TOTAL = Counter(
    "cache_operations_total",
    "Total cache operations",
    ["operation", "cache_type", "result"],  # result: hit, miss, error
)

CACHE_OPERATION_DURATION_SECONDS = Histogram(
    "cache_operation_duration_seconds",
    "Cache operation duration in seconds",
    ["operation", "cache_type"],
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
)

CACHE_KEYS_TOTAL = Gauge(
    "cache_keys_total",
    "Estimated number of cached keys",
    ["cache_type"],
)

CACHE_MEMORY_BYTES = Gauge(
    "cache_memory_bytes",
    "Redis memory usage in bytes",
)

CACHE_CONNECTED = Gauge(
    "cache_connected",
    "Whether the cache is connected (1) or not (0)",
)


# ==================== Metric Recording Functions ====================


def record_cache_hit(cache_type: str, operation: str, duration: float) -> None:
    """Record a cache hit."""
    if not settings.METRICS_ENABLED:
        return
    CACHE_OPERATIONS_TOTAL.labels(
        operation=operation,
        cache_type=cache_type,
        result="hit",
    ).inc()
    CACHE_OPERATION_DURATION_SECONDS.labels(
        operation=operation,
        cache_type=cache_type,
    ).observe(duration)


def record_cache_miss(cache_type: str, operation: str, duration: float) -> None:
    """Record a cache miss."""
    if not settings.METRICS_ENABLED:
        return
    CACHE_OPERATIONS_TOTAL.labels(
        operation=operation,
        cache_type=cache_type,
        result="miss",
    ).inc()
    CACHE_OPERATION_DURATION_SECONDS.labels(
        operation=operation,
        cache_type=cache_type,
    ).observe(duration)


def record_cache_error(cache_type: str, operation: str) -> None:
    """Record a cache error."""
    if not settings.METRICS_ENABLED:
        return
    CACHE_OPERATIONS_TOTAL.labels(
        operation=operation,
        cache_type=cache_type,
        result="error",
    ).inc()


def record_cache_set(cache_type: str, duration: float) -> None:
    """Record a cache set operation."""
    if not settings.METRICS_ENABLED:
        return
    CACHE_OPERATIONS_TOTAL.labels(
        operation="set",
        cache_type=cache_type,
        result="success",
    ).inc()
    CACHE_OPERATION_DURATION_SECONDS.labels(
        operation="set",
        cache_type=cache_type,
    ).observe(duration)


def record_cache_delete(cache_type: str, duration: float) -> None:
    """Record a cache delete/invalidation operation."""
    if not settings.METRICS_ENABLED:
        return
    CACHE_OPERATIONS_TOTAL.labels(
        operation="delete",
        cache_type=cache_type,
        result="success",
    ).inc()
    CACHE_OPERATION_DURATION_SECONDS.labels(
        operation="delete",
        cache_type=cache_type,
    ).observe(duration)


def update_cache_connection_status(connected: bool) -> None:
    """Update the cache connection status gauge."""
    if not settings.METRICS_ENABLED:
        return
    CACHE_CONNECTED.set(1 if connected else 0)


def update_cache_memory(memory_bytes: int) -> None:
    """Update the cache memory usage gauge."""
    if not settings.METRICS_ENABLED:
        return
    CACHE_MEMORY_BYTES.set(memory_bytes)


# ==================== Decorator for Cache Methods ====================


def cache_metric(cache_type: str):
    """
    Decorator to add metrics to cache operations.

    Usage:
        @cache_metric("jwt")
        async def get_jwt_claims(self, token: str) -> Optional[Dict]:
            ...

    Args:
        cache_type: Type of cache (jwt, user, organization, roles)

    Returns:
        Decorated function with metrics collection
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            if not settings.METRICS_ENABLED:
                return await func(*args, **kwargs)

            start_time = time.perf_counter()
            operation = func.__name__

            try:
                result = await func(*args, **kwargs)
                duration = time.perf_counter() - start_time

                # Determine if this was a hit or miss (for get operations)
                if operation.startswith("get"):
                    if result is None:
                        record_cache_miss(cache_type, operation, duration)
                    else:
                        record_cache_hit(cache_type, operation, duration)
                elif operation.startswith("set"):
                    record_cache_set(cache_type, duration)
                elif operation.startswith("invalidate") or operation.startswith(
                    "delete"
                ):
                    record_cache_delete(cache_type, duration)
                else:
                    # Generic operation tracking
                    CACHE_OPERATION_DURATION_SECONDS.labels(
                        operation=operation,
                        cache_type=cache_type,
                    ).observe(duration)

                return result

            except Exception:
                record_cache_error(cache_type, operation)
                raise

        return wrapper

    return decorator
