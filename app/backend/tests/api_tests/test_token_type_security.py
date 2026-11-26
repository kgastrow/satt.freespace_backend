"""
Security tests for JWT token-type enforcement.

Regression tests for the JWT type-confusion vulnerability where a pre-2FA
interstitial token (purpose "2fa_verification") or a legacy token lacking a
"type" claim could authenticate a protected endpoint, bypassing 2FA.

get_current_user (src/api/deps.py) must only accept tokens whose "type" claim
is "access" (normal login) or "impersonation" (super-admin impersonation).
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from src.core.config import settings
from src.core.security import create_access_token


# A protected endpoint that depends on get_current_user.
PROTECTED_ENDPOINT = "/api/v1/user/me"


def _encode(payload: dict) -> str:
    """Encode a JWT the same way the app does."""
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


@pytest.mark.asyncio
async def test_2fa_interstitial_token_is_rejected(
    client, test_user, test_organization
):
    """A pre-2FA interstitial token must NOT authenticate a protected endpoint."""
    two_factor_token = _encode(
        {
            "user_id": str(test_user.id),
            "organization_id": str(test_organization.id),
            "purpose": "2fa_verification",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        }
    )

    response = await client.get(
        PROTECTED_ENDPOINT,
        headers={"Authorization": f"Bearer {two_factor_token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_token_missing_type_claim_is_rejected(
    client, test_user, test_organization
):
    """A token lacking the 'type' claim (e.g. legacy) must be rejected."""
    legacy_token = _encode(
        {
            "user_id": str(test_user.id),
            "organization_id": str(test_organization.id),
            "exp": datetime.now(timezone.utc)
            + timedelta(seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS),
        }
    )

    response = await client.get(
        PROTECTED_ENDPOINT,
        headers={"Authorization": f"Bearer {legacy_token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_type_is_rejected(client, test_user, test_organization):
    """A refresh-type token must not authenticate a protected endpoint."""
    refresh_typed_token = _encode(
        {
            "user_id": str(test_user.id),
            "organization_id": str(test_organization.id),
            "type": "refresh",
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
        }
    )

    response = await client.get(
        PROTECTED_ENDPOINT,
        headers={"Authorization": f"Bearer {refresh_typed_token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_real_access_token_still_works(client, test_user, test_organization):
    """A genuine access token (type='access') must still authenticate."""
    access_token = create_access_token(
        user_id=str(test_user.id),
        organization_id=str(test_organization.id),
    )

    response = await client.get(
        PROTECTED_ENDPOINT,
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.email
