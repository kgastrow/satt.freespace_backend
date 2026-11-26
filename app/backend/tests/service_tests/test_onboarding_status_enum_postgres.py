"""PostgreSQL-gated regression tests for the ``onboarding_status`` enum.

WHY THIS TEST IS GATED (and not a normal unit test)
---------------------------------------------------
``tests/conftest.py`` runs the entire suite against in-memory SQLite. SQLite
has no native ENUM type -- SQLAlchemy renders ``Enum`` as ``VARCHAR`` there, so
*any* string round-trips successfully. That is precisely why the bug this file
guards against was invisible to a green test suite:

``src.models.user_user_type.OnboardingStatus`` is bound with
``SQLAEnum(OnboardingStatus, name="onboarding_status")`` and no
``values_callable``, so SQLAlchemy persists the member NAME ('EXPIRED').
Migration 91ec39088bf1 had added the label in lowercase ('expired'), so
PostgreSQL rejected every write with::

    invalid input value for enum onboarding_status: "EXPIRED"

which ``check_user_type_expiry_handler`` swallowed into a
``{"status": "error", ...}`` dict, failing silently on every cron run.
Migration 9ae4b5522102 adds the correct 'EXPIRED' label.

These tests therefore MUST run against a real PostgreSQL server. They skip
(never fail) when one is unreachable, so ``make test-fast`` stays green in
SQLite-only environments. Point them at a database with
``TEST_DATABASE_URL_DIRECT`` / ``DATABASE_URL_DIRECT`` if the default is wrong.

Every test runs inside an outer transaction that is rolled back on teardown,
so nothing is left behind in the target database.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
import os
import uuid as uuid_module

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.models.organization import Organization
from src.models.user import User
from src.models.user_type import UserType
from src.models.user_user_type import OnboardingStatus, UserUserType


pytestmark = pytest.mark.asyncio


DEFAULT_TEST_DSN = (
    "postgresql+asyncpg://ayzer_template:ayzer_template@localhost:6432/ayzer_template"
)


def _postgres_dsn() -> str:
    """Resolve the PostgreSQL DSN to test against, normalised to asyncpg."""
    dsn = (
        os.environ.get("TEST_DATABASE_URL_DIRECT")
        or os.environ.get("DATABASE_URL_DIRECT")
        or os.environ.get("DATABASE_URL")
        or DEFAULT_TEST_DSN
    )
    if dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql+asyncpg://", 1)
    return dsn


@pytest_asyncio.fixture(scope="function")
async def pg_session() -> AsyncGenerator[AsyncSession, None]:
    """A session bound to real PostgreSQL, rolled back on teardown.

    Skips the test when the server is unreachable, when the resolved DSN is not
    PostgreSQL (e.g. a SQLite override), or when asyncpg is not installed.
    """
    dsn = _postgres_dsn()
    if not dsn.startswith("postgresql+asyncpg://"):
        pytest.skip(f"Not a PostgreSQL DSN, skipping native-enum test: {dsn}")

    try:
        engine = create_async_engine(
            dsn,
            echo=False,
            # PgBouncer transaction pooling cannot cope with prepared statements.
            connect_args={"statement_cache_size": 0},
        )
        conn = await engine.connect()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL unreachable at {dsn}: {exc}")

    try:
        outer = await conn.begin()

        # An unmigrated database has no user_user_type table at all -- skip
        # rather than fail, so a missing schema is not reported as enum drift.
        probe = await conn.execute(text("SELECT to_regclass('public.user_user_type')"))
        if probe.scalar() is None:
            await outer.rollback()
            pytest.skip(
                f"Database at {dsn} has no user_user_type table; run 'make migrate'."
            )

        maker = async_sessionmaker(
            bind=conn,
            class_=AsyncSession,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with maker() as session:
            yield session
        await outer.rollback()
    finally:
        await conn.close()
        await engine.dispose()


async def _seed_assignment(
    session: AsyncSession, *, expires_at: datetime | None = None
) -> UserUserType:
    """Create the minimal org/user/user_type/assignment chain."""
    suffix = uuid_module.uuid4().hex[:12]

    org = Organization(name=f"Enum Test Org {suffix}", slug=f"enum-test-{suffix}")
    session.add(org)
    await session.flush()

    user = User(organization_id=org.id, email=f"enum-test-{suffix}@example.com")
    session.add(user)

    # UserType is a global (non tenant-scoped) catalogue table.
    user_type = UserType(name=f"Enum Test Type {suffix}", code=f"enum_{suffix}")
    session.add(user_type)
    await session.flush()

    assignment = UserUserType(
        organization_id=org.id,
        user_id=user.id,
        user_type_id=user_type.id,
        onboarding_status=OnboardingStatus.PENDING,
        expires_at=expires_at,
    )
    session.add(assignment)
    await session.flush()
    return assignment


async def test_expired_label_exists_in_pg_enum(pg_session: AsyncSession) -> None:
    """Every OnboardingStatus member NAME must exist as a pg_enum label.

    SQLAlchemy persists member names (no ``values_callable`` is configured), so
    a name with no matching label is an unwritable status.
    """
    result = await pg_session.execute(
        text(
            "SELECT e.enumlabel FROM pg_type t "
            "JOIN pg_enum e ON t.oid = e.enumtypid "
            "WHERE t.typname = 'onboarding_status'"
        )
    )
    labels = {row[0] for row in result}

    assert "EXPIRED" in labels, (
        "onboarding_status is missing the 'EXPIRED' label; "
        "migration 9ae4b5522102 has not been applied."
    )

    missing = {m.name for m in OnboardingStatus} - labels
    assert not missing, (
        f"OnboardingStatus members with no matching pg_enum label: {sorted(missing)}. "
        f"Present labels: {sorted(labels)}"
    )


async def test_expired_status_persists_and_reads_back(pg_session: AsyncSession) -> None:
    """Writing OnboardingStatus.EXPIRED must survive a commit and a re-read.

    This is the exact operation that raised
    ``invalid input value for enum onboarding_status: "EXPIRED"``.
    """
    assignment = await _seed_assignment(pg_session)
    assignment_id = assignment.id

    assignment.onboarding_status = OnboardingStatus.EXPIRED
    await pg_session.commit()

    pg_session.expunge_all()
    reloaded = await pg_session.get(UserUserType, assignment_id)
    assert reloaded is not None
    assert reloaded.onboarding_status is OnboardingStatus.EXPIRED

    # And the raw label stored in PostgreSQL is the uppercase member NAME.
    raw = await pg_session.execute(
        text(
            "SELECT onboarding_status::text FROM user_user_type WHERE id = :id"
        ).bindparams(id=assignment_id)
    )
    assert raw.scalar_one() == "EXPIRED"


async def test_every_status_member_is_writable(pg_session: AsyncSession) -> None:
    """Round-trip every OnboardingStatus member, not just EXPIRED."""
    for status in OnboardingStatus:
        assignment = await _seed_assignment(pg_session)
        assignment.onboarding_status = status
        await pg_session.flush()
        await pg_session.refresh(assignment)
        assert assignment.onboarding_status is status, f"{status.name} did not persist"


async def test_check_user_type_expiry_handler_succeeds_on_postgres(
    pg_session: AsyncSession,
) -> None:
    """The cron handler must report success, not a swallowed enum error.

    ``check_user_type_expiry_handler`` catches every exception and returns
    ``{"status": "error", ...}``. Before migration 9ae4b5522102 this returned
    an error on every run without raising, so asserting on ``status`` is the
    only way to detect the regression.
    """
    from src.services.cron.sessions import check_user_type_expiry_handler

    past = datetime.now(timezone.utc) - timedelta(days=1)
    assignment = await _seed_assignment(pg_session, expires_at=past)
    assignment_id = assignment.id
    await pg_session.flush()

    result = await check_user_type_expiry_handler(pg_session, {})

    assert (
        result["status"] == "completed"
    ), f"check_user_type_expiry_handler failed silently: {result}"
    assert result["expired_count"] >= 1

    reloaded = await pg_session.get(UserUserType, assignment_id)
    assert reloaded is not None
    assert reloaded.onboarding_status is OnboardingStatus.EXPIRED
