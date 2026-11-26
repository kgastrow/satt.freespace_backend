"""
SystemConfig model for global system configuration (admin-only).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.user import User


class SystemConfig(Base):
    """
    Global system configuration.

    Key-value store for system-wide settings that can be modified by
    administrators at runtime without code changes.

    Examples of config keys:
    - 'notifications.default_sms_provider': 'aws_sns'
    - 'notifications.bulk_batch_size': 100
    - 'files.max_upload_size_bytes': 104857600
    - 'maintenance.mode': False

    Note: This is a global model (no organization_id) - only super admins
    can access and modify these settings.

    This model does not have deleted_time - config entries are updated or
    removed directly (though removal should be rare).
    """

    __tablename__ = "system_config"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
    )

    # Config identification - key is unique globally
    key: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True
    )

    # Config value (stored as JSON for flexibility)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)

    # Human-readable description of what this config does
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Track who last updated this config
    updated_by_user_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )

    # Relationship
    updated_by: Mapped[User | None] = relationship("User")

    def __repr__(self) -> str:
        return f"<SystemConfig {self.key}>"
