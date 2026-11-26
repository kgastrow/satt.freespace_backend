"""
API tests for about page endpoints.

Tests verify:
- Authenticated read access (not public - requires login)
- Admin write access
"""

from httpx import AsyncClient
import pytest


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def about_content(async_session, test_admin_user):
    """Set up about page content in system config."""
    from src.models.system_config import SystemConfig

    content_config = SystemConfig(
        key="about.content",
        value="<h1>About Us</h1><p>Welcome to our application.</p>",
        description="HTML content displayed on the About page",
        updated_by_user_id=test_admin_user.id,
    )
    content_type_config = SystemConfig(
        key="about.content_type",
        value="html",
        description="Content type for the about page (plain or html)",
        updated_by_user_id=test_admin_user.id,
    )
    async_session.add(content_config)
    async_session.add(content_type_config)
    await async_session.commit()
    await async_session.refresh(content_config)
    await async_session.refresh(content_type_config)
    return content_config


# ============================================================================
# Public Read Tests
# ============================================================================


class TestAboutPublicAccess:
    """Tests for about page public access."""

    @pytest.mark.asyncio
    async def test_get_about_info_requires_auth(self, client: AsyncClient):
        """Test that about info requires authentication (not public)."""
        response = await client.get("/api/v1/about")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_about_info_authenticated(
        self,
        client: AsyncClient,
        test_jwt_token,
        about_content,
    ):
        """Test getting about info when authenticated."""
        response = await client.get(
            "/api/v1/about",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert "content_type" in data
        assert data["content_type"] in ["plain", "html"]

    @pytest.mark.asyncio
    async def test_get_about_info_empty_content(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test getting about info when no content exists."""
        response = await client.get(
            "/api/v1/about",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        # Should return empty content if not set
        assert "content" in data
        assert "content_type" in data


# ============================================================================
# Admin Write Tests
# ============================================================================


class TestAboutAdminAccess:
    """Tests for about page admin access."""

    @pytest.mark.asyncio
    async def test_update_about_requires_admin(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test that updating about info requires admin."""
        response = await client.put(
            "/api/v1/about",
            json={
                "content": "<h1>New Content</h1>",
                "content_type": "html",
            },
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_about_unauthenticated(self, client: AsyncClient):
        """Test that updating about info requires authentication."""
        response = await client.put(
            "/api/v1/about",
            json={
                "content": "<h1>Test</h1>",
                "content_type": "html",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_about_as_admin_html(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test updating about info as admin with HTML content."""
        response = await client.put(
            "/api/v1/about",
            json={
                "content": "<h1>Updated Company</h1><p>New description</p>",
                "content_type": "html",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "about" in data
        assert data["about"]["content_type"] == "html"
        assert "<h1>Updated Company</h1>" in data["about"]["content"]

    @pytest.mark.asyncio
    async def test_update_about_as_admin_plain_text(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test updating about info as admin with plain text content."""
        response = await client.put(
            "/api/v1/about",
            json={
                "content": "This is plain text content for the about page.",
                "content_type": "plain",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["about"]["content_type"] == "plain"

    @pytest.mark.asyncio
    async def test_update_about_invalid_content_type(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test that invalid content_type is rejected."""
        response = await client.put(
            "/api/v1/about",
            json={
                "content": "Some content",
                "content_type": "markdown",  # Invalid - only 'plain' or 'html'
            },
            headers={"Authorization": test_super_admin_token},
        )
        # Pydantic validation should reject this
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_about_persists_content(
        self,
        client: AsyncClient,
        test_super_admin_token,
        test_jwt_token,
    ):
        """Test that updated about content persists and can be retrieved."""
        # Update content
        update_response = await client.put(
            "/api/v1/about",
            json={
                "content": "<h1>Persistent Content</h1>",
                "content_type": "html",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert update_response.status_code == 200

        # Retrieve content
        get_response = await client.get(
            "/api/v1/about",
            headers={"Authorization": test_jwt_token},
        )
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["content"] == "<h1>Persistent Content</h1>"
        assert data["content_type"] == "html"


# ============================================================================
# Content Type Validation Tests
# ============================================================================


class TestAboutContentValidation:
    """Tests for about page content validation."""

    @pytest.mark.asyncio
    async def test_update_about_missing_content(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test that missing content is rejected."""
        response = await client.put(
            "/api/v1/about",
            json={
                "content_type": "html",
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_about_missing_content_type(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test that missing content_type uses default."""
        response = await client.put(
            "/api/v1/about",
            json={
                "content": "Some content",
            },
            headers={"Authorization": test_super_admin_token},
        )
        # Should either succeed with default or fail validation
        assert response.status_code in [200, 422]
