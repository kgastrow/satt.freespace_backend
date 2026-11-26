"""
Generic HTML email templates.

Provides reusable, responsive HTML email templates with consistent styling
that works across major email clients.
"""

import re
from typing import Any, Optional


# Regex pattern for variable substitution
_VARIABLE_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _render_variables(template: str, variables: dict[str, Any]) -> str:
    """
    Substitute {variable} placeholders with values.

    Args:
        template: Template string with {variable} placeholders
        variables: Dictionary of variable names to values

    Returns:
        Rendered string with variables substituted
    """
    if not template or not variables:
        return template

    def replace_var(match: re.Match) -> str:
        var_name = match.group(1)
        if var_name in variables:
            return str(variables[var_name])
        return match.group(0)

    return _VARIABLE_PATTERN.sub(replace_var, template)


# Default brand colors - can be overridden via variables
DEFAULT_COLORS = {
    "primary": "#2563eb",  # Blue
    "primary_dark": "#1d4ed8",
    "secondary": "#64748b",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "error": "#ef4444",
    "background": "#f8fafc",
    "surface": "#ffffff",
    "text": "#1e293b",
    "text_muted": "#64748b",
    "border": "#e2e8f0",
}


BASE_EMAIL_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>{subject}</title>
    <!--[if mso]>
    <noscript>
        <xml>
            <o:OfficeDocumentSettings>
                <o:PixelsPerInch>96</o:PixelsPerInch>
            </o:OfficeDocumentSettings>
        </xml>
    </noscript>
    <![endif]-->
    <style type="text/css">
        /* Reset styles */
        body, table, td, p, a, li, blockquote {{
            -webkit-text-size-adjust: 100%;
            -ms-text-size-adjust: 100%;
        }}
        table, td {{
            mso-table-lspace: 0pt;
            mso-table-rspace: 0pt;
        }}
        img {{
            -ms-interpolation-mode: bicubic;
            border: 0;
            height: auto;
            line-height: 100%;
            outline: none;
            text-decoration: none;
        }}
        body {{
            margin: 0 !important;
            padding: 0 !important;
            width: 100% !important;
            height: 100% !important;
        }}
        a[x-apple-data-detectors] {{
            color: inherit !important;
            text-decoration: none !important;
            font-size: inherit !important;
            font-family: inherit !important;
            font-weight: inherit !important;
            line-height: inherit !important;
        }}
        /* Responsive styles */
        @media screen and (max-width: 600px) {{
            .container {{
                width: 100% !important;
                padding: 10px !important;
            }}
            .content {{
                padding: 20px !important;
            }}
            .button {{
                width: 100% !important;
                display: block !important;
            }}
        }}
    </style>
</head>
<body style="margin: 0; padding: 0; background-color: {background_color}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background-color: {background_color};">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <!-- Main Container -->
                <table role="presentation" cellpadding="0" cellspacing="0" width="600" class="container" style="max-width: 600px; width: 100%;">
                    <!-- Header -->
                    {header_html}

                    <!-- Content -->
                    <tr>
                        <td class="content" style="background-color: {surface_color}; padding: 40px; border-radius: 0 0 8px 8px;">
                            {content_html}
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 30px 20px; text-align: center;">
                            {footer_html}
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

DEFAULT_HEADER = """
<tr>
    <td style="background-color: {primary_color}; padding: 30px 40px; border-radius: 8px 8px 0 0; text-align: center;">
        {logo_html}
        <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600; line-height: 1.4;">
            {header_title}
        </h1>
    </td>
</tr>
"""

DEFAULT_FOOTER = """
<p style="margin: 0 0 10px 0; color: {text_muted_color}; font-size: 14px;">
    {footer_text}
</p>
<p style="margin: 0; color: {text_muted_color}; font-size: 12px;">
    {copyright_text}
</p>
{unsubscribe_html}
"""


def render_button(
    text: str,
    url: str,
    color: str = DEFAULT_COLORS["primary"],
    text_color: str = "#ffffff",
) -> str:
    """
    Render an email-safe button.

    Args:
        text: Button text
        url: Button link URL
        color: Background color (hex)
        text_color: Text color (hex)

    Returns:
        HTML string for the button
    """
    return f"""
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin: 25px auto;">
        <tr>
            <td style="border-radius: 6px; background-color: {color};">
                <a href="{url}" target="_blank" style="display: inline-block; padding: 14px 32px; font-size: 16px; font-weight: 600; color: {text_color}; text-decoration: none; border-radius: 6px;">
                    {text}
                </a>
            </td>
        </tr>
    </table>
    """


def render_alert(
    message: str,
    alert_type: str = "info",
) -> str:
    """
    Render an alert/notice box.

    Args:
        message: Alert message
        alert_type: One of "info", "success", "warning", "error"

    Returns:
        HTML string for the alert box
    """
    colors = {
        "info": {"bg": "#eff6ff", "border": "#2563eb", "text": "#1e40af"},
        "success": {"bg": "#f0fdf4", "border": "#22c55e", "text": "#166534"},
        "warning": {"bg": "#fffbeb", "border": "#f59e0b", "text": "#92400e"},
        "error": {"bg": "#fef2f2", "border": "#ef4444", "text": "#991b1b"},
    }
    style = colors.get(alert_type, colors["info"])

    return f"""
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin: 20px 0;">
        <tr>
            <td style="background-color: {style['bg']}; border-left: 4px solid {style['border']}; padding: 15px 20px; border-radius: 0 6px 6px 0;">
                <p style="margin: 0; color: {style['text']}; font-size: 14px; line-height: 1.5;">
                    {message}
                </p>
            </td>
        </tr>
    </table>
    """


def render_code_block(code: str, font_size: str = "28px") -> str:
    """
    Render a code/OTP display block.

    Args:
        code: The code to display (e.g., OTP)
        font_size: Font size for the code

    Returns:
        HTML string for the code block
    """
    return f"""
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin: 25px 0;">
        <tr>
            <td style="background-color: #f1f5f9; padding: 20px; text-align: center; border-radius: 8px;">
                <span style="font-family: 'Courier New', monospace; font-size: {font_size}; font-weight: 700; letter-spacing: 8px; color: #0f172a;">
                    {code}
                </span>
            </td>
        </tr>
    </table>
    """


def render_divider() -> str:
    """Render a horizontal divider line."""
    return """
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin: 25px 0;">
        <tr>
            <td style="border-top: 1px solid #e2e8f0;"></td>
        </tr>
    </table>
    """


def render_paragraph(text: str, muted: bool = False) -> str:
    """
    Render a paragraph of text.

    Args:
        text: Paragraph text
        muted: If True, use muted (gray) text color

    Returns:
        HTML string for the paragraph
    """
    color = DEFAULT_COLORS["text_muted"] if muted else DEFAULT_COLORS["text"]
    return f"""
    <p style="margin: 0 0 16px 0; color: {color}; font-size: 16px; line-height: 1.6;">
        {text}
    </p>
    """


def render_heading(text: str, level: int = 2) -> str:
    """
    Render a heading.

    Args:
        text: Heading text
        level: Heading level (1-3)

    Returns:
        HTML string for the heading
    """
    sizes = {1: "28px", 2: "22px", 3: "18px"}
    margins = {1: "0 0 20px 0", 2: "25px 0 15px 0", 3: "20px 0 10px 0"}
    size = sizes.get(level, sizes[2])
    margin = margins.get(level, margins[2])

    return f"""
    <h{level} style="margin: {margin}; color: {DEFAULT_COLORS['text']}; font-size: {size}; font-weight: 600; line-height: 1.3;">
        {text}
    </h{level}>
    """


def render_list(items: list, ordered: bool = False) -> str:
    """
    Render an ordered or unordered list.

    Args:
        items: List of item strings
        ordered: If True, render as numbered list

    Returns:
        HTML string for the list
    """
    tag = "ol" if ordered else "ul"
    list_items = "".join(
        f'<li style="margin-bottom: 8px; color: {DEFAULT_COLORS["text"]}; font-size: 16px; line-height: 1.6;">{item}</li>'
        for item in items
    )

    return f"""
    <{tag} style="margin: 15px 0; padding-left: 20px;">
        {list_items}
    </{tag}>
    """


def build_email_html(
    subject: str,
    content_html: str,
    header_title: Optional[str] = None,
    logo_url: Optional[str] = None,
    footer_text: Optional[str] = None,
    copyright_text: Optional[str] = None,
    unsubscribe_url: Optional[str] = None,
    primary_color: Optional[str] = None,
    variables: Optional[dict[str, Any]] = None,
) -> str:
    """
    Build a complete HTML email using the base template.

    Args:
        subject: Email subject (used in title tag)
        content_html: Main content HTML (can use template variables)
        header_title: Title displayed in header. If None, subject is used.
        logo_url: URL to logo image. If None, no logo is displayed.
        footer_text: Footer text. Defaults to generic message.
        copyright_text: Copyright line. Defaults to current year.
        unsubscribe_url: If provided, adds unsubscribe link.
        primary_color: Primary brand color. Defaults to blue.
        variables: Additional template variables for substitution.

    Returns:
        Complete HTML email string with variables substituted.

    Example:
        >>> content = render_paragraph("Hello {name}!")
        >>> content += render_button("Click Here", "https://example.com")
        >>> html = build_email_html(
        ...     subject="Welcome",
        ...     content_html=content,
        ...     header_title="Welcome!",
        ...     variables={"name": "John"}
        ... )
    """
    from datetime import datetime

    primary = primary_color or DEFAULT_COLORS["primary"]

    # Build logo HTML
    logo_html = ""
    if logo_url:
        logo_html = f"""
        <img src="{logo_url}" alt="Logo" width="120" style="display: block; margin: 0 auto 15px auto; max-width: 120px;">
        """

    # Build header
    header_html = DEFAULT_HEADER.format(
        primary_color=primary,
        logo_html=logo_html,
        header_title=header_title or subject,
    )

    # Build unsubscribe link
    unsubscribe_html = ""
    if unsubscribe_url:
        unsubscribe_html = f"""
        <p style="margin: 15px 0 0 0;">
            <a href="{unsubscribe_url}" style="color: {DEFAULT_COLORS['text_muted']}; font-size: 12px; text-decoration: underline;">
                Unsubscribe
            </a>
        </p>
        """

    # Build footer
    footer_html = DEFAULT_FOOTER.format(
        footer_text=footer_text or "This is an automated message.",
        copyright_text=copyright_text
        or f"&copy; {datetime.now().year} All rights reserved.",
        text_muted_color=DEFAULT_COLORS["text_muted"],
        unsubscribe_html=unsubscribe_html,
    )

    # Build complete email
    html = BASE_EMAIL_TEMPLATE.format(
        subject=subject,
        background_color=DEFAULT_COLORS["background"],
        surface_color=DEFAULT_COLORS["surface"],
        header_html=header_html,
        content_html=content_html,
        footer_html=footer_html,
    )

    # Apply variable substitution if provided
    if variables:
        html = _render_variables(html, variables)

    return html


def build_simple_email(
    subject: str,
    greeting: str,
    body_paragraphs: list,
    button_text: Optional[str] = None,
    button_url: Optional[str] = None,
    closing: str = "Best regards,",
    signature: str = "The Team",
    alert_message: Optional[str] = None,
    alert_type: str = "info",
    variables: Optional[dict[str, Any]] = None,
    **kwargs,
) -> str:
    """
    Build a simple email with common structure.

    This is a convenience function for common email patterns with
    greeting, body, optional button, and signature.

    Args:
        subject: Email subject
        greeting: Opening greeting (e.g., "Hello John,")
        body_paragraphs: List of paragraph strings
        button_text: Optional call-to-action button text
        button_url: URL for the button
        closing: Closing text before signature
        signature: Signature name
        alert_message: Optional alert/notice to display
        alert_type: Alert type ("info", "success", "warning", "error")
        variables: Template variables for substitution
        **kwargs: Additional arguments passed to build_email_html

    Returns:
        Complete HTML email string.

    Example:
        >>> html = build_simple_email(
        ...     subject="Password Reset",
        ...     greeting="Hello {name},",
        ...     body_paragraphs=[
        ...         "You requested to reset your password.",
        ...         "Click the button below to proceed."
        ...     ],
        ...     button_text="Reset Password",
        ...     button_url="https://example.com/reset",
        ...     variables={"name": "John"}
        ... )
    """
    content_parts = []

    # Greeting
    content_parts.append(render_paragraph(greeting))

    # Alert if provided
    if alert_message:
        content_parts.append(render_alert(alert_message, alert_type))

    # Body paragraphs
    for para in body_paragraphs:
        content_parts.append(render_paragraph(para))

    # Button
    if button_text and button_url:
        content_parts.append(render_button(button_text, button_url))

    # Signature
    content_parts.append(render_divider())
    content_parts.append(
        f"""
        <p style="margin: 0; color: {DEFAULT_COLORS['text']}; font-size: 16px; line-height: 1.6;">
            {closing}<br>
            <strong>{signature}</strong>
        </p>
        """
    )

    content_html = "".join(content_parts)

    return build_email_html(
        subject=subject,
        content_html=content_html,
        variables=variables,
        **kwargs,
    )


def build_otp_email(
    otp_code: str,
    expires_minutes: int = 10,
    recipient_name: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Build an OTP verification email.

    Args:
        otp_code: The OTP code to display
        expires_minutes: Expiration time in minutes
        recipient_name: Optional recipient name for greeting
        **kwargs: Additional arguments passed to build_email_html

    Returns:
        Complete HTML email string.
    """
    greeting = f"Hello{' ' + recipient_name if recipient_name else ''},"

    content_parts = [
        render_paragraph(greeting),
        render_paragraph("Your verification code is:"),
        render_code_block(otp_code),
        render_alert(
            f"This code will expire in {expires_minutes} minutes.",
            alert_type="warning",
        ),
        render_paragraph(
            "If you did not request this code, please ignore this email or contact support if you have concerns.",
            muted=True,
        ),
    ]

    return build_email_html(
        subject="Your Verification Code",
        content_html="".join(content_parts),
        header_title="Verification Code",
        **kwargs,
    )


def build_password_reset_email(
    reset_url: str,
    expires_hours: int = 1,
    recipient_name: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Build a password reset email.

    Args:
        reset_url: Password reset URL
        expires_hours: Link expiration time in hours
        recipient_name: Optional recipient name for greeting
        **kwargs: Additional arguments passed to build_email_html

    Returns:
        Complete HTML email string.
    """
    greeting = f"Hello{' ' + recipient_name if recipient_name else ''},"

    content_parts = [
        render_paragraph(greeting),
        render_paragraph(
            "We received a request to reset the password for your account."
        ),
        render_paragraph("Click the button below to set a new password:"),
        render_button("Reset Password", reset_url),
        render_alert(
            f"This link will expire in {expires_hours} hour{'s' if expires_hours != 1 else ''}.",
            alert_type="info",
        ),
        render_paragraph(
            "If you did not request a password reset, you can safely ignore this email. Your password will not be changed.",
            muted=True,
        ),
    ]

    return build_email_html(
        subject="Password Reset Request",
        content_html="".join(content_parts),
        header_title="Reset Your Password",
        **kwargs,
    )


def build_welcome_email(
    user_name: str,
    organization_name: str,
    login_url: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Build a welcome email for new users.

    Args:
        user_name: User's name
        organization_name: Organization name
        login_url: Optional login URL
        **kwargs: Additional arguments passed to build_email_html

    Returns:
        Complete HTML email string.
    """
    content_parts = [
        render_paragraph(f"Hello {user_name},"),
        render_paragraph(
            f"Welcome to <strong>{organization_name}</strong>! Your account has been created successfully."
        ),
        render_paragraph("You can now log in and start using the platform."),
    ]

    if login_url:
        content_parts.append(render_button("Log In", login_url))

    content_parts.extend(
        [
            render_divider(),
            render_paragraph(
                "If you have any questions, please don't hesitate to contact support."
            ),
            render_paragraph(
                f"Best regards,<br><strong>The {organization_name} Team</strong>"
            ),
        ]
    )

    return build_email_html(
        subject=f"Welcome to {organization_name}",
        content_html="".join(content_parts),
        header_title=f"Welcome to {organization_name}!",
        **kwargs,
    )


def build_invitation_email(
    organization_name: str,
    registration_url: str,
    invited_by_name: str,
    expires_days: int = 7,
    **kwargs,
) -> str:
    """
    Build an invitation email sent to a prospective user.

    Args:
        organization_name: Display name of the organization
        registration_url: Pre-filled registration URL with invite token
        invited_by_name: Name of the admin who sent the invite
        expires_days: Number of days before the invitation expires

    Returns:
        HTML email string
    """
    subject = f"You've been invited to join {organization_name}"

    content_parts = [
        render_paragraph("Hello,"),
        render_paragraph(
            f"<strong>{invited_by_name}</strong> has invited you to join "
            f"<strong>{organization_name}</strong>."
        ),
        render_paragraph(
            "Click the button below to complete your registration. "
            f"This invitation will expire in {expires_days} days."
        ),
        render_button("Accept Invitation", registration_url),
        render_divider(),
        render_paragraph(
            "If you were not expecting this invitation, you can safely ignore this email."
        ),
        render_paragraph(
            f"Best regards,<br><strong>The {organization_name} Team</strong>"
        ),
    ]

    return build_email_html(
        subject=subject,
        content_html="".join(content_parts),
        header_title=f"You're Invited to {organization_name}",
        **kwargs,
    )
