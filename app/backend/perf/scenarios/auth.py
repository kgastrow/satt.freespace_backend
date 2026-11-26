"""Authentication scenario: login, refresh token, logout."""

from locust import task, tag

from perf.config import (
    TEST_TENANT_ADMIN_EMAIL,
    TEST_TENANT_ADMIN_PASSWORD,
    TEST_ORG_SLUG,
)


class AuthScenario:
    """Authentication flow tasks. Weight: 30."""

    @task(5)
    @tag("auth")
    def login(self):
        """Login with email and password."""
        self.client.post(
            "/api/v1/auth/login",
            json={
                "email": TEST_TENANT_ADMIN_EMAIL,
                "password": TEST_TENANT_ADMIN_PASSWORD,
                "organization_slug": TEST_ORG_SLUG,
            },
            name="/api/v1/auth/login",
        )

    @task(3)
    @tag("auth")
    def refresh_token(self):
        """Refresh the access token using the stored refresh token."""
        refresh_token = self.auth_headers.get("_refresh_token", "")
        if not refresh_token:
            return
        self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
            name="/api/v1/auth/refresh",
        )

    @task(1)
    @tag("auth")
    def check_email(self):
        """Check email authentication methods."""
        self.client.post(
            "/api/v1/auth/check-email",
            json={
                "email": TEST_TENANT_ADMIN_EMAIL,
                "organization_slug": TEST_ORG_SLUG,
            },
            name="/api/v1/auth/check-email",
        )
