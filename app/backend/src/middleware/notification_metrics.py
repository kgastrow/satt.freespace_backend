"""
Notification delivery metrics for Prometheus monitoring.
Tracks notification delivery success/failure rates by channel and provider.
"""

from collections.abc import Generator
from contextlib import contextmanager
import time
from typing import Optional

from prometheus_client import Counter, Histogram

from src.logger.logger import Logger as logger


# ==================== Notification Metrics ====================

NOTIFICATION_DELIVERY_TOTAL = Counter(
    "notification_delivery_total",
    "Total notification delivery attempts",
    ["channel", "status"],
)

NOTIFICATION_DELIVERY_DURATION_SECONDS = Histogram(
    "notification_delivery_duration_seconds",
    "Notification delivery duration in seconds",
    ["channel"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

EMAIL_DELIVERY_FAILURES_TOTAL = Counter(
    "email_delivery_failures_total",
    "Total email delivery failures",
    ["provider", "error_type"],
)

SMS_DELIVERY_TOTAL = Counter(
    "sms_delivery_total",
    "Total SMS delivery attempts",
    ["provider", "status"],
)

WHATSAPP_DELIVERY_TOTAL = Counter(
    "whatsapp_delivery_total",
    "Total WhatsApp delivery attempts",
    ["provider", "status"],
)


# ==================== Helper Functions ====================


def record_notification_delivery(
    channel: str,
    status: str,
    duration: Optional[float] = None,
) -> None:
    """
    Record a notification delivery attempt.

    Args:
        channel: Notification channel (email, sms, whatsapp, in_app)
        status: Delivery status (sent, failed, skipped, pending)
        duration: Optional delivery duration in seconds
    """
    try:
        NOTIFICATION_DELIVERY_TOTAL.labels(
            channel=channel,
            status=status,
        ).inc()

        if duration is not None:
            NOTIFICATION_DELIVERY_DURATION_SECONDS.labels(
                channel=channel,
            ).observe(duration)

        logger.debug(
            f"Recorded notification delivery: channel={channel}, status={status}, "
            f"duration={duration:.3f}s"
            if duration
            else "duration=N/A"
        )
    except Exception as e:
        logger.warning(f"Failed to record notification delivery metric: {e}")


def record_email_failure(
    provider: str,
    error_type: str,
) -> None:
    """
    Record an email delivery failure.

    Args:
        provider: Email provider name (smtp, sendgrid, etc.)
        error_type: Type of error (connection, timeout, invalid_recipient, etc.)
    """
    try:
        EMAIL_DELIVERY_FAILURES_TOTAL.labels(
            provider=provider,
            error_type=error_type,
        ).inc()
        logger.debug(
            f"Recorded email failure: provider={provider}, error_type={error_type}"
        )
    except Exception as e:
        logger.warning(f"Failed to record email failure metric: {e}")


def record_sms_delivery(
    provider: str,
    status: str,
) -> None:
    """
    Record an SMS delivery attempt.

    Args:
        provider: SMS provider name (twilio, sns, etc.)
        status: Delivery status (sent, failed, skipped)
    """
    try:
        SMS_DELIVERY_TOTAL.labels(
            provider=provider,
            status=status,
        ).inc()
    except Exception as e:
        logger.warning(f"Failed to record SMS delivery metric: {e}")


def record_whatsapp_delivery(
    provider: str,
    status: str,
) -> None:
    """
    Record a WhatsApp delivery attempt.

    Args:
        provider: WhatsApp provider name (twilio, etc.)
        status: Delivery status (sent, failed, skipped)
    """
    try:
        WHATSAPP_DELIVERY_TOTAL.labels(
            provider=provider,
            status=status,
        ).inc()
    except Exception as e:
        logger.warning(f"Failed to record WhatsApp delivery metric: {e}")


@contextmanager
def track_notification_delivery(channel: str) -> Generator[dict, None, None]:
    """
    Context manager to track notification delivery time.

    Usage:
        with track_notification_delivery("email") as tracker:
            # Send notification
            result = await send_email(...)
            tracker["status"] = "sent" if result.success else "failed"

    Args:
        channel: Notification channel

    Yields:
        Dict to store status in
    """
    start_time = time.perf_counter()
    tracker: dict = {"status": "failed"}  # Default to failed

    try:
        yield tracker
    finally:
        duration = time.perf_counter() - start_time
        record_notification_delivery(channel, tracker["status"], duration)


# ==================== Aggregation Functions ====================


def get_notification_delivery_count(channel: Optional[str] = None) -> dict[str, int]:
    """
    Get notification delivery counts by status.

    Args:
        channel: Optional filter by channel

    Returns:
        Dict mapping status to count
    """
    counts: dict[str, int] = {}
    try:
        for metric in NOTIFICATION_DELIVERY_TOTAL.collect():
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    sample_channel = sample.labels.get("channel", "")
                    status = sample.labels.get("status", "")

                    if channel and sample_channel != channel:
                        continue

                    counts[status] = counts.get(status, 0) + int(sample.value)
    except Exception as e:
        logger.warning(
            f"Non-critical error in notification delivery count metrics: {e}"
        )
    return counts


def get_email_failure_count() -> int:
    """Get total email failures."""
    total = 0
    try:
        for metric in EMAIL_DELIVERY_FAILURES_TOTAL.collect():
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    total += int(sample.value)
    except Exception as e:
        logger.warning(f"Non-critical error in email failure count metrics: {e}")
    return total


def calculate_success_rate(channel: str) -> float:
    """
    Calculate success rate for a channel.

    Args:
        channel: Notification channel

    Returns:
        Success rate as percentage (0-100)
    """
    sent = 0
    total = 0

    try:
        for metric in NOTIFICATION_DELIVERY_TOTAL.collect():
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    sample_channel = sample.labels.get("channel", "")
                    status = sample.labels.get("status", "")

                    if sample_channel != channel:
                        continue

                    count = int(sample.value)
                    total += count
                    if status == "sent":
                        sent += count
    except Exception as e:
        logger.warning(f"Non-critical error in success rate metrics: {e}")

    if total == 0:
        return 100.0  # No attempts = 100% success

    return round((sent / total) * 100, 2)
