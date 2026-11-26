"""
Tests for the maintenance seeder (scripts/seed_maintenance.py) and the shared
code-owned reference-data steps in src/services/organization_seeding.py.

The guarantees under test:
  1. Every reference-data step is idempotent (re-running creates nothing).
  2. --dry-run executes the writes but persists nothing.
  3. The maintenance seeder never creates an identity (user / API key) or demo
     content, even against a completely empty database.
  4. --only / --skip select the right steps, in dependency order.
  5. The bootstrap seeder and the maintenance seeder call the SAME function for
     every reference-data step - the anti-drift guard.
"""

import ast
import inspect
from pathlib import Path

import pytest
from sqlalchemy import func, select

from scripts import seed_first_tenant, seed_maintenance
from src.models.announcement import Announcement
from src.models.api_key import ApiKey
from src.models.cron_job import CronJobDefinition
from src.models.notification_category import NotificationCategory
from src.models.notification_template import NotificationTemplate
from src.models.organization import Organization
from src.models.permission import Permission
from src.models.role import Role
from src.models.role_permission import RolePermission
from src.models.system_config import SystemConfig
from src.models.user import User
from src.services import organization_seeding
from src.services.organization_seeding import (
    REFERENCE_SEED_STEP_NAMES,
    REFERENCE_SEED_STEPS,
)


STEP_NAMES = list(REFERENCE_SEED_STEP_NAMES)


async def _count(session, model) -> int:
    result = await session.execute(select(func.count()).select_from(model))
    return int(result.scalar() or 0)


async def _run_all_steps(session):
    """Run every reference step once, in dependency order."""
    return {step.name: await step.func(session) for step in REFERENCE_SEED_STEPS}


class TestReferenceStepIdempotency:
    """Run twice; the second run must report 0 created."""

    @pytest.mark.parametrize("step_name", STEP_NAMES)
    async def test_step_is_idempotent(self, async_session, step_name):
        step = next(s for s in REFERENCE_SEED_STEPS if s.name == step_name)

        # First pass: run every step up to and including this one, so the
        # step's dependencies (roles, permissions) exist.
        first = None
        for candidate in REFERENCE_SEED_STEPS:
            first = await candidate.func(async_session)
            if candidate.name == step_name:
                break

        assert first is not None
        assert first.created > 0, f"step '{step_name}' seeded nothing on a fresh DB"

        second = await step.func(async_session)

        assert second.created == 0, (
            f"step '{step_name}' created {second.created} rows on re-run - "
            "it is not idempotent"
        )
        assert second.updated == 0
        assert second.unchanged >= first.created

    async def test_full_run_is_idempotent(self, async_session):
        await _run_all_steps(async_session)
        counts_before = {
            "roles": await _count(async_session, Role),
            "permissions": await _count(async_session, Permission),
            "grants": await _count(async_session, RolePermission),
            "cron_jobs": await _count(async_session, CronJobDefinition),
            "system_config": await _count(async_session, SystemConfig),
            "templates": await _count(async_session, NotificationTemplate),
            "categories": await _count(async_session, NotificationCategory),
        }

        second = await _run_all_steps(async_session)

        assert all(result.created == 0 for result in second.values()), {
            name: result.created for name, result in second.items()
        }
        counts_after = {
            "roles": await _count(async_session, Role),
            "permissions": await _count(async_session, Permission),
            "grants": await _count(async_session, RolePermission),
            "cron_jobs": await _count(async_session, CronJobDefinition),
            "system_config": await _count(async_session, SystemConfig),
            "templates": await _count(async_session, NotificationTemplate),
            "categories": await _count(async_session, NotificationCategory),
        }
        assert counts_after == counts_before


class TestDryRun:
    async def test_dry_run_persists_nothing(self, async_session):
        proxy = seed_maintenance.DryRunSession(async_session)

        results = await _run_all_steps(proxy)

        # The writes really happened inside the transaction.
        assert sum(result.created for result in results.values()) > 0
        assert await _count(async_session, Role) > 0

        await async_session.rollback()

        assert await _count(async_session, Role) == 0
        assert await _count(async_session, Permission) == 0
        assert await _count(async_session, RolePermission) == 0
        assert await _count(async_session, CronJobDefinition) == 0
        assert await _count(async_session, SystemConfig) == 0
        assert await _count(async_session, NotificationTemplate) == 0

    async def test_dry_run_session_commit_only_flushes(self, async_session):
        proxy = seed_maintenance.DryRunSession(async_session)
        await organization_seeding.seed_reference_roles(proxy)
        await async_session.rollback()
        assert await _count(async_session, Role) == 0


class TestNoIdentitiesOrDemoContent:
    async def test_creates_no_users_api_keys_or_demo_content(self, async_session):
        await _run_all_steps(async_session)

        assert await _count(async_session, User) == 0
        assert await _count(async_session, ApiKey) == 0
        assert await _count(async_session, Organization) == 0
        assert await _count(async_session, Announcement) == 0

    async def test_role_permission_grants_have_no_granting_user(self, async_session):
        """No admin exists during maintenance, so grants are attributed to no one."""
        await organization_seeding.seed_reference_roles(async_session)
        await organization_seeding.seed_reference_permissions(async_session)
        await organization_seeding.seed_reference_role_permissions(async_session)

        result = await async_session.execute(select(RolePermission))
        grants = result.scalars().all()
        assert grants
        assert all(grant.granted_by is None for grant in grants)

    def test_maintenance_module_imports_no_identity_helpers(self):
        """The script must not even reach for a user/API key/demo seeding call."""
        source = Path(seed_maintenance.__file__).read_text()
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.update(alias.name for alias in node.names)
        forbidden = {
            "create_user",
            "create_api_key",
            "seed_test_users",
            "seed_api_keys",
            "seed_announcement",
            "seed_feedback_data",
            "seed_help_center",
            "seed_maintenance_history",
            "seed_organizations",
        }
        assert not (imported & forbidden)


class TestStepSelection:
    def test_default_runs_every_step_in_order(self):
        steps = seed_maintenance.select_steps([], [])
        assert [step.name for step in steps] == STEP_NAMES

    def test_only_selects_just_those_steps(self):
        steps = seed_maintenance.select_steps(["system_config", "cron_jobs"], [])
        # --only preserves dependency order rather than argument order.
        assert [step.name for step in steps] == ["cron_jobs", "system_config"]

    def test_skip_removes_those_steps(self):
        steps = seed_maintenance.select_steps([], ["role_permissions", "roles"])
        names = [step.name for step in steps]
        assert "role_permissions" not in names
        assert "roles" not in names
        assert len(names) == len(STEP_NAMES) - 2

    def test_only_and_skip_combine(self):
        steps = seed_maintenance.select_steps(
            ["roles", "permissions", "role_permissions"], ["role_permissions"]
        )
        assert [step.name for step in steps] == ["roles", "permissions"]

    def test_unknown_step_is_rejected(self):
        with pytest.raises(ValueError) as exc:
            seed_maintenance.select_steps(["not_a_step"], [])
        assert "not_a_step" in str(exc.value)

        with pytest.raises(ValueError):
            seed_maintenance.select_steps([], ["also_not_a_step"])

    def test_parse_step_list(self):
        assert seed_maintenance.parse_step_list(None) == []
        assert seed_maintenance.parse_step_list("") == []
        assert seed_maintenance.parse_step_list(" a , b ,") == ["a", "b"]

    def test_role_permissions_is_in_the_default_set_and_warns(self):
        """Default-on, but --list and the runtime output must say what it does."""
        names = [step.name for step in seed_maintenance.select_steps([], [])]
        assert "role_permissions" in names

        step = next(s for s in REFERENCE_SEED_STEPS if s.name == "role_permissions")
        listing = seed_maintenance.format_step_list()
        for text in (
            step.description,
            listing,
            seed_maintenance.ROLE_PERMISSIONS_WARNING,
        ):
            lowered = text.lower()
            assert "not purely additive" in lowered or "restores" in lowered
        assert (
            "revoke" in step.description.lower()
            or "revoked" in step.description.lower()
        )
        assert "--skip role_permissions" in seed_maintenance.ROLE_PERMISSIONS_WARNING
        assert "restored" in seed_maintenance.ROLE_PERMISSIONS_WARNING.lower()


class TestSharedStepsAntiDrift:
    """The bootstrap and maintenance seeders must not own separate copies."""

    def test_maintenance_steps_are_the_shared_registry(self):
        steps = seed_maintenance.select_steps([], [])
        assert steps == REFERENCE_SEED_STEPS
        for step, shared in zip(steps, REFERENCE_SEED_STEPS):
            assert step.func is shared.func

    @pytest.mark.parametrize("step_name", STEP_NAMES)
    def test_bootstrap_uses_the_same_function_object(self, step_name):
        step = next(s for s in REFERENCE_SEED_STEPS if s.name == step_name)
        bootstrap_func = getattr(seed_first_tenant, step.func.__name__, None)
        assert bootstrap_func is not None, (
            f"scripts/seed_first_tenant.py does not import {step.func.__name__} - "
            "the two seeders have drifted"
        )
        assert bootstrap_func is step.func

    @pytest.mark.parametrize("step_name", STEP_NAMES)
    def test_bootstrap_actually_calls_the_shared_function(self, step_name):
        step = next(s for s in REFERENCE_SEED_STEPS if s.name == step_name)
        source = inspect.getsource(seed_first_tenant.seed_first_tenant)
        called = set()
        for node in ast.walk(ast.parse(source.strip())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called.add(node.func.id)
        assert (
            step.func.__name__ in called
        ), f"seed_first_tenant() no longer calls {step.func.__name__}"

    def test_bootstrap_defines_no_private_copies(self):
        """Reference-data seeding must not live in the bootstrap script."""
        removed = [
            "seed_permissions",
            "seed_rate_limits",
            "seed_role_permissions",
            "seed_user_types_and_onboarding",
            "seed_notification_templates",
            "seed_cron_jobs",
            "seed_system_config",
        ]
        tree = ast.parse(Path(seed_first_tenant.__file__).read_text())
        defined = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert not (defined & set(removed)), (
            "seed_first_tenant.py re-defines a shared reference-data seeder; "
            "it must call src/services/organization_seeding.py instead"
        )

    def test_registry_names_are_unique_and_exposed(self):
        assert len(STEP_NAMES) == len(set(STEP_NAMES))
        assert STEP_NAMES == [step.name for step in REFERENCE_SEED_STEPS]
