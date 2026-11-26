"""M1: admin zones API: CRUD, settings validation, discovered-zone review,
tenant isolation, role matrix, audit + event."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from src.constants.freespace import EventType
from src.models.audit_log import AuditLog
from src.models.site_event import SiteEvent
from src.models.zone import Zone
from tests.freespace.conftest import make_zone


def url(site, zone=None) -> str:
    base = f"/api/v1/admin/sites/{site.id}/zones"
    return base if zone is None else f"{base}/{zone.id}"


def h(token: str) -> dict[str, str]:
    return {"Authorization": token}


async def zone_events(session, site):
    stmt = select(SiteEvent).where(
        SiteEvent.site_id == site.id, SiteEvent.type == EventType.CONFIG_CHANGED.value
    )
    return list((await session.execute(stmt.order_by(SiteEvent.occurred_at))).scalars())


class TestCrud:
    async def test_create_defaults(
        self, client, async_session, fs_site, fs_admin_token
    ):
        r = await client.post(
            url(fs_site),
            headers=h(fs_admin_token),
            json={"slug": "b9", "name": "Basement 9"},
        )
        assert r.status_code == 201, r.text
        z = r.json()["zone"]
        assert r.json()["message_code"] == "zone.created"
        assert (
            z["enabled"] is True
            and z["discovered"] is False
            and z["recommendable"] is True
        )
        assert (
            z["priority"],
            z["limited_pct"],
            z["full_pct"],
            z["full_min_free"],
            z["unknown_limit_pct"],
        ) == (100, 80, 95, 5, 25)
        assert z["advisory_pct"] is None and z["note"] == ""
        evs = await zone_events(async_session, fs_site)
        assert (
            len(evs) == 1
            and evs[0].zone_slug == "b9"
            and evs[0].reason == "ZONE_SETTINGS"
        )
        logs = (
            (
                await async_session.execute(
                    select(AuditLog).where(AuditLog.resource_id == uuid.UUID(z["id"]))
                )
            )
            .scalars()
            .all()
        )
        assert [log.action for log in logs] == ["CREATE"]

    async def test_list_ordered_and_filter(
        self, client, async_session, fs_site, fs_zones, fs_admin_token
    ):
        await make_zone(
            async_session,
            fs_site,
            "disc",
            name="Found",
            display_order=0,
            enabled=False,
            discovered=True,
        )
        r = await client.get(url(fs_site), headers=h(fs_admin_token))
        assert [z["slug"] for z in r.json()["items"]] == [
            "disc",
            "b1",
            "b2",
            "b3",
            "b4",
        ]
        assert r.json()["total"] == 5
        r = await client.get(
            url(fs_site), headers=h(fs_admin_token), params={"discovered": True}
        )
        assert [z["slug"] for z in r.json()["items"]] == ["disc"]

    async def test_get(self, client, fs_site, fs_zones, fs_admin_token):
        r = await client.get(url(fs_site, fs_zones["b1"]), headers=h(fs_admin_token))
        assert r.status_code == 200 and r.json()["name"] == "Basement 1"
        r = await client.get(
            f"{url(fs_site)}/{uuid.uuid4()}", headers=h(fs_admin_token)
        )
        assert (r.status_code, r.json()["detail_code"]) == (404, "zone.not_found")

    async def test_update_audits_and_events(
        self, client, async_session, fs_site, fs_zones, fs_admin_token
    ):
        r = await client.put(
            url(fs_site, fs_zones["b2"]),
            headers=h(fs_admin_token),
            json={
                "name": "Level 2",
                "priority": 5,
                "advisory_pct": 90,
                "recommendable": False,
            },
        )
        assert r.status_code == 200, r.text
        z = r.json()["zone"]
        assert (z["name"], z["priority"], z["advisory_pct"], z["recommendable"]) == (
            "Level 2",
            5,
            90,
            False,
        )
        assert z["limited_pct"] == 80 and r.json()["message_code"] == "zone.updated"
        evs = await zone_events(async_session, fs_site)
        assert len(evs) == 1 and evs[0].zone_slug == "b2"
        assert (
            evs[0].details["before"]["priority"] == 100
            and evs[0].details["after"]["priority"] == 5
        )
        logs = (
            (
                await async_session.execute(
                    select(AuditLog).where(AuditLog.resource_id == fs_zones["b2"].id)
                )
            )
            .scalars()
            .all()
        )
        assert logs[0].changes["name"] == {"old": "Basement 2", "new": "Level 2"}

    async def test_unset_advisory_pct_with_null(
        self, client, fs_site, fs_zones, fs_admin_token
    ):
        u = url(fs_site, fs_zones["b1"])
        await client.put(u, headers=h(fs_admin_token), json={"advisory_pct": 80})
        r = await client.put(u, headers=h(fs_admin_token), json={"advisory_pct": None})
        assert r.status_code == 200 and r.json()["zone"]["advisory_pct"] is None

    async def test_noop_update_writes_nothing(
        self, client, async_session, fs_site, fs_zones, fs_admin_token
    ):
        r = await client.put(
            url(fs_site, fs_zones["b1"]),
            headers=h(fs_admin_token),
            json={"priority": 100},
        )
        assert r.status_code == 200
        assert await zone_events(async_session, fs_site) == []

    async def test_soft_delete(
        self, client, async_session, fs_site, fs_zones, fs_admin_token
    ):
        r = await client.delete(url(fs_site, fs_zones["b4"]), headers=h(fs_admin_token))
        assert r.status_code == 200 and r.json()["message_code"] == "zone.deleted"
        await async_session.refresh(fs_zones["b4"])
        assert fs_zones["b4"].deleted_time is not None
        assert (
            await client.get(url(fs_site, fs_zones["b4"]), headers=h(fs_admin_token))
        ).status_code == 404
        assert (
            len(
                (await client.get(url(fs_site), headers=h(fs_admin_token))).json()[
                    "items"
                ]
            )
            == 3
        )
        # slug reusable
        r = await client.post(
            url(fs_site),
            headers=h(fs_admin_token),
            json={"slug": "b4", "name": "New B4"},
        )
        assert r.status_code == 201

    async def test_slug_conflict_and_invalid(
        self, client, fs_site, fs_zones, fs_admin_token
    ):
        r = await client.post(
            url(fs_site), headers=h(fs_admin_token), json={"slug": "b1", "name": "Dup"}
        )
        assert (r.status_code, r.json()["detail_code"]) == (409, "zone.slug_conflict")
        for slug in ("", "Bad Slug", "UP", "x" * 65):
            r = await client.post(
                url(fs_site),
                headers=h(fs_admin_token),
                json={"slug": slug, "name": "N"},
            )
            assert (r.status_code, r.json()["detail_code"]) == (
                422,
                "zone.invalid_slug",
            ), slug

    async def test_same_slug_allowed_in_other_site(
        self,
        client,
        async_session,
        fs_site,
        fs_second_site,
        fs_zones,
        fs_second_org_admin_token,
    ):
        r = await client.post(
            url(fs_second_site),
            headers=h(fs_second_org_admin_token),
            json={"slug": "b1", "name": "Mine"},
        )
        assert r.status_code == 201


class TestValidation:
    @pytest.mark.parametrize(
        "body",
        [
            {"limited_pct": 96},
            {"limited_pct": 0},
            {"full_pct": 101},
            {"full_pct": 70},  # below limited 80
            {"full_min_free": -1},
            {"unknown_limit_pct": 101},
            {"advisory_pct": 0},
            {"advisory_pct": 101},
            {"priority": -1},
            {"display_order": -1},
            {"name": ""},
            {"name": "x" * 256},
        ],
    )
    async def test_update_invalid_refused(
        self, client, async_session, fs_site, fs_zones, fs_admin_token, body
    ):
        r = await client.put(
            url(fs_site, fs_zones["b1"]), headers=h(fs_admin_token), json=body
        )
        assert r.status_code == 422, r.text
        assert r.json()["detail_code"] == "zone.invalid_settings"
        await async_session.refresh(fs_zones["b1"])
        assert fs_zones["b1"].limited_pct == 80 and fs_zones["b1"].name == "Basement 1"
        assert await zone_events(async_session, fs_site) == []

    async def test_create_invalid_refused(self, client, fs_site, fs_admin_token):
        r = await client.post(
            url(fs_site),
            headers=h(fs_admin_token),
            json={"slug": "z1", "name": "Z", "limited_pct": 99, "full_pct": 90},
        )
        assert (r.status_code, r.json()["detail_code"]) == (
            422,
            "zone.invalid_settings",
        )

    async def test_note_stored_not_trimmed(
        self, client, fs_site, fs_zones, fs_admin_token
    ):
        r = await client.put(
            url(fs_site, fs_zones["b1"]),
            headers=h(fs_admin_token),
            json={"note": "Sensed by cameras"},
        )
        assert r.json()["zone"]["note"] == "Sensed by cameras"


class TestDiscoveredReview:
    async def test_review_clears_flag(
        self, client, async_session, fs_site, fs_admin_token
    ):
        zone = await make_zone(
            async_session, fs_site, "newz", name="newz", enabled=False, discovered=True
        )
        r = await client.put(
            url(fs_site, zone),
            headers=h(fs_admin_token),
            json={"reviewed": True, "name": "Basement 5", "enabled": True},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["message_code"] == "zone.reviewed"
        assert (
            body["zone"]["discovered"] is False
            and body["zone"]["enabled"] is True
            and body["zone"]["name"] == "Basement 5"
        )
        evs = await zone_events(async_session, fs_site)
        assert evs[0].details["reviewed"] is True

    async def test_review_alone(self, client, async_session, fs_site, fs_admin_token):
        zone = await make_zone(
            async_session, fs_site, "newz", enabled=False, discovered=True
        )
        r = await client.put(
            url(fs_site, zone), headers=h(fs_admin_token), json={"reviewed": True}
        )
        assert (
            r.json()["zone"]["discovered"] is False
            and r.json()["zone"]["enabled"] is False
        )

    async def test_plain_update_keeps_discovered(
        self, client, async_session, fs_site, fs_admin_token
    ):
        zone = await make_zone(
            async_session, fs_site, "newz", enabled=False, discovered=True
        )
        r = await client.put(
            url(fs_site, zone), headers=h(fs_admin_token), json={"name": "Renamed"}
        )
        assert r.json()["zone"]["discovered"] is True


class TestRoleMatrix:
    async def test_matrix(
        self,
        client,
        fs_site,
        fs_zones,
        fs_admin_token,
        fs_operator_token,
        fs_viewer_token,
        fs_no_role_token,
        test_admin_token,
    ):
        cases = [
            (fs_admin_token, True, True),
            (test_admin_token, True, True),
            (fs_operator_token, True, False),
            (fs_viewer_token, True, False),
            (fs_no_role_token, False, False),
        ]
        z = fs_zones["b3"]
        for token, can_read, can_write in cases:
            for r in (
                await client.get(url(fs_site), headers=h(token)),
                await client.get(url(fs_site, z), headers=h(token)),
            ):
                assert (r.status_code == 200) is can_read
                if not can_read:
                    assert r.status_code == 403
            w = [
                await client.post(
                    url(fs_site),
                    headers=h(token),
                    json={"slug": f"n{uuid.uuid4().hex[:6]}", "name": "N"},
                ),
                await client.put(
                    url(fs_site, z), headers=h(token), json={"priority": 7}
                ),
            ]
            for r in w:
                assert (r.status_code in (200, 201)) is can_write, (
                    r.status_code,
                    r.text,
                )
                if not can_write:
                    assert r.status_code == 403
            if not can_write:
                assert (
                    await client.delete(url(fs_site, z), headers=h(token))
                ).status_code == 403
        # the admin deletes last
        assert (
            await client.delete(url(fs_site, z), headers=h(fs_admin_token))
        ).status_code == 200


class TestTenantIsolation:
    async def test_every_endpoint_404_for_other_tenant(
        self,
        client,
        async_session,
        fs_site,
        fs_zones,
        fs_second_site,
        fs_second_org_admin_token,
    ):
        tok = h(fs_second_org_admin_token)
        z = fs_zones["b1"]
        calls = [
            ("get", url(fs_site), None),
            ("post", url(fs_site), {"slug": "evil", "name": "E"}),
            ("get", url(fs_site, z), None),
            ("put", url(fs_site, z), {"name": "hacked"}),
            ("delete", url(fs_site, z), None),
        ]
        for method, u, body in calls:
            r = await getattr(client, method)(
                u, headers=tok, **({"json": body} if body else {})
            )
            assert (r.status_code, r.json()["detail_code"]) == (
                404,
                "site.not_found",
            ), (method, u)
        await async_session.refresh(z)
        assert z.name == "Basement 1" and z.deleted_time is None
        assert (
            await async_session.execute(select(Zone).where(Zone.slug == "evil"))
        ).first() is None

    async def test_foreign_zone_id_under_own_site_is_404(
        self,
        client,
        async_session,
        fs_site,
        fs_zones,
        fs_second_site,
        fs_second_org_admin_token,
    ):
        """A zone id of another tenant addressed through the caller's own site."""
        tok = h(fs_second_org_admin_token)
        foreign = fs_zones["b1"]
        base = f"/api/v1/admin/sites/{fs_second_site.id}/zones/{foreign.id}"
        assert (await client.get(base, headers=tok)).status_code == 404
        assert (
            await client.put(base, headers=tok, json={"name": "x"})
        ).status_code == 404
        assert (await client.delete(base, headers=tok)).status_code == 404
        r = await client.get(base, headers=tok)
        assert r.json()["detail_code"] == "zone.not_found"
        await async_session.refresh(foreign)
        assert foreign.deleted_time is None and foreign.name == "Basement 1"

    async def test_super_admin_reaches_any_tenant(
        self, client, fs_second_site, test_admin_token
    ):
        r = await client.post(
            url(fs_second_site),
            headers=h(test_admin_token),
            json={"slug": "sa", "name": "S"},
        )
        assert r.status_code == 201
