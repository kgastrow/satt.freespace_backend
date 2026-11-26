"""
Prometheus metrics collection middleware for FastAPI.
Provides request/response metrics with minimal overhead.
"""

import os
import socket
import time
from typing import Callable, Optional

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match

from src.core.config import settings
from src.logger.logger import Logger as logger


# ==================== Instance Identification ====================


def get_instance_id() -> str:
    """
    Generate or retrieve a unique instance ID.
    Uses METRICS_INSTANCE_ID from config, or generates one from hostname + process ID.
    """
    if settings.METRICS_INSTANCE_ID:
        return settings.METRICS_INSTANCE_ID

    hostname = socket.gethostname()
    pid = os.getpid()
    return f"{hostname}-{pid}"


INSTANCE_ID = get_instance_id()


# ==================== Metrics Definitions ====================

# Request metrics
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "HTTP requests currently being processed",
    ["method", "endpoint"],
)

HTTP_REQUEST_SIZE_BYTES = Histogram(
    "http_request_size_bytes",
    "HTTP request body size in bytes",
    ["method", "endpoint"],
    buckets=[100, 1000, 10000, 100000, 1000000, 10000000],
)

HTTP_RESPONSE_SIZE_BYTES = Histogram(
    "http_response_size_bytes",
    "HTTP response body size in bytes",
    ["method", "endpoint"],
    buckets=[100, 1000, 10000, 100000, 1000000, 10000000],
)

HTTP_SLOW_REQUESTS_TOTAL = Counter(
    "http_slow_requests_total",
    "HTTP requests exceeding slow threshold",
    ["method", "endpoint"],
)

# Error metrics
HTTP_ERRORS_TOTAL = Counter(
    "http_errors_total",
    "Total HTTP errors (4xx and 5xx)",
    ["method", "endpoint", "status_code", "error_type"],
)

EXCEPTIONS_TOTAL = Counter(
    "exceptions_total",
    "Total unhandled exceptions",
    ["exception_type", "endpoint"],
)

AUTH_FAILURES_TOTAL = Counter(
    "auth_failures_total",
    "Authentication failures",
    ["failure_reason"],
)

VALIDATION_ERRORS_TOTAL = Counter(
    "validation_errors_total",
    "Request validation errors",
    ["endpoint"],
)

# Instance metrics
INSTANCE_INFO = Info(
    "app_instance",
    "Application instance information",
)

APP_START_TIME = Gauge(
    "app_start_time_seconds",
    "Application start time in Unix timestamp",
    ["instance_id"],
)

# Concurrent users (updated by user activity service)
ACTIVE_USERS_CURRENT = Gauge(
    "active_users_current",
    "Currently active users",
    ["window"],
)

CONCURRENT_REQUESTS = Gauge(
    "concurrent_requests",
    "Current number of concurrent requests being processed",
)


# ==================== Helper Functions ====================


def get_path_template(request: Request) -> str:
    """
    Extract the path template (with parameter placeholders) from the request.
    This normalizes paths like /users/123 to /users/{user_id}.
    """
    # Try to get the path from the matched route
    for route in request.app.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            return route.path

    # Fallback to raw path (grouped to avoid cardinality explosion)
    path = request.url.path

    # Simple grouping for common patterns
    parts = path.split("/")
    normalized_parts = []
    for part in parts:
        # Replace UUIDs
        if len(part) == 36 and part.count("-") == 4:
            normalized_parts.append("{id}")
        # Replace numeric IDs
        elif part.isdigit():
            normalized_parts.append("{id}")
        else:
            normalized_parts.append(part)

    return "/".join(normalized_parts) or "/"


def classify_error(status_code: int) -> str:
    """Classify error type based on status code."""
    if status_code == 401:
        return "authentication"
    elif status_code == 403:
        return "authorization"
    elif status_code == 404:
        return "not_found"
    elif status_code == 422:
        return "validation"
    elif status_code == 429:
        return "rate_limit"
    elif 400 <= status_code < 500:
        return "client_error"
    elif status_code >= 500:
        return "server_error"
    return "unknown"


# ==================== Middleware ====================


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to collect HTTP request metrics.
    Tracks request count, duration, size, and errors.
    """

    def __init__(self, app, excluded_paths: Optional[set[str]] = None):
        super().__init__(app)
        self.excluded_paths = excluded_paths or set()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip metrics for excluded paths
        if request.url.path in self.excluded_paths:
            return await call_next(request)

        method = request.method
        endpoint = get_path_template(request)

        # Track in-progress requests
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).inc()
        CONCURRENT_REQUESTS.inc()

        # Record request size
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                HTTP_REQUEST_SIZE_BYTES.labels(
                    method=method, endpoint=endpoint
                ).observe(int(content_length))
            except ValueError:
                pass

        start_time = time.perf_counter()
        status_code = 500  # Default in case of exception

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response

        except Exception as exc:
            # Track unhandled exceptions
            EXCEPTIONS_TOTAL.labels(
                exception_type=type(exc).__name__,
                endpoint=endpoint,
            ).inc()
            raise

        finally:
            # Calculate duration
            duration = time.perf_counter() - start_time

            # Record request metrics
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                endpoint=endpoint,
                status_code=str(status_code),
            ).inc()

            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                endpoint=endpoint,
            ).observe(duration)

            # Track slow requests
            if duration > settings.METRICS_SLOW_REQUEST_THRESHOLD:
                HTTP_SLOW_REQUESTS_TOTAL.labels(
                    method=method,
                    endpoint=endpoint,
                ).inc()

            # Track errors
            if status_code >= 400:
                HTTP_ERRORS_TOTAL.labels(
                    method=method,
                    endpoint=endpoint,
                    status_code=str(status_code),
                    error_type=classify_error(status_code),
                ).inc()

                # Track specific error types
                if status_code == 401:
                    AUTH_FAILURES_TOTAL.labels(failure_reason="invalid_token").inc()
                elif status_code == 422:
                    VALIDATION_ERRORS_TOTAL.labels(endpoint=endpoint).inc()

            # Record response size if available
            if "response" in dir() and hasattr(response, "headers"):
                response_size = response.headers.get("content-length")
                if response_size:
                    try:
                        HTTP_RESPONSE_SIZE_BYTES.labels(
                            method=method, endpoint=endpoint
                        ).observe(int(response_size))
                    except ValueError:
                        pass

            # Decrement in-progress counters
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).dec()
            CONCURRENT_REQUESTS.dec()


# ==================== Setup Functions ====================


def setup_metrics(app: FastAPI) -> None:
    """
    Configure and attach metrics middleware to the FastAPI application.
    Also exposes the /metrics endpoint for Prometheus scraping.
    """
    if not settings.METRICS_ENABLED:
        logger.info("Metrics collection disabled")
        return

    # Parse excluded paths
    excluded_paths = set(
        path.strip()
        for path in settings.METRICS_EXCLUDED_PATHS.split(",")
        if path.strip()
    )

    # Add metrics middleware
    app.add_middleware(MetricsMiddleware, excluded_paths=excluded_paths)

    # Set instance info
    INSTANCE_INFO.info(
        {
            "instance_id": INSTANCE_ID,
            "hostname": socket.gethostname(),
            "version": app.version or "unknown",
        }
    )

    # Set app start time
    APP_START_TIME.labels(instance_id=INSTANCE_ID).set(time.time())

    # Add metrics endpoint
    @app.get(settings.METRICS_ENDPOINT, include_in_schema=False)
    async def metrics():
        """Prometheus metrics endpoint."""
        return Response(
            content=generate_latest(REGISTRY),
            media_type=CONTENT_TYPE_LATEST,
        )

    logger.info(f"Metrics enabled at {settings.METRICS_ENDPOINT}")


# ==================== Public Metrics API ====================


def record_auth_failure(reason: str) -> None:
    """Record an authentication failure."""
    AUTH_FAILURES_TOTAL.labels(failure_reason=reason).inc()


def record_exception(exception_type: str, endpoint: str) -> None:
    """Record an unhandled exception."""
    EXCEPTIONS_TOTAL.labels(exception_type=exception_type, endpoint=endpoint).inc()


def update_active_users(count: int, window: str = "5m") -> None:
    """Update the active users gauge."""
    ACTIVE_USERS_CURRENT.labels(window=window).set(count)
