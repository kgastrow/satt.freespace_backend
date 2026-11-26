"""
ParkIT intake (BF-10 - BF-19): ``POST /v1/ingest/occupancy``, ``GET /v1/ingest/ping``.
OWNER: M3.

Auth: ``get_ingest_site`` (ping) / ``enforce_ingest_rate_limit`` (occupancy:
authenticates through ``get_ingest_site``, then applies BF-18).
Request models: camelCase aliases, ``extra="ignore"`` (D15).
The logic lives in ``src/services/freespace/intake.py``.

No ``from __future__ import annotations`` here: ``limiter.exempt`` wraps the
endpoint, and FastAPI then resolves string annotations in slowapi's globals.
"""

import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.freespace_deps import IngestAuth, get_ingest_site
from src.core.exceptions import create_http_exception
from src.core.rate_limit import limiter
from src.logger.logger import Logger as logger
from src.serialisers.freespace_ingest import (
    IngestAcceptedResponse,
    IngestIgnoredResponse,
    IngestOccupancyRequest,
    IngestPingResponse,
    IngestSiteView,
    to_wire_timestamp,
)
from src.services.freespace.clock import Clock, get_clock
from src.services.freespace.ingest_rate_limit import enforce_ingest_rate_limit
from src.services.freespace.intake import (
    ClockSkewError,
    SiteMismatchError,
    SiteNotReadyError,
    ingest_snapshot,
)


router = APIRouter(prefix="/ingest", tags=["freespace-ingest"])


# BF-18: the template's default per-IP limit must not throttle ParkIT (several
# publishers can share one corporate egress IP). Authentication is by key and
# POST /occupancy is limited per KEY (``enforce_ingest_rate_limit``).
@router.get("/ping", response_model=IngestPingResponse)
@limiter.exempt
async def ingest_ping(
    auth: Annotated[IngestAuth, Depends(get_ingest_site)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> IngestPingResponse:
    """BF-11: check the key and connectivity; stores nothing."""
    return IngestPingResponse(
        site_id=auth.site.slug,
        site_name=auth.site.name,
        server_time=to_wire_timestamp(clock.now()),
    )


@router.post(
    "/occupancy",
    response_model=IngestAcceptedResponse | IngestIgnoredResponse,
)
@limiter.exempt
async def ingest_occupancy(
    payload: IngestOccupancyRequest,
    request: Request,
    auth: Annotated[IngestAuth, Depends(enforce_ingest_rate_limit)],
    session: Annotated[AsyncSession, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> IngestAcceptedResponse | IngestIgnoredResponse:
    """BF-12 - BF-16: store one snapshot for the key's site and evaluate it."""
    try:
        result = await ingest_snapshot(session, auth.site, payload, clock)
    except SiteMismatchError as exc:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=exc.message,
            detail_code="ingest.site_mismatch",
        ) from exc
    except ClockSkewError as exc:
        raise create_http_exception(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.message,
            detail_code="ingest.clock_skew",
        ) from exc
    except SiteNotReadyError as exc:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found",
            detail_code="ingest.site_not_found",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        error_tb = traceback.format_exc()
        logger.error(f"Unexpected error in ingest_occupancy: {exc}\n{error_tb}")
        request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        ) from exc

    if result.ignored is not None:
        return IngestIgnoredResponse(ignored=result.ignored)
    return IngestAcceptedResponse(
        accepted=True,
        received_at=to_wire_timestamp(result.received_at),
        site=IngestSiteView(
            stale=result.stale,
            state=result.state.value if result.state is not None else "IDLE",
            recommended_zone_id=result.recommended_zone_slug,
        ),
        discovered_zones=list(result.discovered_zones),
        warnings=list(result.warnings),
    )
