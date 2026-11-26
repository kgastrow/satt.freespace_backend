"""
Legacy module - imports from new location for backward compatibility.

This module re-exports all cron handlers from the new modular structure
at src.services.cron for backward compatibility with existing imports.

All new code should import directly from src.services.cron:
    from src.services.cron import cleanup_expired_otps_handler

The handlers are organized into the following modules:
    - src.services.cron.otp: OTP cleanup
    - src.services.cron.tokens: Token lifecycle management
    - src.services.cron.notifications: Notification cleanup and health
    - src.services.cron.storage: Storage monitoring and migration
    - src.services.cron.files: File cleanup
    - src.services.cron.sessions: Auth and session cleanup
    - src.services.cron.health: System health monitoring
    - src.services.cron.maintenance: Data lifecycle and external updates
    - src.services.cron.reports: Report generation
"""

from src.services.cron import (  # noqa: F401
    MAX_THRESHOLD_PERCENT,
    MIN_THRESHOLD_PERCENT,
    check_2fa_grace_period_handler,
    check_api_key_expiry_handler,
    check_brute_force_alerts_handler,
    check_db_pool_health_handler,
    check_disk_usage_handler,
    check_local_storage_handler,
    check_notification_health_handler,
    check_queue_health_handler,
    check_s3_storage_handler,
    check_user_type_expiry_handler,
    cleanup_deleted_files_handler,
    cleanup_expired_exports_handler,
    cleanup_expired_otps_handler,
    cleanup_expired_refresh_tokens_handler,
    cleanup_old_bg_job_executions_handler,
    cleanup_old_notifications_handler,
    cleanup_old_request_logs_handler,
    process_hard_deletions_handler,
    process_scheduled_reports_handler,
    s3_migration_handler,
    update_geoip_database_handler,
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
    # Constants
    "MIN_THRESHOLD_PERCENT",
    "MAX_THRESHOLD_PERCENT",
]
