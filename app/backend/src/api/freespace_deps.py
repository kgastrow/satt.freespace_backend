"""
FastAPI dependencies for the public Freespace endpoints (D3, BF-10, §6.2).

* ``get_ingest_site`` - ``Authorization: Bearer <ingest key>`` -> the key's
  site and key row. 401 on a missing/malformed header, unknown, revoked or
  expired key. Records ``last_used_at`` / ``last_used_ip`` and COMMITS that
  update immediately, so it survives a later 403/422 raised by the endpoint.
* ``require_app_key`` - ``X-Freespace-App-Key`` must be one of the valid app
  keys (hash set cached in Redis for 60 s, D3). 401 otherwise.

Both resolve tenant data WITHOUT an organization filter (D2): the key is the
tenant context. Everything downstream must stay on ``auth.site``.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Annotated
import uuid

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.constants.freespace import (
    APP_KEY_HEADER,
    APP_KEYS_CACHE_TTL_S,
    REDIS_APP_KEYS_KEY,
)
from src.core.client_ip import get_client_ip
from src.core.exceptions import create_http_exception
from src.crud.freespace_keys import (
    get_ingest_key_with_site_by_hash,
    get_valid_app_key_hashes,
    ingest_key_is_valid,
    touch_ingest_key,
)
from src.logger.logger import Logger as logger
from src.models.ingest_key import IngestKey
from src.models.site import Site
from src.services.freespace.clock import Clock, ensure_utc, get_clock
from src.services.freespace.keys import hash_key, is_valid_key_format
from src.services.freespace.redis_client import get_redis


@dataclass(frozen=True)
class IngestAuth:
    """Result of ``get_ingest_site``: the authenticated key and its site."""

    site: Site
    key: IngestKey


def _ingest_unauthorized(detail: str, detail_code: str) -> HTTPException:
    return create_http_exception(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        detail_code=detail_code,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_ingest_site(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
    authorization: Annotated[str | None, Header()] = None,
) -> IngestAuth:
    """Authenticate a ParkIT publisher by its ingest key (BF-10).

    Every 401 is counted for the ingest rejection-rate alert (BF-82): these
    rejections write no ``site_event``. Failed authentications are also
    limited per client IP (review F5): over that budget the answer is 429
    ``ingest.rate_limited`` and the rejection is not recorded."""
    from src.services.freespace.alerts import record_ingest_rejection
    from src.services.freespace.ingest_rate_limit import check_auth_failure_limit

    now = clock.now()

    async def reject(
        key_id: uuid.UUID | None, detail: str, detail_code: str
    ) -> HTTPException:
        await check_auth_failure_limit(get_client_ip(request), now)
        await record_ingest_rejection(key_id, now)
        return _ingest_unauthorized(detail, detail_code)

    if not authorization:
        raise await reject(None, "Missing ingest key", "ingest.unauthorized")
    scheme, _, token = authorization.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token or not is_valid_key_format(token):
        raise await reject(None, "Invalid ingest key", "ingest.unauthorized")

    found = await get_ingest_key_with_site_by_hash(session, hash_key(token))
    if found is None:
        raise await reject(None, "Invalid ingest key", "ingest.unauthorized")
    key, site = found

    if key.revoked_at is not None:
        raise await reject(key.id, "Ingest key revoked", "ingest.key_revoked")
    if key.expires_at is not None and ensure_utc(key.expires_at) <= now:
        raise await reject(key.id, "Ingest key expired", "ingest.key_expired")
    if not ingest_key_is_valid(key, now):  # defensive: any future validity rule
        raise await reject(key.id, "Invalid ingest key", "ingest.unauthorized")

    await touch_ingest_key(session, key, now, get_client_ip(request))
    await session.commit()
    return IngestAuth(site=site, key=key)


async def _cached_app_key_hashes() -> set[str] | None:
    redis = get_redis()
    if redis is None:
        return None
    try:
        raw = await redis.get(REDIS_APP_KEYS_KEY)
    except Exception as exc:  # cache optional: fall back to the DB
        logger.warning(f"Freespace app keys: cache read failed: {exc}")
        return None
    if raw is None:
        return None
    try:
        return set(json.loads(raw))
    except (TypeError, ValueError):
        return None


async def _store_app_key_hashes(hashes: set[str]) -> None:
    redis = get_redis()
    if redis is None:
        return
    try:
        await redis.setex(
            REDIS_APP_KEYS_KEY, APP_KEYS_CACHE_TTL_S, json.dumps(sorted(hashes))
        )
    except Exception as exc:  # cache optional
        logger.warning(f"Freespace app keys: cache write failed: {exc}")


async def invalidate_app_key_cache() -> None:
    """Drop the cached valid app-key set. M2 calls it after create/revoke."""
    redis = get_redis()
    if redis is None:
        return
    try:
        await redis.delete(REDIS_APP_KEYS_KEY)
    except Exception as exc:  # cache optional
        logger.warning(f"Freespace app keys: cache delete failed: {exc}")


async def get_valid_app_key_hash_set(session: AsyncSession) -> set[str]:
    """Valid app-key hashes, from the 60 s Redis cache or the database."""
    cached = await _cached_app_key_hashes()
    if cached is not None:
        return cached
    hashes = await get_valid_app_key_hashes(session)
    await _store_app_key_hashes(hashes)
    return hashes


async def require_app_key(
    session: Annotated[AsyncSession, Depends(get_session)],
    x_freespace_app_key: Annotated[str | None, Header(alias=APP_KEY_HEADER)] = None,
) -> None:
    """Reject app requests without a valid ``X-Freespace-App-Key`` (401).

    Use as ``dependencies=[Depends(require_app_key)]`` on the app routers or
    routes. A speed bump, not authentication (§6.2).
    """
    if not x_freespace_app_key:
        raise create_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing app key",
            detail_code="app_key.invalid",
        )
    if hash_key(x_freespace_app_key) not in await get_valid_app_key_hash_set(session):
        raise create_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid app key",
            detail_code="app_key.invalid",
        )
