"""
Pydantic serializers for Payment operations.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────
# Checkout
# ─────────────────────────────────────────────────────────────


class CreateCheckoutRequest(BaseModel):
    """Request model for creating a checkout session."""

    amount_cents: int = Field(..., gt=0, description="Amount in cents")
    currency: str = Field(
        ..., min_length=3, max_length=3, description="ISO 4217 currency code"
    )
    description: str = Field(..., max_length=500, description="Payment description")
    success_url: str = Field(..., description="Redirect URL after success")
    cancel_url: str = Field(..., description="Redirect URL after cancel")
    metadata: Optional[dict[str, str]] = Field(None, description="Custom metadata")
    save_payment_method: bool = Field(
        False, description="Save payment method for future use"
    )

    model_config = ConfigDict(extra="forbid")


class CreateCheckoutResponse(BaseModel):
    """Response model for checkout session creation."""

    payment_id: str
    checkout_url: str
    expires_at: Optional[str] = None


# ─────────────────────────────────────────────────────────────
# Payment
# ─────────────────────────────────────────────────────────────


class PaymentResponse(BaseModel):
    """Response model for payment details."""

    id: str
    provider: str
    amount_cents: int
    currency: str
    status: str
    payment_method: Optional[str] = None
    description: Optional[str] = None
    refunded_amount_cents: Optional[int] = 0
    created_time: Optional[str] = None
    captured_time: Optional[str] = None
    metadata: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class PaymentListResponse(BaseModel):
    """Response model for paginated payment list."""

    total: int
    limit: int
    offset: int
    items: list[PaymentResponse]


class PaymentEventResponse(BaseModel):
    """Response model for payment event."""

    id: str
    event_type: str
    event_source: str
    previous_status: Optional[str]
    new_status: Optional[str]
    created_time: str

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────
# Refund
# ─────────────────────────────────────────────────────────────


class RefundRequest(BaseModel):
    """Request model for refunding a payment."""

    amount_cents: Optional[int] = Field(None, gt=0, description="Partial refund amount")
    reason: Optional[str] = Field(None, max_length=500, description="Refund reason")

    model_config = ConfigDict(extra="forbid")


class RefundResponse(BaseModel):
    """Response model for refund operation."""

    success: bool
    refund_reference: str
    amount_cents: int
    payment_id: str
    new_status: str


# ─────────────────────────────────────────────────────────────
# Saved Payment Methods
# ─────────────────────────────────────────────────────────────


class SavedPaymentMethodResponse(BaseModel):
    """Response model for saved payment method."""

    id: str
    type: str
    provider: str
    last_four: Optional[str]
    brand: Optional[str]
    exp_month: Optional[int]
    exp_year: Optional[int]
    bank_name: Optional[str]
    account_last_four: Optional[str]
    display_name: Optional[str]
    is_default: bool
    is_expired: bool

    model_config = ConfigDict(from_attributes=True)


class PaymentMethodListResponse(BaseModel):
    """Response model for list of saved payment methods."""

    items: list[SavedPaymentMethodResponse]
    total: int
