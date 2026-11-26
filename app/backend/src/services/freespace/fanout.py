"""
Advisory fan-out (BF-52, BF-58 - BF-60, BF-63 - BF-67, D10). OWNER: M7.

Runs in the ARQ worker (``src/workers/freespace_tasks.fanout_advisory_task``),
one chunk of at most ``FANOUT_CHUNK_SIZE`` devices per job; the task wrapper
re-enqueues the job when ``FanoutResult.reenqueue_in_s`` is set.

The one property that matters most: a phone may MISS an advisory, but never
gets it twice (BF-52, BT-02).

Per call (one chunk), in separate short transactions:

1. **Claim** (event row ``FOR UPDATE``): skip a terminal event; take the
   fan-out lease (below); mark RUNNING (``fanout_started_at`` once); an
   unmanaged site sends nothing (BF-61). Re-claim retry rows whose backoff
   has elapsed, select up to ``chunk_size`` target devices WITHOUT a
   ``push_send`` row for the event (BF-67 exclusions in SQL), run the BF-58
   checks for the chunk in SQL (``limits.py``) - after locking the chunk's
   device rows, so a concurrent fan-out of another event for the same phone
   is serialised (BT-08) - and insert one row per
   device: the reason for suppressed ones (no FCM call, never queued for
   later - BF-59), ``PENDING`` for the rest. **COMMIT** - only then is FCM
   called. A crash after this commit costs those devices the advisory; it
   can never cause a second send, because a resumed run skips every device
   with a row and never re-sends a ``PENDING`` row without a retry marker.
2. **Send** the claimed rows, ``FCM_MAX_IN_FLIGHT`` concurrent requests.
3. **Record** outcomes in bulk: SENT ("accepted by FCM", BF-69), TOKEN_INVALID
   (+ ``device.token_invalidated_at``), SEND_FAILED, retryable ->
   ``PENDING`` + ``RETRY:<code>`` marker (FCM said no, so one more send is
   safe), AUTH_FAILURE -> stop. COMMIT.
4. **Continue / finish**: a full chunk -> re-enqueue now (storing the retry
   backoff first when it had retryable answers, so the next chunk does not
   re-claim those rows early); retry rows ->
   re-enqueue after ``max(Retry-After, exponential backoff)`` until 5 min
   after the fan-out started or the message expired (whichever first), then
   SEND_FAILED (BF-66); otherwise finish: rows left PENDING by a crashed run
   -> SEND_FAILED / UNKNOWN_AFTER_CRASH, counts, FCM latency, start/finish
   on the event (BF-62) and, under the site row lock,
   ``engine.on_fanout_completed`` (BF-54).

**Lease.** ``site_event.details["fanout"]["lease"]`` (owner + expiry, set
under the event row lock) lets only one run work on an event at a time, so a
duplicate job (tick recovery, ARQ retry) exits at once instead of racing the
retry claims or finishing the event while another run is still sending. A
crashed holder's lease lapses after ``LEASE_S`` (the ARQ job timeout plus a
margin); the engine tick then re-enqueues the event (``recover_stuck_fanouts``).
At-most-once does NOT depend on the lease - it rests on the unique
``push_send (event_id, device_id)`` row committed before the send.

Auth failure (401/403 / unusable credentials): the fan-out stops, the event
is marked FAILED, an ``FCM_ERROR / AUTH_FAILURE`` event is written and the
condition is recorded for operator alerts (BF-82) through
``record_fcm_auth_failure`` (see "Alert hook" below).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import math
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.freespace import (
    FANOUT_CHUNK_SIZE,
    FANOUT_STUCK_AFTER_S,
    FCM_MAX_IN_FLIGHT,
    FCM_RETRY_WINDOW_S,
    SEND_ERROR_CLIENT,
    AdvisoryType,
    DeviceOutcome,
    EventType,
    FanoutStatus,
    FcmErrorReason,
    SuppressionReason,
)
from src.crud import freespace_push_send as sends
from src.logger.logger import Logger as logger
from src.models.site import Site
from src.models.site_event import SiteEvent
from src.services.freespace import engine as engine_module
from src.services.freespace.clock import Clock, ensure_utc
from src.services.freespace.deployment_settings import get_deployment_settings
from src.services.freespace.evaluator import SessionFactory
from src.services.freespace.events import write_event
from src.services.freespace.fcm import (
    FcmClient,
    FcmResultKind,
    FcmSendResult,
    build_data_payload,
    build_message,
)
from src.services.freespace.limits import (
    DeviceCheckInput,
    evaluate_device_checks,
    resolve_limit_policy,
)
from src.services.freespace.loaders import (
    apply_engine_state,
    engine_state_from_row,
    load_engine_state_row,
    site_settings_from_row,
)
from src.services.freespace.redis_client import get_redis
from src.services.freespace.types import EventDraft


# Event types that fan out to device tokens.
FANOUT_EVENT_TYPES: frozenset[str] = frozenset(
    {EventType.ADVISORY.value, EventType.TEST_PUSH.value}
)
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {FanoutStatus.COMPLETED.value, FanoutStatus.FAILED.value}
)
# Worker job_timeout (300 s) + margin: a lease older than this is dead.
LEASE_S = 330
# Exponential backoff for retryable FCM answers (BF-66), seconds.
RETRY_BASE_S = 5.0
RETRY_MAX_S = 60.0
# Redis key recording the last FCM auth failure for operator alerts (M9).
REDIS_FCM_AUTH_FAILURE_KEY = "freespace:fcm:auth_failure"

ERROR_EXPIRED = "EXPIRED"
ERROR_RETRY_WINDOW = "RETRY_WINDOW_EXHAUSTED"
ERROR_FANOUT_STOPPED = "FANOUT_STOPPED"
ERROR_CLIENT = SEND_ERROR_CLIENT  # acceptance unknown: counted, never retried


@dataclass(frozen=True)
class FanoutResult:
    """Outcome of one ``run_fanout`` call (one chunk).

    ``reenqueue_in_s``: when not None the task wrapper enqueues another
    ``fanout_advisory_task`` for the same event with ``_defer_by`` this many
    seconds (0 = immediately: more devices remain; > 0 = retry backoff).
    ``counts``: per-``DeviceOutcome`` totals so far for the event.
    """

    event_id: uuid.UUID
    status: FanoutStatus
    reenqueue_in_s: float | None = None
    processed: int = 0
    counts: dict[str, int] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# Alert hook (BF-82, for M9)
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FcmAuthFailure:
    """An FCM credential failure that stopped a fan-out (BF-66, BF-82)."""

    occurred_at: datetime
    organization_id: uuid.UUID
    site_id: uuid.UUID
    site_slug: str
    event_id: uuid.UUID  # the advisory whose fan-out stopped
    fcm_error_event_id: uuid.UUID  # the FCM_ERROR site_event
    error_code: str | None
    http_status: int | None


FcmAuthFailureHook = Callable[[FcmAuthFailure], Awaitable[None]]
_auth_failure_hooks: list[FcmAuthFailureHook] = []


def register_fcm_auth_failure_hook(hook: FcmAuthFailureHook) -> None:
    """M9: register a coroutine called (after commit) on every FCM auth
    failure. Exceptions in hooks are logged and swallowed."""
    if hook not in _auth_failure_hooks:
        _auth_failure_hooks.append(hook)


def unregister_fcm_auth_failure_hook(hook: FcmAuthFailureHook) -> None:
    if hook in _auth_failure_hooks:
        _auth_failure_hooks.remove(hook)


async def record_fcm_auth_failure(failure: FcmAuthFailure) -> None:
    """Record the condition for operator alerts: writes JSON to Redis key
    ``REDIS_FCM_AUTH_FAILURE_KEY`` (no expiry; M9 may read and clear it) and
    calls every registered hook. Fails open. The durable record is the
    ``FCM_ERROR / AUTH_FAILURE`` site_event."""
    redis = get_redis()
    if redis is not None:
        try:
            await redis.set(
                REDIS_FCM_AUTH_FAILURE_KEY,
                json.dumps(
                    {
                        "occurredAt": failure.occurred_at.isoformat(),
                        "organizationId": str(failure.organization_id),
                        "siteId": failure.site_slug,
                        "eventId": str(failure.event_id),
                        "fcmErrorEventId": str(failure.fcm_error_event_id),
                        "errorCode": failure.error_code,
                        "httpStatus": failure.http_status,
                    }
                ),
            )
        except Exception as exc:  # alerts are best-effort
            logger.warning(f"Freespace: could not record FCM auth failure: {exc}")
    for hook in list(_auth_failure_hooks):
        try:
            await hook(failure)
        except Exception as exc:  # a broken hook must not break the fan-out
            logger.error(f"Freespace: FCM auth-failure hook failed: {exc}")


async def write_fcm_error_event(
    session: AsyncSession,
    *,
    site_id: uuid.UUID,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    result: FcmSendResult,
    now: datetime,
    reason: str | None = None,
    advisory_type: AdvisoryType | None = None,
    cycle_id: uuid.UUID | None = None,
    accepted_by_fcm: int = 0,
) -> uuid.UUID:
    """Write the ``FCM_ERROR`` event of a credential failure (BF-66) that hit
    the send for ``event_id`` (an advisory, test push or announcement). Flush
    only; after the caller commits it calls ``record_fcm_auth_failure`` with
    the returned id (BF-82). Used by the fan-out and the back-office pushes."""
    draft = EventDraft(
        type=EventType.FCM_ERROR,
        occurred_at=now,
        reason=reason or FcmErrorReason.AUTH_FAILURE.value,
        advisory_type=advisory_type,
        cycle_id=cycle_id,
        details={
            "eventId": str(event_id),
            "errorCode": result.error_code,
            "httpStatus": result.http_status,
            "acceptedByFcm": accepted_by_fcm,
        },
    )
    row = await write_event(
        session,
        site_id=site_id,
        organization_id=organization_id,
        draft=draft,
        collapse=False,
    )
    return row.id


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


def _fanout_meta(event: SiteEvent) -> dict[str, Any]:
    details = event.details or {}
    meta = details.get("fanout") if isinstance(details, Mapping) else None
    return dict(meta) if isinstance(meta, Mapping) else {}


def _set_fanout_meta(event: SiteEvent, meta: Mapping[str, Any]) -> None:
    details = dict(event.details or {})
    details["fanout"] = dict(meta)
    event.details = details  # reassign: plain JSON column, no mutation tracking


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return ensure_utc(datetime.fromisoformat(str(value)))
    except ValueError:
        return None


def _lease_active(meta: Mapping[str, Any], now: datetime) -> bool:
    until = _parse_dt(meta.get("leaseUntil"))
    return bool(meta.get("lease")) and until is not None and until > now


def _event_occupancy_pct(event: SiteEvent) -> int | None:
    details = event.details or {}
    for value in (
        details.get("occupancyPct") if isinstance(details, Mapping) else None,
        ((event.figures or {}).get("site") or {}).get("occupancyPct"),
    ):
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return None


def _event_occupancy_exact(event: SiteEvent) -> float | None:
    details = event.details or {}
    value = details.get("occupancyExact") if isinstance(details, Mapping) else None
    if value is None:
        pct = _event_occupancy_pct(event)
        return float(pct) if pct is not None else None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _event_top_zones(event: SiteEvent) -> tuple[str, ...]:
    details = event.details or {}
    raw = details.get("topZones") if isinstance(details, Mapping) else None
    if isinstance(raw, (list, tuple)):
        return tuple(str(z) for z in raw)
    return ()


def _expires_at(event: SiteEvent, site: Site) -> datetime:
    """The advisory goes stale ``push_expiry_s`` after it was decided."""
    return ensure_utc(event.occurred_at) + timedelta(seconds=int(site.push_expiry_s))


def _retry_deadline(event: SiteEvent, site: Site) -> datetime:
    started = ensure_utc(event.fanout_started_at or event.occurred_at)
    return min(
        started + timedelta(seconds=FCM_RETRY_WINDOW_S), _expires_at(event, site)
    )


async def _load_event(
    session: AsyncSession, event_id: uuid.UUID, *, for_update: bool
) -> SiteEvent | None:
    query = select(SiteEvent).where(SiteEvent.id == event_id)
    if for_update:
        query = query.with_for_update()
    return (await session.execute(query)).scalars().first()


async def _load_site(session: AsyncSession, site_id: uuid.UUID) -> Site | None:
    return (
        (await session.execute(select(Site).where(Site.id == site_id)))
        .scalars()
        .first()
    )


@dataclass
class _Claim:
    """What phase 1 handed to phase 2."""

    lease: str
    status: FanoutStatus
    finish: FanoutStatus | None = None  # finish right away with this status
    finish_reason: str | None = None
    sends: list[sends.ClaimedSend] = field(default_factory=list)
    new_devices: int = 0
    retried: int = 0
    chunk_full: bool = False
    suppressed: int = 0
    payload: dict[str, Any] = field(default_factory=dict)
    exit_early: FanoutResult | None = None


# ─────────────────────────────────────────────────────────────
# Phase 1: claim (commit BEFORE any FCM call)
# ─────────────────────────────────────────────────────────────


async def _claim_chunk(
    session: AsyncSession, event_id: uuid.UUID, now: datetime, chunk_size: int
) -> _Claim:
    lease = uuid.uuid4().hex
    event = await _load_event(session, event_id, for_update=True)
    if event is None:
        logger.warning(f"Freespace fan-out: event {event_id} not found")
        return _Claim(
            lease="",
            status=FanoutStatus.FAILED,
            exit_early=FanoutResult(event_id=event_id, status=FanoutStatus.FAILED),
        )
    if event.type not in FANOUT_EVENT_TYPES or event.fanout_status is None:
        return _Claim(
            lease="",
            status=FanoutStatus.COMPLETED,
            exit_early=FanoutResult(
                event_id=event_id,
                status=FanoutStatus(event.fanout_status or FanoutStatus.COMPLETED),
                counts=dict(event.counts or {}),
            ),
        )
    if event.fanout_status in TERMINAL_STATUSES:
        return _Claim(
            lease="",
            status=FanoutStatus(event.fanout_status),
            exit_early=FanoutResult(
                event_id=event_id,
                status=FanoutStatus(event.fanout_status),
                counts=dict(event.counts or {}),
            ),
        )

    meta = _fanout_meta(event)
    if _lease_active(meta, now):
        # Another run is working on this event; it re-enqueues itself.
        return _Claim(
            lease="",
            status=FanoutStatus.RUNNING,
            exit_early=FanoutResult(event_id=event_id, status=FanoutStatus.RUNNING),
        )
    retry_at = _parse_dt(meta.get("retryAt"))

    site = await _load_site(session, event.site_id)
    claim = _Claim(lease=lease, status=FanoutStatus.RUNNING)
    if event.fanout_started_at is None:
        event.fanout_started_at = now
    event.fanout_status = FanoutStatus.RUNNING.value
    meta.update(lease=lease, leaseUntil=(now + timedelta(seconds=LEASE_S)).isoformat())
    _set_fanout_meta(event, meta)

    advisory_type = AdvisoryType(event.advisory_type or AdvisoryType.TEST)
    if site is None or site.deleted_time is not None:
        claim.finish, claim.finish_reason = FanoutStatus.FAILED, "SITE_DELETED"
        await session.commit()
        return claim
    if not site.managed and advisory_type != AdvisoryType.TEST:
        # BF-61: nothing is ever sent for an unmanaged site.
        claim.finish = FanoutStatus.COMPLETED
        claim.finish_reason = SuppressionReason.UNMANAGED.value
        await session.commit()
        return claim

    expired = now >= _expires_at(event, site)

    # Retry rows whose backoff has elapsed (they passed the checks already).
    if not expired and (retry_at is None or now >= retry_at):
        claim.sends.extend(
            await sends.claim_retry_rows(session, event.id, limit=chunk_size)
        )
        claim.retried = len(claim.sends)

    # New devices.
    targets = await sends.select_unprocessed_targets(
        session, event_id=event.id, site_id=site.id, limit=chunk_size
    )
    claim.new_devices = len(targets)
    claim.chunk_full = len(targets) >= chunk_size
    if targets:
        settings = site_settings_from_row(site)
        policy = resolve_limit_policy(await get_deployment_settings(session), settings)
        if advisory_type != AdvisoryType.TEST:
            # BF-63 / BT-08: serialise claims of OTHER events for the same
            # phones, so this claim's history read sees their committed
            # PENDING rows (see ``sends.lock_devices``).
            await sends.lock_devices(session, [t.device_id for t in targets])
        reasons = await evaluate_device_checks(
            session,
            [DeviceCheckInput(t.device_id, t.notifications_enabled) for t in targets],
            site=settings,
            advisory_type=advisory_type,
            fingerprint=event.fingerprint or "",
            cycle_id=event.cycle_id,
            event_id=event.id,
            policy=policy,
            now=now,
        )
        outcomes: dict[uuid.UUID, tuple[str, str | None]] = {}
        for target in targets:
            reason = reasons.get(target.device_id)
            if reason is not None:
                outcomes[target.device_id] = (reason.value, None)
                claim.suppressed += 1
            elif expired:
                # Stale guidance is worse than none (BF-59): never sent late.
                outcomes[target.device_id] = (
                    DeviceOutcome.SEND_FAILED.value,
                    ERROR_EXPIRED,
                )
            else:
                outcomes[target.device_id] = (DeviceOutcome.PENDING.value, None)
        row_ids = await sends.insert_send_rows(
            session,
            organization_id=site.organization_id,
            event_id=event.id,
            site_id=site.id,
            advisory_type=advisory_type.value,
            fingerprint=event.fingerprint or "",
            queued_at=now,
            outcomes=outcomes,
        )
        for target in targets:
            if outcomes[target.device_id][0] == DeviceOutcome.PENDING.value:
                claim.sends.append(
                    sends.ClaimedSend(
                        row_id=row_ids[target.device_id],
                        device_id=target.device_id,
                        fcm_token=target.fcm_token,
                    )
                )
    # Retry rows left for a later run (not re-claimed above), from this or
    # an earlier chunk: they keep the fan-out open until the retry deadline.
    retry_waiting = await sends.count_retry_rows(session, event.id)

    claim.payload = {
        "title": event.rendered_title or "",
        "body": event.rendered_body or "",
        "advisory_type": advisory_type,
        "site_slug": site.slug,
        "recommended_zone_slug": event.recommended_zone_slug,
        "occupancy_pct": _event_occupancy_pct(event),
        "event_id": str(event.id),
        "expires_at": _expires_at(event, site),
        "retry_deadline": _retry_deadline(event, site),
        "retry_at": retry_at,
        "retry_attempt": int(meta.get("retryAttempt", 0) or 0),
        "retry_wake_scheduled": bool(meta.get("retryWake")),
        "retry_waiting": retry_waiting,
        "expired": expired,
    }
    # THE at-most-once commit: rows exist before FCM is called.
    await session.commit()
    return claim


# ─────────────────────────────────────────────────────────────
# Phase 2: send
# ─────────────────────────────────────────────────────────────


async def _send_claimed(
    fcm: FcmClient,
    claimed: Sequence[sends.ClaimedSend],
    payload: Mapping[str, Any],
    now: datetime,
) -> list[FcmSendResult]:
    """One ``messages:send`` per token, at most ``FCM_MAX_IN_FLIGHT`` at once.

    ``now`` is the actual send time (``sentAt`` in the data payload, BF-65).

    TTL rule (BF-65, BF-66): the expiry is measured from the DECISION instant
    (``event.occurred_at + push_expiry_s``), not from the send. A later chunk
    or a retry therefore carries the REMAINING lifetime only, so guidance is
    never shown later than ``push_expiry_s`` after it was decided, and
    ``apns-expiration`` (= sentAt + ttl) is the same instant for every send of
    the advisory. With less than one whole second left the advisory has
    expired: no FCM call, outcome SEND_FAILED / EXPIRED.
    """
    semaphore = asyncio.Semaphore(FCM_MAX_IN_FLIGHT)
    ttl_s = math.floor((payload["expires_at"] - now).total_seconds())
    if ttl_s < 1:
        return [
            FcmSendResult(kind=FcmResultKind.FAILED, error_code=ERROR_EXPIRED)
            for _ in claimed
        ]
    data = build_data_payload(
        message_type=payload["advisory_type"],
        site_slug=payload["site_slug"],
        recommended_zone_slug=payload["recommended_zone_slug"],
        occupancy_pct=payload["occupancy_pct"],
        event_id=payload["event_id"],
        sent_at=now,
    )

    async def one(item: sends.ClaimedSend) -> FcmSendResult:
        message = build_message(
            title=payload["title"],
            body=payload["body"],
            data=data,
            site_slug=payload["site_slug"],
            sent_at=now,
            ttl_s=ttl_s,
            token=item.fcm_token,
        )
        async with semaphore:
            try:
                return await fcm.send(message)
            except Exception as exc:  # unknown whether FCM got it: never retry
                logger.error(
                    f"Freespace fan-out: FCM client raised {type(exc).__name__}"
                )
                return FcmSendResult(kind=FcmResultKind.FAILED, error_code=ERROR_CLIENT)

    return list(await asyncio.gather(*(one(item) for item in claimed)))


# ─────────────────────────────────────────────────────────────
# Phase 3: record outcomes
# ─────────────────────────────────────────────────────────────


@dataclass
class _Recorded:
    auth_failure: FcmSendResult | None = None
    retry_after_s: float | None = None
    retryable: int = 0
    latency_sum_ms: float = 0.0
    latency_count: int = 0


async def _record_outcomes(
    session: AsyncSession,
    event_id: uuid.UUID,
    claimed: Sequence[sends.ClaimedSend],
    results: Sequence[FcmSendResult],
    *,
    now: datetime,
    retry_deadline: datetime,
) -> _Recorded:
    recorded = _Recorded()
    updates: list[tuple[uuid.UUID, str, str | None, datetime | None]] = []
    invalid: list[tuple[uuid.UUID, str]] = []
    can_retry = now < retry_deadline
    for item, result in zip(claimed, results, strict=True):
        if result.http_status is not None:
            recorded.latency_sum_ms += float(result.latency_ms)
            recorded.latency_count += 1
        if result.kind == FcmResultKind.ACCEPTED:
            updates.append((item.row_id, DeviceOutcome.SENT.value, None, now))
        elif result.kind == FcmResultKind.TOKEN_INVALID:
            updates.append(
                (
                    item.row_id,
                    DeviceOutcome.TOKEN_INVALID.value,
                    result.error_code,
                    None,
                )
            )
            invalid.append((item.device_id, item.fcm_token))
        elif result.kind == FcmResultKind.RETRYABLE and can_retry:
            code = (sends.RETRY_PREFIX + (result.error_code or "RETRYABLE"))[:64]
            updates.append((item.row_id, DeviceOutcome.PENDING.value, code, None))
            recorded.retryable += 1
            if result.retry_after_s is not None:
                recorded.retry_after_s = max(
                    recorded.retry_after_s or 0.0, float(result.retry_after_s)
                )
        else:
            if (
                result.kind == FcmResultKind.AUTH_FAILURE
                and recorded.auth_failure is None
            ):
                recorded.auth_failure = result
            updates.append(
                (
                    item.row_id,
                    DeviceOutcome.SEND_FAILED.value,
                    result.error_code
                    or (
                        ERROR_RETRY_WINDOW
                        if result.kind == FcmResultKind.RETRYABLE
                        else None
                    ),
                    None,
                )
            )
    # Lock order everywhere: event row first, then device rows (as the claim).
    event = await _load_event(session, event_id, for_update=True)
    # Retry rows keep outcome PENDING, so set_outcomes' "still PENDING" guard
    # applies to them too.
    await sends.set_outcomes(session, updates)
    await sends.invalidate_tokens(session, invalid, now)

    if event is not None:
        meta = _fanout_meta(event)
        meta["latencySumMs"] = (
            float(meta.get("latencySumMs", 0.0)) + recorded.latency_sum_ms
        )
        meta["latencyCount"] = int(meta.get("latencyCount", 0)) + recorded.latency_count
        _set_fanout_meta(event, meta)
    await session.commit()
    return recorded


# ─────────────────────────────────────────────────────────────
# Phase 4: finish
# ─────────────────────────────────────────────────────────────


async def _release_lease(
    session: AsyncSession,
    event_id: uuid.UUID,
    lease: str,
    *,
    retry_at: datetime | None = None,
    attempt: int | None = None,
    retry_wake: bool | None = None,
) -> None:
    """Free the lease; optionally store the retry backoff (``retryAt``,
    ``retryAttempt``) and whether a job is already deferred to ``retryAt``
    (``retryWake``)."""
    event = await _load_event(session, event_id, for_update=True)
    if event is None:
        return
    meta = _fanout_meta(event)
    if meta.get("lease") == lease:
        meta.pop("lease", None)
        meta.pop("leaseUntil", None)
    if retry_at is not None:
        meta["retryAt"] = retry_at.isoformat()
    if attempt is not None:
        meta["retryAttempt"] = attempt
    if retry_wake is not None:
        meta["retryWake"] = retry_wake
    _set_fanout_meta(event, meta)
    await session.commit()


async def _finish(
    session: AsyncSession,
    event_id: uuid.UUID,
    lease: str,
    *,
    status: FanoutStatus,
    now: datetime,
    reason: str | None = None,
    auth_failure: FcmSendResult | None = None,
) -> FanoutResult:
    """Write BF-62 bookkeeping, apply BF-54 under the site lock, commit."""
    event = await _load_event(session, event_id, for_update=True)
    if event is None:
        return FanoutResult(event_id=event_id, status=FanoutStatus.FAILED)
    if event.fanout_status in TERMINAL_STATUSES:
        await session.commit()
        return FanoutResult(
            event_id=event_id,
            status=FanoutStatus(event.fanout_status),
            counts=dict(event.counts or {}),
        )
    meta = _fanout_meta(event)
    if meta.get("lease") not in (None, lease):
        await session.commit()  # someone else took over
        return FanoutResult(event_id=event_id, status=FanoutStatus.RUNNING)

    # Anything still waiting for a retry will not get one (BF-66).
    await sends.fail_retry_rows(
        session,
        event.id,
        error_code=(
            ERROR_FANOUT_STOPPED
            if status == FanoutStatus.FAILED
            else ERROR_RETRY_WINDOW
        ),
    )
    # Rows still PENDING without a retry marker were claimed by a run that
    # died before recording FCM's answer (BF-52): never re-sent, still counted
    # for the limits, reported as SEND_FAILED / UNKNOWN_AFTER_CRASH so the
    # counts hold only real outcomes (BF-62). No live run can still own them:
    # we hold the event row lock and the lease is ours or free, and a run
    # whose lease lapsed (LEASE_S) has been killed by the job timeout.
    await sends.fail_unknown_pending_rows(session, event.id)
    counts = await sends.outcome_counts(session, event.id)

    for key in ("lease", "leaseUntil", "retryAt", "retryWake"):
        meta.pop(key, None)
    if reason is not None:
        meta["stopReason"] = reason
    latency_count = int(meta.get("latencyCount", 0))
    _set_fanout_meta(event, meta)
    event.counts = counts
    event.fanout_status = status.value
    if event.fanout_started_at is None:
        event.fanout_started_at = now
    event.fanout_finished_at = now
    event.fcm_latency_ms = (
        round(float(meta.get("latencySumMs", 0.0)) / latency_count)
        if latency_count
        else None
    )
    if reason == SuppressionReason.UNMANAGED.value:
        event.reason = reason

    fcm_error_event_id: uuid.UUID | None = None
    if auth_failure is not None:
        fcm_error_event_id = await write_fcm_error_event(
            session,
            site_id=event.site_id,
            organization_id=event.organization_id,
            event_id=event.id,
            result=auth_failure,
            now=now,
            reason=reason,
            advisory_type=(
                AdvisoryType(event.advisory_type) if event.advisory_type else None
            ),
            cycle_id=event.cycle_id,
            accepted_by_fcm=counts.get(DeviceOutcome.SENT.value, 0),
        )

    sent_count = counts.get(DeviceOutcome.SENT.value, 0)
    state_row = await load_engine_state_row(session, event.site_id, for_update=True)
    if state_row is not None and event.type == EventType.ADVISORY.value:
        try:
            new_state = engine_module.on_fanout_completed(
                engine_state_from_row(state_row),
                event_id=event.id,
                cycle_id=event.cycle_id,
                advisory_type=AdvisoryType(event.advisory_type or AdvisoryType.TEST),
                fingerprint=event.fingerprint or "",
                recommended_zone_slug=event.recommended_zone_slug,
                top_zones=_event_top_zones(event),
                occupancy_exact=_event_occupancy_exact(event),
                sent_count=sent_count,
                now=now,
            )
            apply_engine_state(state_row, new_state)
        except NotImplementedError:
            logger.warning(
                "Freespace fan-out: engine.on_fanout_completed not implemented"
            )

    site_slug = ""
    if auth_failure is not None:
        site = await _load_site(session, event.site_id)
        site_slug = site.slug if site else ""
    organization_id, site_id = event.organization_id, event.site_id
    await session.commit()

    logger.info(
        f"Freespace fan-out {event_id} {status.value}: "
        f"{sent_count} accepted by FCM, counts={counts}"
    )
    if auth_failure is not None and fcm_error_event_id is not None:
        await record_fcm_auth_failure(
            FcmAuthFailure(
                occurred_at=now,
                organization_id=organization_id,
                site_id=site_id,
                site_slug=site_slug,
                event_id=event_id,
                fcm_error_event_id=fcm_error_event_id,
                error_code=auth_failure.error_code,
                http_status=auth_failure.http_status,
            )
        )
    return FanoutResult(event_id=event_id, status=status, counts=counts)


def _backoff_s(attempt: int, retry_after_s: float | None) -> float:
    exponential = min(RETRY_MAX_S, RETRY_BASE_S * (2 ** max(0, attempt - 1)))
    return max(exponential, retry_after_s or 0.0, 1.0)


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────


async def run_fanout(
    session_factory: SessionFactory,
    event_id: uuid.UUID,
    *,
    clock: Clock,
    fcm: FcmClient,
    chunk_size: int = FANOUT_CHUNK_SIZE,
) -> FanoutResult:
    """Process one chunk of the fan-out of advisory ``event_id`` (see module
    docstring). Idempotent and resumable: safe to call again for the same
    event at any time, including after a crash or concurrently (a second
    concurrent call must not send to any device twice). An event that is
    already COMPLETED/FAILED, or is not an advisory, returns immediately
    with that status and ``reenqueue_in_s=None``."""
    now = clock.now()
    async with session_factory() as session:
        try:
            claim = await _claim_chunk(session, event_id, now, chunk_size)
        except IntegrityError:
            # A concurrent run recorded some of these devices first. Our
            # transaction rolled back, nothing was sent: just try again.
            await session.rollback()
            logger.info(f"Freespace fan-out {event_id}: concurrent claim, retrying")
            return FanoutResult(
                event_id=event_id, status=FanoutStatus.RUNNING, reenqueue_in_s=1.0
            )
    if claim.exit_early is not None:
        return claim.exit_early

    try:
        if claim.finish is not None:
            async with session_factory() as session:
                return await _finish(
                    session,
                    event_id,
                    claim.lease,
                    status=claim.finish,
                    now=now,
                    reason=claim.finish_reason,
                )

        recorded = _Recorded()
        if claim.sends:
            sent_at = clock.now()  # the actual send time (sentAt, BF-65)
            results = await _send_claimed(fcm, claim.sends, claim.payload, sent_at)
            after = clock.now()
            async with session_factory() as session:
                recorded = await _record_outcomes(
                    session,
                    event_id,
                    claim.sends,
                    results,
                    now=after,
                    retry_deadline=claim.payload["retry_deadline"],
                )
        processed = claim.new_devices + claim.retried
        later = clock.now()

        if recorded.auth_failure is not None:
            async with session_factory() as session:
                return await _finish(
                    session,
                    event_id,
                    claim.lease,
                    status=FanoutStatus.FAILED,
                    now=later,
                    reason=FcmErrorReason.AUTH_FAILURE.value,
                    auth_failure=recorded.auth_failure,
                )

        deadline: datetime = claim.payload["retry_deadline"]
        stored_retry_at: datetime | None = claim.payload.get("retry_at")
        attempt = int(claim.payload.get("retry_attempt", 0))
        new_retry_at: datetime | None = None
        if recorded.retryable:
            # BF-66: back off (honouring Retry-After) before ANY run re-claims
            # these rows - also when more devices remain (chunk full).
            attempt += 1
            new_retry_at = later + timedelta(
                seconds=_backoff_s(attempt, recorded.retry_after_s)
            )
            if stored_retry_at is not None and stored_retry_at > new_retry_at:
                new_retry_at = stored_retry_at

        if claim.chunk_full:
            # More devices: next chunk now. It does not re-claim retry rows
            # before ``retryAt``; no job is deferred to ``retryAt`` yet
            # (``retryWake`` False), so the last chunk schedules the wake-up.
            async with session_factory() as session:
                await _release_lease(
                    session,
                    event_id,
                    claim.lease,
                    retry_at=new_retry_at,
                    attempt=attempt if new_retry_at is not None else None,
                    retry_wake=False if new_retry_at is not None else None,
                )
            return FanoutResult(
                event_id=event_id,
                status=FanoutStatus.RUNNING,
                reenqueue_in_s=0,
                processed=processed,
            )

        waiting = recorded.retryable + int(claim.payload.get("retry_waiting", 0))
        if waiting and later < deadline:
            if new_retry_at is not None:
                retry_at = new_retry_at
            else:
                retry_at = stored_retry_at or later
                if (
                    retry_at < deadline
                    and not claim.sends
                    and retry_at > later
                    and claim.payload.get("retry_wake_scheduled")
                ):
                    # Woken before the backoff elapsed (duplicate / recovery
                    # job): the job deferred to ``retryAt`` will continue.
                    async with session_factory() as session:
                        await _release_lease(session, event_id, claim.lease)
                    return FanoutResult(event_id=event_id, status=FanoutStatus.RUNNING)
            delay = max(0.0, (retry_at - later).total_seconds())
            if retry_at < deadline:
                async with session_factory() as session:
                    await _release_lease(
                        session,
                        event_id,
                        claim.lease,
                        retry_at=retry_at,
                        attempt=attempt,
                        retry_wake=True,
                    )
                return FanoutResult(
                    event_id=event_id,
                    status=FanoutStatus.RUNNING,
                    reenqueue_in_s=max(delay, 1.0),
                    processed=processed,
                )
            # The next try would fall past the deadline: give up now.

        async with session_factory() as session:
            result = await _finish(
                session, event_id, claim.lease, status=FanoutStatus.COMPLETED, now=later
            )
        return FanoutResult(
            event_id=result.event_id,
            status=result.status,
            processed=processed,
            counts=result.counts,
        )
    except BaseException:
        # Free the lease so a re-run (ARQ retry, tick) can resume at once.
        # Rows already written stay: a resumed run never re-sends them.
        try:
            async with session_factory() as session:
                await _release_lease(session, event_id, claim.lease)
        except Exception as exc:  # pragma: no cover - best effort
            logger.error(f"Freespace fan-out: lease release failed: {exc}")
        raise


async def fail_fanout_credentials_missing(
    session_factory: SessionFactory,
    event_id: uuid.UUID,
    *,
    clock: Clock,
) -> FanoutResult:
    """FCM is not configured (``get_fcm_client()`` raised): end the fan-out of
    ``event_id`` as FAILED through the normal finish path, so the engine's
    in-flight fields are released (BF-54) and the tick does not re-enqueue it,
    write an ``FCM_ERROR / CREDENTIALS_MISSING`` event and record the
    condition for the operator alert (BF-82). Nothing is sent."""
    now = clock.now()
    async with session_factory() as session:
        event = await _load_event(session, event_id, for_update=False)
        if event is None:
            return FanoutResult(event_id=event_id, status=FanoutStatus.FAILED)
        if event.type not in FANOUT_EVENT_TYPES or event.fanout_status is None:
            return FanoutResult(event_id=event_id, status=FanoutStatus.COMPLETED)
        reason = FcmErrorReason.CREDENTIALS_MISSING.value
        return await _finish(
            session,
            event_id,
            "",  # no lease taken: _finish accepts an unleased event
            status=FanoutStatus.FAILED,
            now=now,
            reason=reason,
            auth_failure=FcmSendResult(
                kind=FcmResultKind.AUTH_FAILURE, error_code=reason
            ),
        )


async def recover_stuck_fanouts(
    session: AsyncSession, now: datetime
) -> list[uuid.UUID]:
    """D7 recovery: ids of advisory events whose ``fanout_status`` is PENDING
    or RUNNING and whose ``occurred_at`` (PENDING) / ``fanout_started_at``
    (RUNNING) is older than ``FANOUT_STUCK_AFTER_S``. Read-only; the tick
    (M6) re-enqueues them with ``evaluator.enqueue_fanouts``.

    Events whose fan-out lease is still held by a live run are left out (that
    run re-enqueues itself). Re-enqueueing is always safe: ``run_fanout``
    never sends a device twice (rows committed before sending)."""
    now = ensure_utc(now)
    cutoff = now - timedelta(seconds=FANOUT_STUCK_AFTER_S)
    rows = (
        (
            await session.execute(
                select(SiteEvent)
                .where(
                    SiteEvent.type.in_(list(FANOUT_EVENT_TYPES)),
                    SiteEvent.fanout_status.in_(
                        [FanoutStatus.PENDING.value, FanoutStatus.RUNNING.value]
                    ),
                )
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    stuck: list[uuid.UUID] = []
    for event in rows:
        if event.fanout_status == FanoutStatus.PENDING.value:
            reference = event.occurred_at
        else:
            reference = event.fanout_started_at or event.occurred_at
        if ensure_utc(reference) > cutoff:
            continue
        if _lease_active(_fanout_meta(event), now):
            continue
        stuck.append(event.id)
    return stuck
