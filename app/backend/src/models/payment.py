"""
Payment and invoice models.

Core payment record and audit trail for all payment operations.
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid as uuid_module

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Payment(Base):
    """
    Core payment record.

    Stores payment information independent of provider.
    Provider-specific details stored in provider_data JSON.
    """

    __tablename__ = "payment"

    # Primary key
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

    # Optional user association
    user_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), index=True, nullable=True
    )

    # Provider information
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_reference: Mapped[str] = mapped_column(String(255), nullable=False)

    # Link to internal customer record (preferred over raw provider ID)
    customer_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_customer.id"),
        index=True,
        nullable=True,
    )
    # Legacy: raw provider customer ID (for backwards compatibility)
    provider_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Idempotency key for preventing duplicate payments
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Amount (always store in smallest unit - cents)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)  # ISO 4217

    # Refund tracking
    refunded_amount_cents: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # Status
    status: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    # Payment details
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Failure information
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Flexible metadata (named extra_data to avoid SQLAlchemy Base conflict)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provider_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Capture timestamp (for auth/capture flow)
    captured_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    events: Mapped[list[PaymentEvent]] = relationship(
        "PaymentEvent", back_populates="payment", lazy="selectin"
    )
    invoices: Mapped[list[PaymentInvoice]] = relationship(
        "PaymentInvoice", back_populates="payment", lazy="selectin"
    )

    __table_args__ = (
        # Unique provider reference per provider
        Index(
            "uq_payment_provider_ref",
            "provider",
            "provider_reference",
            unique=True,
        ),
        # Fast lookups by org + status
        Index(
            "ix_payment_org_status",
            "organization_id",
            "status",
        ),
        # Partial index for active payments
        Index(
            "ix_payment_org_active",
            "organization_id",
            "created_time",
            postgresql_where=text("deleted_time IS NULL"),
        ),
        # Idempotency key lookup
        Index(
            "ix_payment_idempotency",
            "organization_id",
            "idempotency_key",
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Payment {self.provider}:{self.provider_reference} {self.status}>"


class PaymentEvent(Base):
    """
    Payment event log for audit trail.

    Records all status changes, webhook events, and actions.
    Immutable - events are only created, never updated.
    """

    __tablename__ = "payment_event"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    payment_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment.id"), index=True, nullable=False
    )

    # Event details
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_source: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'webhook', 'api', 'system'

    # Provider's event ID (for deduplication)
    provider_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Status transition
    previous_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Full event payload
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Actor (for manual actions)
    actor_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    actor_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # 'user', 'system', 'webhook'

    # Relationship
    payment: Mapped[Payment] = relationship("Payment", back_populates="events")

    __table_args__ = (
        # Prevent duplicate webhook processing
        Index(
            "uq_payment_event_provider",
            "payment_id",
            "provider_event_id",
            unique=True,
            postgresql_where=text("provider_event_id IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<PaymentEvent {self.event_type} {self.event_source}>"


class Invoice(Base):
    """
    Invoice record linked to payments.

    Supports multiple payments per invoice and
    invoice generation independent of payment.
    """

    __tablename__ = "invoice"

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

    # Invoice number (org-scoped)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)

    # Customer details (denormalized for invoice permanence)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_address: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Amounts
    subtotal_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    # Status: draft, sent, paid, void, overdue
    status: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    # Line items
    line_items: Mapped[list[dict]] = mapped_column(JSON, nullable=False)

    # Dates
    issue_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    payments: Mapped[list[PaymentInvoice]] = relationship(
        "PaymentInvoice", back_populates="invoice", lazy="selectin"
    )

    __table_args__ = (
        # Unique invoice number per org
        Index(
            "uq_invoice_org_number",
            "organization_id",
            "invoice_number",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Invoice {self.invoice_number} {self.status}>"


class PaymentInvoice(Base):
    """
    Junction table linking payments to invoices.

    Allows multiple payments per invoice (partial payments)
    and potentially multiple invoices per payment (consolidated).
    """

    __tablename__ = "payment_invoice"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    payment_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment.id"), index=True, nullable=False
    )

    invoice_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoice.id"), index=True, nullable=False
    )

    # Amount of this payment applied to this invoice
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    payment: Mapped[Payment] = relationship("Payment", back_populates="invoices")
    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="payments")

    __table_args__ = (
        Index(
            "uq_payment_invoice",
            "payment_id",
            "invoice_id",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return f"<PaymentInvoice payment={self.payment_id} invoice={self.invoice_id}>"
