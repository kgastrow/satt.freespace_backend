"""Admin serialisers for the Freespace event log (M8). snake_case."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from src.models.site_event import SiteEvent


def iso_z(value: datetime | None) -> str | None:
    """ISO-8601 UTC with ``Z``; naive datetimes (SQLite) are taken as UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class SiteEventResponse(BaseModel):
    id: UUID
    site_id: UUID
    occurred_at: str
    last_seen_at: str | None
    repeat_count: int
    type: str
    reason: str | None
    advisory_type: str | None
    zone_slug: str | None
    recommended_zone_slug: str | None
    figures: dict[str, Any] | None
    rendered_title: str | None
    rendered_body: str | None
    counts: dict[str, int] | None
    fanout_status: str | None
    fcm_latency_ms: int | None
    details: dict[str, Any] | None

    @classmethod
    def from_row(cls, row: SiteEvent) -> SiteEventResponse:
        return cls(
            id=row.id,
            site_id=row.site_id,
            occurred_at=iso_z(row.occurred_at) or "",
            last_seen_at=iso_z(row.last_seen_at),
            repeat_count=row.repeat_count,
            type=row.type,
            reason=row.reason,
            advisory_type=row.advisory_type,
            zone_slug=row.zone_slug,
            recommended_zone_slug=row.recommended_zone_slug,
            figures=row.figures,
            rendered_title=row.rendered_title,
            rendered_body=row.rendered_body,
            counts=row.counts,
            fanout_status=row.fanout_status,
            fcm_latency_ms=row.fcm_latency_ms,
            details=row.details,
        )


class SiteEventListResponse(BaseModel):
    items: list[SiteEventResponse]
    total: int
    limit: int
    offset: int


CSV_COLUMNS: tuple[str, ...] = (
    "occurred_at",
    "last_seen_at",
    "repeat_count",
    "type",
    "reason",
    "advisory_type",
    "zone",
    "recommended_zone",
    "title",
    "body",
    "occupancy_pct",
    "counts",
    "fanout_status",
    "fcm_latency_ms",
    "details",
)
