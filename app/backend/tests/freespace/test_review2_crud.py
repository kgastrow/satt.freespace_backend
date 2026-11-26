"""Review 2 regressions: org hard delete vs ingest_key.created_by (F4) and
single-site deletion cascade + availability cache invalidation (F7)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.crud.organization import hard_delete_organization
from src.models.device import Device, DeviceSite
from src.models.ingest_key import IngestKey
from src.models.organization import Organization
from src.models.site import Site
from src.models.user import User
from src.services.freespace.availability_cache import cache_key
from tests.freespace.conftest import SITE_SLUG, make_ingest_key, make_site, unique_slug


ADMIN = "/api/v1/admin/sites"


def h(token: str) -> dict[str, str]:
    return {"Authorization": token}


# ─────────────────────────── F7: site deletion ───────────────────────────


async def test_delete_site_cascades_keys_selections_and_cache(
    client,
    async_session,
    fs_site,
    fs_ingest_key,
    fs_app_headers,
    fs_snapshot,
    fs_redis,
    fs_admin_token,
):
    device = Device(
        device_key_hash="d" * 64,
        id_suffix="ABC123",
        fcm_token="tok-review2",
        platform="ANDROID",
        notifications_enabled=True,
        first_seen=fs_site.created_time,
        last_seen=fs_site.created_time,
    )
    async_session.add(device)
    await async_session.flush()
    async_session.add(DeviceSite(device_id=device.id, site_id=fs_site.id))
    await async_session.commit()
    await fs_snapshot(fs_site, capacity=100, occupied=10)
    await client.get(f"/v1/sites/{SITE_SLUG}/availability", headers=fs_app_headers)
    assert await fs_redis.get(cache_key(SITE_SLUG)) is not None
    key_id, site_id = fs_ingest_key[1].id, fs_site.id

    resp = await client.delete(f"{ADMIN}/{site_id}", headers=h(fs_admin_token))
    assert resp.status_code == 200, resp.text

    assert await fs_redis.get(cache_key(SITE_SLUG)) is None
    async_session.expire_all()
    key = (
        await async_session.execute(select(IngestKey).where(IngestKey.id == key_id))
    ).scalar_one()
    assert key.deleted_time is not None
    assert (
        await async_session.execute(
            select(DeviceSite).where(DeviceSite.site_id == site_id)
        )
    ).first() is None


async def test_delete_site_leaves_other_organization_keys(
    client,
    async_session,
    fs_site,
    fs_second_site,
    fs_admin_token,
):
    _, other_key = await make_ingest_key(async_session, fs_second_site)
    other_id, site_id = other_key.id, fs_site.id
    resp = await client.delete(f"{ADMIN}/{site_id}", headers=h(fs_admin_token))
    assert resp.status_code == 200, resp.text
    async_session.expire_all()
    row = (
        await async_session.execute(select(IngestKey).where(IngestKey.id == other_id))
    ).scalar_one()
    assert row.deleted_time is None


async def test_config_update_invalidates_availability_cache(
    client,
    fs_site,
    fs_zones,
    fs_snapshot,
    fs_app_headers,
    fs_redis,
    fs_admin_token,
):
    await fs_snapshot(fs_site, capacity=100, occupied=10)
    await client.get(f"/v1/sites/{SITE_SLUG}/availability", headers=fs_app_headers)
    assert await fs_redis.get(cache_key(SITE_SLUG)) is not None

    resp = await client.put(
        f"{ADMIN}/{fs_site.id}/config",
        json={"listed": False},
        headers=h(fs_admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert await fs_redis.get(cache_key(SITE_SLUG)) is None


# ───────────────── F4: hard delete vs ingest_key.created_by ─────────────────


@pytest.mark.postgres
async def test_org_hard_delete_clears_ingest_key_created_by_on_postgres(
    fs_pg_engine, fixed_clock
):
    """A user of the deleted org (a super admin) created an ingest key for a
    site of ANOTHER org: the FK must not block the purge, the key survives."""
    factory = async_sessionmaker(
        bind=fs_pg_engine, class_=AsyncSession, expire_on_commit=False
    )
    now = fixed_clock.now()
    slug = unique_slug("f4")
    ids: dict = {}
    try:
        async with factory() as session:
            doomed = Organization(
                name=f"F4 doomed {slug}",
                slug=f"{slug}-a",
                is_active=True,
                deleted_time=now - timedelta(days=4000),
            )
            other = Organization(
                name=f"F4 other {slug}", slug=f"{slug}-b", is_active=True
            )
            session.add_all([doomed, other])
            await session.commit()
            ids["doomed"], ids["other"] = doomed.id, other.id
            user = User(
                email=f"{slug}@f4.test",
                password="x",
                email_verified=True,
                organization_id=doomed.id,
            )
            session.add(user)
            await session.flush()
            site = await make_site(session, other, slug=f"{slug}-s", now=now)
            ids["site"] = site.id
            _, key = await make_ingest_key(session, site, name="f4", created_by=user.id)
            ids["key"] = key.id

        async with factory() as session:
            await hard_delete_organization(session, str(ids["doomed"]))

        async with factory() as session:
            assert (
                await session.execute(
                    select(Organization).where(Organization.id == ids["doomed"])
                )
            ).scalars().first() is None
            row = (
                await session.execute(
                    select(IngestKey).where(IngestKey.id == ids["key"])
                )
            ).scalar_one()
            assert row.created_by is None
            assert row.organization_id == ids["other"]
    finally:
        async with factory() as session:
            await session.rollback()
            if "key" in ids:
                await session.execute(
                    delete(IngestKey).where(IngestKey.id == ids["key"])
                )
            if "site" in ids:
                from src.models.site_engine_state import SiteEngineState
                from src.models.site_message_template import SiteMessageTemplate

                for model in (SiteEngineState, SiteMessageTemplate):
                    await session.execute(
                        delete(model).where(model.site_id == ids["site"])
                    )
                await session.execute(delete(Site).where(Site.id == ids["site"]))
            for key_ in ("doomed", "other"):
                if key_ in ids:
                    await session.execute(
                        delete(User).where(User.organization_id == ids[key_])
                    )
                    await session.execute(
                        delete(Organization).where(Organization.id == ids[key_])
                    )
            await session.commit()
