"""Final-pass leftovers: live view stale limit, mock-mode CORS, organization
hard delete with Freespace rows, deactivation vs the availability cache and the
customer name on the sites list/summary."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
import uuid

from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.crud.organization import hard_delete_organization
from src.database import get_async_session
from src.models.app_key import AppKey
from src.models.device import Device, DeviceSite
from src.models.occupancy_history import OccupancyHistory
from src.models.organization import Organization
from src.models.push_send import PushSend
from src.models.site import Site
from src.models.site_engine_state import SiteEngineState
from src.models.site_event import SiteEvent
from src.models.site_message_template import SiteMessageTemplate
from src.models.site_snapshot import SiteSnapshot, ZoneSnapshot
from src.models.user import User
from src.models.zone import Zone
from src.services.freespace.availability_cache import cache_key
from src.services.freespace.clock import set_clock_override
from tests.freespace.conftest import SITE_SLUG, make_site, make_zone, unique_slug


ADMIN = "/api/v1/admin/sites"


def h(token: str) -> dict[str, str]:
    return {"Authorization": token if token.startswith("Bearer") else f"Bearer {token}"}


# ───────────────────────── live view stale limit ─────────────────────────


async def test_live_site_block_has_stale_limit(
    client, async_session, test_organization, fs_roles, fs_admin_token
):
    site = await make_site(async_session, test_organization, stale_limit_s=300)
    response = await client.get(f"{ADMIN}/{site.id}/live", headers=h(fs_admin_token))
    assert response.status_code == 200
    assert response.json()["site"]["stale_limit_s"] == 300


# ───────────────────────── customer name (task 7) ─────────────────────────


async def test_site_list_and_summary_carry_organization_name(
    client,
    fs_site,
    fs_second_site,
    test_organization,
    second_organization,
    test_admin_token,
):
    listed = (await client.get(ADMIN, headers=h(test_admin_token))).json()["items"]
    names = {i["slug"]: i["organization_name"] for i in listed}
    assert names[fs_site.slug] == test_organization.name
    assert names[fs_second_site.slug] == second_organization.name

    summary = (await client.get(f"{ADMIN}/summary", headers=h(test_admin_token))).json()
    by_slug = {i["slug"]: i for i in summary["items"]}
    assert by_slug[fs_site.slug]["organization_name"] == test_organization.name
    assert by_slug[fs_second_site.slug]["organization_id"] == str(
        second_organization.id
    )


async def test_site_list_name_is_tenant_scoped(
    client, fs_site, fs_second_site, fs_admin_token, test_organization
):
    items = (await client.get(ADMIN, headers=h(fs_admin_token))).json()["items"]
    assert [i["slug"] for i in items] == [fs_site.slug]
    assert items[0]["organization_name"] == test_organization.name


# ───────────────────────── simulator vs CORS (task 4) ─────────────────────────


@pytest_asyncio.fixture
async def cors_mock_client(
    monkeypatch, async_session
) -> AsyncGenerator[AsyncClient, None]:
    import main

    monkeypatch.setattr(main.settings, "FREESPACE_MOCK_MODE", True)
    monkeypatch.setattr(main.settings, "DEBUG", True)
    monkeypatch.setattr(
        main.settings, "CORS_ALLOWED_ORIGINS", "https://admin.example.com"
    )
    app = main.create_application()
    set_clock_override(None)

    async def override_session():
        yield async_session

    app.dependency_overrides[get_async_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


async def test_mock_clock_preflight_and_post_from_allowed_origin(cors_mock_client):
    origin = "https://admin.example.com"
    preflight = await cors_mock_client.options(
        "/mock/clock",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert "POST" in preflight.headers["access-control-allow-methods"]
    assert "content-type" in preflight.headers["access-control-allow-headers"].lower()

    response = await cors_mock_client.post(
        "/mock/clock", json={"reset": True}, headers={"Origin": origin}
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


async def test_mock_clock_preflight_rejects_other_origin(cors_mock_client):
    preflight = await cors_mock_client.options(
        "/mock/clock",
        headers={
            "Origin": "https://evil.example.org",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers


# ───────────────────── deactivation vs availability cache (task 6) ─────────────────────


async def test_deactivating_organization_drops_site_cache(
    client,
    fs_site,
    fs_zones,
    fs_snapshot,
    fs_app_headers,
    fs_redis,
    test_admin_token,
    test_organization,
    fs_second_site,
):
    await fs_snapshot(fs_site, capacity=100, occupied=10)
    await fs_snapshot(fs_second_site, capacity=100, occupied=10)
    response = await client.get(
        f"/v1/sites/{SITE_SLUG}/availability", headers=fs_app_headers
    )
    assert response.status_code == 200
    assert await fs_redis.get(cache_key(SITE_SLUG)) is not None
    # A cache entry of another organization's site must survive.
    await fs_redis.set(cache_key(fs_second_site.slug), b"{}")

    updated = await client.put(
        f"/api/v1/organizations/{test_organization.id}",
        json={"is_active": False},
        headers=h(test_admin_token),
    )
    assert updated.status_code == 200, updated.text
    assert await fs_redis.get(cache_key(SITE_SLUG)) is None
    assert await fs_redis.get(cache_key(fs_second_site.slug)) is not None

    gone = await client.get(
        f"/v1/sites/{SITE_SLUG}/availability", headers=fs_app_headers
    )
    assert gone.status_code == 404


async def test_rename_without_active_change_keeps_cache(
    client,
    fs_site,
    fs_zones,
    fs_snapshot,
    fs_app_headers,
    fs_redis,
    test_admin_token,
    test_organization,
):
    await fs_snapshot(fs_site, capacity=100, occupied=10)
    await client.get(f"/v1/sites/{SITE_SLUG}/availability", headers=fs_app_headers)
    updated = await client.put(
        f"/api/v1/organizations/{test_organization.id}",
        json={"name": "Renamed"},
        headers=h(test_admin_token),
    )
    assert updated.status_code == 200, updated.text
    assert await fs_redis.get(cache_key(SITE_SLUG)) is not None


# ───────────────────── organization hard delete (task 5) ─────────────────────


async def _populate(session: AsyncSession, org: Organization, now: datetime) -> dict:
    """One of every Freespace row for ``org`` plus a user and a global device."""
    slug = unique_slug("hd")
    site = await make_site(session, org, slug=slug, now=now)
    zone = await make_zone(session, site, "b1")
    user = User(
        email=f"{slug}@hd.test",
        password="x",
        email_verified=True,
        organization_id=org.id,
    )
    session.add(user)
    await session.flush()
    session.add(
        AppKey(
            name="k", key_hash=uuid.uuid4().hex * 2, key_hint="abcd", created_by=user.id
        )
    )
    session.add(
        SiteSnapshot(
            organization_id=org.id,
            site_id=site.id,
            measured_at=now,
            received_at=now,
            capacity=10,
            occupied=1,
            free_usable=9,
            free_reserved=0,
            free_disabled=0,
            unknown=0,
            health="OK",
            reported_health="OK",
        )
    )
    session.add(
        ZoneSnapshot(
            organization_id=org.id,
            site_id=site.id,
            zone_id=zone.id,
            measured_at=now,
            received_at=now,
            capacity=10,
            occupied=1,
            free_usable=9,
            free_reserved=0,
            free_disabled=0,
            unknown=0,
            health="OK",
            reported_health="OK",
        )
    )
    event = SiteEvent(
        organization_id=org.id,
        site_id=site.id,
        occurred_at=now,
        last_seen_at=now,
        repeat_count=1,
        type="CANDIDATE",
    )
    session.add(event)
    session.add(
        OccupancyHistory(
            organization_id=org.id,
            site_id=site.id,
            zone_id=zone.id,
            bucket_minute=now,
            occupied=1,
            capacity=10,
            free_usable=9,
            health="OK",
        )
    )
    device = Device(
        device_key_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        id_suffix="HD0001",
        fcm_token="tok-" + uuid.uuid4().hex,
        platform="ANDROID",
        notifications_enabled=True,
        first_seen=now,
        last_seen=now,
    )
    session.add(device)
    await session.flush()
    session.add(DeviceSite(device_id=device.id, site_id=site.id))
    session.add(
        PushSend(
            organization_id=org.id,
            event_id=event.id,
            device_id=device.id,
            site_id=site.id,
            advisory_type="SITE_INITIAL",
            fingerprint="f" * 64,
            outcome="SENT",
            queued_at=now,
        )
    )
    await session.commit()
    return {"site_id": site.id, "device_id": device.id, "user_id": user.id}


_ORG_TABLES = (
    PushSend,
    SiteEvent,
    OccupancyHistory,
    ZoneSnapshot,
    SiteSnapshot,
    SiteEngineState,
    SiteMessageTemplate,
    Zone,
    Site,
)


async def _count(session: AsyncSession, model, org_id) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(model)
            .where(model.organization_id == org_id)
        )
    ).scalar_one()


async def test_hard_delete_removes_freespace_rows_only_for_that_org(
    async_session, test_organization, second_organization, fixed_clock
):
    now = fixed_clock.now()
    await _populate(async_session, test_organization, now)
    await _populate(async_session, second_organization, now)
    test_organization.deleted_time = now - timedelta(days=4000)
    await async_session.commit()
    org_id, other_id = test_organization.id, second_organization.id

    stats = await hard_delete_organization(async_session, str(org_id))

    assert stats["records_deleted"]["freespace_sites"] == 1
    assert stats["records_deleted"]["freespace_push_sends"] == 1
    for model in _ORG_TABLES:
        assert await _count(async_session, model, org_id) == 0, model
        assert await _count(async_session, model, other_id) >= 1, model
    assert (
        await async_session.execute(
            select(Organization).where(Organization.id == org_id)
        )
    ).scalars().first() is None
    # The other organization's device selection is untouched.
    assert (
        await async_session.execute(select(func.count()).select_from(DeviceSite))
    ).scalar_one() == 1


@pytest.mark.postgres
async def test_hard_delete_on_postgres_respects_foreign_keys(fs_pg_engine, fixed_clock):
    """Real FK enforcement: the purge must not trip on any Freespace table."""
    factory = async_sessionmaker(
        bind=fs_pg_engine, class_=AsyncSession, expire_on_commit=False
    )
    now = fixed_clock.now()
    slug = unique_slug("hdpg")
    async with factory() as session:
        org = Organization(
            name=f"HD {slug}",
            slug=slug,
            is_active=True,
            deleted_time=now - timedelta(days=4000),
        )
        session.add(org)
        await session.commit()
        ids = await _populate(session, org, now)
        org_id = org.id
    device_id = ids["device_id"]
    try:
        async with factory() as session:
            stats = await hard_delete_organization(session, str(org_id))
            assert stats["records_deleted"]["freespace_sites"] == 1
        async with factory() as session:
            assert (
                await session.execute(
                    select(Organization).where(Organization.id == org_id)
                )
            ).scalars().first() is None
            assert (
                await session.execute(
                    select(AppKey).where(
                        AppKey.name == "k",
                        AppKey.created_by.is_(None),
                        AppKey.key_hint == "abcd",
                    )
                )
            ).scalars().first() is not None
    finally:
        async with factory() as session:
            await session.execute(
                delete(DeviceSite).where(DeviceSite.device_id == device_id)
            )
            await session.execute(delete(Device).where(Device.id == device_id))
            await session.execute(
                delete(AppKey).where(AppKey.key_hint == "abcd", AppKey.name == "k")
            )
            await session.commit()
        async with factory() as session:  # leftovers if the purge failed
            await session.rollback()
            for model in _ORG_TABLES:
                await session.execute(
                    delete(model).where(model.organization_id == org_id)
                )
            await session.execute(delete(User).where(User.organization_id == org_id))
            await session.execute(delete(Organization).where(Organization.id == org_id))
            await session.commit()
