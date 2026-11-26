"""Web Push fan-out dispatch.

Fans a single logical notification out to every active browser push
subscription a user has registered, signing each with VAPID via the
``web_push_provider``. This is the transport that complements the in-app
provider on the shared dispatch path (e.g. fixture reminders): the in-app
provider writes one ``Notification`` row + WebSocket broadcast, while this
iterates the user's ``WebPushSubscription`` rows and POSTs to each browser
endpoint.

The dispatcher's ``send_notification(channel="web_push")`` signs a *single*
subscription (``recipient=endpoint`` + ``metadata={p256dh, auth}``), so it
cannot address a user who owns several devices. This module owns the
per-user fan-out, honouring the ``web_push`` preference channel and pruning
dead endpoints (404/410) as it goes.

Degrades gracefully: if ``pywebpush`` is missing or no VAPID private key is
configured, it logs and returns a zeroed summary without raising, so the
in-app path is never affected.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger as logger
from src.models.web_push_subscription import WebPushSubscription
from src.services.notifications.preference_checker import preference_checker
from src.services.notifications.web_push_config import get_web_push_config
from src.services.notifications.web_push_provider import (
    PYWEBPUSH_AVAILABLE,
    WebPushSubscriptionGone,
    web_push_provider,
)


async def send_web_push_to_user(
    session: AsyncSession,
    *,
    user_id: str,
    organization_id: str,
    title: str,
    body: str,
    url: str | None = None,
    category_code: str | None = None,
    is_urgent: bool = False,
) -> dict[str, Any]:
    """Fan a web-push notification out to all of a user's active subscriptions.

    Returns a summary dict ``{"sent", "failed", "pruned", "skipped"}``. Never
    raises for the expected degraded states (library missing, keys unset, no
    subscriptions, preference-blocked) — the caller's in-app path must be
    unaffected either way.

    Args:
        session: Database session.
        user_id: The recipient user's ID.
        organization_id: Organization context for the preference check.
        title: Notification title (shown by the service worker).
        body: Notification body text.
        url: Optional deep-link the service worker opens on click.
        category_code: Optional category for the preference check.
        is_urgent: Bypass quiet hours when True.
    """
    summary: dict[str, Any] = {
        "sent": 0,
        "failed": 0,
        "pruned": 0,
        "skipped": False,
    }

    # Graceful degrade — no pushable transport at all.
    if not PYWEBPUSH_AVAILABLE:
        logger.info("Web push skipped: pywebpush not installed")
        summary["skipped"] = True
        return summary

    cfg = await get_web_push_config(session)
    if not cfg["private_key"]:
        logger.info("Web push skipped: VAPID private key not configured")
        summary["skipped"] = True
        return summary

    # Honour the user's web_push channel + category preferences (org disable,
    # user channel/category toggle, quiet hours). Mirrors the dispatcher path.
    preference_result = await preference_checker.check_can_send(
        session=session,
        user_id=user_id,
        organization_id=organization_id,
        channel="web_push",
        category_code=category_code,
        is_urgent=is_urgent,
    )
    if not preference_result.allowed:
        reason = (
            preference_result.skip_reason.value
            if preference_result.skip_reason
            else "unknown"
        )
        logger.info(f"Web push skipped for user {user_id}: {reason}")
        summary["skipped"] = True
        return summary

    result = await session.execute(
        select(WebPushSubscription).where(
            WebPushSubscription.user_id == UUID(user_id),
            WebPushSubscription.deleted_time.is_(None),
        )
    )
    subscriptions = list(result.scalars().all())
    if not subscriptions:
        return summary

    now = datetime.now(timezone.utc)
    pruned_any = False
    for sub in subscriptions:
        # A subscription missing its keys can never be signed — count it a
        # failure rather than handing pywebpush an unusable payload.
        if not sub.p256dh_key or not sub.auth_key:
            summary["failed"] += 1
            continue
        try:
            send_result = await web_push_provider.send(
                recipient=sub.endpoint,
                message=body,
                subject=title,
                metadata={
                    "p256dh": sub.p256dh_key,
                    "auth": sub.auth_key,
                    "url": url,
                },
            )
        except WebPushSubscriptionGone:
            # Browser reported the endpoint gone (404/410) — prune it.
            sub.deleted_time = now
            summary["pruned"] += 1
            pruned_any = True
            continue

        if send_result.success:
            sub.last_seen_time = now
            summary["sent"] += 1
        else:
            summary["failed"] += 1

    if pruned_any:
        await session.commit()
    return summary
