"""
Daily retention purge (BF-73, D12, D14). OWNER: M9.

Retention periods come from ``get_deployment_settings`` (never constants).
Every class of data is deleted in batches that commit per batch, so the job
holds no long transaction and is safe to run while intake and fan-out write.
Re-running it is harmless: it only ever removes rows already past the cut-off.

Hard deletes are sanctioned here (plan D12). Devices are erased through the
same function as ``DELETE /v1/devices/{deviceId}`` (token, id hash, suffix and
selections go; a tombstone with platform, version and dates stays).

No device id, token or token hash is read into a log line or a result.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from src.crud import freespace_devices as device_crud
from src.logger.logger import Logger as logger
from src.models.device import Device
from src.models.occupancy_history import OccupancyHistory
from src.models.push_send import PushSend
from src.models.request_log import RequestLog
from src.models.site_event import SiteEvent
from src.services.freespace.clock import Clock
from src.services.freespace.deployment_settings import (
    DeploymentSettings,
    get_deployment_settings,
)


DEFAULT_BATCH_SIZE = 5000
# Devices are erased one row at a time in Python, so keep that batch smaller.
DEVICE_BATCH_SIZE = 1000


@dataclass
class PurgeResult:
    """Row counts per data class; ``errors`` names the classes that failed."""

    devices_erased: int = 0
    send_history_deleted: int = 0
    events_deleted: int = 0
    occupancy_history_deleted: int = 0
    request_logs_deleted: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def cutoff_for(now: datetime, days: int) -> datetime:
    """Rows strictly older than this are past retention."""
    return now - timedelta(days=days)


async def _delete_in_batches(
    session: AsyncSession,
    model: Any,
    id_column: InstrumentedAttribute[Any],
    condition: ColumnElement[bool],
    batch_size: int,
) -> int:
    total = 0
    while True:
        ids = list(
            (
                await session.execute(
                    select(id_column).where(condition).limit(batch_size)
                )
            )
            .scalars()
            .all()
        )
        if not ids:
            break
        await session.execute(delete(model).where(id_column.in_(ids)))
        await session.commit()
        total += len(ids)
        if len(ids) < batch_size:
            break
    return total


async def purge_inactive_devices(
    session: AsyncSession,
    now: datetime,
    days: int,
    batch_size: int = DEVICE_BATCH_SIZE,
) -> int:
    """Erase live devices with no PUT (``last_seen``) since the cut-off.

    Rows are locked ``FOR UPDATE SKIP LOCKED`` and the condition is part of the
    query, so a device whose PUT commits first is simply not selected.
    """
    cutoff = cutoff_for(now, days)
    total = 0
    while True:
        devices = list(
            (
                await session.execute(
                    select(Device)
                    .where(Device.deleted_time.is_(None), Device.last_seen < cutoff)
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        if not devices:
            break
        for device in devices:
            await device_crud.erase_device(session, device, now)
        await session.commit()
        total += len(devices)
        if len(devices) < batch_size:
            break
    return total


async def purge_send_history(
    session: AsyncSession, now: datetime, days: int, batch_size: int
) -> int:
    cutoff = cutoff_for(now, days)
    return await _delete_in_batches(
        session, PushSend, PushSend.id, PushSend.queued_at < cutoff, batch_size
    )


async def purge_events(
    session: AsyncSession, now: datetime, days: int, batch_size: int
) -> int:
    """Delete events whose last activity is older than the cut-off.

    A collapsed event that is still being refreshed (``last_seen_at``) stays.
    Send rows that reference an expiring event go with it (foreign key), even
    if the send-history retention was configured longer than the event log's.
    """
    cutoff = cutoff_for(now, days)
    total = 0
    while True:
        ids = list(
            (
                await session.execute(
                    select(SiteEvent.id)
                    .where(SiteEvent.last_seen_at < cutoff)
                    .limit(batch_size)
                )
            )
            .scalars()
            .all()
        )
        if not ids:
            break
        await session.execute(delete(PushSend).where(PushSend.event_id.in_(ids)))
        await session.execute(delete(SiteEvent).where(SiteEvent.id.in_(ids)))
        await session.commit()
        total += len(ids)
        if len(ids) < batch_size:
            break
    return total


async def purge_occupancy_history(
    session: AsyncSession, now: datetime, days: int, batch_size: int
) -> int:
    cutoff = cutoff_for(now, days)
    return await _delete_in_batches(
        session,
        OccupancyHistory,
        OccupancyHistory.id,
        OccupancyHistory.bucket_minute < cutoff,
        batch_size,
    )


async def purge_request_logs(
    session: AsyncSession, now: datetime, days: int, batch_size: int
) -> int:
    cutoff = cutoff_for(now, days)
    return await _delete_in_batches(
        session, RequestLog, RequestLog.id, RequestLog.created_time < cutoff, batch_size
    )


async def run_purge(
    session: AsyncSession,
    clock: Clock,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    settings: DeploymentSettings | None = None,
) -> PurgeResult:
    """Run every retention purge once (BF-73). Commits per batch.

    A failure in one data class is recorded in ``errors`` and does not stop
    the others.
    """
    cfg = settings or await get_deployment_settings(session)
    now = clock.now()
    result = PurgeResult()

    async def step(name: str, attr: str, coro: Any) -> None:
        try:
            setattr(result, attr, await coro)
        except Exception as exc:
            await session.rollback()
            result.errors.append(name)
            logger.error(f"Freespace purge: {name} failed: {type(exc).__name__}")

    await step(
        "devices",
        "devices_erased",
        purge_inactive_devices(
            session, now, cfg.retention_devices_days, min(batch_size, DEVICE_BATCH_SIZE)
        ),
    )
    await step(
        "send_history",
        "send_history_deleted",
        purge_send_history(session, now, cfg.retention_send_history_days, batch_size),
    )
    await step(
        "events",
        "events_deleted",
        purge_events(session, now, cfg.retention_events_days, batch_size),
    )
    await step(
        "occupancy_history",
        "occupancy_history_deleted",
        purge_occupancy_history(
            session, now, cfg.retention_occupancy_history_days, batch_size
        ),
    )
    await step(
        "request_logs",
        "request_logs_deleted",
        purge_request_logs(session, now, cfg.retention_request_logs_days, batch_size),
    )
    logger.info(
        "Freespace purge: "
        f"devices={result.devices_erased} send_history={result.send_history_deleted} "
        f"events={result.events_deleted} occupancy={result.occupancy_history_deleted} "
        f"request_logs={result.request_logs_deleted} errors={len(result.errors)}"
    )
    return result
