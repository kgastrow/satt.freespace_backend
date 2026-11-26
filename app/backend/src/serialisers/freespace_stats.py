"""Admin serialisers for the Freespace operations screens (M8). snake_case.

No model here carries a device id, suffix or token (BF-35).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from src.constants.freespace import EngineState
from src.models.site import Site
from src.models.site_engine_state import SiteEngineState
from src.serialisers.freespace_events import iso_z
from src.services.freespace.types import SiteAvailability, ZoneAvailability


# ── sites summary ────────────────────────────────────────────────


class SiteSummaryItem(BaseModel):
    id: UUID
    organization_id: UUID
    organization_name: str | None = None
    slug: str
    name: str
    managed: bool
    listed: bool
    mode: str  # "managed" | "shadow"
    as_of: str | None
    age_seconds: int | None
    stale: bool
    engine_state: str | None
    capacity: int | None
    occupied: int | None
    occupancy_pct: int | None
    recommended_zone_slug: str | None
    recommended_zone_name: str | None
    devices_opted_in: int


class SiteSummaryResponse(BaseModel):
    items: list[SiteSummaryItem]
    total: int


def summary_item(
    site: Site,
    availability: SiteAvailability,
    engine: SiteEngineState | None,
    devices_opted_in: int,
    organization_name: str | None = None,
) -> SiteSummaryItem:
    names = {z.slug: z.name for z in availability.zones}
    rec = availability.recommended_zone_slug
    return SiteSummaryItem(
        id=site.id,
        organization_id=site.organization_id,
        organization_name=organization_name,
        slug=site.slug,
        name=site.name,
        managed=site.managed,
        listed=site.listed,
        mode="managed" if site.managed else "shadow",
        as_of=iso_z(availability.as_of),
        age_seconds=availability.age_seconds,
        stale=availability.stale,
        engine_state=engine.state if engine is not None else None,
        capacity=availability.capacity,
        occupied=availability.occupied,
        occupancy_pct=availability.occupancy_pct,
        recommended_zone_slug=rec,
        recommended_zone_name=names.get(rec) if rec else None,
        devices_opted_in=devices_opted_in,
    )


# ── live view ────────────────────────────────────────────────────


class LiveZone(BaseModel):
    id: str  # zone slug (the app's zoneId)
    name: str
    enabled: bool  # the app only lists enabled zones
    recommendable: bool
    capacity: int | None
    occupied: int | None
    free: int | None
    occupancy_pct: int | None
    status: str
    stale: bool
    health: str | None
    as_of: str | None


class LiveAvailability(BaseModel):
    as_of: str | None
    age_seconds: int | None
    stale: bool
    capacity: int | None
    occupied: int | None
    free_usable: int | None
    occupancy_pct: int | None
    health: str | None
    recommended_zone_id: str | None
    top_zones: list[str]
    zones: list[LiveZone]


class LiveZoneAdvisory(BaseModel):
    zone: str
    above_since: str | None
    advised: bool


class LiveEngine(BaseModel):
    state: str
    state_entered_at: str | None
    pending_since: str | None
    fires_at: str | None  # pending_since + stabilisation_s while PENDING
    cycle_id: UUID | None
    last_notified_pct: float | None
    last_notified_zone_slug: str | None
    last_notified_top_zones: list[str]
    last_sent_at: str | None
    current_zone_slug: str | None
    current_zone_since: str | None
    stale: bool
    stale_since: str | None
    inflight_event_id: UUID | None
    inflight: bool
    zone_advisories: list[LiveZoneAdvisory]
    last_evaluated_at: str | None


class LiveSite(BaseModel):
    id: UUID
    slug: str
    name: str
    managed: bool
    listed: bool
    time_zone: str
    stabilisation_s: int
    stale_limit_s: int
    trigger_pct: int
    reset_pct: int


class SiteLiveResponse(BaseModel):
    site: LiveSite
    availability: LiveAvailability
    engine: LiveEngine | None


def _live_zone(z: ZoneAvailability) -> LiveZone:
    return LiveZone(
        id=z.slug,
        name=z.name,
        enabled=z.enabled,
        recommendable=z.recommendable,
        capacity=z.capacity,
        occupied=z.occupied,
        free=z.free,
        occupancy_pct=z.occupancy_pct,
        status=str(z.status),
        stale=z.stale,
        health=str(z.health) if z.health is not None else None,
        as_of=iso_z(z.as_of),
    )


def live_response(
    site: Site, availability: SiteAvailability, engine: SiteEngineState | None
) -> SiteLiveResponse:
    from datetime import timedelta

    from src.services.freespace.clock import ensure_utc

    live_engine: LiveEngine | None = None
    if engine is not None:
        fires_at = None
        if engine.state == EngineState.PENDING and engine.pending_since is not None:
            fires_at = iso_z(
                ensure_utc(engine.pending_since)
                + timedelta(seconds=site.stabilisation_s)
            )
        advisories: dict[str, Any] = engine.zone_advisory_state or {}
        live_engine = LiveEngine(
            state=engine.state,
            state_entered_at=iso_z(engine.state_entered_at),
            pending_since=iso_z(engine.pending_since),
            fires_at=fires_at,
            cycle_id=engine.cycle_id,
            last_notified_pct=engine.last_notified_pct,
            last_notified_zone_slug=engine.last_notified_zone_slug,
            last_notified_top_zones=list(engine.last_notified_top_zones or []),
            last_sent_at=iso_z(engine.last_sent_at),
            current_zone_slug=engine.current_zone_slug,
            current_zone_since=iso_z(engine.current_zone_since),
            stale=engine.stale,
            stale_since=iso_z(engine.stale_since),
            inflight_event_id=engine.inflight_event_id,
            inflight=engine.inflight_event_id is not None,
            zone_advisories=[
                LiveZoneAdvisory(
                    zone=slug,
                    above_since=(value or {}).get("above_since"),
                    advised=bool((value or {}).get("advised")),
                )
                for slug, value in sorted(advisories.items())
            ],
            last_evaluated_at=iso_z(engine.last_evaluated_at),
        )
    return SiteLiveResponse(
        site=LiveSite(
            id=site.id,
            slug=site.slug,
            name=site.name,
            managed=site.managed,
            listed=site.listed,
            time_zone=site.time_zone,
            stabilisation_s=site.stabilisation_s,
            stale_limit_s=site.stale_limit_s,
            trigger_pct=site.trigger_pct,
            reset_pct=site.reset_pct,
        ),
        availability=LiveAvailability(
            as_of=iso_z(availability.as_of),
            age_seconds=availability.age_seconds,
            stale=availability.stale,
            capacity=availability.capacity,
            occupied=availability.occupied,
            free_usable=availability.free_usable,
            occupancy_pct=availability.occupancy_pct,
            health=(
                str(availability.health) if availability.health is not None else None
            ),
            recommended_zone_id=availability.recommended_zone_slug,
            top_zones=list(availability.top_zones),
            zones=[_live_zone(z) for z in availability.zones],
        ),
        engine=live_engine,
    )


# ── device statistics ────────────────────────────────────────────


class CountByPlatform(BaseModel):
    platform: str
    count: int


class CountByVersion(BaseModel):
    app_version: str | None
    count: int


class CountBySite(BaseModel):
    site_id: UUID
    slug: str
    name: str
    devices: int
    opted_in: int


class DeviceStatsResponse(BaseModel):
    total_devices: int
    opted_in: int
    by_platform: list[CountByPlatform]
    by_app_version: list[CountByVersion]
    by_site: list[CountBySite]


def device_stats_response(stats: dict[str, Any]) -> DeviceStatsResponse:
    return DeviceStatsResponse(
        total_devices=stats["total"],
        opted_in=stats["opted_in"],
        by_platform=[
            CountByPlatform(platform=p, count=n) for p, n in stats["platforms"]
        ],
        by_app_version=[
            CountByVersion(app_version=v, count=n) for v, n in stats["versions"]
        ],
        by_site=[
            CountBySite(site_id=sid, slug=slug, name=name, devices=n, opted_in=o)
            for sid, slug, name, n, o in stats["sites"]
        ],
    )


# ── occupancy history ────────────────────────────────────────────


class HistoryPoint(BaseModel):
    at: str
    occupied: int
    capacity: int
    free_usable: int
    occupancy_pct: int | None
    health: str


class ZoneSeries(BaseModel):
    id: str  # zone slug
    name: str
    points: list[HistoryPoint]


class SiteHistoryResponse(BaseModel):
    site_id: UUID
    date: str
    time_zone: str
    start: str
    end: str
    trigger_pct: int
    reset_pct: int
    site: list[HistoryPoint]
    zones: list[ZoneSeries]
