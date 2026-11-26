"""
Wire models for ``PUT /v1/devices/{deviceId}`` (BF-33). OWNER: M5.

camelCase on the wire (D15). The response echoes ``deviceId`` only because it
answers that device's own PUT (BF-35).
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from src.constants.freespace import Platform


MAX_SITE_IDS = 100


class _Wire(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class DeviceRegistrationRequest(_Wire):
    """Body of ``PUT /v1/devices/{deviceId}``. ``siteIds`` are site slugs."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid"
    )

    fcm_token: str = Field(min_length=1, max_length=512)
    platform: Platform
    site_ids: list[str] = Field(default_factory=list, max_length=MAX_SITE_IDS)
    notifications_enabled: bool = True
    app_version: str | None = Field(default=None, max_length=32)


class DeviceRegistrationResponse(_Wire):
    """The stored registration."""

    device_id: str
    fcm_token: str | None
    platform: Platform
    site_ids: list[str]
    notifications_enabled: bool
    app_version: str | None
    first_seen: str
    last_seen: str
    token_invalidated_at: str | None


def iso_utc(value: datetime | None) -> str | None:
    """ISO-8601 UTC with ``Z`` (naive values are taken as UTC)."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
