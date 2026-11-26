"""M1: admin sites / config / templates API: validation, tenant isolation,
role matrix, audit + CONFIG_CHANGED event, managed off->on reset."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from src.constants.freespace import EngineState, EventType
from src.models.audit_log import AuditLog
from src.models.site import Site
from src.models.site_engine_state import SiteEngineState
from src.models.site_event import SiteEvent
from src.models.site_message_template import SiteMessageTemplate
from src.models.zone import Zone
from tests.freespace.conftest import make_site


BASE = "/api/v1/admin/sites"


def h(token: str) -> dict[str, str]:
    return {"Authorization": token}


async def events(session, site, type_=EventType.CONFIG_CHANGED, reason=None):
    stmt = select(SiteEvent).where(
        SiteEvent.site_id == site.id, SiteEvent.type == type_.value
    )
    if reason:
        stmt = stmt.where(SiteEvent.reason == reason)
    return list((await session.execute(stmt.order_by(SiteEvent.occurred_at))).scalars())


async def audits(session, resource_id):
    stmt = select(AuditLog).where(AuditLog.resource_id == resource_id)
    return list((await session.execute(stmt)).scalars())


# ── role matrix ──────────────────────────────────────────────


class TestRoleMatrix:
    @pytest.mark.parametrize(
        "token_fixture,read,write",
        [
            ("fs_admin_token", True, True),
            ("fs_operator_token", True, False),
            ("fs_viewer_token", True, False),
            ("fs_no_role_token", False, False),
            ("test_admin_token", True, True),
        ],
    )
    async def test_matrix(
        self,
        client,
        fs_site,
        fs_admin_token,
        fs_operator_token,
        fs_viewer_token,
        fs_no_role_token,
        test_admin_token,
        token_fixture,
        read,
        write,
    ):
        token = {
            "fs_admin_token": fs_admin_token,
            "fs_operator_token": fs_operator_token,
            "fs_viewer_token": fs_viewer_token,
            "fs_no_role_token": fs_no_role_token,
            "test_admin_token": test_admin_token,
        }[token_fixture]
        sid = str(fs_site.id)
        reads = [
            f"{BASE}",
            f"{BASE}/{sid}",
            f"{BASE}/{sid}/config",
            f"{BASE}/{sid}/templates",
            f"{BASE}/{sid}/templates/SITE_CHANGE",
            f"{BASE}/{sid}/zones",
        ]
        for url in reads:
            r = await client.get(url, headers=h(token))
            assert (r.status_code == 200) is read, (url, r.status_code, r.text)
            if not read:
                assert r.status_code == 403
        tpl = {"title": "t", "body": "b"}
        writes = [
            ("post", BASE, {"slug": "new-site", "name": "N"}),
            ("put", f"{BASE}/{sid}", {"name": "X"}),
            ("put", f"{BASE}/{sid}/config", {"cooldown_s": 10}),
            (
                "put",
                f"{BASE}/{sid}/templates",
                {"templates": [{"advisory_type": "TEST", **tpl}]},
            ),
            ("put", f"{BASE}/{sid}/templates/TEST", tpl),
            ("post", f"{BASE}/{sid}/templates/TEST/reset", None),
            ("post", f"{BASE}/{sid}/zones", {"slug": "z9", "name": "Z"}),
            ("delete", f"{BASE}/{sid}", None),
        ]
        for method, url, body in writes:
            r = await getattr(client, method)(
                url, headers=h(token), **({"json": body} if body is not None else {})
            )
            if write:
                assert r.status_code in (200, 201), (method, url, r.text)
            else:
                assert r.status_code == 403, (method, url, r.status_code)

    async def test_unauthenticated(self, client, fs_site):
        assert (await client.get(BASE)).status_code in (401, 403)


# ── tenant isolation, every endpoint ─────────────────────────


class TestTenantIsolation:
    async def test_other_tenant_gets_404_everywhere(
        self, client, async_session, fs_site, fs_second_site, fs_second_org_admin_token
    ):
        tok = h(fs_second_org_admin_token)
        sid = str(fs_site.id)  # belongs to test_organization
        tpl = {"title": "t", "body": "b"}
        calls = [
            ("get", f"{BASE}/{sid}", None),
            ("put", f"{BASE}/{sid}", {"name": "hack"}),
            ("delete", f"{BASE}/{sid}", None),
            ("get", f"{BASE}/{sid}/config", None),
            ("put", f"{BASE}/{sid}/config", {"managed": False}),
            ("get", f"{BASE}/{sid}/templates", None),
            (
                "put",
                f"{BASE}/{sid}/templates",
                {"templates": [{"advisory_type": "TEST", **tpl}]},
            ),
            ("get", f"{BASE}/{sid}/templates/TEST", None),
            ("put", f"{BASE}/{sid}/templates/TEST", tpl),
            ("post", f"{BASE}/{sid}/templates/TEST/reset", None),
        ]
        for method, url, body in calls:
            r = await getattr(client, method)(
                url, headers=tok, **({"json": body} if body is not None else {})
            )
            assert r.status_code == 404, (method, url, r.status_code, r.text)
            assert r.json()["detail_code"] == "site.not_found"
        # untouched
        await async_session.refresh(fs_site)
        assert (
            fs_site.name == "Alice Lane"
            and fs_site.managed
            and fs_site.deleted_time is None
        )
        assert await events(async_session, fs_site) == []

    async def test_list_only_own_tenant(
        self, client, fs_site, fs_second_site, fs_second_org_admin_token, fs_admin_token
    ):
        r = await client.get(BASE, headers=h(fs_second_org_admin_token))
        assert [s["slug"] for s in r.json()["items"]] == [fs_second_site.slug]
        r = await client.get(BASE, headers=h(fs_admin_token))
        assert [s["slug"] for s in r.json()["items"]] == [fs_site.slug]

    async def test_super_admin_sees_all_orgs(
        self, client, fs_site, fs_second_site, test_admin_token
    ):
        r = await client.get(BASE, headers=h(test_admin_token))
        assert {s["slug"] for s in r.json()["items"]} == {
            fs_site.slug,
            fs_second_site.slug,
        }
        r = await client.get(f"{BASE}/{fs_second_site.id}", headers=h(test_admin_token))
        assert r.status_code == 200
        r = await client.get(
            BASE,
            headers=h(test_admin_token),
            params={"organization_id": str(fs_second_site.organization_id)},
        )
        assert [s["slug"] for s in r.json()["items"]] == [fs_second_site.slug]

    async def test_create_cannot_target_other_org_unless_super_admin(
        self,
        client,
        async_session,
        second_organization,
        test_organization,
        fs_admin_token,
        test_admin_token,
    ):
        r = await client.post(
            BASE,
            headers=h(fs_admin_token),
            json={
                "slug": "sneaky",
                "name": "S",
                "organization_id": str(second_organization.id),
            },
        )
        assert r.status_code == 404
        assert r.json()["detail_code"] == "site.organization_not_found"
        r = await client.post(
            BASE,
            headers=h(test_admin_token),
            json={
                "slug": "by-super",
                "name": "S",
                "organization_id": str(second_organization.id),
            },
        )
        assert r.status_code == 201
        assert r.json()["site"]["organization_id"] == str(second_organization.id)
        r = await client.post(
            BASE,
            headers=h(test_admin_token),
            json={"slug": "bad-org", "name": "S", "organization_id": str(uuid.uuid4())},
        )
        assert r.status_code == 404
        assert r.json()["detail_code"] == "site.organization_not_found"

    async def test_nonexistent_site_404(self, client, fs_admin_token):
        r = await client.get(f"{BASE}/{uuid.uuid4()}", headers=h(fs_admin_token))
        assert r.status_code == 404


# ── sites CRUD ───────────────────────────────────────────────


class TestSitesCrud:
    async def test_create_uses_bootstrap(
        self, client, async_session, fs_admin_token, test_organization, fixed_clock
    ):
        r = await client.post(
            BASE,
            headers=h(fs_admin_token),
            json={"slug": "new-site", "name": "  New  "},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["message_code"] == "site.created"
        site_json = body["site"]
        assert site_json["name"] == "New"
        assert site_json["managed"] is False and site_json["listed"] is False
        assert site_json["fcm_topic"] == "freespace-new-site"
        assert site_json["time_zone"] == "Africa/Johannesburg"
        assert site_json["organization_id"] == str(test_organization.id)
        sid = uuid.UUID(site_json["id"])
        state = (
            (
                await async_session.execute(
                    select(SiteEngineState).where(SiteEngineState.site_id == sid)
                )
            )
            .scalars()
            .first()
        )
        assert state is not None and state.state == EngineState.IDLE
        tpls = (
            (
                await async_session.execute(
                    select(SiteMessageTemplate).where(
                        SiteMessageTemplate.site_id == sid
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(tpls) == 5
        assert all(t.title == "{site} parking" for t in tpls)
        site = await async_session.get(Site, sid)
        assert len(await events(async_session, site)) == 1
        logs = await audits(async_session, sid)
        assert [log.action for log in logs] == ["CREATE"]

    @pytest.mark.parametrize(
        "slug", ["", "Upper", "-lead", "has space", "a" * 65, "über"]
    )
    async def test_invalid_slug(self, client, fs_admin_token, slug):
        r = await client.post(
            BASE, headers=h(fs_admin_token), json={"slug": slug, "name": "N"}
        )
        assert r.status_code == 422
        assert r.json()["detail_code"] == "site.invalid_slug"

    async def test_slug_conflict_global(
        self, client, fs_site, fs_second_org_admin_token
    ):
        r = await client.post(
            BASE,
            headers=h(fs_second_org_admin_token),
            json={"slug": fs_site.slug, "name": "N"},
        )
        assert r.status_code == 409
        assert r.json()["detail_code"] == "site.slug_conflict"

    async def test_invalid_time_zone_and_topic(self, client, fs_admin_token):
        r = await client.post(
            BASE,
            headers=h(fs_admin_token),
            json={"slug": "a1", "name": "N", "time_zone": "Mars/Base"},
        )
        assert (r.status_code, r.json()["detail_code"]) == (
            422,
            "site.invalid_time_zone",
        )
        r = await client.post(
            BASE,
            headers=h(fs_admin_token),
            json={"slug": "a1", "name": "N", "fcm_topic": "bad topic!"},
        )
        assert (r.status_code, r.json()["detail_code"]) == (422, "site.invalid_topic")

    async def test_get_and_update_site(
        self, client, async_session, fs_site, fs_admin_token
    ):
        r = await client.get(f"{BASE}/{fs_site.id}", headers=h(fs_admin_token))
        assert r.status_code == 200 and r.json()["slug"] == fs_site.slug
        r = await client.put(
            f"{BASE}/{fs_site.id}",
            headers=h(fs_admin_token),
            json={"name": "Renamed", "fcm_topic": "t-1"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["site"]["name"] == "Renamed"
        assert r.json()["message_code"] == "site.updated"
        assert r.json()["site"]["slug"] == fs_site.slug
        assert len(await events(async_session, fs_site)) == 1
        logs = await audits(async_session, fs_site.id)
        assert logs and logs[0].changes["name"] == {
            "old": "Alice Lane",
            "new": "Renamed",
        }

    async def test_slug_immutable(self, client, fs_site, fs_admin_token):
        r = await client.put(
            f"{BASE}/{fs_site.id}", headers=h(fs_admin_token), json={"slug": "other"}
        )
        assert r.status_code == 422

    async def test_soft_delete(
        self, client, async_session, fs_site, fs_zones, fs_admin_token
    ):
        r = await client.delete(f"{BASE}/{fs_site.id}", headers=h(fs_admin_token))
        assert r.status_code == 200 and r.json()["message_code"] == "site.deleted"
        await async_session.refresh(fs_site)
        assert fs_site.deleted_time is not None and fs_site.managed is False
        zones = (
            (
                await async_session.execute(
                    select(Zone).where(Zone.site_id == fs_site.id)
                )
            )
            .scalars()
            .all()
        )
        assert zones and all(z.deleted_time is not None for z in zones)
        assert (
            await client.get(f"{BASE}/{fs_site.id}", headers=h(fs_admin_token))
        ).status_code == 404
        assert (await client.get(BASE, headers=h(fs_admin_token))).json()["total"] == 0
        # slug is reusable after soft delete
        r = await client.post(
            BASE,
            headers=h(fs_admin_token),
            json={"slug": fs_site.slug, "name": "Again"},
        )
        assert r.status_code == 201

    async def test_pagination(
        self, client, async_session, test_organization, fs_admin_token
    ):
        for i in range(3):
            await make_site(
                async_session, test_organization, slug=f"p{i}", name=f"P{i}"
            )
        r = await client.get(
            BASE, headers=h(fs_admin_token), params={"limit": 2, "offset": 2}
        )
        body = r.json()
        assert body["total"] == 3 and len(body["items"]) == 1 and body["limit"] == 2


# ── config ───────────────────────────────────────────────────


class TestConfig:
    async def test_get_config_defaults(self, client, fs_site, fs_admin_token):
        r = await client.get(f"{BASE}/{fs_site.id}/config", headers=h(fs_admin_token))
        body = r.json()
        assert r.status_code == 200
        assert body["trigger_pct"] == 90 and body["reset_pct"] == 80
        assert body["notification_window"] == [
            {"weekdays": [1, 2, 3, 4, 5], "start": "06:00", "end": "10:00"}
        ]
        assert body["site_id"] == str(fs_site.id)

    async def test_partial_put_merges_and_audits(
        self, client, async_session, fs_site, fs_admin_token, fs_admin_user
    ):
        r = await client.put(
            f"{BASE}/{fs_site.id}/config",
            headers=h(fs_admin_token),
            json={"trigger_pct": 85, "notification_window": []},
        )
        assert r.status_code == 200, r.text
        cfg = r.json()["config"]
        assert r.json()["message_code"] == "site.config_updated"
        assert (
            cfg["trigger_pct"] == 85
            and cfg["reset_pct"] == 80
            and cfg["notification_window"] == []
        )
        await async_session.refresh(fs_site)
        assert fs_site.trigger_pct == 85 and fs_site.notification_window == []
        # event
        evs = await events(async_session, fs_site, reason="SITE_SETTINGS")
        assert len(evs) == 1
        assert evs[0].details["before"]["trigger_pct"] == 90
        assert evs[0].details["after"]["trigger_pct"] == 85
        assert evs[0].details["actor_id"] == str(fs_admin_user.id)
        # audit
        logs = await audits(async_session, fs_site.id)
        assert len(logs) == 1
        assert logs[0].actor_id == fs_admin_user.id and logs[0].action == "UPDATE"
        assert logs[0].changes["trigger_pct"] == {"old": 90, "new": 85}

    async def test_noop_put_writes_nothing(
        self, client, async_session, fs_site, fs_admin_token
    ):
        r = await client.put(
            f"{BASE}/{fs_site.id}/config",
            headers=h(fs_admin_token),
            json={"trigger_pct": 90},
        )
        assert r.status_code == 200
        assert await events(async_session, fs_site) == []
        assert await audits(async_session, fs_site.id) == []

    @pytest.mark.parametrize(
        "body,code",
        [
            ({"trigger_pct": 0}, "site.invalid_settings"),
            ({"trigger_pct": 101}, "site.invalid_settings"),
            ({"reset_pct": 90}, "site.invalid_settings"),
            ({"trigger_pct": 75}, "site.invalid_settings"),
            ({"change_points": 51}, "site.invalid_settings"),
            ({"change_direction": "DOWN"}, "site.invalid_settings"),
            ({"stabilisation_s": 3601}, "site.invalid_settings"),
            ({"recommendation_margin": -1}, "site.invalid_settings"),
            ({"stale_limit_s": 119}, "site.invalid_settings"),
            ({"zone_reset_gap": 0}, "site.invalid_settings"),
            ({"push_expiry_s": 59}, "site.invalid_settings"),
            ({"push_expiry_s": 86401}, "site.invalid_settings"),
            ({"cooldown_s": -5}, "site.invalid_settings"),
            ({"time_zone": "Nowhere/City"}, "site.invalid_time_zone"),
            (
                {
                    "notification_window": [
                        {"weekdays": [1], "start": "22:00", "end": "02:00"}
                    ]
                },
                "site.invalid_notification_window",
            ),
            (
                {
                    "notification_window": [
                        {"weekdays": [9], "start": "06:00", "end": "07:00"}
                    ]
                },
                "site.invalid_notification_window",
            ),
        ],
    )
    async def test_invalid_refused_with_code_and_nothing_written(
        self, client, async_session, fs_site, fs_admin_token, body, code
    ):
        r = await client.put(
            f"{BASE}/{fs_site.id}/config", headers=h(fs_admin_token), json=body
        )
        assert r.status_code == 422, r.text
        assert r.json()["detail_code"] == code
        await async_session.refresh(fs_site)
        assert fs_site.trigger_pct == 90 and fs_site.reset_pct == 80
        assert await events(async_session, fs_site) == []

    async def test_unknown_field_422(self, client, fs_site, fs_admin_token):
        r = await client.put(
            f"{BASE}/{fs_site.id}/config", headers=h(fs_admin_token), json={"bogus": 1}
        )
        assert r.status_code == 422

    async def test_valid_boundary_values_accepted(
        self, client, fs_site, fs_admin_token
    ):
        r = await client.put(
            f"{BASE}/{fs_site.id}/config",
            headers=h(fs_admin_token),
            json={
                "trigger_pct": 100,
                "reset_pct": 99,
                "stale_limit_s": 120,
                "push_expiry_s": 86400,
                "time_zone": "UTC",
            },
        )
        assert r.status_code == 200, r.text

    async def test_other_changes_do_not_reset_engine_state(
        self, client, async_session, fs_site, fs_admin_token, fixed_clock
    ):
        state = (
            (
                await async_session.execute(
                    select(SiteEngineState).where(SiteEngineState.site_id == fs_site.id)
                )
            )
            .scalars()
            .first()
        )
        cycle = uuid.uuid4()
        state.state = EngineState.ACTIVE.value
        state.cycle_id = cycle
        state.last_notified_pct = 91.0
        await async_session.commit()
        r = await client.put(
            f"{BASE}/{fs_site.id}/config",
            headers=h(fs_admin_token),
            json={"trigger_pct": 85, "listed": False},
        )
        assert r.status_code == 200
        await async_session.refresh(state)
        assert (
            state.state == "ACTIVE"
            and state.cycle_id == cycle
            and state.last_notified_pct == 91.0
        )


# ── managed off -> on ────────────────────────────────────────


class TestManaged:
    async def _active_state(self, session, site):
        state = (
            (
                await session.execute(
                    select(SiteEngineState).where(SiteEngineState.site_id == site.id)
                )
            )
            .scalars()
            .first()
        )
        state.state = EngineState.ACTIVE.value
        state.cycle_id = uuid.uuid4()
        state.last_notified_pct = 93.5
        state.last_notified_zone_slug = "b3"
        state.last_sent_fingerprint = "abc"
        await session.commit()
        return state

    async def test_off_then_on_resets_cycle(
        self, client, async_session, fs_site, fs_admin_token, fixed_clock
    ):
        state = await self._active_state(async_session, fs_site)
        old_cycle = state.cycle_id
        url = f"{BASE}/{fs_site.id}/config"

        r = await client.put(url, headers=h(fs_admin_token), json={"managed": False})
        assert r.status_code == 200
        await async_session.refresh(state)
        assert state.state == "ACTIVE", "switching off alone does not reset"
        off = await events(async_session, fs_site, reason="MANAGED_OFF")
        assert len(off) == 1

        fixed_clock.advance(600)
        r = await client.put(url, headers=h(fs_admin_token), json={"managed": True})
        assert r.status_code == 200
        await async_session.refresh(state)
        assert state.state == "IDLE"
        assert state.cycle_id != old_cycle
        assert state.last_notified_pct is None
        assert state.last_notified_zone_slug is None
        assert state.last_sent_fingerprint is None
        assert state.pending_since is None
        on = await events(async_session, fs_site, reason="MANAGED_ON")
        assert len(on) == 1 and on[0].details["after"] == {"managed": True}
        restarted = await events(
            async_session, fs_site, EventType.STATE_CHANGE, "CYCLE_RESTARTED"
        )
        assert len(restarted) == 1
        assert len(await audits(async_session, fs_site.id)) == 2

    async def test_managed_on_from_new_site_logged(
        self, client, async_session, fs_admin_token
    ):
        r = await client.post(
            BASE, headers=h(fs_admin_token), json={"slug": "fresh", "name": "F"}
        )
        sid = r.json()["site"]["id"]
        r = await client.put(
            f"{BASE}/{sid}/config", headers=h(fs_admin_token), json={"managed": True}
        )
        assert r.status_code == 200 and r.json()["config"]["managed"] is True
        site = await async_session.get(Site, uuid.UUID(sid))
        assert len(await events(async_session, site, reason="MANAGED_ON")) == 1

    async def test_managed_unchanged_does_not_reset(
        self, client, async_session, fs_site, fs_admin_token
    ):
        state = await self._active_state(async_session, fs_site)
        r = await client.put(
            f"{BASE}/{fs_site.id}/config",
            headers=h(fs_admin_token),
            json={"managed": True},
        )
        assert r.status_code == 200
        await async_session.refresh(state)
        assert state.state == "ACTIVE"


# ── templates ────────────────────────────────────────────────


class TestTemplates:
    async def test_list_defaults(self, client, fs_site, fs_admin_token):
        r = await client.get(
            f"{BASE}/{fs_site.id}/templates", headers=h(fs_admin_token)
        )
        items = {i["advisory_type"]: i for i in r.json()["items"]}
        assert set(items) == {
            "SITE_INITIAL",
            "SITE_CHANGE",
            "ZONE_ADVISORY",
            "RECOVERY",
            "TEST",
        }
        assert items["ZONE_ADVISORY"]["allowed_placeholders"] == [
            "fullZone",
            "occupancyPct",
            "site",
            "topZones",
            "zone",
        ]
        assert items["TEST"]["allowed_placeholders"] == ["site"]
        assert items["SITE_CHANGE"]["title"] == "{site} parking"

    async def test_put_one_audits_and_events(
        self, client, async_session, fs_site, fs_admin_token
    ):
        r = await client.put(
            f"{BASE}/{fs_site.id}/templates/SITE_CHANGE",
            headers=h(fs_admin_token),
            json={"title": "{site}", "body": "Go to {zone} ({occupancyPct}%)"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["message_code"] == "site_template.updated"
        assert r.json()["template"]["body"] == "Go to {zone} ({occupancyPct}%)"
        r = await client.get(
            f"{BASE}/{fs_site.id}/templates/SITE_CHANGE", headers=h(fs_admin_token)
        )
        assert r.json()["title"] == "{site}"
        assert len(await events(async_session, fs_site, reason="TEMPLATES")) == 1
        assert len(await audits(async_session, fs_site.id)) == 1
        rows = (
            (
                await async_session.execute(
                    select(SiteMessageTemplate).where(
                        SiteMessageTemplate.site_id == fs_site.id,
                        SiteMessageTemplate.advisory_type == "SITE_CHANGE",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1

    async def test_bulk_put_is_atomic(
        self, client, async_session, fs_site, fs_admin_token
    ):
        r = await client.put(
            f"{BASE}/{fs_site.id}/templates",
            headers=h(fs_admin_token),
            json={
                "templates": [
                    {"advisory_type": "RECOVERY", "title": "ok", "body": "fine {site}"},
                    {
                        "advisory_type": "SITE_CHANGE",
                        "title": "ok",
                        "body": "bad {fullZone}",
                    },
                ]
            },
        )
        assert r.status_code == 422
        assert r.json()["detail_code"] == "site_template.invalid_placeholder"
        r = await client.get(
            f"{BASE}/{fs_site.id}/templates/RECOVERY", headers=h(fs_admin_token)
        )
        assert r.json()["title"] == "{site} parking"
        r = await client.put(
            f"{BASE}/{fs_site.id}/templates",
            headers=h(fs_admin_token),
            json={
                "templates": [
                    {"advisory_type": "RECOVERY", "title": "ok", "body": "fine {site}"},
                    {
                        "advisory_type": "ZONE_ADVISORY",
                        "title": "{fullZone}",
                        "body": "x {fullZone}",
                    },
                ]
            },
        )
        assert r.status_code == 200
        assert r.json()["message_code"] == "site_template.updated"
        assert len(r.json()["items"]) == 5
        assert len(await events(async_session, fs_site, reason="TEMPLATES")) == 1

    @pytest.mark.parametrize(
        "advisory_type,title,body,code",
        [
            ("SITE_CHANGE", "{fullZone}", "b", "site_template.invalid_placeholder"),
            ("SITE_INITIAL", "t", "{fullZone}", "site_template.invalid_placeholder"),
            ("RECOVERY", "t", "{nope}", "site_template.invalid_placeholder"),
            ("TEST", "t", "{zone}", "site_template.invalid_placeholder"),
            ("SITE_CHANGE", "", "b", "site_template.invalid"),
            ("SITE_CHANGE", "t", "   ", "site_template.invalid"),
            ("SITE_CHANGE", "t" * 256, "b", "site_template.invalid"),
        ],
    )
    async def test_invalid_template_rejected(
        self, client, fs_site, fs_admin_token, advisory_type, title, body, code
    ):
        r = await client.put(
            f"{BASE}/{fs_site.id}/templates/{advisory_type}",
            headers=h(fs_admin_token),
            json={"title": title, "body": body},
        )
        assert r.status_code == 422, r.text
        assert r.json()["detail_code"] == code

    async def test_unknown_type(self, client, fs_site, fs_admin_token):
        r = await client.get(
            f"{BASE}/{fs_site.id}/templates/NOPE", headers=h(fs_admin_token)
        )
        assert (r.status_code, r.json()["detail_code"]) == (
            404,
            "site_template.unknown_type",
        )
        r = await client.put(
            f"{BASE}/{fs_site.id}/templates",
            headers=h(fs_admin_token),
            json={"templates": [{"advisory_type": "NOPE", "title": "t", "body": "b"}]},
        )
        assert (r.status_code, r.json()["detail_code"]) == (
            422,
            "site_template.unknown_type",
        )

    async def test_reset_to_default(
        self, client, async_session, fs_site, fs_admin_token
    ):
        url = f"{BASE}/{fs_site.id}/templates/RECOVERY"
        await client.put(
            url, headers=h(fs_admin_token), json={"title": "x", "body": "y"}
        )
        r = await client.post(f"{url}/reset", headers=h(fs_admin_token))
        assert (
            r.status_code == 200 and r.json()["message_code"] == "site_template.reset"
        )
        assert r.json()["template"]["title"] == "{site} parking"
        assert "improved at {site}" in r.json()["template"]["body"]
        assert len(await events(async_session, fs_site, reason="TEMPLATES")) == 2

    async def test_other_sites_templates_untouched(
        self, client, async_session, fs_site, fs_second_site, fs_admin_token
    ):
        await client.put(
            f"{BASE}/{fs_site.id}/templates/TEST",
            headers=h(fs_admin_token),
            json={"title": "x", "body": "y"},
        )
        row = (
            (
                await async_session.execute(
                    select(SiteMessageTemplate).where(
                        SiteMessageTemplate.site_id == fs_second_site.id,
                        SiteMessageTemplate.advisory_type == "TEST",
                    )
                )
            )
            .scalars()
            .first()
        )
        assert row.title == "{site} parking"
