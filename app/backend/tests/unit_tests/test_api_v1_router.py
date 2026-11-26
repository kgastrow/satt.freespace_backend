"""
Unit tests for API v1 router structure.

Tests that the v1_router includes all expected sub-routers and
that the API versioning structure is properly configured.
"""

from fastapi import APIRouter
import pytest


class TestV1RouterStructure:
    """Test the v1 router includes all expected sub-routers."""

    def test_v1_router_exists(self):
        """Test that v1_router can be imported."""
        from src.api.v1 import v1_router

        assert v1_router is not None
        assert isinstance(v1_router, APIRouter)

    def test_v1_router_includes_all_subrouters(self):
        """Test that v1_router includes all expected sub-routers."""
        from src.api.v1 import v1_router

        # Expected router prefixes based on src/api/v1/__init__.py
        expected_prefixes = {
            "/auth",
            "/user",
            "/users",
            "/organizations",
            "/roles",
            "/user-roles",
            "/user-otp",
            "/audit-logs",
            "/metrics",
            "/files",
            "/admin",
            "/notifications",
            "/sso",
            "/organization-sso-settings",
        }

        # Extract prefixes from included routes
        included_prefixes = set()
        for route in v1_router.routes:
            if hasattr(route, "path"):
                # Extract the first path segment as the prefix
                path_parts = route.path.strip("/").split("/")
                if path_parts[0]:
                    prefix = f"/{path_parts[0]}"
                    included_prefixes.add(prefix)

        # Verify all expected prefixes are present
        missing_prefixes = expected_prefixes - included_prefixes
        assert (
            len(missing_prefixes) == 0
        ), f"Missing router prefixes: {missing_prefixes}"

    def test_v1_router_has_routes(self):
        """Test that v1_router has routes defined."""
        from src.api.v1 import v1_router

        assert len(v1_router.routes) > 0, "v1_router should have at least one route"


class TestV1RouterEndpointAvailability:
    """Test that key endpoints are available under the v1 router."""

    @pytest.mark.asyncio
    async def test_auth_login_endpoint_available(self, client):
        """Test that auth login endpoint is accessible under /api/v1."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "password",
                "organization_slug": "test-org",
            },
        )
        # We don't care about success (401 is expected), just that the endpoint exists
        # 404 would indicate the route is not found
        assert response.status_code != 404, "Auth login endpoint should be available"

    @pytest.mark.asyncio
    async def test_health_endpoint_not_versioned(self, client):
        """Test that health endpoint remains at root level (not versioned)."""
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_docs_endpoint_accessible(self, client):
        """Test that API documentation is accessible."""
        response = await client.get("/docs")
        # 401 is expected if docs require auth, 404 would mean route doesn't exist
        assert response.status_code != 404, "API docs endpoint should exist"

    @pytest.mark.asyncio
    async def test_user_endpoint_available(self, client):
        """Test that user endpoint is accessible under /api/v1."""
        # Should return 401 (unauthenticated), not 404
        response = await client.get("/api/v1/user/me")
        assert response.status_code != 404, "User me endpoint should be available"

    @pytest.mark.asyncio
    async def test_organizations_endpoint_available(self, client, test_jwt_token):
        """Test that organizations endpoint is accessible under /api/v1."""
        response = await client.get(
            "/api/v1/organizations",
            headers={"Authorization": test_jwt_token},
        )
        # Should return 200 or another valid status, not 404
        assert response.status_code != 404, "Organizations endpoint should be available"

    @pytest.mark.asyncio
    async def test_files_endpoint_available(self, client, test_jwt_token):
        """Test that files endpoint is accessible under /api/v1."""
        response = await client.get(
            "/api/v1/files",
            headers={"Authorization": test_jwt_token},
        )
        # Should return 200 or another valid status, not 404
        assert response.status_code != 404, "Files endpoint should be available"


class TestV1RouterConfiguration:
    """Test the configuration and integration of v1 router."""

    def test_v1_router_exports(self):
        """Test that v1 module exports v1_router in __all__."""
        from src.api import v1

        assert hasattr(v1, "__all__")
        assert "v1_router" in v1.__all__

    def test_all_subrouters_imported(self):
        """Test that all sub-routers are imported in v1 module."""
        import inspect

        from src.api import v1

        source = inspect.getsource(v1)

        # Verify all expected routers are imported
        expected_imports = [
            "auth",
            "user",
            "users",
            "organization",
            "role",
            "user_role",
            "user_otp",
            "audit_log",
            "metrics",
            "file",
            "admin",
            "notification",
            "sso",
            "organization_sso_settings",
        ]

        for router_name in expected_imports:
            assert router_name in source, f"Router '{router_name}' should be imported"

    def test_v1_router_included_in_main_app(self):
        """Test that v1_router is included in main.py with correct prefix."""
        from main import app

        # Verify routes are registered under /api/v1
        has_v1_routes = any(route.path.startswith("/api/v1/") for route in app.routes)

        assert has_v1_routes, "Main app should have routes under /api/v1 prefix"
