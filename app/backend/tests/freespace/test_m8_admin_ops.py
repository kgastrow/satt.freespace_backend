"""M8: back-office operations API: events + CSV, sites summary, live view,
device statistics, occupancy history, test push, announcement."""

from __future__ import annotations

from datetime import timedelta
import uuid

from sqlalchemy import select

from src.constants.freespace import EventType
from src.models.device import Device, DeviceSite
from src.models.occupancy_history import OccupancyHistory
from src.models.push_send import PushSend
from src.models.site_event import SiteEvent
from src.services.freespace.fcm import FcmResultKind, FcmSendResult
from src.services.freespace.keys import device_id_suffix, hash_device_id
from tests.freespace.conftest import make_site


BASE = "/api/v1/admin/sites"
SECRET_TOKEN = "tok-SECRET-abcdefghijklmnop"
DEVICE_ID = "d" * 16 + "ABCDEF" + "xyz"  # 25 chars


def h(token: str) -> dict[str, str]:
    return {"Authorization": token}


async def make_device(
    session,
    now,
    *,
    device_id: str,
    sites,
    token: str | None = None,
    platform: str = "android",
    version: str | None = "1.0.0",
    enabled: bool = True,
) -> Device:
    device = Device(
        device_key_hash=hash_device_id(device_id),
        id_suffix=device_id_suffix(device_id),
        fcm_token=token or f"token-{uuid.uuid4().hex}",
        platform=platform,
        app_version=version,
        notifications_enabled=enabled,
        first_seen=now,
        last_seen=now,
    )
    session.add(device)
    await session.flush()
    for site in sites:
        session.add(DeviceSite(device_id=device.id, site_id=site.id))
    await session.commit()
    await session.refresh(device)
    return device


async def add_event(session, site, now, **kw) -> SiteEvent:
    row = SiteEvent(
        organization_id=site.organization_id,
        site_id=site.id,
        occurred_at=kw.pop("occurred_at", now),
        last_seen_at=now,
        repeat_count=1,
        type=kw.pop("type", EventType.CANDIDATE.value),
        **kw,
    )
    session.add(row)
    await session.commit()
    return row


def assert_no_device_data(text: str, *devices: tuple[str, str]) -> None:
    for device_id, token in devices:
        for secret in (device_id, device_id_suffix(device_id), token):
            assert secret not in text


# ───────────────────────────── events ─────────────────────────────


class TestEvents:
    async def test_list_filters_and_pagination(
        self, client, async_session, fs_site, fs_admin_token, fixed_clock
    ):
        now = fixed_clock.now()
        for i in range(5):
            await add_event(
                async_session,
                fs_site,
                now,
                type="CANDIDATE",
                reason="NO_MATERIAL_CHANGE",
                occurred_at=now - timedelta(hours=i),
            )
        await add_event(
            async_session, fs_site, now, type="DATA_STALE", reason="STALE_DATA"
        )
        url = f"{BASE}/{fs_site.id}/events"
        r = await client.get(url, headers=h(fs_admin_token))
        assert r.status_code == 200
        assert r.json()["total"] == 6
        r = await client.get(
            url, headers=h(fs_admin_token), params={"type": "CANDIDATE", "limit": 2}
        )
        body = r.json()
        assert body["total"] == 5 and len(body["items"]) == 2
        r = await client.get(
            url, headers=h(fs_admin_token), params={"reason": "STALE_DATA"}
        )
        assert [e["type"] for e in r.json()["items"]] == ["DATA_STALE"]
        r = await client.get(
            url,
            headers=h(fs_admin_token),
            params={
                "type": "CANDIDATE",
                "start": (now - timedelta(hours=2, minutes=1)).isoformat(),
                "end": (now + timedelta(minutes=1)).isoformat(),
            },
        )
        assert r.json()["total"] == 3
        # newest first
        times = [e["occurred_at"] for e in r.json()["items"]]
        assert times == sorted(times, reverse=True)

    async def test_invalid_filters(self, client, fs_site, fs_admin_token, fixed_clock):
        url = f"{BASE}/{fs_site.id}/events"
        r = await client.get(url, headers=h(fs_admin_token), params={"type": "NOPE"})
        assert r.status_code == 422
        assert r.json()["detail_code"] == "site_event.invalid_filter"
        now = fixed_clock.now()
        r = await client.get(
            url,
            headers=h(fs_admin_token),
            params={"start": now.isoformat(), "end": (now - timedelta(1)).isoformat()},
        )
        assert r.status_code == 422
        assert r.json()["detail_code"] == "site_event.invalid_period"

    async def test_tenant_isolation_and_roles(
        self,
        client,
        async_session,
        fs_site,
        fs_second_site,
        fs_admin_token,
        fs_second_org_admin_token,
        fs_viewer_token,
        fs_no_role_token,
        test_admin_token,
        fixed_clock,
    ):
        now = fixed_clock.now()
        await add_event(async_session, fs_site, now)
        await add_event(async_session, fs_second_site, now)
        for suffix in ("", "/export.csv"):
            url = f"{BASE}/{fs_site.id}/events{suffix}"
            r = await client.get(url, headers=h(fs_second_org_admin_token))
            assert r.status_code == 404
            assert r.json()["detail_code"] == "site.not_found"
            assert (
                await client.get(url, headers=h(fs_no_role_token))
            ).status_code == 403
            assert (
                await client.get(url, headers=h(fs_viewer_token))
            ).status_code == 200
            assert (
                await client.get(url, headers=h(test_admin_token))
            ).status_code == 200
        r = await client.get(
            f"{BASE}/{fs_second_site.id}/events", headers=h(fs_second_org_admin_token)
        )
        assert r.json()["total"] == 1

    async def test_csv_export_content_and_privacy(
        self, client, async_session, fs_site, fs_admin_token, fixed_clock
    ):
        now = fixed_clock.now()
        await add_event(
            async_session,
            fs_site,
            now,
            type="ANNOUNCEMENT",
            reason="ACCEPTED_BY_FCM",
            rendered_title="Hello",
            rendered_body="=SUM(A1)",
            details={"target": "topic"},
        )
        await add_event(async_session, fs_site, now, type="DATA_STALE")
        url = f"{BASE}/{fs_site.id}/events/export.csv"
        r = await client.get(
            url, headers=h(fs_admin_token), params={"type": "ANNOUNCEMENT"}
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        lines = r.text.strip().splitlines()
        assert lines[0].startswith("occurred_at,last_seen_at,repeat_count,type")
        assert len(lines) == 2
        assert "ANNOUNCEMENT" in lines[1] and "ACCEPTED_BY_FCM" in lines[1]
        assert "'=SUM(A1)" in lines[1]  # formula neutralised
        assert "DATA_STALE" not in r.text
        r = await client.get(url, headers=h(fs_admin_token))
        assert len(r.text.strip().splitlines()) == 3

    async def test_csv_too_large(
        self, client, async_session, fs_site, fs_admin_token, fixed_clock, monkeypatch
    ):
        from src.api import freespace_events

        await add_event(async_session, fs_site, fixed_clock.now())
        monkeypatch.setattr(freespace_events, "MAX_EXPORT_ROWS", 0)
        r = await client.get(
            f"{BASE}/{fs_site.id}/events/export.csv", headers=h(fs_admin_token)
        )
        assert r.status_code == 422
        assert r.json()["detail_code"] == "site_event.export_too_large"


# ───────────────────────────── summary ─────────────────────────────


class TestSummary:
    async def test_summary_row(
        self,
        client,
        async_session,
        fs_site,
        fs_zones,
        fs_snapshot,
        fs_admin_token,
        fixed_clock,
    ):
        await fs_snapshot(
            fs_site,
            capacity=100,
            occupied=50,
            zones={
                "b1": {"capacity": 50, "occupied": 49},
                "b2": {"capacity": 50, "occupied": 1},
            },
        )
        await make_device(
            async_session, fixed_clock.now(), device_id=DEVICE_ID, sites=[fs_site]
        )
        await make_device(
            async_session,
            fixed_clock.now(),
            device_id="f" * 22,
            sites=[fs_site],
            enabled=False,
        )
        r = await client.get(f"{BASE}/summary", headers=h(fs_admin_token))
        assert r.status_code == 200, r.text
        (item,) = r.json()["items"]
        assert item["name"] == fs_site.name and item["managed"] is True
        assert item["mode"] == "managed"
        assert item["stale"] is False
        assert item["occupancy_pct"] == 50
        assert item["engine_state"] == "IDLE"
        assert item["devices_opted_in"] == 1
        assert item["age_seconds"] == 0

    async def test_tenant_scoping(
        self,
        client,
        fs_site,
        fs_second_site,
        fs_admin_token,
        fs_second_org_admin_token,
        test_admin_token,
        fs_no_role_token,
    ):
        r = await client.get(f"{BASE}/summary", headers=h(fs_admin_token))
        assert [i["id"] for i in r.json()["items"]] == [str(fs_site.id)]
        r = await client.get(f"{BASE}/summary", headers=h(fs_second_org_admin_token))
        assert [i["id"] for i in r.json()["items"]] == [str(fs_second_site.id)]
        r = await client.get(f"{BASE}/summary", headers=h(test_admin_token))
        assert len(r.json()["items"]) == 2
        assert (
            await client.get(f"{BASE}/summary", headers=h(fs_no_role_token))
        ).status_code == 403

    async def test_shadow_and_never_received(
        self, client, async_session, test_organization, fs_admin_token, fixed_clock
    ):
        await make_site(
            async_session,
            test_organization,
            slug="shadow-1",
            name="Shadow",
            managed=False,
        )
        r = await client.get(f"{BASE}/summary", headers=h(fs_admin_token))
        (item,) = r.json()["items"]
        assert item["mode"] == "shadow" and item["stale"] is True
        assert item["as_of"] is None and item["occupancy_pct"] is None


# ───────────────────────────── live view ─────────────────────────────


class TestLive:
    async def test_live_equals_app_endpoint(
        self,
        client,
        fs_site,
        fs_zones,
        fs_snapshot,
        fs_admin_token,
        fs_app_headers,
    ):
        await fs_snapshot(
            fs_site,
            capacity=200,
            occupied=150,
            zones={
                "b1": {"capacity": 50, "occupied": 49},
                "b2": {"capacity": 50, "occupied": 10},
                "b3": {"capacity": 50, "occupied": 40},
                "b4": {"capacity": 50, "occupied": 51 - 1},
            },
        )
        live = (
            await client.get(f"{BASE}/{fs_site.id}/live", headers=h(fs_admin_token))
        ).json()
        app = (
            await client.get(
                f"/v1/sites/{fs_site.slug}/availability", headers=fs_app_headers
            )
        ).json()
        av = live["availability"]
        assert av["recommended_zone_id"] == app["recommendedZoneId"]
        assert av["stale"] == app["stale"]
        assert av["age_seconds"] == app["ageSeconds"]
        assert av["occupancy_pct"] == app["site"]["occupancyPct"]
        assert av["free_usable"] == app["site"]["freeUsable"]
        live_zones = {z["id"]: z for z in av["zones"] if z["enabled"]}
        assert set(live_zones) == {z["id"] for z in app["zones"]}
        for z in app["zones"]:
            lz = live_zones[z["id"]]
            assert (lz["free"], lz["occupancy_pct"], lz["status"], lz["capacity"]) == (
                z["free"],
                z["occupancyPct"],
                z["status"],
                z["capacity"],
            )
        assert live["engine"]["state"] == "IDLE"
        assert live["site"]["trigger_pct"] == 90

    async def test_engine_timers(
        self, client, async_session, fs_site, fs_admin_token, fixed_clock
    ):
        from src.models.site_engine_state import SiteEngineState

        state = (
            await async_session.execute(
                select(SiteEngineState).where(SiteEngineState.site_id == fs_site.id)
            )
        ).scalar_one()
        now = fixed_clock.now()
        state.state = "PENDING"
        state.pending_since = now - timedelta(minutes=2)
        state.inflight_event_id = uuid.uuid4()
        state.zone_advisory_state = {
            "b1": {"above_since": "2026-11-24T05:00:00Z", "advised": True}
        }
        await async_session.commit()
        r = await client.get(f"{BASE}/{fs_site.id}/live", headers=h(fs_admin_token))
        eng = r.json()["engine"]
        assert eng["state"] == "PENDING"
        assert eng["pending_since"] == "2026-11-24T05:43:00Z"
        assert eng["fires_at"] == "2026-11-24T05:48:00Z"  # + stabilisation 300 s
        assert eng["inflight"] is True
        assert eng["zone_advisories"] == [
            {"zone": "b1", "above_since": "2026-11-24T05:00:00Z", "advised": True}
        ]

    async def test_tenant_and_roles(
        self,
        client,
        fs_site,
        fs_admin_token,
        fs_second_org_admin_token,
        fs_viewer_token,
        fs_no_role_token,
    ):
        url = f"{BASE}/{fs_site.id}/live"
        assert (
            await client.get(url, headers=h(fs_second_org_admin_token))
        ).status_code == 404
        assert (await client.get(url, headers=h(fs_viewer_token))).status_code == 200
        assert (await client.get(url, headers=h(fs_no_role_token))).status_code == 403
        r = await client.get(f"{BASE}/{uuid.uuid4()}/live", headers=h(fs_admin_token))
        assert r.status_code == 404


# ───────────────────────────── device stats ─────────────────────────────


class TestDeviceStats:
    async def test_counts_and_privacy(
        self,
        client,
        async_session,
        fs_site,
        fs_second_site,
        fs_admin_token,
        fs_second_org_admin_token,
        test_admin_token,
        fixed_clock,
    ):
        now = fixed_clock.now()
        d1 = await make_device(
            async_session, now, device_id=DEVICE_ID, sites=[fs_site], token=SECRET_TOKEN
        )
        await make_device(
            async_session,
            now,
            device_id="g" * 22,
            sites=[fs_site],
            platform="ios",
            version="2.0.0",
        )
        await make_device(
            async_session,
            now,
            device_id="h" * 22,
            sites=[fs_second_site],
            enabled=False,
        )
        await make_device(async_session, now, device_id="i" * 22, sites=[])
        assert d1.id

        r = await client.get(f"{BASE}/device-stats", headers=h(fs_admin_token))
        body = r.json()
        assert body["total_devices"] == 2 and body["opted_in"] == 2
        assert {p["platform"]: p["count"] for p in body["by_platform"]} == {
            "android": 1,
            "ios": 1,
        }
        assert [s["slug"] for s in body["by_site"]] == [fs_site.slug]
        assert_no_device_data(r.text, (DEVICE_ID, SECRET_TOKEN))

        r = await client.get(
            f"{BASE}/device-stats", headers=h(fs_second_org_admin_token)
        )
        assert r.json()["total_devices"] == 1 and r.json()["opted_in"] == 0

        r = await client.get(f"{BASE}/device-stats", headers=h(test_admin_token))
        assert r.json()["total_devices"] == 4

        r = await client.get(
            f"{BASE}/{fs_site.id}/device-stats", headers=h(fs_admin_token)
        )
        assert r.json()["total_devices"] == 2
        assert r.json()["by_site"][0]["opted_in"] == 2
        r = await client.get(
            f"{BASE}/{fs_site.id}/device-stats", headers=h(fs_second_org_admin_token)
        )
        assert r.status_code == 404

    async def test_roles(self, client, fs_no_role_token, fs_viewer_token):
        assert (
            await client.get(f"{BASE}/device-stats", headers=h(fs_no_role_token))
        ).status_code == 403
        assert (
            await client.get(f"{BASE}/device-stats", headers=h(fs_viewer_token))
        ).status_code == 200


# ───────────────────────────── history ─────────────────────────────


class TestHistory:
    async def _point(self, session, site, zone, at, occupied):
        session.add(
            OccupancyHistory(
                organization_id=site.organization_id,
                site_id=site.id,
                zone_id=zone.id if zone else None,
                bucket_minute=at,
                occupied=occupied,
                capacity=100,
                free_usable=100 - occupied,
                health="OK",
            )
        )
        await session.commit()

    async def test_day_in_site_time_zone(
        self, client, async_session, fs_site, fs_zones, fs_admin_token, fixed_clock
    ):
        now = fixed_clock.now()  # 2026-11-24 05:45Z = 07:45 SAST (UTC+2)
        # local midnight = 2026-11-23T22:00Z
        await self._point(async_session, fs_site, None, now, 91)
        await self._point(async_session, fs_site, fs_zones["b1"], now, 40)
        await self._point(
            async_session,
            fs_site,
            None,
            now.replace(hour=21, minute=59) - timedelta(days=1),
            10,
        )  # previous local day
        r = await client.get(f"{BASE}/{fs_site.id}/history", headers=h(fs_admin_token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["date"] == "2026-11-24"
        assert body["start"] == "2026-11-23T22:00:00Z"
        assert body["trigger_pct"] == 90 and body["reset_pct"] == 80
        assert [p["occupied"] for p in body["site"]] == [91]
        assert body["site"][0]["occupancy_pct"] == 91
        assert [z["id"] for z in body["zones"]] == ["b1"]
        r = await client.get(
            f"{BASE}/{fs_site.id}/history",
            headers=h(fs_admin_token),
            params={"date": "2026-11-23"},
        )
        assert [p["occupied"] for p in r.json()["site"]] == [10]

    async def test_invalid_date_tenant_roles(
        self,
        client,
        fs_site,
        fs_admin_token,
        fs_second_org_admin_token,
        fs_no_role_token,
    ):
        url = f"{BASE}/{fs_site.id}/history"
        r = await client.get(url, headers=h(fs_admin_token), params={"date": "nope"})
        assert r.status_code == 422
        assert r.json()["detail_code"] == "site_stats.invalid_date"
        assert (
            await client.get(url, headers=h(fs_second_org_admin_token))
        ).status_code == 404
        assert (await client.get(url, headers=h(fs_no_role_token))).status_code == 403


# ───────────────────────────── test push ─────────────────────────────


class TestTestPush:
    def url(self, site):
        return f"{BASE}/{site.id}/test-push"

    async def test_by_suffix_one_match(
        self, client, async_session, fs_site, fs_operator_token, fake_fcm, fixed_clock
    ):
        await make_device(
            async_session,
            fixed_clock.now(),
            device_id=DEVICE_ID,
            sites=[fs_site],
            token=SECRET_TOKEN,
        )
        r = await client.post(
            self.url(fs_site),
            headers=h(fs_operator_token),
            json={"target": "device", "device_suffix": device_id_suffix(DEVICE_ID)},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["message_code"] == "site_push.test_sent"
        assert body["outcome"] == "ACCEPTED_BY_FCM"
        assert "delivered" not in r.text.lower()
        assert [m.token for m in fake_fcm.sent] == [SECRET_TOKEN]
        assert fake_fcm.sent[0].payload["data"]["type"] == "TEST"
        assert_no_device_data(r.text, (DEVICE_ID, SECRET_TOKEN))

        ev = (
            await async_session.execute(
                select(SiteEvent).where(SiteEvent.type == EventType.TEST_PUSH.value)
            )
        ).scalar_one()
        assert ev.advisory_type == "TEST" and ev.reason == "ACCEPTED_BY_FCM"
        assert str(ev.id) == body["event_id"]
        assert_no_device_data(str(ev.details), (DEVICE_ID, SECRET_TOKEN))
        # not counted: no per-phone history at all
        assert (await async_session.execute(select(PushSend))).first() is None

    async def test_suffix_zero_two_and_other_site(
        self,
        client,
        async_session,
        fs_site,
        fs_second_site,
        fs_admin_token,
        fixed_clock,
    ):
        now = fixed_clock.now()
        url = self.url(fs_site)
        body = {"target": "device", "device_suffix": "ABCDEF"}
        r = await client.post(url, headers=h(fs_admin_token), json=body)
        assert r.status_code == 404
        assert r.json()["detail_code"] == "site_push.device_not_found"
        # one device, but on another site
        await make_device(
            async_session, now, device_id="a" * 16 + "ABCDEF", sites=[fs_second_site]
        )
        r = await client.post(url, headers=h(fs_admin_token), json=body)
        assert r.json()["detail_code"] == "site_push.device_not_found"
        # two on this site
        await make_device(
            async_session, now, device_id="b" * 16 + "ABCDEF", sites=[fs_site]
        )
        await make_device(
            async_session, now, device_id="c" * 16 + "ABCDEF", sites=[fs_site]
        )
        r = await client.post(url, headers=h(fs_admin_token), json=body)
        assert r.status_code == 409
        assert r.json()["detail_code"] == "site_push.device_ambiguous"
        assert "ABCDEF" not in r.text.replace("device_ambiguous", "")

    async def test_invalid_device_target(self, client, fs_site, fs_admin_token):
        r = await client.post(
            self.url(fs_site), headers=h(fs_admin_token), json={"target": "device"}
        )
        assert r.status_code == 422
        assert r.json()["detail_code"] == "site_push.invalid_target"

    async def test_topic_confirmation(
        self, client, fs_site, fs_operator_token, fake_fcm
    ):
        r = await client.post(
            self.url(fs_site), headers=h(fs_operator_token), json={"target": "topic"}
        )
        assert r.json()["detail_code"] == "site_push.confirmation_required"
        r = await client.post(
            self.url(fs_site),
            headers=h(fs_operator_token),
            json={"target": "topic", "confirm_topic": "freespace-other"},
        )
        assert r.status_code == 422
        assert r.json()["detail_code"] == "site_push.confirmation_mismatch"
        assert fake_fcm.sent == []
        r = await client.post(
            self.url(fs_site),
            headers=h(fs_operator_token),
            json={"target": "topic", "confirm_topic": fs_site.fcm_topic},
        )
        assert r.status_code == 200
        assert [m.topic for m in fake_fcm.sent] == [fs_site.fcm_topic]

    async def test_unmanaged_site_works(
        self, client, async_session, test_organization, fs_admin_token, fake_fcm
    ):
        site = await make_site(
            async_session,
            test_organization,
            slug="shadow-x",
            name="Shadow",
            managed=False,
        )
        r = await client.post(
            self.url(site),
            headers=h(fs_admin_token),
            json={"target": "topic", "confirm_topic": site.fcm_topic},
        )
        assert r.status_code == 200
        assert len(fake_fcm.sent) == 1

    async def test_role_matrix_and_tenant(
        self,
        client,
        fs_site,
        fs_admin_token,
        fs_operator_token,
        fs_viewer_token,
        fs_second_org_admin_token,
        fake_fcm,
    ):
        body = {"target": "topic", "confirm_topic": fs_site.fcm_topic}
        assert (
            await client.post(self.url(fs_site), headers=h(fs_viewer_token), json=body)
        ).status_code == 403
        assert (
            await client.post(
                self.url(fs_site), headers=h(fs_operator_token), json=body
            )
        ).status_code == 200
        assert (
            await client.post(self.url(fs_site), headers=h(fs_admin_token), json=body)
        ).status_code == 200
        r = await client.post(
            self.url(fs_site), headers=h(fs_second_org_admin_token), json=body
        )
        assert r.status_code == 404
        assert len(fake_fcm.sent) == 2

    async def test_fcm_failure_is_logged(
        self, client, async_session, fs_site, fs_admin_token, fake_fcm
    ):
        fake_fcm.default_result = FcmSendResult(
            kind=FcmResultKind.FAILED, error_code="INVALID_ARGUMENT"
        )
        r = await client.post(
            self.url(fs_site),
            headers=h(fs_admin_token),
            json={"target": "topic", "confirm_topic": fs_site.fcm_topic},
        )
        assert r.status_code == 502
        assert r.json()["detail_code"] == "site_push.test_failed"
        ev = (
            await async_session.execute(
                select(SiteEvent).where(SiteEvent.type == EventType.TEST_PUSH.value)
            )
        ).scalar_one()
        assert ev.reason == "FAILED"
        assert ev.details["fcm_error_code"] == "INVALID_ARGUMENT"

    async def test_auth_failure_code(self, client, fs_site, fs_admin_token, fake_fcm):
        fake_fcm.default_result = FcmSendResult(kind=FcmResultKind.AUTH_FAILURE)
        r = await client.post(
            self.url(fs_site),
            headers=h(fs_admin_token),
            json={"target": "topic", "confirm_topic": fs_site.fcm_topic},
        )
        assert r.json()["detail_code"] == "site_push.fcm_auth_failure"


# ───────────────────────────── announcement ─────────────────────────────


class TestAnnouncement:
    def url(self, site):
        return f"{BASE}/{site.id}/announcements"

    async def test_admin_sends_one_topic_call(
        self, client, async_session, fs_site, fs_admin_token, fake_fcm
    ):
        r = await client.post(
            self.url(fs_site),
            headers=h(fs_admin_token),
            json={
                "message": "Level 2 closed today",
                "confirm_topic": fs_site.fcm_topic,
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["message_code"] == "site_push.announcement_sent"
        assert len(fake_fcm.sent) == 1
        msg = fake_fcm.sent[0]
        assert msg.topic == fs_site.fcm_topic and msg.token is None
        assert msg.payload["notification"]["body"] == "Level 2 closed today"
        ev = (
            await async_session.execute(
                select(SiteEvent).where(SiteEvent.type == EventType.ANNOUNCEMENT.value)
            )
        ).scalar_one()
        assert ev.rendered_body == "Level 2 closed today"
        assert ev.details["target"] == "topic"

    async def test_role_matrix_confirmation_tenant(
        self,
        client,
        fs_site,
        fs_admin_token,
        fs_operator_token,
        fs_viewer_token,
        fs_second_org_admin_token,
        fake_fcm,
    ):
        body = {"message": "Hi", "confirm_topic": fs_site.fcm_topic}
        for token in (fs_operator_token, fs_viewer_token):
            r = await client.post(self.url(fs_site), headers=h(token), json=body)
            assert r.status_code == 403
        r = await client.post(
            self.url(fs_site), headers=h(fs_second_org_admin_token), json=body
        )
        assert r.status_code == 404
        r = await client.post(
            self.url(fs_site),
            headers=h(fs_admin_token),
            json={"message": "Hi", "confirm_topic": "nope"},
        )
        assert r.json()["detail_code"] == "site_push.confirmation_mismatch"
        r = await client.post(
            self.url(fs_site), headers=h(fs_admin_token), json={"message": "Hi"}
        )
        assert r.json()["detail_code"] == "site_push.confirmation_required"
        assert fake_fcm.sent == []

    async def test_failure_logged(
        self, client, async_session, fs_site, fs_admin_token, fake_fcm
    ):
        fake_fcm.default_result = FcmSendResult(kind=FcmResultKind.RETRYABLE)
        r = await client.post(
            self.url(fs_site),
            headers=h(fs_admin_token),
            json={"message": "Hi", "confirm_topic": fs_site.fcm_topic},
        )
        assert r.status_code == 502
        assert r.json()["detail_code"] == "site_push.announcement_failed"
        ev = (
            await async_session.execute(
                select(SiteEvent).where(SiteEvent.type == EventType.ANNOUNCEMENT.value)
            )
        ).scalar_one()
        assert ev.reason == "RETRYABLE"
