"""
Payment service for coordinating payment operations.

This service sits between the API layer and payment providers,
handling business logic, validation, and event recording.
"""

from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.crud import payment as payment_crud
from src.crud.organization_payment_settings import get_payment_settings
from src.logger.logger import Logger
from src.services.payments.base import (
    CheckoutSession,
    NormalizedEventType,
    PaymentStatus,
    RefundResult,
    WebhookEvent,
)
from src.services.payments.factory import PaymentProviderFactory


class PaymentService:
    """
    Service for handling payment operations.

    Coordinates between:
    - API endpoints (receives requests)
    - Payment providers (processes payments)
    - Database (records transactions)
    - Event log (audit trail)
    """

    @staticmethod
    async def create_checkout(
        session: AsyncSession,
        organization_id: str,
        user_id: Optional[str],
        amount_cents: int,
        currency: str,
        description: str,
        success_url: str,
        cancel_url: str,
        metadata: Optional[dict] = None,
        provider_name: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        Create a checkout session for hosted payment.

        Args:
            session: Database session
            organization_id: Organization UUID string
            user_id: Optional user UUID string
            amount_cents: Amount in cents
            currency: ISO 4217 currency code
            description: Payment description
            success_url: Redirect URL after success
            cancel_url: Redirect URL after cancel
            metadata: Optional metadata
            provider_name: Optional specific provider
            idempotency_key: Optional idempotency key

        Returns:
            Dictionary with payment_id and checkout_url

        Raises:
            ValueError: If payments not enabled or validation fails
        """
        # Generate idempotency key if not provided
        if not idempotency_key:
            idempotency_key = str(uuid4())

        # Check for existing payment with this idempotency key
        existing = await payment_crud.get_payment_by_idempotency_key(
            session, organization_id, idempotency_key
        )
        if existing:
            # Return existing checkout info
            return {
                "payment_id": str(existing.id),
                "checkout_url": (
                    existing.provider_data.get("checkout_url")
                    if existing.provider_data
                    else None
                ),
                "existing": True,
            }

        # Get provider
        provider = await PaymentProviderFactory.get_provider_for_org(
            session, UUID(organization_id), provider_name
        )

        # Get customer email from user if available
        customer_email = ""
        if user_id:
            from src.crud.user import get_user_by_id

            user = await get_user_by_id(session, user_id, organization_id)
            if user:
                customer_email = user.email

        # Prepare metadata with internal references
        full_metadata = metadata or {}
        full_metadata["organization_id"] = organization_id
        if user_id:
            full_metadata["user_id"] = user_id

        # Create checkout session with provider
        checkout_result: CheckoutSession = await provider.create_checkout_session(
            amount_cents=amount_cents,
            currency=currency.upper(),
            customer_email=customer_email,
            description=description,
            metadata=full_metadata,
            success_url=success_url,
            cancel_url=cancel_url,
            idempotency_key=idempotency_key,
        )

        # Create local payment record
        payment = await payment_crud.create_payment(
            session,
            organization_id,
            {
                "user_id": user_id,
                "provider": provider.provider_name,
                "provider_reference": checkout_result.session_id,
                "idempotency_key": idempotency_key,
                "amount_cents": amount_cents,
                "currency": currency.upper(),
                "status": PaymentStatus.PENDING.value,
                "description": description,
                "metadata": metadata,
                "provider_data": {
                    "checkout_url": checkout_result.checkout_url,
                    "expires_at": checkout_result.expires_at,
                },
            },
        )

        # Record creation event
        await payment_crud.create_payment_event(
            session,
            str(payment.id),
            {
                "event_type": "checkout.created",
                "event_source": "api",
                "new_status": PaymentStatus.PENDING.value,
                "payload": {
                    "amount_cents": amount_cents,
                    "currency": currency,
                    "provider": provider.provider_name,
                },
                "actor_id": user_id,
                "actor_type": "user" if user_id else "system",
            },
        )

        return {
            "payment_id": str(payment.id),
            "checkout_url": checkout_result.checkout_url,
            "expires_at": checkout_result.expires_at,
        }

    @staticmethod
    async def get_payment(
        session: AsyncSession,
        organization_id: str,
        payment_id: str,
    ) -> Optional[dict]:
        """
        Get payment details.

        Args:
            session: Database session
            organization_id: Organization UUID string
            payment_id: Payment UUID string

        Returns:
            Payment details dictionary or None
        """
        payment = await payment_crud.get_payment(session, organization_id, payment_id)
        if not payment:
            return None

        return {
            "id": str(payment.id),
            "provider": payment.provider,
            "provider_reference": payment.provider_reference,
            "amount_cents": payment.amount_cents,
            "currency": payment.currency,
            "status": payment.status,
            "payment_method": payment.payment_method,
            "description": payment.description,
            "refunded_amount_cents": payment.refunded_amount_cents,
            "metadata": payment.extra_data,
            "created_time": (
                payment.created_time.isoformat() if payment.created_time else None
            ),
            "captured_time": (
                payment.captured_time.isoformat() if payment.captured_time else None
            ),
        }

    @staticmethod
    async def list_payments(
        session: AsyncSession,
        organization_id: str,
        status: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """
        List payments for an organization.

        Args:
            session: Database session
            organization_id: Organization UUID string
            status: Optional status filter
            user_id: Optional user filter
            limit: Maximum results
            offset: Results to skip

        Returns:
            Dictionary with items, total, limit, offset
        """
        payments, total = await payment_crud.list_payments(
            session, organization_id, status, user_id, limit, offset
        )

        items = [
            {
                "id": str(p.id),
                "provider": p.provider,
                "amount_cents": p.amount_cents,
                "currency": p.currency,
                "status": p.status,
                "payment_method": p.payment_method,
                "description": p.description,
                "created_time": p.created_time.isoformat() if p.created_time else None,
            }
            for p in payments
        ]

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    async def refund_payment(
        session: AsyncSession,
        organization_id: str,
        payment_id: str,
        amount_cents: Optional[int] = None,
        reason: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> dict:
        """
        Refund a payment (full or partial).

        Args:
            session: Database session
            organization_id: Organization UUID string
            payment_id: Payment UUID string
            amount_cents: Amount to refund (None = full refund)
            reason: Refund reason
            actor_id: User initiating refund

        Returns:
            Refund result dictionary

        Raises:
            ValueError: If payment not found or refund fails
        """
        # Get payment
        payment = await payment_crud.get_payment(session, organization_id, payment_id)
        if not payment:
            raise ValueError(f"Payment not found: {payment_id}")

        # Validate refund
        if payment.status not in [
            PaymentStatus.SUCCEEDED.value,
            PaymentStatus.PARTIALLY_REFUNDED.value,
        ]:
            raise ValueError(f"Cannot refund payment with status: {payment.status}")

        # Calculate refund amount
        refund_amount = amount_cents or (
            payment.amount_cents - payment.refunded_amount_cents
        )
        available_for_refund = payment.amount_cents - payment.refunded_amount_cents

        if refund_amount > available_for_refund:
            raise ValueError(
                f"Refund amount ({refund_amount}) exceeds available ({available_for_refund})"
            )

        # Get provider and check capabilities
        org_settings = await get_payment_settings(session, organization_id)
        provider = PaymentProviderFactory.get_provider(payment.provider, org_settings)

        if amount_cents and not provider.capabilities.supports_partial_refund:
            raise ValueError(
                f"Provider {payment.provider} does not support partial refunds"
            )

        # Process refund with provider
        previous_status = payment.status
        result: RefundResult = await provider.refund_payment(
            payment.provider_reference, amount_cents, reason
        )

        if not result.success:
            raise ValueError(f"Refund failed: {result.failure_reason}")

        # Update payment
        new_refunded_total = payment.refunded_amount_cents + result.amount_cents
        new_status = (
            PaymentStatus.REFUNDED.value
            if new_refunded_total >= payment.amount_cents
            else PaymentStatus.PARTIALLY_REFUNDED.value
        )

        await payment_crud.update_payment(
            session,
            organization_id,
            payment_id,
            {
                "status": new_status,
                "refunded_amount_cents": new_refunded_total,
            },
        )

        # Record event
        await payment_crud.create_payment_event(
            session,
            payment_id,
            {
                "event_type": "refund.created",
                "event_source": "api",
                "previous_status": previous_status,
                "new_status": new_status,
                "payload": {
                    "refund_reference": result.refund_reference,
                    "amount_cents": result.amount_cents,
                    "reason": reason,
                },
                "actor_id": actor_id,
                "actor_type": "user" if actor_id else "system",
            },
        )

        return {
            "success": True,
            "refund_reference": result.refund_reference,
            "amount_cents": result.amount_cents,
            "payment_id": payment_id,
            "new_status": new_status,
        }

    @staticmethod
    async def sync_payment_status(
        session: AsyncSession,
        payment_id: str,
    ) -> dict:
        """
        Sync payment status with provider (for missed webhooks).

        Args:
            session: Database session
            payment_id: Payment UUID string

        Returns:
            Updated payment status
        """
        # Note: This method doesn't filter by org_id because it's used
        # for internal sync operations. The payment_id already provides
        # the necessary context.
        from sqlalchemy import select

        from src.models.payment import Payment

        result = await session.execute(
            select(Payment).where(
                Payment.id == UUID(payment_id),
                Payment.deleted_time.is_(None),
            )
        )
        payment = result.scalars().first()

        if not payment:
            raise ValueError(f"Payment not found: {payment_id}")

        # Get provider
        org_settings = await get_payment_settings(session, str(payment.organization_id))
        provider = PaymentProviderFactory.get_provider(payment.provider, org_settings)

        # Get current status from provider
        provider_payment = await provider.get_payment(payment.provider_reference)

        if provider_payment.status.value != payment.status:
            previous_status = payment.status
            await payment_crud.update_payment_status(
                session,
                payment,
                provider_payment.status.value,
                provider_payment.failure_code,
                provider_payment.failure_reason,
            )

            # Record sync event
            await payment_crud.create_payment_event(
                session,
                payment_id,
                {
                    "event_type": "status.synced",
                    "event_source": "system",
                    "previous_status": previous_status,
                    "new_status": provider_payment.status.value,
                    "payload": {"sync_source": "manual"},
                },
            )

        return {
            "payment_id": payment_id,
            "status": provider_payment.status.value,
            "synced": True,
        }

    @staticmethod
    async def process_webhook_event(
        session: AsyncSession,
        provider: str,
        event: WebhookEvent,
    ) -> bool:
        """
        Process a webhook event from a payment provider.

        Args:
            session: Database session
            provider: Provider name
            event: Parsed webhook event

        Returns:
            True if processed successfully
        """
        Logger.info(
            f"Processing webhook event: {event.event_type} -> {event.normalized_type}"
        )

        # Find payment by provider reference
        if not event.payment_reference:
            Logger.warning(f"Webhook event has no payment reference: {event.event_id}")
            return False

        payment = await payment_crud.get_payment_by_provider_reference(
            session, provider, event.payment_reference
        )

        if not payment:
            Logger.warning(
                f"Payment not found for webhook: {provider}:{event.payment_reference}"
            )
            return False

        # Check for duplicate event processing
        if await payment_crud.event_already_processed(
            session, str(payment.id), event.event_id
        ):
            Logger.info(f"Event already processed: {event.event_id}")
            return True

        # Map normalized event to status update
        previous_status = payment.status
        new_status = PaymentService._map_event_to_status(event.normalized_type)

        if new_status and new_status != previous_status:
            # Extract failure info if present
            failure_code = event.data.get("failure_code") or event.data.get(
                "last_payment_error", {}
            ).get("code")
            failure_reason = event.data.get("failure_message") or event.data.get(
                "last_payment_error", {}
            ).get("message")

            await payment_crud.update_payment_status(
                session, payment, new_status, failure_code, failure_reason
            )

        # Record event
        await payment_crud.create_payment_event(
            session,
            str(payment.id),
            {
                "event_type": event.event_type,
                "event_source": "webhook",
                "provider_event_id": event.event_id,
                "previous_status": previous_status,
                "new_status": new_status or previous_status,
                "payload": event.data,
                "actor_type": "webhook",
            },
        )

        Logger.info(
            f"Webhook processed: {event.event_id} - {previous_status} -> {new_status}"
        )
        return True

    @staticmethod
    def _map_event_to_status(
        normalized_type: NormalizedEventType,
    ) -> Optional[str]:
        """Map normalized event type to payment status."""
        mapping = {
            NormalizedEventType.PAYMENT_CREATED: PaymentStatus.PENDING.value,
            NormalizedEventType.PAYMENT_PROCESSING: PaymentStatus.PROCESSING.value,
            NormalizedEventType.PAYMENT_REQUIRES_ACTION: PaymentStatus.REQUIRES_ACTION.value,
            NormalizedEventType.PAYMENT_SUCCEEDED: PaymentStatus.SUCCEEDED.value,
            NormalizedEventType.PAYMENT_CAPTURED: PaymentStatus.SUCCEEDED.value,
            NormalizedEventType.PAYMENT_FAILED: PaymentStatus.FAILED.value,
            NormalizedEventType.PAYMENT_CANCELLED: PaymentStatus.CANCELLED.value,
            NormalizedEventType.CHECKOUT_COMPLETED: PaymentStatus.SUCCEEDED.value,
            NormalizedEventType.REFUND_SUCCEEDED: PaymentStatus.REFUNDED.value,
            NormalizedEventType.DISPUTE_CREATED: PaymentStatus.DISPUTED.value,
        }
        return mapping.get(normalized_type)

    @staticmethod
    async def get_user_payment_methods(
        session: AsyncSession,
        organization_id: str,
        user_id: str,
    ) -> list[dict]:
        """
        Get saved payment methods for a user.

        Args:
            session: Database session
            organization_id: Organization UUID string
            user_id: User UUID string

        Returns:
            List of payment method details
        """
        methods = await payment_crud.get_user_payment_methods(
            session, organization_id, user_id
        )

        return [
            {
                "id": str(m.id),
                "type": m.type,
                "provider": m.provider,
                "last_four": m.last_four,
                "brand": m.brand,
                "exp_month": m.exp_month,
                "exp_year": m.exp_year,
                "bank_name": m.bank_name,
                "account_last_four": m.account_last_four,
                "display_name": m.display_name,
                "is_default": m.is_default,
                "is_expired": m.is_expired,
            }
            for m in methods
        ]

    @staticmethod
    async def delete_payment_method(
        session: AsyncSession,
        organization_id: str,
        user_id: str,
        payment_method_id: str,
    ) -> bool:
        """
        Delete a saved payment method.

        Args:
            session: Database session
            organization_id: Organization UUID string
            user_id: User UUID string
            payment_method_id: Payment method UUID string

        Returns:
            True if deleted, False if not found
        """
        # Verify the payment method belongs to a customer of this user
        methods = await payment_crud.get_user_payment_methods(
            session, organization_id, user_id
        )
        method_ids = [str(m.id) for m in methods]

        if payment_method_id not in method_ids:
            return False

        # Get the method to call provider
        method = await payment_crud.get_saved_payment_method(
            session, organization_id, payment_method_id
        )
        if not method:
            return False

        # Try to detach from provider (optional - some providers don't support)
        try:
            org_settings = await get_payment_settings(session, organization_id)
            provider = PaymentProviderFactory.get_provider(
                method.provider, org_settings
            )
            await provider.detach_payment_method(method.provider_payment_method_id)
        except NotImplementedError:
            pass  # Provider doesn't support detaching

        # Soft delete locally
        return await payment_crud.delete_saved_payment_method(
            session, organization_id, payment_method_id
        )

    @staticmethod
    async def set_default_payment_method(
        session: AsyncSession,
        organization_id: str,
        user_id: str,
        payment_method_id: str,
    ) -> bool:
        """
        Set a payment method as the default for the user.

        Args:
            session: Database session
            organization_id: Organization UUID string
            user_id: User UUID string
            payment_method_id: Payment method UUID string

        Returns:
            True if successful, False if not found
        """
        # Verify the payment method belongs to a customer of this user
        methods = await payment_crud.get_user_payment_methods(
            session, organization_id, user_id
        )
        target_method = None
        for m in methods:
            if str(m.id) == payment_method_id:
                target_method = m
                break

        if not target_method:
            return False

        return await payment_crud.set_default_payment_method(
            session, organization_id, str(target_method.customer_id), payment_method_id
        )
