"""
ARQ background tasks for async job execution.
All tasks use async/await and get database session from ctx.
"""

from datetime import datetime, timedelta, timezone
import io
from typing import Any, Optional

from arq import Retry
from prometheus_client import Gauge
import psutil
from sqlalchemy import select

from src.core.config import settings
from src.logger.logger import Logger as logger
from src.logger.logger import print_exception_with_trace
from src.middleware.metrics import INSTANCE_ID


# ==================== System Metrics Gauges ====================
# Note: Metric names prefixed with "arq_" to avoid collision with
# Prometheus built-in ProcessCollector metrics (process_*)

PROCESS_CPU_PERCENT = Gauge(
    "arq_process_cpu_percent",
    "Process CPU usage percentage",
    ["instance_id"],
)

PROCESS_MEMORY_BYTES = Gauge(
    "arq_process_memory_bytes",
    "Process memory usage in bytes (RSS)",
    ["instance_id"],
)

PROCESS_MEMORY_PERCENT = Gauge(
    "arq_process_memory_percent",
    "Process memory usage percentage",
    ["instance_id"],
)

PROCESS_OPEN_FDS = Gauge(
    "arq_process_open_fds",
    "Number of open file descriptors",
    ["instance_id"],
)

PROCESS_THREADS = Gauge(
    "arq_process_threads",
    "Number of threads",
    ["instance_id"],
)

SYSTEM_CPU_PERCENT = Gauge(
    "system_cpu_percent",
    "System-wide CPU usage percentage",
    ["instance_id"],
)

SYSTEM_MEMORY_PERCENT = Gauge(
    "system_memory_percent",
    "System-wide memory usage percentage",
    ["instance_id"],
)


# ==================== Email Tasks ====================


async def send_email_task(
    ctx,
    to: str,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
    organization_id: Optional[str] = None,
):
    """
    Send an email asynchronously.

    Uses the organization's configured email provider (SMTP or SendGrid)
    when organization_id is provided, otherwise falls back to global SMTP.

    Args:
        ctx: ARQ context with session_factory
        to: Recipient email address
        subject: Email subject
        body: Plain text body
        html_body: Optional HTML body
        organization_id: Optional organization ID for provider resolution

    Returns:
        dict: Status information

    Raises:
        Retry: On failure, will retry with exponential backoff
    """
    try:
        from src.services.email import email_service

        if organization_id:
            from src.crud.organization_email_settings import (
                get_effective_email_config,
            )

            session_factory = ctx.get("session_factory")
            if not session_factory:
                raise RuntimeError("Database session factory not available")

            async with session_factory() as session:
                config = await get_effective_email_config(session, organization_id)

            success = await email_service.send_with_config(
                to=to,
                subject=subject,
                body=body,
                html_body=html_body,
                config=config,
            )
        else:
            success = await email_service.send_email(
                to=to, subject=subject, body=body, html_body=html_body
            )

        if success:
            logger.info(f"Email sent successfully to {to}")
            return {"status": "sent", "to": to}
        else:
            logger.warning(f"Failed to send email to {to}, will retry")
            raise Retry(defer=30)

    except Retry:
        raise
    except Exception as exc:
        print_exception_with_trace(exc, f"Error sending email to {to}")
        logger.error(f"Error sending email to {to}: {exc}")
        raise Retry(defer=60)


async def send_invitation_email_task(
    ctx,
    to: str,
    organization_name: str,
    registration_url: str,
    invited_by_name: str,
    expires_days: int = 7,
    organization_id: Optional[str] = None,
):
    """
    Send a user invitation email.

    Args:
        ctx: ARQ context
        to: Recipient email address
        organization_name: Name of the inviting organization
        registration_url: URL with the invite token pre-filled
        invited_by_name: Name of the admin who sent the invite
        expires_days: Number of days until the invitation expires
        organization_id: Optional organization ID for provider resolution

    Returns:
        dict: Status information

    Raises:
        Retry: On failure, will retry
    """
    try:
        from src.services.email_templates import build_invitation_email

        subject = f"You've been invited to join {organization_name}"
        html_body = build_invitation_email(
            organization_name=organization_name,
            registration_url=registration_url,
            invited_by_name=invited_by_name,
            expires_days=expires_days,
        )
        plain_body = (
            f"Hello,\n\n"
            f"{invited_by_name} has invited you to join {organization_name}.\n\n"
            f"Accept your invitation here:\n{registration_url}\n\n"
            f"This invitation expires in {expires_days} days.\n\n"
            f"Best regards,\nThe {organization_name} Team"
        )

        return await send_email_task(
            ctx,
            to=to,
            subject=subject,
            body=plain_body,
            html_body=html_body,
            organization_id=organization_id,
        )

    except Retry:
        raise
    except Exception as exc:
        print_exception_with_trace(exc, f"Error sending invitation email to {to}")
        logger.error(f"Error sending invitation email to {to}: {exc}")
        raise Retry(defer=60)


async def send_otp_email_task(
    ctx,
    to: str,
    otp_code: str,
    expires_minutes: int = 15,
    organization_id: Optional[str] = None,
):
    """
    Send OTP verification email.

    Args:
        ctx: ARQ context
        to: Recipient email address
        otp_code: The OTP code to send
        expires_minutes: How long the OTP is valid for
        organization_id: Optional organization ID for provider resolution

    Returns:
        dict: Status information

    Raises:
        Retry: On failure, will retry
    """
    subject = "Email Verification Code"
    body = f"""
Hello,

Your email verification code is: {otp_code[:3]}-{otp_code[3:]}

This code will expire in {expires_minutes} minutes.

If you did not request this verification, please ignore this email.

Thank you,
{settings.TEAM_NAME}
    """.strip()

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .code {{ font-size: 32px; font-weight: bold; color: #007bff; text-align: center; padding: 20px; background: #f8f9fa; border-radius: 8px; margin: 20px 0; }}
        .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <h2>Email Verification</h2>
        <p>Hello,</p>
        <p>Your email verification code is:</p>
        <div class="code">{otp_code[:3]}-{otp_code[3:]}</div>
        <p>This code will expire in {expires_minutes} minutes.</p>
        <p>If you did not request this verification, please ignore this email.</p>
        <div class="footer">
            <p>Thank you,<br>{settings.TEAM_NAME}</p>
        </div>
    </div>
</body>
</html>
    """.strip()

    return await send_email_task(
        ctx, to, subject, body, html_body, organization_id=organization_id
    )


async def send_password_reset_email_task(
    ctx,
    to: str,
    reset_token: str,
    reset_url: str,
    organization_id: Optional[str] = None,
):
    """
    Send password reset email.

    Args:
        ctx: ARQ context
        to: Recipient email address
        reset_token: Password reset token
        reset_url: Full URL for password reset page
        organization_id: Optional organization ID for provider resolution

    Returns:
        dict: Status information

    Raises:
        Retry: On failure, will retry
    """
    subject = "Password Reset Request"
    body = f"""
Hello,

You have requested to reset your password.

Click the following link to reset your password:
{reset_url}

This link will expire in 1 hour.

If you did not request a password reset, please ignore this email.

Thank you,
{settings.TEAM_NAME}
    """.strip()

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .button {{ display: inline-block; padding: 12px 24px; background-color: #007bff; color: white; text-decoration: none; border-radius: 4px; margin: 20px 0; }}
        .button:hover {{ background-color: #0056b3; }}
        .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
        .warning {{ margin-top: 20px; padding: 10px; background: #fff3cd; border-radius: 4px; font-size: 13px; }}
    </style>
</head>
<body>
    <div class="container">
        <h2>Password Reset Request</h2>
        <p>Hello,</p>
        <p>You have requested to reset your password. Click the button below to set a new password:</p>
        <p><a href="{reset_url}" class="button">Reset Password</a></p>
        <p>Or copy and paste this link into your browser:</p>
        <p style="word-break: break-all; color: #666;">{reset_url}</p>
        <p>This link will expire in 1 hour.</p>
        <div class="warning">
            If you did not request a password reset, please ignore this email. Your password will remain unchanged.
        </div>
        <div class="footer">
            <p>Thank you,<br>{settings.TEAM_NAME}</p>
        </div>
    </div>
</body>
</html>
    """.strip()

    return await send_email_task(
        ctx, to, subject, body, html_body, organization_id=organization_id
    )


# ==================== Metrics Collection Tasks ====================


async def collect_metrics_task(ctx):
    """
    Cron task: Collect system metrics every 15 seconds.
    Updates Prometheus gauges with CPU, memory, and other system stats.

    Args:
        ctx: ARQ context

    Returns:
        dict: Collected metrics summary
    """
    try:
        # Get current process
        process = psutil.Process()

        # Process metrics
        PROCESS_CPU_PERCENT.labels(instance_id=INSTANCE_ID).set(
            process.cpu_percent(interval=None)
        )

        memory_info = process.memory_info()
        PROCESS_MEMORY_BYTES.labels(instance_id=INSTANCE_ID).set(memory_info.rss)
        PROCESS_MEMORY_PERCENT.labels(instance_id=INSTANCE_ID).set(
            process.memory_percent()
        )

        # File descriptors (Unix only)
        try:
            PROCESS_OPEN_FDS.labels(instance_id=INSTANCE_ID).set(process.num_fds())
        except AttributeError:
            pass  # Not available on Windows

        PROCESS_THREADS.labels(instance_id=INSTANCE_ID).set(process.num_threads())

        # System-wide metrics
        SYSTEM_CPU_PERCENT.labels(instance_id=INSTANCE_ID).set(
            psutil.cpu_percent(interval=None)
        )
        SYSTEM_MEMORY_PERCENT.labels(instance_id=INSTANCE_ID).set(
            psutil.virtual_memory().percent
        )

        # Update user activity metrics
        try:
            from src.services.user_activity import user_activity_service

            await user_activity_service.update_metrics()
        except Exception as e:
            logger.warning(f"Failed to update user activity metrics: {e}")

        return {
            "status": "collected",
            "process_memory_mb": memory_info.rss / (1024 * 1024),
            "process_cpu": process.cpu_percent(interval=None),
        }

    except Exception as exc:
        logger.error(f"Failed to collect metrics: {exc}")
        return {"status": "error", "error": str(exc)}


# ==================== Notification Tasks ====================


# Keys under Notification.extra_data that carry the deferred *delivery payload*
# rather than metadata. A notification created directly (rather than through
# crud.notification.create_notification) stashes the full rendered body here so
# this worker can read it back and send it - see
# src/workers/two_factor_tasks.py. That means the payload cannot be redacted on
# the way in without breaking delivery, yet extra_data is handed back verbatim
# by GET /notifications to any holder of `notifications:read`. Clearing the
# keys once the message is delivered keeps the window to the queue latency
# instead of forever.
_DEFERRED_PAYLOAD_KEYS = ("body", "html_body")


def _clear_deferred_payload(notification: Any) -> None:
    """
    Drop the deferred send payload from a notification's extra_data.

    Called only after a successful send: a failed send is retried and the retry
    needs the payload. Reassigns the column rather than mutating in place, as
    SQLAlchemy does not track in-place mutation of a plain JSON dict.
    """
    extra_data = notification.extra_data
    if not extra_data or not any(key in extra_data for key in _DEFERRED_PAYLOAD_KEYS):
        return

    notification.extra_data = {
        key: value
        for key, value in extra_data.items()
        if key not in _DEFERRED_PAYLOAD_KEYS
    }


async def send_notification_task(ctx, notification_id: str) -> dict:
    """
    Send a single notification via the appropriate provider.

    Args:
        ctx: ARQ context with session_factory
        notification_id: UUID of the notification record to send

    Returns:
        dict: Status information with provider response

    Raises:
        Retry: On temporary failure, will retry with exponential backoff
    """
    session_factory = ctx.get("session_factory")
    if not session_factory:
        logger.error("No session_factory in context")
        raise RuntimeError("Database session factory not available")

    async with session_factory() as session:
        try:
            # Import here to avoid circular dependencies
            from uuid import UUID

            from src.models.notification import Notification
            from src.services.notifications.dispatcher import notification_dispatcher

            # Load the notification record
            result = await session.execute(
                select(Notification).where(
                    Notification.id == UUID(notification_id),
                    Notification.deleted_time.is_(None),
                )
            )
            notification = result.scalar_one_or_none()

            if not notification:
                logger.warning(f"Notification {notification_id} not found")
                return {"status": "not_found", "notification_id": notification_id}

            if notification.status not in ("pending", "queued"):
                logger.info(
                    f"Notification {notification_id} already processed: {notification.status}"
                )
                return {
                    "status": "already_processed",
                    "current_status": notification.status,
                }

            # Update status to processing
            notification.status = "queued"
            await session.commit()

            # Extract content from extra_data if stored there (e.g. 2FA
            # notifications, which are created directly rather than through
            # crud.notification.create_notification and stash the full rendered
            # body under extra_data["body"] for this worker to read back).
            #
            # These keys are a DELIVERY PAYLOAD, not metadata: they cannot be
            # redacted on the way in without sending "[redacted]" to the user.
            # But Notification.extra_data is returned verbatim by
            # GET /notifications to any holder of `notifications:read`, so the
            # payload is cleared below once it has been delivered - see
            # _DEFERRED_PAYLOAD_KEYS.
            content = notification.body_preview or ""
            html_content = None
            if notification.extra_data:
                content = notification.extra_data.get("body", content)
                html_content = notification.extra_data.get("html_body")

            # Resolve the org-specific provider and send directly.
            # We bypass send_notification() here because this notification
            # record already exists — we just need to deliver it without
            # re-running preference checks or creating a duplicate record.
            org_id = (
                str(notification.organization_id)
                if notification.organization_id
                else None
            )

            if notification.channel == "email" and org_id:
                provider = await notification_dispatcher.get_email_provider(
                    session, org_id
                )
            else:
                await notification_dispatcher._ensure_initialized()
                provider = notification_dispatcher._providers.get(notification.channel)

            if not provider:
                raise RuntimeError(f"No provider for channel: {notification.channel}")

            send_result = await provider.send(
                recipient=notification.recipient,
                message=content,
                subject=notification.subject,
                html_message=html_content,
            )

            # Update notification with result
            if send_result.success:
                notification.status = "sent"
                notification.provider_message_id = send_result.provider_message_id
                # The deferred payload has now been delivered, so drop it from
                # the API-exposed extra_data column. It is only kept on the
                # failure branch below, where a retry still needs it.
                _clear_deferred_payload(notification)
                logger.info(f"Notification {notification_id} sent successfully")
            else:
                notification.status = "failed"
                notification.error_message = send_result.error_message
                notification.retry_count += 1
                notification.last_retry_time = datetime.now(timezone.utc)
                logger.warning(
                    f"Notification {notification_id} failed: "
                    f"{send_result.error_message}"
                )

            await session.commit()

            return {
                "status": notification.status,
                "notification_id": notification_id,
                "provider_message_id": notification.provider_message_id,
                "error_message": notification.error_message,
            }

        except Exception as exc:
            await session.rollback()
            print_exception_with_trace(
                exc, f"Error sending notification {notification_id}"
            )
            logger.error(f"Error sending notification {notification_id}: {exc}")

            # Update notification with error
            try:
                notification.status = "failed"
                notification.error_message = str(exc)
                notification.retry_count += 1
                notification.last_retry_time = datetime.now(timezone.utc)
                await session.commit()
            except Exception as e:
                logger.warning(
                    f"Failed to update notification status during error handling: {e}"
                )

            raise Retry(defer=60)  # Retry in 60 seconds


async def process_bulk_notification_task(
    ctx, bulk_id: str, batch_offset: int = 0
) -> dict:
    """
    Process a batch of bulk notifications.
    Processes BATCH_SIZE notifications at a time and enqueues next batch if needed.

    Args:
        ctx: ARQ context with session_factory
        bulk_id: UUID of the bulk notification record
        batch_offset: Starting offset for this batch

    Returns:
        dict: Progress information

    Raises:
        Retry: On temporary failure
    """
    BATCH_SIZE = 100  # Process 100 notifications per batch

    session_factory = ctx.get("session_factory")
    if not session_factory:
        logger.error("No session_factory in context")
        raise RuntimeError("Database session factory not available")

    async with session_factory() as session:
        try:
            from uuid import UUID

            from src.models.bulk_notification import BulkNotification
            from src.services.notifications.bulk_processor import bulk_processor

            # Load the bulk notification record
            result = await session.execute(
                select(BulkNotification).where(
                    BulkNotification.id == UUID(bulk_id),
                    BulkNotification.deleted_time.is_(None),
                )
            )
            bulk_notification = result.scalar_one_or_none()

            if not bulk_notification:
                logger.warning(f"Bulk notification {bulk_id} not found")
                return {"status": "not_found", "bulk_id": bulk_id}

            if bulk_notification.status == "cancelled":
                logger.info(f"Bulk notification {bulk_id} was cancelled")
                return {"status": "cancelled", "bulk_id": bulk_id}

            # Update status to processing on first batch
            if batch_offset == 0:
                bulk_notification.status = "processing"
                bulk_notification.started_time = datetime.now(timezone.utc)
                await session.commit()

            # Process the batch
            batch_result = await bulk_processor.process_batch(  # type: ignore[attr-defined]
                session=session,
                bulk_notification=bulk_notification,
                offset=batch_offset,
                limit=BATCH_SIZE,
            )

            # Update progress
            bulk_notification.sent_count += batch_result.sent_count
            bulk_notification.failed_count += batch_result.failed_count
            await session.commit()

            # Check if there are more batches to process
            processed_total = batch_offset + batch_result.processed_count
            if processed_total < bulk_notification.total_recipients:
                # Enqueue next batch
                from src.services.tasks import task_queue

                await task_queue.enqueue_job(
                    "process_bulk_notification_task",
                    bulk_id=bulk_id,
                    batch_offset=processed_total,
                )
                logger.info(
                    f"Bulk notification {bulk_id}: processed {processed_total}/"
                    f"{bulk_notification.total_recipients}, enqueueing next batch"
                )
            else:
                # All batches complete
                bulk_notification.status = "completed"
                bulk_notification.completed_time = datetime.now(timezone.utc)
                await session.commit()
                logger.info(
                    f"Bulk notification {bulk_id} completed: "
                    f"sent={bulk_notification.sent_count}, failed={bulk_notification.failed_count}"
                )

            return {
                "status": (
                    "processing"
                    if processed_total < bulk_notification.total_recipients
                    else "completed"
                ),
                "bulk_id": bulk_id,
                "batch_offset": batch_offset,
                "batch_size": batch_result.processed_count,
                "sent_count": bulk_notification.sent_count,
                "failed_count": bulk_notification.failed_count,
                "total_recipients": bulk_notification.total_recipients,
            }

        except Exception as exc:
            await session.rollback()
            print_exception_with_trace(
                exc,
                f"Error processing bulk notification {bulk_id} at offset {batch_offset}",
            )
            logger.error(
                f"Error processing bulk notification {bulk_id} at offset {batch_offset}: {exc}"
            )

            # Mark bulk notification as failed
            try:
                bulk_notification.status = "failed"
                await session.commit()
            except Exception as e:
                logger.warning(
                    f"Failed to update bulk notification status during error handling: {e}"
                )

            raise Retry(defer=60)


async def check_delivery_status_task(ctx, notification_id: str) -> dict:
    """
    Check and update delivery status of a sent notification from the provider.

    Args:
        ctx: ARQ context with session_factory
        notification_id: UUID of the notification to check

    Returns:
        dict: Updated status information
    """
    session_factory = ctx.get("session_factory")
    if not session_factory:
        logger.error("No session_factory in context")
        raise RuntimeError("Database session factory not available")

    async with session_factory() as session:
        try:
            from uuid import UUID

            from src.models.notification import Notification
            from src.services.notifications.dispatcher import notification_dispatcher

            # Load the notification record
            result = await session.execute(
                select(Notification).where(
                    Notification.id == UUID(notification_id),
                    Notification.deleted_time.is_(None),
                )
            )
            notification = result.scalar_one_or_none()

            if not notification:
                logger.warning(f"Notification {notification_id} not found")
                return {"status": "not_found", "notification_id": notification_id}

            if not notification.provider_message_id:
                logger.info(
                    f"Notification {notification_id} has no provider message ID"
                )
                return {
                    "status": "no_provider_id",
                    "notification_id": notification_id,
                    "current_status": notification.status,
                }

            # Query provider for status
            new_status = await notification_dispatcher.check_delivery_status(  # type: ignore[attr-defined]
                session=session, notification=notification
            )

            if new_status and new_status != notification.status:
                old_status = notification.status
                notification.status = new_status
                notification.updated_time = datetime.now(timezone.utc)
                await session.commit()
                logger.info(
                    f"Notification {notification_id} status updated: "
                    f"{old_status} -> {new_status}"
                )

            return {
                "status": "checked",
                "notification_id": notification_id,
                "current_status": notification.status,
                "provider_message_id": notification.provider_message_id,
            }

        except Exception as exc:
            await session.rollback()
            logger.error(f"Error checking delivery status for {notification_id}: {exc}")
            return {"status": "error", "error": str(exc)}


# ==================== File Tasks ====================


async def process_file_upload_task(ctx, file_id: str) -> dict:
    """
    Process a newly uploaded file: extract metadata and update status.
    For images: extract dimensions
    For videos: extract duration and dimensions
    For other files: just update status

    Args:
        ctx: ARQ context with session_factory
        file_id: UUID of the file record to process

    Returns:
        dict: Processing result with extracted metadata
    """
    session_factory = ctx.get("session_factory")
    if not session_factory:
        logger.error("No session_factory in context")
        raise RuntimeError("Database session factory not available")

    async with session_factory() as session:
        try:
            from uuid import UUID

            from src.models.file import File

            # Load the file record
            result = await session.execute(
                select(File).where(
                    File.id == UUID(file_id), File.deleted_time.is_(None)
                )
            )
            file_record = result.scalar_one_or_none()

            if not file_record:
                logger.warning(f"File {file_id} not found")
                return {"status": "not_found", "file_id": file_id}

            if file_record.status not in ("pending", "uploaded", "processing"):
                logger.info(f"File {file_id} already processed: {file_record.status}")
                return {
                    "status": "already_processed",
                    "current_status": file_record.status,
                }

            # Update status to processing
            file_record.status = "processing"
            await session.commit()

            file_extra_data = file_record.extra_data or {}

            # Extract metadata based on file type
            content_type = file_record.content_type or ""

            if content_type.startswith("image/"):
                # Extract image dimensions
                try:
                    from src.services.files.file_manager import file_manager

                    dimensions = await file_manager.extract_image_metadata(file_record)  # type: ignore[union-attr]
                    if dimensions:
                        file_extra_data.update(dimensions)
                except Exception as e:
                    logger.warning(
                        f"Failed to extract image metadata for {file_id}: {e}"
                    )

            elif content_type.startswith("video/"):
                # Extract video metadata (duration, dimensions)
                try:
                    from src.services.files.file_manager import file_manager

                    video_meta = await file_manager.extract_video_metadata(file_record)  # type: ignore[union-attr]
                    if video_meta:
                        file_extra_data.update(video_meta)
                except Exception as e:
                    logger.warning(
                        f"Failed to extract video metadata for {file_id}: {e}"
                    )

            # Update file record
            file_record.extra_data = file_extra_data
            file_record.status = "ready"
            file_record.updated_time = datetime.now(timezone.utc)
            await session.commit()

            logger.info(f"File {file_id} processed successfully")
            return {
                "status": "ready",
                "file_id": file_id,
                "extra_data": file_extra_data,
            }

        except Exception as exc:
            await session.rollback()
            logger.error(f"Error processing file {file_id}: {exc}")

            # Mark file as failed
            try:
                file_record.status = "failed"
                await session.commit()
            except Exception as e:
                logger.warning(
                    f"Failed to update file status during error handling: {e}"
                )

            raise Retry(defer=60)


async def recalculate_usage_task(ctx, organization_id: str) -> dict:
    """
    Recalculate file usage statistics for all users in an organization.
    Updates FileUsage records with current totals.

    Args:
        ctx: ARQ context with session_factory
        organization_id: UUID of the organization

    Returns:
        dict: Summary of recalculated usage
    """
    session_factory = ctx.get("session_factory")
    if not session_factory:
        logger.error("No session_factory in context")
        raise RuntimeError("Database session factory not available")

    async with session_factory() as session:
        try:
            from uuid import UUID

            from sqlalchemy import func

            from src.models.file import File
            from src.models.file_usage import FileUsage

            org_uuid = UUID(organization_id)

            # Get all unique uploaders in this organization
            uploader_result = await session.execute(
                select(File.uploaded_by_user_id)
                .where(
                    File.organization_id == org_uuid,
                    File.deleted_time.is_(None),
                    File.status == "ready",
                )
                .distinct()
            )
            user_ids = [row[0] for row in uploader_result.fetchall()]

            users_updated = 0
            total_files = 0
            total_size = 0

            for user_id in user_ids:
                # Calculate totals for this user
                stats_result = await session.execute(
                    select(
                        func.count(File.id).label("total_files"),
                        func.coalesce(func.sum(File.size_bytes), 0).label("total_size"),
                        func.count(File.id)
                        .filter(File.category == "image")
                        .label("image_count"),
                        func.coalesce(
                            func.sum(File.size_bytes).filter(File.category == "image"),
                            0,
                        ).label("image_size"),
                        func.count(File.id)
                        .filter(File.category == "video")
                        .label("video_count"),
                        func.coalesce(
                            func.sum(File.size_bytes).filter(File.category == "video"),
                            0,
                        ).label("video_size"),
                        func.count(File.id)
                        .filter(File.category == "document")
                        .label("document_count"),
                        func.coalesce(
                            func.sum(File.size_bytes).filter(
                                File.category == "document"
                            ),
                            0,
                        ).label("document_size"),
                        func.count(File.id)
                        .filter(File.category == "other")
                        .label("other_count"),
                        func.coalesce(
                            func.sum(File.size_bytes).filter(File.category == "other"),
                            0,
                        ).label("other_size"),
                    ).where(
                        File.organization_id == org_uuid,
                        File.uploaded_by_user_id == user_id,
                        File.deleted_time.is_(None),
                        File.status == "ready",
                    )
                )
                stats = stats_result.fetchone()

                # Get or create FileUsage record
                usage_result = await session.execute(
                    select(FileUsage).where(
                        FileUsage.organization_id == org_uuid,
                        FileUsage.user_id == user_id,
                    )
                )
                usage = usage_result.scalar_one_or_none()

                if not usage:
                    usage = FileUsage(organization_id=org_uuid, user_id=user_id)
                    session.add(usage)

                # Update usage stats
                usage.total_files = stats.total_files
                usage.total_size_bytes = stats.total_size
                usage.image_count = stats.image_count
                usage.image_size_bytes = stats.image_size
                usage.video_count = stats.video_count
                usage.video_size_bytes = stats.video_size
                usage.document_count = stats.document_count
                usage.document_size_bytes = stats.document_size
                usage.other_count = stats.other_count
                usage.other_size_bytes = stats.other_size
                usage.updated_time = datetime.now(timezone.utc)

                users_updated += 1
                total_files += stats.total_files
                total_size += stats.total_size

            await session.commit()

            logger.info(
                f"Recalculated usage for org {organization_id}: "
                f"{users_updated} users, {total_files} files, {total_size} bytes"
            )

            return {
                "status": "completed",
                "organization_id": organization_id,
                "users_updated": users_updated,
                "total_files": total_files,
                "total_size_bytes": total_size,
            }

        except Exception as exc:
            await session.rollback()
            logger.error(
                f"Failed to recalculate usage for org {organization_id}: {exc}"
            )
            raise


# ==================== Data Export Tasks ====================


async def process_data_export_task(ctx, export_request_id: str) -> dict:
    """
    Process a user data export request.
    Collects user data, generates ZIP file, uploads to S3, and updates request status.

    Args:
        ctx: ARQ context with session_factory
        export_request_id: UUID of the export request to process

    Returns:
        dict: Processing result with status and file info
    """
    session_factory = ctx.get("session_factory")
    if not session_factory:
        logger.error("No session_factory in context")
        raise RuntimeError("Database session factory not available")

    async with session_factory() as session:
        export_request = None  # Initialize for exception handler
        try:
            from uuid import UUID

            from src.crud.data_export_request import update_export_request_status
            from src.models.data_export_request import DataExportRequest, ExportStatus
            from src.services.files.s3_storage import s3_storage
            from src.services.user_data_export import user_data_export_service

            # Load the export request
            result = await session.execute(
                select(DataExportRequest).where(
                    DataExportRequest.id == UUID(export_request_id),
                    DataExportRequest.deleted_time.is_(None),
                )
            )
            export_request = result.scalar_one_or_none()

            if not export_request:
                logger.warning(f"Export request {export_request_id} not found")
                return {"status": "not_found", "export_request_id": export_request_id}

            if export_request.status != ExportStatus.PENDING:
                logger.info(
                    f"Export request {export_request_id} already processed: {export_request.status}"
                )
                return {
                    "status": "already_processed",
                    "current_status": export_request.status.value,
                }

            # Update status to processing
            export_request.status = ExportStatus.PROCESSING
            await session.commit()

            # Generate export ZIP
            logger.info(f"Generating export for user {export_request.user_id}")
            zip_bytes = await user_data_export_service.generate_export_zip(
                session=session,
                user_id=str(export_request.user_id),
                organization_id=str(export_request.organization_id),
            )

            # Storage key format: exports/{org_id}/{user_id}/{request_id}.zip
            storage_key = (
                f"exports/{export_request.organization_id}/"
                f"{export_request.user_id}/{export_request_id}.zip"
            )

            # Try S3 first, fall back to local storage
            if s3_storage and s3_storage.is_available():
                # Upload to S3
                zip_file = io.BytesIO(zip_bytes)
                upload_result = await s3_storage.upload(
                    file_data=zip_file,
                    storage_key=storage_key,
                    content_type="application/zip",
                    metadata={
                        "export_request_id": export_request_id,
                        "user_id": str(export_request.user_id),
                        "organization_id": str(export_request.organization_id),
                    },
                )

                if not upload_result.success:
                    logger.error(
                        f"Failed to upload export to S3: {upload_result.error_message}"
                    )
                    await update_export_request_status(
                        session=session,
                        export_request_id=export_request_id,
                        status=ExportStatus.FAILED,
                    )
                    return {
                        "status": "failed",
                        "error": upload_result.error_message,
                    }
                logger.info(f"Export uploaded to S3: {storage_key}")
            else:
                # Fall back to local filesystem storage (for dev environments)
                import os

                local_exports_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    "exports",
                )
                local_path = os.path.join(local_exports_dir, storage_key)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)

                with open(local_path, "wb") as f:
                    f.write(zip_bytes)

                # Prefix with "local:" to indicate local storage
                storage_key = f"local:{local_path}"
                logger.info(f"Export saved to local storage: {local_path}")

            # Update export request with file details
            file_size = len(zip_bytes)
            expires_at = datetime.now(timezone.utc) + timedelta(days=30)

            await update_export_request_status(
                session=session,
                export_request_id=export_request_id,
                status=ExportStatus.COMPLETED,
                file_path=storage_key,
                file_size_bytes=file_size,
                expires_at=expires_at,
            )

            # Send WebSocket notification to user
            try:
                from src.services.websocket.broadcaster import message_broadcaster

                await message_broadcaster.send_to_user(
                    user_id=export_request.user_id,
                    message_type="data_export_status",
                    payload={
                        "export_id": str(export_request_id),
                        "status": "completed",
                        "file_size_bytes": file_size,
                        "expires_at": expires_at.isoformat(),
                    },
                )
            except Exception as ws_exc:
                logger.warning(f"Failed to send WebSocket notification: {ws_exc}")

            logger.info(
                f"Export request {export_request_id} completed successfully: "
                f"{file_size} bytes, expires at {expires_at}"
            )

            return {
                "status": "completed",
                "export_request_id": export_request_id,
                "file_path": storage_key,
                "file_size_bytes": file_size,
                "expires_at": expires_at.isoformat(),
            }

        except Exception as exc:
            await session.rollback()
            print_exception_with_trace(
                exc, f"Error processing export request {export_request_id}"
            )
            logger.error(f"Error processing export request {export_request_id}: {exc}")

            # Mark export as failed
            try:
                from src.crud.data_export_request import update_export_request_status
                from src.models.data_export_request import ExportStatus

                await update_export_request_status(
                    session=session,
                    export_request_id=export_request_id,
                    status=ExportStatus.FAILED,
                )

                # Send WebSocket notification to user about failure
                if export_request is not None:
                    try:
                        from src.services.websocket.broadcaster import (
                            message_broadcaster,
                        )

                        await message_broadcaster.send_to_user(
                            user_id=export_request.user_id,
                            message_type="data_export_status",
                            payload={
                                "export_id": str(export_request_id),
                                "status": "failed",
                            },
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to send WebSocket notification during error handling: {e}"
                        )
            except Exception as e:
                logger.warning(
                    f"Failed to update export request status during error handling: {e}"
                )

            return {
                "status": "failed",
                "export_request_id": export_request_id,
                "error": str(exc),
            }


# ==================== Cron Job Scheduler Tasks ====================


async def system_cron_scheduler_task(ctx) -> dict:
    """
    Cron task: Check for due cron jobs and execute them.
    Runs every minute to check for jobs that need to be executed.

    Args:
        ctx: ARQ context with session_factory

    Returns:
        dict: Summary of jobs checked and executed
    """
    session_factory = ctx.get("session_factory")
    if not session_factory:
        logger.error("No session_factory in context")
        raise RuntimeError("Database session factory not available")

    async with session_factory() as session:
        try:
            from src.services.cron_scheduler import cron_scheduler_service

            result = await cron_scheduler_service.check_and_execute_due_jobs(session)

            if result.get("jobs_executed", 0) > 0 or result.get("jobs_failed", 0) > 0:
                logger.info(
                    f"Cron scheduler: executed={result.get('jobs_executed', 0)}, "
                    f"failed={result.get('jobs_failed', 0)}"
                )

            return result

        except Exception as exc:
            await session.rollback()
            logger.error(f"Failed to run cron scheduler task: {exc}")
            print_exception_with_trace(exc, "Cron scheduler task failed")
            return {"status": "error", "error": str(exc)}
