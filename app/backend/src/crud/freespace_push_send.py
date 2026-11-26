"""
Send-history queries (``push_send``, BF-7, D10). OWNER: M7.

Every query here works on a whole fan-out chunk at once (BF-58 checks are
evaluated per chunk in SQL, never one query per device). Engine / worker code
paths: the event and site have been resolved already, so the queries filter
by ``event_id`` / ``site_id`` (which carry the tenant) rather than by user.

Row states (``outcome`` / ``error_code``):

* ``PENDING`` + ``error_code IS NULL``: claimed for a send and committed
  BEFORE the FCM call. If the worker died, FCM may or may not have accepted
  it, so such a row is NEVER sent again (at-most-once, BF-52).
* ``PENDING`` + ``error_code = 'RETRY:<code>'``: FCM answered 429/500/503, so
  it certainly did not accept the message; the row may be re-claimed
  (atomically, back to ``error_code IS NULL``) and sent once more (BF-66).
* ``SEND_FAILED`` + ``error_code = 'UNKNOWN_AFTER_CRASH'``: a claimed row
  that was still ``PENDING`` (no retry marker) when the fan-out finished, i.e.
  its run died between the claim commit and recording the FCM answer. FCM may
  have accepted it, so it still counts for DUPLICATE / COOLDOWN / DAILY_CAP
  and is never sent again (BF-52, BF-62).
* ``SEND_FAILED`` + ``CLIENT_ERROR`` / ``NO_RESPONSE_*``: the request may
  have reached FCM; same as UNKNOWN_AFTER_CRASH (counted, never retried).
* anything else: final.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import and_, case, exists, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.freespace import (
    LIMIT_COUNTED_ADVISORY_TYPES,
    LIMIT_COUNTED_OUTCOMES,
    SEND_ACCEPTANCE_UNKNOWN_CODES,
    SEND_ERROR_NO_RESPONSE_PREFIX,
    SEND_ERROR_UNKNOWN_AFTER_CRASH,
    DeviceOutcome,
)
from src.models.device import Device, DeviceSite
from src.models.push_send import PushSend
from src.models.site_event import SiteEvent
from src.services.freespace.clock import ensure_utc


RETRY_PREFIX = "RETRY:"
UNKNOWN_AFTER_CRASH = SEND_ERROR_UNKNOWN_AFTER_CRASH

# Which rows count for DUPLICATE / COOLDOWN / DAILY_CAP is defined ONCE, in
# ``src/constants/freespace.py`` (``send_counts_towards_limits``);
# ``_counted_outcome`` is its SQL form and must stay equivalent to it.
_COUNTED_TYPES: tuple[str, ...] = tuple(t.value for t in LIMIT_COUNTED_ADVISORY_TYPES)


def _counted_outcome() -> Any:
    """SQL form of ``send_counts_towards_limits``: SENT, PENDING, or
    SEND_FAILED whose acceptance by FCM is unknown (UNKNOWN_AFTER_CRASH,
    CLIENT_ERROR, NO_RESPONSE_*)."""
    return or_(
        PushSend.outcome.in_(LIMIT_COUNTED_OUTCOMES),
        and_(
            PushSend.outcome == DeviceOutcome.SEND_FAILED.value,
            or_(
                PushSend.error_code.in_(sorted(SEND_ACCEPTANCE_UNKNOWN_CODES)),
                PushSend.error_code.like(f"{SEND_ERROR_NO_RESPONSE_PREFIX}%"),
            ),
        ),
    )


@dataclass(frozen=True)
class TargetDevice:
    """A device selected for a fan-out chunk. ``fcm_token`` is personal data:
    never log it (BF-35)."""

    device_id: uuid.UUID
    fcm_token: str
    notifications_enabled: bool
    platform: str


@dataclass(frozen=True)
class ClaimedSend:
    """A ``push_send`` row in state PENDING that this run will send."""

    row_id: uuid.UUID
    device_id: uuid.UUID
    fcm_token: str


@dataclass(frozen=True)
class LimitUsage:
    """Per-device usage in the limit scope."""

    last_at: datetime | None
    today_count: int


def _utc(value: datetime | None) -> datetime | None:
    return ensure_utc(value) if value is not None else None


async def select_unprocessed_targets(
    session: AsyncSession, *, event_id: uuid.UUID, site_id: uuid.UUID, limit: int
) -> list[TargetDevice]:
    """BF-58 / BF-67 target set, minus devices already recorded for the event:
    devices that selected the site, are not tombstoned, have a token and no
    ``token_invalidated_at``. Ordered by device id (deterministic chunks)."""
    already = exists().where(
        PushSend.event_id == event_id, PushSend.device_id == Device.id
    )
    query = (
        select(
            Device.id,
            Device.fcm_token,
            Device.notifications_enabled,
            Device.platform,
        )
        .join(DeviceSite, DeviceSite.device_id == Device.id)
        .where(
            DeviceSite.site_id == site_id,
            Device.deleted_time.is_(None),
            Device.fcm_token.is_not(None),
            Device.token_invalidated_at.is_(None),
            ~already,
        )
        .order_by(Device.id)
        .limit(limit)
    )
    rows = (await session.execute(query)).all()
    return [
        TargetDevice(
            device_id=row[0],
            fcm_token=str(row[1]),
            notifications_enabled=bool(row[2]),
            platform=str(row[3]),
        )
        for row in rows
    ]


async def lock_devices(session: AsyncSession, device_ids: Sequence[uuid.UUID]) -> None:
    """Row-lock the devices of a fan-out chunk (``SELECT ... ORDER BY id FOR
    UPDATE``) before their send history is read (BF-63, BT-08).

    Two fan-outs of DIFFERENT events (two sites going ACTIVE in one tick, two
    zone advisories) may target the same phone. Without the lock both read the
    history under READ COMMITTED before either has committed its ``PENDING``
    row, and both pass COOLDOWN. With it, the second claim waits until the
    first commits and its next statement sees that row. Transaction-scoped
    (PgBouncer transaction pooling); ids are locked in id order, so two claims
    cannot deadlock on each other. No-op on SQLite."""
    if not device_ids:
        return
    await session.execute(
        select(Device.id)
        .where(Device.id.in_(sorted(set(device_ids))))
        .order_by(Device.id)
        .with_for_update()
    )


async def limit_usage(
    session: AsyncSession,
    device_ids: Sequence[uuid.UUID],
    *,
    site_id: uuid.UUID | None,
    since: datetime,
    day_start: datetime,
    exclude_event_id: uuid.UUID,
) -> dict[uuid.UUID, LimitUsage]:
    """Last counted advisory time and today's count per device, in ONE query.

    ``site_id`` None = scope ``DEVICE`` (all sites), else ``DEVICE_PER_SITE``.
    Only limit-counted types (TEST excluded, RECOVERY included, BF-60) and
    counted outcomes. ``since`` = min(day_start, now - cooldown)."""
    if not device_ids:
        return {}
    today_expr = func.sum(case((PushSend.queued_at >= day_start, 1), else_=0))
    conditions = [
        PushSend.device_id.in_(list(device_ids)),
        PushSend.advisory_type.in_(_COUNTED_TYPES),
        _counted_outcome(),
        PushSend.queued_at >= since,
        PushSend.event_id != exclude_event_id,
    ]
    if site_id is not None:
        conditions.append(PushSend.site_id == site_id)
    query = (
        select(PushSend.device_id, func.max(PushSend.queued_at), today_expr)
        .where(and_(*conditions))
        .group_by(PushSend.device_id)
    )
    result: dict[uuid.UUID, LimitUsage] = {}
    for device_id, last_at, today_count in (await session.execute(query)).all():
        result[device_id] = LimitUsage(
            last_at=_utc(last_at), today_count=int(today_count or 0)
        )
    return result


async def last_fingerprints(
    session: AsyncSession,
    device_ids: Sequence[uuid.UUID],
    *,
    site_id: uuid.UUID,
    cycle_id: uuid.UUID | None,
    since: datetime,
    exclude_event_id: uuid.UUID,
) -> dict[uuid.UUID, str]:
    """Fingerprint of each device's LAST advisory of this site that it
    (probably) received, in ONE query. Bounded to the site's current engine
    cycle (``cycle_id``; when None: rows since ``since``), so the same
    wording on a later morning is not a duplicate (BF-58 check 3)."""
    if not device_ids:
        return {}
    query = select(PushSend.device_id, PushSend.fingerprint, PushSend.queued_at).where(
        PushSend.device_id.in_(list(device_ids)),
        PushSend.site_id == site_id,
        PushSend.advisory_type.in_(_COUNTED_TYPES),
        _counted_outcome(),
        PushSend.event_id != exclude_event_id,
    )
    if cycle_id is not None:
        query = query.join(SiteEvent, SiteEvent.id == PushSend.event_id).where(
            SiteEvent.cycle_id == cycle_id
        )
    else:
        query = query.where(PushSend.queued_at >= since)
    latest: dict[uuid.UUID, tuple[datetime, str]] = {}
    for device_id, fingerprint, queued_at in (await session.execute(query)).all():
        queued = ensure_utc(queued_at)
        current = latest.get(device_id)
        if current is None or queued >= current[0]:
            latest[device_id] = (queued, fingerprint)
    return {device_id: value[1] for device_id, value in latest.items()}


async def insert_send_rows(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    site_id: uuid.UUID,
    advisory_type: str,
    fingerprint: str,
    queued_at: datetime,
    outcomes: Mapping[uuid.UUID, tuple[str, str | None]],
) -> dict[uuid.UUID, uuid.UUID]:
    """Bulk insert one row per device (``{device_id: (outcome, error_code)}``).
    Returns ``{device_id: row id}``. Flush only; the CALLER commits before
    any FCM call. A concurrent duplicate raises ``IntegrityError`` (unique
    ``(event_id, device_id)``)."""
    if not outcomes:
        return {}
    ids = {device_id: uuid.uuid4() for device_id in outcomes}
    await session.execute(
        insert(PushSend),
        [
            {
                "id": ids[device_id],
                "organization_id": organization_id,
                "event_id": event_id,
                "device_id": device_id,
                "site_id": site_id,
                "advisory_type": advisory_type,
                "fingerprint": fingerprint,
                "outcome": outcome,
                "queued_at": queued_at,
                "sent_at": None,
                "error_code": error_code,
            }
            for device_id, (outcome, error_code) in outcomes.items()
        ],
    )
    return ids


async def count_retry_rows(session: AsyncSession, event_id: uuid.UUID) -> int:
    """Rows waiting for a retry (``PENDING`` + ``RETRY:`` marker)."""
    query = select(func.count()).where(
        PushSend.event_id == event_id,
        PushSend.outcome == DeviceOutcome.PENDING.value,
        PushSend.error_code.like(f"{RETRY_PREFIX}%"),
    )
    return int((await session.execute(query)).scalar() or 0)


async def claim_retry_rows(
    session: AsyncSession, event_id: uuid.UUID, *, limit: int
) -> list[ClaimedSend]:
    """Atomically re-claim up to ``limit`` retry rows for one more send.

    The conditional UPDATE (``... AND error_code LIKE 'RETRY:%'``) is the
    claim: a concurrent claimer re-checks the predicate after the row lock
    and updates nothing, so a row is re-sent by one run only. Rows whose
    device lost / changed its token or was tombstoned in the meantime are
    not claimed (they stay retry rows and fail at the deadline). Flush only.
    """
    candidates = (
        await session.execute(
            select(PushSend.id, PushSend.device_id, Device.fcm_token)
            .join(Device, Device.id == PushSend.device_id)
            .where(
                PushSend.event_id == event_id,
                PushSend.outcome == DeviceOutcome.PENDING.value,
                PushSend.error_code.like(f"{RETRY_PREFIX}%"),
                Device.deleted_time.is_(None),
                Device.fcm_token.is_not(None),
                Device.token_invalidated_at.is_(None),
            )
            .order_by(PushSend.id)
            .limit(limit)
        )
    ).all()
    if not candidates:
        return []
    ids = [row[0] for row in candidates]
    claimed = (
        await session.execute(
            update(PushSend)
            .where(
                PushSend.id.in_(ids),
                PushSend.outcome == DeviceOutcome.PENDING.value,
                PushSend.error_code.like(f"{RETRY_PREFIX}%"),
            )
            .values(error_code=None)
            .returning(PushSend.id)
            .execution_options(synchronize_session=False)
        )
    ).scalars()
    claimed_ids = set(claimed)
    return [
        ClaimedSend(row_id=row[0], device_id=row[1], fcm_token=str(row[2]))
        for row in candidates
        if row[0] in claimed_ids
    ]


async def set_outcomes(
    session: AsyncSession,
    updates: Iterable[tuple[uuid.UUID, str, str | None, datetime | None]],
) -> None:
    """Bulk outcome update: ``(row id, outcome, error_code, sent_at)``,
    grouped into one UPDATE per distinct ``(outcome, error_code, sent_at)``.
    Only rows still PENDING are touched. Flush only."""
    groups: dict[tuple[str, str | None, datetime | None], list[uuid.UUID]] = {}
    for row_id, outcome, error_code, sent_at in updates:
        groups.setdefault((outcome, error_code, sent_at), []).append(row_id)
    for (outcome, error_code, sent_at), ids in groups.items():
        await session.execute(
            update(PushSend)
            .where(
                PushSend.id.in_(ids), PushSend.outcome == DeviceOutcome.PENDING.value
            )
            .values(outcome=outcome, error_code=error_code, sent_at=sent_at)
            .execution_options(synchronize_session=False)
        )


async def fail_retry_rows(
    session: AsyncSession, event_id: uuid.UUID, *, error_code: str
) -> int:
    """Retry window over (BF-66): every remaining retry row -> SEND_FAILED."""
    result = await session.execute(
        update(PushSend)
        .where(
            PushSend.event_id == event_id,
            PushSend.outcome == DeviceOutcome.PENDING.value,
            PushSend.error_code.like(f"{RETRY_PREFIX}%"),
        )
        .values(outcome=DeviceOutcome.SEND_FAILED.value, error_code=error_code)
        .execution_options(synchronize_session=False)
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def fail_unknown_pending_rows(session: AsyncSession, event_id: uuid.UUID) -> int:
    """At finish (BF-62): rows still ``PENDING`` without a retry marker were
    claimed by a run that died before recording FCM's answer. They become
    ``SEND_FAILED`` / ``UNKNOWN_AFTER_CRASH``: never re-sent, still counted
    for the limit checks. Call after ``fail_retry_rows``. Flush only."""
    result = await session.execute(
        update(PushSend)
        .where(
            PushSend.event_id == event_id,
            PushSend.outcome == DeviceOutcome.PENDING.value,
            or_(
                PushSend.error_code.is_(None),
                ~PushSend.error_code.like(f"{RETRY_PREFIX}%"),
            ),
        )
        .values(outcome=DeviceOutcome.SEND_FAILED.value, error_code=UNKNOWN_AFTER_CRASH)
        .execution_options(synchronize_session=False)
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def invalidate_tokens(
    session: AsyncSession,
    invalid: Iterable[tuple[uuid.UUID, str]],
    now: datetime,
) -> None:
    """BF-66 / BF-67: set ``token_invalidated_at`` for ``(device_id, token)``
    pairs - only while the device still holds THAT token, so a fresh token
    from a ``PUT`` in the meantime is not invalidated. Device id order, like
    ``lock_devices``, so it cannot deadlock with a claim. Flush only."""
    for device_id, token in sorted(invalid, key=lambda pair: pair[0]):
        await session.execute(
            update(Device)
            .where(
                Device.id == device_id,
                Device.fcm_token == token,
                Device.token_invalidated_at.is_(None),
            )
            .values(token_invalidated_at=now)
            .execution_options(synchronize_session=False)
        )


async def outcome_counts(session: AsyncSession, event_id: uuid.UUID) -> dict[str, int]:
    """``{DeviceOutcome value: rows}`` for one event (BF-62 counts)."""
    rows = (
        await session.execute(
            select(PushSend.outcome, func.count())
            .where(PushSend.event_id == event_id)
            .group_by(PushSend.outcome)
        )
    ).all()
    return {str(outcome): int(count) for outcome, count in rows}
