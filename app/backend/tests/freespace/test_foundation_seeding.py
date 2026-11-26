"""Foundation: permissions, operator role and grants via the SHARED seeder (D16,
CLAUDE.md rule 14), SystemConfig keys, response codes."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from src.constants.freespace import FREESPACE_PERMISSION_CODES, OPERATOR_ROLE_NAME
from src.core.response_codes import RESPONSE_CODES
from src.crud.role_permission import get_user_permissions
from src.models.permission import Permission
from src.models.role import Role
from src.models.role_permission import RolePermission
from src.models.system_config import SystemConfig
from src.models.user_role import UserRole
from src.services.freespace.deployment_settings import SYSTEM_CONFIG_KEYS
from src.services.organization_seeding import (
    seed_reference_permissions,
    seed_reference_role_permissions,
    seed_reference_roles,
    seed_reference_system_config,
)


EXPECTED = {
    "owner": set(FREESPACE_PERMISSION_CODES),
    "admin": set(FREESPACE_PERMISSION_CODES),
    OPERATOR_ROLE_NAME: {"sites:read", "site_events:read", "site_push:test"},
    "viewer": {"sites:read", "site_events:read"},
    "member": set(),
}


async def _seed(session) -> None:
    await seed_reference_roles(session)
    await seed_reference_permissions(session)
    await seed_reference_role_permissions(session)
    await seed_reference_system_config(session)


async def _grants(session) -> dict[str, set[str]]:
    rows = await session.execute(
        select(Role.name, Permission.code)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(RolePermission.deleted_time.is_(None))
    )
    grants: dict[str, set[str]] = {}
    for role, code in rows.all():
        if code in FREESPACE_PERMISSION_CODES:
            grants.setdefault(role, set()).add(code)
    return grants


async def test_shared_seeder_creates_roles_permissions_and_grants(async_session):
    await _seed(async_session)
    roles = {r.name for r in (await async_session.execute(select(Role))).scalars()}
    assert OPERATOR_ROLE_NAME in roles
    codes = {
        p.code for p in (await async_session.execute(select(Permission))).scalars()
    }
    assert set(FREESPACE_PERMISSION_CODES) <= codes

    grants = await _grants(async_session)
    for role, expected in EXPECTED.items():
        assert grants.get(role, set()) == expected, role
    # BF-75 / plan Q7: announcements are Administrator only
    assert "site_push:announce" not in grants[OPERATOR_ROLE_NAME]


async def test_seeder_is_idempotent(async_session):
    await _seed(async_session)
    before = await _grants(async_session)
    result = await seed_reference_role_permissions(async_session)
    roles_again = await seed_reference_roles(async_session)
    assert await _grants(async_session) == before
    assert roles_again.created == 0
    assert result.created == 0


async def test_system_config_keys_seeded(async_session):
    await seed_reference_system_config(async_session)
    keys = {
        c.key for c in (await async_session.execute(select(SystemConfig))).scalars()
    }
    assert set(SYSTEM_CONFIG_KEYS.values()) <= keys


async def test_operator_permissions_resolve(
    async_session, test_organization, test_user
):
    await _seed(async_session)
    operator = (
        await async_session.execute(select(Role).where(Role.name == OPERATOR_ROLE_NAME))
    ).scalar_one()
    async_session.add(
        UserRole(
            user_id=test_user.id,
            role_id=operator.id,
            organization_id=test_organization.id,
        )
    )
    await async_session.commit()
    perms = set(
        await get_user_permissions(
            async_session, str(test_user.id), str(test_organization.id)
        )
    )
    assert {"sites:read", "site_events:read", "site_push:test"} <= perms
    assert "sites:write" not in perms and "site_push:announce" not in perms


async def test_fixture_roles_match_seed(async_session, fs_roles):
    """The shared ``fs_roles`` fixture grants exactly what the seed grants."""
    grants = await _grants(async_session)
    for role in fs_roles.roles:
        assert grants.get(role, set()) == EXPECTED[role], role


def test_freespace_response_codes_have_english_copy():
    locale = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "frontend"
            / "src"
            / "locales"
            / "en"
            / "backend.json"
        ).read_text()
    )
    domains = (
        "ingest.",
        "app_key.",
        "ingest_key.",
        "site.",
        "zone.",
        "site_template.",
        "device.",
        "site_push.",
        "site_event.",
        "site_stats.",
        "mock.",
    )
    codes = [c for c in RESPONSE_CODES if c.startswith(domains)]
    assert len(codes) > 60
    for code in codes:
        domain, key = code.split(".", 1)
        assert locale.get(domain, {}).get(key), f"no English copy for {code}"
