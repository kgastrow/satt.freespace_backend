"""
Unit tests for help center content scoping.

Three visibility scopes must stay distinct and must never be confused:
1. organization_id=<uuid>                     -> that org's content + platform-wide
2. platform_only=True                         -> platform-wide content ONLY
3. organization_id=None, platform_only=False  -> unfiltered super admin view
"""

import pytest

from src.crud.help_center import (
    create_article,
    create_category,
    create_faq,
    get_article_by_slug,
    get_articles,
    get_faqs,
    search_articles,
    search_faqs,
)


async def _seed(async_session, test_organization, second_organization, test_user):
    """Seed one platform-wide and two org-scoped published articles/FAQs."""
    category = await create_category(
        async_session, {"name": "Scope", "slug": "scope-category"}
    )

    platform_article = await create_article(
        async_session,
        {
            "title": "Platform Scope Article",
            "slug": "platform-scope-article",
            "content": "Scopeword platform content",
            "category_id": str(category.id),
            "status": "published",
        },
        None,
        str(test_user.id),
    )
    org_article = await create_article(
        async_session,
        {
            "title": "Org Scope Article",
            "slug": "org-scope-article",
            "content": "Scopeword org content",
            "category_id": str(category.id),
            "status": "published",
        },
        str(test_organization.id),
        str(test_user.id),
    )
    other_org_article = await create_article(
        async_session,
        {
            "title": "Other Org Scope Article",
            "slug": "other-org-scope-article",
            "content": "Scopeword other org content",
            "category_id": str(category.id),
            "status": "published",
        },
        str(second_organization.id),
        str(test_user.id),
    )

    platform_faq = await create_faq(
        async_session,
        {
            "question": "Scopeword platform question?",
            "answer": "Platform answer.",
            "category_id": str(category.id),
            "status": "published",
        },
        None,
    )
    org_faq = await create_faq(
        async_session,
        {
            "question": "Scopeword org question?",
            "answer": "Org answer.",
            "category_id": str(category.id),
            "status": "published",
        },
        str(test_organization.id),
    )

    return {
        "category": category,
        "platform_article": platform_article,
        "org_article": org_article,
        "other_org_article": other_org_article,
        "platform_faq": platform_faq,
        "org_faq": org_faq,
    }


class TestHelpArticleScopes:
    """Scope behaviour for article queries."""

    @pytest.mark.asyncio
    async def test_platform_only_excludes_all_org_content(
        self, async_session, test_organization, second_organization, test_user
    ):
        """platform_only=True returns platform-wide rows only."""
        seeded = await _seed(
            async_session, test_organization, second_organization, test_user
        )

        articles, total = await get_articles(
            async_session, organization_id=None, platform_only=True
        )
        ids = {a.id for a in articles}

        assert total == 1
        assert seeded["platform_article"].id in ids
        assert seeded["org_article"].id not in ids
        assert seeded["other_org_article"].id not in ids

    @pytest.mark.asyncio
    async def test_organization_scope_includes_own_and_platform(
        self, async_session, test_organization, second_organization, test_user
    ):
        """An organization sees its own rows plus platform-wide rows."""
        seeded = await _seed(
            async_session, test_organization, second_organization, test_user
        )

        articles, total = await get_articles(
            async_session, organization_id=str(test_organization.id)
        )
        ids = {a.id for a in articles}

        assert total == 2
        assert seeded["platform_article"].id in ids
        assert seeded["org_article"].id in ids
        assert seeded["other_org_article"].id not in ids

    @pytest.mark.asyncio
    async def test_unfiltered_admin_scope_sees_everything(
        self, async_session, test_organization, second_organization, test_user
    ):
        """organization_id=None with platform_only=False stays unfiltered."""
        seeded = await _seed(
            async_session, test_organization, second_organization, test_user
        )

        articles, total = await get_articles(
            async_session, organization_id=None, platform_only=False
        )
        ids = {a.id for a in articles}

        assert total == 3
        assert seeded["platform_article"].id in ids
        assert seeded["org_article"].id in ids
        assert seeded["other_org_article"].id in ids

    @pytest.mark.asyncio
    async def test_get_article_by_slug_platform_only(
        self, async_session, test_organization, second_organization, test_user
    ):
        """Slug lookups honour the platform-only scope."""
        seeded = await _seed(
            async_session, test_organization, second_organization, test_user
        )

        assert (
            await get_article_by_slug(
                async_session,
                seeded["org_article"].slug,
                organization_id=None,
                platform_only=True,
            )
            is None
        )
        found = await get_article_by_slug(
            async_session,
            seeded["platform_article"].slug,
            organization_id=None,
            platform_only=True,
        )
        assert found is not None
        assert found.id == seeded["platform_article"].id

    @pytest.mark.asyncio
    async def test_search_articles_platform_only(
        self, async_session, test_organization, second_organization, test_user
    ):
        """Search honours the platform-only scope."""
        seeded = await _seed(
            async_session, test_organization, second_organization, test_user
        )

        results = await search_articles(
            async_session, "Scopeword", organization_id=None, platform_only=True
        )
        ids = {a.id for a in results}

        assert ids == {seeded["platform_article"].id}

    @pytest.mark.asyncio
    async def test_platform_only_with_organization_id_is_rejected(
        self, async_session, test_organization
    ):
        """The contradictory scope combination raises instead of guessing."""
        with pytest.raises(ValueError):
            await get_articles(
                async_session,
                organization_id=str(test_organization.id),
                platform_only=True,
            )


class TestHelpFaqScopes:
    """Scope behaviour for FAQ queries."""

    @pytest.mark.asyncio
    async def test_faqs_platform_only_excludes_org_content(
        self, async_session, test_organization, second_organization, test_user
    ):
        """platform_only=True returns platform-wide FAQs only."""
        seeded = await _seed(
            async_session, test_organization, second_organization, test_user
        )

        faqs, total = await get_faqs(
            async_session, organization_id=None, platform_only=True
        )
        ids = {f.id for f in faqs}

        assert total == 1
        assert seeded["platform_faq"].id in ids
        assert seeded["org_faq"].id not in ids

    @pytest.mark.asyncio
    async def test_faqs_unfiltered_admin_scope_sees_everything(
        self, async_session, test_organization, second_organization, test_user
    ):
        """The super admin view still sees org-scoped FAQs."""
        seeded = await _seed(
            async_session, test_organization, second_organization, test_user
        )

        faqs, total = await get_faqs(
            async_session, organization_id=None, platform_only=False
        )
        ids = {f.id for f in faqs}

        assert total == 2
        assert seeded["platform_faq"].id in ids
        assert seeded["org_faq"].id in ids

    @pytest.mark.asyncio
    async def test_search_faqs_platform_only(
        self, async_session, test_organization, second_organization, test_user
    ):
        """FAQ search honours the platform-only scope."""
        seeded = await _seed(
            async_session, test_organization, second_organization, test_user
        )

        results = await search_faqs(
            async_session, "Scopeword", organization_id=None, platform_only=True
        )
        ids = {f.id for f in results}

        assert ids == {seeded["platform_faq"].id}

    @pytest.mark.asyncio
    async def test_faqs_platform_only_with_organization_id_is_rejected(
        self, async_session, test_organization
    ):
        """The contradictory scope combination raises instead of guessing."""
        with pytest.raises(ValueError):
            await get_faqs(
                async_session,
                organization_id=str(test_organization.id),
                platform_only=True,
            )
