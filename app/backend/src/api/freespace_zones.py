"""
Admin: zones CRUD and discovered-zone review (BF-2, BF-14, §10.2). OWNER: M1.

Prefix ``/admin/sites/{site_id}/zones``. Permissions: ``sites:read`` /
``sites:write``. The parent site is resolved with the tenant rule of
``freespace_sites`` (other tenant -> 404 ``site.not_found``); a zone is looked
up by id AND that site, so a foreign zone id is 404 ``zone.not_found``.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_session, require_permission
from src.api.freespace_sites import (
    internal_error,
    record_config_change,
    require_site,
    unprocessable,
)
from src.constants.freespace import (
    PERM_SITES_READ,
    PERM_SITES_WRITE,
    SLUG_RE,
    ConfigChangeReason,
)
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.crud.freespace_zones import (
    get_zone,
    list_zones,
    soft_delete_zone,
    zone_slug_exists,
)
from src.models.zone import Zone
from src.serialisers.freespace_zones import (
    CreateZoneRequest,
    CreateZoneResponse,
    DeleteZoneResponse,
    UpdateZoneRequest,
    UpdateZoneResponse,
    ZoneListResponse,
    ZoneResponse,
)
from src.services.freespace.clock import Clock, get_clock
from src.services.freespace.site_config import (
    ZONE_SETTING_FIELDS,
    ZoneSettingsError,
    validate_zone_settings,
)


router = APIRouter(
    prefix="/admin/sites/{site_id}/zones", tags=["freespace-admin-zones"]
)

ReadUser = Annotated[CurrentUser, Depends(require_permission(PERM_SITES_READ))]
WriteUser = Annotated[CurrentUser, Depends(require_permission(PERM_SITES_WRITE))]
Session = Annotated[AsyncSession, Depends(get_session)]
ClockDep = Annotated[Clock, Depends(get_clock)]


def _zone_not_found():
    return create_http_exception(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Zone not found",
        detail_code="zone.not_found",
    )


def _zone_values(zone: Zone) -> dict[str, Any]:
    return {name: getattr(zone, name) for name in ZONE_SETTING_FIELDS}


def _validated(values: dict[str, Any]) -> dict[str, Any]:
    try:
        return validate_zone_settings(values)
    except ZoneSettingsError as exc:
        raise unprocessable(str(exc), exc.detail_code)


@router.get("", response_model=ZoneListResponse)
async def list_zones_endpoint(
    site_id: UUID,
    http_request: Request,
    current_user: ReadUser,
    session: Session,
    discovered: bool | None = Query(
        None, description="Only zones awaiting (true) / past (false) review"
    ),
):
    try:
        site = await require_site(session, site_id, current_user)
        rows = await list_zones(session, site.id, discovered=discovered)
        return ZoneListResponse(
            items=[ZoneResponse.from_row(row) for row in rows], total=len(rows)
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "list_zones_endpoint", exc)


@router.post("", response_model=CreateZoneResponse, status_code=status.HTTP_201_CREATED)
async def create_zone_endpoint(
    site_id: UUID,
    request: CreateZoneRequest,
    http_request: Request,
    current_user: WriteUser,
    session: Session,
    clock: ClockDep,
):
    try:
        site = await require_site(session, site_id, current_user)
        if not SLUG_RE.match(request.slug):
            raise unprocessable(
                "slug must match [a-z0-9][a-z0-9_-]{0,63}", "zone.invalid_slug"
            )
        values = _validated(request.model_dump(exclude={"slug"}))
        if await zone_slug_exists(session, site.id, request.slug):
            raise create_http_exception(
                status_code=status.HTTP_409_CONFLICT,
                detail="A zone with this slug already exists",
                detail_code="zone.slug_conflict",
            )
        zone = Zone(
            organization_id=site.organization_id,
            site_id=site.id,
            slug=request.slug,
            discovered=False,
            **values,
        )
        session.add(zone)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raise create_http_exception(
                status_code=status.HTTP_409_CONFLICT,
                detail="A zone with this slug already exists",
                detail_code="zone.slug_conflict",
            )
        await record_config_change(
            session,
            clock,
            http_request,
            current_user,
            site,
            reason=ConfigChangeReason.ZONE_SETTINGS,
            resource_type="Zone",
            resource_id=zone.id,
            before={},
            after={"slug": zone.slug, **values},
            zone_slug=zone.slug,
            create=True,
        )
        await session.refresh(zone)
        return CreateZoneResponse(
            message="Zone created successfully",
            message_code=get_response_code("zone.created"),
            zone=ZoneResponse.from_row(zone),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "create_zone_endpoint", exc)


@router.get("/{zone_id}", response_model=ZoneResponse)
async def get_zone_endpoint(
    site_id: UUID,
    zone_id: UUID,
    http_request: Request,
    current_user: ReadUser,
    session: Session,
):
    try:
        site = await require_site(session, site_id, current_user)
        zone = await get_zone(session, site.id, zone_id)
        if zone is None:
            raise _zone_not_found()
        return ZoneResponse.from_row(zone)
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "get_zone_endpoint", exc)


@router.put("/{zone_id}", response_model=UpdateZoneResponse)
async def update_zone_endpoint(
    site_id: UUID,
    zone_id: UUID,
    request: UpdateZoneRequest,
    http_request: Request,
    current_user: WriteUser,
    session: Session,
    clock: ClockDep,
):
    """Change zone settings (§10.2) and/or review a discovered zone
    (``reviewed: true``). Omitted fields keep their value; the merged result is
    validated and refused (422) when invalid."""
    try:
        site = await require_site(session, site_id, current_user)
        zone = await get_zone(session, site.id, zone_id)
        if zone is None:
            raise _zone_not_found()
        before = _zone_values(zone)
        before["discovered"] = zone.discovered
        merged = _zone_values(zone)
        sent = request.model_dump(exclude={"reviewed"}, exclude_unset=True)
        merged.update(
            {k: v for k, v in sent.items() if v is not None or k == "advisory_pct"}
        )
        after = _validated(merged)
        reviewed = bool(request.reviewed) and zone.discovered
        after["discovered"] = False if reviewed else zone.discovered

        if after != before:
            for name, value in after.items():
                setattr(zone, name, value)
            zone.updated_time = clock.now()
            await session.flush()
            await record_config_change(
                session,
                clock,
                http_request,
                current_user,
                site,
                reason=ConfigChangeReason.ZONE_SETTINGS,
                resource_type="Zone",
                resource_id=zone.id,
                before=before,
                after=after,
                zone_slug=zone.slug,
                details={"reviewed": True} if reviewed else None,
            )
            await session.refresh(zone)
        code = "zone.reviewed" if reviewed else "zone.updated"
        return UpdateZoneResponse(
            message=(
                "Zone reviewed successfully"
                if reviewed
                else "Zone updated successfully"
            ),
            message_code=get_response_code(code),
            zone=ZoneResponse.from_row(zone),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "update_zone_endpoint", exc)


@router.delete("/{zone_id}", response_model=DeleteZoneResponse)
async def delete_zone_endpoint(
    site_id: UUID,
    zone_id: UUID,
    http_request: Request,
    current_user: WriteUser,
    session: Session,
    clock: ClockDep,
):
    """Soft delete a zone (D12)."""
    try:
        site = await require_site(session, site_id, current_user)
        zone = await get_zone(session, site.id, zone_id)
        if zone is None:
            raise _zone_not_found()
        before = {"slug": zone.slug, **_zone_values(zone)}
        await soft_delete_zone(session, zone, clock.now())
        await record_config_change(
            session,
            clock,
            http_request,
            current_user,
            site,
            reason=ConfigChangeReason.ZONE_SETTINGS,
            resource_type="Zone",
            resource_id=zone.id,
            before=before,
            after={},
            zone_slug=zone.slug,
            delete=True,
        )
        return DeleteZoneResponse(
            message="Zone deleted successfully",
            message_code=get_response_code("zone.deleted"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "delete_zone_endpoint", exc)
