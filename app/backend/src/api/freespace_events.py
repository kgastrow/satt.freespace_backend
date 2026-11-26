"""
Admin: event log list with filters and CSV export (BF-62, BF-76, BF-78).
OWNER: M8.

Prefix ``/admin/sites/{site_id}/events``. Permission: ``site_events:read``.
The CSV contains no device data (BF-35). Wording: "accepted by FCM", never
"delivered" (BF-69).
"""

from __future__ import annotations

from collections.abc import Iterator
import csv
from datetime import datetime
import io
import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_session, require_permission
from src.api.freespace_sites import internal_error, require_site
from src.constants.freespace import PERM_SITE_EVENTS_READ, EventType
from src.core.exceptions import create_http_exception
from src.crud.freespace_events import count_events, export_events, list_events
from src.models.site import Site
from src.models.site_event import SiteEvent
from src.serialisers.freespace_events import (
    CSV_COLUMNS,
    SiteEventListResponse,
    SiteEventResponse,
    iso_z,
)
from src.services.freespace.clock import ensure_utc


router = APIRouter(
    prefix="/admin/sites/{site_id}/events", tags=["freespace-admin-events"]
)

ReadUser = Annotated[CurrentUser, Depends(require_permission(PERM_SITE_EVENTS_READ))]
Session = Annotated[AsyncSession, Depends(get_session)]

MAX_EXPORT_ROWS = 50_000
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _validated_filters(
    event_type: str | None, start: datetime | None, end: datetime | None
) -> tuple[datetime | None, datetime | None]:
    if event_type is not None and event_type not in {e.value for e in EventType}:
        raise create_http_exception(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unknown event type",
            detail_code="site_event.invalid_filter",
        )
    start_utc = ensure_utc(start) if start is not None else None
    end_utc = ensure_utc(end) if end is not None else None
    if start_utc is not None and end_utc is not None and start_utc >= end_utc:
        raise create_http_exception(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Period start must be before its end",
            detail_code="site_event.invalid_period",
        )
    return start_utc, end_utc


@router.get("", response_model=SiteEventListResponse)
async def list_site_events(
    site_id: UUID,
    http_request: Request,
    current_user: ReadUser,
    session: Session,
    type: str | None = Query(None, description="Event type (BF-62)"),
    reason: str | None = Query(None, max_length=40),
    start: datetime | None = Query(None, description="Period start (inclusive)"),
    end: datetime | None = Query(None, description="Period end (exclusive)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    try:
        site = await require_site(session, site_id, current_user)
        start_utc, end_utc = _validated_filters(type, start, end)
        rows, total = await list_events(
            session,
            site,
            event_type=type,
            reason=reason,
            start=start_utc,
            end=end_utc,
            limit=limit,
            offset=offset,
        )
        return SiteEventListResponse(
            items=[SiteEventResponse.from_row(r) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "list_site_events", exc)


def _cell(value: Any) -> str:
    """CSV cell; neutralises spreadsheet formula injection."""
    text = "" if value is None else str(value)
    if text.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + text
    return text


def _row_values(row: SiteEvent) -> list[str]:
    site_figures = (row.figures or {}).get("site")
    pct = site_figures.get("occupancyPct") if isinstance(site_figures, dict) else None
    return [
        _cell(iso_z(row.occurred_at)),
        _cell(iso_z(row.last_seen_at)),
        _cell(row.repeat_count),
        _cell(row.type),
        _cell(row.reason),
        _cell(row.advisory_type),
        _cell(row.zone_slug),
        _cell(row.recommended_zone_slug),
        _cell(row.rendered_title),
        _cell(row.rendered_body),
        _cell(pct),
        _cell(json.dumps(row.counts, sort_keys=True) if row.counts else ""),
        _cell(row.fanout_status),
        _cell(row.fcm_latency_ms),
        _cell(json.dumps(row.details, sort_keys=True) if row.details else ""),
    ]


def _csv_lines(rows: list[SiteEvent]) -> Iterator[str]:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    yield buffer.getvalue()
    for row in rows:
        buffer.seek(0)
        buffer.truncate()
        writer.writerow(_row_values(row))
        yield buffer.getvalue()


@router.get("/export.csv")
async def export_site_events_csv(
    site_id: UUID,
    http_request: Request,
    current_user: ReadUser,
    session: Session,
    type: str | None = Query(None),
    reason: str | None = Query(None, max_length=40),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
):
    try:
        site: Site = await require_site(session, site_id, current_user)
        start_utc, end_utc = _validated_filters(type, start, end)
        total = await count_events(
            session, site, event_type=type, reason=reason, start=start_utc, end=end_utc
        )
        if total > MAX_EXPORT_ROWS:
            raise create_http_exception(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Too many events to export; narrow the period",
                detail_code="site_event.export_too_large",
            )
        rows = await export_events(
            session,
            site,
            event_type=type,
            reason=reason,
            start=start_utc,
            end=end_utc,
            limit=MAX_EXPORT_ROWS,
        )
        return StreamingResponse(
            _csv_lines(rows),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="events-{site.slug}.csv"'
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "export_site_events_csv", exc)
