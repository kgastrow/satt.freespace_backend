"""
Onboarding Notification Service.

Manages notification triggers for onboarding events including submission,
review required, approval, and rejection notifications.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger as logger
from src.models.role import Role
from src.models.user import User
from src.models.user_role import UserRole
from src.services.notifications import notification_dispatcher
from src.services.websocket.broadcaster import MessageBroadcaster


class OnboardingNotificationService:
    """
    Service for sending onboarding-related notifications.

    Triggers notifications for key onboarding events:
    - User submits onboarding (pending_review): notify org admins via WebSocket + email
    - Admin approves onboarding: notify user
    - Admin rejects onboarding: notify user with reason

    Uses the notification dispatcher to send via all user-subscribed channels.
    """

    def __init__(self):
        self.broadcaster = MessageBroadcaster()

    async def send_submission_notification(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        user_user_type_id: str,
    ) -> None:
        """
        Send notification to user confirming onboarding submission.

        Sends notifications via all user-subscribed channels confirming submission.

        Args:
            session: Database session
            user_id: User UUID who submitted
            organization_id: Organization UUID
            user_user_type_id: UserUserType UUID for the submission
        """
        try:
            user_uuid = UUID(user_id)

            # Send real-time WebSocket notification
            await self.broadcaster.send_to_user(
                user_uuid,
                "onboarding_submitted",
                {
                    "message": "Your onboarding has been submitted for review",
                    "user_user_type_id": user_user_type_id,
                    "status": "pending_review",
                },
            )

            body_text = "Your onboarding has been submitted for review. We'll notify you once it's been reviewed."

            # Send in-app notification (persisted)
            await notification_dispatcher.send_in_app_notification(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                title="Onboarding Submitted",
                body=body_text,
                category_code="onboarding",
            )

            # Send email notification
            await notification_dispatcher.send_to_user(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                channel="email",
                content=body_text,
                subject="Onboarding Submitted for Review",
                category_code="onboarding",
            )

            logger.info(
                f"Sent submission notification to user {user_id} "
                f"for onboarding {user_user_type_id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to send submission notification to user {user_id}: {e}"
            )

    async def send_new_review_required_notification(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        user_user_type_id: str,
    ) -> None:
        """
        Send notification to org admins that a new review is required.

        Broadcasts WebSocket notification to all org admins (owner/admin roles)
        alerting them of a pending onboarding review.

        Args:
            session: Database session
            user_id: User UUID who submitted
            organization_id: Organization UUID
            user_user_type_id: UserUserType UUID for the submission
        """
        try:
            # Get the user details for context
            user = await self._get_user(session, user_id, organization_id)
            user_email = user.email if user else "Unknown"

            # Get all org admin user IDs
            admin_user_ids = await self._get_org_admin_user_ids(
                session, organization_id
            )

            # Send WebSocket notification to each admin
            for admin_user_id in admin_user_ids:
                await self.broadcaster.send_to_user(
                    admin_user_id,
                    "new_review_required",
                    {
                        "message": f"New onboarding submission from {user_email}",
                        "user_id": user_id,
                        "user_email": user_email,
                        "user_user_type_id": user_user_type_id,
                        "status": "pending_review",
                    },
                )

            logger.info(
                f"Sent new review notification to {len(admin_user_ids)} admins "
                f"in org {organization_id} for onboarding {user_user_type_id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to send new review notification for onboarding {user_user_type_id}: {e}"
            )

    async def send_approved_notification(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        user_user_type_id: str,
    ) -> None:
        """
        Send notification to user that their onboarding was approved.

        Sends notifications via all user-subscribed channels (in-app, email, etc.).

        Args:
            session: Database session
            user_id: User UUID who was approved
            organization_id: Organization UUID
            user_user_type_id: UserUserType UUID for the submission
        """
        try:
            user_uuid = UUID(user_id)

            # Send real-time WebSocket notification
            await self.broadcaster.send_to_user(
                user_uuid,
                "onboarding_approved",
                {
                    "message": "Your onboarding has been approved",
                    "user_user_type_id": user_user_type_id,
                    "status": "approved",
                },
            )

            # Send in-app notification (persisted)
            await notification_dispatcher.send_in_app_notification(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                title="Onboarding Approved",
                body="Your onboarding has been approved. You now have full access to the platform.",
                category_code="onboarding",
                link="/dashboard",
            )

            # Send email notification
            await notification_dispatcher.send_to_user(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                channel="email",
                content="Your onboarding has been approved. You now have full access to the platform.",
                subject="Onboarding Approved",
                category_code="onboarding",
            )

            logger.info(
                f"Sent approval notification to user {user_id} "
                f"for onboarding {user_user_type_id}"
            )
        except Exception as e:
            logger.error(f"Failed to send approval notification to user {user_id}: {e}")

    async def send_rejected_notification(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        user_user_type_id: str,
        reason: str,
    ) -> None:
        """
        Send notification to user that their onboarding was rejected.

        Sends notifications via all user-subscribed channels with the rejection reason.

        Args:
            session: Database session
            user_id: User UUID who was rejected
            organization_id: Organization UUID
            user_user_type_id: UserUserType UUID for the submission
            reason: Rejection reason provided by admin
        """
        try:
            user_uuid = UUID(user_id)

            # Send real-time WebSocket notification
            await self.broadcaster.send_to_user(
                user_uuid,
                "onboarding_rejected",
                {
                    "message": "Your onboarding has been rejected",
                    "user_user_type_id": user_user_type_id,
                    "status": "rejected",
                    "reason": reason,
                },
            )

            body_text = f"Your onboarding has been rejected.\n\nReason: {reason}\n\nPlease contact support if you have questions."

            # Send in-app notification (persisted)
            await notification_dispatcher.send_in_app_notification(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                title="Onboarding Rejected",
                body=body_text,
                category_code="onboarding",
                link="/onboarding",
            )

            # Send email notification
            await notification_dispatcher.send_to_user(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                channel="email",
                content=body_text,
                subject="Onboarding Rejected",
                category_code="onboarding",
            )

            logger.info(
                f"Sent rejection notification to user {user_id} "
                f"for onboarding {user_user_type_id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to send rejection notification to user {user_id}: {e}"
            )

    async def send_change_requested_notification(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        user_user_type_id: str,
        comment: str,
    ) -> None:
        """
        Send notification to user that changes are requested for their onboarding.

        Sends notifications via all user-subscribed channels with the admin's comment.

        Args:
            session: Database session
            user_id: User UUID whose submission needs changes
            organization_id: Organization UUID
            user_user_type_id: UserUserType UUID for the submission
            comment: Admin's comment explaining what changes are needed
        """
        try:
            user_uuid = UUID(user_id)

            # Send real-time WebSocket notification
            await self.broadcaster.send_to_user(
                user_uuid,
                "onboarding_change_requested",
                {
                    "message": "Changes requested for your onboarding",
                    "user_user_type_id": user_user_type_id,
                    "status": "change_requested",
                    "comment": comment,
                },
            )

            body_text = f"Changes have been requested for your onboarding submission.\n\nFeedback: {comment}\n\nPlease review and update your information accordingly."

            # Send in-app notification (persisted)
            await notification_dispatcher.send_in_app_notification(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                title="Changes Requested",
                body=body_text,
                category_code="onboarding",
                link="/onboarding",
            )

            # Send email notification
            await notification_dispatcher.send_to_user(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                channel="email",
                content=body_text,
                subject="Onboarding: Changes Requested",
                category_code="onboarding",
            )

            logger.info(
                f"Sent change requested notification to user {user_id} "
                f"for onboarding {user_user_type_id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to send change requested notification to user {user_id}: {e}"
            )

    async def send_user_responded_notification(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        user_user_type_id: str,
    ) -> None:
        """
        Send notification to org admins that a user has responded to a change request.

        Broadcasts WebSocket notification to all org admins (owner/admin roles)
        alerting them that action is required.

        Args:
            session: Database session
            user_id: User UUID who responded
            organization_id: Organization UUID
            user_user_type_id: UserUserType UUID for the submission
        """
        try:
            # Get the user details for context
            user = await self._get_user(session, user_id, organization_id)
            user_name = ""
            if user:
                user_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                if not user_name:
                    user_name = user.email

            # Get all org admin user IDs
            admin_user_ids = await self._get_org_admin_user_ids(
                session, organization_id
            )

            # Send WebSocket notification to each admin
            for admin_user_id in admin_user_ids:
                await self.broadcaster.send_to_user(
                    admin_user_id,
                    "onboarding_user_responded",
                    {
                        "message": f"{user_name} responded to change request",
                        "user_id": user_id,
                        "user_user_type_id": user_user_type_id,
                        "requires_attention": True,
                    },
                )

            logger.info(
                f"Sent user responded notification to {len(admin_user_ids)} admins "
                f"in org {organization_id} for onboarding {user_user_type_id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to send user responded notification for onboarding {user_user_type_id}: {e}"
            )

    async def send_user_resubmitted_notification(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        user_user_type_id: str,
    ) -> None:
        """
        Send notification to org admins that a user has resubmitted their onboarding.

        Broadcasts WebSocket notification to all org admins (owner/admin roles)
        alerting them that action is required.

        Args:
            session: Database session
            user_id: User UUID who resubmitted
            organization_id: Organization UUID
            user_user_type_id: UserUserType UUID for the submission
        """
        try:
            # Get the user details for context
            user = await self._get_user(session, user_id, organization_id)
            user_name = ""
            if user:
                user_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                if not user_name:
                    user_name = user.email

            # Get all org admin user IDs
            admin_user_ids = await self._get_org_admin_user_ids(
                session, organization_id
            )

            # Send WebSocket notification to each admin
            for admin_user_id in admin_user_ids:
                await self.broadcaster.send_to_user(
                    admin_user_id,
                    "onboarding_resubmitted",
                    {
                        "message": f"{user_name} resubmitted onboarding for review",
                        "user_id": user_id,
                        "user_user_type_id": user_user_type_id,
                        "status": "pending_review",
                        "requires_attention": True,
                    },
                )

            logger.info(
                f"Sent resubmission notification to {len(admin_user_ids)} admins "
                f"in org {organization_id} for onboarding {user_user_type_id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to send resubmission notification for onboarding {user_user_type_id}: {e}"
            )

    async def send_user_withdrew_notification(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        user_user_type_id: str,
        user_type_name: str,
        prior_status: str,
    ) -> None:
        """
        Send notification to org admins that a user has withdrawn from onboarding.

        Used to clear stale items from the admin review queue when a user backs
        out of an in-flight submission.
        """
        try:
            user = await self._get_user(session, user_id, organization_id)
            user_name = ""
            if user:
                user_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                if not user_name:
                    user_name = user.email

            admin_user_ids = await self._get_org_admin_user_ids(
                session, organization_id
            )

            for admin_user_id in admin_user_ids:
                await self.broadcaster.send_to_user(
                    admin_user_id,
                    "onboarding_withdrawn",
                    {
                        "message": f"{user_name} withdrew from {user_type_name} onboarding",
                        "user_id": user_id,
                        "user_user_type_id": user_user_type_id,
                        "prior_status": prior_status,
                    },
                )

            logger.info(
                f"Sent withdrawal notification to {len(admin_user_ids)} admins "
                f"in org {organization_id} for onboarding {user_user_type_id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to send withdrawal notification for onboarding {user_user_type_id}: {e}"
            )

    async def _get_org_admin_user_ids(
        self,
        session: AsyncSession,
        organization_id: str,
    ) -> list[UUID]:
        """
        Get all user IDs with admin roles (owner or admin) in the organization.

        Args:
            session: Database session
            organization_id: Organization UUID

        Returns:
            List of user UUIDs with admin roles
        """
        org_uuid = UUID(organization_id)

        # Query for users with owner or admin roles
        result = await session.execute(
            select(UserRole.user_id)
            .join(Role, UserRole.role_id == Role.id)
            .join(User, UserRole.user_id == User.id)
            .where(
                UserRole.organization_id == org_uuid,
                UserRole.deleted_time.is_(None),
                Role.name.in_(["owner", "admin"]),
                Role.deleted_time.is_(None),
                User.deleted_time.is_(None),
            )
            .distinct()
        )

        user_ids = result.scalars().all()
        return list(user_ids)

    async def _get_user(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
    ) -> Optional[User]:
        """
        Get user by ID with organization filtering.

        Args:
            session: Database session
            user_id: User UUID
            organization_id: Organization UUID

        Returns:
            User object or None
        """
        from src.crud.user import get_user_by_id

        return await get_user_by_id(session, user_id, organization_id)


# Singleton instance
onboarding_notification_service = OnboardingNotificationService()
