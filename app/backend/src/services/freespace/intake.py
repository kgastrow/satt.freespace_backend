"""
ParkIT intake service (BF-3, BF-4, BF-10, BF-12 - BF-16, BF-19, D7). OWNER: M3.

``ingest_snapshot`` is the ONE entry point that stores a validated snapshot
for a site and runs the evaluation. The HTTP endpoint
(``src/api/freespace_public/ingest.py``) calls it after authentication and
rate limiting; mock mode (M10) calls it to inject a snapshot "as if ParkIT had
sent it".

Transaction: the function owns the transaction from here on. It COMMITS -
rejection events before raising (so they survive the HTTP error), the
snapshot + engine outcome before enqueueing fan-outs (BF-52) - and enqueues
the advisory fan-outs after that commit (D7).

Order of checks
1. ``siteId`` must be the site's slug, else ``INGEST_REJECTED / SITE_MISMATCH``
   and ``SiteMismatchError`` (nothing stored, BT-03).
2. ``measuredAt`` more than ``MAX_FUTURE_SKEW_S`` ahead of the server clock:
   ``INGEST_REJECTED / CLOCK_SKEW`` and ``ClockSkewError`` (BT-04).
3. Lock ``site_engine_state`` FOR UPDATE (serialises intake per site with
   the evaluator, so zone discovery and the out-of-order check cannot race).
4. ``measuredAt`` older than the stored site snapshot: ``INGEST_REJECTED /
   OUT_OF_ORDER``, nothing overwritten, result ``ignored="OUT_OF_ORDER"``.
5. Unknown ``zoneId`` -> discovered zone (``enabled=False``,
   ``discovered=True``, labelled with ``name``) + ``ZONE_DISCOVERED``.
6. BF-12 sum check per block; a mismatch downgrades ``OK`` to ``PARTIAL``
   (``reported_health`` keeps the original) and logs one
   ``INGEST_INCONSISTENT / SUM_MISMATCH`` event per submission.
7. Overwrite snapshot rows of the site and of the submitted zones only
   (missing zones keep their last values and age, BF-14); upsert one history
   point per minute for the site and each submitted zone (BF-4).
8. ``evaluator.evaluate_site`` in a savepoint, commit, ``enqueue_fanouts``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import traceback
from typing import Any
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.freespace import (
    MAX_FUTURE_SKEW_S,
    MAX_INGEST_WARNING_LENGTH,
    MAX_INGEST_WARNINGS,
    EngineState,
    EventType,
    Health,
    IngestInconsistencyReason,
    IngestRejectReason,
)
from src.crud.freespace_history import upsert_history_point
from src.crud.freespace_snapshots import (
    SnapshotValues,
    get_site_snapshot,
    get_zone_snapshots,
    upsert_site_snapshot,
    upsert_zone_snapshot,
)
from src.logger.logger import Logger as logger
from src.models.site import Site
from src.models.zone import Zone
from src.serialisers.freespace_ingest import (
    IngestCounts,
    IngestOccupancyRequest,
    to_wire_timestamp,
)
from src.services.freespace import evaluator
from src.services.freespace.clock import Clock, ensure_utc
from src.services.freespace.events import write_event
from src.services.freespace.loaders import load_engine_state_row
from src.services.freespace.types import EventDraft


OUT_OF_ORDER = "OUT_OF_ORDER"
_PUBLISHER_FIELD_MAX = 100
_ZONE_NAME_MAX = 255
_SUBMITTED_SITE_ID_MAX = 64


# ─────────────────────────────────────────────────────────────
# Result and errors
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IntakeResult:
    """Outcome of ``ingest_snapshot``.

    ``ignored`` is ``"OUT_OF_ORDER"`` when the submission was older than the
    stored snapshot (nothing stored); otherwise ``accepted`` is True and
    ``state`` / ``stale`` / ``recommended_zone_slug`` are the evaluator's view
    (BF-15). ``discovered_zones`` lists the submitted zone slugs that are
    discovered and not yet reviewed (including those created now).
    """

    accepted: bool
    received_at: datetime
    ignored: str | None = None
    state: EngineState | None = None
    stale: bool = True
    recommended_zone_slug: str | None = None
    discovered_zones: tuple[str, ...] = ()
    created_zones: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    fanout_event_ids: tuple[uuid.UUID, ...] = field(default_factory=tuple)


class IntakeRejectedError(Exception):
    """A submission refused after its ``INGEST_REJECTED`` event was committed."""

    reason: IngestRejectReason = IngestRejectReason.SITE_MISMATCH

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class SiteMismatchError(IntakeRejectedError):
    """``siteId`` is not the ingest key's site (BF-10 -> 403)."""

    reason = IngestRejectReason.SITE_MISMATCH


class ClockSkewError(IntakeRejectedError):
    """``measuredAt`` too far in the future (BF-13 -> 422 ``CLOCK_SKEW``)."""

    reason = IngestRejectReason.CLOCK_SKEW


class SiteNotReadyError(Exception):
    """The site has no engine-state row (deleted or never bootstrapped)."""


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


class _Warnings:
    """Short, capped warning list (BF-19)."""

    def __init__(self) -> None:
        self.items: list[str] = []
        self.dropped = 0

    def add(self, text: str) -> None:
        if len(self.items) >= MAX_INGEST_WARNINGS - 1:
            self.dropped += 1
            return
        if len(text) > MAX_INGEST_WARNING_LENGTH:
            text = text[: MAX_INGEST_WARNING_LENGTH - 3] + "..."
        self.items.append(text)

    def result(self) -> tuple[str, ...]:
        if self.dropped:
            return (*self.items, f"... and {self.dropped} more warning(s)")
        return tuple(self.items)


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value[:limit]


def _publisher_json(payload: IngestOccupancyRequest) -> dict[str, Any] | None:
    if payload.publisher is None:
        return None
    return {
        "product": _truncate(payload.publisher.product, _PUBLISHER_FIELD_MAX),
        "version": _truncate(payload.publisher.version, _PUBLISHER_FIELD_MAX),
        "instance": _truncate(payload.publisher.instance, _PUBLISHER_FIELD_MAX),
    }


def _counts_figures(block: IngestCounts) -> dict[str, int]:
    return {
        "capacity": block.capacity,
        "occupied": block.occupied,
        "freeUsable": block.free_usable,
        "freeReserved": block.free_reserved,
        "freeDisabled": block.free_disabled,
        "unknown": block.unknown,
        "sum": block.counted_total,
    }


def _effective_health(reported: Health, consistent: bool) -> Health:
    """BF-12: a sum mismatch marks an ``OK`` block ``PARTIAL``. ``OFFLINE``
    (already worse) and ``PARTIAL`` stay as reported."""
    if not consistent and reported == Health.OK:
        return Health.PARTIAL
    return reported


def _values(
    block: IngestCounts,
    health: Health,
    reported: Health,
    measured_at: datetime,
    received_at: datetime,
) -> SnapshotValues:
    return SnapshotValues(
        capacity=block.capacity,
        occupied=block.occupied,
        free_usable=block.free_usable,
        free_reserved=block.free_reserved,
        free_disabled=block.free_disabled,
        unknown=block.unknown,
        health=health.value,
        reported_health=reported.value,
        measured_at=measured_at,
        received_at=received_at,
    )


async def _reject(
    session: AsyncSession,
    site: Site,
    now: datetime,
    reason: IngestRejectReason,
    details: dict[str, Any],
) -> None:
    """Write and COMMIT an ``INGEST_REJECTED`` event (survives the HTTP error)."""
    await write_event(
        session,
        site_id=site.id,
        organization_id=site.organization_id,
        draft=EventDraft(
            type=EventType.INGEST_REJECTED,
            occurred_at=now,
            reason=reason.value,
            details=details,
        ),
    )
    await session.commit()


async def _live_zones_by_slug(session: AsyncSession, site: Site) -> dict[str, Zone]:
    result = await session.execute(
        select(Zone).where(
            Zone.site_id == site.id,
            Zone.organization_id == site.organization_id,
            Zone.deleted_time.is_(None),
        )
    )
    return {zone.slug: zone for zone in result.scalars().all()}


async def _next_display_order(session: AsyncSession, site: Site) -> int:
    result = await session.execute(
        select(func.max(Zone.display_order)).where(
            Zone.site_id == site.id,
            Zone.organization_id == site.organization_id,
            Zone.deleted_time.is_(None),
        )
    )
    current = result.scalar()
    return int(current) + 1 if current is not None else 0


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────


async def ingest_snapshot(
    session: AsyncSession,
    site: Site,
    payload: IngestOccupancyRequest,
    clock: Clock,
) -> IntakeResult:
    """Store a validated submission for ``site`` and evaluate the site.

    See the module docstring for the order of checks and the transaction
    contract (this function commits). Raises ``SiteMismatchError`` /
    ``ClockSkewError`` after committing the rejection event, and
    ``SiteNotReadyError`` (nothing written) when the site has no engine state.
    """
    now = clock.now()

    # 1. BF-10 / BT-03: the key's site only.
    if payload.site_id != site.slug:
        await _reject(
            session,
            site,
            now,
            IngestRejectReason.SITE_MISMATCH,
            {"submittedSiteId": payload.site_id[:_SUBMITTED_SITE_ID_MAX]},
        )
        raise SiteMismatchError(
            "siteId does not match the site of the ingest key (SITE_MISMATCH)"
        )

    # 2. BF-13 / BT-04: clock skew.
    measured_at = ensure_utc(payload.measured_at)
    ahead_s = (measured_at - now).total_seconds()
    if ahead_s > MAX_FUTURE_SKEW_S:
        await _reject(
            session,
            site,
            now,
            IngestRejectReason.CLOCK_SKEW,
            {
                "measuredAt": to_wire_timestamp(measured_at),
                "receivedAt": to_wire_timestamp(now),
                "aheadSeconds": round(ahead_s, 1),
            },
        )
        raise ClockSkewError(
            f"CLOCK_SKEW: measuredAt is {int(ahead_s)} s ahead of server time "
            f"(limit {MAX_FUTURE_SKEW_S} s)"
        )

    # 3. Per-site serialisation (same lock the evaluator takes).
    state_row = await load_engine_state_row(session, site.id, for_update=True)
    if state_row is None:
        raise SiteNotReadyError(f"site {site.id} has no engine state row")

    # 4. BF-13: out of order.
    site_row = await get_site_snapshot(session, site)
    if site_row is not None and measured_at < ensure_utc(site_row.measured_at):
        await write_event(
            session,
            site_id=site.id,
            organization_id=site.organization_id,
            draft=EventDraft(
                type=EventType.INGEST_REJECTED,
                occurred_at=now,
                reason=IngestRejectReason.OUT_OF_ORDER.value,
                details={
                    "measuredAt": to_wire_timestamp(measured_at),
                    "storedMeasuredAt": to_wire_timestamp(site_row.measured_at),
                },
            ),
        )
        await session.commit()
        return IntakeResult(accepted=False, received_at=now, ignored=OUT_OF_ORDER)

    warnings = _Warnings()

    # 5. BF-14: zone matching / discovery.
    zones = await _live_zones_by_slug(session, site)
    created: list[str] = []
    next_order: int | None = None
    for block in payload.zones:
        if block.zone_id in zones:
            continue
        if next_order is None:
            next_order = await _next_display_order(session, site)
        name = (block.name or "").strip()[:_ZONE_NAME_MAX] or block.zone_id
        zone = Zone(
            organization_id=site.organization_id,
            site_id=site.id,
            slug=block.zone_id,
            name=name,
            display_order=next_order,
            enabled=False,
            discovered=True,
        )
        next_order += 1
        session.add(zone)
        await session.flush()
        zones[block.zone_id] = zone
        created.append(block.zone_id)
        await write_event(
            session,
            site_id=site.id,
            organization_id=site.organization_id,
            draft=EventDraft(
                type=EventType.ZONE_DISCOVERED,
                occurred_at=now,
                zone_slug=block.zone_id,
                details={"name": name},
            ),
        )
    discovered = tuple(
        block.zone_id for block in payload.zones if zones[block.zone_id].discovered
    )

    # 6. BF-12: sum check.
    mismatches: dict[str, dict[str, int]] = {}
    site_consistent = payload.site.is_consistent
    if not site_consistent:
        mismatches["site"] = _counts_figures(payload.site)
        warnings.add(
            f"SUM_MISMATCH site: counts sum to {payload.site.counted_total}, "
            f"capacity {payload.site.capacity}; marked PARTIAL"
        )
    zone_mismatch_slugs: list[str] = []
    for block in payload.zones:
        if not block.is_consistent:
            zone_mismatch_slugs.append(block.zone_id)
            mismatches[f"zone:{block.zone_id}"] = _counts_figures(block)
            warnings.add(
                f"SUM_MISMATCH zone {block.zone_id}: counts sum to "
                f"{block.counted_total}, capacity {block.capacity}; marked PARTIAL"
            )

    # 7. Snapshot rows (BF-3) and history (BF-4).
    site_health = _effective_health(payload.site.health, site_consistent)
    await upsert_site_snapshot(
        session,
        site,
        _values(payload.site, site_health, payload.site.health, measured_at, now),
        publisher=_publisher_json(payload),
        existing=site_row,
    )
    await upsert_history_point(
        session,
        organization_id=site.organization_id,
        site_id=site.id,
        zone_id=None,
        at=now,
        occupied=payload.site.occupied,
        capacity=payload.site.capacity,
        free_usable=payload.site.free_usable,
        health=site_health.value,
    )

    existing_zone_rows = await get_zone_snapshots(
        session, site, [zones[block.zone_id].id for block in payload.zones]
    )
    for block in payload.zones:
        zone = zones[block.zone_id]
        zone_health = _effective_health(block.health, block.is_consistent)
        zone_measured = (
            ensure_utc(block.measured_at) if block.measured_at else measured_at
        )
        await upsert_zone_snapshot(
            session,
            site,
            zone.id,
            _values(block, zone_health, block.health, zone_measured, now),
            existing=existing_zone_rows.get(zone.id),
        )
        await upsert_history_point(
            session,
            organization_id=site.organization_id,
            site_id=site.id,
            zone_id=zone.id,
            at=now,
            occupied=block.occupied,
            capacity=block.capacity,
            free_usable=block.free_usable,
            health=zone_health.value,
        )

    if mismatches:
        blocks = sorted(mismatches)
        await write_event(
            session,
            site_id=site.id,
            organization_id=site.organization_id,
            draft=EventDraft(
                type=EventType.INGEST_INCONSISTENT,
                occurred_at=now,
                reason=IngestInconsistencyReason.SUM_MISMATCH.value,
                zone_slug=(
                    zone_mismatch_slugs[0]
                    if site_consistent and len(zone_mismatch_slugs) == 1
                    else None
                ),
                figures=mismatches,
                # Same set of inconsistent blocks -> collapses (D11).
                fingerprint=hashlib.sha256("|".join(blocks).encode()).hexdigest(),
                details={"blocks": blocks},
            ),
        )

    # 8. Inline evaluation (D7, BF-16). A failing evaluator must not make the
    # site go dark: the snapshot is kept, the engine outcome rolled back.
    await session.flush()
    try:
        async with session.begin_nested():
            view = await evaluator.evaluate_site(session, site.id, clock)
    except Exception as exc:
        logger.error(
            f"Freespace intake: evaluation of site {site.id} failed: {exc}\n"
            f"{traceback.format_exc()}"
        )
        warnings.add("Evaluation failed; the snapshot was stored")
        await session.refresh(state_row)
        view = evaluator.EvaluatedSiteView(
            state=EngineState(state_row.state),
            recommended_zone_slug=None,
            stale=bool(state_row.stale),
        )

    await session.commit()
    await evaluator.enqueue_fanouts(view.fanout_event_ids)

    return IntakeResult(
        accepted=True,
        received_at=now,
        state=view.state,
        stale=view.stale,
        recommended_zone_slug=view.recommended_zone_slug,
        discovered_zones=discovered,
        created_zones=tuple(created),
        warnings=warnings.result(),
        fanout_event_ids=tuple(view.fanout_event_ids),
    )


__all__ = [
    "OUT_OF_ORDER",
    "ClockSkewError",
    "IntakeRejectedError",
    "IntakeResult",
    "SiteMismatchError",
    "SiteNotReadyError",
    "ingest_snapshot",
]
