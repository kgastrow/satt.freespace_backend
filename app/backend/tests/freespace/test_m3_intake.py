"""M3 intake: ``GET /v1/ingest/ping`` and ``POST /v1/ingest/occupancy``
(BF-3, BF-10 - BF-19, BT-03, BT-04, BT-11, BN-2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any
import uuid

import pytest
from sqlalchemy import func, select

from src.constants.freespace import (
    MAX_INGEST_WARNING_LENGTH,
    MAX_INGEST_WARNINGS,
    EngineState,
    EventType,
)
from src.models.occupancy_history import OccupancyHistory
from src.models.site_event import SiteEvent
from src.models.site_snapshot import SiteSnapshot, ZoneSnapshot
from src.models.zone import Zone
from src.serialisers.freespace_ingest import IngestOccupancyRequest
from src.services.freespace import evaluator, intake
from src.services.freespace.clock import ensure_utc
from tests.freespace.conftest import (
    FIXED_START,
    SECOND_SITE_SLUG,
    SITE_SLUG,
    make_ingest_key,
)


OCCUPANCY = "/v1/ingest/occupancy"
PING = "/v1/ingest/ping"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def zone_block(
    zone_id: str, capacity: int = 100, occupied: int = 50, **extra: Any
) -> dict[str, Any]:
    block = {
        "zoneId": zone_id,
        "name": f"Basement {zone_id[1:]}",
        "capacity": capacity,
        "occupied": occupied,
        "freeUsable": capacity - occupied,
        "freeReserved": 0,
        "freeDisabled": 0,
        "unknown": 0,
        "health": "OK",
    }
    block.update(extra)
    return block


def body(
    *,
    site_id: str = SITE_SLUG,
    measured_at: datetime | None = None,
    capacity: int = 400,
    occupied: int = 200,
    zones: list[dict[str, Any]] | None = None,
    **site_extra: Any,
) -> dict[str, Any]:
    site = {
        "capacity": capacity,
        "occupied": occupied,
        "freeUsable": capacity - occupied,
        "freeReserved": 0,
        "freeDisabled": 0,
        "unknown": 0,
        "health": "OK",
    }
    site.update(site_extra)
    return {
        "siteId": site_id,
        "measuredAt": _iso(measured_at or FIXED_START),
        "publisher": {"product": "ParkIT", "version": "2.4.0", "instance": "PK-01"},
        "site": site,
        "zones": (
            zones
            if zones is not None
            else [zone_block("b1"), zone_block("b2", occupied=80)]
        ),
    }


async def _all(session, query):
    return list(
        (await session.execute(query.execution_options(populate_existing=True)))
        .scalars()
        .all()
    )


async def _events(session, site, type_: EventType | None = None) -> list[SiteEvent]:
    query = select(SiteEvent).where(SiteEvent.site_id == site.id)
    if type_ is not None:
        query = query.where(SiteEvent.type == type_.value)
    return await _all(session, query)


async def _count(session, model, **where: Any) -> int:
    query = select(func.count()).select_from(model)
    for column, value in where.items():
        query = query.where(getattr(model, column) == value)
    return int((await session.execute(query)).scalar() or 0)


# ─────────────────────────────────────────────────────────────
# Ping (BF-11)
# ─────────────────────────────────────────────────────────────


async def test_ping_shape(client, async_session, fs_site, fs_ingest_headers):
    response = await client.get(PING, headers=fs_ingest_headers)
    assert response.status_code == 200
    data = response.json()
    assert data == {
        "siteId": SITE_SLUG,
        "siteName": "Alice Lane",
        "serverTime": "2026-11-24T05:45:00Z",
    }
    assert len(response.content) < 1024
    assert await _count(async_session, SiteSnapshot) == 0


async def test_ping_and_occupancy_require_key(client, fs_site):
    assert (await client.get(PING)).status_code == 401
    response = await client.post(OCCUPANCY, json=body())
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


# ─────────────────────────────────────────────────────────────
# Accepted submission (BF-3, BF-15, BN-2)
# ─────────────────────────────────────────────────────────────


async def test_accepted_response_shape_exactly_bf15(
    client, async_session, fs_site, fs_zones, fs_ingest_headers
):
    response = await client.post(OCCUPANCY, json=body(), headers=fs_ingest_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == {
        "accepted",
        "receivedAt",
        "site",
        "discoveredZones",
        "warnings",
    }
    assert data["accepted"] is True
    assert data["receivedAt"] == "2026-11-24T05:45:00Z"
    assert set(data["site"]) == {"stale", "state", "recommendedZoneId"}
    assert data["site"]["state"] in {s.value for s in EngineState}
    assert isinstance(data["site"]["stale"], bool)
    assert data["discoveredZones"] == []
    assert data["warnings"] == []


async def test_timestamps_iso_utc_z(
    client, fixed_clock, fs_site, fs_zones, fs_ingest_headers
):
    fixed_clock.advance(1.25)
    measured = fixed_clock.now()
    data = (
        await client.post(
            OCCUPANCY, json=body(measured_at=measured), headers=fs_ingest_headers
        )
    ).json()
    assert data["receivedAt"].endswith("Z")
    assert datetime.fromisoformat(data["receivedAt"]) == fixed_clock.now()
    ping = (await client.get(PING, headers=fs_ingest_headers)).json()
    assert ping["serverTime"].endswith("Z") and "+00:00" not in ping["serverTime"]


async def test_snapshot_rows_written_and_overwritten(
    client, async_session, fixed_clock, fs_site, fs_zones, fs_ingest_headers
):
    await client.post(OCCUPANCY, json=body(), headers=fs_ingest_headers)
    fixed_clock.advance(30)
    response = await client.post(
        OCCUPANCY,
        json=body(
            measured_at=fixed_clock.now(),
            occupied=300,
            zones=[zone_block("b1", occupied=90)],
        ),
        headers=fs_ingest_headers,
    )
    assert response.status_code == 200
    site_rows = await _all(async_session, select(SiteSnapshot))
    assert len(site_rows) == 1
    row = site_rows[0]
    assert (row.capacity, row.occupied, row.free_usable) == (400, 300, 100)
    assert row.health == "OK" and row.reported_health == "OK"
    assert ensure_utc(row.received_at) == fixed_clock.now()
    assert row.publisher == {
        "product": "ParkIT",
        "version": "2.4.0",
        "instance": "PK-01",
    }
    zone_rows = await _all(
        async_session,
        select(ZoneSnapshot).where(ZoneSnapshot.zone_id == fs_zones["b1"].id),
    )
    assert len(zone_rows) == 1 and zone_rows[0].occupied == 90


async def test_unknown_extra_fields_accepted(
    client, async_session, fs_site, fs_zones, fs_ingest_headers
):
    payload = body()
    payload["futureField"] = {"x": 1}
    payload["site"]["sensorCount"] = 99
    payload["zones"][0]["colour"] = "red"
    payload["publisher"]["build"] = "abc"
    response = await client.post(OCCUPANCY, json=payload, headers=fs_ingest_headers)
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] is True


async def test_site_totals_never_summed_from_zones(
    client, async_session, fs_site, fs_zones, fs_ingest_headers
):
    # Nested zones: the zones' sum (2 x 100) differs from the site block (1000).
    await client.post(
        OCCUPANCY,
        json=body(
            capacity=1000, occupied=10, zones=[zone_block("b1"), zone_block("b2")]
        ),
        headers=fs_ingest_headers,
    )
    row = (await _all(async_session, select(SiteSnapshot)))[0]
    assert (row.capacity, row.occupied) == (1000, 10)


# ─────────────────────────────────────────────────────────────
# Validation (BF-12)
# ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("mutate", "loc"),
    [
        (lambda b: b["site"].update(occupied=-1), ["body", "site", "occupied"]),
        (lambda b: b["site"].update(capacity=1.5), ["body", "site", "capacity"]),
        (lambda b: b["site"].update(unknown="3"), ["body", "site", "unknown"]),
        (
            lambda b: b["zones"][0].update(freeUsable=-5),
            ["body", "zones", 0, "freeUsable"],
        ),
        (lambda b: b["zones"][1].update(health="GOOD"), ["body", "zones", 1, "health"]),
        (lambda b: b.pop("site"), ["body", "site"]),
        (lambda b: b.update(measuredAt="yesterday"), ["body", "measuredAt"]),
    ],
)
async def test_malformed_body_422_with_field_path(
    client, async_session, fs_site, fs_zones, fs_ingest_headers, mutate, loc
):
    payload = body()
    mutate(payload)
    response = await client.post(OCCUPANCY, json=payload, headers=fs_ingest_headers)
    assert response.status_code == 422
    locs = [err["loc"] for err in response.json()["detail"]]
    assert loc in locs
    assert await _count(async_session, SiteSnapshot) == 0


async def test_duplicate_zone_ids_rejected(
    client, fs_site, fs_zones, fs_ingest_headers
):
    payload = body(zones=[zone_block("b1"), zone_block("b1")])
    response = await client.post(OCCUPANCY, json=payload, headers=fs_ingest_headers)
    assert response.status_code == 422


async def test_bt11_sum_mismatch_accepted_inconsistent_partial(
    client, async_session, fs_site, fs_zones, fs_ingest_headers
):
    bad_zone = zone_block("b1", capacity=100, occupied=50, freeUsable=40)  # sums 90
    response = await client.post(
        OCCUPANCY,
        json=body(zones=[bad_zone, zone_block("b2")]),
        headers=fs_ingest_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] is True
    assert any("b1" in w and "SUM_MISMATCH" in w for w in data["warnings"])

    rows = {r.zone_id: r for r in await _all(async_session, select(ZoneSnapshot))}
    b1 = rows[fs_zones["b1"].id]
    assert b1.health == "PARTIAL" and b1.reported_health == "OK"
    assert rows[fs_zones["b2"].id].health == "OK"
    site_row = (await _all(async_session, select(SiteSnapshot)))[0]
    assert site_row.health == "OK"

    events = await _events(async_session, fs_site, EventType.INGEST_INCONSISTENT)
    assert len(events) == 1
    event = events[0]
    assert event.reason == "SUM_MISMATCH"
    assert event.zone_slug == "b1"
    assert event.figures["zone:b1"]["sum"] == 90
    assert event.figures["zone:b1"]["capacity"] == 100

    history = await _all(
        async_session,
        select(OccupancyHistory).where(OccupancyHistory.zone_id == fs_zones["b1"].id),
    )
    assert history[0].health == "PARTIAL"


async def test_site_block_mismatch_marks_site_partial_offline_kept(
    client, async_session, fs_site, fs_zones, fs_ingest_headers
):
    payload = body(unknown=7)  # site sums to 407 != 400
    payload["zones"][0].update(unknown=3, health="OFFLINE")  # zone sums 103, OFFLINE
    response = await client.post(OCCUPANCY, json=payload, headers=fs_ingest_headers)
    assert response.status_code == 200
    site_row = (await _all(async_session, select(SiteSnapshot)))[0]
    assert site_row.health == "PARTIAL" and site_row.reported_health == "OK"
    b1 = (
        await _all(
            async_session,
            select(ZoneSnapshot).where(ZoneSnapshot.zone_id == fs_zones["b1"].id),
        )
    )[0]
    assert b1.health == "OFFLINE"  # never upgraded
    events = await _events(async_session, fs_site, EventType.INGEST_INCONSISTENT)
    assert len(events) == 1
    assert set(events[0].figures) == {"site", "zone:b1"}
    assert events[0].zone_slug is None


async def test_repeated_mismatch_collapses(
    client, async_session, fixed_clock, fs_site, fs_zones, fs_ingest_headers
):
    for _ in range(3):
        await client.post(
            OCCUPANCY,
            json=body(measured_at=fixed_clock.now(), unknown=1),
            headers=fs_ingest_headers,
        )
        fixed_clock.advance(30)
    events = await _events(async_session, fs_site, EventType.INGEST_INCONSISTENT)
    assert len(events) == 1 and events[0].repeat_count == 3


async def test_warnings_capped_and_response_small(
    client, async_session, fs_site, fs_ingest_headers
):
    zones = [
        zone_block(
            f"z{i:03d}",
            capacity=100,
            occupied=10,
            freeUsable=0,
            name="N" * 2000,
        )
        for i in range(200)
    ]
    response = await client.post(
        OCCUPANCY,
        json=body(zones=zones, unknown=5),
        headers=fs_ingest_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["warnings"]) <= MAX_INGEST_WARNINGS
    assert all(len(w) <= MAX_INGEST_WARNING_LENGTH for w in data["warnings"])
    assert "more" in data["warnings"][-1]
    assert len(response.content) < 64 * 1024
    # The very long names are truncated to the column size.
    zone = (await _all(async_session, select(Zone).where(Zone.slug == "z000")))[0]
    assert len(zone.name) == 255


# ─────────────────────────────────────────────────────────────
# BT-03: site mismatch
# ─────────────────────────────────────────────────────────────


async def test_bt03_site_mismatch_403_event_nothing_stored(
    client, async_session, fs_site, fs_zones, fs_second_site, fs_ingest_headers
):
    response = await client.post(
        OCCUPANCY, json=body(site_id=SECOND_SITE_SLUG), headers=fs_ingest_headers
    )
    assert response.status_code == 403
    assert response.json()["detail_code"] == "ingest.site_mismatch"

    assert await _count(async_session, SiteSnapshot) == 0
    assert await _count(async_session, ZoneSnapshot) == 0
    assert await _count(async_session, OccupancyHistory) == 0
    events = await _events(async_session, fs_site, EventType.INGEST_REJECTED)
    assert len(events) == 1
    assert events[0].reason == "SITE_MISMATCH"
    assert events[0].details == {"submittedSiteId": SECOND_SITE_SLUG}
    # Nothing is written on the other site either.
    assert await _events(async_session, fs_second_site) == []


async def test_bt03_second_site_key_cannot_write_first_site(
    client, async_session, fs_site, fs_second_site
):
    plaintext, _ = await make_ingest_key(async_session, fs_second_site)
    response = await client.post(
        OCCUPANCY,
        json=body(site_id=SITE_SLUG),
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert response.status_code == 403
    assert await _count(async_session, SiteSnapshot) == 0
    assert await _events(async_session, fs_site) == []
    assert len(await _events(async_session, fs_second_site)) == 1


# ─────────────────────────────────────────────────────────────
# BF-13 clocks
# ─────────────────────────────────────────────────────────────


async def test_bt04_clock_skew_422(client, async_session, fs_site, fs_ingest_headers):
    response = await client.post(
        OCCUPANCY,
        json=body(measured_at=FIXED_START + timedelta(minutes=5)),
        headers=fs_ingest_headers,
    )
    assert response.status_code == 422
    data = response.json()
    assert data["detail_code"] == "ingest.clock_skew"
    assert "CLOCK_SKEW" in data["detail"]
    assert await _count(async_session, SiteSnapshot) == 0
    events = await _events(async_session, fs_site, EventType.INGEST_REJECTED)
    assert [e.reason for e in events] == ["CLOCK_SKEW"]


async def test_skew_within_limit_accepted(client, fs_site, fs_zones, fs_ingest_headers):
    response = await client.post(
        OCCUPANCY,
        json=body(measured_at=FIXED_START + timedelta(seconds=119)),
        headers=fs_ingest_headers,
    )
    assert response.status_code == 200


async def test_staleness_uses_received_at(
    client, async_session, fs_site, fs_zones, fs_ingest_headers
):
    measured = FIXED_START - timedelta(minutes=10)
    await client.post(
        OCCUPANCY, json=body(measured_at=measured), headers=fs_ingest_headers
    )
    row = (await _all(async_session, select(SiteSnapshot)))[0]
    assert ensure_utc(row.measured_at) == measured
    assert ensure_utc(row.received_at) == FIXED_START


async def test_out_of_order_ignored_without_overwrite(
    client, async_session, fixed_clock, fs_site, fs_zones, fs_ingest_headers
):
    await client.post(OCCUPANCY, json=body(occupied=200), headers=fs_ingest_headers)
    fixed_clock.advance(30)
    response = await client.post(
        OCCUPANCY,
        json=body(measured_at=FIXED_START - timedelta(seconds=10), occupied=399),
        headers=fs_ingest_headers,
    )
    assert response.status_code == 200
    assert response.json() == {"ignored": "OUT_OF_ORDER"}
    row = (await _all(async_session, select(SiteSnapshot)))[0]
    assert row.occupied == 200
    assert ensure_utc(row.received_at) == FIXED_START
    events = await _events(async_session, fs_site, EventType.INGEST_REJECTED)
    assert [e.reason for e in events] == ["OUT_OF_ORDER"]


async def test_same_measured_at_is_not_out_of_order(
    client, fixed_clock, fs_site, fs_zones, fs_ingest_headers
):
    await client.post(OCCUPANCY, json=body(), headers=fs_ingest_headers)
    fixed_clock.advance(5)
    response = await client.post(OCCUPANCY, json=body(), headers=fs_ingest_headers)
    assert response.json()["accepted"] is True


# ─────────────────────────────────────────────────────────────
# BF-14 zone matching
# ─────────────────────────────────────────────────────────────


async def test_unknown_zone_discovered(
    client, async_session, fixed_clock, fs_site, fs_zones, fs_ingest_headers
):
    payload = body(zones=[zone_block("b1"), zone_block("b5", name="Basement 5")])
    response = await client.post(OCCUPANCY, json=payload, headers=fs_ingest_headers)
    assert response.status_code == 200
    assert response.json()["discoveredZones"] == ["b5"]

    zone = (
        await _all(
            async_session,
            select(Zone).where(Zone.site_id == fs_site.id, Zone.slug == "b5"),
        )
    )[0]
    assert zone.enabled is False
    assert zone.discovered is True
    assert zone.name == "Basement 5"
    assert zone.organization_id == fs_site.organization_id
    assert zone.display_order == 5  # after b1..b4 (1..4)
    snapshot = await _all(
        async_session, select(ZoneSnapshot).where(ZoneSnapshot.zone_id == zone.id)
    )
    assert snapshot and snapshot[0].occupied == 50

    events = await _events(async_session, fs_site, EventType.ZONE_DISCOVERED)
    assert [(e.zone_slug, e.details) for e in events] == [
        ("b5", {"name": "Basement 5"})
    ]

    # Re-submitting does not create it again; it is still reported until reviewed.
    fixed_clock.advance(30)
    response = await client.post(
        OCCUPANCY,
        json=body(measured_at=fixed_clock.now(), zones=payload["zones"]),
        headers=fs_ingest_headers,
    )
    assert response.json()["discoveredZones"] == ["b5"]
    assert await _count(async_session, Zone, site_id=fs_site.id, slug="b5") == 1
    assert len(await _events(async_session, fs_site, EventType.ZONE_DISCOVERED)) == 1

    # Once reviewed (M1 clears ``discovered``) it is no longer reported.
    zone.discovered = False
    await async_session.commit()
    fixed_clock.advance(30)
    response = await client.post(
        OCCUPANCY,
        json=body(measured_at=fixed_clock.now(), zones=payload["zones"]),
        headers=fs_ingest_headers,
    )
    assert response.json()["discoveredZones"] == []


async def test_discovered_zone_without_name_uses_zone_id(
    client, async_session, fs_site, fs_ingest_headers
):
    block = zone_block("x9")
    del block["name"]
    await client.post(OCCUPANCY, json=body(zones=[block]), headers=fs_ingest_headers)
    zone = (await _all(async_session, select(Zone).where(Zone.slug == "x9")))[0]
    assert zone.name == "x9"
    assert zone.display_order == 0


async def test_missing_zone_keeps_last_values(
    client, async_session, fixed_clock, fs_site, fs_zones, fs_ingest_headers
):
    await client.post(OCCUPANCY, json=body(), headers=fs_ingest_headers)
    fixed_clock.advance(30)
    await client.post(
        OCCUPANCY,
        json=body(measured_at=fixed_clock.now(), zones=[zone_block("b1", occupied=70)]),
        headers=fs_ingest_headers,
    )
    rows = {r.zone_id: r for r in await _all(async_session, select(ZoneSnapshot))}
    b1, b2 = rows[fs_zones["b1"].id], rows[fs_zones["b2"].id]
    assert b1.occupied == 70 and ensure_utc(b1.received_at) == fixed_clock.now()
    assert b2.occupied == 80 and ensure_utc(b2.received_at) == FIXED_START
    assert fs_zones["b3"].id not in rows


# ─────────────────────────────────────────────────────────────
# BF-18 rate limit
# ─────────────────────────────────────────────────────────────


async def test_rate_limit_429_retry_after(
    client, fixed_clock, fs_site, fs_zones, fs_ingest_headers
):
    for _ in range(12):
        response = await client.post(
            OCCUPANCY,
            json=body(measured_at=fixed_clock.now()),
            headers=fs_ingest_headers,
        )
        assert response.status_code == 200
        fixed_clock.advance(1)
    response = await client.post(
        OCCUPANCY, json=body(measured_at=fixed_clock.now()), headers=fs_ingest_headers
    )
    assert response.status_code == 429
    retry_after = response.headers["retry-after"]
    assert retry_after.isdigit() and 1 <= int(retry_after) <= 600
    # Ping is not a submission and is not limited.
    assert (await client.get(PING, headers=fs_ingest_headers)).status_code == 200


# ─────────────────────────────────────────────────────────────
# Evaluation (BF-16, D7)
# ─────────────────────────────────────────────────────────────


async def test_response_reports_evaluator_view_and_enqueues_after_commit(
    client, async_session, fs_site, fs_zones, fs_ingest_headers, monkeypatch
):
    event_id = uuid.uuid4()
    calls: list[Any] = []

    async def fake_evaluate(session, site_id, clock):
        calls.append(("evaluate", site_id))
        return evaluator.EvaluatedSiteView(
            state=EngineState.ACTIVE,
            recommended_zone_slug="b2",
            stale=False,
            fanout_event_ids=(event_id,),
        )

    async def fake_enqueue(event_ids):
        calls.append(("enqueue", tuple(event_ids)))

    real_commit = async_session.commit

    async def recording_commit():
        calls.append(("commit",))
        await real_commit()

    monkeypatch.setattr(evaluator, "evaluate_site", fake_evaluate)
    monkeypatch.setattr(evaluator, "enqueue_fanouts", fake_enqueue)
    monkeypatch.setattr(async_session, "commit", recording_commit)
    response = await client.post(OCCUPANCY, json=body(), headers=fs_ingest_headers)
    assert response.json()["site"] == {
        "stale": False,
        "state": "ACTIVE",
        "recommendedZoneId": "b2",
    }
    # Commit (after the auth dependency's own commit) precedes the enqueue (BF-52).
    evaluate_at = calls.index(("evaluate", fs_site.id))
    enqueue_at = calls.index(("enqueue", (event_id,)))
    assert ("commit",) in calls[evaluate_at:enqueue_at]


async def test_evaluator_failure_keeps_snapshot(
    client, async_session, fs_site, fs_zones, fs_ingest_headers, monkeypatch
):
    async def boom(session, site_id, clock):
        raise RuntimeError("engine bug")

    monkeypatch.setattr(evaluator, "evaluate_site", boom)
    response = await client.post(OCCUPANCY, json=body(), headers=fs_ingest_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] is True
    assert data["site"]["state"] == "IDLE"
    assert data["site"]["recommendedZoneId"] is None
    assert any("Evaluation failed" in w for w in data["warnings"])
    assert await _count(async_session, SiteSnapshot) == 1


# ─────────────────────────────────────────────────────────────
# Service entry point used by mock mode (M10)
# ─────────────────────────────────────────────────────────────


async def test_service_entry_point(async_session, fixed_clock, fs_site, fs_zones):
    payload = IngestOccupancyRequest.model_validate(json.loads(json.dumps(body())))
    result = await intake.ingest_snapshot(async_session, fs_site, payload, fixed_clock)
    assert result.accepted is True
    assert result.received_at == FIXED_START
    assert result.state == EngineState.IDLE
    assert await _count(async_session, SiteSnapshot) == 1

    with pytest.raises(intake.SiteMismatchError):
        await intake.ingest_snapshot(
            async_session,
            fs_site,
            payload.model_copy(update={"site_id": "nope"}),
            fixed_clock,
        )
    with pytest.raises(intake.ClockSkewError):
        await intake.ingest_snapshot(
            async_session,
            fs_site,
            payload.model_copy(
                update={"measured_at": FIXED_START + timedelta(seconds=121)}
            ),
            fixed_clock,
        )
