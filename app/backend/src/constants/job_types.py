"""
Background Job Type Definitions.

Defines all known background job types with their descriptions and categories.

This registry is the background jobs panel's allowlist: the stats endpoint
iterates it and looks up database stats per known code. A task that runs but
is absent here records to the database and is then never displayed, so every
new `@instrument_task` needs a `JobTypeDefinition` in the same change.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class JobTypeDefinition:
    """Definition of a background job type."""

    code: str
    name: str
    description: str
    category: str
    is_cron: bool = False


# Job categories
CATEGORY_EMAIL = "email"
CATEGORY_CLEANUP = "cleanup"
CATEGORY_NOTIFICATIONS = "notifications"
CATEGORY_FILES = "files"
CATEGORY_DATA = "data"
CATEGORY_PAYMENTS = "payments"
CATEGORY_SECURITY = "security"
CATEGORY_SYSTEM = "system"


# All known job types
JOB_TYPES: list[JobTypeDefinition] = [
    # Email tasks
    JobTypeDefinition(
        code="send_email_task",
        name="Send Email",
        description="Send a single email asynchronously",
        category=CATEGORY_EMAIL,
    ),
    JobTypeDefinition(
        code="send_invitation_email_task",
        name="Send Invitation Email",
        description="Send an organization invitation email",
        category=CATEGORY_EMAIL,
    ),
    JobTypeDefinition(
        code="send_otp_email_task",
        name="Send OTP Email",
        description="Send OTP verification email",
        category=CATEGORY_EMAIL,
    ),
    JobTypeDefinition(
        code="send_password_reset_email_task",
        name="Send Password Reset Email",
        description="Send password reset email",
        category=CATEGORY_EMAIL,
    ),
    # Cleanup tasks
    JobTypeDefinition(
        code="cleanup_expired_otps_task",
        name="Cleanup Expired OTPs",
        description="Remove expired OTP codes from the database",
        category=CATEGORY_CLEANUP,
        is_cron=True,
    ),
    JobTypeDefinition(
        code="cleanup_expired_refresh_tokens_task",
        name="Cleanup Expired Refresh Tokens",
        description="Remove expired refresh tokens from the database",
        category=CATEGORY_CLEANUP,
        is_cron=True,
    ),
    JobTypeDefinition(
        code="cleanup_old_request_logs_task",
        name="Cleanup Old Request Logs",
        description="Remove old request logs past retention period",
        category=CATEGORY_CLEANUP,
        is_cron=True,
    ),
    JobTypeDefinition(
        code="cleanup_old_notifications_task",
        name="Cleanup Old Notifications",
        description="Remove notifications older than retention period",
        category=CATEGORY_CLEANUP,
        is_cron=True,
    ),
    JobTypeDefinition(
        code="cleanup_deleted_files_task",
        name="Cleanup Deleted Files",
        description="Hard delete files past retention period from storage",
        category=CATEGORY_CLEANUP,
        is_cron=True,
    ),
    # Notification tasks
    JobTypeDefinition(
        code="send_notification_task",
        name="Send Notification",
        description="Send a single notification via the appropriate provider",
        category=CATEGORY_NOTIFICATIONS,
    ),
    JobTypeDefinition(
        code="process_bulk_notification_task",
        name="Process Bulk Notification",
        description="Process a batch of bulk notifications",
        category=CATEGORY_NOTIFICATIONS,
    ),
    JobTypeDefinition(
        code="check_delivery_status_task",
        name="Check Delivery Status",
        description="Check and update delivery status from notification provider",
        category=CATEGORY_NOTIFICATIONS,
    ),
    # File tasks
    JobTypeDefinition(
        code="process_file_upload_task",
        name="Process File Upload",
        description="Extract metadata from uploaded files",
        category=CATEGORY_FILES,
    ),
    JobTypeDefinition(
        code="recalculate_usage_task",
        name="Recalculate File Usage",
        description="Recalculate file usage statistics for an organization",
        category=CATEGORY_FILES,
    ),
    # Data export tasks
    JobTypeDefinition(
        code="process_data_export_task",
        name="Process Data Export",
        description="Generate and upload user data export ZIP",
        category=CATEGORY_DATA,
    ),
    # Payment tasks
    JobTypeDefinition(
        code="process_payment_webhook_task",
        name="Process Payment Webhook",
        description="Process incoming payment webhook",
        category=CATEGORY_PAYMENTS,
    ),
    JobTypeDefinition(
        code="sync_payment_status_task",
        name="Sync Payment Status",
        description="Sync payment status with payment provider",
        category=CATEGORY_PAYMENTS,
    ),
    JobTypeDefinition(
        code="reconcile_pending_payments_task",
        name="Reconcile Pending Payments",
        description="Reconcile pending payments that may have missed webhooks",
        category=CATEGORY_PAYMENTS,
        is_cron=True,
    ),
    # Security tasks
    JobTypeDefinition(
        code="notify_2fa_mandatory_change",
        name="Notify 2FA Mandatory Change",
        description="Notify users about mandatory 2FA policy change",
        category=CATEGORY_SECURITY,
    ),
    JobTypeDefinition(
        code="check_2fa_grace_period_expired",
        name="Check 2FA Grace Period",
        description="Check for users whose 2FA grace period has expired",
        category=CATEGORY_SECURITY,
        is_cron=True,
    ),
    # System tasks
    JobTypeDefinition(
        code="collect_metrics_task",
        name="Collect Metrics",
        description="Collect system metrics for monitoring",
        category=CATEGORY_SYSTEM,
        is_cron=True,
    ),
    JobTypeDefinition(
        code="system_cron_scheduler_task",
        name="Cron Scheduler",
        description="Check for due cron jobs and execute them",
        category=CATEGORY_SYSTEM,
        is_cron=True,
    ),
]


# Create lookup dictionaries
JOB_TYPES_BY_CODE: dict[str, JobTypeDefinition] = {jt.code: jt for jt in JOB_TYPES}
JOB_TYPE_CODES: list[str] = [jt.code for jt in JOB_TYPES]


def get_job_type(code: str) -> Optional[JobTypeDefinition]:
    """Get a job type definition by code."""
    return JOB_TYPES_BY_CODE.get(code)


def get_all_job_types() -> list[JobTypeDefinition]:
    """Get all job type definitions."""
    return JOB_TYPES


def get_non_cron_job_types() -> list[JobTypeDefinition]:
    """Get all job type definitions that are NOT cron jobs."""
    return [jt for jt in JOB_TYPES if not jt.is_cron]


def get_cron_job_types() -> list[JobTypeDefinition]:
    """Get all job type definitions that are cron jobs."""
    return [jt for jt in JOB_TYPES if jt.is_cron]


def get_job_types_by_category(category: str) -> list[JobTypeDefinition]:
    """Get all job types in a category."""
    return [jt for jt in JOB_TYPES if jt.category == category]
