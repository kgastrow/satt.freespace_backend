"""
Admin: ingest keys under a site and deployment-wide app keys
(BF-9, BF-10a, BF-10b, BF-76). OWNER: M2.

Two routers, both registered in ``src/api/v1/__init__.py``:
* ``router`` - prefix ``/admin/sites/{site_id}/ingest-keys``
* ``app_keys_router`` - prefix ``/admin/app-keys`` (super admin only: app
  keys are not tenant data)
Permission: ``site_keys:write`` (``sites:read`` to list ingest keys).

Plaintext keys are returned exactly once, in the create response; only the
SHA-256 hash is stored and neither is ever logged or audited.
"""

import traceback
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_super_admin,
    get_session,
    require_permission,
)
from src.api.freespace_deps import invalidate_app_key_cache
from src.constants.freespace import PERM_SITE_KEYS_WRITE, PERM_SITES_READ
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.crud import freespace_keys as crud
from src.logger.logger import Logger
from src.models.audit_log import AuditAction
from src.models.site import Site
from src.serialisers.freespace_keys import (
    CreateAppKeyRequest,
    CreateAppKeyResponse,
    CreateIngestKeyRequest,
    CreateIngestKeyResponse,
    ListAppKeysResponse,
    ListIngestKeysResponse,
    RevokeAppKeyResponse,
    RevokeIngestKeyResponse,
    serialise_app_key,
    serialise_ingest_key,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent
from src.services.freespace.clock import Clock, ensure_utc, get_clock
from src.services.freespace.keys import (
    generate_app_key,
    generate_ingest_key,
    hash_key,
    key_hint,
)


router = APIRouter(
    prefix="/admin/sites/{site_id}/ingest-keys", tags=["freespace-admin-keys"]
)
app_keys_router = APIRouter(prefix="/admin/app-keys", tags=["freespace-admin-keys"])


def _internal_error(http_request: Request, what: str, exc: Exception):
    error_tb = traceback.format_exc()
    Logger.error(f"Failed to {what}: {type(exc).__name__}\n{error_tb}")
    http_request.state.error_traceback = error_tb
    return create_http_exception(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error",
        detail_code="common.internal_error",
    )


async def _resolve_site(
    session: AsyncSession, site_id: UUID, current_user: CurrentUser
) -> Site:
    """Live site of the caller's tenant (super admin: any); else 404."""
    org_id = None if current_user.is_admin else UUID(str(current_user.organization_id))
    site = await crud.get_site_for_admin(session, site_id, org_id)
    if site is None:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found",
            detail_code="site.not_found",
        )
    return site


# ---------------------------------------------------------------------------
# Ingest keys
# ---------------------------------------------------------------------------


@router.get("", response_model=ListIngestKeysResponse)
async def list_ingest_keys_endpoint(
    site_id: UUID,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission(PERM_SITES_READ))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """List the site's ingest keys (never the hash or plaintext)."""
    try:
        site = await _resolve_site(session, site_id, current_user)
        rows = await crud.list_ingest_keys(session, site)
        return ListIngestKeysResponse(items=[serialise_ingest_key(r) for r in rows])
    except HTTPException:
        raise
    except Exception as e:
        raise _internal_error(http_request, "list ingest keys", e)


@router.post(
    "", response_model=CreateIngestKeyResponse, status_code=status.HTTP_201_CREATED
)
async def create_ingest_key_endpoint(
    site_id: UUID,
    request_body: CreateIngestKeyRequest,
    http_request: Request,
    current_user: Annotated[
        CurrentUser, Depends(require_permission(PERM_SITE_KEYS_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
):
    """Create an ingest key. The plaintext is in this response only."""
    try:
        site = await _resolve_site(session, site_id, current_user)
        now = clock.now()
        expires_at = request_body.expires_at
        if expires_at is not None:
            expires_at = ensure_utc(expires_at)
            if expires_at <= now:
                raise create_http_exception(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Expiry must be in the future",
                    detail_code="ingest_key.invalid_expiry",
                )
        plaintext = generate_ingest_key()
        row = await crud.create_ingest_key(
            session,
            site,
            name=request_body.name.strip(),
            key_hash=hash_key(plaintext),
            key_hint=key_hint(plaintext),
            expires_at=expires_at,
            created_by=UUID(str(current_user.id)),
        )
        await audit_service.log_action(
            session=session,
            organization_id=str(site.organization_id),
            action=AuditAction.CREATE,
            resource_type="ingest_key",
            resource_id=str(row.id),
            actor_id=current_user.id,
            changes={
                "site_id": str(site.id),
                "name": row.name,
                "key_hint": row.key_hint,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_name=row.name,
        )
        await session.commit()
        base = serialise_ingest_key(row)
        return CreateIngestKeyResponse(
            **base.model_dump(),
            key=plaintext,
            message="Ingest key created. Store it now: it cannot be shown again.",
            message_code=get_response_code("ingest_key.created"),
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except Exception as e:
        raise _internal_error(http_request, "create ingest key", e)


@router.post("/{key_id}/revoke", response_model=RevokeIngestKeyResponse)
async def revoke_ingest_key_endpoint(
    site_id: UUID,
    key_id: UUID,
    http_request: Request,
    current_user: Annotated[
        CurrentUser, Depends(require_permission(PERM_SITE_KEYS_WRITE))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
):
    """Revoke an ingest key; takes effect on its next request."""
    try:
        site = await _resolve_site(session, site_id, current_user)
        key = await crud.get_ingest_key_for_site(session, site, key_id)
        if key is None:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ingest key not found",
                detail_code="ingest_key.not_found",
            )
        if key.revoked_at is not None:
            raise create_http_exception(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ingest key already revoked",
                detail_code="ingest_key.already_revoked",
            )
        now = clock.now()
        await crud.revoke_ingest_key(session, key, now)
        await audit_service.log_action(
            session=session,
            organization_id=str(site.organization_id),
            action=AuditAction.UPDATE,
            resource_type="ingest_key",
            resource_id=str(key.id),
            actor_id=current_user.id,
            changes={
                "revoked_at": {"old": None, "new": now.isoformat()},
                "site_id": str(site.id),
                "name": key.name,
                "key_hint": key.key_hint,
            },
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_name=key.name,
        )
        await session.commit()
        return RevokeIngestKeyResponse(
            key=serialise_ingest_key(key),
            message="Ingest key revoked",
            message_code=get_response_code("ingest_key.revoked"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _internal_error(http_request, "revoke ingest key", e)


# ---------------------------------------------------------------------------
# App keys (deployment-wide, super admin only)
# ---------------------------------------------------------------------------


@app_keys_router.get("", response_model=ListAppKeysResponse)
async def list_app_keys_endpoint(
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        rows = await crud.list_app_keys(session)
        return ListAppKeysResponse(items=[serialise_app_key(r) for r in rows])
    except HTTPException:
        raise
    except Exception as e:
        raise _internal_error(http_request, "list app keys", e)


@app_keys_router.post(
    "", response_model=CreateAppKeyResponse, status_code=status.HTTP_201_CREATED
)
async def create_app_key_endpoint(
    request_body: CreateAppKeyRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Create an app key. The plaintext is in this response only."""
    try:
        plaintext = generate_app_key()
        row = await crud.create_app_key(
            session,
            name=request_body.name.strip(),
            key_hash=hash_key(plaintext),
            key_hint=key_hint(plaintext),
            created_by=UUID(str(current_user.id)),
        )
        await audit_service.log_action(
            session=session,
            organization_id=str(current_user.organization_id),
            action=AuditAction.CREATE,
            resource_type="app_key",
            resource_id=str(row.id),
            actor_id=current_user.id,
            changes={"name": row.name, "key_hint": row.key_hint},
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_name=row.name,
        )
        await session.commit()
        await invalidate_app_key_cache()
        base = serialise_app_key(row)
        return CreateAppKeyResponse(
            **base.model_dump(),
            key=plaintext,
            message="App key created. Store it now: it cannot be shown again.",
            message_code=get_response_code("app_key.created"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _internal_error(http_request, "create app key", e)


@app_keys_router.post("/{key_id}/revoke", response_model=RevokeAppKeyResponse)
async def revoke_app_key_endpoint(
    key_id: UUID,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
):
    try:
        key = await crud.get_app_key(session, key_id)
        if key is None:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="App key not found",
                detail_code="app_key.not_found",
            )
        if key.revoked_at is not None:
            raise create_http_exception(
                status_code=status.HTTP_409_CONFLICT,
                detail="App key already revoked",
                detail_code="app_key.already_revoked",
            )
        now = clock.now()
        await crud.revoke_app_key(session, key, now)
        await audit_service.log_action(
            session=session,
            organization_id=str(current_user.organization_id),
            action=AuditAction.UPDATE,
            resource_type="app_key",
            resource_id=str(key.id),
            actor_id=current_user.id,
            changes={
                "revoked_at": {"old": None, "new": now.isoformat()},
                "name": key.name,
                "key_hint": key.key_hint,
            },
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_name=key.name,
        )
        await session.commit()
        await invalidate_app_key_cache()
        return RevokeAppKeyResponse(
            key=serialise_app_key(key),
            message="App key revoked",
            message_code=get_response_code("app_key.revoked"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _internal_error(http_request, "revoke app key", e)
