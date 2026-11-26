"""
Unit tests for email templates.
"""

from src.services.email_templates import (
    DEFAULT_COLORS,
    build_email_html,
    build_otp_email,
    build_password_reset_email,
    build_simple_email,
    build_welcome_email,
    render_alert,
    render_button,
    render_code_block,
    render_divider,
    render_heading,
    render_list,
    render_paragraph,
)


class TestRenderHelpers:
    """Tests for HTML render helper functions."""

    def test_render_button(self):
        """Test button rendering."""
        html = render_button("Click Me", "https://example.com")
        assert "Click Me" in html
        assert 'href="https://example.com"' in html
        assert DEFAULT_COLORS["primary"] in html

    def test_render_button_custom_color(self):
        """Test button with custom colors."""
        html = render_button(
            "Submit", "https://test.com", color="#ff0000", text_color="#000000"
        )
        assert "#ff0000" in html
        assert "#000000" in html
        assert "Submit" in html

    def test_render_alert_info(self):
        """Test info alert rendering."""
        html = render_alert("This is a message", "info")
        assert "This is a message" in html
        assert "#eff6ff" in html  # info background
        assert "#2563eb" in html  # info border

    def test_render_alert_success(self):
        """Test success alert rendering."""
        html = render_alert("Success!", "success")
        assert "Success!" in html
        assert "#f0fdf4" in html  # success background

    def test_render_alert_warning(self):
        """Test warning alert rendering."""
        html = render_alert("Warning!", "warning")
        assert "Warning!" in html
        assert "#fffbeb" in html  # warning background

    def test_render_alert_error(self):
        """Test error alert rendering."""
        html = render_alert("Error occurred", "error")
        assert "Error occurred" in html
        assert "#fef2f2" in html  # error background

    def test_render_code_block(self):
        """Test code block rendering."""
        html = render_code_block("123456")
        assert "123456" in html
        assert "letter-spacing" in html
        assert "Courier New" in html

    def test_render_code_block_custom_size(self):
        """Test code block with custom font size."""
        html = render_code_block("ABC123", font_size="32px")
        assert "32px" in html

    def test_render_divider(self):
        """Test divider rendering."""
        html = render_divider()
        assert "border-top" in html
        assert "#e2e8f0" in html

    def test_render_paragraph(self):
        """Test paragraph rendering."""
        html = render_paragraph("Hello world")
        assert "Hello world" in html
        assert DEFAULT_COLORS["text"] in html

    def test_render_paragraph_muted(self):
        """Test muted paragraph rendering."""
        html = render_paragraph("Faded text", muted=True)
        assert "Faded text" in html
        assert DEFAULT_COLORS["text_muted"] in html

    def test_render_heading_h1(self):
        """Test h1 rendering."""
        html = render_heading("Main Title", level=1)
        assert "<h1" in html
        assert "Main Title" in html
        assert "28px" in html

    def test_render_heading_h2(self):
        """Test h2 rendering."""
        html = render_heading("Section", level=2)
        assert "<h2" in html
        assert "Section" in html
        assert "22px" in html

    def test_render_heading_h3(self):
        """Test h3 rendering."""
        html = render_heading("Subsection", level=3)
        assert "<h3" in html
        assert "Subsection" in html
        assert "18px" in html

    def test_render_list_unordered(self):
        """Test unordered list rendering."""
        html = render_list(["Item 1", "Item 2", "Item 3"])
        assert "<ul" in html
        assert "<li" in html
        assert "Item 1" in html
        assert "Item 2" in html
        assert "Item 3" in html

    def test_render_list_ordered(self):
        """Test ordered list rendering."""
        html = render_list(["First", "Second", "Third"], ordered=True)
        assert "<ol" in html
        assert "<li" in html
        assert "First" in html


class TestBuildEmailHtml:
    """Tests for build_email_html function."""

    def test_build_email_html_minimal(self):
        """Test building email with minimal parameters."""
        html = build_email_html(
            subject="Test Subject",
            content_html="<p>Hello World</p>",
        )
        assert "<!DOCTYPE html>" in html
        assert "<title>Test Subject</title>" in html
        assert "Hello World" in html
        assert "This is an automated message" in html

    def test_build_email_html_with_header_title(self):
        """Test building email with custom header title."""
        html = build_email_html(
            subject="Test",
            content_html="<p>Content</p>",
            header_title="Custom Header",
        )
        assert "Custom Header" in html

    def test_build_email_html_with_logo(self):
        """Test building email with logo."""
        html = build_email_html(
            subject="Test",
            content_html="<p>Content</p>",
            logo_url="https://example.com/logo.png",
        )
        assert 'src="https://example.com/logo.png"' in html
        assert 'alt="Logo"' in html

    def test_build_email_html_with_footer(self):
        """Test building email with custom footer."""
        html = build_email_html(
            subject="Test",
            content_html="<p>Content</p>",
            footer_text="Custom Footer Text",
            copyright_text="Custom Copyright",
        )
        assert "Custom Footer Text" in html
        assert "Custom Copyright" in html

    def test_build_email_html_with_unsubscribe(self):
        """Test building email with unsubscribe link."""
        html = build_email_html(
            subject="Test",
            content_html="<p>Content</p>",
            unsubscribe_url="https://example.com/unsubscribe",
        )
        assert 'href="https://example.com/unsubscribe"' in html
        assert "Unsubscribe" in html

    def test_build_email_html_with_custom_color(self):
        """Test building email with custom primary color."""
        html = build_email_html(
            subject="Test",
            content_html="<p>Content</p>",
            primary_color="#ff5500",
        )
        assert "#ff5500" in html

    def test_build_email_html_with_variables(self):
        """Test building email with variable substitution."""
        html = build_email_html(
            subject="Test",
            content_html="<p>Hello {name}!</p>",
            variables={"name": "John"},
        )
        assert "Hello John!" in html
        assert "{name}" not in html


class TestBuildSimpleEmail:
    """Tests for build_simple_email function."""

    def test_build_simple_email_minimal(self):
        """Test building simple email with minimal parameters."""
        html = build_simple_email(
            subject="Test",
            greeting="Hello,",
            body_paragraphs=["This is a test."],
        )
        assert "Hello," in html
        assert "This is a test." in html
        assert "Best regards," in html
        assert "The Team" in html

    def test_build_simple_email_with_button(self):
        """Test building simple email with button."""
        html = build_simple_email(
            subject="Test",
            greeting="Hi,",
            body_paragraphs=["Click below."],
            button_text="Click Here",
            button_url="https://example.com",
        )
        assert "Click Here" in html
        assert 'href="https://example.com"' in html

    def test_build_simple_email_with_alert(self):
        """Test building simple email with alert."""
        html = build_simple_email(
            subject="Test",
            greeting="Hi,",
            body_paragraphs=["Content"],
            alert_message="Important notice!",
            alert_type="warning",
        )
        assert "Important notice!" in html

    def test_build_simple_email_custom_signature(self):
        """Test building simple email with custom signature."""
        html = build_simple_email(
            subject="Test",
            greeting="Hi,",
            body_paragraphs=["Content"],
            closing="Cheers,",
            signature="Acme Team",
        )
        assert "Cheers," in html
        assert "Acme Team" in html

    def test_build_simple_email_with_variables(self):
        """Test building simple email with variables."""
        html = build_simple_email(
            subject="Test",
            greeting="Hello {name},",
            body_paragraphs=["Your order {order_id} is ready."],
            variables={"name": "Alice", "order_id": "12345"},
        )
        assert "Hello Alice," in html
        assert "Your order 12345 is ready." in html


class TestBuildOtpEmail:
    """Tests for build_otp_email function."""

    def test_build_otp_email_basic(self):
        """Test building OTP email."""
        html = build_otp_email(otp_code="123456")
        assert "123456" in html
        assert "Verification Code" in html
        assert "10 minutes" in html

    def test_build_otp_email_custom_expiry(self):
        """Test building OTP email with custom expiry."""
        html = build_otp_email(otp_code="ABCD12", expires_minutes=5)
        assert "ABCD12" in html
        assert "5 minutes" in html

    def test_build_otp_email_with_name(self):
        """Test building OTP email with recipient name."""
        html = build_otp_email(otp_code="999999", recipient_name="Bob")
        assert "Hello Bob," in html


class TestBuildPasswordResetEmail:
    """Tests for build_password_reset_email function."""

    def test_build_password_reset_email_basic(self):
        """Test building password reset email."""
        html = build_password_reset_email(reset_url="https://example.com/reset/abc123")
        assert "Reset Password" in html
        assert 'href="https://example.com/reset/abc123"' in html
        assert "1 hour" in html

    def test_build_password_reset_email_custom_expiry(self):
        """Test building password reset email with custom expiry."""
        html = build_password_reset_email(
            reset_url="https://example.com/reset",
            expires_hours=2,
        )
        assert "2 hours" in html

    def test_build_password_reset_email_with_name(self):
        """Test building password reset email with recipient name."""
        html = build_password_reset_email(
            reset_url="https://example.com/reset",
            recipient_name="Charlie",
        )
        assert "Hello Charlie," in html


class TestBuildWelcomeEmail:
    """Tests for build_welcome_email function."""

    def test_build_welcome_email_basic(self):
        """Test building welcome email."""
        html = build_welcome_email(
            user_name="Alice",
            organization_name="Acme Corp",
        )
        assert "Hello Alice," in html
        assert "Acme Corp" in html
        assert "Welcome" in html

    def test_build_welcome_email_with_login_url(self):
        """Test building welcome email with login URL."""
        html = build_welcome_email(
            user_name="Bob",
            organization_name="Test Inc",
            login_url="https://example.com/login",
        )
        assert "Log In" in html
        assert 'href="https://example.com/login"' in html


class TestEmailResponsiveness:
    """Tests for email template responsiveness and compatibility."""

    def test_email_has_viewport_meta(self):
        """Test that email includes viewport meta tag."""
        html = build_email_html(subject="Test", content_html="<p>Content</p>")
        assert 'name="viewport"' in html
        assert "width=device-width" in html

    def test_email_has_mso_conditional(self):
        """Test that email includes MSO conditional for Outlook."""
        html = build_email_html(subject="Test", content_html="<p>Content</p>")
        assert "<!--[if mso]>" in html

    def test_email_has_responsive_styles(self):
        """Test that email includes responsive media queries."""
        html = build_email_html(subject="Test", content_html="<p>Content</p>")
        assert "@media screen and (max-width: 600px)" in html

    def test_email_uses_table_layout(self):
        """Test that email uses table-based layout for compatibility."""
        html = build_email_html(subject="Test", content_html="<p>Content</p>")
        assert 'role="presentation"' in html
        assert "cellpadding" in html
        assert "cellspacing" in html

    def test_email_has_inline_styles(self):
        """Test that email uses inline styles for compatibility."""
        html = build_email_html(subject="Test", content_html="<p>Content</p>")
        # Check that key elements have inline styles
        assert 'style="' in html
        # Background colors should be inline
        assert "background-color:" in html
