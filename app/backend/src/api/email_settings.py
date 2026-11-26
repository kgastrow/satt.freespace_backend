"""
Organization Email Settings API endpoints.

Provides endpoints for managing per-organization email configuration
including SMTP and SendGrid provider settings.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_session,
    require_permission,
)
from src.core.config import settings
from src.core.exceptions import create_http_exception
from src.core.rate_limit import limiter
from src.core.response_codes import get_response_code
from src.crud.organization_email_settings import (
    delete_organization_email_settings,
    get_decrypted_settings,
    get_effective_email_config,
    get_or_create_organization_email_settings,
    get_organization_email_settings,
    update_organization_email_settings,
)
from src.logger.logger import Logger
from src.models.audit_log import AuditAction
from src.serialisers.organization_email_settings import (
    EffectiveEmailConfigResponse,
    EmailSettingsResponse,
    ResetEmailSettingsResponse,
    TestEmailRequest,
    TestEmailResponse,
    UpdateEmailSettingsRequest,
    build_effective_config_response,
    build_email_settings_response,
)
from src.services.audit import compute_changes, create_audit_log


router = APIRouter(prefix="/email-settings", tags=["email-settings"])


@router.get(
    "",
    response_model=EmailSettingsResponse,
    summary="Get organization email settings",
)
async def get_email_settings(
    current_user: Annotated[
        CurrentUser, Depends(require_permission("email_settings:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get the current organization's email settings.

    Returns the organization-specific email configuration. If no custom
    settings exist, returns default values indicating platform defaults will be used.

    Requires email_settings:read permission.
    """
    organization_id = str(current_user.organization_id)

    email_settings = await get_or_create_organization_email_settings(
        session, organization_id
    )
    decrypted = get_decrypted_settings(email_settings)

    return build_email_settings_response(email_settings, decrypted)


@router.get(
    "/effective",
    response_model=EffectiveEmailConfigResponse,
    summary="Get effective email configuration",
)
async def get_effective_email_settings(
    current_user: Annotated[
        CurrentUser, Depends(require_permission("email_settings:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get the effective (merged) email configuration for the organization.

    This shows what email settings will actually be used when sending emails,
    including any fallback to platform defaults.

    Requires email_settings:read permission.
    """
    organization_id = str(current_user.organization_id)

    email_config = await get_effective_email_config(session, organization_id)

    # Determine config source
    org_settings = await get_organization_email_settings(session, organization_id)
    if org_settings and org_settings.provider:
        config_source = "organization"
    elif org_settings:
        config_source = "platform"
    else:
        config_source = "default"

    return build_effective_config_response(email_config, config_source)


@router.put(
    "",
    response_model=EmailSettingsResponse,
    summary="Update organization email settings",
)
async def update_email_settings(
    http_request: Request,
    request: UpdateEmailSettingsRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("email_settings:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update the organization's email settings.

    Allows configuring:
    - Email provider (SMTP or SendGrid)
    - SMTP server settings and credentials
    - SendGrid API key
    - Sender email/name and reply-to address

    Set provider to null to use platform defaults.
    Credentials are stored encrypted.

    Requires email_settings:write permission.
    """
    organization_id = str(current_user.organization_id)

    # Extract request metadata for audit logging
    ip_address = http_request.client.host if http_request.client else None
    user_agent = http_request.headers.get("User-Agent")

    # Get old settings for audit log
    old_settings = await get_organization_email_settings(session, organization_id)
    old_provider = old_settings.provider if old_settings else None

    # Build update data, converting enum to string
    update_data = request.model_dump(exclude_unset=True)
    if "provider" in update_data and update_data["provider"] is not None:
        update_data["provider"] = update_data["provider"].value

    # Sender branding (sender_email, sender_name, reply_to_email) belongs to
    # the org's own provider config. When the org is on platform defaults
    # (provider IS NULL), the platform's sender identity is authoritative —
    # SendGrid in particular requires verified senders that only the platform
    # owns, so allowing org-level overrides would silently fail at send time.
    # Reject any update that would leave the org on platform defaults while
    # also setting a branding field.
    resulting_provider = (
        update_data["provider"] if "provider" in update_data else old_provider
    )
    if resulting_provider is None:
        locked_fields = [
            f for f in ("sender_email", "sender_name", "reply_to_email")
            if update_data.get(f) is not None
        ]
        if locked_fields:
            raise create_http_exception(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Cannot set sender branding while using platform defaults. "
                    "Select a provider (SMTP or SendGrid) first. "
                    f"Locked fields: {', '.join(locked_fields)}"
                ),
                detail_code="email_settings.sender_locked_on_platform_defaults",
            )

    email_settings = await update_organization_email_settings(
        session, organization_id, update_data
    )

    # Audit log with IP and User-Agent
    await create_audit_log(
        session=session,
        organization_id=organization_id,
        action=AuditAction.UPDATE,
        resource_type="EmailSettings",
        resource_id=str(email_settings.id),
        actor_id=str(current_user.id),
        changes=compute_changes(
            {"provider": old_provider} if old_provider else {},
            {"provider": email_settings.provider},
        ),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    decrypted = get_decrypted_settings(email_settings)
    return build_email_settings_response(email_settings, decrypted)


@router.post(
    "/test",
    response_model=TestEmailResponse,
    summary="Send a test email",
)
@limiter.limit(settings.RATE_LIMIT_EMAIL_TEST)
async def send_test_email(
    http_request: Request,
    request: TestEmailRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("email_settings:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Send a test email using the current email configuration.

    Uses the effective email settings (organization or platform defaults)
    to send a test email to the specified recipient.

    Rate limited to prevent abuse (5 per 5 minutes).

    Requires email_settings:write permission.
    """
    organization_id = str(current_user.organization_id)

    # Extract request metadata for audit logging
    ip_address = http_request.client.host if http_request.client else None
    user_agent = http_request.headers.get("User-Agent")

    email_service = None
    try:
        # Get effective email config
        email_config = await get_effective_email_config(session, organization_id)

        # Import and use the appropriate provider
        if email_config.provider == "sendgrid":
            if not email_config.sendgrid_api_key:
                raise create_http_exception(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="SendGrid API key is not configured",
                    detail_code="email_settings.sendgrid_not_configured",
                )

            from src.services.notifications.sendgrid_provider import SendGridProvider

            provider = SendGridProvider(api_key=email_config.sendgrid_api_key)
            result = await provider.send(
                recipient=request.recipient_email,
                message="This is a test email from your organization's email settings.",
                subject="Test Email - Email Settings Verification",
                html_message="<h2>Test Email</h2><p>This is a test email from your organization's email settings configuration.</p><p>If you received this email, your email settings are working correctly.</p>",
                metadata={
                    "sender_email": email_config.sender_email,
                    "sender_name": email_config.sender_name,
                },
            )
        else:
            # Use SMTP
            from src.services.email import AsyncEmailService

            email_service = AsyncEmailService()
            # Override with org settings
            email_service.server = email_config.smtp_host or email_service.server
            email_service.port = email_config.smtp_port or email_service.port
            email_service.username = (
                email_config.smtp_username or email_service.username
            )
            email_service.password = (
                email_config.smtp_password or email_service.password
            )
            email_service.use_tls = email_config.smtp_use_tls
            email_service.use_ssl = email_config.smtp_use_ssl
            email_service.sender = email_config.sender_email or email_service.sender

            try:
                success = await email_service.send_email(
                    to=request.recipient_email,
                    subject="Test Email - Email Settings Verification",
                    body="This is a test email from your organization's email settings. If you received this email, your email settings are working correctly.",
                    html_body="<h2>Test Email</h2><p>This is a test email from your organization's email settings configuration.</p><p>If you received this email, your email settings are working correctly.</p>",
                )
            finally:
                # Clear credentials from memory after use
                email_service.password = None
                email_service.username = None

            if not success:
                return TestEmailResponse(
                    success=False,
                    message="Failed to send test email. Please check your SMTP settings.",
                    message_code=get_response_code("email_settings.test_failed"),
                    provider_used="smtp",
                )

            result = type("obj", (object,), {"success": True})()

        # Audit log with IP and User-Agent (test_email action recorded as UPDATE)
        await create_audit_log(
            session=session,
            organization_id=organization_id,
            action=AuditAction.UPDATE,
            resource_type="EmailSettings",
            resource_id=organization_id,
            actor_id=str(current_user.id),
            changes={
                "test_email": {
                    "old": None,
                    "new": {
                        "recipient": request.recipient_email,
                        "provider": email_config.provider,
                    },
                }
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        if result.success:
            return TestEmailResponse(
                success=True,
                message="Test email sent successfully",
                message_code=get_response_code("email_settings.test_success"),
                provider_used=email_config.provider,
            )
        else:
            return TestEmailResponse(
                success=False,
                message="Failed to send test email",
                message_code=get_response_code("email_settings.test_failed"),
                provider_used=email_config.provider,
            )

    except Exception as e:
        # Log full exception details server-side for debugging
        Logger.error(
            f"Test email failed for org {organization_id}: {str(e)}", exc_info=True
        )
        # Return generic error message to user (avoid information disclosure)
        return TestEmailResponse(
            success=False,
            message="Failed to send test email. Please verify your settings.",
            message_code=get_response_code("email_settings.test_failed"),
            provider_used="unknown",
        )
    finally:
        # Ensure credentials are cleared even on exception
        if email_service is not None:
            email_service.password = None
            email_service.username = None


@router.delete(
    "",
    response_model=ResetEmailSettingsResponse,
    summary="Reset to platform defaults",
)
async def reset_email_settings(
    http_request: Request,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("email_settings:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Reset organization email settings to platform defaults.

    This soft-deletes the organization's custom email settings,
    causing the platform-wide defaults to be used instead.

    Requires email_settings:write permission.
    """
    organization_id = str(current_user.organization_id)

    # Extract request metadata for audit logging
    ip_address = http_request.client.host if http_request.client else None
    user_agent = http_request.headers.get("User-Agent")

    # Get old settings for audit log
    old_settings = await get_organization_email_settings(session, organization_id)

    if not old_settings:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No custom email settings found",
            detail_code="email_settings.not_found",
        )

    deleted = await delete_organization_email_settings(session, organization_id)

    if deleted:
        # Audit log with IP and User-Agent
        await create_audit_log(
            session=session,
            organization_id=organization_id,
            action=AuditAction.DELETE,
            resource_type="EmailSettings",
            resource_id=str(old_settings.id),
            actor_id=str(current_user.id),
            changes={"provider": {"old": old_settings.provider, "new": None}},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    return ResetEmailSettingsResponse(
        message="Email settings reset to platform defaults",
        message_code=get_response_code("email_settings.reset_success"),
    )
