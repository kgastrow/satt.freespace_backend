#!/usr/bin/env python3
"""
Seed script for smoke test authentication.

Creates a dedicated organization and user for smoke testing, then outputs
JWT tokens for browser authentication injection.

Usage: python scripts/seed_smoke_test.py --adw-id <adw_id>

Outputs JSON to stdout:
{
  "user_id": "uuid",
  "organization_id": "uuid",
  "org_slug": "smoke-test-<adw_id>",
  "email": "smoke@test.local",
  "access_token": "jwt...",
  "refresh_token": "jwt..."
}
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import yaml

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings
from src.core.security import create_access_token
from src.crud.help_center import (
    create_article,
    create_category,
    create_faq,
    get_categories,
)
from src.crud.organization import create_organization, get_organization_by_slug
from src.crud.refresh_token import create_refresh_token as create_db_refresh_token
from src.crud.user import create_user, get_user_by_email
from src.services.organization_seeding import (
    seed_default_notification_categories,
    seed_default_permissions,
    seed_default_roles,
)

SEED_DATA_DIR = Path(__file__).parent / "seed_data"


# Fixed smoke test credentials
SMOKE_EMAIL = "smoke-test@example.com"
SMOKE_PASSWORD = "SmokeTest@123"
SMOKE_FIRST_NAME = "Smoke"
SMOKE_LAST_NAME = "Tester"


def load_yaml(filename: str):
    """Load a YAML file from the seed_data directory."""
    filepath = SEED_DATA_DIR / filename
    with open(filepath) as f:
        return yaml.safe_load(f)


async def seed_help_center(
    session: AsyncSession, organization_id: str, created_by_id: str
) -> None:
    """Seed Help Center categories, FAQs, and articles from YAML if not already present."""
    existing_categories, _ = await get_categories(session, limit=1)
    if existing_categories:
        return

    categories_data = load_yaml("help_center/categories.yaml")
    faqs_data = load_yaml("help_center/faqs.yaml")
    articles_data = load_yaml("help_center/articles.yaml")

    category_map = {}
    for cat_data in categories_data:
        category = await create_category(session, cat_data)
        category_map[cat_data["slug"]] = str(category.id)

    for faq_data in faqs_data:
        category_id = category_map.get(faq_data["category_slug"])
        if category_id:
            await create_faq(
                session,
                {
                    "question": faq_data["question"],
                    "answer": faq_data["answer"],
                    "category_id": category_id,
                    "status": "published",
                    "display_order": faq_data.get("display_order", 0),
                },
                organization_id,
            )

    for article_data in articles_data:
        category_id = category_map.get(article_data["category_slug"])
        if category_id:
            await create_article(
                session,
                {
                    "title": article_data["title"],
                    "slug": article_data["slug"],
                    "content": article_data["content"],
                    "category_id": category_id,
                    "status": "published",
                    "featured_image_url": article_data.get("featured_image_url"),
                },
                organization_id,
                created_by_id,
            )


async def seed_smoke_test(adw_id: str) -> dict:
    """
    Create or reuse smoke test organization and user, then generate tokens.

    Args:
        adw_id: The ADW identifier for unique org slug

    Returns:
        Dictionary with user_id, organization_id, org_slug, email, access_token, refresh_token
    """
    org_slug = f"smoke-test-{adw_id}"
    org_name = f"Smoke Test Org ({adw_id})"

    # Create engine - use direct connection for seeding
    engine = create_async_engine(
        settings.DATABASE_URL_DIRECT,
        echo=False,
        poolclass=NullPool,
    )

    # Create session factory
    async_session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    result = {}

    async with async_session_factory() as session:
        try:
            # Step 1: Create or get organization
            existing_org = await get_organization_by_slug(session, org_slug)

            if existing_org:
                organization = existing_org
            else:
                organization_data = {"name": org_name, "slug": org_slug}
                organization = await create_organization(session, organization_data)

            org_id = str(organization.id)

            # Step 2: Ensure global roles and permissions exist
            await seed_default_roles(session)
            await seed_default_permissions(session)
            await seed_default_notification_categories(session)

            # Step 3: Create or get smoke test user
            existing_user = await get_user_by_email(session, SMOKE_EMAIL, org_id)

            if existing_user:
                user = existing_user
            else:
                user_data = {
                    "email": SMOKE_EMAIL,
                    "password": SMOKE_PASSWORD,
                    "email_verified": True,
                    "is_admin": True,
                    "first_name": SMOKE_FIRST_NAME,
                    "last_name": SMOKE_LAST_NAME,
                }
                user = await create_user(session, user_data, org_id)

            # Step 4: Seed help center content
            await seed_help_center(session, org_id, str(user.id))

            # Step 5: Generate tokens
            access_token = create_access_token(str(user.id), org_id)
            refresh_token = await create_db_refresh_token(session, str(user.id), org_id)

            result = {
                "user_id": str(user.id),
                "organization_id": org_id,
                "org_slug": org_slug,
                "email": SMOKE_EMAIL,
                "access_token": access_token,
                "refresh_token": refresh_token,
            }

        except Exception as e:
            await session.rollback()
            # Output error as JSON for consistency
            print(json.dumps({"error": str(e), "success": False}), file=sys.stderr)
            sys.exit(1)

    # Close engine
    await engine.dispose()

    return result


def main():
    """Entry point for the smoke test seed script."""
    parser = argparse.ArgumentParser(
        description="Seed smoke test organization and user, output JWT tokens"
    )
    parser.add_argument(
        "--adw-id",
        required=True,
        help="ADW identifier for unique org slug (e.g., 'abc123')",
    )
    args = parser.parse_args()

    result = asyncio.run(seed_smoke_test(args.adw_id))

    # Output JSON to stdout
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
