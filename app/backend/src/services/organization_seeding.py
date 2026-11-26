"""
Organization seeding service for creating default global roles, permissions and
notification categories.
Since roles, permissions and system notification categories are global
(system-wide), this seeds them once if they don't exist.
Migrated to async patterns.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import yaml  # type: ignore[import-untyped]

from src.crud.api_key_rate_limit import (
    create_rate_limit,
    get_rate_limit_by_permission,
)
from src.crud.cron_job import create_cron_job, get_cron_job_by_code
from src.crud.notification_category import (
    create_system_category,
    get_system_categories,
)
from src.crud.onboarding_step import create as create_onboarding_step
from src.crud.onboarding_step import get_all_for_user_type
from src.crud.permission import create_permission, get_permission_by_code
from src.crud.role import create_role, get_role_by_name
from src.crud.system_config import get_system_config_by_key, update_system_config
from src.crud.user_type import create as create_user_type
from src.crud.user_type import get_by_code as get_user_type_by_code
from src.logger.logger import Logger
from src.models.notification_template import NotificationTemplate
from src.models.permission import Permission
from src.models.role import Role
from src.models.role_permission import RolePermission


DEFAULT_ROLES = [
    {
        "name": "owner",
        "description": "Organization owner with full access. Cannot be removed from organization.",
        "is_default_on_registration": False,
    },
    {
        "name": "admin",
        "description": "Can manage users, roles, and organization settings.",
        "is_default_on_registration": False,
    },
    {
        "name": "member",
        "description": "Standard team member with access to organization resources.",
        "is_default_on_registration": True,
    },
    {
        "name": "viewer",
        "description": "Read-only access to organization resources.",
        "is_default_on_registration": False,
    },
    {
        "name": "tester",
        "description": "QA tester with feature flag bypass to test unreleased features.",
        "is_default_on_registration": False,
    },
    {
        # Freespace back office (D16): view everything, send test pushes.
        "name": "operator",
        "description": "Freespace operator: views all sites and events and sends test pushes.",
        "is_default_on_registration": False,
    },
]


DEFAULT_PERMISSIONS = [
    # API Keys permissions
    {
        "code": "api_keys:read",
        "name": "API Keys Read",
        "description": "View API keys for the organization",
    },
    {
        "code": "api_keys:write",
        "name": "API Keys Write",
        "description": "Create and update API keys for the organization",
    },
    {
        "code": "api_keys:delete",
        "name": "API Keys Delete",
        "description": "Revoke API keys for the organization",
    },
    # Users permissions
    {
        "code": "users:read",
        "name": "Users Read",
        "description": "View users in the organization",
    },
    {
        "code": "users:write",
        "name": "Users Write",
        "description": "Create and update users in the organization",
    },
    {
        "code": "users:delete",
        "name": "Users Delete",
        "description": "Remove users from the organization",
    },
    # Roles permissions
    {
        "code": "roles:read",
        "name": "Roles Read",
        "description": "View roles and their permissions",
    },
    {
        "code": "roles:write",
        "name": "Roles Write",
        "description": "Create and update roles",
    },
    {
        "code": "roles:delete",
        "name": "Roles Delete",
        "description": "Delete roles",
    },
    # Announcements permissions
    {
        "code": "announcements:read",
        "name": "Announcements Read",
        "description": "View announcements in the organization",
    },
    {
        "code": "announcements:write",
        "name": "Announcements Write",
        "description": "Create and update announcements",
    },
    {
        "code": "announcements:delete",
        "name": "Announcements Delete",
        "description": "Delete announcements",
    },
    # Changelog permissions
    {
        "code": "changelog:write",
        "name": "Changelog Write",
        "description": "Create, update, and delete changelog entries",
    },
    # Two-Factor Authentication permissions
    {
        "code": "two_factor:read",
        "name": "Two-Factor Read",
        "description": "View two-factor authentication settings",
    },
    {
        "code": "two_factor:write",
        "name": "Two-Factor Write",
        "description": "Manage two-factor authentication settings",
    },
    {
        "code": "two_factor:delete",
        "name": "Two-Factor Delete",
        "description": "Delete two-factor authentication settings",
    },
]


# Notification categories seeded as SYSTEM categories (organization_id=None) so
# every organization resolves them through the crud fallback without per-org rows.
#
# The codes here MUST cover every `category_code=` value dispatched from src/.
# preference_checker._get_category() returns None for an unknown code, which
# silently disables both the mandatory-category bypass and the per-category
# channel guard for that notification.
DEFAULT_NOTIFICATION_CATEGORIES = [
    {
        "code": "account",
        "name": "Account & Security",
        "description": (
            "Account, security and administrative notices such as password "
            "changes, sign-in alerts and impersonation transparency notices."
        ),
        "default_enabled": True,
        # Transactional / security critical - users must not be able to opt out.
        "user_configurable": False,
        "display_order": 10,
    },
    {
        "code": "phone_verification",
        "name": "Phone Verification",
        "description": (
            "One-time codes sent to verify a phone number. Required to complete "
            "verification, so it cannot be disabled."
        ),
        "default_enabled": True,
        # Transactional - the user explicitly asked for this code.
        "user_configurable": False,
        "display_order": 20,
    },
    {
        "code": "onboarding",
        "name": "Onboarding",
        "description": (
            "Onboarding progress, submission and review notifications for new "
            "users and their administrators."
        ),
        "default_enabled": True,
        "user_configurable": True,
        "display_order": 30,
    },
    {
        "code": "marketing",
        "name": "Marketing & Updates",
        "description": (
            "Product news, promotions and other non-essential messages. "
            "Opt-out by default policy: enabled initially, always user-configurable."
        ),
        "default_enabled": True,
        # Must remain user-configurable - this is the unsubscribe target.
        "user_configurable": True,
        "display_order": 40,
    },
    {
        "code": "site_operations",
        "name": "Site Operations Alerts",
        "description": (
            "Freespace operator alerts: a site stopped or resumed sending data, "
            "push credentials were rejected, the device ceiling was reached or "
            "ingest requests are being rejected (BF-82)."
        ),
        "default_enabled": True,
        # Operational alerts for permission holders - not opt-out.
        "user_configurable": False,
        "display_order": 50,
    },
]


async def seed_default_roles(session: AsyncSession):
    """
    Create default global roles if they don't exist.
    Roles are system-wide, so this only needs to run once.

    Args:
        session: Async SQLAlchemy session

    Returns:
        List of created role objects (empty if roles already exist)
    """
    created_roles = []

    for role_data in DEFAULT_ROLES:
        try:
            # Check if role already exists (roles are global, unique by name)
            existing_role = await get_role_by_name(session, str(role_data["name"]))
            if existing_role:
                Logger.info(f"Global role '{role_data['name']}' already exists")
                continue

            role = await create_role(
                session=session,
                request={
                    "name": role_data["name"],
                    "description": role_data["description"],
                    "is_default_on_registration": role_data.get(
                        "is_default_on_registration", False
                    ),
                },
            )
            created_roles.append(role)
            Logger.info(f"Created global role '{role_data['name']}'")
        except Exception as e:
            Logger.error(
                f"Failed to create global role '{role_data['name']}': {str(e)}"
            )
            # Continue creating other roles even if one fails
            continue

    if created_roles:
        Logger.info(f"Seeded {len(created_roles)} default global roles")
    else:
        Logger.info("All default global roles already exist")

    return created_roles


def get_default_role_names():
    """
    Get the list of default role names that are created globally.

    Returns:
        List of role name strings
    """
    return [role["name"] for role in DEFAULT_ROLES]


async def seed_default_permissions(session: AsyncSession):
    """
    Create default global permissions if they don't exist.
    Permissions are system-wide, so this only needs to run once.

    Args:
        session: Async SQLAlchemy session

    Returns:
        List of created permission objects (empty if permissions already exist)
    """
    created_permissions = []

    for perm_data in DEFAULT_PERMISSIONS:
        try:
            # Check if permission already exists (permissions are global, unique by code)
            existing_perm = await get_permission_by_code(session, perm_data["code"])
            if existing_perm:
                Logger.info(f"Global permission '{perm_data['code']}' already exists")
                continue

            permission = await create_permission(
                session=session,
                code=perm_data["code"],
                name=perm_data["name"],
                description=perm_data.get("description"),
            )
            created_permissions.append(permission)
            Logger.info(f"Created global permission '{perm_data['code']}'")
        except Exception as e:
            Logger.error(
                f"Failed to create global permission '{perm_data['code']}': {str(e)}"
            )
            # Continue creating other permissions even if one fails
            continue

    if created_permissions:
        Logger.info(f"Seeded {len(created_permissions)} default global permissions")
    else:
        Logger.info("All default global permissions already exist")

    return created_permissions


def get_default_permission_codes():
    """
    Get the list of default permission codes that are created globally.

    Returns:
        List of permission code strings
    """
    return [perm["code"] for perm in DEFAULT_PERMISSIONS]


async def seed_default_notification_categories(session: AsyncSession):
    """
    Create default system notification categories if they don't exist.

    Categories are seeded with organization_id=None (system scope), which
    get_category_by_code() falls back to for every organization. Seeding them
    once is therefore enough for the whole platform.

    Without these rows preference_checker._get_category() returns None for
    every code the application dispatches under, which means:
      - the mandatory-category bypass (user_configurable=False) never fires, and
      - the per-category channel guard never fires, so a user who has opted out
        of a category still receives that category's notifications.

    Args:
        session: Async SQLAlchemy session

    Returns:
        List of created NotificationCategory objects (empty if all exist)
    """
    created_categories = []

    existing_categories, _ = await get_system_categories(session, limit=1000)
    existing_codes = {category.code for category in existing_categories}

    for category_data in DEFAULT_NOTIFICATION_CATEGORIES:
        code = str(category_data["code"])
        try:
            if code in existing_codes:
                Logger.info(f"System notification category '{code}' already exists")
                continue

            category = await create_system_category(
                session=session,
                category_data=dict(category_data),
            )
            created_categories.append(category)
            Logger.info(f"Created system notification category '{code}'")
        except Exception as e:
            Logger.error(
                f"Failed to create system notification category '{code}': {str(e)}"
            )
            # Continue creating other categories even if one fails
            continue

    if created_categories:
        Logger.info(f"Seeded {len(created_categories)} default notification categories")
    else:
        Logger.info("All default notification categories already exist")

    return created_categories


def get_default_notification_category_codes():
    """
    Get the list of default notification category codes seeded globally.

    Returns:
        List of category code strings
    """
    return [str(category["code"]) for category in DEFAULT_NOTIFICATION_CATEGORIES]


# =============================================================================
# SHARED CODE-OWNED REFERENCE DATA
# =============================================================================
#
# Everything below this line is *reference data owned by the code*: it is a
# property of the repository, not of a particular deployment. It is seeded by
# BOTH seeders:
#
#   scripts/seed_first_tenant.py  - bootstrap (fresh database: reference data +
#                                   identities + demo content)
#   scripts/seed_maintenance.py   - maintenance (live deployment: reference data
#                                   ONLY, additive, safe to re-run)
#
# NEW REFERENCE DATA (a permission, a cron definition, a notification template
# or category, a system config key, a rate limit, a user type) MUST be added
# here - to the shared function or the YAML file it reads - never to
# seed_first_tenant.py alone. A key only the bootstrap seeder knows about can
# never reach an already-deployed environment.
#
# Every function below is additive get-or-create: an existing row is never
# updated or deleted, so admin-edited values survive a re-run.

# YAML seed data lives next to the scripts that historically owned it.
SEED_DATA_DIR = Path(__file__).resolve().parents[2] / "scripts" / "seed_data"


def load_seed_yaml(filename: str) -> Any:
    """Load a YAML file from the shared seed_data directory."""
    with open(SEED_DATA_DIR / filename) as handle:
        return yaml.safe_load(handle)


@dataclass
class SeedResult:
    """Per-step outcome of a reference-data seeding function.

    ``updated`` exists for reporting symmetry only: the reference-data seeders
    are additive and never modify an existing row, so it stays at 0 unless a
    future step deliberately reconciles a row it owns.
    """

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.created} created, {self.updated} updated, "
            f"{self.unchanged} unchanged"
        )


async def get_permissions_by_code(session: AsyncSession) -> dict[str, Permission]:
    """Return every live permission keyed by its code."""
    result = await session.execute(
        select(Permission).where(Permission.deleted_time.is_(None))
    )
    return {perm.code: perm for perm in result.scalars().all()}


async def seed_reference_roles(session: AsyncSession) -> SeedResult:
    """Seed the global role definitions (DEFAULT_ROLES)."""
    created = await seed_default_roles(session)
    await session.commit()
    return SeedResult(created=len(created), unchanged=len(DEFAULT_ROLES) - len(created))


async def seed_reference_permissions(session: AsyncSession) -> SeedResult:
    """Seed every permission code the application checks.

    Two sources, deliberately unioned:
      - ``DEFAULT_PERMISSIONS`` in this module (code constants), and
      - ``scripts/seed_data/permissions.yaml``.

    Neither set is a superset of the other, and ``require_permission(...)``
    guards exist for codes in both, so both must be seeded.
    """
    created = len(await seed_default_permissions(session))
    unchanged = len(DEFAULT_PERMISSIONS) - created

    for perm_data in load_seed_yaml("permissions.yaml"):
        existing = await get_permission_by_code(session, perm_data["code"])
        if existing:
            unchanged += 1
            continue
        await create_permission(
            session,
            code=perm_data["code"],
            name=perm_data["name"],
            description=perm_data.get("description"),
            display_order=perm_data.get("display_order", 0),
        )
        created += 1

    await session.commit()
    return SeedResult(created=created, unchanged=unchanged)


async def seed_reference_role_permissions(
    session: AsyncSession, granted_by: Any = None
) -> SeedResult:
    """Grant permissions to the global roles from ``role_permissions.yaml``.

    WARNING - THIS STEP IS NOT PURELY ADDITIVE IN EFFECT. Revoking a permission
    from a role soft-deletes the grant (``deleted_time`` is set) and this step
    matches on ``deleted_time IS NULL``, so a grant an administrator
    deliberately removed from a system role is RE-CREATED on the next run. It
    stays in the default run because a deploy that adds a permission needs its
    grants applied; use ``--skip role_permissions`` on a deployment whose
    system roles have been hand-tuned.
    """
    role_permissions_data = load_seed_yaml("role_permissions.yaml")
    permissions = await get_permissions_by_code(session)

    result = await session.execute(select(Role).where(Role.deleted_time.is_(None)))
    roles = {role.name: role for role in result.scalars().all()}

    granted_by_id: Any = granted_by
    if isinstance(granted_by, str):
        granted_by_id = UUID(granted_by)

    outcome = SeedResult()

    for role_name, perm_codes in role_permissions_data.items():
        role = roles.get(role_name)
        if not role:
            outcome.notes.append(f"role '{role_name}' not found - skipped")
            continue

        for perm_code in perm_codes or []:
            permission = permissions.get(perm_code)
            if not permission:
                outcome.notes.append(
                    f"permission '{perm_code}' not found for role '{role_name}'"
                )
                continue

            existing = await session.execute(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == permission.id,
                    RolePermission.deleted_time.is_(None),
                )
            )
            if existing.scalars().first():
                outcome.unchanged += 1
                continue

            session.add(
                RolePermission(
                    role_id=role.id,
                    permission_id=permission.id,
                    granted_by=granted_by_id,
                )
            )
            outcome.created += 1

    await session.commit()
    return outcome


async def seed_reference_rate_limits(session: AsyncSession) -> SeedResult:
    """Seed the per-permission API key rate limits from YAML."""
    outcome = SeedResult()

    for limit_data in load_seed_yaml("rate_limits.yaml"):
        perm_code = limit_data["permission_code"]
        existing = await get_rate_limit_by_permission(session, perm_code)
        if existing:
            outcome.unchanged += 1
            continue

        try:
            await create_rate_limit(
                session,
                permission_code=perm_code,
                requests_per_minute=limit_data["requests_per_minute"],
                burst_limit=limit_data["burst_limit"],
            )
            outcome.created += 1
        except Exception as exc:  # pragma: no cover - defensive
            outcome.notes.append(f"rate limit '{perm_code}' failed: {exc}")

    await session.commit()
    return outcome


async def seed_reference_user_types(session: AsyncSession) -> SeedResult:
    """Seed user types and their onboarding steps from YAML."""
    user_types_data = load_seed_yaml("user_types.yaml")
    onboarding_steps_data = load_seed_yaml("onboarding_steps.yaml") or {}

    outcome = SeedResult()
    user_type_ids: dict[str, str] = {}

    for type_data in user_types_data:
        existing = await get_user_type_by_code(session, type_data["code"])
        if existing:
            user_type_ids[type_data["code"]] = str(existing.id)
            outcome.unchanged += 1
            continue
        user_type = await create_user_type(session, dict(type_data))
        user_type_ids[type_data["code"]] = str(user_type.id)
        outcome.created += 1

    for user_type_code, steps in onboarding_steps_data.items():
        user_type_id = user_type_ids.get(user_type_code)
        if not user_type_id:
            outcome.notes.append(f"user type '{user_type_code}' not found for steps")
            continue

        existing_steps = await get_all_for_user_type(session, user_type_id)
        existing_codes = {step.code for step in existing_steps}

        for step_data in steps or []:
            if step_data["code"] in existing_codes:
                outcome.unchanged += 1
                continue
            payload = dict(step_data)
            payload["user_type_id"] = user_type_id
            payload["validation_rules"] = payload.get("validation_rules", {})
            await create_onboarding_step(session, payload)
            outcome.created += 1

    await session.commit()
    return outcome


async def seed_reference_notification_categories(session: AsyncSession) -> SeedResult:
    """Seed the system notification categories."""
    created = await seed_default_notification_categories(session)
    await session.commit()
    return SeedResult(
        created=len(created),
        unchanged=len(DEFAULT_NOTIFICATION_CATEGORIES) - len(created),
    )


async def seed_reference_notification_templates(session: AsyncSession) -> SeedResult:
    """Seed the system-wide (organization_id IS NULL) notification templates."""
    outcome = SeedResult()

    for template_data in load_seed_yaml("notification_templates.yaml"):
        code = template_data["code"]
        channel = template_data["channel"]

        existing = await session.execute(
            select(NotificationTemplate).where(
                NotificationTemplate.code == code,
                NotificationTemplate.channel == channel,
                NotificationTemplate.organization_id.is_(None),
                NotificationTemplate.deleted_time.is_(None),
            )
        )
        if existing.scalars().first():
            outcome.unchanged += 1
            continue

        now = datetime.now(timezone.utc)
        session.add(
            NotificationTemplate(
                organization_id=None,
                code=code,
                name=template_data["name"],
                description=template_data.get("description"),
                channel=channel,
                subject=template_data.get("subject"),
                body_text=template_data["body_text"],
                body_html=template_data.get("body_html"),
                variables=template_data.get("variables", []),
                is_active=template_data.get("is_active", True),
                created_time=now,
                updated_time=now,
            )
        )
        await session.flush()
        outcome.created += 1

    await session.commit()
    return outcome


async def seed_reference_cron_jobs(session: AsyncSession) -> SeedResult:
    """Seed the system-wide cron job definitions ARQ reads at dispatch time."""
    outcome = SeedResult()

    for job_data in load_seed_yaml("cron_jobs.yaml"):
        existing = await get_cron_job_by_code(
            session, job_data["code"], organization_id=None
        )
        if existing:
            outcome.unchanged += 1
            continue
        await create_cron_job(session, dict(job_data), organization_id=None)
        outcome.created += 1

    await session.commit()
    return outcome


async def seed_reference_system_config(session: AsyncSession) -> SeedResult:
    """Seed the system configuration keys from YAML.

    Existing keys are left exactly as they are: an operator's edited value in
    the admin UI must survive every re-run.
    """
    outcome = SeedResult()

    for config_entry in load_seed_yaml("system_config.yaml"):
        key = config_entry["key"]
        existing = await get_system_config_by_key(session, key)
        if existing:
            outcome.unchanged += 1
            continue
        await update_system_config(
            session,
            key=key,
            value=config_entry["value"],
            description=config_entry.get("description"),
        )
        outcome.created += 1

    await session.commit()
    return outcome


@dataclass(frozen=True)
class ReferenceSeedStep:
    """One code-owned reference-data step, shared by both seeders."""

    name: str
    description: str
    func: Callable[..., Awaitable[SeedResult]]


# Dependency order: roles and permissions exist before the grants that resolve
# them by name/code. Both seeders run these in this order.
REFERENCE_SEED_STEPS: list[ReferenceSeedStep] = [
    ReferenceSeedStep("roles", "Global role definitions", seed_reference_roles),
    ReferenceSeedStep(
        "permissions",
        "Permission codes (module constants + permissions.yaml)",
        seed_reference_permissions,
    ),
    ReferenceSeedStep(
        "role_permissions",
        "Role->permission grants. NOT purely additive: RESTORES GRANTS AN ADMIN "
        "REVOKED (revocation is a soft delete and this step matches on live "
        "rows). --skip role_permissions on hand-tuned system roles.",
        seed_reference_role_permissions,
    ),
    ReferenceSeedStep(
        "rate_limits",
        "API key rate limits per permission code",
        seed_reference_rate_limits,
    ),
    ReferenceSeedStep(
        "user_types",
        "User types and their onboarding steps",
        seed_reference_user_types,
    ),
    ReferenceSeedStep(
        "notification_categories",
        "System notification categories (preference layer is inert without them)",
        seed_reference_notification_categories,
    ),
    ReferenceSeedStep(
        "notification_templates",
        "System-wide notification templates",
        seed_reference_notification_templates,
    ),
    ReferenceSeedStep(
        "cron_jobs",
        "Cron job definitions (ARQ reads these rows)",
        seed_reference_cron_jobs,
    ),
    ReferenceSeedStep(
        "system_config",
        "System configuration keys (existing values are never overwritten)",
        seed_reference_system_config,
    ),
]

REFERENCE_SEED_STEP_NAMES: list[str] = [step.name for step in REFERENCE_SEED_STEPS]
