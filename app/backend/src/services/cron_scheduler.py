"""
Cron job scheduler service.

Responsible for:
1. Checking for due cron jobs (next_run_time <= now)
2. Executing cron jobs using a registry pattern
3. Recording execution results
4. Calculating next run times using croniter
"""

from collections.abc import Awaitable
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from croniter import croniter  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession

from src.crud.cron_job import (
    get_due_cron_jobs,
    record_execution_complete,
    record_execution_start,
    update_next_run_time,
)
from src.logger.logger import Logger as logger
from src.logger.logger import print_exception_with_trace
from src.models.cron_job import CronJobStatus


# Type alias for job handler functions
JobHandler = Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]]


def get_all_cron_handlers() -> dict[str, JobHandler]:
    """
    Get all cron job handlers in a centralized registry.

    This is the single source of truth for job code -> handler mappings.
    Used by both the ARQ worker and the API trigger endpoint.

    Returns:
        Dict mapping job codes to their handler functions
    """
    from src.services.cron_handlers import (
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
        cleanup_old_request_logs_configured_handler,
        freespace_daily_purge_handler,
        process_hard_deletions_handler,
        process_scheduled_reports_handler,
        s3_migration_handler,
        update_geoip_database_handler,
    )

    return {
        "cleanup_expired_otps": cleanup_expired_otps_handler,
        "cleanup_expired_refresh_tokens": cleanup_expired_refresh_tokens_handler,
        "cleanup_old_notifications": cleanup_old_notifications_handler,
        "cleanup_deleted_files": cleanup_deleted_files_handler,
        "check_2fa_grace_period": check_2fa_grace_period_handler,
        # Honours the request_logs.retention_days SystemConfig key.
        "cleanup_old_request_logs": cleanup_old_request_logs_configured_handler,
        "cleanup_old_bg_job_executions": cleanup_old_bg_job_executions_handler,
        "s3_storage_monitor": check_s3_storage_handler,
        "local_storage_monitor": check_local_storage_handler,
        "cleanup_expired_exports": cleanup_expired_exports_handler,
        "process_hard_deletions": process_hard_deletions_handler,
        "disk_usage_monitor": check_disk_usage_handler,
        "check_brute_force_alerts": check_brute_force_alerts_handler,
        "check_queue_health": check_queue_health_handler,
        "check_notification_health": check_notification_health_handler,
        "check_db_pool_health": check_db_pool_health_handler,
        "update_geoip_database": update_geoip_database_handler,
        "check_user_type_expiry": check_user_type_expiry_handler,
        "check_api_key_expiry": check_api_key_expiry_handler,
        "process_scheduled_reports": process_scheduled_reports_handler,
        "s3_migration": s3_migration_handler,
        "freespace_daily_purge": freespace_daily_purge_handler,
    }


class CronSchedulerService:
    """
    Cron job scheduler service that manages scheduled task execution.

    Uses a registry pattern to map job codes to handler functions.
    """

    def __init__(self):
        """Initialize the scheduler with an empty job registry."""
        self._job_registry: dict[str, JobHandler] = {}

    def register_all_handlers(self) -> None:
        """Register all cron job handlers from the central registry."""
        for code, handler in get_all_cron_handlers().items():
            if code not in self._job_registry:
                self.register_job(code, handler)
        logger.info(f"Registered {len(self._job_registry)} cron job handlers")

    def register_job(self, code: str, handler: JobHandler) -> None:
        """
        Register a job handler for a specific job code.

        Args:
            code: Job code identifier
            handler: Async function that takes (session, parameters) and returns result dict
        """
        self._job_registry[code] = handler
        logger.info(f"Registered cron job handler for code: {code}")

    async def check_and_execute_due_jobs(self, session: AsyncSession) -> dict[str, Any]:
        """
        Check for due jobs and execute them.

        This is called by the scheduled task every minute.

        Args:
            session: Database session

        Returns:
            Summary dict with jobs checked and executed counts
        """
        try:
            # Get all jobs that are due to run
            due_jobs = await get_due_cron_jobs(session)

            if not due_jobs:
                return {
                    "status": "completed",
                    "jobs_checked": 0,
                    "jobs_executed": 0,
                    "jobs_failed": 0,
                }

            logger.info(f"Found {len(due_jobs)} due cron jobs to execute")

            executed_count = 0
            failed_count = 0

            for job in due_jobs:
                # Eagerly capture attributes before any session commit
                # expires the ORM object (MissingGreenlet prevention)
                job_id = str(job.id)
                job_code = str(job.code)
                job_parameters = dict(job.parameters) if job.parameters else {}
                try:
                    await self.execute_cron_job(
                        session, job_id, job_code, job_parameters
                    )
                    executed_count += 1
                except Exception as exc:
                    failed_count += 1
                    logger.error(f"Failed to execute cron job {job_code}: {exc}")
                    print_exception_with_trace(
                        exc, f"Cron job {job_code} execution failed"
                    )

            return {
                "status": "completed",
                "jobs_checked": len(due_jobs),
                "jobs_executed": executed_count,
                "jobs_failed": failed_count,
            }

        except Exception as exc:
            logger.error(f"Error in check_and_execute_due_jobs: {exc}")
            print_exception_with_trace(exc, "Cron scheduler check failed")
            return {
                "status": "error",
                "error": str(exc),
            }

    async def execute_cron_job(
        self,
        session: AsyncSession,
        job_id: str,
        job_code: str,
        job_parameters: dict[str, Any],
    ) -> None:
        """
        Execute a single cron job.

        Args:
            session: Database session
            job_id: String UUID of the CronJobDefinition
            job_code: The job code identifier
            job_parameters: The job parameters dict

        Raises:
            Exception: On execution failure
        """
        logger.info(f"Executing cron job: {job_code} (ID: {job_id})")

        # Record execution start
        execution = await record_execution_start(session, job_id)
        execution_id = str(execution.id)

        try:
            # Get the handler for this job code
            handler = self._job_registry.get(job_code)

            if not handler:
                error_msg = f"No handler registered for job code: {job_code}"
                logger.error(error_msg)
                await record_execution_complete(
                    session,
                    execution_id,
                    CronJobStatus.ERROR,
                    error_message=error_msg,
                )
                return

            # Execute the job handler
            result = await handler(session, job_parameters)

            # Check if handler reported an error in its result
            if isinstance(result, dict) and result.get("status") == "error":
                error_reason = result.get("reason", "Handler returned error status")
                await record_execution_complete(
                    session,
                    execution_id,
                    CronJobStatus.ERROR,
                    error_message=error_reason,
                    result=result,
                )
                logger.warning(f"Cron job {job_code} returned error: {error_reason}")
            else:
                # Record successful completion
                await record_execution_complete(
                    session,
                    execution_id,
                    CronJobStatus.SUCCESS,
                    result=result,
                )
                logger.info(f"Cron job {job_code} completed successfully")

        except Exception as exc:
            error_msg = str(exc)
            logger.error(f"Cron job {job_code} failed: {error_msg}")
            print_exception_with_trace(exc, f"Cron job {job_code} execution error")

            # Rollback the session to clear any aborted transaction state
            # This is necessary because a database error in the handler
            # will abort the PostgreSQL transaction, preventing further SQL
            await session.rollback()

            # Record error
            await record_execution_complete(
                session,
                execution_id,
                CronJobStatus.ERROR,
                error_message=error_msg,
            )

            raise

        finally:
            # Update next run time
            try:
                await update_next_run_time(session, job_id)
            except Exception as exc:
                logger.error(
                    f"Failed to update next_run_time for job {job_code}: {exc}"
                )

    def calculate_next_run_from_expression(
        self,
        schedule_expression: str,
        base_time: Optional[datetime] = None,
    ) -> datetime:
        """
        Calculate the next run time from a cron expression.

        Args:
            schedule_expression: Cron expression (standard 5-field format)
            base_time: Base time to calculate from (defaults to now)

        Returns:
            Next run datetime (timezone-aware UTC)

        Raises:
            ValueError: If cron expression is invalid
        """
        if base_time is None:
            base_time = datetime.now(timezone.utc)

        try:
            # croniter expects timezone-aware datetime
            cron = croniter(schedule_expression, base_time)
            next_run = cron.get_next(datetime)

            # Ensure timezone-aware UTC
            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=timezone.utc)

            return next_run

        except Exception as exc:
            logger.error(f"Invalid cron expression '{schedule_expression}': {exc}")
            raise ValueError(f"Invalid cron expression: {schedule_expression}") from exc


# Singleton instance
cron_scheduler_service = CronSchedulerService()


# Example job handlers (these can be replaced with actual implementations)


async def example_cleanup_handler(
    session: AsyncSession,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """
    Example handler for cleanup jobs.

    Args:
        session: Database session
        parameters: Job-specific parameters from the database

    Returns:
        Result dict with execution summary
    """
    logger.info(f"Running example cleanup with parameters: {parameters}")

    # Implement actual cleanup logic here
    # For now, just return a success result

    return {
        "status": "completed",
        "items_cleaned": 0,
        "message": "Example cleanup completed",
    }


# Register example handlers
# In a real implementation, you would register actual task handlers here
# cron_scheduler_service.register_job("cleanup_expired_otps", actual_handler_function)
