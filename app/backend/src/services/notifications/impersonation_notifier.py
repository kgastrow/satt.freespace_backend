"""
Impersonation Notifier Service.

Sends notifications to target users when they are impersonated by super admins.
Notifies on both impersonation start and end events via email and in-app channels.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger as logger
from src.models.user import User
from src.services.notifications import notification_dispatcher


def format_duration(seconds: float) -> str:
    """
    Format a duration in seconds to a human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Human-readable duration string (e.g., "5 minutes", "1 hour 30 minutes")
    """
    if seconds < 60:
        return f"{int(seconds)} second{'s' if seconds != 1 else ''}"

    minutes = int(seconds // 60)
    hours = int(minutes // 60)
    remaining_minutes = minutes % 60

    if hours == 0:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    elif remaining_minutes == 0:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    else:
        hour_str = f"{hours} hour{'s' if hours != 1 else ''}"
        min_str = f"{remaining_minutes} minute{'s' if remaining_minutes != 1 else ''}"
        return f"{hour_str} {min_str}"


class ImpersonationNotifier:
    """
    Service for sending impersonation-related notifications to target users.

    Sends both email and in-app notifications when a super admin starts or
    ends impersonating a user. Respects user notification preferences.
    """

    async def notify_start(
        self,
        session: AsyncSession,
        target_user_id: str,
        target_organization_id: str,
        impersonator_id: str,
        started_at: datetime,
    ) -> dict:
        """
        Notify target user that impersonation has started.

        Sends both email and in-app notifications to inform the user that
        a super admin is now impersonating their account.

        Args:
            session: Database session
            target_user_id: UUID of the user being impersonated
            target_organization_id: UUID of the target user's organization
            impersonator_id: UUID of the super admin who initiated impersonation
            started_at: Timestamp when impersonation started

        Returns:
            Dict with notification results for each channel
        """
        impersonator = await self._get_user(session, impersonator_id)
        if not impersonator:
            logger.error(f"Impersonator not found: {impersonator_id}")
            return {"email": None, "in_app": None, "error": "Impersonator not found"}

        impersonator_name = self._get_display_name(impersonator)
        formatted_time = started_at.strftime("%Y-%m-%d %H:%M:%S UTC")

        email_subject = "Account Access Notification"
        email_content = (
            f"A super administrator ({impersonator_name}) has started accessing your account.\n\n"
            f"Started at: {formatted_time}\n\n"
            "This access is for support or administrative purposes. "
            "If you did not request assistance, please contact your administrator."
        )

        in_app_title = "Account Access Started"
        in_app_body = (
            f"Administrator {impersonator_name} has started accessing your account."
        )

        results = {}

        # Send email notification
        try:
            email_result = await notification_dispatcher.send_to_user(
                session=session,
                user_id=target_user_id,
                organization_id=target_organization_id,
                channel="email",
                content=email_content,
                category_code="account",
                is_urgent=True,
                subject=email_subject,
            )
            results["email"] = email_result
        except Exception as e:
            logger.error(f"Failed to send impersonation start email: {e}")
            results["email"] = {"error": str(e)}

        # Send in-app notification
        try:
            in_app_result = await notification_dispatcher.send_in_app_notification(
                session=session,
                user_id=target_user_id,
                organization_id=target_organization_id,
                title=in_app_title,
                body=in_app_body,
                category_code="account",
            )
            results["in_app"] = in_app_result
        except Exception as e:
            logger.error(f"Failed to send impersonation start in-app notification: {e}")
            results["in_app"] = {"error": str(e)}

        logger.info(
            f"Impersonation start notifications sent to user {target_user_id} "
            f"(impersonator: {impersonator_id})"
        )

        return results

    async def notify_end(
        self,
        session: AsyncSession,
        target_user_id: str,
        target_organization_id: str,
        impersonator_id: str,
        started_at: datetime,
        ended_at: datetime,
    ) -> dict:
        """
        Notify target user that impersonation has ended.

        Sends both email and in-app notifications to inform the user that
        the super admin has stopped impersonating their account, including
        the duration of the impersonation session.

        Args:
            session: Database session
            target_user_id: UUID of the user who was impersonated
            target_organization_id: UUID of the target user's organization
            impersonator_id: UUID of the super admin who was impersonating
            started_at: Timestamp when impersonation started
            ended_at: Timestamp when impersonation ended

        Returns:
            Dict with notification results for each channel
        """
        impersonator = await self._get_user(session, impersonator_id)
        if not impersonator:
            logger.error(f"Impersonator not found: {impersonator_id}")
            return {"email": None, "in_app": None, "error": "Impersonator not found"}

        impersonator_name = self._get_display_name(impersonator)
        duration_seconds = (ended_at - started_at).total_seconds()
        duration_str = format_duration(duration_seconds)
        formatted_end_time = ended_at.strftime("%Y-%m-%d %H:%M:%S UTC")

        email_subject = "Account Access Ended"
        email_content = (
            f"A super administrator ({impersonator_name}) has ended accessing your account.\n\n"
            f"Session ended at: {formatted_end_time}\n"
            f"Duration: {duration_str}\n\n"
            "If you have any concerns about this access, please contact your administrator."
        )

        in_app_title = "Account Access Ended"
        in_app_body = (
            f"Administrator {impersonator_name} has ended accessing your account. "
            f"Duration: {duration_str}."
        )

        results = {}

        # Send email notification
        try:
            email_result = await notification_dispatcher.send_to_user(
                session=session,
                user_id=target_user_id,
                organization_id=target_organization_id,
                channel="email",
                content=email_content,
                category_code="account",
                is_urgent=True,
                subject=email_subject,
            )
            results["email"] = email_result
        except Exception as e:
            logger.error(f"Failed to send impersonation end email: {e}")
            results["email"] = {"error": str(e)}

        # Send in-app notification
        try:
            in_app_result = await notification_dispatcher.send_in_app_notification(
                session=session,
                user_id=target_user_id,
                organization_id=target_organization_id,
                title=in_app_title,
                body=in_app_body,
                category_code="account",
            )
            results["in_app"] = in_app_result
        except Exception as e:
            logger.error(f"Failed to send impersonation end in-app notification: {e}")
            results["in_app"] = {"error": str(e)}

        logger.info(
            f"Impersonation end notifications sent to user {target_user_id} "
            f"(impersonator: {impersonator_id}, duration: {duration_str})"
        )

        return results

    async def _get_user(self, session: AsyncSession, user_id: str) -> Optional[User]:
        """
        Get a user by ID.

        Args:
            session: Database session
            user_id: UUID string of the user

        Returns:
            User object or None if not found
        """
        from uuid import UUID

        result = await session.execute(
            select(User).where(
                User.id == UUID(user_id),
                User.deleted_time.is_(None),
            )
        )
        return result.scalar_one_or_none()

    def _get_display_name(self, user: User) -> str:
        """
        Get a display name for a user.

        Returns full name if available, otherwise email.

        Args:
            user: User object

        Returns:
            Display name string
        """
        if user.first_name and user.last_name:
            return f"{user.first_name} {user.last_name}"
        elif user.first_name:
            return user.first_name
        else:
            return user.email


# Singleton instance
impersonation_notifier = ImpersonationNotifier()
