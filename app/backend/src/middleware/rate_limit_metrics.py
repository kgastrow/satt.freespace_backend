"""
Rate limit metrics for Prometheus monitoring.
Tracks rate limit violations by organization, IP, and endpoint.
"""

from prometheus_client import Counter

from src.logger.logger import Logger as logger


# ==================== Rate Limit Metrics ====================

RATE_LIMIT_VIOLATIONS_TOTAL = Counter(
    "rate_limit_violations_total",
    "Total rate limit violations",
    ["organization_id", "ip_address", "endpoint"],
)

RATE_LIMIT_REQUESTS_TOTAL = Counter(
    "rate_limit_requests_total",
    "Total requests checked against rate limits",
    ["endpoint", "allowed"],
)

# Bumped once per request whose limit check could not reach Redis. The limiter
# fails OPEN in that state (see src/core/rate_limit.py), so without this counter
# the only signal that limits stopped being enforced cluster-wide is a
# throttled log line. Unlabelled on purpose: it is an infrastructure condition,
# not a per-endpoint one, and its rate is what matters.
RATE_LIMIT_STORAGE_ERRORS_TOTAL = Counter(
    "rate_limit_storage_errors_total",
    "Requests whose rate limit check could not reach its storage backend",
)


# ==================== Helper Functions ====================


def record_rate_limit_violation(
    org_id: str,
    ip: str,
    endpoint: str,
) -> None:
    """
    Record a rate limit violation.

    Args:
        org_id: Organization ID (or "unknown" if not determinable)
        ip: Client IP address
        endpoint: API endpoint that was rate limited
    """
    try:
        # Truncate endpoint to avoid high cardinality
        # Only keep the path pattern, not query params or specific IDs
        clean_endpoint = _sanitize_endpoint(endpoint)

        RATE_LIMIT_VIOLATIONS_TOTAL.labels(
            organization_id=org_id or "unknown",
            ip_address=ip,
            endpoint=clean_endpoint,
        ).inc()
        logger.debug(
            f"Recorded rate limit violation: org={org_id}, ip={ip}, endpoint={clean_endpoint}"
        )
    except Exception as e:
        logger.warning(f"Failed to record rate limit violation metric: {e}")


def record_rate_limit_check(
    endpoint: str,
    allowed: bool,
) -> None:
    """
    Record a rate limit check result.

    Args:
        endpoint: API endpoint being checked
        allowed: Whether the request was allowed
    """
    try:
        clean_endpoint = _sanitize_endpoint(endpoint)
        RATE_LIMIT_REQUESTS_TOTAL.labels(
            endpoint=clean_endpoint,
            allowed="true" if allowed else "false",
        ).inc()
    except Exception as e:
        logger.warning(f"Failed to record rate limit check metric: {e}")


def record_rate_limit_storage_error() -> None:
    """
    Record a request whose rate limit check could not reach Redis.

    Alert on a sustained non-zero rate: limits are being enforced per worker
    from memory instead of across the cluster, so the effective limit is
    multiplied by the worker count.
    """
    try:
        RATE_LIMIT_STORAGE_ERRORS_TOTAL.inc()
    except Exception:  # pragma: no cover - metrics must never break a request
        pass


def _sanitize_endpoint(endpoint: str) -> str:
    """
    Sanitize endpoint to avoid high cardinality metrics.

    Replaces UUIDs and numeric IDs with placeholders.

    Args:
        endpoint: Raw endpoint path

    Returns:
        Sanitized endpoint pattern
    """
    import re

    if not endpoint:
        return "unknown"

    # Remove query parameters
    endpoint = endpoint.split("?")[0]

    # Replace UUIDs with {id}
    uuid_pattern = (
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    )
    endpoint = re.sub(uuid_pattern, "{id}", endpoint)

    # Replace numeric IDs with {id}
    numeric_pattern = r"/\d+(?=/|$)"
    endpoint = re.sub(numeric_pattern, "/{id}", endpoint)

    # Limit length
    if len(endpoint) > 100:
        endpoint = endpoint[:100]

    return endpoint


# ==================== Aggregation Functions ====================


def get_violations_count() -> int:
    """Get total rate limit violations."""
    total = 0
    try:
        for metric in RATE_LIMIT_VIOLATIONS_TOTAL.collect():
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    total += int(sample.value)
    except Exception as e:
        logger.warning(f"Non-critical error in violations count metrics: {e}")
    return total


def get_violations_by_endpoint() -> dict[str, int]:
    """Get violations count grouped by endpoint."""
    by_endpoint: dict[str, int] = {}
    try:
        for metric in RATE_LIMIT_VIOLATIONS_TOTAL.collect():
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    endpoint = sample.labels.get("endpoint", "unknown")
                    by_endpoint[endpoint] = by_endpoint.get(endpoint, 0) + int(
                        sample.value
                    )
    except Exception as e:
        logger.warning(f"Non-critical error in violations by endpoint metrics: {e}")
    return by_endpoint


def get_violations_by_ip() -> dict[str, int]:
    """Get violations count grouped by IP address."""
    by_ip: dict[str, int] = {}
    try:
        for metric in RATE_LIMIT_VIOLATIONS_TOTAL.collect():
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    ip = sample.labels.get("ip_address", "unknown")
                    by_ip[ip] = by_ip.get(ip, 0) + int(sample.value)
    except Exception as e:
        logger.warning(f"Non-critical error in violations by IP metrics: {e}")
    return by_ip
