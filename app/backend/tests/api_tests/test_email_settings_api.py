"""API tests for the org email settings sender-lock policy.

When an org is on platform defaults (provider IS NULL), the platform owns
the sender identity (SendGrid in particular requires verified senders).
The PUT endpoint must reject any update that would set sender_email,
sender_name, or reply_to_email while the resulting provider is NULL.
"""

from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_branding_rejected_when_on_platform_defaults(admin_client: AsyncClient):
    """Setting sender_email while provider is NULL must return 422."""
    response = await admin_client.put(
        "/api/v1/email-settings",
        json={"sender_email": "noreply@example.com"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["detail_code"] == "email_settings.sender_locked_on_platform_defaults"


@pytest.mark.asyncio
async def test_all_three_branding_fields_are_locked(admin_client: AsyncClient):
    """sender_name and reply_to_email are equally locked, not just sender_email."""
    for field in ("sender_name", "reply_to_email"):
        value = "Test Name" if field == "sender_name" else "reply@example.com"
        response = await admin_client.put(
            "/api/v1/email-settings",
            json={field: value},
        )
        assert response.status_code == 422, f"{field} should be locked"
        assert (
            response.json()["detail_code"]
            == "email_settings.sender_locked_on_platform_defaults"
        )


@pytest.mark.asyncio
async def test_branding_allowed_when_transitioning_off_platform_defaults(
    admin_client: AsyncClient,
):
    """Setting provider AND branding in one request must succeed — the
    resulting provider is no longer NULL, so the lock doesn't apply."""
    response = await admin_client.put(
        "/api/v1/email-settings",
        json={
            "provider": "smtp",
            "smtp_host": "smtp.example.com",
            "sender_email": "noreply@example.com",
            "sender_name": "Example Org",
        },
    )
    assert response.status_code == 200
    assert response.json()["sender_email"] == "noreply@example.com"


@pytest.mark.asyncio
async def test_explicit_null_branding_on_defaults_is_allowed(admin_client: AsyncClient):
    """Sending sender_email=null on a defaults-org is a no-op clear, not an
    override attempt — should not trigger the lock."""
    response = await admin_client.put(
        "/api/v1/email-settings",
        json={"sender_email": None, "sender_name": None, "reply_to_email": None},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_branding_allowed_with_existing_provider(admin_client: AsyncClient):
    """Once a provider is set, branding updates work normally — the lock
    only applies while the resulting provider is NULL."""
    # First set a provider.
    setup = await admin_client.put(
        "/api/v1/email-settings",
        json={"provider": "sendgrid", "sendgrid_api_key": "SG.test"},
    )
    assert setup.status_code == 200

    # Now updating branding alone should succeed (provider stays sendgrid).
    response = await admin_client.put(
        "/api/v1/email-settings",
        json={"sender_email": "noreply@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["sender_email"] == "noreply@example.com"
