from __future__ import annotations

from datetime import datetime, timezone
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class WebPushSubscription(Base):
    """A browser Web Push subscription for one user device.

    Platform-level rather than tenant-scoped: a browser subscribes once, and the
    subscription belongs to the person, not to whichever organization they were
    looking at when they allowed notifications. Pruned by the dispatcher when
    the push service reports the endpoint gone (404/410).
    """

    __tablename__ = "web_push_subscription"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_seen_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    __table_args__ = (
        # The ENDPOINT is the device identity, so it is unique on its own among
        # live rows — not per (user, endpoint). A browser hands out one push
        # endpoint per installation, and the push service delivers to the
        # endpoint, not to a person. Keying on (user_id, endpoint) let one
        # endpoint hold ACTIVE rows for several users, so on a shared device the
        # person who logged out kept receiving notification titles and bodies on
        # the screen of the person who logged in. Re-registering an endpoint now
        # REASSIGNS it to the current user instead of adding a second row (see
        # api/push.py).
        Index(
            "uq_web_push_endpoint_active",
            "endpoint",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )
