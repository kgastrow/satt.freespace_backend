"""
Freespace event writer (BF-62, D11). The ONLY way to insert ``site_event`` rows.

Repeat-collapse rule (D11)
--------------------------
A draft whose type is in ``COLLAPSIBLE_EVENT_TYPES`` is compared with the
site's most recent event that is EITHER of the same type OR of a
non-collapsible type (state changes, advisories, config changes, ... break a
run). If that event has the same type and the same ``reason``,
``advisory_type``, ``zone_slug`` and ``fingerprint``, no row is inserted: the
existing row's ``repeat_count`` is incremented and its ``last_seen_at`` set to
the draft's ``occurred_at``. Otherwise a new row is inserted.

So a site sitting above T+Δ logs ONE ``CANDIDATE / NO_MATERIAL_CHANGE`` row
with a growing count instead of 2 880 rows a day, while the timeline still
shows each new run after any significant event.

Transactions: the writer only ``flush``es. The caller owns the transaction
(the evaluator commits after persisting state and events; an endpoint relies
on ``get_session``'s commit). If you raise an HTTPException after writing an
event in an endpoint, ``get_session`` rolls the event back - commit first.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from enum import Enum
from typing import Any
import uuid

from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.freespace import EventType
from src.models.site_event import SiteEvent
from src.services.freespace.types import EventDraft


COLLAPSIBLE_EVENT_TYPES: frozenset[EventType] = frozenset(
    {
        EventType.CANDIDATE,
        EventType.INGEST_REJECTED,
        EventType.INGEST_INCONSISTENT,
    }
)


def to_json_value(value: Any) -> Any:
    """Deep-convert ``value`` to JSON-safe builtins (mappings -> dict,
    sequences -> list, enums -> value, datetimes -> ISO, UUID -> str)."""
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(to_json_value(k)): to_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_json_value(v) for v in value]
    raise TypeError(f"Cannot store {type(value).__name__} in a site_event JSON column")


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


_WRITE_ORDER_RANK = case(
    (
        SiteEvent.type.in_(
            [EventType.INGEST_REJECTED.value, EventType.INGEST_INCONSISTENT.value]
        ),
        0,
    ),
    (SiteEvent.type.in_([EventType.CANDIDATE.value, EventType.ADVISORY.value]), 2),
    else_=1,
)


async def _find_collapse_target(
    session: AsyncSession, site_id: uuid.UUID, draft: EventDraft
) -> SiteEvent | None:
    other_collapsible = [t.value for t in COLLAPSIBLE_EVENT_TYPES if t != draft.type]
    query = (
        select(SiteEvent)
        .where(
            SiteEvent.site_id == site_id,
            or_(
                SiteEvent.type == draft.type.value,
                SiteEvent.type.not_in(other_collapsible),
            ),
        )
        .order_by(
            SiteEvent.last_seen_at.desc(),
            SiteEvent.occurred_at.desc(),
            # Same timestamps = written in one evaluation. Break the tie in
            # the order the engine writes them: ingest events, then state
            # events (DATA_STALE, STATE_CHANGE, ...), then decisions
            # (CANDIDATE / ADVISORY), site-level before zone-level; the id
            # keeps the choice deterministic.
            _WRITE_ORDER_RANK.desc(),
            SiteEvent.zone_slug.is_not(None).desc(),
            SiteEvent.id.desc(),
        )
        .limit(1)
    )
    previous = (await session.execute(query)).scalars().first()
    if previous is None:
        return None
    same = (
        previous.type == draft.type.value
        and previous.reason == _enum_value(draft.reason)
        and previous.advisory_type == _enum_value(draft.advisory_type)
        and previous.zone_slug == draft.zone_slug
        and previous.fingerprint == draft.fingerprint
    )
    return previous if same else None


async def write_event(
    session: AsyncSession,
    *,
    site_id: uuid.UUID,
    organization_id: uuid.UUID,
    draft: EventDraft,
    collapse: bool = True,
) -> SiteEvent:
    """Persist ``draft`` (or collapse it into the previous identical event).

    Returns the inserted row, or the existing row that absorbed the repeat
    (whose ``id`` then differs from ``draft.id``). Flushes; never commits.
    ``collapse=False`` forces an insert.
    """
    if collapse and draft.type in COLLAPSIBLE_EVENT_TYPES:
        target = await _find_collapse_target(session, site_id, draft)
        if target is not None:
            target.repeat_count = (target.repeat_count or 1) + 1
            target.last_seen_at = draft.occurred_at
            await session.flush()
            return target

    row = SiteEvent(
        id=draft.id,
        organization_id=organization_id,
        site_id=site_id,
        occurred_at=draft.occurred_at,
        last_seen_at=draft.occurred_at,
        repeat_count=1,
        type=draft.type.value,
        reason=_enum_value(draft.reason),
        advisory_type=_enum_value(draft.advisory_type),
        zone_slug=draft.zone_slug,
        cycle_id=draft.cycle_id,
        figures=to_json_value(draft.figures) if draft.figures is not None else None,
        recommended_zone_slug=draft.recommended_zone_slug,
        rendered_title=draft.rendered_title,
        rendered_body=draft.rendered_body,
        fingerprint=draft.fingerprint,
        counts=to_json_value(draft.counts) if draft.counts is not None else None,
        fanout_status=_enum_value(draft.fanout_status),
        details=to_json_value(draft.details) if draft.details is not None else None,
    )
    session.add(row)
    await session.flush()
    return row


async def write_events(
    session: AsyncSession,
    *,
    site_id: uuid.UUID,
    organization_id: uuid.UUID,
    drafts: Iterable[EventDraft],
) -> list[SiteEvent]:
    """``write_event`` for each draft, in order."""
    return [
        await write_event(
            session, site_id=site_id, organization_id=organization_id, draft=draft
        )
        for draft in drafts
    ]
