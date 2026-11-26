"""
Web Push notification provider.

Signs payloads with VAPID and POSTs to the browser PushSubscription endpoint.
Prunes the subscription on a 404/410 response (subscription gone). Uses
``pywebpush`` if available, with a guarded import so a missing library never
hard-crashes the dispatcher (matches the Twilio provider optional-import
pattern).
"""

from typing import Any, Optional

from src.core.config import settings
from src.logger.logger import Logger as logger
from src.services.notifications.base import NotificationProvider, NotificationResult
from src.services.notifications.web_push_config import DEFAULT_SUBJECT


try:
    from pywebpush import WebPushException, webpush

    PYWEBPUSH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when lib missing
    PYWEBPUSH_AVAILABLE = False
    webpush = None  # type: ignore[assignment]
    WebPushException = Exception  # type: ignore[assignment,misc]


class WebPushSubscriptionGone(Exception):
    """Raised when the push endpoint reports the subscription is gone (404/410)."""


class WebPushProvider(NotificationProvider):
    """Web Push (VAPID) notification provider.

    The ``recipient`` for :meth:`send` is the subscription endpoint URL, and the
    ``metadata`` must carry the subscription ``keys`` (``p256dh`` / ``auth``).
    """

    def __init__(
        self,
        vapid_private_key: Optional[str] = None,
        vapid_public_key: Optional[str] = None,
        vapid_subject: Optional[str] = None,
    ):
        self._vapid_private_key: str = (
            vapid_private_key or getattr(settings, "VAPID_PRIVATE_KEY", "") or ""
        )
        self._vapid_public_key: str = (
            vapid_public_key or getattr(settings, "VAPID_PUBLIC_KEY", "") or ""
        )
        self._vapid_subject: str = (
            vapid_subject
            or getattr(settings, "VAPID_SUBJECT", DEFAULT_SUBJECT)
            or DEFAULT_SUBJECT
        )

    @property
    def provider_name(self) -> str:
        return "vapid"

    @property
    def channel(self) -> str:
        return "web_push"

    async def _resolve_keys(self) -> tuple[str, str]:
        """Effective (private_key, subject).

        When constructed with an explicit key (e.g. in tests, or an env-pinned
        deploy) that is authoritative. Otherwise resolve from the SystemConfig
        store so a super-admin's saved keypair takes effect without a restart.
        """
        if self._vapid_private_key:
            return self._vapid_private_key, self._vapid_subject
        try:
            from src.database import AsyncSessionLocal
            from src.services.notifications.web_push_config import get_web_push_config

            async with AsyncSessionLocal() as session:
                cfg = await get_web_push_config(session)
            return cfg["private_key"], cfg["subject"] or self._vapid_subject
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Could not resolve Web Push config: {e}")
            return "", self._vapid_subject

    async def send(
        self,
        recipient: str,
        message: str,
        subject: Optional[str] = None,
        html_message: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> NotificationResult:
        """Send a Web Push notification.

        Args:
            recipient: The PushSubscription endpoint URL.
            message: The notification body.
            subject: Optional title.
            html_message: Ignored for web push.
            metadata: Must include ``p256dh`` and ``auth`` keys; optional ``url``.
        """
        if not PYWEBPUSH_AVAILABLE:
            logger.error("pywebpush library not available")
            return NotificationResult(
                success=False,
                error_message="pywebpush library not installed",
                status="failed",
            )

        vapid_private_key, vapid_subject = await self._resolve_keys()
        if not vapid_private_key:
            return NotificationResult(
                success=False,
                error_message="VAPID private key not configured",
                status="failed",
            )

        metadata = metadata or {}
        p256dh = metadata.get("p256dh")
        auth = metadata.get("auth")
        if not p256dh or not auth:
            return NotificationResult(
                success=False,
                error_message="Missing p256dh/auth keys for push subscription",
                status="failed",
            )

        import json

        subscription_info = {
            "endpoint": recipient,
            "keys": {"p256dh": p256dh, "auth": auth},
        }
        data = json.dumps(
            {
                "title": subject or settings.APP_NAME,
                "body": message,
                "url": metadata.get("url"),
            }
        )

        try:
            webpush(
                subscription_info=subscription_info,
                data=data,
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": vapid_subject},
            )
            return NotificationResult(success=True, status="sent")
        except WebPushException as e:  # type: ignore[misc]
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code in (404, 410):
                logger.info(
                    f"Web push subscription gone ({status_code}) for {recipient}"
                )
                raise WebPushSubscriptionGone(str(e)) from e
            logger.error(f"Web push send error for {recipient}: {e}")
            return NotificationResult(
                success=False, error_message=str(e), status="failed"
            )
        except Exception as e:
            logger.error(f"Web push send error for {recipient}: {e}")
            return NotificationResult(
                success=False, error_message=str(e), status="failed"
            )

    async def check_delivery_status(self, message_id: str) -> str:
        # Web push has no delivery-status API.
        return "unknown"


# Singleton instance
web_push_provider = WebPushProvider()
