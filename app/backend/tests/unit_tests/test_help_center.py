"""
Unit tests for help center models and CRUD operations.
Tests HelpCategory, HelpArticle, and HelpFaq model creation, field constraints, relationships, and CRUD operations.
"""

import pytest

from src.crud.help_center import (
    create_article,
    create_faq,
    get_article_by_id,
    get_article_by_slug,
    get_articles,
    get_faq_by_id,
    get_faqs,
    search_articles,
    search_faqs,
    soft_delete_article,
    soft_delete_faq,
    update_article,
    update_faq,
)
from src.crud.help_center import (
    create_category as create_help_category,
)
from src.crud.help_center import (
    get_categories as get_help_categories,
)
from src.crud.help_center import (
    get_category_by_id as get_help_category_by_id,
)
from src.crud.help_center import (
    get_category_by_slug as get_help_category_by_slug,
)
from src.crud.help_center import (
    soft_delete_category as soft_delete_help_category,
)
from src.crud.help_center import (
    update_category as update_help_category,
)
from src.models.help_center import HelpArticle, HelpCategory, HelpFaq


class TestHelpCategoryModel:
    """Tests for HelpCategory model."""

    @pytest.mark.asyncio
    async def test_create_help_category(self, async_session):
        """Test creating a help category."""
        category = HelpCategory(
            name="Getting Started",
            description="Guides for new users",
            slug="getting-started",
            display_order=1,
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        assert category.id is not None
        assert category.name == "Getting Started"
        assert category.description == "Guides for new users"
        assert category.slug == "getting-started"
        assert category.display_order == 1
        assert category.created_time is not None
        assert category.deleted_time is None

    @pytest.mark.asyncio
    async def test_help_category_default_display_order(self, async_session):
        """Test category has default display_order of 0."""
        category = HelpCategory(
            name="FAQ",
            slug="faq",
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        assert category.display_order == 0

    @pytest.mark.asyncio
    async def test_help_category_unique_slug(self, async_session):
        """Test category slug must be unique for non-deleted categories."""
        category1 = HelpCategory(
            name="Category 1",
            slug="duplicate-slug",
        )
        async_session.add(category1)
        await async_session.commit()

        category2 = HelpCategory(
            name="Category 2",
            slug="duplicate-slug",
        )
        async_session.add(category2)

        with pytest.raises(Exception):
            await async_session.commit()


class TestHelpArticleModel:
    """Tests for HelpArticle model."""

    @pytest.mark.asyncio
    async def test_create_platform_wide_article(self, async_session, test_user):
        """Test creating a platform-wide article (NULL organization_id)."""
        category = HelpCategory(
            name="Tutorials",
            slug="tutorials",
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        article = HelpArticle(
            organization_id=None,
            title="How to Get Started",
            slug="how-to-get-started",
            content="# Getting Started\n\nWelcome to our platform!",
            category_id=category.id,
            status="published",
            created_by_id=test_user.id,
        )
        async_session.add(article)
        await async_session.commit()
        await async_session.refresh(article)

        assert article.id is not None
        assert article.organization_id is None
        assert article.title == "How to Get Started"
        assert article.slug == "how-to-get-started"
        assert article.content == "# Getting Started\n\nWelcome to our platform!"
        assert article.category_id == category.id
        assert article.status == "published"
        assert article.created_by_id == test_user.id
        assert article.created_time is not None
        assert article.deleted_time is None

    @pytest.mark.asyncio
    async def test_create_org_specific_article(
        self, async_session, test_organization, test_user
    ):
        """Test creating an org-specific article."""
        category = HelpCategory(
            name="Tutorials",
            slug="tutorials",
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        article = HelpArticle(
            organization_id=test_organization.id,
            title="Organization Guide",
            slug="org-guide",
            content="Organization-specific content",
            category_id=category.id,
            status="draft",
            created_by_id=test_user.id,
        )
        async_session.add(article)
        await async_session.commit()
        await async_session.refresh(article)

        assert article.id is not None
        assert article.organization_id == test_organization.id
        assert article.status == "draft"

    @pytest.mark.asyncio
    async def test_help_article_default_status(self, async_session, test_user):
        """Test article defaults to draft status."""
        category = HelpCategory(
            name="Tutorials",
            slug="tutorials",
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        article = HelpArticle(
            title="Draft Article",
            slug="draft-article",
            content="Draft content",
            category_id=category.id,
            created_by_id=test_user.id,
        )
        async_session.add(article)
        await async_session.commit()
        await async_session.refresh(article)

        assert article.status == "draft"

    @pytest.mark.asyncio
    async def test_help_article_with_featured_image(self, async_session, test_user):
        """Test article with featured image."""
        category = HelpCategory(
            name="Tutorials",
            slug="tutorials",
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        article = HelpArticle(
            title="Article with Image",
            slug="article-with-image",
            content="Content with image",
            category_id=category.id,
            created_by_id=test_user.id,
            featured_image_url="https://example.com/image.jpg",
        )
        async_session.add(article)
        await async_session.commit()
        await async_session.refresh(article)

        assert article.featured_image_url == "https://example.com/image.jpg"

    @pytest.mark.asyncio
    async def test_help_article_category_relationship(self, async_session, test_user):
        """Test article has proper relationship to category."""
        category = HelpCategory(
            name="Tutorials",
            slug="tutorials",
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        article = HelpArticle(
            title="Test Article",
            slug="test-article",
            content="Test content",
            category_id=category.id,
            created_by_id=test_user.id,
        )
        async_session.add(article)
        await async_session.commit()
        await async_session.refresh(article)

        await async_session.refresh(article, ["category"])
        assert article.category is not None
        assert article.category.id == category.id
        assert article.category.name == "Tutorials"

    @pytest.mark.asyncio
    async def test_help_article_organization_relationship(
        self, async_session, test_organization, test_user
    ):
        """Test article has proper relationship to organization."""
        category = HelpCategory(
            name="Tutorials",
            slug="tutorials",
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        article = HelpArticle(
            organization_id=test_organization.id,
            title="Org Article",
            slug="org-article",
            content="Org content",
            category_id=category.id,
            created_by_id=test_user.id,
        )
        async_session.add(article)
        await async_session.commit()
        await async_session.refresh(article)

        await async_session.refresh(article, ["organization"])
        assert article.organization is not None
        assert article.organization.id == test_organization.id

    @pytest.mark.asyncio
    async def test_help_article_unique_slug(self, async_session, test_user):
        """Test article slug must be unique for non-deleted articles."""
        category = HelpCategory(
            name="Tutorials",
            slug="tutorials",
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        article1 = HelpArticle(
            title="Article 1",
            slug="duplicate-slug",
            content="Content 1",
            category_id=category.id,
            created_by_id=test_user.id,
        )
        async_session.add(article1)
        await async_session.commit()

        article2 = HelpArticle(
            title="Article 2",
            slug="duplicate-slug",
            content="Content 2",
            category_id=category.id,
            created_by_id=test_user.id,
        )
        async_session.add(article2)

        with pytest.raises(Exception):
            await async_session.commit()


class TestHelpFaqModel:
    """Tests for HelpFaq model."""

    @pytest.mark.asyncio
    async def test_create_platform_wide_faq(self, async_session):
        """Test creating a platform-wide FAQ (NULL organization_id)."""
        category = HelpCategory(
            name="General",
            slug="general",
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        faq = HelpFaq(
            organization_id=None,
            question="What is this platform?",
            answer="This is a multi-tenant SaaS platform.",
            category_id=category.id,
            status="published",
            display_order=1,
        )
        async_session.add(faq)
        await async_session.commit()
        await async_session.refresh(faq)

        assert faq.id is not None
        assert faq.organization_id is None
        assert faq.question == "What is this platform?"
        assert faq.answer == "This is a multi-tenant SaaS platform."
        assert faq.category_id == category.id
        assert faq.status == "published"
        assert faq.display_order == 1
        assert faq.created_time is not None
        assert faq.deleted_time is None

    @pytest.mark.asyncio
    async def test_create_org_specific_faq(self, async_session, test_organization):
        """Test creating an org-specific FAQ."""
        category = HelpCategory(
            name="General",
            slug="general",
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        faq = HelpFaq(
            organization_id=test_organization.id,
            question="How do I use this feature?",
            answer="Organization-specific instructions.",
            category_id=category.id,
            status="draft",
        )
        async_session.add(faq)
        await async_session.commit()
        await async_session.refresh(faq)

        assert faq.id is not None
        assert faq.organization_id == test_organization.id
        assert faq.status == "draft"

    @pytest.mark.asyncio
    async def test_help_faq_default_status(self, async_session):
        """Test FAQ defaults to draft status."""
        category = HelpCategory(
            name="General",
            slug="general",
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        faq = HelpFaq(
            question="Test question?",
            answer="Test answer.",
            category_id=category.id,
        )
        async_session.add(faq)
        await async_session.commit()
        await async_session.refresh(faq)

        assert faq.status == "draft"

    @pytest.mark.asyncio
    async def test_help_faq_default_display_order(self, async_session):
        """Test FAQ has default display_order of 0."""
        category = HelpCategory(
            name="General",
            slug="general",
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        faq = HelpFaq(
            question="Test question?",
            answer="Test answer.",
            category_id=category.id,
        )
        async_session.add(faq)
        await async_session.commit()
        await async_session.refresh(faq)

        assert faq.display_order == 0

    @pytest.mark.asyncio
    async def test_help_faq_category_relationship(self, async_session):
        """Test FAQ has proper relationship to category."""
        category = HelpCategory(
            name="General",
            slug="general",
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        faq = HelpFaq(
            question="Test question?",
            answer="Test answer.",
            category_id=category.id,
        )
        async_session.add(faq)
        await async_session.commit()
        await async_session.refresh(faq)

        await async_session.refresh(faq, ["category"])
        assert faq.category is not None
        assert faq.category.id == category.id
        assert faq.category.name == "General"

    @pytest.mark.asyncio
    async def test_help_faq_organization_relationship(
        self, async_session, test_organization
    ):
        """Test FAQ has proper relationship to organization."""
        category = HelpCategory(
            name="General",
            slug="general",
        )
        async_session.add(category)
        await async_session.commit()
        await async_session.refresh(category)

        faq = HelpFaq(
            organization_id=test_organization.id,
            question="Org question?",
            answer="Org answer.",
            category_id=category.id,
        )
        async_session.add(faq)
        await async_session.commit()
        await async_session.refresh(faq)

        await async_session.refresh(faq, ["organization"])
        assert faq.organization is not None
        assert faq.organization.id == test_organization.id


# ============================================================================
# CRUD Tests
# ============================================================================


class TestHelpCategoryCRUD:
    """Tests for HelpCategory CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_category(self, async_session):
        """Test creating a category via CRUD."""
        category_data = {
            "name": "Getting Started",
            "description": "New user guides",
            "slug": "getting-started",
            "display_order": 1,
        }
        category = await create_help_category(async_session, category_data)

        assert category.id is not None
        assert category.name == "Getting Started"
        assert category.slug == "getting-started"
        assert category.display_order == 1

    @pytest.mark.asyncio
    async def test_create_category_duplicate_slug(self, async_session):
        """Test creating category with duplicate slug raises error."""
        category_data = {"name": "Cat 1", "slug": "duplicate"}
        await create_help_category(async_session, category_data)

        with pytest.raises(ValueError, match="already exists"):
            await create_help_category(
                async_session, {"name": "Cat 2", "slug": "duplicate"}
            )

    @pytest.mark.asyncio
    async def test_get_category_by_id(self, async_session):
        """Test retrieving category by ID."""
        category_data = {"name": "Test", "slug": "test"}
        created = await create_help_category(async_session, category_data)

        retrieved = await get_help_category_by_id(async_session, str(created.id))
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "Test"

    @pytest.mark.asyncio
    async def test_get_category_by_slug(self, async_session):
        """Test retrieving category by slug."""
        category_data = {"name": "Test", "slug": "test-slug"}
        created = await create_help_category(async_session, category_data)

        retrieved = await get_help_category_by_slug(async_session, "test-slug")
        assert retrieved is not None
        assert retrieved.id == created.id

    @pytest.mark.asyncio
    async def test_get_categories_pagination(self, async_session):
        """Test retrieving categories with pagination."""
        for i in range(5):
            await create_help_category(
                async_session, {"name": f"Cat {i}", "slug": f"cat-{i}"}
            )

        categories, total = await get_help_categories(async_session, limit=2, offset=0)
        assert total == 5
        assert len(categories) == 2

    @pytest.mark.asyncio
    async def test_update_category(self, async_session):
        """Test updating a category."""
        category_data = {"name": "Original", "slug": "original"}
        created = await create_help_category(async_session, category_data)

        updated = await update_help_category(
            async_session, str(created.id), {"name": "Updated", "display_order": 5}
        )
        assert updated is not None
        assert updated.name == "Updated"
        assert updated.display_order == 5
        assert updated.slug == "original"

    @pytest.mark.asyncio
    async def test_soft_delete_category(self, async_session):
        """Test soft deleting a category."""
        category_data = {"name": "To Delete", "slug": "to-delete"}
        created = await create_help_category(async_session, category_data)

        deleted = await soft_delete_help_category(async_session, str(created.id))
        assert deleted is not None
        assert deleted.deleted_time is not None

        retrieved = await get_help_category_by_id(async_session, str(created.id))
        assert retrieved is None


class TestHelpArticleCRUD:
    """Tests for HelpArticle CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_platform_wide_article(self, async_session, test_user):
        """Test creating a platform-wide article."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        article_data = {
            "title": "Platform Article",
            "slug": "platform-article",
            "content": "# Platform content",
            "category_id": str(category.id),
            "status": "published",
        }
        article = await create_article(
            async_session, article_data, None, str(test_user.id)
        )

        assert article.id is not None
        assert article.organization_id is None
        assert article.title == "Platform Article"
        assert article.status == "published"
        assert article.published_at is not None

    @pytest.mark.asyncio
    async def test_create_org_specific_article(
        self, async_session, test_organization, test_user
    ):
        """Test creating an org-specific article."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        article_data = {
            "title": "Org Article",
            "slug": "org-article",
            "content": "Org content",
            "category_id": str(category.id),
            "status": "draft",
        }
        article = await create_article(
            async_session, article_data, str(test_organization.id), str(test_user.id)
        )

        assert article.organization_id == test_organization.id
        assert article.status == "draft"
        assert article.published_at is None

    @pytest.mark.asyncio
    async def test_create_article_duplicate_slug(self, async_session, test_user):
        """Test creating article with duplicate slug raises error."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        article_data = {
            "title": "Article 1",
            "slug": "duplicate",
            "content": "Content",
            "category_id": str(category.id),
        }
        await create_article(async_session, article_data, None, str(test_user.id))

        with pytest.raises(ValueError, match="already exists"):
            article_data["title"] = "Article 2"
            await create_article(async_session, article_data, None, str(test_user.id))

    @pytest.mark.asyncio
    async def test_get_article_by_id(self, async_session, test_organization, test_user):
        """Test retrieving article by ID within org context."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        article_data = {
            "title": "Test Article",
            "slug": "test-article",
            "content": "Content",
            "category_id": str(category.id),
        }
        created = await create_article(
            async_session, article_data, str(test_organization.id), str(test_user.id)
        )

        # Can retrieve with matching org
        retrieved = await get_article_by_id(
            async_session, str(created.id), str(test_organization.id)
        )
        assert retrieved is not None
        assert retrieved.id == created.id

    @pytest.mark.asyncio
    async def test_get_article_by_slug(self, async_session, test_user):
        """Test retrieving article by slug."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        article_data = {
            "title": "Test",
            "slug": "test-slug",
            "content": "Content",
            "category_id": str(category.id),
        }
        created = await create_article(
            async_session, article_data, None, str(test_user.id)
        )

        retrieved = await get_article_by_slug(async_session, "test-slug", None)
        assert retrieved is not None
        assert retrieved.id == created.id

    @pytest.mark.asyncio
    async def test_get_articles_published_only(self, async_session, test_user):
        """Test retrieving only published articles."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        # Create draft and published
        await create_article(
            async_session,
            {
                "title": "Draft",
                "slug": "draft",
                "content": "Content",
                "category_id": str(category.id),
                "status": "draft",
            },
            None,
            str(test_user.id),
        )
        await create_article(
            async_session,
            {
                "title": "Published",
                "slug": "published",
                "content": "Content",
                "category_id": str(category.id),
                "status": "published",
            },
            None,
            str(test_user.id),
        )

        articles, total = await get_articles(async_session, None, published_only=True)
        assert total == 1
        assert articles[0].status == "published"

    @pytest.mark.asyncio
    async def test_search_articles(self, async_session, test_user):
        """Test searching articles by content."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        await create_article(
            async_session,
            {
                "title": "Python Guide",
                "slug": "python-guide",
                "content": "Learn Python programming",
                "category_id": str(category.id),
                "status": "published",
            },
            None,
            str(test_user.id),
        )
        await create_article(
            async_session,
            {
                "title": "JavaScript Tutorial",
                "slug": "js-tutorial",
                "content": "Learn JavaScript basics",
                "category_id": str(category.id),
                "status": "published",
            },
            None,
            str(test_user.id),
        )

        results = await search_articles(
            async_session, "Python", None, published_only=True
        )
        assert len(results) == 1
        assert "Python" in results[0].title

    @pytest.mark.asyncio
    async def test_update_article(self, async_session, test_user):
        """Test updating an article."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        article_data = {
            "title": "Original",
            "slug": "original",
            "content": "Original content",
            "category_id": str(category.id),
            "status": "draft",
        }
        created = await create_article(
            async_session, article_data, None, str(test_user.id)
        )

        updated = await update_article(
            async_session,
            str(created.id),
            None,
            {"title": "Updated", "status": "published"},
        )
        assert updated is not None
        assert updated.title == "Updated"
        assert updated.status == "published"
        assert updated.published_at is not None

    @pytest.mark.asyncio
    async def test_soft_delete_article(self, async_session, test_user):
        """Test soft deleting an article."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        article_data = {
            "title": "To Delete",
            "slug": "to-delete",
            "content": "Content",
            "category_id": str(category.id),
        }
        created = await create_article(
            async_session, article_data, None, str(test_user.id)
        )

        deleted = await soft_delete_article(async_session, str(created.id), None)
        assert deleted is not None
        assert deleted.deleted_time is not None

        retrieved = await get_article_by_id(async_session, str(created.id), None)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_article_tenant_isolation(
        self, async_session, test_organization, second_organization, test_user
    ):
        """Test articles are properly isolated by organization."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        # Create article in second_org
        article_data = {
            "title": "Other Org Article",
            "slug": "other-org",
            "content": "Content",
            "category_id": str(category.id),
        }
        other_article = await create_article(
            async_session, article_data, str(second_organization.id), str(test_user.id)
        )

        # Try to access with test_org - should not find it
        retrieved = await get_article_by_id(
            async_session, str(other_article.id), str(test_organization.id)
        )
        assert retrieved is None

        # Super admin (org_id=None) should see it
        retrieved = await get_article_by_id(async_session, str(other_article.id), None)
        assert retrieved is not None


class TestHelpFaqCRUD:
    """Tests for HelpFaq CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_platform_wide_faq(self, async_session):
        """Test creating a platform-wide FAQ."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        faq_data = {
            "question": "What is this?",
            "answer": "This is a FAQ.",
            "category_id": str(category.id),
            "status": "published",
            "display_order": 1,
        }
        faq = await create_faq(async_session, faq_data, None)

        assert faq.id is not None
        assert faq.organization_id is None
        assert faq.question == "What is this?"
        assert faq.status == "published"
        assert faq.display_order == 1

    @pytest.mark.asyncio
    async def test_create_org_specific_faq(self, async_session, test_organization):
        """Test creating an org-specific FAQ."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        faq_data = {
            "question": "Org question?",
            "answer": "Org answer.",
            "category_id": str(category.id),
            "status": "draft",
        }
        faq = await create_faq(async_session, faq_data, str(test_organization.id))

        assert faq.organization_id == test_organization.id
        assert faq.status == "draft"

    @pytest.mark.asyncio
    async def test_get_faq_by_id(self, async_session, test_organization):
        """Test retrieving FAQ by ID within org context."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        faq_data = {
            "question": "Test question?",
            "answer": "Test answer.",
            "category_id": str(category.id),
        }
        created = await create_faq(async_session, faq_data, str(test_organization.id))

        # Can retrieve with matching org
        retrieved = await get_faq_by_id(
            async_session, str(created.id), str(test_organization.id)
        )
        assert retrieved is not None
        assert retrieved.id == created.id

    @pytest.mark.asyncio
    async def test_get_faqs_published_only(self, async_session):
        """Test retrieving only published FAQs."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        # Create draft and published
        await create_faq(
            async_session,
            {
                "question": "Draft?",
                "answer": "Draft.",
                "category_id": str(category.id),
                "status": "draft",
            },
            None,
        )
        await create_faq(
            async_session,
            {
                "question": "Published?",
                "answer": "Published.",
                "category_id": str(category.id),
                "status": "published",
            },
            None,
        )

        faqs, total = await get_faqs(async_session, None, published_only=True)
        assert total == 1
        assert faqs[0].status == "published"

    @pytest.mark.asyncio
    async def test_get_faqs_by_category(self, async_session):
        """Test retrieving FAQs filtered by category."""
        cat1 = await create_help_category(
            async_session, {"name": "Cat1", "slug": "cat1"}
        )
        cat2 = await create_help_category(
            async_session, {"name": "Cat2", "slug": "cat2"}
        )

        await create_faq(
            async_session,
            {
                "question": "Q1?",
                "answer": "A1",
                "category_id": str(cat1.id),
                "status": "published",
            },
            None,
        )
        await create_faq(
            async_session,
            {
                "question": "Q2?",
                "answer": "A2",
                "category_id": str(cat2.id),
                "status": "published",
            },
            None,
        )

        faqs, total = await get_faqs(
            async_session, None, category_id=str(cat1.id), published_only=True
        )
        assert total == 1
        assert faqs[0].category_id == cat1.id

    @pytest.mark.asyncio
    async def test_search_faqs(self, async_session):
        """Test searching FAQs by question and answer."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        await create_faq(
            async_session,
            {
                "question": "How to reset password?",
                "answer": "Click forgot password link.",
                "category_id": str(category.id),
                "status": "published",
            },
            None,
        )
        await create_faq(
            async_session,
            {
                "question": "How to login?",
                "answer": "Enter credentials.",
                "category_id": str(category.id),
                "status": "published",
            },
            None,
        )

        results = await search_faqs(
            async_session, "password", None, published_only=True
        )
        assert len(results) == 1
        assert "password" in results[0].question.lower()

    @pytest.mark.asyncio
    async def test_update_faq(self, async_session):
        """Test updating a FAQ."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        faq_data = {
            "question": "Original?",
            "answer": "Original.",
            "category_id": str(category.id),
            "status": "draft",
            "display_order": 0,
        }
        created = await create_faq(async_session, faq_data, None)

        updated = await update_faq(
            async_session,
            str(created.id),
            None,
            {"answer": "Updated.", "status": "published", "display_order": 5},
        )
        assert updated is not None
        assert updated.answer == "Updated."
        assert updated.status == "published"
        assert updated.display_order == 5

    @pytest.mark.asyncio
    async def test_soft_delete_faq(self, async_session):
        """Test soft deleting a FAQ."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        faq_data = {
            "question": "To delete?",
            "answer": "To delete.",
            "category_id": str(category.id),
        }
        created = await create_faq(async_session, faq_data, None)

        deleted = await soft_delete_faq(async_session, str(created.id), None)
        assert deleted is not None
        assert deleted.deleted_time is not None

        retrieved = await get_faq_by_id(async_session, str(created.id), None)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_faq_tenant_isolation(
        self, async_session, test_organization, second_organization
    ):
        """Test FAQs are properly isolated by organization."""
        category = await create_help_category(
            async_session, {"name": "Test", "slug": "test"}
        )

        # Create FAQ in second_org
        faq_data = {
            "question": "Other org question?",
            "answer": "Other org answer.",
            "category_id": str(category.id),
        }
        other_faq = await create_faq(
            async_session, faq_data, str(second_organization.id)
        )

        # Try to access with test_org - should not find it
        retrieved = await get_faq_by_id(
            async_session, str(other_faq.id), str(test_organization.id)
        )
        assert retrieved is None

        # Super admin (org_id=None) should see it
        retrieved = await get_faq_by_id(async_session, str(other_faq.id), None)
        assert retrieved is not None
