"""Auth helpers and tenant setup utilities for performance tests."""

from perf.config import (
    TEST_TENANT_ADMIN_EMAIL,
    TEST_TENANT_ADMIN_PASSWORD,
    TEST_ORG_SLUG,
)


def login(client) -> dict:
    """Authenticate and return headers with Bearer token."""
    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": TEST_TENANT_ADMIN_EMAIL,
            "password": TEST_TENANT_ADMIN_PASSWORD,
            "organization_slug": TEST_ORG_SLUG,
        },
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Login failed with status {resp.status_code}: {resp.text}"
        )
    data = resp.json()
    token = data["access_token"]
    return {
        "Authorization": f"Bearer {token}",
        "_refresh_token": data.get("refresh_token", ""),
    }
