"""Shared helpers for the M7 tests (no tests in this module)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.constants.freespace import (
    AdvisoryType,
    EventType,
    FanoutStatus,
    LimitScope,
    Platform,
)
from src.models.device import Device, DeviceSite
from src.models.push_send import PushSend
from src.models.site import Site
from src.models.site_event import SiteEvent
from src.services.freespace import engine as engine_module
from src.services.freespace import fanout as fanout_module
from src.services.freespace.clock import FixedClock
from src.services.freespace.deployment_settings import DeploymentSettings
from src.services.freespace.events import write_event
from src.services.freespace.fanout import FanoutResult, run_fanout
from src.services.freespace.fcm import FcmClient
from src.services.freespace.keys import device_id_suffix, hash_device_id
from src.services.freespace.loaders import load_engine_state_row
from src.services.freespace.types import EngineStateData, EventDraft


def session_factory_for(session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    """Sessions on the same (SQLite StaticPool) engine as ``async_session``."""
    return async_sessionmaker(
        bind=session.bind, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


def token_for(index: int, prefix: str = "tok") -> str:
    return f"{prefix}-{index:05d}-" + "x" * 20


async def make_devices(
    session: AsyncSession,
    sites: Sequence[Site],
    count: int,
    *,
    now: datetime,
    prefix: str = "tok",
    notifications_enabled: bool = True,
    platform: Platform = Platform.ANDROID,
    commit: bool = True,
) -> list[Device]:
    """``count`` devices that selected every site in ``sites``."""
    devices = []
    for index in range(count):
        raw_id = f"{prefix}{uuid.uuid4().hex}"[:40].ljust(22, "a")
        device = Device(
            id=uuid.uuid4(),
            device_key_hash=hash_device_id(raw_id),
            id_suffix=device_id_suffix(raw_id),
            fcm_token=token_for(index, prefix),
            platform=platform.value,
            app_version="1.0.0",
            notifications_enabled=notifications_enabled,
            first_seen=now,
            last_seen=now,
        )
        devices.append(device)
    session.add_all(devices)
    await session.flush()
    session.add_all(
        [DeviceSite(device_id=d.id, site_id=s.id) for d in devices for s in sites]
    )
    if commit:
        await session.commit()
    return devices


async def make_advisory_event(
    session: AsyncSession,
    site: Site,
    *,
    now: datetime,
    advisory_type: AdvisoryType = AdvisoryType.SITE_INITIAL,
    fingerprint: str | None = None,
    recommended_zone_slug: str | None = "b4",
    cycle_id: uuid.UUID | None = None,
    occupancy_pct: int = 90,
    title: str = "Alice Lane",
    body: str = "Basement 3 and Basement 4 currently have the most available bays.",
) -> SiteEvent:
    """An ADVISORY event with fanout PENDING, like the engine writes it.
    ``cycle_id`` defaults to the site's engine-state cycle (set if empty)."""
    state_row = await load_engine_state_row(session, site.id)
    assert state_row is not None
    if cycle_id is None:
        if state_row.cycle_id is None:
            state_row.cycle_id = uuid.uuid4()
        cycle_id = state_row.cycle_id
    draft = EventDraft(
        type=EventType.ADVISORY,
        occurred_at=now,
        advisory_type=advisory_type,
        cycle_id=cycle_id,
        figures={"site": {"occupancyPct": occupancy_pct}},
        recommended_zone_slug=recommended_zone_slug,
        rendered_title=title,
        rendered_body=body,
        fingerprint=fingerprint or uuid.uuid4().hex * 2,
        fanout_status=FanoutStatus.PENDING,
        details={"topZones": ["b4", "b3"], "occupancyExact": occupancy_pct + 0.25},
    )
    event = await write_event(
        session, site_id=site.id, organization_id=site.organization_id, draft=draft
    )
    state_row.inflight_event_id = event.id
    state_row.inflight_fingerprint = event.fingerprint
    await session.commit()
    return event


async def drive_fanout(
    factory: Any,
    event_id: uuid.UUID,
    clock: FixedClock,
    fcm: FcmClient,
    *,
    chunk_size: int = 500,
    max_runs: int = 1000,
) -> list[FanoutResult]:
    """Call ``run_fanout`` like the worker would until it stops re-enqueueing,
    advancing the clock by each deferral."""
    results = []
    for _ in range(max_runs):
        result = await run_fanout(
            factory, event_id, clock=clock, fcm=fcm, chunk_size=chunk_size
        )
        results.append(result)
        if result.reenqueue_in_s is None:
            return results
        if result.reenqueue_in_s > 0:
            clock.advance(result.reenqueue_in_s)
    raise AssertionError("fan-out did not finish")


async def reload_event(session: AsyncSession, event_id: uuid.UUID) -> SiteEvent:
    row = (
        (
            await session.execute(
                select(SiteEvent)
                .where(SiteEvent.id == event_id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .one()
    )
    return row


async def send_rows(session: AsyncSession, event_id: uuid.UUID) -> list[PushSend]:
    return list(
        (
            await session.execute(
                select(PushSend)
                .where(PushSend.event_id == event_id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )


@dataclass
class EngineCalls:
    calls: list[dict[str, Any]]


def install_engine_recorder(monkeypatch: pytest.MonkeyPatch) -> EngineCalls:
    """Replace ``engine.on_fanout_completed`` (M6) with a recorder that clears
    the in-flight guard and, when sent >= 1, advances last_sent_*."""
    calls: list[dict[str, Any]] = []

    def fake(state: EngineStateData, **kwargs: Any) -> EngineStateData:
        calls.append(kwargs)
        new = state
        if state.inflight_event_id == kwargs["event_id"]:
            new = replace(new, inflight_event_id=None, inflight_fingerprint=None)
        if kwargs["sent_count"] >= 1:
            new = replace(
                new,
                last_sent_fingerprint=kwargs["fingerprint"],
                last_sent_at=kwargs["now"],
            )
        return new

    monkeypatch.setattr(engine_module, "on_fanout_completed", fake)
    return EngineCalls(calls)


def use_deployment_settings(
    monkeypatch: pytest.MonkeyPatch, **values: Any
) -> DeploymentSettings:
    settings = DeploymentSettings(**values)

    async def fake(session: Any = None) -> DeploymentSettings:
        return settings

    monkeypatch.setattr(fanout_module, "get_deployment_settings", fake)
    return settings


__all__ = [
    "LimitScope",
    "drive_fanout",
    "install_engine_recorder",
    "make_advisory_event",
    "make_devices",
    "reload_event",
    "send_rows",
    "session_factory_for",
    "token_for",
    "use_deployment_settings",
]
