"""
Device registration and erasure (BF-33, BF-34, BF-37, D5). OWNER: M5.

Privacy (BF-35): the raw deviceId exists only as a function argument. It is
hashed on entry (``keys.hash_device_id``) and never logged, stored, or put into
an exception message.
"""

from __future__ import annotations

from datetime import datetime
import json
from typing import Final

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import create_http_exception
from src.crud import freespace_devices as crud
from src.logger.logger import Logger as logger
from src.models.device import Device
from src.serialisers.freespace_devices import (
    DeviceRegistrationRequest,
    DeviceRegistrationResponse,
    iso_utc,
)
from src.services.freespace.clock import Clock
from src.services.freespace.deployment_settings import get_deployment_settings
from src.services.freespace.keys import (
    device_id_suffix,
    hash_device_id,
    is_valid_device_id,
)
from src.services.freespace.redis_client import get_redis


# Operator-alert hook for M9 (BF-37 -> BF-82): while the condition persists
# this Redis key holds a JSON payload; M9 reads it, sends the alert email, and
# may delete it. The key expires by itself so a resolved condition clears.
DEVICE_CEILING_ALERT_KEY: Final = "freespace:alerts:device_ceiling_reached"
DEVICE_CEILING_ALERT_TTL_S: Final = 3600
DEVICE_CEILING_LOG_MARKER: Final = "FREESPACE_ALERT device_ceiling_reached"


async def record_device_ceiling_alert(
    registered: int, ceiling: int, now: datetime
) -> bool:
    """Record that a new registration was refused at the ceiling (BF-37).

    Logs one error line (``DEVICE_CEILING_LOG_MARKER``) and sets
    ``DEVICE_CEILING_ALERT_KEY`` (set-if-absent, 1 h TTL) so M9's alert job
    can raise the BF-82 operator alert once per window. Returns True when this
    call raised the condition, False when it was already raised. Contains no
    device data.
    """
    raised = True
    redis = get_redis()
    if redis is not None:
        payload = json.dumps(
            {
                "registered": registered,
                "ceiling": ceiling,
                "raised_at": iso_utc(now),
            }
        )
        try:
            raised = bool(
                await redis.set(
                    DEVICE_CEILING_ALERT_KEY,
                    payload,
                    nx=True,
                    ex=DEVICE_CEILING_ALERT_TTL_S,
                )
            )
        except Exception as exc:  # alerting must never break registration
            logger.warning(f"Device ceiling alert: redis write failed: {exc}")
    if raised:
        logger.error(
            f"{DEVICE_CEILING_LOG_MARKER} registered={registered} ceiling={ceiling}"
        )
    return raised


def validate_device_id(device_id: str) -> None:
    """422 ``device.invalid_id`` unless the id matches BF-33. Never echoes it."""
    if not is_valid_device_id(device_id):
        raise create_http_exception(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid device id",
            detail_code="device.invalid_id",
        )


async def _to_response(
    session: AsyncSession, device: Device, device_id: str
) -> DeviceRegistrationResponse:
    return DeviceRegistrationResponse(
        device_id=device_id,
        fcm_token=device.fcm_token,
        platform=device.platform,  # type: ignore[arg-type]
        site_ids=await crud.get_device_site_slugs(session, device.id),
        notifications_enabled=device.notifications_enabled,
        app_version=device.app_version,
        first_seen=iso_utc(device.first_seen) or "",
        last_seen=iso_utc(device.last_seen) or "",
        token_invalidated_at=iso_utc(device.token_invalidated_at),
    )


async def _register(
    session: AsyncSession,
    key_hash: str,
    suffix: str,
    body: DeviceRegistrationRequest,
    now: datetime,
) -> Device:
    requested = list(dict.fromkeys(body.site_ids))
    sites = await crud.get_listed_sites_by_slugs(session, requested)
    if len(sites) != len(requested):
        raise create_http_exception(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="One or more sites are unknown or not listed",
            detail_code="device.unknown_site",
        )

    device = await crud.get_device_by_key_hash(session, key_hash)
    if device is None:
        settings = await get_deployment_settings(session)
        registered = await crud.count_registered_devices(session)
        if registered >= settings.device_ceiling:
            await record_device_ceiling_alert(registered, settings.device_ceiling, now)
            raise create_http_exception(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Device registration is temporarily unavailable",
                detail_code="device.ceiling_reached",
            )

    # A token held by another device moves here (reinstall, BF-33).
    holder = await crud.get_device_by_token(session, body.fcm_token)
    if holder is not None and (device is None or holder.id != device.id):
        await crud.release_token(session, holder.id, now)

    if device is None:
        device = Device(
            device_key_hash=key_hash,
            id_suffix=suffix,
            fcm_token=body.fcm_token,
            platform=body.platform.value,
            app_version=body.app_version,
            notifications_enabled=body.notifications_enabled,
            first_seen=now,
            last_seen=now,
        )
        session.add(device)
    else:
        if device.fcm_token != body.fcm_token:
            device.token_invalidated_at = None  # a new token arrived
        device.fcm_token = body.fcm_token
        device.platform = body.platform.value
        device.app_version = body.app_version
        device.notifications_enabled = body.notifications_enabled
        device.last_seen = now
        device.updated_time = now
    await session.flush()
    await crud.replace_device_sites(session, device.id, [s.id for s in sites])
    return device


async def register_device(
    session: AsyncSession,
    device_id: str,
    body: DeviceRegistrationRequest,
    clock: Clock,
) -> DeviceRegistrationResponse:
    """Idempotent create-or-replace (BF-33). Commits."""
    validate_device_id(device_id)
    key_hash = hash_device_id(device_id)
    suffix = device_id_suffix(device_id)
    now = clock.now()
    try:
        device = await _register(session, key_hash, suffix, body, now)
        await session.commit()
    except IntegrityError:
        # Two concurrent first registrations of one id: retry once as an update.
        await session.rollback()
        try:
            device = await _register(session, key_hash, suffix, body, now)
            await session.commit()
        except IntegrityError:
            # Lost the race twice. The SQLAlchemy message carries the statement
            # parameters (FCM token, id hash): never let it out (BF-35).
            await session.rollback()
            raise create_http_exception(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Device registration conflicted, please retry",
                detail_code="common.service_unavailable",
                headers={"Retry-After": "1"},
            ) from None
    await session.refresh(device)
    return await _to_response(session, device, device_id)


async def delete_device(session: AsyncSession, device_id: str, clock: Clock) -> None:
    """Full opt-out (BF-34). Silent for unknown ids; commits.

    A malformed id is treated like an unknown one: the caller must not learn
    whether an id exists.
    """
    if not is_valid_device_id(device_id):
        return
    device = await crud.get_device_by_key_hash(session, hash_device_id(device_id))
    if device is None:
        return
    await crud.erase_device(session, device, clock.now())
    await session.commit()
