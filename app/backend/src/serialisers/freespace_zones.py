"""Admin serialisers for Freespace zones (M1). snake_case."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from src.models.zone import Zone


class CreateZoneRequest(BaseModel):
    """Admin-created zones are enabled by default (discovered ones are not)."""

    slug: StrictStr = Field(..., max_length=200)
    name: StrictStr
    display_order: StrictInt = 0
    enabled: StrictBool = True
    recommendable: StrictBool = True
    preferred: StrictBool = False
    priority: StrictInt = 100
    limited_pct: StrictInt = 80
    full_pct: StrictInt = 95
    full_min_free: StrictInt = 5
    unknown_limit_pct: StrictInt = 25
    advisory_pct: StrictInt | None = None
    note: StrictStr = ""
    model_config = ConfigDict(extra="forbid")


class UpdateZoneRequest(BaseModel):
    """Omitted fields keep their value; the merged result is validated.
    ``reviewed: true`` clears the ``discovered`` flag (BF-2, BF-14).
    ``advisory_pct: null`` unsets the zone advisory."""

    name: StrictStr | None = None
    display_order: StrictInt | None = None
    enabled: StrictBool | None = None
    recommendable: StrictBool | None = None
    preferred: StrictBool | None = None
    priority: StrictInt | None = None
    limited_pct: StrictInt | None = None
    full_pct: StrictInt | None = None
    full_min_free: StrictInt | None = None
    unknown_limit_pct: StrictInt | None = None
    advisory_pct: StrictInt | None = None
    note: StrictStr | None = None
    reviewed: StrictBool | None = None
    model_config = ConfigDict(extra="forbid")


class ZoneResponse(BaseModel):
    id: UUID
    site_id: UUID
    slug: str
    name: str
    display_order: int
    enabled: bool
    recommendable: bool
    preferred: bool
    priority: int
    limited_pct: int
    full_pct: int
    full_min_free: int
    unknown_limit_pct: int
    advisory_pct: int | None
    note: str
    discovered: bool
    created_time: str | None = None
    updated_time: str | None = None

    @classmethod
    def from_row(cls, zone: Zone) -> ZoneResponse:
        return cls(
            id=zone.id,
            site_id=zone.site_id,
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
            note=zone.note,
            discovered=zone.discovered,
            created_time=zone.created_time.isoformat() if zone.created_time else None,
            updated_time=zone.updated_time.isoformat() if zone.updated_time else None,
        )


class ZoneListResponse(BaseModel):
    items: list[ZoneResponse]
    total: int


class CreateZoneResponse(BaseModel):
    message: str
    message_code: str
    zone: ZoneResponse


class UpdateZoneResponse(CreateZoneResponse):
    pass


class DeleteZoneResponse(BaseModel):
    message: str
    message_code: str
