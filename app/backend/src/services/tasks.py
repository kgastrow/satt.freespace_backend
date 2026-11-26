"""
Task queue service for enqueueing background jobs.
Provides a simple interface for FastAPI to dispatch async tasks to ARQ workers.
"""

from typing import Optional

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from src.constants.queues import ARQ_QUEUE_NAME
from src.core.config import settings
from src.logger.logger import Logger as logger


class TaskQueue:
    """
    ARQ task queue client for enqueueing background jobs.
    Manages connection pool to Redis and provides methods to enqueue tasks.
    """

    _pool: Optional[ArqRedis] = None

    @classmethod
    async def connect(cls):
        """
        Initialize ARQ Redis connection pool.
        Should be called during application startup.
        """
        if cls._pool is not None:
            logger.warning("TaskQueue already connected")
            return

        try:
            # Parse Redis URL for ARQ
            from urllib.parse import urlparse

            # Use dedicated ARQ Redis URL if available
            redis_url = (
                settings.ARQ_REDIS_URL
                if hasattr(settings, "ARQ_REDIS_URL") and settings.ARQ_REDIS_URL
                else settings.REDIS_URL
            )
            parsed = urlparse(redis_url)

            redis_settings = RedisSettings(
                host=parsed.hostname or "localhost",
                port=parsed.port or 6379,
                database=int(parsed.path.lstrip("/")) if parsed.path else 0,
                password=parsed.password,
                conn_timeout=5,
                conn_retries=3,
                conn_retry_delay=1,
            )

            cls._pool = await create_pool(
                redis_settings, default_queue_name=ARQ_QUEUE_NAME
            )
            logger.info(
                f"TaskQueue connected to Redis at {parsed.hostname}:{parsed.port}/{parsed.path.lstrip('/')}"
            )

        except Exception as exc:
            logger.error(f"Failed to connect TaskQueue to Redis: {exc}")
            raise

    @classmethod
    async def disconnect(cls):
        """
        Close ARQ Redis connection pool.
        Should be called during application shutdown.
        """
        if cls._pool is not None:
            await cls._pool.close()
            cls._pool = None
            logger.info("TaskQueue disconnected from Redis")

    @classmethod
    async def _ensure_connected(cls):
        """Ensure connection pool is initialized."""
        if cls._pool is None:
            await cls.connect()

    @classmethod
    async def enqueue_email(
        cls,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Enqueue a generic email sending task.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            organization_id: Optional organization ID for provider resolution

        Returns:
            str: Job ID if enqueued successfully, None on failure
        """
        await cls._ensure_connected()
        assert cls._pool is not None

        try:
            job = await cls._pool.enqueue_job(
                "send_email_task",
                to,
                subject,
                body,
                html_body,
                organization_id,
            )
            if job is None:
                logger.error("Failed to enqueue email task: job is None")
                return None
            logger.info(f"Enqueued email task to {to}, job_id={job.job_id}")
            return job.job_id

        except Exception as exc:
            logger.error(f"Failed to enqueue email task: {exc}")
            return None

    @classmethod
    async def enqueue_otp_email(
        cls,
        to: str,
        otp_code: str,
        expires_minutes: int = 15,
        organization_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Enqueue an OTP verification email.

        Args:
            to: Recipient email address
            otp_code: The OTP code to send
            expires_minutes: How long the OTP is valid for (default: 15 minutes)
            organization_id: Optional organization ID for provider resolution

        Returns:
            str: Job ID if enqueued successfully, None on failure
        """
        await cls._ensure_connected()
        assert cls._pool is not None

        try:
            job = await cls._pool.enqueue_job(
                "send_otp_email_task",
                to,
                otp_code,
                expires_minutes,
                organization_id,
            )
            if job is None:
                logger.error("Failed to enqueue OTP email task: job is None")
                return None
            logger.info(f"Enqueued OTP email task to {to}, job_id={job.job_id}")
            return job.job_id

        except Exception as exc:
            logger.error(f"Failed to enqueue OTP email task: {exc}")
            return None

    @classmethod
    async def enqueue_password_reset_email(
        cls,
        to: str,
        reset_token: str,
        reset_url: str,
        organization_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Enqueue a password reset email.

        Args:
            to: Recipient email address
            reset_token: The password reset token
            reset_url: Full URL for password reset page
            organization_id: Optional organization ID for provider resolution

        Returns:
            str: Job ID if enqueued successfully, None on failure
        """
        await cls._ensure_connected()
        assert cls._pool is not None

        try:
            job = await cls._pool.enqueue_job(
                "send_password_reset_email_task",
                to,
                reset_token,
                reset_url,
                organization_id,
            )
            if job is None:
                logger.error("Failed to enqueue password reset email task: job is None")
                return None
            logger.info(
                f"Enqueued password reset email task to {to}, job_id={job.job_id}"
            )
            return job.job_id

        except Exception as exc:
            logger.error(f"Failed to enqueue password reset email task: {exc}")
            return None

    @classmethod
    async def enqueue_invitation_email(
        cls,
        to: str,
        organization_name: str,
        registration_url: str,
        invited_by_name: str,
        expires_days: int = 7,
        organization_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Enqueue an invitation email.

        Args:
            to: Recipient email address
            organization_name: Name of the inviting organization
            registration_url: URL with invite token pre-filled
            invited_by_name: Name of the admin who sent the invite
            expires_days: Days until expiry
            organization_id: Optional organization ID for provider resolution

        Returns:
            str: Job ID if enqueued successfully, None on failure
        """
        await cls._ensure_connected()
        assert cls._pool is not None

        try:
            job = await cls._pool.enqueue_job(
                "send_invitation_email_task",
                to,
                organization_name,
                registration_url,
                invited_by_name,
                expires_days,
                organization_id,
            )
            if job is None:
                logger.error("Failed to enqueue invitation email task: job is None")
                return None
            logger.info(f"Enqueued invitation email task to {to}, job_id={job.job_id}")
            return job.job_id

        except Exception as exc:
            logger.error(f"Failed to enqueue invitation email task: {exc}")
            return None

    @classmethod
    async def enqueue_job(cls, task_name: str, *args, **kwargs) -> Optional[str]:
        """
        Enqueue a generic background job.

        Args:
            task_name: Name of the task function to execute
            *args: Positional arguments to pass to the task
            **kwargs: Keyword arguments to pass to the task

        Returns:
            str: Job ID if enqueued successfully, None on failure
        """
        await cls._ensure_connected()
        assert cls._pool is not None

        try:
            job = await cls._pool.enqueue_job(
                task_name,
                *args,
                **kwargs,
            )
            if job is None:
                logger.error(f"Failed to enqueue job {task_name}: job is None")
                return None
            logger.info(f"Enqueued job {task_name}, job_id={job.job_id}")
            return job.job_id

        except Exception as exc:
            logger.error(f"Failed to enqueue job {task_name}: {exc}")
            return None

    @classmethod
    async def get_job_status(cls, job_id: str) -> Optional[dict]:
        """
        Get the status of a queued job.

        Args:
            job_id: The job ID returned from enqueue methods

        Returns:
            dict: Job status information with keys:
                - job_id: str
                - status: str (queued, in_progress, complete, not_found)
                - result: any (if complete)
                - error: str (if failed)
            None if job not found or error
        """
        await cls._ensure_connected()
        assert cls._pool is not None

        try:
            job_info = await cls._pool.job(job_id)  # type: ignore[attr-defined]

            if job_info is None:
                return {
                    "job_id": job_id,
                    "status": "not_found",
                }

            # Get job result if complete
            result = None
            error = None

            if job_info.status == "complete":
                try:
                    result = await job_info.result()
                except Exception as e:
                    error = str(e)

            return {
                "job_id": job_id,
                "status": job_info.status,
                "result": result,
                "error": error,
            }

        except Exception as exc:
            logger.error(f"Failed to get job status for {job_id}: {exc}")
            return None


# Singleton instance
task_queue = TaskQueue()
