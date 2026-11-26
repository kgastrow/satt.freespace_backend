"""
Admin: sites list summary, site live view, device statistics, occupancy
history (BF-76, BF-78). OWNER: M8.

Prefix ``/admin/sites``. Contains the LITERAL single-segment routes
(``/summary``, ``/device-stats``) so it is included BEFORE
``freespace_sites.router`` (whose ``/{site_id}`` would otherwise capture them,
CLAUDE.md rule 13). Permission: ``sites:read``.

Read-only: the live view runs the shared availability computation with the
stored recommendation and never evaluates the engine or writes anything.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_session, require_permission
from src.api.freespace_sites import internal_error, require_site, tenant_scope
from src.constants.freespace import PERM_SITES_READ
from src.core.exceptions import create_http_exception
from src.crud.freespace_sites import organization_names
from src.crud.freespace_stats import (
    device_statistics,
    engine_states_by_site,
    history_points,
    list_scoped_sites,
    opted_in_counts_by_site,
    snapshots_by_site,
    zones_by_site,
)
from src.models.site_engine_state import SiteEngineState
from src.serialisers.freespace_events import iso_z
from src.serialisers.freespace_stats import (
    DeviceStatsResponse,
    HistoryPoint,
    SiteHistoryResponse,
    SiteLiveResponse,
    SiteSummaryResponse,
    ZoneSeries,
    device_stats_response,
    live_response,
    summary_item,
)
from src.services.freespace.availability import (
    compute_site_availability,
    occupancy_pct_floor,
)
from src.services.freespace.clock import Clock, ensure_utc, get_clock
from src.services.freespace.loaders import (
    load_engine_state_row,
    load_snapshot,
    load_zone_rows,
    site_settings_from_row,
    zone_config_from_row,
)


router = APIRouter(prefix="/admin/sites", tags=["freespace-admin-stats"])

ReadUser = Annotated[CurrentUser, Depends(require_permission(PERM_SITES_READ))]
Session = Annotated[AsyncSession, Depends(get_session)]
ClockDep = Annotated[Clock, Depends(get_clock)]


@router.get("/summary", response_model=SiteSummaryResponse)
async def sites_summary(
    http_request: Request,
    current_user: ReadUser,
    session: Session,
    clock: ClockDep,
):
    """BF-76 sites list. A fixed number of queries regardless of site count."""
    try:
        now = clock.now()
        sites = await list_scoped_sites(session, tenant_scope(current_user))
        ids = [s.id for s in sites]
        zones = await zones_by_site(session, ids)
        snapshots = await snapshots_by_site(session, ids)
        engines = await engine_states_by_site(session, ids)
        devices = await opted_in_counts_by_site(session, ids)
        names = await organization_names(session, [s.organization_id for s in sites])
        items = []
        for site in sites:
            engine = engines.get(site.id)
            availability = compute_site_availability(
                site_settings_from_row(site),
                tuple(zone_config_from_row(z) for z in zones.get(site.id, [])),
                snapshots[site.id],
                engine.current_zone_slug if engine else None,
                now,
            )
            items.append(
                summary_item(
                    site,
                    availability,
                    engine,
                    devices.get(site.id, 0),
                    names.get(site.organization_id),
                )
            )
        return SiteSummaryResponse(items=items, total=len(items))
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "sites_summary", exc)


@router.get("/device-stats", response_model=DeviceStatsResponse)
async def all_device_stats(
    http_request: Request, current_user: ReadUser, session: Session
):
    """Counts by platform, app version, opted-in and site. Aggregates only."""
    try:
        stats = await device_statistics(session, tenant_scope(current_user))
        return device_stats_response(stats)
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "all_device_stats", exc)


@router.get("/{site_id}/device-stats", response_model=DeviceStatsResponse)
async def site_device_stats(
    site_id: UUID, http_request: Request, current_user: ReadUser, session: Session
):
    try:
        site = await require_site(session, site_id, current_user)
        stats = await device_statistics(session, site.organization_id, site.id)
        return device_stats_response(stats)
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "site_device_stats", exc)


@router.get("/{site_id}/live", response_model=SiteLiveResponse)
async def site_live_view(
    site_id: UUID,
    http_request: Request,
    current_user: ReadUser,
    session: Session,
    clock: ClockDep,
):
    """BF-76 live view: the app's zone table (same computation, BF-24) plus
    the engine state and its timers."""
    try:
        site = await require_site(session, site_id, current_user)
        engine: SiteEngineState | None = await load_engine_state_row(session, site.id)
        availability = compute_site_availability(
            site_settings_from_row(site),
            tuple(
                zone_config_from_row(z) for z in await load_zone_rows(session, site.id)
            ),
            await load_snapshot(session, site.id),
            engine.current_zone_slug if engine else None,
            clock.now(),
        )
        return live_response(site, availability, engine)
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "site_live_view", exc)


def _invalid_date() -> HTTPException:
    return create_http_exception(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Invalid date",
        detail_code="site_stats.invalid_date",
    )


@router.get("/{site_id}/history", response_model=SiteHistoryResponse)
async def site_history(
    site_id: UUID,
    http_request: Request,
    current_user: ReadUser,
    session: Session,
    clock: ClockDep,
    day: str | None = Query(
        None,
        alias="date",
        description="YYYY-MM-DD in the site's time zone (default: today there)",
    ),
):
    """Site and zone occupancy series for one local day, with the site's
    trigger and reset levels for the chart."""
    try:
        site = await require_site(session, site_id, current_user)
        tz = ZoneInfo(site.time_zone)
        if day is None:
            local_day = ensure_utc(clock.now()).astimezone(tz).date()
        else:
            try:
                local_day = date.fromisoformat(day)
            except ValueError:
                raise _invalid_date()
        start_local = datetime.combine(local_day, time.min, tzinfo=tz)
        end_local = datetime.combine(local_day + timedelta(days=1), time.min, tzinfo=tz)
        start = start_local.astimezone(timezone.utc)
        end = end_local.astimezone(timezone.utc)
        zones = {z.id: z for z in await load_zone_rows(session, site.id)}
        site_points: list[HistoryPoint] = []
        zone_points: dict[UUID, list[HistoryPoint]] = {}
        for zone_id, row in await history_points(session, site, start, end):
            point = HistoryPoint(
                at=iso_z(row.bucket_minute) or "",
                occupied=row.occupied,
                capacity=row.capacity,
                free_usable=row.free_usable,
                occupancy_pct=occupancy_pct_floor(row.occupied, row.capacity),
                health=row.health,
            )
            if zone_id is None:
                site_points.append(point)
            elif zone_id in zones:
                zone_points.setdefault(zone_id, []).append(point)
        return SiteHistoryResponse(
            site_id=site.id,
            date=local_day.isoformat(),
            time_zone=site.time_zone,
            start=iso_z(start) or "",
            end=iso_z(end) or "",
            trigger_pct=site.trigger_pct,
            reset_pct=site.reset_pct,
            site=site_points,
            zones=[
                ZoneSeries(id=z.slug, name=z.name, points=zone_points[z.id])
                for z in zones.values()
                if z.id in zone_points
            ],
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "site_history", exc)
