"""
Freespace ARQ tasks (D7, D10). Registered in ``src/workers/worker.py``.

* ``fanout_advisory_task(ctx, event_id)`` - one fan-out chunk; re-enqueues
  itself when ``FanoutResult.reenqueue_in_s`` is set. Body: M7
  (``fanout.run_fanout``).
* ``engine_tick(ctx)`` - hardcoded ARQ cron, every minute (BF-50, D7). Body:
  M6 (``evaluator.run_engine_tick``).

While the delegated functions are still stubs these wrappers log and return
``{"status": "not_implemented"}`` instead of raising, so the worker keeps
running. The wrappers themselves are foundation code; M6/M7 change only the
functions they delegate to.
"""

from __future__ import annotations

from typing import Any
import uuid

from src.constants.freespace import JOB_FANOUT_ADVISORY
from src.logger.logger import Logger as logger


def _session_factory(ctx: dict[str, Any]):
    factory = ctx.get("session_factory")
    if factory is None:
        raise RuntimeError("Database session factory not available")
    return factory


async def fanout_advisory_task(ctx: dict[str, Any], event_id: str) -> dict[str, Any]:
    """Fan out one chunk of advisory ``event_id`` (BF-52, D10)."""
    from src.services.freespace.clock import get_clock
    from src.services.freespace.fanout import (
        fail_fanout_credentials_missing,
        run_fanout,
    )
    from src.services.freespace.fcm import get_fcm_client

    try:
        fcm = get_fcm_client()
    except RuntimeError as exc:
        # FCM not configured: retrying cannot help. Fail the fan-out (releases
        # the engine's in-flight guard, FCM_ERROR event, operator alert).
        logger.error(f"Freespace fan-out {event_id}: FCM unavailable ({exc})")
        failed = await fail_fanout_credentials_missing(
            _session_factory(ctx), uuid.UUID(event_id), clock=await get_clock()
        )
        return {
            "status": failed.status.value,
            "event_id": event_id,
            "processed": 0,
            "reenqueued": False,
        }

    try:
        result = await run_fanout(
            _session_factory(ctx),
            uuid.UUID(event_id),
            clock=await get_clock(),
            fcm=fcm,
        )
    except NotImplementedError as exc:
        logger.warning(
            f"Freespace fan-out not implemented yet ({exc}); event {event_id} left pending"
        )
        return {"status": "not_implemented", "event_id": event_id}

    if result.reenqueue_in_s is not None:
        from src.services.tasks import task_queue

        kwargs: dict[str, Any] = {}
        if result.reenqueue_in_s > 0:
            kwargs["_defer_by"] = result.reenqueue_in_s
        await task_queue.enqueue_job(JOB_FANOUT_ADVISORY, event_id, **kwargs)

    return {
        "status": result.status.value,
        "event_id": event_id,
        "processed": result.processed,
        "reenqueued": result.reenqueue_in_s is not None,
    }


async def engine_tick(ctx: dict[str, Any]) -> dict[str, Any]:
    """Evaluate every site once (BF-50) and recover stuck fan-outs (D7)."""
    from src.services.freespace.clock import get_clock
    from src.services.freespace.evaluator import run_engine_tick

    try:
        result = await run_engine_tick(_session_factory(ctx), await get_clock())
    except NotImplementedError as exc:
        logger.debug(f"Freespace engine tick not implemented yet ({exc})")
        return {"status": "not_implemented"}

    return {
        "status": "ok",
        "sites_evaluated": result.sites_evaluated,
        "sites_failed": result.sites_failed,
        "fanouts_enqueued": result.fanouts_enqueued,
        "fanouts_recovered": result.fanouts_recovered,
    }
