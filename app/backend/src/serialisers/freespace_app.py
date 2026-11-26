"""
Wire models of the app endpoints (BF-30, BF-31). OWNER: M4.

camelCase on the wire (D15); every timestamp ISO-8601 UTC with ``Z`` (BN-2).
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from src.constants.freespace import ZoneStatus
from src.models.site import Site
from src.services.freespace.types import SiteAvailability, ZoneAvailability


def to_wire_time(value: datetime | None) -> str | None:
    """ISO-8601 UTC with a ``Z`` suffix (BN-2); None stays None."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class _WireModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ─────────────────────────────────────────────────────────────
# GET /v1/sites (BF-30)
# ─────────────────────────────────────────────────────────────


class AppSiteItem(_WireModel):
    id: str = Field(description="Wire siteId (slug)")
    name: str
    topic: str = Field(description="FCM topic the app subscribes to (BF-40)")
    managed: bool
    time_zone: str = Field(description="IANA time zone")


class AppSiteListResponse(_WireModel):
    sites: list[AppSiteItem]


def site_list_response(sites: list[Site]) -> AppSiteListResponse:
    return AppSiteListResponse(
        sites=[
            AppSiteItem(
                id=site.slug,
                name=site.name,
                topic=site.fcm_topic,
                managed=site.managed,
                time_zone=site.time_zone,
            )
            for site in sites
        ]
    )


# ─────────────────────────────────────────────────────────────
# GET /v1/sites/{siteId}/availability (BF-31)
# ─────────────────────────────────────────────────────────────


class AppSiteTotals(_WireModel):
    capacity: int
    occupied: int
    occupancy_pct: int | None = Field(description="floor(occupied/capacity*100)")
    free_usable: int


class AppZoneAvailability(_WireModel):
    id: str = Field(description="Wire zoneId (slug)")
    name: str
    capacity: int | None
    free: int | None = Field(description="freeUsable")
    occupancy_pct: int | None
    status: ZoneStatus
    as_of: str | None = Field(description="Zone receivedAt, ISO-8601 UTC")


class AppAvailabilityResponse(_WireModel):
    site_id: str
    as_of: str | None = Field(description="Site receivedAt, ISO-8601 UTC")
    age_seconds: int | None = Field(description="Server-computed data age")
    stale: bool
    site: AppSiteTotals | None
    recommended_zone_id: str | None
    zones: list[AppZoneAvailability]


def _zone_item(zone: ZoneAvailability) -> AppZoneAvailability:
    return AppZoneAvailability(
        id=zone.slug,
        name=zone.name,
        capacity=zone.capacity,
        free=zone.free,
        occupancy_pct=zone.occupancy_pct,
        status=zone.status,
        as_of=to_wire_time(zone.as_of),
    )


def availability_response(availability: SiteAvailability) -> AppAvailabilityResponse:
    """BF-31 shape. Only ``enabled`` zones, in display order, UNKNOWN included.
    A never-received site answers ``stale: true``, ``asOf: null``,
    ``site: null``, ``zones: []``."""
    never_received = availability.as_of is None
    site: AppSiteTotals | None = None
    if (
        not never_received
        and availability.capacity is not None
        and availability.occupied is not None
        and availability.free_usable is not None
    ):
        site = AppSiteTotals(
            capacity=availability.capacity,
            occupied=availability.occupied,
            occupancy_pct=availability.occupancy_pct,
            free_usable=availability.free_usable,
        )
    return AppAvailabilityResponse(
        site_id=availability.site_slug,
        as_of=to_wire_time(availability.as_of),
        age_seconds=availability.age_seconds,
        stale=availability.stale,
        site=site,
        recommended_zone_id=availability.recommended_zone_slug,
        zones=(
            []
            if never_received
            else [_zone_item(z) for z in availability.zones if z.enabled]
        ),
    )
