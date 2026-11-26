"""
CRUD tests for Payment, PaymentEvent, PaymentCustomer, and SavedPaymentMethod models.

Tests verify:
- Basic CRUD operations
- Organization-based tenant isolation
- Idempotency key handling
- Provider reference lookups
"""

from uuid import uuid4

import pytest

from src.crud.payment import (
    create_payment,
    create_payment_customer,
    create_payment_event,
    create_saved_payment_method,
    delete_saved_payment_method,
    event_already_processed,
    get_or_create_payment_customer,
    get_payment,
    get_payment_by_idempotency_key,
    get_payment_by_provider_reference,
    get_payment_customer,
    get_payment_customer_by_provider_id,
    get_payment_customer_by_user,
    get_payment_events,
    get_saved_payment_method,
    get_user_payment_methods,
    list_payments,
    set_default_payment_method,
    update_payment,
    update_payment_status,
)


# ─────────────────────────────────────────────────────────────
# Payment CRUD Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_payment(async_session, test_organization, test_user):
    """Test creating a payment record."""
    payment = await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_test_create_123",
            "amount_cents": 10000,
            "currency": "USD",
            "status": "pending",
            "payment_method": "card",
            "description": "Test payment",
        },
    )

    assert payment is not None
    assert payment.organization_id == test_organization.id
    assert payment.user_id == test_user.id
    assert payment.provider == "stripe"
    assert payment.provider_reference == "pi_test_create_123"
    assert payment.amount_cents == 10000
    assert payment.currency == "USD"
    assert payment.status == "pending"


@pytest.mark.asyncio
async def test_create_payment_with_idempotency_key(
    async_session, test_organization, test_user
):
    """Test creating a payment with idempotency key."""
    idempotency_key = f"idem_{uuid4()}"

    payment = await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_test_idem_123",
            "amount_cents": 5000,
            "currency": "USD",
            "status": "pending",
            "idempotency_key": idempotency_key,
        },
    )

    assert payment.idempotency_key == idempotency_key


@pytest.mark.asyncio
async def test_get_payment(async_session, test_organization, test_payment):
    """Test retrieving a payment by ID."""
    retrieved = await get_payment(
        async_session,
        str(test_organization.id),
        str(test_payment.id),
    )

    assert retrieved is not None
    assert retrieved.id == test_payment.id
    assert retrieved.organization_id == test_organization.id


@pytest.mark.asyncio
async def test_get_payment_wrong_organization(
    async_session, test_organization, second_organization, test_payment
):
    """Test that payment cannot be retrieved with wrong organization ID."""
    # Test payment belongs to test_organization
    retrieved = await get_payment(
        async_session,
        str(second_organization.id),  # Wrong org
        str(test_payment.id),
    )

    assert retrieved is None


@pytest.mark.asyncio
async def test_get_payment_by_provider_reference(async_session, test_payment):
    """Test retrieving a payment by provider reference."""
    retrieved = await get_payment_by_provider_reference(
        async_session,
        test_payment.provider,
        test_payment.provider_reference,
    )

    assert retrieved is not None
    assert retrieved.id == test_payment.id


@pytest.mark.asyncio
async def test_get_payment_by_idempotency_key(
    async_session, test_organization, test_user
):
    """Test retrieving a payment by idempotency key."""
    idempotency_key = f"idem_lookup_{uuid4()}"

    # Create payment with idempotency key
    payment = await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_test_idem_lookup",
            "amount_cents": 5000,
            "currency": "USD",
            "status": "pending",
            "idempotency_key": idempotency_key,
        },
    )

    retrieved = await get_payment_by_idempotency_key(
        async_session,
        str(test_organization.id),
        idempotency_key,
    )

    assert retrieved is not None
    assert retrieved.id == payment.id


@pytest.mark.asyncio
async def test_update_payment(async_session, test_organization, test_payment):
    """Test updating a payment record."""
    updated = await update_payment(
        async_session,
        str(test_organization.id),
        str(test_payment.id),
        {"status": "refunded", "refunded_amount_cents": 5000},
    )

    assert updated.status == "refunded"
    assert updated.refunded_amount_cents == 5000


@pytest.mark.asyncio
async def test_update_payment_not_found(async_session, test_organization):
    """Test updating a non-existent payment raises error."""
    fake_id = str(uuid4())

    with pytest.raises(ValueError, match="Payment not found"):
        await update_payment(
            async_session,
            str(test_organization.id),
            fake_id,
            {"status": "cancelled"},
        )


@pytest.mark.asyncio
async def test_update_payment_status(async_session, test_organization, test_user):
    """Test updating payment status directly."""
    # Create a pending payment
    payment = await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_test_status_update",
            "amount_cents": 5000,
            "currency": "USD",
            "status": "pending",
        },
    )

    # Update to succeeded
    updated = await update_payment_status(
        async_session,
        payment,
        "succeeded",
    )

    assert updated.status == "succeeded"
    assert updated.captured_time is not None


@pytest.mark.asyncio
async def test_update_payment_status_with_failure(
    async_session, test_organization, test_user
):
    """Test updating payment status with failure info."""
    payment = await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_test_fail_update",
            "amount_cents": 5000,
            "currency": "USD",
            "status": "pending",
        },
    )

    updated = await update_payment_status(
        async_session,
        payment,
        "failed",
        failure_code="card_declined",
        failure_reason="Insufficient funds",
    )

    assert updated.status == "failed"
    assert updated.failure_code == "card_declined"
    assert updated.failure_reason == "Insufficient funds"


@pytest.mark.asyncio
async def test_list_payments(async_session, test_organization, test_user):
    """Test listing payments with pagination."""
    # Create multiple payments
    for i in range(5):
        await create_payment(
            async_session,
            str(test_organization.id),
            {
                "user_id": str(test_user.id),
                "provider": "stripe",
                "provider_reference": f"pi_test_list_{i}",
                "amount_cents": 1000 * (i + 1),
                "currency": "USD",
                "status": "succeeded" if i % 2 == 0 else "pending",
            },
        )

    # List all
    payments, total = await list_payments(
        async_session,
        str(test_organization.id),
    )

    assert len(payments) == 5
    assert total == 5


@pytest.mark.asyncio
async def test_list_payments_with_status_filter(
    async_session, test_organization, test_user
):
    """Test listing payments filtered by status."""
    # Create payments with different statuses
    for i, status in enumerate(["succeeded", "pending", "succeeded", "failed"]):
        await create_payment(
            async_session,
            str(test_organization.id),
            {
                "user_id": str(test_user.id),
                "provider": "stripe",
                "provider_reference": f"pi_test_status_{i}",
                "amount_cents": 1000,
                "currency": "USD",
                "status": status,
            },
        )

    # Filter by succeeded
    payments, total = await list_payments(
        async_session,
        str(test_organization.id),
        status="succeeded",
    )

    assert len(payments) == 2
    assert total == 2
    assert all(p.status == "succeeded" for p in payments)


@pytest.mark.asyncio
async def test_list_payments_with_user_filter(
    async_session, test_organization, test_user, second_org_user
):
    """Test listing payments filtered by user."""
    # Create payment for test_user
    await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_test_user_filter_1",
            "amount_cents": 1000,
            "currency": "USD",
            "status": "succeeded",
        },
    )

    # Filter by user
    payments, total = await list_payments(
        async_session,
        str(test_organization.id),
        user_id=str(test_user.id),
    )

    assert total >= 1
    assert all(p.user_id == test_user.id for p in payments)


@pytest.mark.asyncio
async def test_list_payments_organization_isolation(
    async_session, test_organization, second_organization, test_user
):
    """Test that listing payments only returns payments from the specified org."""
    # Create payment in test_organization
    await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_org_a",
            "amount_cents": 1000,
            "currency": "USD",
            "status": "succeeded",
        },
    )

    # List from second_organization
    payments, total = await list_payments(
        async_session,
        str(second_organization.id),
    )

    assert total == 0
    assert len(payments) == 0


# ─────────────────────────────────────────────────────────────
# Payment Event CRUD Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_payment_event(async_session, test_payment, test_user):
    """Test creating a payment event."""
    event = await create_payment_event(
        async_session,
        str(test_payment.id),
        {
            "event_type": "payment.succeeded",
            "event_source": "webhook",
            "provider_event_id": "evt_test_123",
            "previous_status": "pending",
            "new_status": "succeeded",
            "payload": {"stripe_event": "charge.succeeded"},
        },
    )

    assert event is not None
    assert event.payment_id == test_payment.id
    assert event.event_type == "payment.succeeded"
    assert event.event_source == "webhook"
    assert event.provider_event_id == "evt_test_123"


@pytest.mark.asyncio
async def test_get_payment_events(
    async_session, test_organization, test_payment, test_user
):
    """Test retrieving all events for a payment."""
    # Create multiple events
    for i in range(3):
        await create_payment_event(
            async_session,
            str(test_payment.id),
            {
                "event_type": f"event_{i}",
                "event_source": "api",
                "payload": {"index": i},
            },
        )

    events = await get_payment_events(
        async_session,
        str(test_organization.id),
        str(test_payment.id),
    )

    assert len(events) == 3


@pytest.mark.asyncio
async def test_get_payment_events_org_isolation(
    async_session, test_organization, second_organization, test_payment
):
    """Test that events cannot be retrieved with wrong organization."""
    await create_payment_event(
        async_session,
        str(test_payment.id),
        {
            "event_type": "test.event",
            "event_source": "api",
            "payload": {},
        },
    )

    # Try to get events from wrong org
    events = await get_payment_events(
        async_session,
        str(second_organization.id),  # Wrong org
        str(test_payment.id),
    )

    assert len(events) == 0


@pytest.mark.asyncio
async def test_event_already_processed(async_session, test_payment):
    """Test checking if webhook event was already processed."""
    provider_event_id = "evt_duplicate_123"

    # First event
    await create_payment_event(
        async_session,
        str(test_payment.id),
        {
            "event_type": "payment.succeeded",
            "event_source": "webhook",
            "provider_event_id": provider_event_id,
            "payload": {},
        },
    )

    # Check if processed
    is_processed = await event_already_processed(
        async_session,
        str(test_payment.id),
        provider_event_id,
    )

    assert is_processed is True


@pytest.mark.asyncio
async def test_event_not_processed(async_session, test_payment):
    """Test that unprocessed events return False."""
    is_processed = await event_already_processed(
        async_session,
        str(test_payment.id),
        "evt_new_event_123",
    )

    assert is_processed is False


# ─────────────────────────────────────────────────────────────
# Payment Customer CRUD Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_payment_customer(async_session, test_organization, test_user):
    """Test creating a payment customer."""
    customer = await create_payment_customer(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_customer_id": "cus_create_test",
            "email": test_user.email,
            "name": "Test Customer",
        },
    )

    assert customer is not None
    assert customer.organization_id == test_organization.id
    assert customer.user_id == test_user.id
    assert customer.provider == "stripe"
    assert customer.provider_customer_id == "cus_create_test"


@pytest.mark.asyncio
async def test_get_payment_customer(async_session, test_organization, payment_customer):
    """Test retrieving a payment customer by ID."""
    retrieved = await get_payment_customer(
        async_session,
        str(test_organization.id),
        str(payment_customer.id),
    )

    assert retrieved is not None
    assert retrieved.id == payment_customer.id


@pytest.mark.asyncio
async def test_get_payment_customer_wrong_org(
    async_session, second_organization, payment_customer
):
    """Test that customer cannot be retrieved with wrong org."""
    retrieved = await get_payment_customer(
        async_session,
        str(second_organization.id),  # Wrong org
        str(payment_customer.id),
    )

    assert retrieved is None


@pytest.mark.asyncio
async def test_get_payment_customer_by_user(
    async_session, test_organization, test_user
):
    """Test retrieving a payment customer by user and provider."""
    # Create customer
    await create_payment_customer(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_customer_id": "cus_by_user_test",
            "email": test_user.email,
        },
    )

    retrieved = await get_payment_customer_by_user(
        async_session,
        str(test_organization.id),
        str(test_user.id),
        "stripe",
    )

    assert retrieved is not None
    assert retrieved.user_id == test_user.id
    assert retrieved.provider == "stripe"


@pytest.mark.asyncio
async def test_get_payment_customer_by_provider_id(
    async_session, test_organization, payment_customer
):
    """Test retrieving a customer by provider's customer ID."""
    retrieved = await get_payment_customer_by_provider_id(
        async_session,
        str(test_organization.id),
        payment_customer.provider,
        payment_customer.provider_customer_id,
    )

    assert retrieved is not None
    assert retrieved.id == payment_customer.id


@pytest.mark.asyncio
async def test_get_or_create_payment_customer_get(
    async_session, test_organization, test_user
):
    """Test get_or_create returns existing customer."""
    # Create customer first
    created = await create_payment_customer(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_customer_id": "cus_get_or_create",
            "email": test_user.email,
        },
    )

    # Get or create should return existing
    retrieved = await get_or_create_payment_customer(
        async_session,
        str(test_organization.id),
        str(test_user.id),
        "stripe",
        "cus_get_or_create",
        test_user.email,
    )

    assert retrieved.id == created.id


@pytest.mark.asyncio
async def test_get_or_create_payment_customer_create(
    async_session, test_organization, test_user
):
    """Test get_or_create creates new customer if not found."""
    customer = await get_or_create_payment_customer(
        async_session,
        str(test_organization.id),
        str(test_user.id),
        "stripe",
        "cus_new_create",
        test_user.email,
        "New Customer",
    )

    assert customer is not None
    assert customer.provider_customer_id == "cus_new_create"
    assert customer.name == "New Customer"


# ─────────────────────────────────────────────────────────────
# Saved Payment Method CRUD Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_saved_payment_method(
    async_session, test_organization, payment_customer
):
    """Test creating a saved payment method."""
    method = await create_saved_payment_method(
        async_session,
        str(test_organization.id),
        {
            "customer_id": str(payment_customer.id),
            "provider": "stripe",
            "provider_payment_method_id": "pm_create_test",
            "type": "card",
            "last_four": "1234",
            "brand": "mastercard",
            "exp_month": 6,
            "exp_year": 2025,
        },
    )

    assert method is not None
    assert method.customer_id == payment_customer.id
    assert method.type == "card"
    assert method.last_four == "1234"
    assert method.brand == "mastercard"


@pytest.mark.asyncio
async def test_get_saved_payment_method(
    async_session, test_organization, saved_payment_method
):
    """Test retrieving a saved payment method by ID."""
    retrieved = await get_saved_payment_method(
        async_session,
        str(test_organization.id),
        str(saved_payment_method.id),
    )

    assert retrieved is not None
    assert retrieved.id == saved_payment_method.id


@pytest.mark.asyncio
async def test_get_saved_payment_method_wrong_org(
    async_session, second_organization, saved_payment_method
):
    """Test that payment method cannot be retrieved with wrong org."""
    retrieved = await get_saved_payment_method(
        async_session,
        str(second_organization.id),  # Wrong org
        str(saved_payment_method.id),
    )

    assert retrieved is None


@pytest.mark.asyncio
async def test_get_user_payment_methods(
    async_session, test_organization, test_user, payment_customer
):
    """Test retrieving all payment methods for a user."""
    # Create multiple payment methods
    for i in range(3):
        await create_saved_payment_method(
            async_session,
            str(test_organization.id),
            {
                "customer_id": str(payment_customer.id),
                "provider": "stripe",
                "provider_payment_method_id": f"pm_user_methods_{i}",
                "type": "card",
                "last_four": f"000{i}",
                "brand": "visa",
            },
        )

    methods = await get_user_payment_methods(
        async_session,
        str(test_organization.id),
        str(test_user.id),
    )

    assert len(methods) == 3


@pytest.mark.asyncio
async def test_delete_saved_payment_method(
    async_session, test_organization, payment_customer
):
    """Test soft deleting a saved payment method."""
    # Create method
    method = await create_saved_payment_method(
        async_session,
        str(test_organization.id),
        {
            "customer_id": str(payment_customer.id),
            "provider": "stripe",
            "provider_payment_method_id": "pm_to_delete",
            "type": "card",
        },
    )

    # Delete
    result = await delete_saved_payment_method(
        async_session,
        str(test_organization.id),
        str(method.id),
    )

    assert result is True

    # Verify deleted
    retrieved = await get_saved_payment_method(
        async_session,
        str(test_organization.id),
        str(method.id),
    )

    assert retrieved is None


@pytest.mark.asyncio
async def test_delete_saved_payment_method_not_found(async_session, test_organization):
    """Test deleting non-existent payment method returns False."""
    result = await delete_saved_payment_method(
        async_session,
        str(test_organization.id),
        str(uuid4()),
    )

    assert result is False


@pytest.mark.asyncio
async def test_set_default_payment_method(
    async_session, test_organization, payment_customer
):
    """Test setting a payment method as default."""
    # Create two methods
    method1 = await create_saved_payment_method(
        async_session,
        str(test_organization.id),
        {
            "customer_id": str(payment_customer.id),
            "provider": "stripe",
            "provider_payment_method_id": "pm_default_1",
            "type": "card",
            "is_default": True,
        },
    )

    method2 = await create_saved_payment_method(
        async_session,
        str(test_organization.id),
        {
            "customer_id": str(payment_customer.id),
            "provider": "stripe",
            "provider_payment_method_id": "pm_default_2",
            "type": "card",
            "is_default": False,
        },
    )

    # Set method2 as default
    result = await set_default_payment_method(
        async_session,
        str(test_organization.id),
        str(payment_customer.id),
        str(method2.id),
    )

    assert result is True

    # Refresh and verify
    await async_session.refresh(method1)
    await async_session.refresh(method2)

    assert method1.is_default is False
    assert method2.is_default is True


@pytest.mark.asyncio
async def test_set_default_payment_method_wrong_customer(
    async_session, test_organization, payment_customer, test_user
):
    """Test setting default fails if method belongs to different customer."""
    # Create another customer
    other_customer = await create_payment_customer(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "payfast",  # Different provider
            "provider_customer_id": "cus_other",
            "email": test_user.email,
        },
    )

    # Create method for other customer
    method = await create_saved_payment_method(
        async_session,
        str(test_organization.id),
        {
            "customer_id": str(other_customer.id),
            "provider": "payfast",
            "provider_payment_method_id": "pm_other_customer",
            "type": "card",
        },
    )

    # Try to set as default for payment_customer
    result = await set_default_payment_method(
        async_session,
        str(test_organization.id),
        str(payment_customer.id),  # Different customer
        str(method.id),
    )

    assert result is False
