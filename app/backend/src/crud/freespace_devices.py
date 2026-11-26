"""
Device data access (BF-6, BF-33, BF-34, D5). OWNER: M5.

Devices are NOT tenant data (D2): there is no ``organization_id`` filter. A
device is looked up only by the SHA-256 hash of its id; the raw id never
reaches this module.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.device import Device, DeviceSite
from src.models.organization import Organization
from src.models.site import Site


async def get_device_by_key_hash(session: AsyncSession, key_hash: str) -> Device | None:
    """The live (not tombstoned) device with this id hash, or None."""
    result = await session.execute(
        select(Device).where(
            Device.device_key_hash == key_hash, Device.deleted_time.is_(None)
        )
    )
    return result.scalars().first()


async def get_device_by_token(session: AsyncSession, token: str) -> Device | None:
    """The device currently holding this FCM token, or None."""
    result = await session.execute(select(Device).where(Device.fcm_token == token))
    return result.scalars().first()


async def count_registered_devices(session: AsyncSession) -> int:
    """Live devices (tombstones are not counted toward the ceiling, BF-37)."""
    result = await session.execute(
        select(func.count()).select_from(Device).where(Device.deleted_time.is_(None))
    )
    return int(result.scalar_one())


async def get_listed_sites_by_slugs(
    session: AsyncSession, slugs: Iterable[str]
) -> list[Site]:
    """Live, listed sites with these slugs (any organization, D2)."""
    wanted = list(slugs)
    if not wanted:
        return []
    result = await session.execute(
        select(Site)
        .join(Organization, Organization.id == Site.organization_id)
        .where(
            Site.slug.in_(wanted),
            Site.listed.is_(True),
            Site.deleted_time.is_(None),
            Organization.deleted_time.is_(None),
            Organization.is_active.is_(True),
        )
    )
    return list(result.scalars().all())


async def get_device_site_slugs(
    session: AsyncSession, device_pk: uuid.UUID
) -> list[str]:
    """Slugs of the sites this device has selected, sorted."""
    result = await session.execute(
        select(Site.slug)
        .join(DeviceSite, DeviceSite.site_id == Site.id)
        .join(Organization, Organization.id == Site.organization_id)
        .where(
            DeviceSite.device_id == device_pk,
            Site.deleted_time.is_(None),
            Organization.deleted_time.is_(None),
            Organization.is_active.is_(True),
        )
        .order_by(Site.slug)
    )
    return list(result.scalars().all())


async def replace_device_sites(
    session: AsyncSession, device_pk: uuid.UUID, site_ids: Iterable[uuid.UUID]
) -> None:
    """Make the device's selections exactly ``site_ids``."""
    wanted = set(site_ids)
    existing = set(
        (
            await session.execute(
                select(DeviceSite.site_id).where(DeviceSite.device_id == device_pk)
            )
        )
        .scalars()
        .all()
    )
    stale = existing - wanted
    if stale:
        await session.execute(
            delete(DeviceSite).where(
                DeviceSite.device_id == device_pk, DeviceSite.site_id.in_(stale)
            )
        )
    for site_id in wanted - existing:
        session.add(DeviceSite(device_id=device_pk, site_id=site_id))
    await session.flush()


async def release_token(
    session: AsyncSession, device_pk: uuid.UUID, now: datetime
) -> None:
    """Remove the FCM token from a device that lost it to a reinstall (BF-33)."""
    await session.execute(
        update(Device)
        .where(Device.id == device_pk)
        .values(fcm_token=None, updated_time=now)
    )
    await session.flush()


async def erase_device(session: AsyncSession, device: Device, now: datetime) -> None:
    """BF-34 / D5 / D12: erase token, id hash, suffix and selections; tombstone.

    The ``device_site`` delete is the one sanctioned hard delete of a
    selection (D12). The row survives with platform, app version and dates.
    """
    await session.execute(delete(DeviceSite).where(DeviceSite.device_id == device.id))
    device.fcm_token = None
    device.device_key_hash = None
    device.id_suffix = None
    device.deleted_time = now
    device.updated_time = now
    await session.flush()
