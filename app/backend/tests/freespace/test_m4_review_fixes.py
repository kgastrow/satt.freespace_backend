"""Review fixes: organization lifecycle on /v1, device log privacy, limits.

BF-10, BF-18, BF-30 - BF-37, BF-73.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.crud import freespace_devices as device_crud
from src.crud.freespace_sites import organization_exists
from src.crud.organization import soft_delete_organization_cascade
from src.models.device import Device, DeviceSite
from src.models.ingest_key import IngestKey
from src.models.site import Site
from src.models.zone import Zone
from src.services.freespace import devices as device_service
from tests.freespace.conftest import make_ingest_key, make_site, make_zone


DEVICE_ID = "dev_ABCDEFGHIJKLMNOPQRSTUV-1234"
TOKEN = "fcmtok:" + "A1b2C3d4" * 20
BACKEND = Path(__file__).resolve().parents[2]


def reg_body(sites: list[str]) -> dict:
    return {
        "fcmToken": TOKEN,
        "platform": "ANDROID",
        "siteIds": sites,
        "notificationsEnabled": True,
        "appVersion": "1.0",
    }


def occupancy(slug: str) -> dict:
    return {
        "siteId": slug,
        "measuredAt": "2026-11-24T05:44:50Z",
        "site": {"capacity": 100, "occupied": 50, "freeUsable": 50, "health": "OK"},
        "zones": [],
    }


# ---------------------------------------------------------------- finding 1


@pytest.mark.parametrize("mode", ["deleted", "inactive"])
@pytest.mark.asyncio
async def test_org_not_live_hides_sites_on_every_v1_route(
    mode,
    client,
    async_session,
    fs_site,
    test_organization,
    fs_app_headers,
    fs_ingest_headers,
    fixed_clock,
):
    # Registered while the organization was live.
    ok = await client.put(
        f"/v1/devices/{DEVICE_ID}",
        json=reg_body([fs_site.slug]),
        headers=fs_app_headers,
    )
    assert ok.status_code == 200 and ok.json()["siteIds"] == [fs_site.slug]
    assert (
        await client.get("/v1/ingest/ping", headers=fs_ingest_headers)
    ).status_code == 200

    if mode == "deleted":
        test_organization.deleted_time = fixed_clock.now()
    else:
        test_organization.is_active = False
    await async_session.commit()

    # Ingest: indistinguishable from a revoked or unknown key (401).
    assert (
        await client.get("/v1/ingest/ping", headers=fs_ingest_headers)
    ).status_code == 401
    assert (
        await client.post(
            "/v1/ingest/occupancy",
            json=occupancy(fs_site.slug),
            headers=fs_ingest_headers,
        )
    ).status_code == 401
    # App: absent / 404.
    listed = await client.get("/v1/sites", headers=fs_app_headers)
    assert listed.status_code == 200 and listed.json() == {"sites": []}
    avail = await client.get(
        f"/v1/sites/{fs_site.slug}/availability", headers=fs_app_headers
    )
    assert avail.status_code == 404
    # Device: unknown site (422); the stored selection is not echoed either.
    put = await client.put(
        f"/v1/devices/{DEVICE_ID}",
        json=reg_body([fs_site.slug]),
        headers=fs_app_headers,
    )
    assert put.status_code == 422
    assert put.json()["detail_code"] == "device.unknown_site"
    device = (await async_session.execute(select(Device))).scalars().one()
    assert await device_crud.get_device_site_slugs(async_session, device.id) == []
    # Creating a site for such an organization is refused.
    assert await organization_exists(async_session, test_organization.id) is False


@pytest.mark.asyncio
async def test_org_delete_cascades_to_freespace_tables(
    async_session, fs_site, test_organization, second_organization, fixed_clock
):
    await make_zone(async_session, fs_site, "z1")
    _, key = await make_ingest_key(async_session, fs_site)
    other = await make_site(
        async_session, second_organization, slug="other-site", name="Other"
    )
    _, other_key = await make_ingest_key(async_session, other)
    device = Device(
        device_key_hash="h" * 64,
        id_suffix="1234",
        fcm_token=TOKEN,
        platform="ANDROID",
        first_seen=fixed_clock.now(),
        last_seen=fixed_clock.now(),
    )
    async_session.add(device)
    await async_session.flush()
    async_session.add(DeviceSite(device_id=device.id, site_id=fs_site.id))
    async_session.add(DeviceSite(device_id=device.id, site_id=other.id))
    await async_session.commit()

    org_id, site_id, key_id = str(test_organization.id), fs_site.id, key.id
    other_id, other_key_id, device_id = other.id, other_key.id, device.id
    await soft_delete_organization_cascade(async_session, org_id)
    async_session.expire_all()

    site = await async_session.get(Site, site_id)
    assert site.deleted_time is not None and not site.listed and not site.managed
    zones = (
        (await async_session.execute(select(Zone).where(Zone.site_id == site_id)))
        .scalars()
        .all()
    )
    assert zones and all(z.deleted_time is not None for z in zones)
    assert (await async_session.get(IngestKey, key_id)).deleted_time is not None
    selections = (await async_session.execute(select(DeviceSite))).scalars().all()
    assert [s.site_id for s in selections] == [other_id]
    # Tenant isolation: the other organization is untouched.
    assert (await async_session.get(Site, other_id)).deleted_time is None
    assert (await async_session.get(IngestKey, other_key_id)).deleted_time is None
    assert (await async_session.get(Device, device_id)).deleted_time is None


# ---------------------------------------------------------------- finding 2


def test_uvicorn_access_log_is_off_everywhere():
    for path in (
        BACKEND / "deploy" / "freespace-api.service",
        BACKEND / "docker-compose.prod.yml",
        BACKEND / "Dockerfile",
    ):
        assert "--no-access-log" in path.read_text(), path


def test_sqlalchemy_engines_hide_parameters():
    from src import database

    assert database.async_engine.sync_engine.hide_parameters is True
    assert database.direct_engine.sync_engine.hide_parameters is True


@pytest.mark.asyncio
async def test_second_integrity_error_is_clean_and_retryable(
    client, fs_app_headers, monkeypatch, caplog
):
    async def boom(*args, **kwargs):
        raise IntegrityError(
            f"INSERT INTO device VALUES ('{TOKEN}')", {"t": TOKEN}, Exception()
        )

    monkeypatch.setattr(device_service, "_register", boom)
    resp = await client.put(
        f"/v1/devices/{DEVICE_ID}", json=reg_body([]), headers=fs_app_headers
    )
    assert resp.status_code == 503
    assert resp.headers.get("retry-after") == "1"
    assert TOKEN not in resp.text and DEVICE_ID not in resp.text
    assert TOKEN not in caplog.text


# ---------------------------------------------------------------- finding 3


@pytest.mark.asyncio
async def test_app_site_500_stores_string_traceback(
    client, fs_site, fs_app_headers, monkeypatch
):
    from src.api.freespace_public import app_sites

    seen = {}
    real = app_sites._internal_error

    def spy(request, exc, what):
        out = real(request, exc, what)
        seen["tb"] = request.state.error_traceback
        return out

    async def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(app_sites, "_internal_error", spy)
    monkeypatch.setattr(app_sites, "load_snapshot", boom)
    resp = await client.get(
        f"/v1/sites/{fs_site.slug}/availability", headers=fs_app_headers
    )
    assert resp.status_code == 500
    assert isinstance(seen["tb"], str) and "RuntimeError" in seen["tb"]


def test_no_freespace_router_stores_an_exception_object():
    import re

    for path in (BACKEND / "src" / "api").glob("freespace*"):
        files = path.rglob("*.py") if path.is_dir() else [path]
        for f in files:
            for line in f.read_text().splitlines():
                m = re.search(r"error_traceback\s*=\s*(\w+)\s*$", line)
                assert not m or m.group(1) in {"error_tb", "tb"}, (f, line)


# ------------------------------------------------------- findings 4 and 5


@pytest.mark.asyncio
async def test_ingest_not_throttled_by_default_per_ip_limit(client, fs_ingest_headers):
    for _ in range(150):
        resp = await client.get("/v1/ingest/ping", headers=fs_ingest_headers)
        assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_availability_limit_is_per_ip_not_per_site_url(
    client, async_session, test_organization, fs_app_headers, fixed_clock
):
    from src.core.config import settings

    count = int(settings.RATE_LIMIT_FREESPACE_AVAILABILITY.split("/")[0])
    slugs = []
    for i in range(3):
        site = await make_site(
            async_session, test_organization, slug=f"s-{i}", name=f"S{i}"
        )
        slugs.append(site.slug)
    codes = []
    for n in range(count + 1):
        r = await client.get(
            f"/v1/sites/{slugs[n % 3]}/availability", headers=fs_app_headers
        )
        codes.append(r.status_code)
    assert codes[:count] == [200] * count
    assert codes[count] == 429


# ---------------------------------------------------------------- finding 6


@pytest.mark.asyncio
async def test_device_site_slugs_exclude_soft_deleted_sites(
    async_session, fs_site, test_organization, fixed_clock
):
    gone = await make_site(async_session, test_organization, slug="gone", name="Gone")
    device = Device(
        device_key_hash="g" * 64,
        id_suffix="1234",
        fcm_token=TOKEN,
        platform="ANDROID",
        first_seen=fixed_clock.now(),
        last_seen=fixed_clock.now(),
    )
    async_session.add(device)
    await async_session.flush()
    await device_crud.replace_device_sites(
        async_session, device.id, [fs_site.id, gone.id]
    )
    gone.deleted_time = fixed_clock.now()
    await async_session.commit()
    assert await device_crud.get_device_site_slugs(async_session, device.id) == [
        fs_site.slug
    ]
