"""
Payment API endpoints.

Handles payment operations including checkout, refunds, and payment history.
"""

import traceback
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_user,
    get_session,
    require_permission,
)
from src.core.exceptions import create_http_exception
from src.logger.logger import Logger
from src.serialisers.payment import (
    CreateCheckoutRequest,
    CreateCheckoutResponse,
    PaymentListResponse,
    PaymentResponse,
    RefundRequest,
    RefundResponse,
)
from src.services.payments import PaymentService


router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/checkout", response_model=CreateCheckoutResponse)
async def create_checkout_session(
    checkout_request: CreateCheckoutRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    http_request: Request,
):
    """
    Create a hosted checkout session.

    Returns a URL to redirect the customer to complete payment.
    The customer will be redirected to success_url or cancel_url
    after completing or cancelling the checkout.
    """
    try:
        result = await PaymentService.create_checkout(
            session=session,
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            amount_cents=checkout_request.amount_cents,
            currency=checkout_request.currency,
            description=checkout_request.description,
            success_url=checkout_request.success_url,
            cancel_url=checkout_request.cancel_url,
            metadata=checkout_request.metadata,
        )
        return CreateCheckoutResponse(
            payment_id=result["payment_id"],
            checkout_url=result["checkout_url"],
            expires_at=result.get("expires_at"),
        )

    except ValueError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error creating checkout session: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="payments.checkout_failed",
        )


@router.get("", response_model=PaymentListResponse)
async def list_payments(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 20,
    offset: int = 0,
    status_filter: Optional[str] = None,
):
    """
    List payments for the organization.

    Non-admin users only see their own payments.
    Admin users see all payments in the organization.

    Args:
        limit: Maximum number of results (default 20, max 100)
        offset: Number of results to skip
        status_filter: Optional status filter (pending, succeeded, failed, etc.)

    Returns:
        Paginated list of payments
    """
    limit = min(limit, 100)  # Cap at 100

    # Non-admin users can only see their own payments
    user_id_filter = None if current_user.is_admin else current_user.id

    result = await PaymentService.list_payments(
        session=session,
        organization_id=current_user.organization_id,
        status=status_filter,
        user_id=user_id_filter,
        limit=limit,
        offset=offset,
    )

    return PaymentListResponse(
        items=[PaymentResponse(**item) for item in result["items"]],
        total=result["total"],
        limit=result["limit"],
        offset=result["offset"],
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get payment details.

    Args:
        payment_id: Payment UUID

    Returns:
        Payment details
    """
    payment = await PaymentService.get_payment(
        session=session,
        organization_id=current_user.organization_id,
        payment_id=payment_id,
    )

    if not payment:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
            detail_code="payments.not_found",
        )

    return PaymentResponse(**payment)


@router.post("/{payment_id}/refund", response_model=RefundResponse)
async def refund_payment(
    payment_id: str,
    refund_request: RefundRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("payments:refund"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    http_request: Request,
):
    """
    Refund a payment (full or partial).

    Args:
        payment_id: Payment UUID
        refund_request: Refund details (amount_cents for partial refund, reason)

    Returns:
        Refund result
    """
    try:
        result = await PaymentService.refund_payment(
            session=session,
            organization_id=current_user.organization_id,
            payment_id=payment_id,
            amount_cents=refund_request.amount_cents,
            reason=refund_request.reason,
            actor_id=current_user.id,
        )

        return RefundResponse(**result)

    except ValueError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error refunding payment {payment_id}: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="payments.refund_failed",
        )
