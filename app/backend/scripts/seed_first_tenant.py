#!/usr/bin/env python3
"""
Bootstrap seed script: creates a first tenant with identities and demo data.

THIS IS A BOOTSTRAP, NOT A MAINTENANCE TOOL
-------------------------------------------
Alongside code-owned reference data it creates a super admin at a fixed
ADMIN_EMAIL/ADMIN_PASSWORD, test users with YAML passwords, API keys, and demo
content (announcements, feedback, help centre articles, maintenance history).
Every step is get-or-create keyed on the natural key, so re-running this on a
live deployment recreates the original admin address alongside an admin who has
since changed their email, and re-seeds demo content into a real tenant.

To pick up NEW reference data (a permission, cron definition, notification
template or category, system config key) on an already-deployed environment,
run ``scripts/seed_maintenance.py`` instead: it seeds only the shared,
code-owned reference steps and never touches a user, an API key or demo
content.

The reference-data steps live in ``src/services/organization_seeding.py``
(``REFERENCE_SEED_STEPS``) and are shared by both seeders, so the two cannot
drift. Add new reference data THERE, never to this file.

This script creates:
1. Organizations with full details (from YAML)
2. A super admin user
3. Default global roles and permissions
4. Organization settings (SSO, 2FA)
5. Test users with roles and avatars
6. API keys with rate limits
7. Sample content (announcements, help center, feedback, maintenance history)

Usage: python scripts/seed_first_tenant.py

The seeder is ADDITIVE by default and never deletes anything. The destructive
"truncate every table first" branch is opt-in only:

    python scripts/seed_first_tenant.py --force-clear

and even then it requires an interactive terminal and the target database name
typed back after the resolved host/database are printed. See
``confirm_destructive_clear``.

Environment variables (optional):
- ADMIN_EMAIL: Admin email (default: "super@test.com")
- ADMIN_PASSWORD: Admin password (default: "Admin@123")
- ADMIN_FIRST_NAME: Admin first name (default: "Super")
- ADMIN_LAST_NAME: Admin last name (default: "Admin")
"""

import argparse
import asyncio
import base64
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
from typing import Any, Optional, TextIO
from uuid import UUID

import yaml


# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings
from src.crud.announcement import create_announcement, get_announcements
from src.crud.api_key import create_api_key
from src.crud.feature_flag import (
    create_feature_flag,
    create_override,
    get_feature_flag_by_key,
)
from src.crud.feedback import create_feedback
from src.crud.file import create_file
from src.crud.help_center import (
    create_article,
    create_category,
    create_faq,
    get_categories,
)
from src.crud.maintenance import create_maintenance_history
from src.crud.organization import create_organization, get_organization_by_slug
from src.crud.organization_sso_settings import (
    create_organization_sso_settings,
    get_organization_sso_settings,
)
from src.crud.organization_two_factor_settings import (
    create_settings as create_two_factor_settings,
)
from src.crud.organization_two_factor_settings import (
    get_by_organization_id as get_two_factor_settings,
)
from src.crud.role import get_role_by_name
from src.crud.user import create_user, get_user_by_email
from src.crud.user_notification import create_user_notification
from src.models.api_key_permission import ApiKeyPermission
from src.models.file import MediaUse
from src.models.maintenance_history import MaintenanceStatus
from src.models.user_role import UserRole
from src.services.organization_seeding import (
    get_permissions_by_code,
    seed_reference_cron_jobs,
    seed_reference_notification_categories,
    seed_reference_notification_templates,
    seed_reference_permissions,
    seed_reference_rate_limits,
    seed_reference_role_permissions,
    seed_reference_roles,
    seed_reference_system_config,
    seed_reference_user_types,
)


# Configuration from environment or defaults
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "super@test.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@123")
ADMIN_FIRST_NAME = os.getenv("ADMIN_FIRST_NAME", "Super")
ADMIN_LAST_NAME = os.getenv("ADMIN_LAST_NAME", "Admin")

# Path to seed data files
SEED_DATA_DIR = Path(__file__).parent / "seed_data"


def load_yaml(filename: str) -> Any:
    """Load a YAML file from the seed_data directory."""
    filepath = SEED_DATA_DIR / filename
    with open(filepath) as f:
        return yaml.safe_load(f)


# Export loaded YAML data as module constants for tests to import.
# NOTE: the seeding of these is owned by src/services/organization_seeding.py
# (seed_reference_permissions / seed_reference_role_permissions).
DEFAULT_PERMISSIONS = load_yaml("permissions.yaml")
ROLE_PERMISSIONS = load_yaml("role_permissions.yaml")


def load_avatar_base64() -> str:
    """Load the avatar image as base64."""
    avatar_path = SEED_DATA_DIR / "avatar_1.png"
    with open(avatar_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def seed_organizations(session: AsyncSession) -> dict:
    """Seed organizations from YAML. Returns dict mapping slugs to org objects."""
    orgs_data = load_yaml("organizations.yaml")
    organizations = {}

    for org_data in orgs_data:
        slug = org_data["slug"]
        existing = await get_organization_by_slug(session, slug)

        if existing:
            print(f"  Organization '{slug}' already exists")
            organizations[slug] = existing
        else:
            org = await create_organization(session, org_data)
            print(f"  Created organization: {org_data['name']} ({slug})")
            organizations[slug] = org

    return organizations


async def seed_organization_settings(
    session: AsyncSession, organizations: dict
) -> None:
    """Seed SSO and 2FA settings for organizations from YAML."""
    settings_data = load_yaml("organization_settings.yaml")

    for org_slug, org_settings in settings_data.items():
        org = organizations.get(org_slug)
        if not org:
            print(f"  Warning: Organization '{org_slug}' not found, skipping settings")
            continue

        org_id = str(org.id)

        # SSO Settings
        sso_data = org_settings.get("sso", {})
        existing_sso = await get_organization_sso_settings(session, org_id)
        if existing_sso:
            print(f"  SSO settings for '{org_slug}' already exist")
        else:
            await create_organization_sso_settings(session, org_id, sso_data)
            print(f"  Created SSO settings for '{org_slug}'")

        # 2FA Settings
        two_factor_data = org_settings.get("two_factor", {})
        existing_2fa = await get_two_factor_settings(session, org_id)
        if existing_2fa:
            print(f"  2FA settings for '{org_slug}' already exist")
        else:
            await create_two_factor_settings(session, two_factor_data, org_id)
            print(f"  Created 2FA settings for '{org_slug}'")


async def seed_feature_flags(session: AsyncSession) -> None:
    """Seed default feature flags."""
    flags = [
        {
            "key": "feedback_widget",
            "name": "Feedback Widget",
            "description": "Enable the floating feedback widget for users to submit feedback",
            "default_enabled": False,
        },
        {
            "key": "user_onboarding",
            "name": "User Onboarding",
            "description": "Enable user onboarding flows for new users to complete registration steps",
            "default_enabled": False,
        },
        {
            "key": "api_keys",
            "name": "API Keys",
            "description": "Enable API key management for programmatic access to the platform",
            "default_enabled": True,
        },
        {
            "key": "changelog_enabled",
            "name": "Changelog",
            "description": "Enable the changelog feature to display product updates and release notes",
            "default_enabled": False,
        },
    ]

    for flag_data in flags:
        existing = await get_feature_flag_by_key(session, flag_data["key"])
        if existing:
            print(f"  Feature flag '{flag_data['key']}' already exists")
        else:
            await create_feature_flag(session, flag_data)
            print(f"  Created feature flag '{flag_data['key']}'")


async def enable_feedback_widget(session: AsyncSession, organization_id: str) -> None:
    """Enable the feedback_widget feature flag for the given organization."""
    flag = await get_feature_flag_by_key(session, "feedback_widget")
    if not flag:
        return

    try:
        await create_override(session, str(flag.id), organization_id, enabled=True)
        print("  Enabled feedback_widget for organization")
    except Exception:
        pass  # Override already exists


async def enable_user_onboarding(session: AsyncSession, organization_id: str) -> None:
    """Enable the user_onboarding feature flag for the given organization."""
    flag = await get_feature_flag_by_key(session, "user_onboarding")
    if not flag:
        return

    try:
        await create_override(session, str(flag.id), organization_id, enabled=True)
        print("  Enabled user_onboarding for organization")
    except Exception:
        pass  # Override already exists


async def seed_avatar(
    session: AsyncSession, organization_id: str, user_id: str
) -> str | None:
    """Create avatar file and return its ID."""
    try:
        avatar_path = SEED_DATA_DIR / "avatar_1.png"
        size_bytes = avatar_path.stat().st_size

        # Generate a storage key for the avatar
        import uuid

        storage_key = f"{organization_id}/avatar/{uuid.uuid4()}.png"

        file_record = await create_file(
            session,
            organization_id,
            user_id,
            {
                "original_filename": "avatar_1.png",
                "storage_key": storage_key,
                "content_type": "image/png",
                "size_bytes": size_bytes,
                "category": "image",
                "media_use": MediaUse.AVATAR,
                "status": "ready",
                "storage_provider": "local",
            },
        )
        return str(file_record.id)
    except Exception as e:
        print(f"  Warning: Failed to create avatar: {e}")
        return None


async def seed_test_users(
    session: AsyncSession, organization_id: str, assigned_by_user_id: str
) -> list:
    """Create test users and assign them roles and avatars from YAML."""
    test_users_data = load_yaml("test_users.yaml")
    org_uuid = UUID(organization_id)
    assigned_by_uuid = UUID(assigned_by_user_id)
    created_users = []

    # Create avatar once for all test users
    avatar_file_id = await seed_avatar(session, organization_id, assigned_by_user_id)

    for user_config in test_users_data:
        email = user_config["email"]
        role_name = user_config["role"]

        existing_user = await get_user_by_email(session, email, organization_id)

        if existing_user:
            print(f"  User '{email}' already exists")
            user = existing_user
            # Update avatar if not set
            if avatar_file_id and not user.avatar_file_id:
                user.avatar_file_id = UUID(avatar_file_id)
                await session.commit()
        else:
            user_data = {
                "email": email,
                "password": user_config["password"],
                "email_verified": True,
                "is_admin": False,
                "first_name": user_config["first_name"],
                "last_name": user_config["last_name"],
            }
            user = await create_user(session, user_data, organization_id)
            # Set avatar
            if avatar_file_id:
                user.avatar_file_id = UUID(avatar_file_id)
                await session.commit()
            print(f"  Created user '{email}' with avatar")

        role = await get_role_by_name(session, role_name)
        if not role:
            print(f"  Warning: Role '{role_name}' not found")
            created_users.append({"user": user, "role": None})
            continue

        existing_role_result = await session.execute(
            select(UserRole).where(
                UserRole.user_id == user.id,
                UserRole.role_id == role.id,
                UserRole.organization_id == org_uuid,
                UserRole.deleted_time.is_(None),
            )
        )

        if not existing_role_result.scalars().first():
            user_role = UserRole(
                user_id=user.id,
                role_id=role.id,
                assigned_by=assigned_by_uuid,
                organization_id=org_uuid,
            )
            session.add(user_role)
            await session.commit()
            print(f"  Assigned role '{role_name}' to '{email}'")

        created_users.append({"user": user, "role": role_name})

    return created_users


async def seed_api_keys(
    session: AsyncSession, organizations: dict, admin_user_id: str, permissions: dict
) -> None:
    """Seed sample API keys from YAML."""
    api_keys_data = load_yaml("api_keys.yaml")

    for key_data in api_keys_data:
        org_slug = key_data["organization_slug"]
        org = organizations.get(org_slug)
        if not org:
            print(f"  Warning: Organization '{org_slug}' not found for API key")
            continue

        org_id = str(org.id)
        name = key_data["name"]

        # Calculate expiry
        expires_at = None
        if key_data.get("expires_in_days"):
            expires_at = datetime.now(timezone.utc) + timedelta(
                days=key_data["expires_in_days"]
            )

        try:
            api_key, full_key = await create_api_key(
                session,
                name=name,
                organization_id=org_id,
                created_by=admin_user_id,
                expires_at=expires_at,
            )

            # Assign permissions
            perm_codes = key_data.get("permissions", [])
            for perm_code in perm_codes:
                perm = permissions.get(perm_code)
                if perm:
                    api_key_perm = ApiKeyPermission(
                        organization_id=UUID(org_id),
                        api_key_id=api_key.id,
                        permission_id=perm.id,
                    )
                    session.add(api_key_perm)

            await session.commit()
            print(f"  Created API key '{name}' (prefix: {api_key.prefix}...)")
            print(f"    Full key (save this!): {full_key}")
        except ValueError:
            print(f"  API key '{name}' already exists")


async def seed_maintenance_history(session: AsyncSession, admin_user_id: str) -> int:
    """Seed sample maintenance history from YAML."""

    history_data = load_yaml("maintenance_history.yaml")
    created = 0

    for entry in history_data:
        now = datetime.now(timezone.utc)
        days_ago = entry.get("scheduled_start_days_ago", 0)
        duration_hours = entry.get("duration_hours", 1)

        scheduled_start = now - timedelta(days=days_ago)
        scheduled_end = scheduled_start + timedelta(hours=duration_hours)

        actual_start = None
        actual_end = None
        if entry["status"] == "completed":
            actual_start = scheduled_start
            actual_end = scheduled_end

        try:
            history = await create_maintenance_history(
                session,
                scheduled_start=scheduled_start,
                scheduled_end=scheduled_end,
                actual_start=actual_start,
                message=entry["message"],
                started_by_user_id=admin_user_id,
                status=MaintenanceStatus(entry["status"]),
            )
            # Set actual_end directly on the model (not supported by create function)
            if actual_end:
                history.actual_end = actual_end
                await session.commit()
            created += 1
        except Exception as e:
            print(f"  Warning: Failed to create maintenance entry: {e}")

    print(f"  Created {created} maintenance history entries")
    return created


async def seed_announcement(
    session: AsyncSession, organization_id: str, created_by_id: str
) -> None:
    """Seed a sample announcement for the organization."""
    existing, _ = await get_announcements(session, organization_id, limit=10)
    if existing:
        return

    await create_announcement(
        session,
        {
            "title": "Warning",
            "body": "Here be dragons! Go to the Help Center to find your way around.",
            "priority": "normal",
            "cta_text": "Go to Help Center",
            "cta_url": "/help-center",
            "is_dismissible": True,
        },
        organization_id,
        created_by_id,
    )
    print("  Created sample announcement")


async def seed_user_notification(
    session: AsyncSession, organization_id: str, user_id: str
) -> None:
    """Seed an onboarding notification for a user."""
    await create_user_notification(
        session,
        organization_id=organization_id,
        user_id=user_id,
        title="Complete Your Onboarding",
        body="Welcome and thank you for registering. Please complete your onboarding here.",
        link="/settings/account/profile",
    )


async def seed_feedback_data(
    session: AsyncSession,
    organization_id: str,
    user_ids: list[str],
    admin_user_id: str,
) -> None:
    """Seed sample feedback data from YAML with attachments and conversations."""
    from src.crud.feedback import (
        create_feedback_attachment,
        create_feedback_reply,
    )

    if not user_ids:
        return

    feedbacks_data = load_yaml("feedback_samples.yaml")
    created_count = 0

    for idx, feedback_data in enumerate(feedbacks_data):
        user_id = user_ids[idx % len(user_ids)]

        # Extract special fields before creating feedback
        has_attachment = feedback_data.pop("has_attachment", False)
        attachment_file = feedback_data.pop("attachment_file", None)
        conversation = feedback_data.pop("conversation", [])

        try:
            feedback = await create_feedback(
                session, feedback_data, organization_id, user_id
            )
            created_count += 1

            # Add attachment if specified
            if has_attachment and attachment_file:
                attachment_path = SEED_DATA_DIR / attachment_file
                if attachment_path.exists():
                    # In a real app this would be an S3 path, but for seeding we use a placeholder
                    file_size = attachment_path.stat().st_size
                    await create_feedback_attachment(
                        session,
                        feedback_id=str(feedback.id),
                        organization_id=organization_id,
                        file_path=f"feedback/{feedback.id}/{attachment_file}",
                        file_type="image/png",
                        file_size_bytes=file_size,
                    )
                    print(
                        f"  Added attachment to feedback: {feedback_data.get('subject', 'Unknown')[:30]}"
                    )

            # Add conversation replies
            for reply in conversation:
                is_admin = reply.get("is_admin", False)
                reply_user_id = admin_user_id if is_admin else user_id
                await create_feedback_reply(
                    session,
                    feedback_id=str(feedback.id),
                    organization_id=organization_id,
                    user_id=reply_user_id,
                    message=reply["message"],
                    is_admin_reply=is_admin,
                )

            if conversation:
                print(
                    f"  Added {len(conversation)} replies to feedback: {feedback_data.get('subject', 'Unknown')[:30]}"
                )

        except Exception as e:
            # Restore popped fields for error logging
            print(f"  Warning: Failed to create feedback: {e}")

    print(f"  Created {created_count} feedback items")


async def seed_help_center(
    session: AsyncSession, organization_id: str, created_by_id: str
) -> None:
    """Seed Help Center categories, FAQs, and articles from YAML."""
    existing_categories, _ = await get_categories(session, limit=1)
    if existing_categories:
        print("  Help Center content already exists")
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

    print(
        f"  Created {len(categories_data)} categories, {len(faqs_data)} FAQs, {len(articles_data)} articles"
    )


def describe_database_target(database_url: str) -> tuple[str, str]:
    """Return ``(host:port, database_name)`` for a SQLAlchemy URL.

    Used to show the operator exactly which server is about to be truncated;
    the URL itself is never printed because it carries the password.
    """
    url = make_url(database_url)
    host = f"{url.host or 'localhost'}:{url.port or 5432}"
    return host, url.database or "<unknown>"


def confirm_destructive_clear(
    database_url: str,
    *,
    force_clear: bool,
    input_fn: Callable[[str], str] = input,
    stdin: Optional[TextIO] = None,
) -> bool:
    """Decide whether the TRUNCATE-everything branch may run.

    ``clear_all_tables`` is a ``TRUNCATE ... CASCADE`` over every table in the
    schema, aimed at whatever ``config.json`` happens to point at - which on a
    developer machine is very often a shared or staging database. A ``[y/N]``
    prompt is not a safeguard: a stray keypress, a mistyped shell history entry
    or a piped ``yes`` satisfies it, and none of those leave a trace.

    Three gates, all of which must pass:

    1. ``--force-clear`` on the command line. The destructive branch is not
       merely defaulted off, it is *unreachable* without the flag - the prompt
       is never even shown - so the ordinary ``python scripts/seed_first_tenant.py``
       cannot destroy anything no matter what is typed or piped at it. A flag
       (rather than an env var) was chosen deliberately: it is per-invocation
       and visible in shell history, whereas an exported env var persists for a
       whole shell session and silently arms every later run, which is exactly
       the failure mode we are trying to remove.
    2. An interactive terminal. This blocks ``yes | ...``, ``echo x | ...`` and
       CI jobs, which are the ways an automated pipeline could stumble into it.
    3. The operator types the target database name back, after the resolved
       host and database name have been printed. This forces them to *read*
       which database they are about to erase rather than acknowledge a prompt
       reflexively, and unlike a fixed word ("yes", "DELETE") it cannot be
       memorised or scripted once and reused against the wrong target.

    A name-based heuristic ("refuse unless the database is called dev/test")
    was rejected on purpose: this is a template that gets forked, and forks name
    their databases whatever they like. Such a check gives false confidence when
    it passes and blocks legitimate use when it fails.

    Returns:
        True when every gate passed and the caller may truncate.
        False when ``--force-clear`` was not given (the ordinary path: seed
        additively, destroy nothing).

    Raises:
        SystemExit: when ``--force-clear`` was given but a gate failed. The
            operator explicitly asked for a destructive run and did not confirm
            it, so quietly falling through to a normal seed would not be what
            they asked for either.
    """
    if not force_clear:
        return False

    host, database = describe_database_target(database_url)

    print()
    print("!" * 60)
    print("DESTRUCTIVE: --force-clear will TRUNCATE every table, CASCADE.")
    print(f"  host:     {host}")
    print(f"  database: {database}")
    print("!" * 60)

    stream = stdin if stdin is not None else sys.stdin
    if not (stream is not None and hasattr(stream, "isatty") and stream.isatty()):
        print(
            "Refusing to clear: --force-clear requires an interactive terminal "
            "(piped or non-TTY input cannot confirm a destructive operation)."
        )
        raise SystemExit(2)

    typed = input_fn(f'Type the database name "{database}" to confirm: ').strip()
    if typed != database:
        print("Database name did not match. Nothing was cleared; aborting.")
        raise SystemExit(2)

    return True


async def clear_all_tables(session: AsyncSession) -> None:
    """Truncate all application tables (preserving alembic_version)."""
    # Get all table names except alembic_version
    result = await session.execute(
        text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename != 'alembic_version'"
        )
    )
    tables = [row[0] for row in result.fetchall()]

    if not tables:
        print("  No tables to clear.")
        return

    # Truncate all tables in one statement with CASCADE
    table_list = ", ".join(f'"{t}"' for t in tables)
    await session.execute(text(f"TRUNCATE TABLE {table_list} CASCADE"))
    await session.commit()
    print(f"  Cleared {len(tables)} tables.")


async def seed_first_tenant(force_clear: bool = False) -> None:
    """Main seed function.

    Args:
        force_clear: Opt-in to the destructive TRUNCATE branch. Without it the
            seeder is purely additive and never prompts - see
            :func:`confirm_destructive_clear`.
    """
    print("=" * 60)
    print("Seeding Database")
    print("=" * 60)
    print()

    # Use direct connection (bypassing PgBouncer) for seeding
    engine = create_async_engine(
        settings.DATABASE_URL_DIRECT,
        poolclass=NullPool,
        connect_args={
            "statement_cache_size": 100,
            "command_timeout": 60,
        },
    )
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        try:
            # Destructive branch: only reachable with --force-clear, an
            # interactive terminal, and the target database name typed back.
            if confirm_destructive_clear(
                settings.DATABASE_URL_DIRECT, force_clear=force_clear
            ):
                print("Clearing all tables...")
                await clear_all_tables(session)
                print()

            # Step 1: Create organizations
            print("Creating organizations...")
            organizations = await seed_organizations(session)
            default_org = organizations.get("default-org")
            if not default_org:
                raise ValueError("Default organization not found")
            default_org_id = str(default_org.id)
            print()

            # Step 2: Seed global roles (shared reference data)
            print("Seeding global roles...")
            print(f"  Roles: {(await seed_reference_roles(session)).summary()}")
            print()

            # Notification categories are seeded before anything that dispatches
            # a notification: without them every category_code the app sends
            # under resolves to None, and the whole category-preference layer
            # (mandatory categories, per-category channel opt-outs) is inert.
            print("Seeding notification categories...")
            categories_result = await seed_reference_notification_categories(session)
            print(f"  Notification categories: {categories_result.summary()}")
            print()

            # Step 3: Seed global permissions
            print("Seeding global permissions...")
            print(
                f"  Permissions: {(await seed_reference_permissions(session)).summary()}"
            )
            permissions = await get_permissions_by_code(session)
            print()

            # Step 4: Seed rate limits
            print("Seeding API key rate limits...")
            print(
                f"  Rate limits: {(await seed_reference_rate_limits(session)).summary()}"
            )
            print()

            # Step 5: Create super admin user
            print(f"Creating super admin user: {ADMIN_EMAIL}")
            existing_admin = await get_user_by_email(
                session, ADMIN_EMAIL, default_org_id
            )
            if existing_admin:
                print(f"  User '{ADMIN_EMAIL}' already exists")
                admin_user = existing_admin
            else:
                admin_user = await create_user(
                    session,
                    {
                        "email": ADMIN_EMAIL,
                        "password": ADMIN_PASSWORD,
                        "email_verified": True,
                        "is_admin": True,
                        "first_name": ADMIN_FIRST_NAME,
                        "last_name": ADMIN_LAST_NAME,
                    },
                    default_org_id,
                )
                print(f"  Super admin created (ID: {admin_user.id})")
            admin_user_id = str(admin_user.id)
            print()

            # Step 6: Seed organization settings (SSO, 2FA)
            print("Seeding organization settings (SSO, 2FA)...")
            await seed_organization_settings(session, organizations)
            print()

            # Step 7: Assign permissions to global roles
            # NOTE: this step restores grants an admin revoked - see the warning
            # on seed_reference_role_permissions.
            print("Assigning permissions to global roles...")
            role_permission_result = await seed_reference_role_permissions(
                session, granted_by=admin_user_id
            )
            print(f"  Role permissions: {role_permission_result.summary()}")
            print()

            # Step 8: Seed feature flags
            print("Seeding feature flags...")
            await seed_feature_flags(session)
            for org in organizations.values():
                await enable_feedback_widget(session, str(org.id))
                await enable_user_onboarding(session, str(org.id))
            print()

            # Step 9: Seed user types and onboarding steps
            print("Seeding user types and onboarding steps...")
            user_type_result = await seed_reference_user_types(session)
            print(f"  User types + onboarding steps: {user_type_result.summary()}")
            print()

            # Step 10: Create test users with roles and avatars
            print("Creating test users with roles and avatars...")
            test_users = await seed_test_users(session, default_org_id, admin_user_id)
            print()

            # Step 11: Seed API keys
            print("Seeding API keys...")
            await seed_api_keys(session, organizations, admin_user_id, permissions)
            print()

            # Step 12: Seed maintenance history
            print("Seeding maintenance history...")
            await seed_maintenance_history(session, admin_user_id)
            print()

            # Step 13: Seed sample announcement
            print("Seeding sample content...")
            await seed_announcement(session, default_org_id, admin_user_id)

            # Seed user notification for test user
            test_user = next(
                (u for u in test_users if u["user"].email == "user@test.com"), None
            )
            if test_user:
                await seed_user_notification(
                    session, default_org_id, str(test_user["user"].id)
                )

            # Seed feedback
            all_user_ids = [admin_user_id] + [str(u["user"].id) for u in test_users]
            await seed_feedback_data(
                session, default_org_id, all_user_ids, admin_user_id
            )
            print()

            # Step 14: Seed Help Center content
            print("Seeding Help Center content...")
            await seed_help_center(session, default_org_id, admin_user_id)
            print()

            # Step 15: Seed notification templates
            print("Seeding notification templates...")
            template_result = await seed_reference_notification_templates(session)
            print(f"  Notification templates: {template_result.summary()}")
            print()

            # Step 16: Seed cron jobs
            print("Seeding cron jobs...")
            print(f"  Cron jobs: {(await seed_reference_cron_jobs(session)).summary()}")
            print()

            # Step 17: Seed system config (for cron job configuration)
            print("Seeding system config...")
            config_result = await seed_reference_system_config(session)
            print(f"  System config: {config_result.summary()}")
            print()

            # Summary
            print("=" * 60)
            print("Seeding completed successfully!")
            print("=" * 60)
            print("\nOrganizations:")
            for slug, org in organizations.items():
                print(f"  - {org.name} ({slug})")

            print(f"\nSuper Admin: {admin_user.email} / {ADMIN_PASSWORD}")
            print("\nTest users (password: Admin@123):")
            for u in test_users:
                print(f"  - {u['user'].email} ({u['role']})")

        except Exception as e:
            await session.rollback()
            print(f"\nError seeding: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)

    await engine.dispose()


def main():
    """Entry point for the seed script."""
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap seed: creates the first tenant, a super admin, "
            "reference data and demo content. Additive by default."
        )
    )
    parser.add_argument(
        "--force-clear",
        action="store_true",
        help=(
            "DESTRUCTIVE. Opt in to truncating every table before seeding. "
            "Still requires an interactive terminal and typing the target "
            "database name back. Without this flag nothing is ever deleted."
        ),
    )
    args = parser.parse_args()
    asyncio.run(seed_first_tenant(force_clear=args.force_clear))


if __name__ == "__main__":
    main()
