"""
Async email service using aiosmtplib with support for
organization-specific email providers (SMTP, SendGrid).
"""

from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, Optional, Union

import aiosmtplib

from src.core.config import settings
from src.logger.logger import Logger as logger
from src.services.email_templates import (
    build_otp_email,
    build_password_reset_email,
    build_welcome_email,
)


if TYPE_CHECKING:
    from src.crud.organization_email_settings import EmailConfig


class AsyncEmailService:
    """
    Async email service using aiosmtplib.
    Provides non-blocking email sending for FastAPI.
    """

    def __init__(self):
        self.server = settings.EMAIL_SERVER
        self.port = settings.EMAIL_PORT
        self.username = settings.EMAIL_USERNAME
        self.password = settings.EMAIL_PASSWORD
        self.use_tls = settings.EMAIL_USE_TLS
        self.use_ssl = settings.EMAIL_USE_SSL
        self.sender = settings.EMAIL_SENDER

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
    ) -> bool:
        """
        Send an email asynchronously.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            cc: Optional list of CC recipients
            bcc: Optional list of BCC recipients

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Create message
            message: Union[MIMEMultipart, MIMEText]
            if html_body:
                message = MIMEMultipart("alternative")
                message.attach(MIMEText(body, "plain"))
                message.attach(MIMEText(html_body, "html"))
            else:
                message = MIMEText(body, "plain")

            message["Subject"] = subject
            message["From"] = self.sender
            message["To"] = to

            if cc:
                message["Cc"] = ", ".join(cc)

            # Build recipient list
            recipients = [to]
            if cc:
                recipients.extend(cc)
            if bcc:
                recipients.extend(bcc)

            # Send email
            await aiosmtplib.send(
                message,
                hostname=self.server,
                port=self.port,
                username=self.username,
                password=self.password,
                use_tls=self.use_ssl,  # use_tls in aiosmtplib means implicit TLS (port 465)
                start_tls=self.use_tls and not self.use_ssl,  # STARTTLS for port 587
            )

            logger.info(f"Email sent successfully to {to}")
            return True

        except aiosmtplib.SMTPException as e:
            logger.error(f"SMTP error sending email to {to}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending email to {to}: {e}")
            return False

    async def send_with_config(
        self,
        to: str,
        subject: str,
        body: str,
        config: EmailConfig,
        html_body: Optional[str] = None,
    ) -> bool:
        """
        Send an email using organization-specific email configuration.

        Dispatches to the correct provider (SMTP or SendGrid) based on config.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Plain text body
            config: Organization-resolved email configuration
            html_body: Optional HTML body

        Returns:
            True if email sent successfully, False otherwise
        """
        if config.provider == "sendgrid":
            return await self._send_via_sendgrid(
                to=to,
                subject=subject,
                body=body,
                html_body=html_body,
                config=config,
            )
        else:
            return await self._send_via_smtp(
                to=to,
                subject=subject,
                body=body,
                html_body=html_body,
                config=config,
            )

    async def _send_via_smtp(
        self,
        to: str,
        subject: str,
        body: str,
        config: EmailConfig,
        html_body: Optional[str] = None,
    ) -> bool:
        """Send email via SMTP using the provided config."""
        try:
            message: Union[MIMEMultipart, MIMEText]
            if html_body:
                message = MIMEMultipart("alternative")
                message.attach(MIMEText(body, "plain"))
                message.attach(MIMEText(html_body, "html"))
            else:
                message = MIMEText(body, "plain")

            sender = config.sender_email or self.sender
            message["Subject"] = subject
            message["From"] = sender
            message["To"] = to

            await aiosmtplib.send(
                message,
                hostname=config.smtp_host,
                port=config.smtp_port,
                username=config.smtp_username,
                password=config.smtp_password,
                use_tls=config.smtp_use_ssl,
                start_tls=config.smtp_use_tls and not config.smtp_use_ssl,
            )

            logger.info(f"Email sent via SMTP to {to}")
            return True

        except aiosmtplib.SMTPException as e:
            logger.error(f"SMTP error sending email to {to}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending email via SMTP to {to}: {e}")
            return False

    async def _send_via_sendgrid(
        self,
        to: str,
        subject: str,
        body: str,
        config: EmailConfig,
        html_body: Optional[str] = None,
    ) -> bool:
        """Send email via SendGrid using the provided config."""
        try:
            from src.services.notifications.sendgrid_provider import SendGridProvider

            provider = SendGridProvider(
                api_key=config.sendgrid_api_key,
                sender_email=config.sender_email,
                sender_name=config.sender_name,
            )

            result = await provider.send(
                recipient=to,
                message=body,
                subject=subject,
                html_message=html_body,
            )

            if result.success:
                logger.info(f"Email sent via SendGrid to {to}")
                return True
            else:
                logger.error(f"SendGrid send failed for {to}: {result.error_message}")
                return False

        except Exception as e:
            logger.error(f"Error sending email via SendGrid to {to}: {e}")
            return False

    async def send_otp_email(
        self,
        to: str,
        otp_code: str,
        expires_minutes: int = 10,
        config: Optional[EmailConfig] = None,
    ) -> bool:
        """
        Send OTP verification email.

        Args:
            to: Recipient email address
            otp_code: The OTP code
            expires_minutes: OTP expiration time in minutes
            config: Optional org-specific email config
        """
        subject = "Your Verification Code"
        body = f"""
Your verification code is: {otp_code[:3]}-{otp_code[3:]}

This code will expire in {expires_minutes} minutes.

If you did not request this code, please ignore this email.
"""
        html_body = build_otp_email(
            otp_code=f"{otp_code[:3]}-{otp_code[3:]}", expires_minutes=expires_minutes
        )
        if config:
            return await self.send_with_config(to, subject, body, config, html_body)
        return await self.send_email(to, subject, body, html_body)

    async def send_password_reset_email(
        self,
        to: str,
        reset_token: str,
        reset_url: str,
        config: Optional[EmailConfig] = None,
    ) -> bool:
        """
        Send password reset email.

        Args:
            to: Recipient email address
            reset_token: Password reset token
            reset_url: Full URL for password reset
            config: Optional org-specific email config
        """
        subject = "Password Reset Request"
        body = f"""
You have requested to reset your password.

Click the following link to reset your password:
{reset_url}

This link will expire in 1 hour.

If you did not request a password reset, please ignore this email.
"""
        html_body = build_password_reset_email(reset_url=reset_url, expires_hours=1)
        if config:
            return await self.send_with_config(to, subject, body, config, html_body)
        return await self.send_email(to, subject, body, html_body)

    async def send_welcome_email(
        self,
        to: str,
        user_name: str,
        organization_name: str,
        config: Optional[EmailConfig] = None,
    ) -> bool:
        """
        Send welcome email to new user.

        Args:
            to: Recipient email address
            user_name: User's name
            organization_name: Organization name
            config: Optional org-specific email config
        """
        subject = f"Welcome to {organization_name}"
        body = f"""
Hello {user_name},

Welcome to {organization_name}!

Your account has been created successfully. You can now log in and start using the platform.

If you have any questions, please contact support.

Best regards,
The Team
"""
        html_body = build_welcome_email(
            user_name=user_name,
            organization_name=organization_name,
        )
        if config:
            return await self.send_with_config(to, subject, body, config, html_body)
        return await self.send_email(to, subject, body, html_body)


# Singleton instance
email_service = AsyncEmailService()
