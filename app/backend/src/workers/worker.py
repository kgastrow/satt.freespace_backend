"""
ARQ worker entry point.
This module is used by the arq CLI to start the worker.

Usage:
    arq src.workers.worker.WorkerSettings
"""

from arq import cron

from src.constants.queues import ARQ_QUEUE_NAME
from src.workers.job_metrics import instrument_cron_task, instrument_task
from src.workers.payment_tasks import (
    # Payment processing tasks
    process_payment_webhook_task,
    reconcile_pending_payments_task,
    sync_payment_status_task,
)
from src.workers.settings import (
    WorkerSettings as BaseWorkerSettings,
)
from src.workers.settings import (
    get_redis_settings,
    shutdown,
    startup,
)
from src.workers.tasks import (
    check_delivery_status_task,
    # Metrics tasks
    collect_metrics_task,
    process_bulk_notification_task,
    # Data export tasks
    process_data_export_task,
    # File tasks
    process_file_upload_task,
    recalculate_usage_task,
    # Email tasks
    send_email_task,
    send_invitation_email_task,
    # Notification tasks
    send_notification_task,
    send_otp_email_task,
    send_password_reset_email_task,
    # Cron scheduler tasks
    system_cron_scheduler_task,
)
from src.workers.two_factor_tasks import (
    # Two-Factor Authentication tasks
    notify_2fa_mandatory_change,
)


# Create instrumented cron task wrappers once, so the same wrapper is used
# in both the functions list (for ARQ task lookup) and the cron_jobs list
# (for scheduled execution). ARQ cron() calls the function directly and does
# NOT look it up from the functions list, so both must reference the same wrapper.
_collect_metrics = instrument_cron_task(collect_metrics_task)
_system_cron_scheduler = instrument_cron_task(system_cron_scheduler_task)
_reconcile_pending_payments = instrument_cron_task(reconcile_pending_payments_task)


class WorkerSettings(BaseWorkerSettings):
    """
    ARQ worker configuration with task functions and cron jobs.
    ARQ CLI looks for this class to configure the worker.

    IMPORTANT: arq's `get_kwargs` reads `settings_cls.__dict__`, so inherited
    attributes are silently dropped and arq's defaults apply instead. Every
    setting must be re-declared here, sourced from `BaseWorkerSettings` so the
    two cannot drift.
    """

    # Explicitly set Redis settings (inheritance doesn't work reliably for ARQ class attributes)
    redis_settings = get_redis_settings()

    # Use app-specific queue name to prevent job stealing by other ARQ workers
    # sharing the same Redis instance
    queue_name = ARQ_QUEUE_NAME

    # Explicitly set lifecycle hooks (inheritance doesn't work reliably for ARQ)
    on_startup = startup
    on_shutdown = shutdown

    # Worker tuning - re-declared so arq actually applies them.
    max_jobs = BaseWorkerSettings.max_jobs
    job_timeout = BaseWorkerSettings.job_timeout
    keep_result = BaseWorkerSettings.keep_result
    max_tries = BaseWorkerSettings.max_tries
    poll_delay = BaseWorkerSettings.poll_delay
    queue_read_limit = BaseWorkerSettings.queue_read_limit
    health_check_interval = BaseWorkerSettings.health_check_interval

    # Register task functions with metrics instrumentation
    functions = [
        # Email tasks
        instrument_task(send_email_task),
        instrument_task(send_invitation_email_task),
        instrument_task(send_otp_email_task),
        instrument_task(send_password_reset_email_task),
        # Metrics tasks (cron)
        _collect_metrics,
        # Notification tasks
        instrument_task(send_notification_task),
        instrument_task(process_bulk_notification_task),
        instrument_task(check_delivery_status_task),
        # File tasks
        instrument_task(process_file_upload_task),
        instrument_task(recalculate_usage_task),
        # Data export tasks
        instrument_task(process_data_export_task),
        # Two-Factor Authentication tasks
        instrument_task(notify_2fa_mandatory_change),
        # Payment tasks
        instrument_task(process_payment_webhook_task),
        instrument_task(sync_payment_status_task),
        _reconcile_pending_payments,
        # Cron scheduler tasks
        _system_cron_scheduler,
    ]

    # Cron jobs (scheduled tasks)
    # Note: Most cleanup jobs have been migrated to CronSchedulerService
    # and are managed via the admin UI. Only high-frequency jobs that
    # require sub-minute granularity remain as hardcoded ARQ crons.
    cron_jobs = [
        # Collect metrics every 15 seconds (too frequent for minute-based scheduler)
        cron(_collect_metrics, second={0, 15, 30, 45}),
        # Check for due cron jobs every minute (the scheduler itself)
        cron(_system_cron_scheduler, minute=None),
        # Reconcile pending payments every 15 minutes (catch missed webhooks)
        cron(_reconcile_pending_payments, minute={0, 15, 30, 45}),
    ]
