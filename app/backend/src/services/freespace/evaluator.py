"""
Engine DB shell (D6, D7, BF-16, BF-50, BF-51). OWNER: M6.

Transaction contract
--------------------
``evaluate_site`` runs inside the CALLER's transaction and never commits:

1. ``SELECT ... FROM site_engine_state WHERE site_id = :id FOR UPDATE``
   (``loaders.load_engine_state_row(..., for_update=True)``) - the per-site
   lock of BF-51. It is held until the caller commits or rolls back.
2. Load settings, zones, snapshot and templates (``loaders.load_site_context``).
3. ``engine.evaluate(...)``.
4. Persist the new state (``loaders.apply_engine_state``) and the events
   (``events.write_events``); flush.
5. Return an ``EvaluatedSiteView``.

The caller then COMMITS and only afterwards calls
``enqueue_fanouts(view.fanout_event_ids)`` - a fan-out job must never run
before its event row is visible (BF-52: recorded before sent).

Intake (M3)::

    view = await evaluate_site(session, site.id, clock)
    await session.commit()
    await enqueue_fanouts(view.fanout_event_ids)

Tick (``run_engine_tick``): every live site, managed or not (shadow mode
needs its timers too, D7), each in its own session and transaction, so one
failing site never stops the others; then stuck fan-outs are re-enqueued and
the tick time is written to Redis ``REDIS_ENGINE_TICK_KEY``
(``freespace:engine_tick:last``, ISO-8601 UTC) for ``/health`` (BF-80).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.freespace import (
    JOB_FANOUT_ADVISORY,
    REDIS_ENGINE_TICK_KEY,
    EngineState,
    FanoutStatus,
)
from src.logger.logger import Logger as logger
from src.models.site import Site
from src.models.site_engine_state import SiteEngineState
from src.services.freespace import engine
from src.services.freespace.clock import Clock, ensure_utc
from src.services.freespace.events import write_event
from src.services.freespace.loaders import (
    apply_engine_state,
    engine_state_from_row,
    load_snapshot,
    load_templates,
    load_zone_configs,
    site_settings_from_row,
)
from src.services.freespace.redis_client import get_redis


SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@dataclass(frozen=True)
class EvaluatedSiteView:
    """What intake (BF-15 ``site`` block) and the tick need after evaluating."""

    state: EngineState
    recommended_zone_slug: str | None
    stale: bool
    fanout_event_ids: tuple[uuid.UUID, ...] = ()


@dataclass(frozen=True)
class TickResult:
    """Summary of one ``run_engine_tick``."""

    sites_evaluated: int = 0
    sites_failed: int = 0
    fanouts_enqueued: int = 0
    fanouts_recovered: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)


async def evaluate_site(
    session: AsyncSession, site_id: uuid.UUID, clock: Clock
) -> EvaluatedSiteView:
    """Evaluate one site under its row lock and persist the outcome (see the
    module docstring for the transaction contract). Raises ``LookupError``
    when the site has no engine-state row (deleted / never bootstrapped)."""
    # Never trust identity-map copies: the row lock is only useful if the
    # values we modify are the ones read under it (populate_existing).
    await session.flush()
    row = (
        (
            await session.execute(
                select(SiteEngineState)
                .where(SiteEngineState.site_id == site_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        raise LookupError(f"site {site_id} has no engine state row")
    site = (
        (
            await session.execute(
                select(Site)
                .where(Site.id == site_id, Site.deleted_time.is_(None))
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .first()
    )
    if site is None:
        raise LookupError(f"site {site_id} is not a live site")

    now = ensure_utc(clock.now())
    # BF-72: settings, zones and templates are read fresh on every evaluation.
    result = engine.evaluate(
        site_settings_from_row(site),
        await load_zone_configs(session, site_id),
        await load_snapshot(session, site_id),
        engine_state_from_row(row),
        await load_templates(session, site_id),
        now,
    )
    apply_engine_state(row, result.new_state)

    fanout_ids: list[uuid.UUID] = []
    for draft in result.events:
        written = await write_event(
            session,
            site_id=site.id,
            organization_id=site.organization_id,
            draft=draft,
        )
        if draft.fanout_status == FanoutStatus.PENDING:
            fanout_ids.append(written.id)
    await session.flush()

    return EvaluatedSiteView(
        state=result.new_state.state,
        recommended_zone_slug=result.availability.recommended_zone_slug,
        stale=result.availability.stale,
        fanout_event_ids=tuple(fanout_ids),
    )


async def enqueue_fanouts(event_ids: Sequence[uuid.UUID]) -> None:
    """Enqueue one ``fanout_advisory_task`` ARQ job per event id.

    Call AFTER the transaction that wrote the events has committed. Enqueue
    failures are logged and swallowed (``TaskQueue.enqueue_job`` already
    swallows): the engine tick re-enqueues fan-outs left PENDING (D7)."""
    from src.services.tasks import task_queue

    for event_id in event_ids:
        job_id = await task_queue.enqueue_job(JOB_FANOUT_ADVISORY, str(event_id))
        if job_id is None:
            logger.warning(
                f"Freespace: fan-out for event {event_id} not enqueued; tick will retry"
            )


async def run_engine_tick(session_factory: SessionFactory, clock: Clock) -> TickResult:
    """BF-50 / D7 once-a-minute tick (called by the ``engine_tick`` ARQ cron).

    For EVERY live site (managed or not - shadow mode needs timers too, D7):
    open a session, ``evaluate_site``, commit, ``enqueue_fanouts``; one
    site's failure must not stop the others. Then re-enqueue fan-outs stuck
    in PENDING/RUNNING (``fanout.recover_stuck_fanouts``). Finally write
    ``clock.now()`` (ISO) to Redis key ``REDIS_ENGINE_TICK_KEY`` for /health
    (BF-80) and run the operator alert checks (``alerts.run_alert_checks``,
    BF-82) on their own session."""
    started = ensure_utc(clock.now())
    errors: list[str] = []
    evaluated = failed = enqueued = recovered = 0

    try:
        async with session_factory() as session:
            site_ids = list(
                (
                    await session.execute(
                        select(Site.id)
                        .join(SiteEngineState, SiteEngineState.site_id == Site.id)
                        .where(Site.deleted_time.is_(None))
                        .order_by(Site.id)
                    )
                )
                .scalars()
                .all()
            )
    except Exception as exc:
        logger.error(f"Freespace engine tick: cannot list sites: {exc}")
        return TickResult(sites_failed=1, errors=(f"list sites: {exc}",))

    for site_id in site_ids:
        try:
            async with session_factory() as session:
                view = await evaluate_site(session, site_id, clock)
                await session.commit()
        except Exception as exc:  # one site never stops the others
            failed += 1
            errors.append(f"{site_id}: {type(exc).__name__}: {exc}")
            logger.error(f"Freespace engine tick: site {site_id} failed: {exc}")
            continue
        evaluated += 1
        await enqueue_fanouts(view.fanout_event_ids)
        enqueued += len(view.fanout_event_ids)

    try:
        from src.services.freespace.fanout import recover_stuck_fanouts

        async with session_factory() as session:
            stuck = await recover_stuck_fanouts(session, started)
        await enqueue_fanouts(stuck)
        recovered = len(stuck)
    except Exception as exc:
        errors.append(f"recover_stuck_fanouts: {type(exc).__name__}: {exc}")
        logger.error(f"Freespace engine tick: fan-out recovery failed: {exc}")

    redis = get_redis()
    if redis is not None:
        try:
            await redis.set(REDIS_ENGINE_TICK_KEY, started.isoformat())
        except Exception as exc:  # fail open (redis_client contract)
            logger.warning(f"Freespace engine tick: cannot record tick time: {exc}")

    # Operator alerts (BF-82) on their own session; never breaks the tick.
    try:
        from src.services.freespace.alerts import run_alert_checks

        async with session_factory() as session:
            await run_alert_checks(session, clock)
    except Exception as exc:
        errors.append(f"alerts: {type(exc).__name__}: {exc}")
        logger.error(f"Freespace engine tick: alert checks failed: {exc}")

    return TickResult(
        sites_evaluated=evaluated,
        sites_failed=failed,
        fanouts_enqueued=enqueued,
        fanouts_recovered=recovered,
        errors=tuple(errors),
    )
