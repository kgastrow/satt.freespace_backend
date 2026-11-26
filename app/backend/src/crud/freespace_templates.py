"""CRUD for per-site message templates (admin API, M1). The site is resolved
and tenant-checked by the caller; rows are filtered by ``site_id``."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.freespace import DEFAULT_LOCALE, AdvisoryType
from src.models.site import Site
from src.models.site_message_template import SiteMessageTemplate


async def list_template_rows(
    session: AsyncSession, site_id: uuid.UUID, locale: str = DEFAULT_LOCALE
) -> dict[str, SiteMessageTemplate]:
    result = await session.execute(
        select(SiteMessageTemplate).where(
            SiteMessageTemplate.site_id == site_id,
            SiteMessageTemplate.locale == locale,
            SiteMessageTemplate.deleted_time.is_(None),
        )
    )
    return {row.advisory_type: row for row in result.scalars().all()}


async def upsert_template(
    session: AsyncSession,
    site: Site,
    advisory_type: AdvisoryType,
    title: str,
    body: str,
    locale: str = DEFAULT_LOCALE,
) -> SiteMessageTemplate:
    """Update the live row, or create it when missing."""
    rows = await list_template_rows(session, site.id, locale)
    row = rows.get(advisory_type.value)
    if row is None:
        row = SiteMessageTemplate(
            organization_id=site.organization_id,
            site_id=site.id,
            advisory_type=advisory_type.value,
            locale=locale,
            title=title,
            body=body,
        )
        session.add(row)
    else:
        row.title = title
        row.body = body
    await session.flush()
    return row
