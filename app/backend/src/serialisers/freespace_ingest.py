"""
Wire models for the ParkIT intake (BF-11, BF-12, BF-15, §5.2). OWNER: M3.

Request models use camelCase aliases and ``extra="ignore"`` (D15) so a later
ParkIT that adds a field is not rejected. Malformed bodies get FastAPI's
default 422 (with the field path, BF-12). Responses stay tiny (BF-19).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from src.constants.freespace import Health


# Upper bound keeps counts inside a 32-bit INTEGER column; far above any car park.
MAX_COUNT = 1_000_000
# Defensive cap on zones per submission (a site has "a handful").
MAX_ZONES_PER_SUBMISSION = 500
MAX_IDENTIFIER_LENGTH = 64

Count = Annotated[int, Field(ge=0, le=MAX_COUNT, strict=True)]
Identifier = Annotated[
    str, Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH, strict=True)
]


def to_wire_timestamp(value: datetime) -> str:
    """ISO-8601 UTC with a ``Z`` suffix (BN-2). Naive values are taken as UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class _IngestIn(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class _WireOut(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class IngestCounts(_IngestIn):
    """The five counts of a site or zone block (§5.2)."""

    capacity: Count
    occupied: Count
    free_usable: Count
    free_reserved: Count = 0
    free_disabled: Count = 0
    unknown: Count = 0

    @property
    def counted_total(self) -> int:
        """``occupied + freeUsable + freeReserved + freeDisabled + unknown``."""
        return (
            self.occupied
            + self.free_usable
            + self.free_reserved
            + self.free_disabled
            + self.unknown
        )

    @property
    def is_consistent(self) -> bool:
        """BF-12 sum check."""
        return self.counted_total == self.capacity


class IngestSiteBlock(IngestCounts):
    """Site totals as computed by ParkIT (never summed from zones)."""

    health: Health


class IngestZoneBlock(IngestCounts):
    """One zone of the submission."""

    zone_id: Identifier
    name: str | None = None
    health: Health
    measured_at: datetime | None = None


class IngestPublisher(_IngestIn):
    """``publisher`` block; informational only."""

    product: str | None = None
    version: str | None = None
    instance: str | None = None


class IngestOccupancyRequest(_IngestIn):
    """``POST /v1/ingest/occupancy`` body (§5.2)."""

    site_id: Identifier
    measured_at: datetime
    publisher: IngestPublisher | None = None
    site: IngestSiteBlock
    zones: list[IngestZoneBlock] = Field(
        default_factory=list, max_length=MAX_ZONES_PER_SUBMISSION
    )

    @model_validator(mode="after")
    def _unique_zone_ids(self) -> IngestOccupancyRequest:
        seen: set[str] = set()
        for zone in self.zones:
            if zone.zone_id in seen:
                raise ValueError(f"duplicate zoneId '{zone.zone_id}' in zones")
            seen.add(zone.zone_id)
        return self


class IngestSiteView(_WireOut):
    """BF-15 ``site`` block: the backend's view after evaluation."""

    stale: bool
    state: str
    recommended_zone_id: str | None = None


class IngestAcceptedResponse(_WireOut):
    """BF-15 response of an accepted submission."""

    accepted: bool = True
    received_at: str
    site: IngestSiteView
    discovered_zones: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class IngestIgnoredResponse(_WireOut):
    """BF-13 ``{"ignored": "OUT_OF_ORDER"}``."""

    ignored: str


class IngestPingResponse(_WireOut):
    """BF-11 ``GET /v1/ingest/ping`` response."""

    site_id: str
    site_name: str
    server_time: str
