"""
Shared fixtures for every Freespace test (``tests/freespace/``).

Autouse (every Freespace test gets them without asking):
* ``fs_redis``   - a fresh fakeredis async client wired into
  ``src.services.freespace.redis_client`` (caches, mock clock offset, ...).
* ``fixed_clock`` - a ``FixedClock`` at 2026-11-24 05:45:00Z (07:45 in
  Africa/Johannesburg, a Tuesday, inside the default notification window),
  installed with ``set_clock_override`` so ``get_clock`` - and therefore every
  API dependency and worker helper - uses it. Advance it with
  ``fixed_clock.advance(seconds)``.
* ``fake_fcm``   - a ``FakeFcmClient`` installed with ``set_fcm_client_override``.

Data (opt-in): ``fs_roles``, ``fs_site``, ``fs_zones``, ``fs_snapshot``,
``fs_ingest_key``, ``fs_app_key``, ``fs_app_headers``, ``fs_second_site``,
users/tokens for administrator, operator, viewer and a second-organization
administrator, and ``fs_pg_engine`` for PostgreSQL-only tests (BT-01/BT-02).

All helpers create rows through the ORM on the shared ``async_session`` from
``tests/conftest.py`` and commit, so API tests using the root ``client``
fixture see them.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any
import uuid

import fakeredis.aioredis
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
import yaml  # type: ignore[import-untyped]

from src.constants.freespace import (
    FREESPACE_PERMISSION_CODES,
    OPERATOR_ROLE_NAME,
    Health,
)
from src.core.security import create_access_token, hash_password
import src.models  # noqa: F401  (registers every model, Freespace included)
from src.models.app_key import AppKey
from src.models.ingest_key import IngestKey
from src.models.organization import Organization
from src.models.permission import Permission
from src.models.role import Role
from src.models.role_permission import RolePermission
from src.models.site import Site
from src.models.site_snapshot import SiteSnapshot, ZoneSnapshot
from src.models.user import User
from src.models.user_role import UserRole
from src.models.zone import Zone
from src.services.freespace import clock as clock_module
from src.services.freespace import fcm as fcm_module
from src.services.freespace import redis_client
from src.services.freespace.clock import FixedClock
from src.services.freespace.fcm import FakeFcmClient
from src.services.freespace.keys import (
    generate_app_key,
    generate_ingest_key,
    hash_key,
    key_hint,
)
from src.services.freespace.site_bootstrap import create_site_dependents


SEED_DATA_DIR = Path(__file__).resolve().parents[2] / "scripts" / "seed_data"
FIXED_START = datetime(2026, 11, 24, 5, 45, 0, tzinfo=timezone.utc)

SITE_SLUG = "absa-alice-lane"
SECOND_SITE_SLUG = "other-customer-site"


# ─────────────────────────────────────────────────────────────
# Autouse infrastructure
# ─────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def fs_redis() -> AsyncGenerator[Any, None]:
    """Fresh fake async Redis for Freespace code (``redis_client.get_redis``)."""
    client = fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer())
    redis_client.set_redis_override(client)
    yield client
    redis_client.set_redis_override(None)
    await client.aclose()


@pytest.fixture(autouse=True)
def fixed_clock() -> Any:
    """The Freespace clock for this test (see module docstring)."""
    clock = FixedClock(FIXED_START)
    clock_module.set_clock_override(clock)
    yield clock
    clock_module.set_clock_override(None)


@pytest.fixture(autouse=True)
def fake_fcm() -> Any:
    """In-memory FCM; inspect ``fake_fcm.sent`` / script ``results_by_token``."""
    client = FakeFcmClient()
    fcm_module.set_fcm_client_override(client)
    yield client
    fcm_module.set_fcm_client_override(None)


# ─────────────────────────────────────────────────────────────
# Roles, permissions and users (D16)
# ─────────────────────────────────────────────────────────────


@dataclass
class FsRoles:
    """Roles keyed by name, with the Freespace grants from role_permissions.yaml."""

    roles: dict[str, Role]
    permissions: dict[str, Permission]


async def _get_or_create_role(session: AsyncSession, name: str) -> Role:
    existing = (
        (await session.execute(select(Role).where(Role.name == name))).scalars().first()
    )
    if existing:
        return existing
    role = Role(name=name, description=f"{name} (Freespace test)")
    session.add(role)
    await session.flush()
    return role


async def _get_or_create_permission(session: AsyncSession, code: str) -> Permission:
    existing = (
        (await session.execute(select(Permission).where(Permission.code == code)))
        .scalars()
        .first()
    )
    if existing:
        return existing
    resource, action = code.split(":")
    perm = Permission(code=code, name=code, resource=resource, action=action)
    session.add(perm)
    await session.flush()
    return perm


@pytest_asyncio.fixture
async def fs_roles(async_session: AsyncSession) -> FsRoles:
    """owner/admin/operator/viewer roles with exactly the Freespace grants of
    ``scripts/seed_data/role_permissions.yaml`` (so tests track the seed)."""
    grants = yaml.safe_load((SEED_DATA_DIR / "role_permissions.yaml").read_text())
    permissions = {
        code: await _get_or_create_permission(async_session, code)
        for code in FREESPACE_PERMISSION_CODES
    }
    roles: dict[str, Role] = {}
    for role_name in ("owner", "admin", OPERATOR_ROLE_NAME, "viewer"):
        role = await _get_or_create_role(async_session, role_name)
        roles[role_name] = role
        for code in grants.get(role_name) or []:
            if code in permissions:
                async_session.add(
                    RolePermission(role_id=role.id, permission_id=permissions[code].id)
                )
    await async_session.commit()
    return FsRoles(roles=roles, permissions=permissions)


async def _make_user(
    session: AsyncSession, org: Organization, email: str, role: Role | None
) -> User:
    user = User(
        email=email,
        password=hash_password("Password123!"),
        email_verified=True,
        organization_id=org.id,
    )
    session.add(user)
    await session.flush()
    if role is not None:
        session.add(UserRole(user_id=user.id, role_id=role.id, organization_id=org.id))
    await session.commit()
    await session.refresh(user)
    return user


def _bearer(user: User) -> str:
    token = create_access_token(
        user_id=str(user.id), organization_id=str(user.organization_id)
    )
    return f"Bearer {token}"


@pytest_asyncio.fixture
async def fs_admin_user(async_session, test_organization, fs_roles) -> User:
    """Administrator (template ``admin`` role) in ``test_organization``."""
    return await _make_user(
        async_session, test_organization, "fs-admin@test.com", fs_roles.roles["admin"]
    )


@pytest_asyncio.fixture
async def fs_operator_user(async_session, test_organization, fs_roles) -> User:
    """Operator (new ``operator`` role) in ``test_organization``."""
    return await _make_user(
        async_session,
        test_organization,
        "fs-operator@test.com",
        fs_roles.roles[OPERATOR_ROLE_NAME],
    )


@pytest_asyncio.fixture
async def fs_viewer_user(async_session, test_organization, fs_roles) -> User:
    """Viewer (template ``viewer`` role) in ``test_organization``."""
    return await _make_user(
        async_session, test_organization, "fs-viewer@test.com", fs_roles.roles["viewer"]
    )


@pytest_asyncio.fixture
async def fs_no_role_user(async_session, test_organization, fs_roles) -> User:
    """A user in ``test_organization`` with no role (expects 403 everywhere)."""
    return await _make_user(
        async_session, test_organization, "fs-norole@test.com", None
    )


@pytest_asyncio.fixture
async def fs_second_org_admin_user(
    async_session, second_organization, fs_roles
) -> User:
    """Administrator of ``second_organization`` (tenant isolation tests)."""
    return await _make_user(
        async_session,
        second_organization,
        "fs-admin2@test.com",
        fs_roles.roles["admin"],
    )


@pytest.fixture
def fs_admin_token(fs_admin_user) -> str:
    return _bearer(fs_admin_user)


@pytest.fixture
def fs_operator_token(fs_operator_user) -> str:
    return _bearer(fs_operator_user)


@pytest.fixture
def fs_viewer_token(fs_viewer_user) -> str:
    return _bearer(fs_viewer_user)


@pytest.fixture
def fs_no_role_token(fs_no_role_user) -> str:
    return _bearer(fs_no_role_user)


@pytest.fixture
def fs_second_org_admin_token(fs_second_org_admin_user) -> str:
    return _bearer(fs_second_org_admin_user)


# Super admin: use the root fixtures ``test_admin_user`` / ``test_admin_token``.


# ─────────────────────────────────────────────────────────────
# Sites, zones, snapshots
# ─────────────────────────────────────────────────────────────


async def make_site(
    session: AsyncSession,
    organization: Organization,
    *,
    slug: str = SITE_SLUG,
    name: str = "Alice Lane",
    managed: bool = True,
    listed: bool = True,
    now: datetime = FIXED_START,
    **settings: Any,
) -> Site:
    """Create a live site with its engine-state row and default templates.
    ``settings`` override any ``Site`` column (e.g. ``trigger_pct=85``)."""
    site = Site(
        organization_id=organization.id,
        slug=slug,
        name=name,
        fcm_topic=settings.pop("fcm_topic", f"freespace-{slug}"),
        managed=managed,
        listed=listed,
        **settings,
    )
    session.add(site)
    await session.flush()
    await create_site_dependents(session, site, now)
    await session.commit()
    await session.refresh(site)
    return site


async def make_zone(
    session: AsyncSession,
    site: Site,
    slug: str,
    *,
    name: str | None = None,
    display_order: int = 0,
    enabled: bool = True,
    **settings: Any,
) -> Zone:
    """Create a live zone (enabled by default, unlike a discovered zone)."""
    zone = Zone(
        organization_id=site.organization_id,
        site_id=site.id,
        slug=slug,
        name=name or slug.upper(),
        display_order=display_order,
        enabled=enabled,
        **settings,
    )
    session.add(zone)
    await session.commit()
    await session.refresh(zone)
    return zone


@pytest_asyncio.fixture
async def fs_site(async_session, test_organization) -> Site:
    """Managed, listed site ``absa-alice-lane`` in ``test_organization`` with
    engine-state row and default template rows. Default settings (§10.1)."""
    return await make_site(async_session, test_organization)


@pytest_asyncio.fixture
async def fs_second_site(async_session, second_organization) -> Site:
    """A site of ``second_organization`` (tenant isolation, BT-03)."""
    return await make_site(
        async_session, second_organization, slug=SECOND_SITE_SLUG, name="Other Site"
    )


@pytest_asyncio.fixture
async def fs_zones(async_session, fs_site) -> dict[str, Zone]:
    """Four enabled zones b1..b4 (display order 1..4, names "Basement N")."""
    zones = {}
    for index in range(1, 5):
        slug = f"b{index}"
        zones[slug] = await make_zone(
            async_session, fs_site, slug, name=f"Basement {index}", display_order=index
        )
    return zones


SnapshotFn = Callable[..., Awaitable[tuple[SiteSnapshot, dict[str, ZoneSnapshot]]]]


@pytest.fixture
def fs_snapshot(async_session: AsyncSession, fixed_clock: FixedClock) -> SnapshotFn:
    """Builder that writes (overwrites) the latest snapshot of a site.

    ``await fs_snapshot(site, capacity=1200, occupied=1081, zones={"b1":
    {"capacity": 450, "occupied": 432}})``. Counts default so the BF-12 sum
    holds (``free_usable = capacity - occupied - reserved - disabled -
    unknown``); ``health`` defaults to OK, ``received_at``/``measured_at`` to
    ``fixed_clock.now()``. ``zones`` keys are zone slugs of existing zones.
    Returns ``(site_snapshot_row, {slug: zone_snapshot_row})``.
    """

    def _counts(data: dict[str, Any]) -> dict[str, Any]:
        capacity = int(data["capacity"])
        occupied = int(data["occupied"])
        reserved = int(data.get("free_reserved", 0))
        disabled = int(data.get("free_disabled", 0))
        unknown = int(data.get("unknown", 0))
        free_usable = int(
            data.get(
                "free_usable",
                max(0, capacity - occupied - reserved - disabled - unknown),
            )
        )
        health = Health(data.get("health", Health.OK)).value
        return {
            "capacity": capacity,
            "occupied": occupied,
            "free_usable": free_usable,
            "free_reserved": reserved,
            "free_disabled": disabled,
            "unknown": unknown,
            "health": health,
            "reported_health": Health(data.get("reported_health", health)).value,
        }

    async def build(
        site: Site,
        *,
        zones: dict[str, dict[str, Any]] | None = None,
        received_at: datetime | None = None,
        measured_at: datetime | None = None,
        **site_counts: Any,
    ) -> tuple[SiteSnapshot, dict[str, ZoneSnapshot]]:
        received = received_at or fixed_clock.now()
        measured = measured_at or received
        site_row = (
            (
                await async_session.execute(
                    select(SiteSnapshot).where(SiteSnapshot.site_id == site.id)
                )
            )
            .scalars()
            .first()
        )
        values = _counts(site_counts)
        if site_row is None:
            site_row = SiteSnapshot(
                organization_id=site.organization_id,
                site_id=site.id,
                measured_at=measured,
                received_at=received,
                **values,
            )
            async_session.add(site_row)
        else:
            for key, value in values.items():
                setattr(site_row, key, value)
            site_row.measured_at = measured
            site_row.received_at = received

        zone_rows: dict[str, ZoneSnapshot] = {}
        for slug, data in (zones or {}).items():
            zone = (
                (
                    await async_session.execute(
                        select(Zone).where(
                            Zone.site_id == site.id,
                            Zone.slug == slug,
                            Zone.deleted_time.is_(None),
                        )
                    )
                )
                .scalars()
                .one()
            )
            row = (
                (
                    await async_session.execute(
                        select(ZoneSnapshot).where(ZoneSnapshot.zone_id == zone.id)
                    )
                )
                .scalars()
                .first()
            )
            zone_values = _counts(data)
            zone_received = data.get("received_at", received)
            zone_measured = data.get("measured_at", measured)
            if row is None:
                row = ZoneSnapshot(
                    organization_id=site.organization_id,
                    site_id=site.id,
                    zone_id=zone.id,
                    measured_at=zone_measured,
                    received_at=zone_received,
                    **zone_values,
                )
                async_session.add(row)
            else:
                for key, value in zone_values.items():
                    setattr(row, key, value)
                row.measured_at = zone_measured
                row.received_at = zone_received
            zone_rows[slug] = row

        await async_session.commit()
        return site_row, zone_rows

    return build


# ─────────────────────────────────────────────────────────────
# Keys
# ─────────────────────────────────────────────────────────────


async def make_ingest_key(
    session: AsyncSession, site: Site, *, name: str = "ParkIT", **columns: Any
) -> tuple[str, IngestKey]:
    """Create an ingest key; returns ``(plaintext, row)``. ``columns`` may set
    ``expires_at`` / ``revoked_at`` / ``deleted_time``."""
    plaintext = generate_ingest_key()
    row = IngestKey(
        organization_id=site.organization_id,
        site_id=site.id,
        name=name,
        key_hash=hash_key(plaintext),
        key_hint=key_hint(plaintext),
        **columns,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return plaintext, row


async def make_app_key(
    session: AsyncSession, *, name: str = "Android 1.0", **columns: Any
) -> tuple[str, AppKey]:
    """Create an app key; returns ``(plaintext, row)``."""
    plaintext = generate_app_key()
    row = AppKey(
        name=name, key_hash=hash_key(plaintext), key_hint=key_hint(plaintext), **columns
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return plaintext, row


@pytest_asyncio.fixture
async def fs_ingest_key(async_session, fs_site) -> tuple[str, IngestKey]:
    """Valid ingest key of ``fs_site``: ``(plaintext, row)``."""
    return await make_ingest_key(async_session, fs_site)


@pytest.fixture
def fs_ingest_headers(fs_ingest_key) -> dict[str, str]:
    """``{"Authorization": "Bearer <ingest key>"}`` for ``fs_site``."""
    return {"Authorization": f"Bearer {fs_ingest_key[0]}"}


@pytest_asyncio.fixture
async def fs_app_key(async_session) -> tuple[str, AppKey]:
    """Valid app key: ``(plaintext, row)``."""
    return await make_app_key(async_session)


@pytest.fixture
def fs_app_headers(fs_app_key) -> dict[str, str]:
    """``{"X-Freespace-App-Key": <plaintext>}``."""
    return {"X-Freespace-App-Key": fs_app_key[0]}


# ─────────────────────────────────────────────────────────────
# PostgreSQL-only tests (D15: BT-01, BT-02)
# ─────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def fs_pg_engine() -> AsyncGenerator[AsyncEngine, None]:
    """An engine on a real, MIGRATED PostgreSQL for row-lock tests.

    DSN: ``TEST_DATABASE_URL_DIRECT`` (e.g.
    ``postgresql+asyncpg://freespace:freespace@localhost:5432/freespace``).
    Skips when unset, unreachable or not migrated. Tests run real commits:
    they must create uniquely-named rows and delete everything they create
    (hard deletes are fine in test cleanup). Mark such tests
    ``@pytest.mark.postgres``.
    """
    dsn = os.environ.get("TEST_DATABASE_URL_DIRECT", "")
    if dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    if not dsn.startswith("postgresql+asyncpg://"):
        pytest.skip("TEST_DATABASE_URL_DIRECT not set to a PostgreSQL DSN")
    engine = create_async_engine(dsn, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn:
            from sqlalchemy import text

            probe = await conn.execute(
                text("SELECT to_regclass('public.site_engine_state')")
            )
            if probe.scalar() is None:
                pytest.skip("PostgreSQL is not migrated (no site_engine_state table)")
    except Exception as exc:  # pragma: no cover - environment dependent
        await engine.dispose()
        pytest.skip(f"PostgreSQL unreachable: {exc}")
    yield engine
    await engine.dispose()


def unique_slug(prefix: str = "pg") -> str:
    """A slug unlikely to collide in a shared database."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"
