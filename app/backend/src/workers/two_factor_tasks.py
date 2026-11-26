"""
Two-Factor Authentication background tasks.
Handles notifications and policy enforcement for 2FA.
"""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import select

from src.crud.notification import prepare_body_preview
from src.logger.logger import Logger as logger
from src.logger.logger import print_exception_with_trace
from src.models.organization_two_factor_settings import OrganizationTwoFactorSettings
from src.models.user import User
from src.models.user_two_factor import UserTwoFactor
from src.services.tasks import task_queue


async def notify_2fa_mandatory_change(ctx, organization_id: str) -> dict:
    """
    Send notifications to users without 2FA when policy changes to mandatory.
    Called when an organization's 2FA policy changes from optional to mandatory.

    Args:
        ctx: ARQ context with session_factory
        organization_id: UUID of the organization

    Returns:
        dict: Summary of notifications sent
    """
    session_factory = ctx.get("session_factory")
    if not session_factory:
        logger.error("No session_factory in context")
        raise RuntimeError("Database session factory not available")

    async with session_factory() as session:
        try:
            org_uuid = UUID(organization_id)

            # Get organization 2FA settings
            settings_result = await session.execute(
                select(OrganizationTwoFactorSettings).where(
                    OrganizationTwoFactorSettings.organization_id == org_uuid,
                    OrganizationTwoFactorSettings.deleted_time.is_(None),
                )
            )
            settings = settings_result.scalar_one_or_none()

            if not settings:
                logger.warning(
                    f"2FA settings not found for organization {organization_id}"
                )
                return {"status": "not_found", "organization_id": organization_id}

            if not settings.enforcement_start_time:
                logger.warning(
                    f"No enforcement_start_time set for organization {organization_id}"
                )
                return {
                    "status": "no_enforcement_time",
                    "organization_id": organization_id,
                }

            # Calculate deadline
            deadline = settings.enforcement_start_time + timedelta(
                days=settings.grace_period_days
            )

            # Find all active users in the organization without 2FA enabled
            users_result = await session.execute(
                select(User)
                .outerjoin(
                    UserTwoFactor,
                    (UserTwoFactor.user_id == User.id)
                    & (UserTwoFactor.deleted_time.is_(None)),
                )
                .where(
                    User.organization_id == org_uuid,
                    User.deleted_time.is_(None),
                    (UserTwoFactor.id.is_(None) | ~UserTwoFactor.is_enabled),
                )
            )
            users_without_2fa = users_result.scalars().all()

            notification_count = 0
            failed_count = 0

            # Import notification dependencies here to avoid circular imports
            from src.models.notification import Notification

            for user in users_without_2fa:
                try:
                    # Prepare notification body
                    body = f"""Hello {user.first_name or 'there'},

Your organization has enabled mandatory Two-Factor Authentication (2FA) for enhanced security.

You are required to set up 2FA before {deadline.strftime('%Y-%m-%d %H:%M UTC')}.

After this deadline, you will be prompted to complete 2FA setup when you next log in.

To set up 2FA now, please visit your Security Settings:
- Log in to your account
- Navigate to Settings > Security > Two-Factor Authentication
- Follow the setup instructions

If you have any questions, please contact your organization administrator.

Thank you,
Security Team"""

                    # Create notification record.
                    #
                    # !!! DEFERRED-SEND PAYLOAD - READ BEFORE REUSING THIS
                    # !!! PATTERN FOR ANYTHING CREDENTIAL-BEARING.
                    #
                    # extra_data["body"] is not metadata: it is the delivery
                    # payload. send_notification_task() reads it back as the
                    # message content (src/workers/tasks.py), because this
                    # record is created directly rather than through
                    # crud.notification.create_notification() and body_preview
                    # is both truncated and scrubbed. Redacting it here would
                    # therefore not protect anything - it would send
                    # "[redacted]" to the user.
                    #
                    # The constraint that makes that acceptable *today* is that
                    # this body is the 2FA-mandate notice: a deadline and a
                    # link to Settings, no token, no OTP, nothing that is a
                    # credential. Notification.extra_data is returned verbatim
                    # by GET /notifications to any holder of
                    # `notifications:read` - i.e. org admins, not just the
                    # recipient - so a fork that reuses this pattern to defer
                    # an OTP or a reset link would publish a live credential to
                    # every admin in the organization.
                    #
                    # If you need to defer a credential-bearing message, do NOT
                    # widen this dict. Either send it inline through
                    # NotificationDispatcher.send_notification() (which hands
                    # the provider the real content and persists only a
                    # scrubbed preview), or add a store that is not projected
                    # by the notification API. As a defence in depth,
                    # send_notification_task() drops the deferred payload keys
                    # from extra_data as soon as delivery succeeds, so the body
                    # is transient rather than archived.
                    #
                    # body_preview goes through the same scrubbing and length
                    # policy crud.notification.create_notification() applies,
                    # so this hand-built record is not a hole in that control.
                    # (The subject is a literal constant, so it needs none.)
                    notification = Notification(
                        organization_id=org_uuid,
                        user_id=user.id,
                        channel="email",
                        recipient=user.email,
                        subject="Two-Factor Authentication Now Mandatory",
                        body_preview=prepare_body_preview(body),
                        status="pending",
                        extra_data={
                            "category": "security",
                            # Delivery payload - see the warning above.
                            "body": body,
                            "deadline": deadline.isoformat(),
                            "enforcement_start_time": settings.enforcement_start_time.isoformat(),
                            "grace_period_days": settings.grace_period_days,
                        },
                    )
                    session.add(notification)
                    await session.flush()

                    # Enqueue notification task
                    await task_queue.enqueue_job(
                        "send_notification_task", notification_id=str(notification.id)
                    )
                    notification_count += 1

                except Exception as e:
                    logger.error(
                        f"Failed to create notification for user {user.id}: {e}"
                    )
                    failed_count += 1

            await session.commit()

            logger.info(
                f"2FA mandatory notifications for org {organization_id}: "
                f"sent={notification_count}, failed={failed_count}"
            )

            return {
                "status": "completed",
                "organization_id": organization_id,
                "notifications_queued": notification_count,
                "failed": failed_count,
                "deadline": deadline.isoformat(),
            }

        except Exception as exc:
            await session.rollback()
            print_exception_with_trace(
                exc,
                f"Error sending 2FA mandatory notifications for org {organization_id}",
            )
            logger.error(
                f"Error sending 2FA mandatory notifications for org {organization_id}: {exc}"
            )
            raise
