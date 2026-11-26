"""
Security metrics for Prometheus monitoring.
Tracks authentication failures, brute force events, and API key abuse.
"""

from prometheus_client import Counter

from src.logger.logger import Logger as logger


# ==================== Security Metrics ====================

FAILED_LOGIN_ATTEMPTS_TOTAL = Counter(
    "failed_login_attempts_total",
    "Total failed login attempts",
    ["organization_id", "reason"],
)

TWO_FACTOR_FAILURES_TOTAL = Counter(
    "two_factor_failures_total",
    "Total 2FA verification failures",
    ["organization_id", "reason"],
)

API_KEY_AUTH_FAILURES_TOTAL = Counter(
    "api_key_auth_failures_total",
    "Total API key authentication failures",
    ["organization_id", "reason"],
)

BRUTE_FORCE_EVENTS_TOTAL = Counter(
    "brute_force_events_total",
    "Total brute force detection events",
    ["ip_address", "event_type"],
)


# ==================== Helper Functions ====================


def record_failed_login(
    org_id: str,
    ip: str,
    reason: str,
) -> None:
    """
    Record a failed login attempt.

    Args:
        org_id: Organization ID (or "unknown" if not determinable)
        ip: Client IP address
        reason: Reason for failure (e.g., "invalid_credentials", "user_not_found", "suspended")
    """
    try:
        FAILED_LOGIN_ATTEMPTS_TOTAL.labels(
            organization_id=org_id or "unknown",
            reason=reason,
        ).inc()
        logger.debug(f"Recorded failed login: org={org_id}, ip={ip}, reason={reason}")
    except Exception as e:
        logger.warning(f"Failed to record failed login metric: {e}")


def record_2fa_failure(
    org_id: str,
    reason: str,
) -> None:
    """
    Record a 2FA verification failure.

    Args:
        org_id: Organization ID
        reason: Reason for failure (e.g., "invalid_code", "expired_token", "backup_code_reused")
    """
    try:
        TWO_FACTOR_FAILURES_TOTAL.labels(
            organization_id=org_id or "unknown",
            reason=reason,
        ).inc()
        logger.debug(f"Recorded 2FA failure: org={org_id}, reason={reason}")
    except Exception as e:
        logger.warning(f"Failed to record 2FA failure metric: {e}")


def record_api_key_failure(
    org_id: str,
    reason: str,
) -> None:
    """
    Record an API key authentication failure.

    Args:
        org_id: Organization ID (or "unknown" if not determinable)
        reason: Reason for failure (e.g., "invalid_key", "expired", "revoked", "rate_limited")
    """
    try:
        API_KEY_AUTH_FAILURES_TOTAL.labels(
            organization_id=org_id or "unknown",
            reason=reason,
        ).inc()
        logger.debug(f"Recorded API key failure: org={org_id}, reason={reason}")
    except Exception as e:
        logger.warning(f"Failed to record API key failure metric: {e}")


def record_brute_force_event(
    ip: str,
    event_type: str,
) -> None:
    """
    Record a brute force detection event.

    Args:
        ip: Source IP address
        event_type: Type of event (e.g., "threshold_exceeded", "ip_blocked", "attack_detected")
    """
    try:
        BRUTE_FORCE_EVENTS_TOTAL.labels(
            ip_address=ip,
            event_type=event_type,
        ).inc()
        logger.info(f"Brute force event: ip={ip}, type={event_type}")
    except Exception as e:
        logger.warning(f"Failed to record brute force event metric: {e}")


# ==================== Aggregation Functions ====================


def get_failed_logins_count() -> int:
    """Get total failed login attempts across all labels."""
    total = 0
    try:
        for metric in FAILED_LOGIN_ATTEMPTS_TOTAL.collect():
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    total += int(sample.value)
    except Exception as e:
        logger.warning(f"Non-critical error in failed logins count metrics: {e}")
    return total


def get_2fa_failures_count() -> int:
    """Get total 2FA failures across all labels."""
    total = 0
    try:
        for metric in TWO_FACTOR_FAILURES_TOTAL.collect():
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    total += int(sample.value)
    except Exception as e:
        logger.warning(f"Non-critical error in 2FA failures count metrics: {e}")
    return total


def get_api_key_failures_count() -> int:
    """Get total API key failures across all labels."""
    total = 0
    try:
        for metric in API_KEY_AUTH_FAILURES_TOTAL.collect():
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    total += int(sample.value)
    except Exception as e:
        logger.warning(f"Non-critical error in API key failures count metrics: {e}")
    return total


def get_brute_force_events_count() -> int:
    """Get total brute force events across all labels."""
    total = 0
    try:
        for metric in BRUTE_FORCE_EVENTS_TOTAL.collect():
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    total += int(sample.value)
    except Exception as e:
        logger.warning(f"Non-critical error in brute force events count metrics: {e}")
    return total
