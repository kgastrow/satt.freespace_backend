"""
Device registration (BF-33 - BF-37): ``PUT`` / ``DELETE /v1/devices/{deviceId}``.
OWNER: M5.

Auth: ``Depends(require_app_key)``. The deviceId is a bearer secret (BF-35):
never log it, never echo it except in its own PUT response.

Limits (BF-36): 30/minute per IP and 10/minute per deviceId. The per-device
limit is keyed by a HASH of the id, so the raw id never becomes a Redis key.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.freespace_deps import require_app_key
from src.core.config import settings
from src.core.rate_limit import limiter
from src.serialisers.freespace_devices import (
    DeviceRegistrationRequest,
    DeviceRegistrationResponse,
)
from src.services.freespace import devices as device_service
from src.services.freespace.clock import Clock, get_clock
from src.services.freespace.keys import hash_device_id


router = APIRouter(
    prefix="/devices",
    tags=["freespace-devices"],
    dependencies=[Depends(require_app_key)],
)


# Explicit scopes are REQUIRED: slowapi's default scope is the request path,
# which would put the raw deviceId into the Redis key (BF-35) and make the
# per-IP limit per-device instead. PUT and DELETE share one budget.
SCOPE_PER_IP = "freespace_device_ip"
SCOPE_PER_ID = "freespace_device_id"


def device_rate_key(request: Request) -> str:
    """slowapi ``key_func``: ``fsdev:`` + SHA-256 of the path's deviceId."""
    return "fsdev:" + hash_device_id(str(request.path_params.get("device_id", "")))


@router.put("/{device_id}", response_model=DeviceRegistrationResponse)
@limiter.shared_limit(settings.RATE_LIMIT_FREESPACE_DEVICE_PER_IP, scope=SCOPE_PER_IP)
@limiter.shared_limit(
    settings.RATE_LIMIT_FREESPACE_DEVICE_PER_ID,
    key_func=device_rate_key,
    scope=SCOPE_PER_ID,
)
async def put_device(
    request: Request,
    device_id: str,
    body: DeviceRegistrationRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> DeviceRegistrationResponse:
    """Create or replace this device's registration (BF-33)."""
    return await device_service.register_device(session, device_id, body, clock)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.shared_limit(settings.RATE_LIMIT_FREESPACE_DEVICE_PER_IP, scope=SCOPE_PER_IP)
@limiter.shared_limit(
    settings.RATE_LIMIT_FREESPACE_DEVICE_PER_ID,
    key_func=device_rate_key,
    scope=SCOPE_PER_ID,
)
async def delete_device(
    request: Request,
    device_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> Response:
    """Full opt-out (BF-34): erase token, id and selections; always 204."""
    await device_service.delete_device(session, device_id, clock)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
