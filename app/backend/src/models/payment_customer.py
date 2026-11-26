"""
Payment customer and saved payment method models.

Maps application users to payment provider customer records.
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid as uuid_module

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class PaymentCustomer(Base):
    """
    Maps application users to payment provider customer records.

    Supports:
    - Multiple providers per user (user can have Stripe + PayFast customers)
    - Guest customers (user_id = NULL)
    - Saved payment methods via relationship

    This enables:
    - Saved cards for returning customers
    - Subscription billing
    - Customer-level analytics
    """

    __tablename__ = "payment_customer"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Multi-tenancy
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), index=True, nullable=False
    )

    # Optional user association (NULL for guest checkout)
    user_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), index=True, nullable=True
    )

    # Provider information
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_customer_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Customer details (denormalized for provider sync)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Default payment method reference
    default_payment_method_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Flexible metadata (named extra_data to avoid SQLAlchemy Base conflict)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    payment_methods: Mapped[list[SavedPaymentMethod]] = relationship(
        "SavedPaymentMethod",
        back_populates="customer",
        lazy="selectin",
    )

    __table_args__ = (
        # Unique provider customer per org+provider combination
        Index(
            "uq_payment_customer_provider",
            "organization_id",
            "provider",
            "provider_customer_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
        # Fast lookup by user
        Index(
            "ix_payment_customer_user",
            "organization_id",
            "user_id",
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<PaymentCustomer {self.provider}:{self.provider_customer_id}>"


class SavedPaymentMethod(Base):
    """
    Saved payment methods (cards, bank accounts, etc.)

    Linked to PaymentCustomer for multi-provider support.
    Card details are stored at the provider - we only keep
    non-sensitive display information.
    """

    __tablename__ = "saved_payment_method"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Multi-tenancy
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), index=True, nullable=False
    )

    # Link to customer
    customer_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_customer.id"),
        index=True,
        nullable=False,
    )

    # Provider information
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_payment_method_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Payment method type
    type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'card', 'bank_account', 'sepa_debit', etc.

    # Card details (non-sensitive display info)
    last_four: Mapped[str | None] = mapped_column(String(4), nullable=True)
    brand: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # 'visa', 'mastercard', 'amex', etc.
    exp_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exp_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Bank account details (non-sensitive)
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_last_four: Mapped[str | None] = mapped_column(String(4), nullable=True)

    # Display name (user-defined or auto-generated)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Status
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_expired: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationship
    customer: Mapped[PaymentCustomer] = relationship(
        "PaymentCustomer", back_populates="payment_methods"
    )

    __table_args__ = (
        # Unique provider payment method
        Index(
            "uq_saved_payment_method_provider",
            "provider",
            "provider_payment_method_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
        # Find default payment method for customer
        Index(
            "ix_saved_payment_method_default",
            "customer_id",
            "is_default",
            postgresql_where=text("deleted_time IS NULL AND is_default = true"),
        ),
    )

    def __repr__(self) -> str:
        return f"<SavedPaymentMethod {self.type} {self.last_four or self.account_last_four}>"
