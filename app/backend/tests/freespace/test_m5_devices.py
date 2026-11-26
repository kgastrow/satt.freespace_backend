"""M5: device registration, erasure, ceiling and limits (BF-33 - BF-37, BT-07)."""

from __future__ import annotations

import json
import logging

import pytest
from sqlalchemy import select

from src.models.device import Device, DeviceSite
from src.services.freespace import devices as device_service
from src.services.freespace.deployment_settings import DeploymentSettings
from src.services.freespace.keys import device_id_suffix, hash_device_id
from tests.freespace.conftest import make_site


DEVICE_ID = "dev_ABCDEFGHIJKLMNOPQRSTUV-1234"
OTHER_ID = "dev_ZYXWVUTSRQPONMLKJIHGFE-9876"
TOKEN = "fcmtok:" + "A1b2C3d4" * 20
OTHER_TOKEN = "fcmtok:" + "Z9y8X7w6" * 20


def body(token: str = TOKEN, sites: list[str] | None = None, **extra):
    data = {
        "fcmToken": token,
        "platform": "ANDROID",
        "siteIds": sites if sites is not None else [],
        "notificationsEnabled": True,
        "appVersion": "1.2.3",
    }
    data.update(extra)
    return data


async def put(client, headers, device_id=DEVICE_ID, **kw):
    return await client.put(
        f"/v1/devices/{device_id}", json=body(**kw), headers=headers
    )


async def devices(session):
    session.expire_all()
    return list((await session.execute(select(Device))).scalars().all())


@pytest.mark.asyncio
async def test_put_creates_and_returns_registration(
    client, async_session, fs_app_headers, fs_site
):
    resp = await put(client, fs_app_headers, sites=[fs_site.slug])
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["deviceId"] == DEVICE_ID
    assert data["fcmToken"] == TOKEN
    assert data["platform"] == "ANDROID"
    assert data["siteIds"] == [fs_site.slug]
    assert data["notificationsEnabled"] is True
    assert data["appVersion"] == "1.2.3"
    assert data["firstSeen"].endswith("Z") and data["lastSeen"].endswith("Z")
    assert data["tokenInvalidatedAt"] is None

    rows = await devices(async_session)
    assert len(rows) == 1
    assert rows[0].device_key_hash == hash_device_id(DEVICE_ID)
    assert rows[0].id_suffix == device_id_suffix(DEVICE_ID)
    assert DEVICE_ID not in json.dumps(
        [str(getattr(rows[0], c.name)) for c in Device.__table__.columns]
    )


@pytest.mark.asyncio
async def test_put_is_idempotent_and_updates_last_seen(
    client, async_session, fs_app_headers, fs_site, fixed_clock
):
    first = (await put(client, fs_app_headers, sites=[fs_site.slug])).json()
    fixed_clock.advance(120)
    second = (await put(client, fs_app_headers, sites=[fs_site.slug])).json()
    assert second["firstSeen"] == first["firstSeen"]
    assert second["lastSeen"] != first["lastSeen"]
    assert len(await devices(async_session)) == 1
    count = len((await async_session.execute(select(DeviceSite))).scalars().all())
    assert count == 1


@pytest.mark.asyncio
async def test_put_replaces_settings_and_sites(
    client, async_session, fs_app_headers, fs_site, fs_second_site
):
    await put(client, fs_app_headers, sites=[fs_site.slug])
    resp = await put(
        client,
        fs_app_headers,
        sites=[fs_second_site.slug],
        notificationsEnabled=False,
        appVersion="2.0.0",
    )
    data = resp.json()
    assert data["siteIds"] == [fs_second_site.slug]
    assert data["notificationsEnabled"] is False
    assert data["appVersion"] == "2.0.0"
    # A phone may follow sites of several customers (D2).
    resp = await put(client, fs_app_headers, sites=[fs_site.slug, fs_second_site.slug])
    assert sorted(resp.json()["siteIds"]) == sorted([fs_site.slug, fs_second_site.slug])


@pytest.mark.asyncio
async def test_unknown_site_is_422_and_nothing_stored(
    client, async_session, fs_app_headers, fs_site
):
    resp = await put(client, fs_app_headers, sites=[fs_site.slug, "no-such-site"])
    assert resp.status_code == 422
    assert resp.json()["detail_code"] == "device.unknown_site"
    assert await devices(async_session) == []


@pytest.mark.asyncio
async def test_unlisted_site_is_422(
    client, async_session, fs_app_headers, test_organization
):
    hidden = await make_site(
        async_session, test_organization, slug="hidden", listed=False
    )
    resp = await put(client, fs_app_headers, sites=[hidden.slug])
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_device_id_is_422(client, fs_app_headers):
    resp = await put(client, fs_app_headers, device_id="too-short")
    assert resp.status_code == 422
    assert resp.json()["detail_code"] == "device.invalid_id"
    assert "too-short" not in resp.text


@pytest.mark.asyncio
async def test_requires_app_key(client):
    assert (
        await client.put(f"/v1/devices/{DEVICE_ID}", json=body())
    ).status_code == 401
    assert (await client.delete(f"/v1/devices/{DEVICE_ID}")).status_code == 401


@pytest.mark.asyncio
async def test_token_moves_to_new_device(client, async_session, fs_app_headers):
    await put(client, fs_app_headers, device_id=DEVICE_ID)
    resp = await put(client, fs_app_headers, device_id=OTHER_ID)
    assert resp.status_code == 200
    by_hash = {d.device_key_hash: d for d in await devices(async_session)}
    assert by_hash[hash_device_id(OTHER_ID)].fcm_token == TOKEN
    assert by_hash[hash_device_id(DEVICE_ID)].fcm_token is None


@pytest.mark.asyncio
async def test_new_token_clears_invalidation(
    client, async_session, fs_app_headers, fixed_clock
):
    await put(client, fs_app_headers)
    (device,) = await devices(async_session)
    device.token_invalidated_at = fixed_clock.now()
    await async_session.commit()

    resp = await put(client, fs_app_headers, token=OTHER_TOKEN)
    assert resp.json()["tokenInvalidatedAt"] is None
    assert resp.json()["fcmToken"] == OTHER_TOKEN


@pytest.mark.asyncio
async def test_delete_erases_everything_but_a_tombstone(
    client, async_session, fs_app_headers, fs_site
):
    await put(client, fs_app_headers, sites=[fs_site.slug])
    resp = await client.delete(f"/v1/devices/{DEVICE_ID}", headers=fs_app_headers)
    assert resp.status_code == 204
    assert resp.content == b""

    # BT-07 (storage part): token gone from the database immediately.
    (tomb,) = await devices(async_session)
    assert tomb.fcm_token is None
    assert tomb.device_key_hash is None
    assert tomb.id_suffix is None
    assert tomb.deleted_time is not None
    assert tomb.platform == "ANDROID" and tomb.app_version == "1.2.3"
    assert (await async_session.execute(select(DeviceSite))).scalars().all() == []
    # ... and the token is free for another device.
    assert (await put(client, fs_app_headers, device_id=OTHER_ID)).status_code == 200


@pytest.mark.asyncio
async def test_delete_unknown_malformed_and_repeat_are_204(client, fs_app_headers):
    for device_id in (OTHER_ID, "x", DEVICE_ID):
        for _ in range(2):
            resp = await client.delete(
                f"/v1/devices/{device_id}", headers=fs_app_headers
            )
            assert resp.status_code == 204


@pytest.mark.asyncio
async def test_reregistering_after_delete_creates_a_fresh_device(
    client, async_session, fs_app_headers
):
    await put(client, fs_app_headers)
    await client.delete(f"/v1/devices/{DEVICE_ID}", headers=fs_app_headers)
    assert (await put(client, fs_app_headers)).status_code == 200
    rows = await devices(async_session)
    assert len(rows) == 2
    assert sum(1 for d in rows if d.deleted_time is None) == 1


@pytest.fixture
def ceiling_two(monkeypatch):
    async def fake_settings(session=None):
        return DeploymentSettings(device_ceiling=2)

    monkeypatch.setattr(device_service, "get_deployment_settings", fake_settings)


@pytest.mark.asyncio
async def test_ceiling_blocks_new_but_not_existing(
    client, fs_app_headers, ceiling_two, fs_redis, caplog
):
    caplog.set_level(logging.ERROR)
    assert (
        await put(client, fs_app_headers, device_id="a" * 24, token="t1")
    ).status_code == 200
    assert (
        await put(client, fs_app_headers, device_id="b" * 24, token="t2")
    ).status_code == 200

    resp = await put(client, fs_app_headers, device_id="c" * 24, token="t3")
    assert resp.status_code == 503
    assert resp.json()["detail_code"] == "device.ceiling_reached"

    # Alert hook for M9: Redis key + one error log line, raised once per window.
    payload = json.loads(await fs_redis.get(device_service.DEVICE_CEILING_ALERT_KEY))
    assert payload["registered"] == 2 and payload["ceiling"] == 2
    await put(client, fs_app_headers, device_id="d" * 24, token="t4")
    lines = [
        r
        for r in caplog.records
        if device_service.DEVICE_CEILING_LOG_MARKER in r.getMessage()
    ]
    assert len(lines) == 1
    assert "c" * 24 not in caplog.text

    # Updates of an existing device still work.
    assert (
        await put(client, fs_app_headers, device_id="a" * 24, token="t1b")
    ).status_code == 200

    # A deleted device frees a slot.
    await client.delete(f"/v1/devices/{'b' * 24}", headers=fs_app_headers)
    assert (
        await put(client, fs_app_headers, device_id="c" * 24, token="t3")
    ).status_code == 200


@pytest.mark.asyncio
async def test_per_device_limit_is_10_a_minute(client, fs_app_headers):
    for _ in range(10):
        assert (await put(client, fs_app_headers)).status_code == 200
    assert (await put(client, fs_app_headers)).status_code == 429
    # Another device is unaffected.
    assert (
        await put(client, fs_app_headers, device_id=OTHER_ID, token="z")
    ).status_code == 200


@pytest.mark.asyncio
async def test_per_device_limit_applies_to_delete(client, fs_app_headers):
    for _ in range(10):
        assert (
            await client.delete(f"/v1/devices/{DEVICE_ID}", headers=fs_app_headers)
        ).status_code == 204
    assert (
        await client.delete(f"/v1/devices/{DEVICE_ID}", headers=fs_app_headers)
    ).status_code == 429


@pytest.mark.asyncio
async def test_per_ip_limit_is_30_a_minute(client, fs_app_headers):
    for i in range(30):
        resp = await client.delete(f"/v1/devices/id{i:030d}", headers=fs_app_headers)
        assert resp.status_code == 204
    resp = await client.delete(f"/v1/devices/id{99:030d}", headers=fs_app_headers)
    assert resp.status_code == 429
