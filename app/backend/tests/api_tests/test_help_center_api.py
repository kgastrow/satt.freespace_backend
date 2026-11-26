"""
API tests for help center endpoints.

Tests verify:
- Public article viewing
- Public FAQ viewing
- Admin article management
- Admin FAQ management
- Category management
- Search functionality
"""

from uuid import uuid4

from httpx import AsyncClient
import pytest


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def help_category(async_session):
    """Create a help center category."""
    from src.models.help_center import HelpCategory

    category = HelpCategory(
        name="Getting Started",
        slug="getting-started",
        description="Introduction and setup guides",
        display_order=1,
    )
    async_session.add(category)
    await async_session.commit()
    await async_session.refresh(category)
    return category


@pytest.fixture
async def second_help_category(async_session):
    """Create a second help center category."""
    from src.models.help_center import HelpCategory

    category = HelpCategory(
        name="Advanced Topics",
        slug="advanced-topics",
        description="Advanced features and configurations",
        display_order=2,
    )
    async_session.add(category)
    await async_session.commit()
    await async_session.refresh(category)
    return category


@pytest.fixture
async def help_article(async_session, help_category, test_admin_user):
    """Create a published help center article."""
    from src.models.help_center import HelpArticle

    article = HelpArticle(
        category_id=help_category.id,
        title="How to Get Started",
        slug="how-to-get-started",
        content="This is the article content explaining how to get started...",
        status="published",
        display_order=1,
        created_by_id=test_admin_user.id,
    )
    async_session.add(article)
    await async_session.commit()
    await async_session.refresh(article)
    return article


@pytest.fixture
async def draft_help_article(async_session, help_category, test_admin_user):
    """Create a draft help center article."""
    from src.models.help_center import HelpArticle

    article = HelpArticle(
        category_id=help_category.id,
        title="Draft Article",
        slug="draft-article",
        content="This article is still a draft.",
        status="draft",
        display_order=2,
        created_by_id=test_admin_user.id,
    )
    async_session.add(article)
    await async_session.commit()
    await async_session.refresh(article)
    return article


@pytest.fixture
async def help_faq(async_session, help_category):
    """Create a published FAQ."""
    from src.models.help_center import HelpFaq

    faq = HelpFaq(
        category_id=help_category.id,
        question="What is this application?",
        answer="This is a multi-tenant web application template.",
        status="published",
        display_order=1,
    )
    async_session.add(faq)
    await async_session.commit()
    await async_session.refresh(faq)
    return faq


@pytest.fixture
async def draft_help_faq(async_session, help_category):
    """Create a draft FAQ."""
    from src.models.help_center import HelpFaq

    faq = HelpFaq(
        category_id=help_category.id,
        question="Draft FAQ Question?",
        answer="This FAQ is still a draft.",
        status="draft",
        display_order=2,
    )
    async_session.add(faq)
    await async_session.commit()
    await async_session.refresh(faq)
    return faq


# ============================================================================
# Public Category Tests
# ============================================================================


class TestHelpCategoriesPublic:
    """Tests for public help category endpoints."""

    @pytest.mark.asyncio
    async def test_list_help_categories_public(
        self,
        client: AsyncClient,
        help_category,
    ):
        """Test that help categories are publicly accessible."""
        response = await client.get("/api/v1/help/categories")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_help_categories_pagination(
        self,
        client: AsyncClient,
        help_category,
        second_help_category,
    ):
        """Test pagination for help categories."""
        response = await client.get("/api/v1/help/categories?limit=1&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 1
        assert data["offset"] == 0
        assert len(data["items"]) <= 1


# ============================================================================
# Public Article Tests
# ============================================================================


class TestHelpArticlesPublic:
    """Tests for public help article endpoints."""

    @pytest.mark.asyncio
    async def test_list_help_articles_public(
        self,
        client: AsyncClient,
        help_article,
    ):
        """Test that help articles are publicly accessible."""
        response = await client.get("/api/v1/help/articles")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_help_articles_filter_by_category(
        self,
        client: AsyncClient,
        help_article,
        help_category,
    ):
        """Test filtering help articles by category."""
        response = await client.get(
            f"/api/v1/help/articles?category_id={help_category.id}"
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["category_id"] == str(help_category.id)

    @pytest.mark.asyncio
    async def test_list_help_articles_invalid_category_id(
        self,
        client: AsyncClient,
    ):
        """Test that invalid category_id returns 400."""
        response = await client.get("/api/v1/help/articles?category_id=invalid-uuid")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_article_by_slug(
        self,
        client: AsyncClient,
        help_article,
    ):
        """Test getting an article by slug."""
        response = await client.get(f"/api/v1/help/articles/{help_article.slug}")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == help_article.title
        assert data["slug"] == help_article.slug

    @pytest.mark.asyncio
    async def test_get_article_not_found(self, client: AsyncClient):
        """Test getting non-existent article returns 404."""
        response = await client.get("/api/v1/help/articles/non-existent-slug")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_draft_articles_not_visible_publicly(
        self,
        client: AsyncClient,
        draft_help_article,
    ):
        """Test that draft articles are not visible publicly."""
        response = await client.get(f"/api/v1/help/articles/{draft_help_article.slug}")
        assert response.status_code == 404


# ============================================================================
# Public FAQ Tests
# ============================================================================


class TestHelpFaqsPublic:
    """Tests for public FAQ endpoints."""

    @pytest.mark.asyncio
    async def test_list_help_faqs_public(
        self,
        client: AsyncClient,
        help_faq,
    ):
        """Test that FAQs are publicly accessible."""
        response = await client.get("/api/v1/help/faqs")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_help_faqs_filter_by_category(
        self,
        client: AsyncClient,
        help_faq,
        help_category,
    ):
        """Test filtering FAQs by category."""
        response = await client.get(f"/api/v1/help/faqs?category_id={help_category.id}")
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["category_id"] == str(help_category.id)

    @pytest.mark.asyncio
    async def test_draft_faqs_not_visible_publicly(
        self,
        client: AsyncClient,
        draft_help_faq,
        help_faq,
    ):
        """Test that draft FAQs are not visible publicly."""
        response = await client.get("/api/v1/help/faqs")
        assert response.status_code == 200
        data = response.json()
        faq_ids = [item["id"] for item in data["items"]]
        assert str(draft_help_faq.id) not in faq_ids


# ============================================================================
# Public Search Tests
# ============================================================================


class TestHelpSearch:
    """Tests for help search endpoint."""

    @pytest.mark.asyncio
    async def test_search_help_articles(
        self,
        client: AsyncClient,
        help_article,
    ):
        """Test searching help articles."""
        response = await client.get("/api/v1/help/search?q=started")
        assert response.status_code == 200
        data = response.json()
        assert "articles" in data
        assert "faqs" in data
        assert "total_results" in data

    @pytest.mark.asyncio
    async def test_search_help_faqs(
        self,
        client: AsyncClient,
        help_faq,
    ):
        """Test searching FAQs."""
        response = await client.get("/api/v1/help/search?q=application")
        assert response.status_code == 200
        data = response.json()
        assert "articles" in data
        assert "faqs" in data

    @pytest.mark.asyncio
    async def test_search_empty_query_rejected(
        self,
        client: AsyncClient,
    ):
        """Test that empty search query is rejected."""
        response = await client.get("/api/v1/help/search?q=")
        assert response.status_code == 422  # Validation error


# ============================================================================
# Admin Category Tests
# ============================================================================


class TestAdminCategories:
    """Tests for admin category endpoints."""

    @pytest.mark.asyncio
    async def test_create_category_requires_admin(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test that creating categories requires admin."""
        response = await client.post(
            "/api/v1/help/admin/categories",
            json={
                "name": "New Category",
                "slug": "new-category",
            },
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_category_unauthenticated(
        self,
        client: AsyncClient,
    ):
        """Test that creating categories requires authentication."""
        response = await client.post(
            "/api/v1/help/admin/categories",
            json={
                "name": "New Category",
                "slug": "new-category",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_category_as_admin(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test creating a category as admin."""
        unique_slug = f"new-category-{uuid4().hex[:8]}"
        response = await client.post(
            "/api/v1/help/admin/categories",
            json={
                "name": "New Category",
                "slug": unique_slug,
                "description": "A new category",
                "display_order": 10,
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Category"
        assert data["slug"] == unique_slug

    @pytest.mark.asyncio
    async def test_update_category(
        self,
        client: AsyncClient,
        test_super_admin_token,
        help_category,
    ):
        """Test updating a category."""
        response = await client.put(
            f"/api/v1/help/admin/categories/{help_category.id}",
            json={"name": "Updated Category Name"},
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Category Name"

    @pytest.mark.asyncio
    async def test_update_category_not_found(
        self,
        client: AsyncClient,
        test_super_admin_token,
    ):
        """Test updating a non-existent category returns 404."""
        response = await client.put(
            f"/api/v1/help/admin/categories/{uuid4()}",
            json={"name": "Updated Category Name"},
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_category(
        self,
        client: AsyncClient,
        test_super_admin_token,
        second_help_category,
    ):
        """Test deleting a category."""
        response = await client.delete(
            f"/api/v1/help/admin/categories/{second_help_category.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_reorder_categories(
        self,
        client: AsyncClient,
        test_super_admin_token,
        help_category,
        second_help_category,
    ):
        """Test reordering categories."""
        response = await client.put(
            "/api/v1/help/admin/categories/reorder",
            json={
                "items": [
                    {"id": str(help_category.id), "display_order": 2},
                    {"id": str(second_help_category.id), "display_order": 1},
                ]
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["updated_count"] == 2


# ============================================================================
# Admin Article Tests
# ============================================================================


class TestAdminArticles:
    """Tests for admin article endpoints."""

    @pytest.mark.asyncio
    async def test_create_article_requires_admin(
        self,
        client: AsyncClient,
        test_jwt_token,
        help_category,
    ):
        """Test that creating articles requires admin."""
        response = await client.post(
            "/api/v1/help/admin/articles",
            json={
                "category_id": str(help_category.id),
                "title": "New Article",
                "slug": "new-article",
                "content": "Content",
            },
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_article_as_admin(
        self,
        client: AsyncClient,
        test_super_admin_token,
        help_category,
    ):
        """Test creating an article as admin."""
        unique_slug = f"new-article-{uuid4().hex[:8]}"
        response = await client.post(
            "/api/v1/help/admin/articles",
            json={
                "category_id": str(help_category.id),
                "title": "New Article",
                "slug": unique_slug,
                "content": "Article content here",
                "status": "published",
                "is_platform_wide": True,
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Article"
        assert data["slug"] == unique_slug

    @pytest.mark.asyncio
    async def test_list_all_articles_as_admin(
        self,
        client: AsyncClient,
        test_super_admin_token,
        help_article,
        draft_help_article,
    ):
        """Test listing all articles including drafts as admin."""
        response = await client.get(
            "/api/v1/help/admin/articles",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        # Should include both published and draft articles
        article_ids = [item["id"] for item in data["items"]]
        assert str(help_article.id) in article_ids
        assert str(draft_help_article.id) in article_ids

    @pytest.mark.asyncio
    async def test_get_article_by_id_as_admin(
        self,
        client: AsyncClient,
        test_super_admin_token,
        help_article,
    ):
        """Test getting an article by ID as admin."""
        response = await client.get(
            f"/api/v1/help/admin/articles/{help_article.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(help_article.id)

    @pytest.mark.asyncio
    async def test_update_article(
        self,
        client: AsyncClient,
        test_super_admin_token,
        help_article,
    ):
        """Test updating an article."""
        response = await client.put(
            f"/api/v1/help/admin/articles/{help_article.id}",
            json={"title": "Updated Article Title"},
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Article Title"

    @pytest.mark.asyncio
    async def test_delete_article(
        self,
        client: AsyncClient,
        test_super_admin_token,
        draft_help_article,
    ):
        """Test deleting an article."""
        response = await client.delete(
            f"/api/v1/help/admin/articles/{draft_help_article.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_reorder_articles(
        self,
        client: AsyncClient,
        test_super_admin_token,
        help_article,
        draft_help_article,
    ):
        """Test reordering articles."""
        response = await client.put(
            "/api/v1/help/admin/articles/reorder",
            json={
                "items": [
                    {"id": str(help_article.id), "display_order": 2},
                    {"id": str(draft_help_article.id), "display_order": 1},
                ]
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["updated_count"] == 2


# ============================================================================
# Admin FAQ Tests
# ============================================================================


class TestAdminFaqs:
    """Tests for admin FAQ endpoints."""

    @pytest.mark.asyncio
    async def test_create_faq_requires_admin(
        self,
        client: AsyncClient,
        test_jwt_token,
        help_category,
    ):
        """Test that creating FAQs requires admin."""
        response = await client.post(
            "/api/v1/help/admin/faqs",
            json={
                "category_id": str(help_category.id),
                "question": "New FAQ?",
                "answer": "Answer",
            },
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_faq_as_admin(
        self,
        client: AsyncClient,
        test_super_admin_token,
        help_category,
    ):
        """Test creating a FAQ as admin."""
        response = await client.post(
            "/api/v1/help/admin/faqs",
            json={
                "category_id": str(help_category.id),
                "question": "New FAQ Question?",
                "answer": "This is the answer.",
                "status": "published",
                "is_platform_wide": True,
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["question"] == "New FAQ Question?"

    @pytest.mark.asyncio
    async def test_list_all_faqs_as_admin(
        self,
        client: AsyncClient,
        test_super_admin_token,
        help_faq,
        draft_help_faq,
    ):
        """Test listing all FAQs including drafts as admin."""
        response = await client.get(
            "/api/v1/help/admin/faqs",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        # Should include both published and draft FAQs
        faq_ids = [item["id"] for item in data["items"]]
        assert str(help_faq.id) in faq_ids
        assert str(draft_help_faq.id) in faq_ids

    @pytest.mark.asyncio
    async def test_get_faq_by_id_as_admin(
        self,
        client: AsyncClient,
        test_super_admin_token,
        help_faq,
    ):
        """Test getting a FAQ by ID as admin."""
        response = await client.get(
            f"/api/v1/help/admin/faqs/{help_faq.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(help_faq.id)

    @pytest.mark.asyncio
    async def test_update_faq(
        self,
        client: AsyncClient,
        test_super_admin_token,
        help_faq,
    ):
        """Test updating a FAQ."""
        response = await client.put(
            f"/api/v1/help/admin/faqs/{help_faq.id}",
            json={"question": "Updated FAQ Question?"},
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["question"] == "Updated FAQ Question?"

    @pytest.mark.asyncio
    async def test_delete_faq(
        self,
        client: AsyncClient,
        test_super_admin_token,
        draft_help_faq,
    ):
        """Test deleting a FAQ."""
        response = await client.delete(
            f"/api/v1/help/admin/faqs/{draft_help_faq.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_reorder_faqs(
        self,
        client: AsyncClient,
        test_super_admin_token,
        help_faq,
        draft_help_faq,
    ):
        """Test reordering FAQs."""
        response = await client.put(
            "/api/v1/help/admin/faqs/reorder",
            json={
                "items": [
                    {"id": str(help_faq.id), "display_order": 2},
                    {"id": str(draft_help_faq.id), "display_order": 1},
                ]
            },
            headers={"Authorization": test_super_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["updated_count"] == 2
