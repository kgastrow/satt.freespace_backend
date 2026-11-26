"""
App endpoints (BF-30 - BF-32, BF-36): ``GET /v1/sites``,
``GET /v1/sites/{siteId}/availability``. OWNER: M4.

Auth: ``Depends(require_app_key)`` from ``src/api/freespace_deps.py``.
Per-IP limits: ``settings.RATE_LIMIT_FREESPACE_SITES`` /
``RATE_LIMIT_FREESPACE_AVAILABILITY`` via ``src.core.rate_limit.limiter``.

Reads only (BF-32): no evaluation, no push, no write. The availability endpoint
feeds the engine's STORED recommendation (``site_engine_state.current_zone_slug``)
into ``availability.compute_site_availability`` as the stickiness input and
persists nothing (D9), so it can never pick a different sticky winner than the
engine. Sites are resolved by slug only (D2: the one unscoped public read).
"""

import traceback
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.freespace_deps import require_app_key
from src.constants.freespace import AVAILABILITY_CACHE_MAX_AGE_S
from src.core.config import settings
from src.core.exceptions import create_http_exception
from src.core.rate_limit import limiter
from src.logger.logger import Logger as logger
from src.models.organization import Organization
from src.models.site import Site
from src.models.site_engine_state import SiteEngineState
from src.serialisers.freespace_app import (
    AppAvailabilityResponse,
    AppSiteListResponse,
    availability_response,
    site_list_response,
)
from src.services.freespace.availability import compute_site_availability
from src.services.freespace.availability_cache import (
    get_cached_availability,
    set_cached_availability,
)
from src.services.freespace.clock import Clock, get_clock
from src.services.freespace.loaders import (
    load_site_row_by_slug,
    load_snapshot,
    load_zone_configs,
    site_settings_from_row,
)


router = APIRouter(
    prefix="/sites",
    tags=["freespace-app"],
    dependencies=[Depends(require_app_key)],
)

# Explicit scopes are REQUIRED (BF-36): slowapi's default scope is the URL, which
# would give every /sites/{slug}/availability its own per-IP bucket.
SCOPE_SITES = "freespace_sites"
SCOPE_AVAILABILITY = "freespace_availability"

CACHE_CONTROL = f"max-age={AVAILABILITY_CACHE_MAX_AGE_S}"


def _internal_error(request: Request, exc: Exception, what: str) -> HTTPException:
    logger.error(f"Freespace app {what} failed: {exc}")
    request.state.error_traceback = traceback.format_exc()
    return create_http_exception(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error",
        detail_code="common.internal_error",
    )


@router.get("", response_model=AppSiteListResponse)
@limiter.shared_limit(settings.RATE_LIMIT_FREESPACE_SITES, scope=SCOPE_SITES)
async def list_app_sites(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AppSiteListResponse:
    """BF-30: listed live sites, ordered by name (then siteId)."""
    try:
        result = await session.execute(
            select(Site)
            .join(Organization, Organization.id == Site.organization_id)
            .where(
                Site.listed.is_(True),
                Site.deleted_time.is_(None),
                Organization.deleted_time.is_(None),
                Organization.is_active.is_(True),
            )
            .order_by(Site.name, Site.slug)
        )
        return site_list_response(list(result.scalars().all()))
    except HTTPException:
        raise
    except Exception as exc:
        raise _internal_error(request, exc, "site list") from exc


@router.get(
    "/{site_slug}/availability",
    response_model=AppAvailabilityResponse,
    responses={404: {"description": "Unknown or unlisted site"}},
)
@limiter.shared_limit(
    settings.RATE_LIMIT_FREESPACE_AVAILABILITY, scope=SCOPE_AVAILABILITY
)
async def get_app_site_availability(
    request: Request,
    site_slug: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> JSONResponse:
    """BF-31 / BF-32: live availability of one listed site (5 s cache)."""
    try:
        now = clock.now()
        cached = await get_cached_availability(site_slug, now)
        if cached is not None:
            return _availability_json(cached)

        site = await load_site_row_by_slug(session, site_slug)
        if site is None or not site.listed:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Site not found",
                detail_code="site.not_found",
            )
        current = (
            await session.execute(
                select(SiteEngineState.current_zone_slug).where(
                    SiteEngineState.site_id == site.id
                )
            )
        ).scalar_one_or_none()
        availability = compute_site_availability(
            site_settings_from_row(site),
            await load_zone_configs(session, site.id),
            await load_snapshot(session, site.id),
            current,
            now,
        )
        body = availability_response(availability).model_dump(
            mode="json", by_alias=True
        )
        await set_cached_availability(site_slug, now, body)
        return _availability_json(body)
    except HTTPException:
        raise
    except Exception as exc:
        raise _internal_error(request, exc, "availability") from exc


def _availability_json(body: dict[str, Any]) -> JSONResponse:
    return JSONResponse(content=body, headers={"Cache-Control": CACHE_CONTROL})
