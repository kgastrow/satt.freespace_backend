"""
Cron job handlers.

Re-exports all handlers for backward compatibility with existing imports:
    from src.services.cron_handlers import cleanup_expired_otps_handler

This module provides a centralized registry of all cron job handlers,
organized by functional area:
    - otp: OTP cleanup
    - tokens: Token lifecycle management
    - notifications: Notification cleanup and health
    - storage: Storage monitoring and migration
    - files: File cleanup
    - sessions: Auth and session cleanup
    - health: System health monitoring
    - maintenance: Data lifecycle and external updates
    - reports: Report generation
    - freespace_purge: Freespace retention purge (BF-73)
"""

from src.services.cron.files import (
    cleanup_deleted_files_handler,
    cleanup_expired_exports_handler,
)
from src.services.cron.freespace_purge import (
    cleanup_old_request_logs_configured_handler,
    freespace_daily_purge_handler,
)
from src.services.cron.health import (
    check_brute_force_alerts_handler,
    check_db_pool_health_handler,
    check_queue_health_handler,
)
from src.services.cron.maintenance import (
    process_hard_deletions_handler,
    update_geoip_database_handler,
)
from src.services.cron.notifications import (
    check_notification_health_handler,
    cleanup_old_notifications_handler,
)
from src.services.cron.otp import cleanup_expired_otps_handler
from src.services.cron.reports import process_scheduled_reports_handler
from src.services.cron.sessions import (
    check_2fa_grace_period_handler,
    check_user_type_expiry_handler,
    cleanup_old_bg_job_executions_handler,
    cleanup_old_request_logs_handler,
)
from src.services.cron.storage import (
    MAX_THRESHOLD_PERCENT,
    MIN_THRESHOLD_PERCENT,
    check_disk_usage_handler,
    check_local_storage_handler,
    check_s3_storage_handler,
    s3_migration_handler,
)
from src.services.cron.tokens import (
    check_api_key_expiry_handler,
    cleanup_expired_refresh_tokens_handler,
)


__all__ = [
    # OTP
    "cleanup_expired_otps_handler",
    # Tokens
    "cleanup_expired_refresh_tokens_handler",
    "check_api_key_expiry_handler",
    # Notifications
    "cleanup_old_notifications_handler",
    "check_notification_health_handler",
    # Storage
    "check_s3_storage_handler",
    "check_local_storage_handler",
    "check_disk_usage_handler",
    "s3_migration_handler",
    # Files
    "cleanup_deleted_files_handler",
    "cleanup_expired_exports_handler",
    # Sessions
    "check_2fa_grace_period_handler",
    "check_user_type_expiry_handler",
    "cleanup_old_request_logs_handler",
    "cleanup_old_bg_job_executions_handler",
    # Health
    "check_brute_force_alerts_handler",
    "check_queue_health_handler",
    "check_db_pool_health_handler",
    # Maintenance
    "process_hard_deletions_handler",
    "update_geoip_database_handler",
    # Reports
    "process_scheduled_reports_handler",
    # Freespace
    "freespace_daily_purge_handler",
    "cleanup_old_request_logs_configured_handler",
    # Constants (for backward compatibility)
    "MIN_THRESHOLD_PERCENT",
    "MAX_THRESHOLD_PERCENT",
]
