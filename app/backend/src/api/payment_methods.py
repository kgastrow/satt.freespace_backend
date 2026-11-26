"""
Saved payment methods API endpoints.

Handles listing, deleting, and setting default payment methods for users.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_user,
    get_session,
)
from src.core.exceptions import create_http_exception
from src.serialisers.payment import (
    PaymentMethodListResponse,
    SavedPaymentMethodResponse,
)
from src.services.payments import PaymentService


router = APIRouter(prefix="/payment-methods", tags=["payment-methods"])


@router.get("", response_model=PaymentMethodListResponse)
async def list_saved_payment_methods(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    List saved payment methods for the current user.

    Returns all saved cards, bank accounts, etc. for the user
    across all payment providers.
    """
    methods = await PaymentService.get_user_payment_methods(
        session=session,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
    )

    return PaymentMethodListResponse(
        items=[SavedPaymentMethodResponse(**m) for m in methods],
        total=len(methods),
    )


@router.delete("/{payment_method_id}")
async def delete_saved_payment_method(
    payment_method_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Delete a saved payment method.

    Removes from both local database and payment provider.

    Args:
        payment_method_id: Payment method UUID
    """
    success = await PaymentService.delete_payment_method(
        session=session,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        payment_method_id=payment_method_id,
    )

    if not success:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment method not found",
            detail_code="payments.method_not_found",
        )

    return {"deleted": True}


@router.post("/{payment_method_id}/default")
async def set_default_payment_method(
    payment_method_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Set a payment method as the default for the user.

    The default payment method will be used automatically
    for future payments when no other method is specified.

    Args:
        payment_method_id: Payment method UUID
    """
    success = await PaymentService.set_default_payment_method(
        session=session,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        payment_method_id=payment_method_id,
    )

    if not success:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment method not found",
            detail_code="payments.method_not_found",
        )

    return {"success": True}
