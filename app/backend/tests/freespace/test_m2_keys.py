"""M2: ingest-key and app-key admin API (BF-9, BF-10a, BF-10b)."""

from __future__ import annotations

from datetime import timedelta
import re
import uuid

from sqlalchemy import select

from src.api.freespace_deps import get_ingest_site
from src.models.audit_log import AuditLog
from src.models.ingest_key import IngestKey
from src.services.freespace.keys import hash_key
from tests.freespace.conftest import make_app_key, make_ingest_key


KEY_RE = re.compile(r"^fsk_[A-Za-z0-9_-]{43}$")
APP_KEY_RE = re.compile(r"^fsa_[A-Za-z0-9_-]{43}$")
BF10A_RE = re.compile(r"^[\x21-\x7e]{1,512}$")


def ik(site_id) -> str:
    return f"/api/v1/admin/sites/{site_id}/ingest-keys"


async def _create(client, token, site, **body):
    body.setdefault("name", "ParkIT")
    return await client.post(ik(site.id), json=body, headers={"Authorization": token})


class TestCreateIngestKey:
    async def test_format_and_shown_once(
        self, client, async_session, fs_site, fs_admin_token
    ):
        resp = await _create(client, fs_admin_token, fs_site)
        assert resp.status_code == 201
        data = resp.json()
        assert KEY_RE.match(data["key"]) and BF10A_RE.match(data["key"])
        assert data["key_hint"] == data["key"][-4:]
        assert "key_hash" not in data
        assert data["message_code"]
        row = (
            await async_session.execute(
                select(IngestKey).where(IngestKey.id == uuid.UUID(data["id"]))
            )
        ).scalar_one()
        assert row.key_hash == hash_key(data["key"])
        assert data["key"] not in (row.key_hash, row.key_hint, row.name)

        listing = await client.get(
            ik(fs_site.id), headers={"Authorization": fs_admin_token}
        )
        assert listing.status_code == 200
        text = listing.text
        assert data["key"] not in text and row.key_hash not in text
        item = listing.json()["items"][0]
        assert {
            "name",
            "key_hint",
            "created_time",
            "expires_at",
            "revoked_at",
            "last_used_at",
            "last_used_ip",
        } <= set(item)
        assert "key" not in item

    async def test_audit_logged_without_plaintext(
        self, client, async_session, fs_site, fs_admin_token
    ):
        data = (await _create(client, fs_admin_token, fs_site)).json()
        revoke = await client.post(
            f"{ik(fs_site.id)}/{data['id']}/revoke",
            headers={"Authorization": fs_admin_token},
        )
        assert revoke.status_code == 200
        logs = (
            (
                await async_session.execute(
                    select(AuditLog).where(AuditLog.resource_type == "ingest_key")
                )
            )
            .scalars()
            .all()
        )
        assert len(logs) == 2
        assert data["key"] not in str([log.changes for log in logs])

    async def test_expiry(self, client, fs_site, fs_admin_token, fixed_clock):
        future = (fixed_clock.now() + timedelta(days=30)).isoformat()
        ok = await _create(client, fs_admin_token, fs_site, expires_at=future)
        assert ok.status_code == 201
        assert ok.json()["expires_at"].startswith("2026-12-24T05:45:00")
        past = (fixed_clock.now() - timedelta(days=1)).isoformat()
        bad = await _create(client, fs_admin_token, fs_site, expires_at=past)
        assert bad.status_code == 400
        assert bad.json()["detail_code"] == "ingest_key.invalid_expiry"

    async def test_validation(self, client, fs_site, fs_admin_token):
        resp = await _create(client, fs_admin_token, fs_site, name="")
        assert resp.status_code == 422


class TestKeyLifecycleOnIngestAuth:
    async def test_two_keys_and_revocation_effect(
        self, client, async_session, fs_site, fs_admin_token, fixed_clock
    ):
        from fastapi import Depends

        from main import app

        @app.get("/__m2_probe")
        async def probe(auth=Depends(get_ingest_site)):
            return {"slug": auth.site.slug}

        try:
            k1 = (await _create(client, fs_admin_token, fs_site, name="old")).json()
            k2 = (await _create(client, fs_admin_token, fs_site, name="new")).json()
            for k in (k1, k2):
                r = await client.get(
                    "/__m2_probe", headers={"Authorization": f"Bearer {k['key']}"}
                )
                assert r.status_code == 200
            rv = await client.post(
                f"{ik(fs_site.id)}/{k1['id']}/revoke",
                headers={"Authorization": fs_admin_token},
            )
            assert rv.status_code == 200
            assert rv.json()["key"]["revoked_at"]
            r1 = await client.get(
                "/__m2_probe", headers={"Authorization": f"Bearer {k1['key']}"}
            )
            assert r1.status_code == 401
            assert r1.json()["detail_code"] == "ingest.key_revoked"
            r2 = await client.get(
                "/__m2_probe", headers={"Authorization": f"Bearer {k2['key']}"}
            )
            assert r2.status_code == 200
            # last use is recorded and listed
            listing = (
                await client.get(
                    ik(fs_site.id), headers={"Authorization": fs_admin_token}
                )
            ).json()["items"]
            used = {i["name"]: i for i in listing}
            assert used["new"]["last_used_at"] is not None
            # expiry
            exp = (
                await _create(
                    client,
                    fs_admin_token,
                    fs_site,
                    name="exp",
                    expires_at=(fixed_clock.now() + timedelta(hours=1)).isoformat(),
                )
            ).json()
            hdr = {"Authorization": f"Bearer {exp['key']}"}
            assert (await client.get("/__m2_probe", headers=hdr)).status_code == 200
            fixed_clock.advance(7200)
            r = await client.get("/__m2_probe", headers=hdr)
            assert r.status_code == 401
            assert r.json()["detail_code"] == "ingest.key_expired"
        finally:
            app.router.routes = [
                r for r in app.router.routes if getattr(r, "path", "") != "/__m2_probe"
            ]

    async def test_revoke_twice_conflicts(self, client, fs_site, fs_admin_token):
        k = (await _create(client, fs_admin_token, fs_site)).json()
        url = f"{ik(fs_site.id)}/{k['id']}/revoke"
        h = {"Authorization": fs_admin_token}
        assert (await client.post(url, headers=h)).status_code == 200
        again = await client.post(url, headers=h)
        assert again.status_code == 409
        assert again.json()["detail_code"] == "ingest_key.already_revoked"

    async def test_revoke_unknown_key(self, client, fs_site, fs_admin_token):
        r = await client.post(
            f"{ik(fs_site.id)}/{uuid.uuid4()}/revoke",
            headers={"Authorization": fs_admin_token},
        )
        assert r.status_code == 404
        assert r.json()["detail_code"] == "ingest_key.not_found"


class TestIngestKeyTenancyAndRoles:
    async def test_cross_tenant_is_404_everywhere(
        self, client, async_session, fs_second_site, fs_admin_token
    ):
        _, key = await make_ingest_key(async_session, fs_second_site)
        h = {"Authorization": fs_admin_token}
        assert (await client.get(ik(fs_second_site.id), headers=h)).status_code == 404
        r = await client.post(ik(fs_second_site.id), json={"name": "x"}, headers=h)
        assert r.status_code == 404
        r = await client.post(f"{ik(fs_second_site.id)}/{key.id}/revoke", headers=h)
        assert r.status_code == 404
        await async_session.refresh(key)
        assert key.revoked_at is None

    async def test_key_of_other_site_not_revocable_via_own_site(
        self, client, async_session, fs_site, fs_second_site, fs_admin_token
    ):
        _, key = await make_ingest_key(async_session, fs_second_site)
        r = await client.post(
            f"{ik(fs_site.id)}/{key.id}/revoke",
            headers={"Authorization": fs_admin_token},
        )
        assert r.status_code == 404

    async def test_second_org_admin_cannot_touch_first_site(
        self, client, fs_site, fs_second_org_admin_token
    ):
        h = {"Authorization": fs_second_org_admin_token}
        assert (await client.get(ik(fs_site.id), headers=h)).status_code == 404

    async def test_super_admin_sees_all(
        self, client, async_session, fs_site, fs_second_site, test_admin_token
    ):
        await make_ingest_key(async_session, fs_second_site)
        h = {"Authorization": test_admin_token}
        assert (
            len((await client.get(ik(fs_second_site.id), headers=h)).json()["items"])
            == 1
        )
        r = await client.post(ik(fs_site.id), json={"name": "x"}, headers=h)
        assert r.status_code == 201

    async def test_unknown_site_404(self, client, fs_admin_token):
        r = await client.get(
            ik(uuid.uuid4()), headers={"Authorization": fs_admin_token}
        )
        assert r.status_code == 404

    async def test_role_matrix(
        self,
        client,
        async_session,
        fs_site,
        fs_admin_token,
        fs_operator_token,
        fs_viewer_token,
        fs_no_role_token,
    ):
        _, key = await make_ingest_key(async_session, fs_site)
        # list needs sites:read
        for token, expected in (
            (fs_admin_token, 200),
            (fs_operator_token, 200),
            (fs_viewer_token, 200),
            (fs_no_role_token, 403),
        ):
            r = await client.get(ik(fs_site.id), headers={"Authorization": token})
            assert r.status_code == expected, token
        # create/revoke need site_keys:write
        for token in (fs_operator_token, fs_viewer_token, fs_no_role_token):
            h = {"Authorization": token}
            assert (
                await client.post(ik(fs_site.id), json={"name": "x"}, headers=h)
            ).status_code == 403
            assert (
                await client.post(f"{ik(fs_site.id)}/{key.id}/revoke", headers=h)
            ).status_code == 403
        await async_session.refresh(key)
        assert key.revoked_at is None

    async def test_unauthenticated(self, client, fs_site):
        assert (await client.get(ik(fs_site.id))).status_code in (401, 403)


class TestAppKeys:
    async def test_create_list_revoke_and_cache(
        self, client, async_session, test_admin_token, fs_redis
    ):
        h = {"Authorization": test_admin_token}
        k1 = (
            await client.post("/api/v1/admin/app-keys", json={"name": "a1"}, headers=h)
        ).json()
        k2 = (
            await client.post("/api/v1/admin/app-keys", json={"name": "a2"}, headers=h)
        ).json()
        assert APP_KEY_RE.match(k1["key"]) and APP_KEY_RE.match(k2["key"])
        assert "key_hash" not in k1

        from src.api.freespace_deps import get_valid_app_key_hash_set

        hashes = await get_valid_app_key_hash_set(async_session)
        assert {hash_key(k1["key"]), hash_key(k2["key"])} <= hashes  # primes cache

        listing = await client.get("/api/v1/admin/app-keys", headers=h)
        assert listing.status_code == 200
        assert k1["key"] not in listing.text
        assert {i["name"] for i in listing.json()["items"]} == {"a1", "a2"}

        rv = await client.post(f"/api/v1/admin/app-keys/{k1['id']}/revoke", headers=h)
        assert rv.status_code == 200
        hashes = await get_valid_app_key_hash_set(async_session)  # cache was dropped
        assert hash_key(k1["key"]) not in hashes
        assert hash_key(k2["key"]) in hashes

        again = await client.post(
            f"/api/v1/admin/app-keys/{k1['id']}/revoke", headers=h
        )
        assert again.status_code == 409
        assert again.json()["detail_code"] == "app_key.already_revoked"
        missing = await client.post(
            f"/api/v1/admin/app-keys/{uuid.uuid4()}/revoke", headers=h
        )
        assert missing.status_code == 404

    async def test_create_invalidates_cache(
        self, client, async_session, test_admin_token
    ):
        from src.api.freespace_deps import get_valid_app_key_hash_set

        await make_app_key(async_session)
        await get_valid_app_key_hash_set(async_session)  # cache holds 1
        k = (
            await client.post(
                "/api/v1/admin/app-keys",
                json={"name": "n"},
                headers={"Authorization": test_admin_token},
            )
        ).json()
        assert hash_key(k["key"]) in await get_valid_app_key_hash_set(async_session)

    async def test_non_super_admin_forbidden(
        self, client, async_session, fs_admin_token, fs_viewer_token
    ):
        _, key = await make_app_key(async_session)
        for token in (fs_admin_token, fs_viewer_token):
            h = {"Authorization": token}
            assert (
                await client.get("/api/v1/admin/app-keys", headers=h)
            ).status_code == 403
            assert (
                await client.post(
                    "/api/v1/admin/app-keys", json={"name": "x"}, headers=h
                )
            ).status_code == 403
            assert (
                await client.post(f"/api/v1/admin/app-keys/{key.id}/revoke", headers=h)
            ).status_code == 403
        await async_session.refresh(key)
        assert key.revoked_at is None
