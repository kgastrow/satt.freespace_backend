"""
Cron job configuration mapping to SystemConfig keys.

This module defines which SystemConfig keys are associated with each cron job,
allowing the UI to display and edit relevant configuration for each job.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class CronJobConfigKey:
    """Represents a single SystemConfig key associated with a cron job."""

    key: str
    value_type: str  # "integer", "string", "boolean", "float"
    default: Any
    label: str
    description: str
    min_value: int | None = None
    max_value: int | None = None


# Mapping of cron job codes to their SystemConfig keys
CRON_JOB_CONFIG_MAPPING: dict[str, list[CronJobConfigKey]] = {
    "cleanup_old_notifications": [
        CronJobConfigKey(
            key="cleanup.notifications.retention_days",
            value_type="integer",
            default=90,
            label="Notification Retention Days",
            description="Number of days to retain notifications before automatic cleanup",
            min_value=1,
            max_value=365,
        ),
    ],
    "cleanup_deleted_files": [
        CronJobConfigKey(
            key="cleanup.deleted_files.retention_days",
            value_type="integer",
            default=30,
            label="Deleted File Retention Days",
            description="Number of days to retain soft-deleted files before permanent deletion",
            min_value=1,
            max_value=365,
        ),
    ],
    "cleanup_old_request_logs": [
        CronJobConfigKey(
            key="request_logs.retention_days",
            value_type="integer",
            default=30,
            label="Request Log Retention Days",
            description="Number of days to retain request logs before automatic cleanup",
            min_value=1,
            max_value=365,
        ),
    ],
    "s3_storage_monitor": [
        CronJobConfigKey(
            key="s3_storage.total_allocated_bytes",
            value_type="integer",
            default=None,
            label="Total Allocated Storage (bytes)",
            description="Total S3 storage capacity in bytes for monitoring alerts",
            min_value=1,
            max_value=None,
        ),
        CronJobConfigKey(
            key="s3_storage.warning_threshold_percent",
            value_type="integer",
            default=20,
            label="Warning Threshold (%)",
            description="Send alert when remaining storage falls below this percentage",
            min_value=1,
            max_value=99,
        ),
    ],
    "local_storage_monitor": [
        CronJobConfigKey(
            key="local_storage.total_allocated_bytes",
            value_type="integer",
            default=None,
            label="Total Allocated Storage (bytes)",
            description="Total local storage capacity in bytes for monitoring alerts",
            min_value=1,
            max_value=None,
        ),
        CronJobConfigKey(
            key="local_storage.warning_threshold_percent",
            value_type="integer",
            default=20,
            label="Warning Threshold (%)",
            description="Send alert when remaining storage falls below this percentage",
            min_value=1,
            max_value=99,
        ),
    ],
    "update_geoip_database": [
        CronJobConfigKey(
            key="geoip.maxmind.account_id",
            value_type="string",
            default=None,
            label="MaxMind Account ID",
            description="Your MaxMind account ID for downloading GeoIP databases",
        ),
        CronJobConfigKey(
            key="geoip.maxmind.license_key",
            value_type="string",
            default=None,
            label="MaxMind License Key",
            description="Your MaxMind license key (stored encrypted)",
        ),
        CronJobConfigKey(
            key="geoip.maxmind.edition_id",
            value_type="string",
            default="GeoLite2-City",
            label="Database Edition ID",
            description="MaxMind database edition (e.g., GeoLite2-City, GeoLite2-Country)",
        ),
    ],
}


def get_config_keys_for_job(job_code: str) -> list[CronJobConfigKey]:
    """
    Get the SystemConfig keys associated with a cron job.

    Args:
        job_code: The cron job code

    Returns:
        List of CronJobConfigKey objects for the job, or empty list if none
    """
    return CRON_JOB_CONFIG_MAPPING.get(job_code, [])


def has_config_keys(job_code: str) -> bool:
    """
    Check if a cron job has associated SystemConfig keys.

    Args:
        job_code: The cron job code

    Returns:
        True if the job has config keys, False otherwise
    """
    return job_code in CRON_JOB_CONFIG_MAPPING
