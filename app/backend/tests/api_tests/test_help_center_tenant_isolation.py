"""
Tenant isolation tests for the PUBLIC (unauthenticated) help center endpoints.

The public endpoints must only ever expose platform-wide content
(organization_id IS NULL). Organization-scoped help content must never leak to
anonymous callers, even when it is published.

The super admin endpoints keep their unfiltered cross-organization view.
"""

from httpx import AsyncClient
import pytest


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def isolation_category(async_session):
    """Create a help center category."""
    from src.models.help_center import HelpCategory

    category = HelpCategory(
        name="Isolation Category",
        slug="isolation-category",
        description="Category used by tenant isolation tests",
        display_order=1,
    )
    async_session.add(category)
    await async_session.commit()
    await async_session.refresh(category)
    return category


@pytest.fixture
async def org_scoped_article(
    async_session, isolation_category, test_organization, test_admin_user
):
    """Create a PUBLISHED article owned by a single organization."""
    from src.models.help_center import HelpArticle

    article = HelpArticle(
        organization_id=test_organization.id,
        category_id=isolation_category.id,
        title="Tenant Confidential Runbook",
        slug="tenant-confidential-runbook",
        content="Confidential internal runbook for one tenant only.",
        status="published",
        display_order=1,
        created_by_id=test_admin_user.id,
    )
    async_session.add(article)
    await async_session.commit()
    await async_session.refresh(article)
    return article


@pytest.fixture
async def platform_article(async_session, isolation_category, test_admin_user):
    """Create a PUBLISHED platform-wide article."""
    from src.models.help_center import HelpArticle

    article = HelpArticle(
        organization_id=None,
        category_id=isolation_category.id,
        title="Public Platform Runbook",
        slug="public-platform-runbook",
        content="Confidential is a word that also appears in public content.",
        status="published",
        display_order=2,
        created_by_id=test_admin_user.id,
    )
    async_session.add(article)
    await async_session.commit()
    await async_session.refresh(article)
    return article


@pytest.fixture
async def org_scoped_faq(async_session, isolation_category, test_organization):
    """Create a PUBLISHED FAQ owned by a single organization."""
    from src.models.help_center import HelpFaq

    faq = HelpFaq(
        organization_id=test_organization.id,
        category_id=isolation_category.id,
        question="What is the tenant confidential escalation path?",
        answer="Confidential tenant-only escalation details.",
        status="published",
        display_order=1,
    )
    async_session.add(faq)
    await async_session.commit()
    await async_session.refresh(faq)
    return faq


@pytest.fixture
async def platform_faq(async_session, isolation_category):
    """Create a PUBLISHED platform-wide FAQ."""
    from src.models.help_center import HelpFaq

    faq = HelpFaq(
        organization_id=None,
        question="What is this platform?",
        answer="Confidential is a word that also appears in public answers.",
        category_id=isolation_category.id,
        status="published",
        display_order=2,
    )
    async_session.add(faq)
    await async_session.commit()
    await async_session.refresh(faq)
    return faq


# ============================================================================
# Public endpoints must NOT leak organization-scoped content
# ============================================================================


class TestPublicHelpCenterTenantIsolation:
    """Anonymous callers must never see organization-scoped help content."""

    @pytest.mark.asyncio
    async def test_public_article_list_excludes_org_content(
        self, client: AsyncClient, org_scoped_article, platform_article
    ):
        """GET /help/articles must not return another tenant's article."""
        response = await client.get("/api/v1/help/articles")
        assert response.status_code == 200
        data = response.json()

        returned_ids = {item["id"] for item in data["items"]}
        assert str(org_scoped_article.id) not in returned_ids
        assert str(platform_article.id) in returned_ids
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_public_article_by_slug_excludes_org_content(
        self, client: AsyncClient, org_scoped_article
    ):
        """GET /help/articles/{slug} must 404 for an org-scoped article."""
        response = await client.get(f"/api/v1/help/articles/{org_scoped_article.slug}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_public_faq_list_excludes_org_content(
        self, client: AsyncClient, org_scoped_faq, platform_faq
    ):
        """GET /help/faqs must not return another tenant's FAQ."""
        response = await client.get("/api/v1/help/faqs")
        assert response.status_code == 200
        data = response.json()

        returned_ids = {item["id"] for item in data["items"]}
        assert str(org_scoped_faq.id) not in returned_ids
        assert str(platform_faq.id) in returned_ids
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_public_search_excludes_org_content(
        self,
        client: AsyncClient,
        org_scoped_article,
        org_scoped_faq,
        platform_article,
        platform_faq,
    ):
        """GET /help/search must not return another tenant's content."""
        response = await client.get("/api/v1/help/search?q=Confidential")
        assert response.status_code == 200
        data = response.json()

        article_ids = {item["id"] for item in data["articles"]}
        faq_ids = {item["id"] for item in data["faqs"]}

        assert str(org_scoped_article.id) not in article_ids
        assert str(org_scoped_faq.id) not in faq_ids
        assert str(platform_article.id) in article_ids
        assert str(platform_faq.id) in faq_ids

    @pytest.mark.asyncio
    async def test_public_article_list_filtered_by_category_excludes_org_content(
        self,
        client: AsyncClient,
        isolation_category,
        org_scoped_article,
        platform_article,
    ):
        """Category filtering must not bypass the platform-only scope."""
        response = await client.get(
            f"/api/v1/help/articles?category_id={isolation_category.id}"
        )
        assert response.status_code == 200
        returned_ids = {item["id"] for item in response.json()["items"]}
        assert str(org_scoped_article.id) not in returned_ids
        assert str(platform_article.id) in returned_ids


class TestPublicHelpCenterPlatformContent:
    """Platform-wide content must still be publicly available."""

    @pytest.mark.asyncio
    async def test_public_endpoints_return_platform_content(
        self, client: AsyncClient, platform_article, platform_faq
    ):
        """All public routes serve published platform-wide content."""
        list_response = await client.get("/api/v1/help/articles")
        assert list_response.status_code == 200
        assert str(platform_article.id) in {
            item["id"] for item in list_response.json()["items"]
        }

        slug_response = await client.get(
            f"/api/v1/help/articles/{platform_article.slug}"
        )
        assert slug_response.status_code == 200
        assert slug_response.json()["id"] == str(platform_article.id)

        faq_response = await client.get("/api/v1/help/faqs")
        assert faq_response.status_code == 200
        assert str(platform_faq.id) in {
            item["id"] for item in faq_response.json()["items"]
        }

        search_response = await client.get("/api/v1/help/search?q=platform")
        assert search_response.status_code == 200
        search_data = search_response.json()
        assert str(platform_article.id) in {
            item["id"] for item in search_data["articles"]
        }


class TestSuperAdminHelpCenterScope:
    """Super admins keep the unfiltered cross-organization view."""

    @pytest.mark.asyncio
    async def test_super_admin_sees_all_articles(
        self,
        client: AsyncClient,
        test_admin_token,
        org_scoped_article,
        platform_article,
    ):
        """GET /help/admin/articles returns org-scoped and platform content."""
        response = await client.get(
            "/api/v1/help/admin/articles",
            headers={"Authorization": test_admin_token},
        )
        assert response.status_code == 200
        returned_ids = {item["id"] for item in response.json()["items"]}
        assert str(org_scoped_article.id) in returned_ids
        assert str(platform_article.id) in returned_ids

    @pytest.mark.asyncio
    async def test_super_admin_sees_all_faqs(
        self, client: AsyncClient, test_admin_token, org_scoped_faq, platform_faq
    ):
        """GET /help/admin/faqs returns org-scoped and platform content."""
        response = await client.get(
            "/api/v1/help/admin/faqs",
            headers={"Authorization": test_admin_token},
        )
        assert response.status_code == 200
        returned_ids = {item["id"] for item in response.json()["items"]}
        assert str(org_scoped_faq.id) in returned_ids
        assert str(platform_faq.id) in returned_ids
