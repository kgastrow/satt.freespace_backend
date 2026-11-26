"""Web Push subscription API.

The VAPID key fetch doubles as the "is push configured?" probe: with no
keypair it answers 503 ``push.not_configured`` and the client keeps quiet
rather than showing a toggle that cannot work. Every other notification
channel is unaffected.
"""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_user,
    get_session,
    require_permission,
)
from src.core.exceptions import create_http_exception
from src.models.audit_log import AuditAction
from src.models.web_push_subscription import WebPushSubscription
from src.serialisers.push import (
    PushSubscriptionRequest,
    PushSubscriptionResponse,
    PushUnsubscribeRequest,
    VapidKeyResponse,
)
from src.serialisers.web_push import (
    GenerateVapidKeyResponse,
    SetWebPushProviderRequest,
    WebPushProviderStatusResponse,
)
from src.services.audit import audit_service
from src.services.notifications.push_endpoint import (
    MAX_ACTIVE_SUBSCRIPTIONS_PER_USER,
    InvalidPushEndpoint,
    validate_push_endpoint,
)
from src.services.notifications.web_push_config import (
    DEFAULT_SUBJECT,
    active_subscription_count,
    clear_web_push_config,
    generate_vapid_keypair,
    get_web_push_config,
    purge_all_subscriptions,
    set_web_push_config,
)


router = APIRouter(prefix="/notifications/push", tags=["push"])


def _checked_endpoint(endpoint: str) -> str:
    """Validate a client-supplied push endpoint, or raise a coded 400.

    Raised here rather than as a pydantic validator so the refusal arrives as a
    ``detail_code`` the client can translate, instead of a raw 422 blob.
    """
    try:
        return validate_push_endpoint(endpoint)
    except InvalidPushEndpoint as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="push.invalid_endpoint",
        )


@router.get("/vapid-key", response_model=VapidKeyResponse)
async def get_vapid_key_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    cfg = await get_web_push_config(session)
    if not cfg["public_key"]:
        raise create_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Web Push is not configured",
            detail_code="push.not_configured",
        )
    return VapidKeyResponse(public_key=cfg["public_key"])


# -- Web Push (VAPID) provider management -------------------------------------
def _provider_status(cfg: dict, count: int) -> WebPushProviderStatusResponse:
    return WebPushProviderStatusResponse(
        configured=bool(cfg["public_key"] and cfg["private_key"]),
        public_key=cfg["public_key"] or None,
        subject=cfg["subject"],
        private_key_configured=bool(cfg["private_key"]),
        source=cfg["source"],
        active_subscriptions=count,
    )


@router.get("/providers/web-push", response_model=WebPushProviderStatusResponse)
async def get_web_push_provider_endpoint(
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notification_providers:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Current Web Push provider status (never returns the private key)."""
    cfg = await get_web_push_config(session)
    count = await active_subscription_count(session)
    return _provider_status(cfg, count)


@router.post("/providers/web-push/generate", response_model=GenerateVapidKeyResponse)
async def generate_web_push_keys_endpoint(
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notification_providers:write"))
    ],
):
    """Generate a fresh VAPID keypair for preview (not persisted)."""
    public_key, private_key = generate_vapid_keypair()
    return GenerateVapidKeyResponse(
        public_key=public_key,
        private_key=private_key,
        subject_suggestion=DEFAULT_SUBJECT,
        warning=(
            "Saving a new keypair invalidates every existing push subscription; "
            "users must re-subscribe before they receive web push again."
        ),
    )


@router.put("/providers/web-push", response_model=WebPushProviderStatusResponse)
async def set_web_push_provider_endpoint(
    request: SetWebPushProviderRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notification_providers:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Persist the VAPID keypair + subject (optionally purging subscriptions)."""
    await set_web_push_config(
        session,
        public_key=request.public_key,
        private_key=request.private_key,
        subject=request.subject,
        updated_by_user_id=current_user.id,
    )
    purged = 0
    if request.purge_subscriptions:
        purged = await purge_all_subscriptions(session)

    await audit_service.log_action(
        session=session,
        organization_id=str(current_user.organization_id),
        action=AuditAction.UPDATE,
        resource_type="WebPushProvider",
        resource_id="vapid",
        actor_id=current_user.id,
        resource_context={
            "event": "push.provider_updated",
            "purged_subscriptions": purged,
        },
    )

    cfg = await get_web_push_config(session)
    count = await active_subscription_count(session)
    return _provider_status(cfg, count)


@router.delete("/providers/web-push", response_model=WebPushProviderStatusResponse)
async def disable_web_push_provider_endpoint(
    current_user: Annotated[
        CurrentUser, Depends(require_permission("notification_providers:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Clear the DB-stored VAPID config (reverts to startup settings/unset)."""
    await clear_web_push_config(session)
    await audit_service.log_action(
        session=session,
        organization_id=str(current_user.organization_id),
        action=AuditAction.DELETE,
        resource_type="WebPushProvider",
        resource_id="vapid",
        actor_id=current_user.id,
        resource_context={"event": "push.provider_disabled"},
    )
    cfg = await get_web_push_config(session)
    count = await active_subscription_count(session)
    return _provider_status(cfg, count)


@router.post(
    "/subscriptions",
    response_model=PushSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_subscription_endpoint(
    request: PushSubscriptionRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    # Idempotent on the ENDPOINT, which is the device identity. A browser hands
    # out one push endpoint per installation and the push service delivers to
    # the endpoint, not to a person - so an endpoint already on file is
    # REASSIGNED to whoever is signed in now rather than gaining a second live
    # row. Keyed on (user, endpoint) instead, a shared device keeps delivering
    # the previous user's notification titles and bodies to the current one.
    endpoint = _checked_endpoint(request.endpoint)
    user_uuid = UUID(current_user.id)

    existing = await session.execute(
        select(WebPushSubscription).where(
            WebPushSubscription.endpoint == endpoint,
            WebPushSubscription.deleted_time.is_(None),
        )
    )
    sub = existing.scalars().first()
    now = datetime.now(timezone.utc)
    if sub:
        reassigned = sub.user_id != user_uuid
        sub.user_id = user_uuid
        sub.p256dh_key = request.keys.p256dh
        sub.auth_key = request.keys.auth
        sub.user_agent = request.user_agent
        sub.last_seen_time = now
        await session.commit()
        await session.refresh(sub)
        if reassigned:
            await audit_service.log_action(
                session=session,
                organization_id=str(current_user.organization_id),
                action=AuditAction.UPDATE,
                resource_type="WebPushSubscription",
                resource_id=str(sub.id),
                actor_id=current_user.id,
                resource_context={"event": "push.subscription_reassigned"},
            )
        return PushSubscriptionResponse.model_validate(sub)

    # Cap live devices per user. Each row is one outbound POST on every send, so
    # an unbounded count turns one notification into unbounded fan-out; a real
    # person has a handful of devices, and anything near the ceiling is a client
    # re-registering in a loop.
    active = await session.execute(
        select(func.count())
        .select_from(WebPushSubscription)
        .where(
            WebPushSubscription.user_id == user_uuid,
            WebPushSubscription.deleted_time.is_(None),
        )
    )
    if int(active.scalar() or 0) >= MAX_ACTIVE_SUBSCRIPTIONS_PER_USER:
        raise create_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            detail="Too many registered push devices. Remove one before adding another.",
            detail_code="push.too_many_subscriptions",
        )

    sub = WebPushSubscription(
        user_id=user_uuid,
        endpoint=endpoint,
        p256dh_key=request.keys.p256dh,
        auth_key=request.keys.auth,
        user_agent=request.user_agent,
        last_seen_time=now,
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)

    await audit_service.log_action(
        session=session,
        organization_id=str(current_user.organization_id),
        action=AuditAction.CREATE,
        resource_type="WebPushSubscription",
        resource_id=str(sub.id),
        actor_id=current_user.id,
        resource_context={"event": "push.subscription_registered"},
    )
    return PushSubscriptionResponse.model_validate(sub)


@router.delete("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
async def remove_subscription_endpoint(
    request: PushUnsubscribeRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    result = await session.execute(
        select(WebPushSubscription).where(
            WebPushSubscription.user_id == UUID(current_user.id),
            WebPushSubscription.endpoint == request.endpoint,
            WebPushSubscription.deleted_time.is_(None),
        )
    )
    sub = result.scalars().first()
    if not sub:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Push subscription not found",
            detail_code="push.subscription_not_found",
        )
    sub.deleted_time = datetime.now(timezone.utc)
    await session.commit()
    return None
