"""
In-App Notification Provider.

Implements the NotificationProvider interface for in-app notifications.
Creates UserNotification records and broadcasts via WebSocket for real-time delivery.

Redaction
---------
This provider writes straight to ``UserNotification`` via
``crud.user_notification.create_user_notification``; it never passes through
``crud.notification.create_notification``, so none of the scrubbing that guards
the ``Notification`` table applied here. An in-app OTP or a rendered reset link
was therefore stored verbatim in a column that outlives the credential.

The same persist-path-only property the ``Notification`` table establishes is
applied here instead (see ``TestRedactionIsPersistPathOnly``): the transport -
for in-app, the WebSocket push that raises the toast - is handed the original
text, while the row that is kept in the user's inbox is scrubbed. The scrubbing
itself is imported from ``crud.notification`` rather than reimplemented; two
divergent copies of a security control are worse than one.
"""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.crud.notification import scrub_credential_text
from src.crud.user_notification import create_user_notification
from src.logger.logger import Logger as logger
from src.services.notifications.base import NotificationProvider, NotificationResult
from src.services.websocket.broadcaster import message_broadcaster


class InAppProvider(NotificationProvider):
    """
    In-app notification provider.

    Creates notification records in the database and broadcasts to connected
    WebSocket clients for real-time delivery.
    """

    @property
    def provider_name(self) -> str:
        return "in_app"

    @property
    def channel(self) -> str:
        return "in_app"

    async def send(
        self,
        recipient: str,
        message: str,
        subject: Optional[str] = None,
        html_message: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> NotificationResult:
        """
        Send an in-app notification.

        Note: This method signature matches the NotificationProvider interface but
        for in-app notifications we need additional context (session, org_id, user_id).
        Use send_in_app() method for full functionality.

        Args:
            recipient: Not used for in-app (user_id is in metadata)
            message: Notification body text
            subject: Notification title
            html_message: Not used for in-app
            metadata: Must contain 'session', 'organization_id', 'user_id'

        Returns:
            NotificationResult with success status
        """
        if not metadata:
            return NotificationResult(
                success=False,
                status="failed",
                error_message="metadata required with session, organization_id, user_id",
            )

        session = metadata.get("session")
        organization_id = metadata.get("organization_id")
        user_id = metadata.get("user_id")
        link = metadata.get("link")
        category_id = metadata.get("category_id")

        if session is None or organization_id is None or user_id is None:
            return NotificationResult(
                success=False,
                status="failed",
                error_message="session, organization_id, and user_id are required in metadata",
            )

        return await self.send_in_app(
            session=session,
            organization_id=str(organization_id),
            user_id=str(user_id),
            title=subject or "Notification",
            body=message,
            link=str(link) if link else None,
            category_id=str(category_id) if category_id else None,
        )

    async def send_in_app(
        self,
        session: AsyncSession,
        organization_id: str,
        user_id: str,
        title: str,
        body: Optional[str] = None,
        link: Optional[str] = None,
        category_id: Optional[str] = None,
    ) -> NotificationResult:
        """
        Send an in-app notification with full context.

        This is the preferred method for sending in-app notifications as it provides
        all necessary context for database persistence and WebSocket broadcasting.

        Args:
            session: Database session
            organization_id: Organization UUID string
            user_id: Target user UUID string
            title: Notification title (required)
            body: Notification body text (optional)
            link: Click-through URL (optional)
            category_id: Notification category UUID string (optional)

        Returns:
            NotificationResult with created notification ID

        Note:
            ``title`` and ``body`` are scrubbed before they are persisted; the
            WebSocket payload below carries the originals. Delivery is
            unaffected - only what is kept afterwards changes.
        """
        try:
            # Persist path only. The row is the long-lived copy: it survives in
            # the recipient's inbox until they dismiss it, is returned by
            # GET /notifications/in-app, and is reachable by a super admin
            # holding an impersonation token for this user. A live OTP or reset
            # token has no business in it. scrubbed_* is what is stored; the
            # broadcast below still gets the caller's original text.
            scrubbed_title = scrub_credential_text(title)
            stored_title = scrubbed_title if scrubbed_title is not None else title
            stored_body = scrub_credential_text(body)

            # `link` is deliberately NOT scrubbed. Unlike title/body it is the
            # notification's action rather than its display text, and the row
            # is the only copy of it the UI can ever click - redacting a token
            # out of it would leave a notification that renders fine and does
            # nothing. Callers must therefore not put a credential-bearing URL
            # in `link` if it should not persist; put it in `body` (which is
            # scrubbed) or send it over a channel with a real transport.

            # Create the notification record in the database
            notification = await create_user_notification(
                session=session,
                organization_id=organization_id,
                user_id=user_id,
                title=stored_title,
                body=stored_body,
                link=link,
                category_id=category_id,
            )

            notification_id = str(notification.id)

            # Broadcast via WebSocket for real-time delivery.
            # Payload structure must match frontend InAppNotificationWebSocketPayload
            # interface.
            #
            # This is the transport, so it carries the ORIGINAL title/body, not
            # the scrubbed row: the frontend renders this payload directly as a
            # toast and prepends it to the store, and it only ever reaches the
            # recipient's own authenticated socket. Redacting here would make
            # in-app the one channel that cannot deliver its own content.
            payload = {
                "notification": {
                    "id": notification_id,
                    "title": title,
                    "body": body,
                    "link": notification.link,
                    "category_id": (
                        str(notification.category_id)
                        if notification.category_id
                        else None
                    ),
                    "read_time": None,
                    "created_time": (
                        notification.created_time.isoformat()
                        if notification.created_time
                        else None
                    ),
                }
            }

            broadcast_success = await message_broadcaster.send_to_user(
                user_id=UUID(user_id),
                message_type="notification",
                payload=payload,
            )

            if not broadcast_success:
                # Notification was saved but WebSocket broadcast failed
                # This is not a failure - the notification is persisted
                logger.warning(
                    f"In-app notification {notification_id} saved but WebSocket broadcast failed"
                )

            logger.info(
                f"In-app notification sent: {notification_id} to user {user_id}"
            )

            return NotificationResult(
                success=True,
                provider_message_id=notification_id,
                status="sent",
                metadata={"broadcast_success": broadcast_success},
            )

        except Exception as e:
            logger.error(f"Error sending in-app notification: {e}")
            return NotificationResult(
                success=False,
                status="failed",
                error_message=str(e),
            )

    async def check_delivery_status(self, message_id: str) -> str:
        """
        Check delivery status of an in-app notification.

        In-app notifications are considered delivered immediately upon creation
        since they are persisted to the database.

        Args:
            message_id: The notification ID

        Returns:
            Status string - always "delivered" for in-app
        """
        return "delivered"


# Singleton instance
in_app_provider = InAppProvider()
