"""
Email Change Service for handling notifications during email change flow.

Provides methods for:
- Sending OTP to new email address
- Sending confirmation email to old email address
- Sending confirmation email to new email address
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger
from src.services.notifications import notification_dispatcher


def mask_email(email: str) -> str:
    """
    Mask email address for security purposes.

    Example: john.doe@example.com -> j***@example.com

    Args:
        email: Email address to mask

    Returns:
        Masked email address
    """
    if "@" not in email:
        return email

    local, domain = email.split("@", 1)

    if len(local) <= 1:
        masked_local = local[0] + "***"
    else:
        masked_local = local[0] + "***"

    return f"{masked_local}@{domain}"


class EmailChangeService:
    """
    Service for handling email notifications during email change process.
    """

    async def send_otp_to_new_email(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        new_email: str,
        otp_code: str,
        expires_minutes: int = 10,
    ) -> bool:
        """
        Send OTP verification code to the new email address.

        Args:
            session: Database session
            user_id: User ID requesting the change
            organization_id: Organization ID
            new_email: The new email address to send OTP to
            otp_code: 6-digit OTP code
            expires_minutes: OTP expiration time in minutes (default: 10)

        Returns:
            True if email sent successfully, False otherwise
        """
        subject = "Email Change Verification Code"
        content = f"""Your email change verification code is: {otp_code[:3]}-{otp_code[3:]}

This code will expire in {expires_minutes} minutes.

If you did not request this email change, please contact support immediately."""

        try:
            result = await notification_dispatcher.send_notification(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                channel="email",
                recipient=new_email,
                content=content,
                subject=subject,
                is_urgent=True,
            )
            if result:
                Logger.info(
                    f"OTP email sent to new email address: {mask_email(new_email)}"
                )
                return True
            else:
                Logger.error(f"Failed to send OTP email to: {mask_email(new_email)}")
                return False
        except Exception as e:
            Logger.error(f"Error sending OTP email: {e}")
            return False

    async def send_change_confirmation_to_old_email(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        old_email: str,
        new_email: str,
        timestamp: str,
        support_contact: Optional[str] = None,
    ) -> bool:
        """
        Send confirmation notification to the old email address.

        Args:
            session: Database session
            user_id: User ID
            organization_id: Organization ID
            old_email: The old (current) email address
            new_email: The new email address (will be masked)
            timestamp: Timestamp when the change occurred
            support_contact: Optional support contact information

        Returns:
            True if email sent successfully, False otherwise
        """
        masked_new_email = mask_email(new_email)
        support_text = (
            f"Contact support at: {support_contact}"
            if support_contact
            else "Contact support immediately."
        )

        subject = "Your Email Address Has Been Changed"
        content = f"""SECURITY ALERT: Your email address has been changed.

Your account email address was successfully changed at {timestamp}.

New email address: {masked_new_email}

If you did not authorize this change, your account may be compromised.
{support_text}

This is an automated security notification."""

        try:
            result = await notification_dispatcher.send_notification(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                channel="email",
                recipient=old_email,
                content=content,
                subject=subject,
                is_urgent=True,
            )
            if result:
                Logger.info(
                    f"Change confirmation sent to old email: {mask_email(old_email)}"
                )
                return True
            else:
                Logger.error(
                    f"Failed to send confirmation to old email: {mask_email(old_email)}"
                )
                return False
        except Exception as e:
            Logger.error(f"Error sending confirmation to old email: {e}")
            return False

    async def send_change_confirmation_to_new_email(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        new_email: str,
        timestamp: str,
    ) -> bool:
        """
        Send confirmation notification to the new email address.

        Args:
            session: Database session
            user_id: User ID
            organization_id: Organization ID
            new_email: The new email address
            timestamp: Timestamp when the change completed

        Returns:
            True if email sent successfully, False otherwise
        """
        subject = "Email Change Completed"
        content = f"""Your email change has been completed successfully.

Your account email address was changed at {timestamp}.

You can now use this email address to log in to your account.

SECURITY REMINDER: Keep your login credentials secure and never share them with anyone.

If you did not request this change, please contact support immediately."""

        try:
            result = await notification_dispatcher.send_notification(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                channel="email",
                recipient=new_email,
                content=content,
                subject=subject,
                is_urgent=True,
            )
            if result:
                Logger.info(
                    f"Change confirmation sent to new email: {mask_email(new_email)}"
                )
                return True
            else:
                Logger.error(
                    f"Failed to send confirmation to new email: {mask_email(new_email)}"
                )
                return False
        except Exception as e:
            Logger.error(f"Error sending confirmation to new email: {e}")
            return False


# Singleton instance
email_change_service = EmailChangeService()
