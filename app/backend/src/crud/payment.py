"""
CRUD operations for Payment, PaymentEvent, PaymentCustomer, and SavedPaymentMethod models.

CRITICAL: All functions filter by organization_id to ensure tenant isolation.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.payment import Payment, PaymentEvent
from src.models.payment_customer import PaymentCustomer, SavedPaymentMethod


# ─────────────────────────────────────────────────────────────
# Payment CRUD
# ─────────────────────────────────────────────────────────────


async def get_payment(
    session: AsyncSession,
    organization_id: str,
    payment_id: str,
) -> Optional[Payment]:
    """
    Get a payment by ID.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        payment_id: Payment UUID string

    Returns:
        The Payment or None if not found
    """
    org_uuid = UUID(organization_id)
    pay_uuid = UUID(payment_id)

    result = await session.execute(
        select(Payment).where(
            Payment.id == pay_uuid,
            Payment.organization_id == org_uuid,
            Payment.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_payment_by_provider_reference(
    session: AsyncSession,
    provider: str,
    provider_reference: str,
) -> Optional[Payment]:
    """
    Get a payment by provider reference (for webhook processing).

    Note: This is used for webhook processing and does not filter by org
    since webhooks don't have org context. The payment is verified against
    the provider reference.

    Args:
        session: Database session
        provider: Provider name (e.g., 'stripe')
        provider_reference: Provider's payment ID

    Returns:
        The Payment or None if not found
    """
    result = await session.execute(
        select(Payment).where(
            Payment.provider == provider,
            Payment.provider_reference == provider_reference,
            Payment.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_payment_by_idempotency_key(
    session: AsyncSession,
    organization_id: str,
    idempotency_key: str,
) -> Optional[Payment]:
    """
    Get a payment by idempotency key.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        idempotency_key: Idempotency key

    Returns:
        The Payment or None if not found
    """
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(Payment).where(
            Payment.organization_id == org_uuid,
            Payment.idempotency_key == idempotency_key,
            Payment.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def create_payment(
    session: AsyncSession,
    organization_id: str,
    payment_data: dict[str, Any],
) -> Payment:
    """
    Create a new payment record.

    CRITICAL: Always associates with organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        payment_data: Payment data

    Returns:
        The created Payment
    """
    org_uuid = UUID(organization_id)

    payment = Payment(
        organization_id=org_uuid,
        user_id=UUID(payment_data["user_id"]) if payment_data.get("user_id") else None,
        provider=payment_data["provider"],
        provider_reference=payment_data["provider_reference"],
        customer_id=(
            UUID(payment_data["customer_id"])
            if payment_data.get("customer_id")
            else None
        ),
        provider_customer_id=payment_data.get("provider_customer_id"),
        idempotency_key=payment_data.get("idempotency_key"),
        amount_cents=payment_data["amount_cents"],
        currency=payment_data["currency"],
        status=payment_data["status"],
        payment_method=payment_data.get("payment_method"),
        description=payment_data.get("description"),
        extra_data=payment_data.get("metadata"),
        provider_data=payment_data.get("provider_data"),
    )

    session.add(payment)
    try:
        await session.commit()
        await session.refresh(payment)
    except Exception as e:
        await session.rollback()
        raise e

    return payment


async def update_payment(
    session: AsyncSession,
    organization_id: str,
    payment_id: str,
    payment_data: dict[str, Any],
) -> Payment:
    """
    Update a payment record.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        payment_id: Payment UUID string
        payment_data: Fields to update

    Returns:
        The updated Payment

    Raises:
        ValueError: If payment not found
    """
    payment = await get_payment(session, organization_id, payment_id)

    if not payment:
        raise ValueError(f"Payment not found: {payment_id}")

    updatable_fields = [
        "status",
        "payment_method",
        "failure_code",
        "failure_reason",
        "extra_data",
        "provider_data",
        "captured_time",
        "refunded_amount_cents",
    ]

    for field in updatable_fields:
        if field in payment_data:
            setattr(payment, field, payment_data[field])

    try:
        await session.commit()
        await session.refresh(payment)
    except Exception as e:
        await session.rollback()
        raise e

    return payment


async def update_payment_status(
    session: AsyncSession,
    payment: Payment,
    new_status: str,
    failure_code: Optional[str] = None,
    failure_reason: Optional[str] = None,
) -> Payment:
    """
    Update payment status (for internal use, e.g., webhook processing).

    Args:
        session: Database session
        payment: Payment object (already fetched)
        new_status: New status
        failure_code: Optional failure code
        failure_reason: Optional failure reason

    Returns:
        The updated Payment
    """
    payment.status = new_status
    if failure_code:
        payment.failure_code = failure_code
    if failure_reason:
        payment.failure_reason = failure_reason
    if new_status == "succeeded":
        payment.captured_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(payment)
    except Exception as e:
        await session.rollback()
        raise e

    return payment


async def list_payments(
    session: AsyncSession,
    organization_id: str,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Payment], int]:
    """
    List payments for an organization with optional filters.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        status: Optional status filter
        user_id: Optional user filter
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of Payments, total count)
    """
    org_uuid = UUID(organization_id)

    # Build base query
    base_conditions = [
        Payment.organization_id == org_uuid,
        Payment.deleted_time.is_(None),
    ]

    if status:
        base_conditions.append(Payment.status == status)
    if user_id:
        base_conditions.append(Payment.user_id == UUID(user_id))

    # Get total count
    count_result = await session.execute(
        select(func.count(Payment.id)).where(and_(*base_conditions))
    )
    total = count_result.scalar() or 0

    # Get paginated results
    result = await session.execute(
        select(Payment)
        .where(and_(*base_conditions))
        .order_by(Payment.created_time.desc())
        .limit(limit)
        .offset(offset)
    )

    return list(result.scalars().all()), total


# ─────────────────────────────────────────────────────────────
# Payment Event CRUD
# ─────────────────────────────────────────────────────────────


async def create_payment_event(
    session: AsyncSession,
    payment_id: str,
    event_data: dict[str, Any],
) -> PaymentEvent:
    """
    Create a payment event for audit trail.

    Args:
        session: Database session
        payment_id: Payment UUID string
        event_data: Event data

    Returns:
        The created PaymentEvent
    """
    event = PaymentEvent(
        payment_id=UUID(payment_id),
        event_type=event_data["event_type"],
        event_source=event_data["event_source"],
        provider_event_id=event_data.get("provider_event_id"),
        previous_status=event_data.get("previous_status"),
        new_status=event_data.get("new_status"),
        payload=event_data["payload"],
        actor_id=UUID(event_data["actor_id"]) if event_data.get("actor_id") else None,
        actor_type=event_data.get("actor_type"),
    )

    session.add(event)
    try:
        await session.commit()
        await session.refresh(event)
    except Exception as e:
        await session.rollback()
        raise e

    return event


async def get_payment_events(
    session: AsyncSession,
    organization_id: str,
    payment_id: str,
) -> list[PaymentEvent]:
    """
    Get all events for a payment.

    CRITICAL: Validates payment belongs to organization for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        payment_id: Payment UUID string

    Returns:
        List of PaymentEvents
    """
    # First verify payment belongs to org
    payment = await get_payment(session, organization_id, payment_id)
    if not payment:
        return []

    result = await session.execute(
        select(PaymentEvent)
        .where(PaymentEvent.payment_id == UUID(payment_id))
        .order_by(PaymentEvent.created_time.asc())
    )

    return list(result.scalars().all())


async def event_already_processed(
    session: AsyncSession,
    payment_id: str,
    provider_event_id: str,
) -> bool:
    """
    Check if a webhook event has already been processed (idempotency).

    Args:
        session: Database session
        payment_id: Payment UUID string
        provider_event_id: Provider's event ID

    Returns:
        True if event was already processed
    """
    result = await session.execute(
        select(PaymentEvent.id).where(
            PaymentEvent.payment_id == UUID(payment_id),
            PaymentEvent.provider_event_id == provider_event_id,
        )
    )
    return result.scalars().first() is not None


# ─────────────────────────────────────────────────────────────
# Payment Customer CRUD
# ─────────────────────────────────────────────────────────────


async def get_payment_customer(
    session: AsyncSession,
    organization_id: str,
    customer_id: str,
) -> Optional[PaymentCustomer]:
    """
    Get a payment customer by ID.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        customer_id: Customer UUID string

    Returns:
        The PaymentCustomer or None if not found
    """
    org_uuid = UUID(organization_id)
    cust_uuid = UUID(customer_id)

    result = await session.execute(
        select(PaymentCustomer).where(
            PaymentCustomer.id == cust_uuid,
            PaymentCustomer.organization_id == org_uuid,
            PaymentCustomer.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_payment_customer_by_user(
    session: AsyncSession,
    organization_id: str,
    user_id: str,
    provider: str,
) -> Optional[PaymentCustomer]:
    """
    Get a payment customer by user ID and provider.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        user_id: User UUID string
        provider: Provider name

    Returns:
        The PaymentCustomer or None if not found
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    result = await session.execute(
        select(PaymentCustomer).where(
            PaymentCustomer.organization_id == org_uuid,
            PaymentCustomer.user_id == user_uuid,
            PaymentCustomer.provider == provider,
            PaymentCustomer.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_payment_customer_by_provider_id(
    session: AsyncSession,
    organization_id: str,
    provider: str,
    provider_customer_id: str,
) -> Optional[PaymentCustomer]:
    """
    Get a payment customer by provider's customer ID.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        provider: Provider name
        provider_customer_id: Provider's customer ID

    Returns:
        The PaymentCustomer or None if not found
    """
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(PaymentCustomer).where(
            PaymentCustomer.organization_id == org_uuid,
            PaymentCustomer.provider == provider,
            PaymentCustomer.provider_customer_id == provider_customer_id,
            PaymentCustomer.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def create_payment_customer(
    session: AsyncSession,
    organization_id: str,
    customer_data: dict[str, Any],
) -> PaymentCustomer:
    """
    Create a payment customer record.

    CRITICAL: Always associates with organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        customer_data: Customer data

    Returns:
        The created PaymentCustomer
    """
    org_uuid = UUID(organization_id)

    customer = PaymentCustomer(
        organization_id=org_uuid,
        user_id=(
            UUID(customer_data["user_id"]) if customer_data.get("user_id") else None
        ),
        provider=customer_data["provider"],
        provider_customer_id=customer_data["provider_customer_id"],
        email=customer_data["email"],
        name=customer_data.get("name"),
        extra_data=customer_data.get("metadata"),
    )

    session.add(customer)
    try:
        await session.commit()
        await session.refresh(customer)
    except Exception as e:
        await session.rollback()
        raise e

    return customer


async def get_or_create_payment_customer(
    session: AsyncSession,
    organization_id: str,
    user_id: Optional[str],
    provider: str,
    provider_customer_id: str,
    email: str,
    name: Optional[str] = None,
) -> PaymentCustomer:
    """
    Get existing customer or create a new one.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        user_id: Optional user UUID string
        provider: Provider name
        provider_customer_id: Provider's customer ID
        email: Customer email
        name: Optional customer name

    Returns:
        The PaymentCustomer (existing or newly created)
    """
    # Try to find by provider customer ID first
    customer = await get_payment_customer_by_provider_id(
        session, organization_id, provider, provider_customer_id
    )

    if not customer:
        customer = await create_payment_customer(
            session,
            organization_id,
            {
                "user_id": user_id,
                "provider": provider,
                "provider_customer_id": provider_customer_id,
                "email": email,
                "name": name,
            },
        )

    return customer


# ─────────────────────────────────────────────────────────────
# Saved Payment Method CRUD
# ─────────────────────────────────────────────────────────────


async def get_saved_payment_method(
    session: AsyncSession,
    organization_id: str,
    payment_method_id: str,
) -> Optional[SavedPaymentMethod]:
    """
    Get a saved payment method by ID.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        payment_method_id: Payment method UUID string

    Returns:
        The SavedPaymentMethod or None if not found
    """
    org_uuid = UUID(organization_id)
    pm_uuid = UUID(payment_method_id)

    result = await session.execute(
        select(SavedPaymentMethod).where(
            SavedPaymentMethod.id == pm_uuid,
            SavedPaymentMethod.organization_id == org_uuid,
            SavedPaymentMethod.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_user_payment_methods(
    session: AsyncSession,
    organization_id: str,
    user_id: str,
) -> list[SavedPaymentMethod]:
    """
    Get all saved payment methods for a user.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        user_id: User UUID string

    Returns:
        List of SavedPaymentMethods
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    # Get all customers for this user
    customers_result = await session.execute(
        select(PaymentCustomer.id).where(
            PaymentCustomer.organization_id == org_uuid,
            PaymentCustomer.user_id == user_uuid,
            PaymentCustomer.deleted_time.is_(None),
        )
    )
    customer_ids = [row for row in customers_result.scalars().all()]

    if not customer_ids:
        return []

    # Get payment methods for all customers
    result = await session.execute(
        select(SavedPaymentMethod)
        .where(
            SavedPaymentMethod.organization_id == org_uuid,
            SavedPaymentMethod.customer_id.in_(customer_ids),
            SavedPaymentMethod.deleted_time.is_(None),
        )
        .order_by(
            SavedPaymentMethod.is_default.desc(), SavedPaymentMethod.created_time.desc()
        )
    )

    return list(result.scalars().all())


async def create_saved_payment_method(
    session: AsyncSession,
    organization_id: str,
    method_data: dict[str, Any],
) -> SavedPaymentMethod:
    """
    Create a saved payment method record.

    CRITICAL: Always associates with organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        method_data: Payment method data

    Returns:
        The created SavedPaymentMethod
    """
    org_uuid = UUID(organization_id)

    payment_method = SavedPaymentMethod(
        organization_id=org_uuid,
        customer_id=UUID(method_data["customer_id"]),
        provider=method_data["provider"],
        provider_payment_method_id=method_data["provider_payment_method_id"],
        type=method_data["type"],
        last_four=method_data.get("last_four"),
        brand=method_data.get("brand"),
        exp_month=method_data.get("exp_month"),
        exp_year=method_data.get("exp_year"),
        bank_name=method_data.get("bank_name"),
        account_last_four=method_data.get("account_last_four"),
        display_name=method_data.get("display_name"),
        is_default=method_data.get("is_default", False),
        is_expired=method_data.get("is_expired", False),
    )

    session.add(payment_method)
    try:
        await session.commit()
        await session.refresh(payment_method)
    except Exception as e:
        await session.rollback()
        raise e

    return payment_method


async def delete_saved_payment_method(
    session: AsyncSession,
    organization_id: str,
    payment_method_id: str,
) -> bool:
    """
    Soft delete a saved payment method.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        payment_method_id: Payment method UUID string

    Returns:
        True if deleted, False if not found
    """
    payment_method = await get_saved_payment_method(
        session, organization_id, payment_method_id
    )

    if not payment_method:
        return False

    payment_method.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise e

    return True


async def set_default_payment_method(
    session: AsyncSession,
    organization_id: str,
    customer_id: str,
    payment_method_id: str,
) -> bool:
    """
    Set a payment method as the default for a customer.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        customer_id: Customer UUID string
        payment_method_id: Payment method UUID string to set as default

    Returns:
        True if successful, False if payment method not found
    """
    org_uuid = UUID(organization_id)
    cust_uuid = UUID(customer_id)
    pm_uuid = UUID(payment_method_id)

    # Verify payment method exists and belongs to customer
    payment_method = await get_saved_payment_method(
        session, organization_id, payment_method_id
    )

    if not payment_method or payment_method.customer_id != cust_uuid:
        return False

    # Clear all current defaults for this customer using bulk update
    await session.execute(
        update(SavedPaymentMethod)
        .where(
            SavedPaymentMethod.organization_id == org_uuid,
            SavedPaymentMethod.customer_id == cust_uuid,
            SavedPaymentMethod.deleted_time.is_(None),
        )
        .values(is_default=False)
    )

    # Set new default
    payment_method.is_default = True

    # Also update customer's default reference
    customer = await get_payment_customer(session, organization_id, customer_id)
    if customer:
        customer.default_payment_method_id = pm_uuid

    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise e

    return True
