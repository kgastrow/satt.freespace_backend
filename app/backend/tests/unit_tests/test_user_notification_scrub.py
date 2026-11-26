"""In-app notification rows are scrubbed at the CRUD chokepoint.

`in_app_provider` scrubs before calling this, but `src/api/feedback.py` writes
rows directly and bypassed it. A redaction control applied per caller is one
new caller away from being absent, so it belongs on the single function every
writer goes through.

These rows are not self-only storage: an impersonation token carries the
TARGET user's id (src/core/security.py::create_impersonation_token), so a super
admin impersonating a user reads that user's inbox through the ordinary
endpoint - and the row outlives any credential in it by weeks.
"""

import pytest

from src.crud.user_notification import create_user_notification


OTP_BODY = "Your verification code is: 483-920\n\nThis code expires in 10 minutes."
RESET = "Reset here: https://app.example.com/reset-password?token=Xj7Qw2mKp9Lr4Ts6Vn1Bd8Fh&org=acme"


@pytest.mark.asyncio
async def test_direct_crud_writer_is_scrubbed(async_session, test_user, test_organization):
    """The path api/feedback.py uses - no provider involved."""
    row = await create_user_notification(
        session=async_session,
        organization_id=str(test_organization.id),
        user_id=str(test_user.id),
        title=f"Security: {OTP_BODY}",
        body=RESET,
    )

    assert "483-920" not in row.title
    assert "Xj7Qw2mKp9Lr4Ts6Vn1Bd8Fh" not in row.body
    # The surrounding text must survive - a scrub that destroys the message
    # makes the inbox useless.
    assert "Reset here" in row.body
    assert "app.example.com" in row.body


@pytest.mark.asyncio
async def test_ordinary_content_is_untouched(async_session, test_user, test_organization):
    """Guard against over-aggressive scrubbing: this is the common case."""
    title = "Export ready"
    body = "42 rows were written to report.csv. Download it from /exports/42 before Friday."

    row = await create_user_notification(
        session=async_session,
        organization_id=str(test_organization.id),
        user_id=str(test_user.id),
        title=title,
        body=body,
    )

    assert row.title == title
    assert row.body == body


@pytest.mark.asyncio
async def test_link_is_deliberately_not_scrubbed(async_session, test_user, test_organization):
    """`link` is the notification's ACTION and this row is the only copy the UI
    can click. Redacting it yields a notification that renders and does nothing.
    Pinned so the decision is explicit rather than an oversight."""
    link = "https://app.example.com/invite?token=Xj7Qw2mKp9Lr4Ts6Vn1Bd8Fh"

    row = await create_user_notification(
        session=async_session,
        organization_id=str(test_organization.id),
        user_id=str(test_user.id),
        title="You were invited",
        link=link,
    )

    assert row.link == link


@pytest.mark.asyncio
async def test_none_body_survives(async_session, test_user, test_organization):
    row = await create_user_notification(
        session=async_session,
        organization_id=str(test_organization.id),
        user_id=str(test_user.id),
        title="Title only",
    )
    assert row.body is None
