"""
Mock / demonstration endpoints (BF-84, BF-85, D13). OWNER: M10.

* ``GET  /mock/status``                      mock mode on + current mock time.
* ``POST /mock/sites/{site_slug}/occupancy`` inject a snapshot as if ParkIT sent it.
* ``POST /mock/clock``                       advance / reset the mock clock.

Mounted at the application ROOT (not under /v1) and ONLY when
``settings.FREESPACE_MOCK_MODE`` is on; otherwise the routes do not exist
(404, not 403 - BT-10). The startup guard is ``services/freespace/mock_mode.py``.

Auth decision: these endpoints are deliberately UNAUTHENTICATED (the spec gives
none; the demo simulator page calls them directly). The protection is the
deployment guard (mock mode refuses to start outside DEBUG without an explicit
acknowledgement) plus the global per-IP rate limit middleware.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.exceptions import create_http_exception
from src.logger.logger import Logger as logger
from src.models.site import Site
from src.serialisers.freespace_ingest import (
    IngestAcceptedResponse,
    IngestIgnoredResponse,
    IngestSiteView,
    to_wire_timestamp,
)
from src.serialisers.freespace_mock import (
    MockClockRequest,
    MockClockResponse,
    MockOccupancyRequest,
    MockStatusResponse,
    MockTickSummary,
)
from src.services.freespace.clock import (
    Clock,
    advance_mock_offset,
    get_clock,
    get_mock_offset_seconds,
    reset_mock_offset,
)
from src.services.freespace.intake import (
    ClockSkewError,
    SiteMismatchError,
    SiteNotReadyError,
    ingest_snapshot,
)
from src.services.freespace.redis_client import get_redis


router = APIRouter(prefix="/mock", tags=["freespace-mock"])


def _internal_error(request: Request, exc: Exception) -> HTTPException:
    error_tb = traceback.format_exc()
    logger.error(f"Unexpected error in mock endpoint: {exc}\n{error_tb}")
    request.state.error_traceback = error_tb
    return create_http_exception(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error",
        detail_code="common.internal_error",
    )


@router.get("/status", response_model=MockStatusResponse)
async def mock_status(
    clock: Annotated[Clock, Depends(get_clock)],
) -> MockStatusResponse:
    """Mock mode is on (this route exists only then) and the mock time."""
    return MockStatusResponse(
        mock_time=to_wire_timestamp(clock.now()),
        offset_seconds=await get_mock_offset_seconds(),
    )


@router.post(
    "/sites/{site_slug}/occupancy",
    response_model=IngestAcceptedResponse | IngestIgnoredResponse,
)
async def mock_set_occupancy(
    site_slug: str,
    payload: MockOccupancyRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> IngestAcceptedResponse | IngestIgnoredResponse:
    """Set a snapshot as if ParkIT had sent it (same path as real intake, no key).

    ``siteId`` in the body is required (same body as intake) and must equal the
    path slug, otherwise SITE_MISMATCH (403), exactly like real intake.
    """
    site = (
        await session.execute(
            select(Site).where(Site.slug == site_slug, Site.deleted_time.is_(None))
        )
    ).scalar_one_or_none()
    if site is None:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found",
            detail_code="ingest.site_not_found",
        )

    real_payload = payload.model_copy(
        update={"measured_at": payload.measured_at or clock.now()}
    )
    try:
        result = await ingest_snapshot(session, site, real_payload, clock)  # type: ignore[arg-type]
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
        raise _internal_error(request, exc) from exc

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


async def _run_tick(session: AsyncSession, clock: Clock) -> MockTickSummary:
    """Run the engine tick for all sites inline (what the ARQ cron does)."""
    from src.services.freespace.evaluator import run_engine_tick

    @asynccontextmanager
    async def _factory() -> AsyncIterator[AsyncSession]:
        # The request session; the caller owns its lifecycle. A real factory
        # discards a failed session; here the shared one must be rolled back
        # so one site's half-done evaluation is never committed with the
        # next site (and a PostgreSQL aborted transaction does not cascade).
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise

    try:
        result = await run_engine_tick(_factory, clock)
    except NotImplementedError:
        logger.debug("Freespace mock clock: engine tick not implemented yet")
        return MockTickSummary(ran=False)
    return MockTickSummary(
        ran=True,
        sites_evaluated=result.sites_evaluated,
        sites_failed=result.sites_failed,
        fanouts_enqueued=result.fanouts_enqueued,
    )


@router.post("/clock", response_model=MockClockResponse)
async def mock_clock(
    body: MockClockRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MockClockResponse:
    """Advance the mock clock by ``seconds`` or reset the offset (``reset``).

    The offset lives in Redis so every API worker and the ARQ worker agree.
    After the change an engine tick runs inline so stabilisation timers expire.
    """
    if get_redis() is None:
        raise create_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis is required to move the mock clock",
            detail_code="mock.redis_unavailable",
        )
    try:
        if body.reset:
            await reset_mock_offset()
        else:
            assert body.seconds is not None
            await advance_mock_offset(body.seconds)
        clock = await get_clock()
        offset = await get_mock_offset_seconds()
        tick = await _run_tick(session, clock)
    except HTTPException:
        raise
    except Exception as exc:
        raise _internal_error(request, exc) from exc
    return MockClockResponse(
        mock_time=to_wire_timestamp(clock.now()),
        offset_seconds=offset,
        tick=tick,
    )
