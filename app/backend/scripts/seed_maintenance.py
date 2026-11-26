#!/usr/bin/env python3
"""
Maintenance seed - code-owned reference data only, no identities, no demo data.

WHY THIS EXISTS
---------------
``scripts/seed_first_tenant.py`` is a *bootstrap*: alongside reference data it
creates the default organization, a super admin at a fixed
ADMIN_EMAIL/ADMIN_PASSWORD, test users with YAML passwords, API keys and demo
content (announcements, feedback, help centre articles, maintenance history).
Every step is get-or-create keyed on the natural key, so re-running it on a live
deployment to pick up (say) four new system config keys also re-asserts all of
that: an admin who changed their email in the UI gets the seed's original
address recreated beside them as a second super admin with the seed password,
and demo announcements and feedback land in a real tenant.

This script seeds ONLY data that is a property of the CODE, not of the
deployment: roles, permissions, role grants, rate limits, user types,
notification categories and templates, cron definitions and system config keys.
Every step is additive get-or-create - an existing row is never updated or
deleted, so admin-edited values survive.

Run it after any deploy that adds reference data.

The steps themselves live in ``src/services/organization_seeding.py``
(``REFERENCE_SEED_STEPS``) and are the exact same functions the bootstrap
seeder calls, so the two seeders cannot drift.

WHAT IT DELIBERATELY DOES NOT TOUCH
-----------------------------------
- Users, passwords, user-role assignments, API keys.
- Organizations and their SSO/2FA settings.
- Feature flags and per-organization flag overrides. The flag DEFINITIONS in
  ``seed_first_tenant.seed_feature_flags`` are code-owned and additive, so a
  new flag added to the code has the same reach problem this script exists to
  fix - but a flag's ``default_enabled`` and its per-org overrides are
  deployment policy (the bootstrap turns feedback_widget and user_onboarding on
  for every org it seeds), so promoting the step here needs the definition
  split from the enablement first. Until then, add a new flag by hand.
- Demo/sample content of any kind: announcements, feedback, help centre
  articles, maintenance history, avatars.

ONE STEP THAT IS NOT PURELY ADDITIVE
------------------------------------
``role_permissions``. Revoking a permission from a role soft-deletes the grant
and the seeders match on ``deleted_time IS NULL``, so a grant an admin
deliberately removed from a system role is RE-CREATED here. It stays in the
default run because a deploy that adds a permission needs its grants applied -
but use ``--skip role_permissions`` on a deployment with hand-tuned system
roles.

Usage (from app/backend with .venv active):
    python scripts/seed_maintenance.py                     # all steps
    python scripts/seed_maintenance.py --list              # show steps and exit
    python scripts/seed_maintenance.py --only system_config
    python scripts/seed_maintenance.py --skip role_permissions
    python scripts/seed_maintenance.py --dry-run           # write, report, roll back

``--dry-run`` redirects each step's ``commit()`` to a ``flush()`` and rolls the
whole transaction back at the end, so the counts printed are real (the INSERTs
actually run) but nothing persists. Steps run in dependency order (roles and
permissions before the grants that resolve them); ``--only``/``--skip`` preserve
that order but do not pull in dependencies for you.

Safe to re-run.
"""

import argparse
import asyncio
import os
import sys
from typing import Any


# Add project root to path so `src` imports cleanly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings
from src.services.organization_seeding import (
    REFERENCE_SEED_STEP_NAMES,
    REFERENCE_SEED_STEPS,
    ReferenceSeedStep,
    SeedResult,
)


# Printed both by --list and at runtime, so an operator cannot miss it.
ROLE_PERMISSIONS_WARNING = (
    "WARNING: this step is not purely additive - revoking a permission "
    "soft-deletes the grant, so a grant an admin deliberately removed from a "
    "system role is RESTORED here. Use --skip role_permissions to avoid that."
)


class DryRunSession:
    """Session proxy whose ``commit()`` only flushes.

    Writes stay visible to later steps inside the transaction, but the outer
    transaction can still be rolled back so nothing persists. Everything else
    delegates to the real session unchanged.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)


def parse_step_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def select_steps(only: list[str], skip: list[str]) -> list[ReferenceSeedStep]:
    """Return the steps to run, in dependency order."""
    unknown = [name for name in only + skip if name not in REFERENCE_SEED_STEP_NAMES]
    if unknown:
        raise ValueError(
            f"Unknown step(s): {', '.join(unknown)}. "
            f"Valid steps: {', '.join(REFERENCE_SEED_STEP_NAMES)}"
        )

    selected = (
        REFERENCE_SEED_STEPS
        if not only
        else [step for step in REFERENCE_SEED_STEPS if step.name in only]
    )
    return [step for step in selected if step.name not in skip]


def format_step_list() -> str:
    """Human-readable listing of every step, for --list."""
    width = max(len(name) for name in REFERENCE_SEED_STEP_NAMES)
    lines = []
    for step in REFERENCE_SEED_STEPS:
        lines.append(f"  {step.name.ljust(width)}  {step.description}")
    return "\n".join(lines)


async def run_steps(
    session: Any, steps: list[ReferenceSeedStep]
) -> dict[str, SeedResult]:
    """Run the given steps against ``session`` and return their results."""
    results: dict[str, SeedResult] = {}
    for step in steps:
        print(f"[{step.name}] {step.description.splitlines()[0]}")
        if step.name == "role_permissions":
            print(f"  {ROLE_PERMISSIONS_WARNING}")
        result = await step.func(session)
        results[step.name] = result
        print(f"  {result.summary()}")
        for note in result.notes:
            print(f"  note: {note}")
        print()
    return results


async def seed_maintenance(steps: list[ReferenceSeedStep], dry_run: bool) -> None:
    print("=" * 60)
    print("Maintenance seed" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 60)
    print("Reference data only - no users, API keys, organizations or demo data.")
    print()

    engine = create_async_engine(
        settings.DATABASE_URL_DIRECT,
        poolclass=NullPool,
        connect_args={"statement_cache_size": 100, "command_timeout": 60},
    )
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with async_session() as session:
            target: Any = DryRunSession(session) if dry_run else session
            try:
                results = await run_steps(target, steps)

                if dry_run:
                    await session.rollback()

                print("=" * 60)
                total_created = sum(r.created for r in results.values())
                total_unchanged = sum(r.unchanged for r in results.values())
                print(
                    f"Totals: {total_created} created, {total_unchanged} unchanged "
                    f"across {len(results)} step(s)"
                )
                if dry_run:
                    print(
                        "Dry run complete - transaction rolled back, nothing persisted."
                    )
                else:
                    print("Maintenance seed completed successfully")
                print("=" * 60)
            except Exception as exc:
                await session.rollback()
                print(f"\nError during maintenance seed: {exc}")
                import traceback

                traceback.print_exc()
                sys.exit(1)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Seed code-owned reference data without touching identities or "
            "demo content. Safe to re-run on a live deployment."
        )
    )
    parser.add_argument("--list", action="store_true", help="List steps and exit")
    parser.add_argument("--only", help="Comma-separated steps to run")
    parser.add_argument("--skip", help="Comma-separated steps to skip")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute the writes, report the counts, then roll back",
    )
    args = parser.parse_args()

    if args.list:
        print("Reference-data seed steps (dependency order):")
        print(format_step_list())
        return

    try:
        steps = select_steps(parse_step_list(args.only), parse_step_list(args.skip))
    except ValueError as exc:
        print(exc)
        sys.exit(2)

    if not steps:
        print("No steps selected.")
        sys.exit(2)

    asyncio.run(seed_maintenance(steps, args.dry_run))


if __name__ == "__main__":
    main()
