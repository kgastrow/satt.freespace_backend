"""
Per-site message template, one per (advisory type, locale) (BF-70, D13).

Only ``locale = 'en'`` exists in this revision; the column is there so a
locale can be added later without a schema change. Default rows are created
with the site (``src/services/freespace/site_bootstrap.py``).
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.constants.freespace import DEFAULT_LOCALE
from src.database import Base


class SiteMessageTemplate(Base):
    """Title/body template for one advisory type of one site."""

    __tablename__ = "site_message_template"

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

    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )
    site_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site.id"), nullable=False, index=True
    )
    # AdvisoryType value (see TEMPLATED_ADVISORY_TYPES)
    advisory_type: Mapped[str] = mapped_column(String(20), nullable=False)
    locale: Mapped[str] = mapped_column(
        String(10), nullable=False, default=DEFAULT_LOCALE
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index(
            "uq_site_message_template_active",
            "site_id",
            "advisory_type",
            "locale",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
            sqlite_where=text("deleted_time IS NULL"),
        ),
    )
