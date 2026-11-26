"""
ARQ background tasks for payment processing.

These tasks handle:
- Webhook event processing (async for fast webhook response)
- Payment status synchronization (for missed webhooks)
- Payment reconciliation (cron job)
"""

from typing import TYPE_CHECKING, Optional

from arq import Retry

from src.logger.logger import Logger as logger
from src.logger.logger import print_exception_with_trace


if TYPE_CHECKING:
    from src.services.payments.base import WebhookEvent


# ==================== Webhook Processing Tasks ====================


async def process_payment_webhook_task(
    ctx,
    provider: str,
    event_id: str,
    event_type: str,
    normalized_type: str,
    payment_reference: Optional[str],
    customer_reference: Optional[str],
    event_data: dict,
    created_at: str,
):
    """
    Process a payment provider webhook event asynchronously.

    This task is queued immediately when a webhook is received,
    allowing the webhook endpoint to respond quickly to the provider.

    Args:
        ctx: ARQ context with session_factory
        provider: Payment provider name (stripe, payfast, paypal)
        event_id: Provider's event ID
        event_type: Provider's native event type
        normalized_type: Our normalized event type
        payment_reference: Provider's payment/intent ID
        customer_reference: Provider's customer ID
        event_data: Full event payload
        created_at: Event creation timestamp

    Returns:
        dict: Processing result

    Raises:
        Retry: On transient failures, will retry with backoff
    """
    from src.services.payments import PaymentService
    from src.services.payments.base import NormalizedEventType, WebhookEvent

    try:
        session_factory = ctx["session_factory"]

        # Reconstruct the WebhookEvent
        try:
            normalized = NormalizedEventType(normalized_type)
        except ValueError:
            normalized = NormalizedEventType.UNKNOWN

        event = WebhookEvent(
            event_id=event_id,
            event_type=event_type,
            normalized_type=normalized,
            payment_reference=payment_reference,
            customer_reference=customer_reference,
            data=event_data,
            created_at=created_at,
        )

        async with session_factory() as session:
            success = await PaymentService.process_webhook_event(
                session=session,
                provider=provider,
                event=event,
            )

            if success:
                logger.info(
                    f"Payment webhook processed successfully: {provider}:{event_id}"
                )
                return {
                    "status": "processed",
                    "provider": provider,
                    "event_id": event_id,
                    "event_type": event_type,
                }
            else:
                logger.warning(
                    f"Payment webhook processing returned false: {provider}:{event_id}"
                )
                return {
                    "status": "skipped",
                    "provider": provider,
                    "event_id": event_id,
                    "reason": "Event not applicable or payment not found",
                }

    except Exception as exc:
        print_exception_with_trace(
            exc, f"Error processing payment webhook {provider}:{event_id}"
        )
        logger.error(f"Payment webhook processing failed: {provider}:{event_id}: {exc}")
        # Retry with exponential backoff for transient failures
        raise Retry(defer=60)  # Retry in 60 seconds


async def sync_payment_status_task(
    ctx,
    payment_id: str,
):
    """
    Synchronize payment status with the provider.

    Use this to recover from missed webhooks or verify payment state.

    Args:
        ctx: ARQ context with session_factory
        payment_id: Internal payment UUID

    Returns:
        dict: Sync result with current status

    Raises:
        Retry: On transient failures
    """
    from src.services.payments import PaymentService

    try:
        session_factory = ctx["session_factory"]

        async with session_factory() as session:
            result = await PaymentService.sync_payment_status(
                session=session,
                payment_id=payment_id,
            )

            logger.info(f"Payment status synced: {payment_id} -> {result['status']}")
            return result

    except ValueError as e:
        # Payment not found - don't retry
        logger.warning(f"Payment sync failed - not found: {payment_id}: {e}")
        return {"status": "error", "payment_id": payment_id, "error": str(e)}

    except Exception as exc:
        print_exception_with_trace(exc, f"Error syncing payment status: {payment_id}")
        logger.error(f"Payment status sync failed: {payment_id}: {exc}")
        raise Retry(defer=120)  # Retry in 2 minutes


# ==================== Scheduled/Cron Tasks ====================


async def reconcile_pending_payments_task(ctx):
    """
    Cron task to reconcile pending payments that may have missed webhooks.

    Finds payments that have been in 'pending' or 'processing' status
    for too long and syncs their status with the provider.

    This runs periodically (e.g., every 15 minutes) to catch any
    payments where webhooks may have been missed or delayed.

    Args:
        ctx: ARQ context with session_factory

    Returns:
        dict: Reconciliation summary
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import and_, select

    from src.models.payment import Payment
    from src.services.payments import PaymentService

    try:
        session_factory = ctx["session_factory"]

        async with session_factory() as session:
            # Find payments stuck in transient states for more than 30 minutes
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=30)

            result = await session.execute(
                select(Payment)
                .where(
                    and_(
                        Payment.status.in_(
                            ["pending", "processing", "requires_action"]
                        ),
                        Payment.created_time < cutoff_time,
                        Payment.deleted_time.is_(None),
                    )
                )
                .limit(50)  # Process in batches
            )
            stale_payments = result.scalars().all()

            synced_count = 0
            error_count = 0

            for payment in stale_payments:
                try:
                    await PaymentService.sync_payment_status(
                        session=session,
                        payment_id=str(payment.id),
                    )
                    synced_count += 1
                except Exception as e:
                    logger.warning(
                        f"Failed to sync payment {payment.id} during reconciliation: {e}"
                    )
                    error_count += 1

            logger.info(
                f"Payment reconciliation complete: "
                f"checked={len(stale_payments)}, synced={synced_count}, errors={error_count}"
            )

            return {
                "status": "completed",
                "checked": len(stale_payments),
                "synced": synced_count,
                "errors": error_count,
            }

    except Exception as exc:
        print_exception_with_trace(exc, "Error during payment reconciliation")
        logger.error(f"Payment reconciliation failed: {exc}")
        return {"status": "error", "error": str(exc)}


# ==================== Helper Functions ====================


async def enqueue_webhook_processing(
    redis_pool,
    provider: str,
    event: "WebhookEvent",
) -> str:
    """
    Helper to enqueue a webhook event for background processing.

    Call this from the webhook endpoint after signature verification.

    Args:
        redis_pool: ARQ Redis connection pool (unused, kept for API compat)
        provider: Payment provider name
        event: Parsed WebhookEvent

    Returns:
        Job ID for tracking
    """
    from src.services.tasks import task_queue

    job_id = await task_queue.enqueue_job(
        "process_payment_webhook_task",
        provider,
        event.event_id,
        event.event_type,
        event.normalized_type.value,
        event.payment_reference,
        event.customer_reference,
        event.data,
        event.created_at,
    )

    return job_id or ""


async def enqueue_payment_sync(
    redis_pool,
    payment_id: str,
) -> str:
    """
    Helper to enqueue a payment status sync.

    Args:
        redis_pool: ARQ Redis connection pool (unused, kept for API compat)
        payment_id: Internal payment UUID

    Returns:
        Job ID for tracking
    """
    from src.services.tasks import task_queue

    job_id = await task_queue.enqueue_job(
        "sync_payment_status_task",
        payment_id,
    )

    return job_id or ""
