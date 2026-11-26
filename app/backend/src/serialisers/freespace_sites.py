"""Admin serialisers for Freespace sites and site config (M1). snake_case."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from src.models.site import Site


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class NotificationWindowRule(BaseModel):
    """One notification window rule, site local time (BF-71). Validated
    semantically by ``site_config.normalise_notification_window``."""

    weekdays: list[int]
    start: str
    end: str
    model_config = ConfigDict(extra="forbid")


class CreateSiteRequest(BaseModel):
    slug: StrictStr = Field(..., max_length=200)
    name: StrictStr = Field(..., min_length=1, max_length=255)
    time_zone: StrictStr | None = None
    fcm_topic: StrictStr | None = Field(None, max_length=255)
    organization_id: UUID | None = None  # super admin only
    model_config = ConfigDict(extra="forbid")


class UpdateSiteRequest(BaseModel):
    """Site details. ``slug`` (the wire siteId) is immutable."""

    name: StrictStr | None = Field(None, min_length=1, max_length=255)
    fcm_topic: StrictStr | None = Field(None, max_length=255)
    model_config = ConfigDict(extra="forbid")


class SiteResponse(BaseModel):
    id: UUID
    organization_id: UUID
    organization_name: str | None = None
    slug: str
    name: str
    time_zone: str
    fcm_topic: str
    managed: bool
    listed: bool
    created_time: str | None = None
    updated_time: str | None = None

    @classmethod
    def from_row(cls, site: Site, organization_name: str | None = None) -> SiteResponse:
        return cls(
            id=site.id,
            organization_id=site.organization_id,
            organization_name=organization_name,
            slug=site.slug,
            name=site.name,
            time_zone=site.time_zone,
            fcm_topic=site.fcm_topic,
            managed=site.managed,
            listed=site.listed,
            created_time=_iso(site.created_time),
            updated_time=_iso(site.updated_time),
        )


class SiteListResponse(BaseModel):
    items: list[SiteResponse]
    total: int
    limit: int
    offset: int


class CreateSiteResponse(BaseModel):
    message: str
    message_code: str
    site: SiteResponse


class UpdateSiteResponse(CreateSiteResponse):
    pass


class DeleteSiteResponse(BaseModel):
    message: str
    message_code: str


class UpdateSiteConfigRequest(BaseModel):
    """Site settings (BF-71). Omitted fields keep their current value; the
    merged result is validated as a whole. ``notification_window: []`` means
    "any time"."""

    managed: StrictBool | None = None
    listed: StrictBool | None = None
    time_zone: StrictStr | None = None
    trigger_pct: StrictInt | None = None
    reset_pct: StrictInt | None = None
    change_points: StrictInt | None = None
    change_direction: StrictStr | None = None
    stabilisation_s: StrictInt | None = None
    recommendation_margin: StrictInt | None = None
    stale_limit_s: StrictInt | None = None
    partial_is_stale: StrictBool | None = None
    recovery_push: StrictBool | None = None
    zone_advisory: StrictBool | None = None
    zone_reset_gap: StrictInt | None = None
    notification_window: list[NotificationWindowRule] | None = None
    cooldown_s: StrictInt | None = None
    daily_cap: StrictInt | None = None
    push_expiry_s: StrictInt | None = None
    model_config = ConfigDict(extra="forbid")


class SiteConfigResponse(BaseModel):
    site_id: UUID
    managed: bool
    listed: bool
    time_zone: str
    trigger_pct: int
    reset_pct: int
    change_points: int
    change_direction: str
    stabilisation_s: int
    recommendation_margin: int
    stale_limit_s: int
    partial_is_stale: bool
    recovery_push: bool
    zone_advisory: bool
    zone_reset_gap: int
    notification_window: list[NotificationWindowRule]
    cooldown_s: int
    daily_cap: int
    push_expiry_s: int
    updated_time: str | None = None

    @classmethod
    def from_row(cls, site: Site) -> SiteConfigResponse:
        data: dict[str, Any] = {
            "site_id": site.id,
            "managed": site.managed,
            "listed": site.listed,
            "time_zone": site.time_zone,
            "trigger_pct": site.trigger_pct,
            "reset_pct": site.reset_pct,
            "change_points": site.change_points,
            "change_direction": site.change_direction,
            "stabilisation_s": site.stabilisation_s,
            "recommendation_margin": site.recommendation_margin,
            "stale_limit_s": site.stale_limit_s,
            "partial_is_stale": site.partial_is_stale,
            "recovery_push": site.recovery_push,
            "zone_advisory": site.zone_advisory,
            "zone_reset_gap": site.zone_reset_gap,
            "notification_window": [
                NotificationWindowRule(**rule) for rule in site.notification_window
            ],
            "cooldown_s": site.cooldown_s,
            "daily_cap": site.daily_cap,
            "push_expiry_s": site.push_expiry_s,
            "updated_time": _iso(site.updated_time),
        }
        return cls(**data)


class UpdateSiteConfigResponse(BaseModel):
    message: str
    message_code: str
    config: SiteConfigResponse
