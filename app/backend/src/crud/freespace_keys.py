"""
Ingest-key and app-key data access (BF-9, D3).

Foundation provides the READ side used by the auth dependencies in
``src/api/freespace_deps.py``. OWNER after foundation: M2, which adds the
write side (create / revoke / list for the admin API) to this file. Do not
change the signatures below.

The lookups here are deliberately NOT tenant-filtered: an ingest/app request
has no tenant context and is resolved by the key itself (D2). Admin-side
functions M2 adds must take and filter by ``organization_id``.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.app_key import AppKey
from src.models.ingest_key import IngestKey
from src.models.organization import Organization
from src.models.site import Site


def ingest_key_is_valid(key: IngestKey, now: datetime) -> bool:
    """Not soft-deleted, not revoked and not expired at ``now``."""
    from src.services.freespace.clock import ensure_utc

    if key.deleted_time is not None or key.revoked_at is not None:
        return False
    if key.expires_at is not None and ensure_utc(key.expires_at) <= now:
        return False
    return True


async def get_ingest_key_with_site_by_hash(
    session: AsyncSession, key_hash: str
) -> tuple[IngestKey, Site] | None:
    """The ingest key with this hash and its LIVE site, or None.

    Returns revoked/expired keys too (callers check ``ingest_key_is_valid``)
    but never soft-deleted keys, keys of soft-deleted sites or keys of sites whose
    organization is deleted or inactive (BF-10: indistinguishable from an unknown key).
    """
    result = await session.execute(
        select(IngestKey, Site)
        .join(Site, Site.id == IngestKey.site_id)
        .join(Organization, Organization.id == Site.organization_id)
        .where(
            IngestKey.key_hash == key_hash,
            IngestKey.deleted_time.is_(None),
            Site.deleted_time.is_(None),
            Organization.deleted_time.is_(None),
            Organization.is_active.is_(True),
        )
    )
    row = result.first()
    if row is None:
        return None
    return row[0], row[1]


async def touch_ingest_key(
    session: AsyncSession, key: IngestKey, now: datetime, ip: str | None
) -> None:
    """Record use of ``key`` (last_used_at / last_used_ip). Flushes only."""
    key.last_used_at = now
    key.last_used_ip = ip[:45] if ip else None
    await session.flush()


async def get_valid_app_key_hashes(session: AsyncSession) -> set[str]:
    """Hashes of every app key that is neither soft-deleted nor revoked."""
    result = await session.execute(
        select(AppKey.key_hash).where(
            AppKey.deleted_time.is_(None),
            AppKey.revoked_at.is_(None),
        )
    )
    return {row[0] for row in result.all()}


# ---------------------------------------------------------------------------
# Write side (M2): admin API for ingest keys and app keys
# ---------------------------------------------------------------------------


async def get_site_for_admin(
    session: AsyncSession, site_id: UUID, organization_id: UUID | None
) -> Site | None:
    """Live site by id; ``organization_id=None`` (super admin) = any tenant."""
    stmt = select(Site).where(Site.id == site_id, Site.deleted_time.is_(None))
    if organization_id is not None:
        stmt = stmt.where(Site.organization_id == organization_id)
    return (await session.execute(stmt)).scalars().first()


async def list_ingest_keys(
    session: AsyncSession, site: Site, organization_id: UUID | None = None
) -> list[IngestKey]:
    """Every non-deleted key of ``site`` (revoked/expired included), newest first."""
    stmt = select(IngestKey).where(
        IngestKey.site_id == site.id,
        IngestKey.organization_id == site.organization_id,
        IngestKey.deleted_time.is_(None),
    )
    if organization_id is not None:
        stmt = stmt.where(IngestKey.organization_id == organization_id)
    stmt = stmt.order_by(IngestKey.created_time.desc(), IngestKey.id)
    return list((await session.execute(stmt)).scalars().all())


async def get_ingest_key_for_site(
    session: AsyncSession, site: Site, key_id: UUID
) -> IngestKey | None:
    result = await session.execute(
        select(IngestKey).where(
            IngestKey.id == key_id,
            IngestKey.site_id == site.id,
            IngestKey.organization_id == site.organization_id,
            IngestKey.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def create_ingest_key(
    session: AsyncSession,
    site: Site,
    *,
    name: str,
    key_hash: str,
    key_hint: str,
    expires_at: datetime | None,
    created_by: UUID | None,
) -> IngestKey:
    """Insert an ingest key (only the hash is stored). Flushes only."""
    row = IngestKey(
        organization_id=site.organization_id,
        site_id=site.id,
        name=name,
        key_hash=key_hash,
        key_hint=key_hint,
        expires_at=expires_at,
        created_by=created_by,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def revoke_ingest_key(
    session: AsyncSession, key: IngestKey, now: datetime
) -> IngestKey:
    key.revoked_at = now
    await session.flush()
    await session.refresh(key)
    return key


async def list_app_keys(session: AsyncSession) -> list[AppKey]:
    result = await session.execute(
        select(AppKey)
        .where(AppKey.deleted_time.is_(None))
        .order_by(AppKey.created_time.desc(), AppKey.id)
    )
    return list(result.scalars().all())


async def get_app_key(session: AsyncSession, key_id: UUID) -> AppKey | None:
    result = await session.execute(
        select(AppKey).where(AppKey.id == key_id, AppKey.deleted_time.is_(None))
    )
    return result.scalars().first()


async def create_app_key(
    session: AsyncSession,
    *,
    name: str,
    key_hash: str,
    key_hint: str,
    created_by: UUID | None,
) -> AppKey:
    row = AppKey(name=name, key_hash=key_hash, key_hint=key_hint, created_by=created_by)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def revoke_app_key(session: AsyncSession, key: AppKey, now: datetime) -> AppKey:
    key.revoked_at = now
    await session.flush()
    await session.refresh(key)
    return key
