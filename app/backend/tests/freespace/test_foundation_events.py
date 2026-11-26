"""Foundation: event writer and the D11 repeat-collapse rule."""

from __future__ import annotations

from types import MappingProxyType
import uuid

from sqlalchemy import func, select

from src.constants.freespace import (
    AdvisoryType,
    EventType,
    FanoutStatus,
    StateChangeReason,
    SuppressionReason,
)
from src.models.site_event import SiteEvent
from src.services.freespace.events import to_json_value, write_event
from src.services.freespace.types import EventDraft


def _candidate(clock, reason=SuppressionReason.NO_MATERIAL_CHANGE, fingerprint="f1"):
    return EventDraft(
        type=EventType.CANDIDATE,
        occurred_at=clock.now(),
        reason=reason,
        advisory_type=AdvisoryType.SITE_CHANGE,
        fingerprint=fingerprint,
    )


async def _write(session, site, draft, **kwargs):
    return await write_event(
        session,
        site_id=site.id,
        organization_id=site.organization_id,
        draft=draft,
        **kwargs,
    )


async def _count(session, site) -> int:
    result = await session.execute(
        select(func.count()).select_from(SiteEvent).where(SiteEvent.site_id == site.id)
    )
    return int(result.scalar_one())


async def test_insert_maps_all_fields(async_session, fs_site, fixed_clock):
    draft = EventDraft(
        type=EventType.ADVISORY,
        occurred_at=fixed_clock.now(),
        advisory_type=AdvisoryType.SITE_INITIAL,
        recommended_zone_slug="b4",
        rendered_title="T",
        rendered_body="B",
        fingerprint="abc",
        figures=MappingProxyType({"site": {"capacity": 10, "health": "OK"}}),
        counts={"SENT": 0},
        fanout_status=FanoutStatus.PENDING,
        details={"zones": ("b1", "b2"), "at": fixed_clock.now()},
        cycle_id=uuid.uuid4(),
    )
    row = await _write(async_session, fs_site, draft)
    await async_session.commit()
    assert row.id == draft.id
    assert row.type == "ADVISORY"
    assert row.advisory_type == "SITE_INITIAL"
    assert row.fanout_status == "PENDING"
    assert row.repeat_count == 1
    assert row.figures == {"site": {"capacity": 10, "health": "OK"}}
    assert row.details["zones"] == ["b1", "b2"]
    assert row.details["at"] == fixed_clock.now().isoformat()
    assert row.organization_id == fs_site.organization_id


async def test_identical_suppressions_collapse(async_session, fs_site, fixed_clock):
    first = await _write(async_session, fs_site, _candidate(fixed_clock))
    fixed_clock.advance(30)
    second = await _write(async_session, fs_site, _candidate(fixed_clock))
    fixed_clock.advance(30)
    third = await _write(async_session, fs_site, _candidate(fixed_clock))
    await async_session.commit()

    assert first.id == second.id == third.id
    assert await _count(async_session, fs_site) == 1
    await async_session.refresh(first)
    assert first.repeat_count == 3
    assert first.last_seen_at.replace(tzinfo=None) == fixed_clock.now().replace(
        tzinfo=None
    )


async def test_different_reason_or_fingerprint_inserts(
    async_session, fs_site, fixed_clock
):
    await _write(async_session, fs_site, _candidate(fixed_clock))
    await _write(
        async_session,
        fs_site,
        _candidate(fixed_clock, reason=SuppressionReason.STALE_DATA),
    )
    await _write(
        async_session,
        fs_site,
        _candidate(fixed_clock, reason=SuppressionReason.STALE_DATA, fingerprint="f2"),
    )
    assert await _count(async_session, fs_site) == 3


async def test_significant_event_breaks_the_run(async_session, fs_site, fixed_clock):
    await _write(async_session, fs_site, _candidate(fixed_clock))
    fixed_clock.advance(30)
    await _write(
        async_session,
        fs_site,
        EventDraft(
            type=EventType.STATE_CHANGE,
            occurred_at=fixed_clock.now(),
            reason=StateChangeReason.RESET,
        ),
    )
    fixed_clock.advance(30)
    await _write(async_session, fs_site, _candidate(fixed_clock))
    assert await _count(async_session, fs_site) == 3


async def test_other_collapsible_types_do_not_break_the_run(
    async_session, fs_site, fixed_clock
):
    first = await _write(async_session, fs_site, _candidate(fixed_clock))
    fixed_clock.advance(30)
    inconsistent = EventDraft(
        type=EventType.INGEST_INCONSISTENT,
        occurred_at=fixed_clock.now(),
        reason="SUM_MISMATCH",
    )
    await _write(async_session, fs_site, inconsistent)
    fixed_clock.advance(30)
    again = await _write(async_session, fs_site, _candidate(fixed_clock))
    assert again.id == first.id
    assert await _count(async_session, fs_site) == 2


async def test_advisories_never_collapse(async_session, fs_site, fixed_clock):
    for _ in range(2):
        await _write(
            async_session,
            fs_site,
            EventDraft(
                type=EventType.ADVISORY,
                occurred_at=fixed_clock.now(),
                advisory_type=AdvisoryType.SITE_INITIAL,
                fingerprint="same",
                fanout_status=FanoutStatus.PENDING,
            ),
        )
    assert await _count(async_session, fs_site) == 2


async def test_collapse_false_forces_insert(async_session, fs_site, fixed_clock):
    await _write(async_session, fs_site, _candidate(fixed_clock))
    await _write(async_session, fs_site, _candidate(fixed_clock), collapse=False)
    assert await _count(async_session, fs_site) == 2


async def test_collapse_is_per_site(
    async_session, fs_site, fs_second_site, fixed_clock
):
    a = await _write(async_session, fs_site, _candidate(fixed_clock))
    b = await _write(async_session, fs_second_site, _candidate(fixed_clock))
    assert a.id != b.id
    assert b.organization_id == fs_second_site.organization_id


def test_to_json_value():
    ident = uuid.uuid4()
    assert to_json_value({"a": (1, EventType.ADVISORY), ident: None}) == {
        "a": [1, "ADVISORY"],
        str(ident): None,
    }
