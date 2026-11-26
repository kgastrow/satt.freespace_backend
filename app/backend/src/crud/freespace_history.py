"""
Occupancy history writes (BF-4, D14): at most one point per minute per site
(``zone_id IS NULL``) and per zone; the last value in the minute wins. OWNER: M3.

PostgreSQL and SQLite both use ``INSERT ... ON CONFLICT (...) WHERE ... DO
UPDATE`` against the two partial unique indexes of ``occupancy_history``
(contracts §2 / §10.3). Any other dialect falls back to select-then-update.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.occupancy_history import OccupancyHistory


def bucket_minute(value: datetime) -> datetime:
    """Start of the minute containing ``value`` (seconds/microseconds zeroed)."""
    return value.replace(second=0, microsecond=0)


async def upsert_history_point(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID,
    zone_id: uuid.UUID | None,
    at: datetime,
    occupied: int,
    capacity: int,
    free_usable: int,
    health: str,
) -> None:
    """Write the history point of ``at``'s minute for a site (``zone_id`` None)
    or a zone, replacing an earlier point in the same minute. Flush only."""
    bucket = bucket_minute(at)
    figures: dict[str, Any] = {
        "occupied": occupied,
        "capacity": capacity,
        "free_usable": free_usable,
        "health": health,
    }
    values: dict[str, Any] = {
        "organization_id": organization_id,
        "site_id": site_id,
        "zone_id": zone_id,
        "bucket_minute": bucket,
        **figures,
    }
    if zone_id is None:
        index_elements = [OccupancyHistory.site_id, OccupancyHistory.bucket_minute]
        index_where = OccupancyHistory.zone_id.is_(None)
    else:
        index_elements = [OccupancyHistory.zone_id, OccupancyHistory.bucket_minute]
        index_where = OccupancyHistory.zone_id.is_not(None)

    dialect = session.get_bind().dialect.name
    if dialect in ("postgresql", "sqlite"):
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        stmt = insert(OccupancyHistory).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=index_elements,
            index_where=index_where,
            set_=figures,
        )
        await session.execute(stmt)
        return

    # Generic fallback (not used by the supported databases).
    query = select(OccupancyHistory).where(
        OccupancyHistory.organization_id == organization_id,
        OccupancyHistory.site_id == site_id,
        OccupancyHistory.bucket_minute == bucket,
        (
            OccupancyHistory.zone_id.is_(None)
            if zone_id is None
            else OccupancyHistory.zone_id == zone_id
        ),
    )
    row = (await session.execute(query)).scalars().first()
    if row is None:
        session.add(OccupancyHistory(**values))
    else:
        for column, value in figures.items():
            setattr(row, column, value)
    await session.flush()
