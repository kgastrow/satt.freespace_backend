"""
ORM rows -> pure core types (and back for engine state).

Pure converters are synchronous and take rows; the ``load_*`` coroutines run
the queries. Ingest / app / engine code paths address a site by id or slug
with no tenant context (D2), so these loaders do NOT filter by
``organization_id``; admin endpoints must resolve and tenant-check the site
first (see contracts §tenant scoping) and only then call a loader.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, time
from types import MappingProxyType
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.freespace import (
    AdvisoryType,
    ChangeDirection,
    EngineState,
    Health,
)
from src.models.organization import Organization
from src.models.site import Site
from src.models.site_engine_state import SiteEngineState
from src.models.site_message_template import SiteMessageTemplate
from src.models.site_snapshot import SiteSnapshot, ZoneSnapshot
from src.models.zone import Zone
from src.services.freespace.clock import ensure_utc
from src.services.freespace.types import (
    EngineStateData,
    MessageTemplate,
    NotificationWindowRule,
    SiteFigures,
    SiteSettings,
    SnapshotView,
    ZoneAdvisoryState,
    ZoneConfig,
    ZoneFigures,
)


def _utc(value: datetime | None) -> datetime | None:
    return ensure_utc(value) if value is not None else None


def _parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def parse_notification_window(raw: Any) -> tuple[NotificationWindowRule, ...]:
    """Parse the ``site.notification_window`` JSON (see model docstring).

    Raises ``ValueError`` on a malformed rule (M1 validates on save, so this
    only fires on hand-edited data).
    """
    if not raw:
        return ()
    rules: list[NotificationWindowRule] = []
    for item in raw:
        weekdays = frozenset(int(d) for d in item["weekdays"])
        if not weekdays or not weekdays <= frozenset(range(1, 8)):
            raise ValueError(f"invalid weekdays in notification window: {item!r}")
        start = _parse_hhmm(str(item["start"]))
        end = _parse_hhmm(str(item["end"]))
        if not start < end:
            raise ValueError(f"notification window start must be < end: {item!r}")
        rules.append(NotificationWindowRule(weekdays=weekdays, start=start, end=end))
    return tuple(rules)


def notification_window_to_json(
    rules: Iterable[NotificationWindowRule],
) -> list[dict[str, Any]]:
    """Inverse of ``parse_notification_window``."""
    return [
        {
            "weekdays": sorted(rule.weekdays),
            "start": rule.start.strftime("%H:%M"),
            "end": rule.end.strftime("%H:%M"),
        }
        for rule in rules
    ]


def site_settings_from_row(site: Site) -> SiteSettings:
    """Site row -> ``SiteSettings``."""
    return SiteSettings(
        site_id=site.id,
        organization_id=site.organization_id,
        slug=site.slug,
        name=site.name,
        time_zone=site.time_zone,
        fcm_topic=site.fcm_topic,
        managed=site.managed,
        listed=site.listed,
        trigger_pct=site.trigger_pct,
        reset_pct=site.reset_pct,
        change_points=site.change_points,
        change_direction=ChangeDirection(site.change_direction),
        stabilisation_s=site.stabilisation_s,
        recommendation_margin=site.recommendation_margin,
        stale_limit_s=site.stale_limit_s,
        partial_is_stale=site.partial_is_stale,
        recovery_push=site.recovery_push,
        zone_advisory=site.zone_advisory,
        zone_reset_gap=site.zone_reset_gap,
        notification_window=parse_notification_window(site.notification_window),
        cooldown_s=site.cooldown_s,
        daily_cap=site.daily_cap,
        push_expiry_s=site.push_expiry_s,
    )


def zone_config_from_row(zone: Zone) -> ZoneConfig:
    """Zone row -> ``ZoneConfig``."""
    return ZoneConfig(
        zone_id=zone.id,
        slug=zone.slug,
        name=zone.name,
        display_order=zone.display_order,
        enabled=zone.enabled,
        recommendable=zone.recommendable,
        preferred=zone.preferred,
        priority=zone.priority,
        limited_pct=zone.limited_pct,
        full_pct=zone.full_pct,
        full_min_free=zone.full_min_free,
        unknown_limit_pct=zone.unknown_limit_pct,
        advisory_pct=zone.advisory_pct,
        discovered=zone.discovered,
    )


def site_figures_from_row(row: SiteSnapshot) -> SiteFigures:
    """Site snapshot row -> ``SiteFigures``."""
    return SiteFigures(
        capacity=row.capacity,
        occupied=row.occupied,
        free_usable=row.free_usable,
        free_reserved=row.free_reserved,
        free_disabled=row.free_disabled,
        unknown=row.unknown,
        health=Health(row.health),
        measured_at=ensure_utc(row.measured_at),
        received_at=ensure_utc(row.received_at),
    )


def zone_figures_from_row(row: ZoneSnapshot, zone_slug: str) -> ZoneFigures:
    """Zone snapshot row (+ its zone's slug) -> ``ZoneFigures``."""
    return ZoneFigures(
        capacity=row.capacity,
        occupied=row.occupied,
        free_usable=row.free_usable,
        free_reserved=row.free_reserved,
        free_disabled=row.free_disabled,
        unknown=row.unknown,
        health=Health(row.health),
        measured_at=ensure_utc(row.measured_at),
        received_at=ensure_utc(row.received_at),
        zone_slug=zone_slug,
    )


def message_template_from_row(row: SiteMessageTemplate) -> MessageTemplate:
    """Template row -> ``MessageTemplate``."""
    return MessageTemplate(
        advisory_type=AdvisoryType(row.advisory_type),
        title=row.title,
        body=row.body,
        locale=row.locale,
    )


def _zone_advisory_from_json(
    raw: Mapping[str, Any] | None,
) -> dict[str, ZoneAdvisoryState]:
    result: dict[str, ZoneAdvisoryState] = {}
    for slug, item in (raw or {}).items():
        above = item.get("above_since")
        result[slug] = ZoneAdvisoryState(
            above_since=ensure_utc(datetime.fromisoformat(above)) if above else None,
            advised=bool(item.get("advised", False)),
        )
    return result


def _zone_advisory_to_json(data: Mapping[str, ZoneAdvisoryState]) -> dict[str, Any]:
    return {
        slug: {
            "above_since": state.above_since.isoformat() if state.above_since else None,
            "advised": state.advised,
        }
        for slug, state in data.items()
    }


def engine_state_from_row(row: SiteEngineState) -> EngineStateData:
    """Engine state row -> ``EngineStateData``."""
    return EngineStateData(
        state=EngineState(row.state),
        state_entered_at=ensure_utc(row.state_entered_at),
        pending_since=_utc(row.pending_since),
        cycle_id=row.cycle_id,
        last_notified_pct=row.last_notified_pct,
        last_notified_zone_slug=row.last_notified_zone_slug,
        last_notified_top_zones=tuple(row.last_notified_top_zones or ()),
        last_sent_fingerprint=row.last_sent_fingerprint,
        last_sent_at=_utc(row.last_sent_at),
        current_zone_slug=row.current_zone_slug,
        current_zone_since=_utc(row.current_zone_since),
        zone_advisory=MappingProxyType(
            _zone_advisory_from_json(row.zone_advisory_state)
        ),
        stale=row.stale,
        stale_since=_utc(row.stale_since),
        inflight_event_id=row.inflight_event_id,
        inflight_fingerprint=row.inflight_fingerprint,
        last_evaluated_at=_utc(row.last_evaluated_at),
    )


def apply_engine_state(row: SiteEngineState, data: EngineStateData) -> None:
    """Copy ``data`` onto ``row`` (in place; caller flushes/commits).

    Leaves ``ops_alert_state`` alone - it belongs to M9.
    """
    row.state = data.state.value
    row.state_entered_at = data.state_entered_at
    row.pending_since = data.pending_since
    row.cycle_id = data.cycle_id
    row.last_notified_pct = data.last_notified_pct
    row.last_notified_zone_slug = data.last_notified_zone_slug
    row.last_notified_top_zones = list(data.last_notified_top_zones)
    row.last_sent_fingerprint = data.last_sent_fingerprint
    row.last_sent_at = data.last_sent_at
    row.current_zone_slug = data.current_zone_slug
    row.current_zone_since = data.current_zone_since
    row.zone_advisory_state = _zone_advisory_to_json(data.zone_advisory)
    row.stale = data.stale
    row.stale_since = data.stale_since
    row.inflight_event_id = data.inflight_event_id
    row.inflight_fingerprint = data.inflight_fingerprint
    row.last_evaluated_at = data.last_evaluated_at


# ─────────────────────────────────────────────────────────────
# Queries
# ─────────────────────────────────────────────────────────────


async def load_site_row(session: AsyncSession, site_id: uuid.UUID) -> Site | None:
    """Live site row by id (no tenant filter, see module docstring)."""
    result = await session.execute(
        select(Site).where(Site.id == site_id, Site.deleted_time.is_(None))
    )
    return result.scalars().first()


async def load_site_row_by_slug(session: AsyncSession, slug: str) -> Site | None:
    """Live site row by wire siteId (no tenant filter, see module docstring)."""
    result = await session.execute(
        select(Site)
        .join(Organization, Organization.id == Site.organization_id)
        .where(
            Site.slug == slug,
            Site.deleted_time.is_(None),
            Organization.deleted_time.is_(None),
            Organization.is_active.is_(True),
        )
    )
    return result.scalars().first()


async def load_zone_rows(session: AsyncSession, site_id: uuid.UUID) -> list[Zone]:
    """Live zones of a site in display order (then slug)."""
    result = await session.execute(
        select(Zone)
        .where(Zone.site_id == site_id, Zone.deleted_time.is_(None))
        .order_by(Zone.display_order, Zone.slug)
    )
    return list(result.scalars().all())


async def load_zone_configs(
    session: AsyncSession, site_id: uuid.UUID
) -> tuple[ZoneConfig, ...]:
    """Live zones of a site as ``ZoneConfig`` in display order."""
    return tuple(
        zone_config_from_row(z) for z in await load_zone_rows(session, site_id)
    )


async def load_snapshot(session: AsyncSession, site_id: uuid.UUID) -> SnapshotView:
    """Latest snapshot of a site; zone snapshots of deleted zones are skipped."""
    site_row = (
        (
            await session.execute(
                select(SiteSnapshot).where(SiteSnapshot.site_id == site_id)
            )
        )
        .scalars()
        .first()
    )
    zone_rows = await session.execute(
        select(ZoneSnapshot, Zone.slug)
        .join(Zone, Zone.id == ZoneSnapshot.zone_id)
        .where(ZoneSnapshot.site_id == site_id, Zone.deleted_time.is_(None))
    )
    zones = {slug: zone_figures_from_row(row, slug) for row, slug in zone_rows.all()}
    return SnapshotView(
        site=site_figures_from_row(site_row) if site_row else None,
        zones=MappingProxyType(zones),
    )


async def load_templates(
    session: AsyncSession, site_id: uuid.UUID, locale: str = "en"
) -> dict[AdvisoryType, MessageTemplate]:
    """Live templates of a site for ``locale``, keyed by advisory type."""
    result = await session.execute(
        select(SiteMessageTemplate).where(
            SiteMessageTemplate.site_id == site_id,
            SiteMessageTemplate.locale == locale,
            SiteMessageTemplate.deleted_time.is_(None),
        )
    )
    return {
        AdvisoryType(row.advisory_type): message_template_from_row(row)
        for row in result.scalars().all()
    }


async def load_engine_state_row(
    session: AsyncSession, site_id: uuid.UUID, *, for_update: bool = False
) -> SiteEngineState | None:
    """The engine-state row of a site. ``for_update=True`` takes the D6 row
    lock (``SELECT ... FOR UPDATE``; a no-op on SQLite)."""
    query = select(SiteEngineState).where(SiteEngineState.site_id == site_id)
    if for_update:
        query = query.with_for_update()
    return (await session.execute(query)).scalars().first()


@dataclass(frozen=True)
class SiteContext:
    """Everything the core needs for one site, loaded in one go."""

    site: Site
    settings: SiteSettings
    zones: tuple[ZoneConfig, ...]
    snapshot: SnapshotView
    templates: Mapping[AdvisoryType, MessageTemplate]


async def load_site_context(
    session: AsyncSession, site_id: uuid.UUID, *, with_templates: bool = True
) -> SiteContext | None:
    """Load site settings, zones, snapshot (and templates). None if no live site."""
    site = await load_site_row(session, site_id)
    if site is None:
        return None
    templates: Mapping[AdvisoryType, MessageTemplate] = (
        await load_templates(session, site_id) if with_templates else {}
    )
    return SiteContext(
        site=site,
        settings=site_settings_from_row(site),
        zones=await load_zone_configs(session, site_id),
        snapshot=await load_snapshot(session, site_id),
        templates=MappingProxyType(dict(templates)),
    )


def zones_by_slug(zones: Sequence[ZoneConfig]) -> dict[str, ZoneConfig]:
    """Index zone configs by slug."""
    return {zone.slug: zone for zone in zones}
