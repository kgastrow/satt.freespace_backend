"""The five ``native_enum=False`` enum columns must be wide enough and checked.

``Enum(X, native_enum=False)`` renders as a bare VARCHAR, and SQLAlchemy 2.0
defaults ``create_constraint`` to ``False``. That left five columns storing the
uppercase Python member NAME as free text with nothing enforcing validity, so a
bad value was accepted on WRITE and only exploded much later on READ, as a
``LookupError`` raised while the ORM inflated the row.

Four of them were also sized to the exact byte of the longest member name of the
day, which turns adding any longer member into a data-truncation outage:

  * ``user.created_via``             varchar(6)  vs 'GOOGLE'    (6)
  * ``data_export_request.status``   varchar(10) vs 'PROCESSING'(10)
  * ``data_deletion_request.status`` varchar(9)  vs 'CANCELLED' (9)
  * ``user.suspension_status``       varchar(9)  vs 'SUSPENDED' (9)

All five are now ``length=50`` with ``create_constraint=True``. These tests pin
both halves: the declared shape of the column, that every member round-trips
through a real database, and that an out-of-range value is rejected BY THE
DATABASE rather than stored and left to fail on a later read.
"""

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import exc as sa_exc
from sqlalchemy import select
from sqlalchemy.sql.sqltypes import Enum as SAEnum

from src.models.data_deletion_request import DataDeletionRequest, DeletionStatus
from src.models.data_export_request import DataExportRequest, ExportStatus
from src.models.file import File, MediaUse
from src.models.user import CreatedVia, SuspensionStatus, User


# The width every non-native enum column in this codebase uses.
ENUM_COLUMN_LENGTH = 50

# (model, column name, python enum, expected CHECK constraint name)
ENUM_COLUMNS = [
    (User, "created_via", CreatedVia, "ck_user_created_via"),
    (User, "suspension_status", SuspensionStatus, "ck_user_suspension_status"),
    (
        DataExportRequest,
        "status",
        ExportStatus,
        "ck_data_export_request_status",
    ),
    (
        DataDeletionRequest,
        "status",
        DeletionStatus,
        "ck_data_deletion_request_status",
    ),
    (File, "media_use", MediaUse, "ck_file_media_use"),
]

_IDS = [f"{m.__tablename__}.{c}" for m, c, _e, _n in ENUM_COLUMNS]


def _column_type(model, column_name) -> SAEnum:
    return model.__table__.c[column_name].type


async def _read_raw(async_session, model, column_name, row_id):
    """Read the column as a plain string, bypassing the ORM's enum decoding.

    Cast to String so SQLAlchemy's Enum result processor (the thing that raises
    ``LookupError`` on a bad value) does not run - we want to see exactly what
    bytes are in the column.
    """
    table = model.__table__
    return await async_session.scalar(
        select(sa.cast(table.c[column_name], sa.String)).where(table.c.id == row_id)
    )


async def _write_raw(async_session, model, column_name, row_id, value: str):
    """Write an arbitrary string into the enum column, bypassing the ORM.

    ``sa.literal(value, sa.String())`` carries its own type, so SQLAlchemy does
    NOT run the Enum bind processor (which would reject the value in Python and
    prove nothing about the database). Whatever refusal we see comes from the
    database itself.
    """
    table = model.__table__
    await async_session.execute(
        table.update()
        .where(table.c.id == row_id)
        .values({column_name: sa.literal(value, sa.String())})
    )


# ============================================================================
# DECLARED SHAPE
# ============================================================================


@pytest.mark.parametrize(
    "model,column_name,py_enum,constraint_name", ENUM_COLUMNS, ids=_IDS
)
def test_enum_column_is_width_50(model, column_name, py_enum, constraint_name):
    assert _column_type(model, column_name).length == ENUM_COLUMN_LENGTH


@pytest.mark.parametrize(
    "model,column_name,py_enum,constraint_name", ENUM_COLUMNS, ids=_IDS
)
def test_enum_column_has_generous_headroom(
    model, column_name, py_enum, constraint_name
):
    """Never size a VARCHAR enum to the exact longest member name.

    ``user.created_via`` was varchar(6) against a 6-character 'GOOGLE'; the very
    next provider member was going to be longer.
    """
    longest = max(len(member.name) for member in py_enum)
    assert ENUM_COLUMN_LENGTH >= longest * 2, (
        f"{model.__tablename__}.{column_name} has only "
        f"{ENUM_COLUMN_LENGTH - longest} spare characters"
    )


@pytest.mark.parametrize(
    "model,column_name,py_enum,constraint_name", ENUM_COLUMNS, ids=_IDS
)
def test_enum_column_emits_a_check_constraint(
    model, column_name, py_enum, constraint_name
):
    column_type = _column_type(model, column_name)

    assert column_type.native_enum is False
    assert column_type.create_constraint is True, (
        f"{model.__tablename__}.{column_name} is an unconstrained VARCHAR: "
        "bad values are accepted on write and only fail later on read"
    )
    assert column_type.name == constraint_name

    names = {c.name for c in model.__table__.constraints if c.name == constraint_name}
    assert names == {constraint_name}


@pytest.mark.parametrize(
    "model,column_name,py_enum,constraint_name", ENUM_COLUMNS, ids=_IDS
)
def test_check_constraint_lists_the_member_names_not_the_values(
    model, column_name, py_enum, constraint_name
):
    """The columns persist member NAMES ('GOOGLE'), not values ('google')."""
    column_type = _column_type(model, column_name)
    assert set(column_type.enums) == {member.name for member in py_enum}


# ============================================================================
# ROUND TRIP: every member survives a real write/read at full width
# ============================================================================


@pytest.fixture
def enum_row_factory(async_session, test_organization):
    """Persist one row of any of the five models, with its enum column set.

    Each row gets its own freshly created user: ``data_deletion_request`` has a
    unique constraint on ``user_id``, so a shared user would collide as soon as
    the test walks the second member of the enum.
    """

    async def build(model, column_name, value):
        owner = User(
            email=f"enum_{uuid.uuid4().hex[:10]}@test.com",
            password=None,
            email_verified=True,
            organization_id=test_organization.id,
        )
        async_session.add(owner)
        await async_session.flush()

        if model is User:
            row = User(
                email=f"enum_{uuid.uuid4().hex[:10]}@test.com",
                password=None,
                email_verified=True,
                organization_id=test_organization.id,
                **{column_name: value},
            )
        elif model is File:
            row = File(
                organization_id=test_organization.id,
                uploaded_by_user_id=owner.id,
                original_filename="f.png",
                storage_key=f"k/{uuid.uuid4().hex}",
                content_type="image/png",
                size_bytes=1,
                **{column_name: value},
            )
        else:
            row = model(
                user_id=owner.id,
                organization_id=test_organization.id,
                **{column_name: value},
            )

        async_session.add(row)
        await async_session.commit()
        return row

    return build


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model,column_name,py_enum,constraint_name", ENUM_COLUMNS, ids=_IDS
)
async def test_every_member_round_trips_through_the_database(
    async_session, enum_row_factory, model, column_name, py_enum, constraint_name
):
    for member in py_enum:
        row = await enum_row_factory(model, column_name, member)
        row_id = row.id

        async_session.expunge_all()
        fetched = (
            await async_session.execute(select(model).where(model.id == row_id))
        ).scalar_one()

        # A truncated write would come back as a LookupError here, not a
        # mismatch: SQLAlchemy cannot map the truncated string to a member.
        assert getattr(fetched, column_name) is member

        stored = await _read_raw(async_session, model, column_name, row_id)
        assert stored == member.name, "column stores the uppercase member NAME"
        assert len(stored) <= ENUM_COLUMN_LENGTH


# ============================================================================
# NEGATIVE: the DATABASE rejects an invalid value
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model,column_name,py_enum,constraint_name", ENUM_COLUMNS, ids=_IDS
)
async def test_database_rejects_a_value_outside_the_enum(
    async_session, enum_row_factory, model, column_name, py_enum, constraint_name
):
    """Written as raw SQL on purpose: the ORM's own validation is not the point.

    Before ``create_constraint=True`` this UPDATE succeeded, and the damage only
    surfaced on a later SELECT as a ``LookupError``.
    """
    row = await enum_row_factory(model, column_name, next(iter(py_enum)))
    row_id = row.id

    with pytest.raises(sa_exc.IntegrityError):
        await _write_raw(async_session, model, column_name, row_id, "NOT_A_REAL_MEMBER")
    await async_session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model,column_name,py_enum,constraint_name", ENUM_COLUMNS, ids=_IDS
)
async def test_database_rejects_the_lowercase_enum_value(
    async_session, enum_row_factory, model, column_name, py_enum, constraint_name
):
    """The classic drift: writing the enum VALUE where the NAME is stored.

    Migration 9ae4b5522102 exists because exactly this mix-up shipped once
    already, for the native ``onboarding_status`` enum.
    """
    member = next(iter(py_enum))
    if member.value == member.name:
        pytest.skip("member name and value are identical for this enum")

    row = await enum_row_factory(model, column_name, member)
    row_id = row.id

    with pytest.raises(sa_exc.IntegrityError):
        await _write_raw(async_session, model, column_name, row_id, member.value)
    await async_session.rollback()


@pytest.mark.asyncio
async def test_microsoft_would_fit_the_column_but_needs_the_check_widened():
    """``CreatedVia.MICROSOFT`` (9 chars) no longer overflows varchar(6).

    Enabling it is still a two-part change - the model member AND a migration
    updating ``ck_user_created_via`` - and this test documents that, so nobody
    uncomments the member and ships a CheckViolation instead of a truncation.
    """
    column_type = _column_type(User, "created_via")

    assert len("MICROSOFT") <= column_type.length
    assert "MICROSOFT" not in column_type.enums, (
        "CreatedVia.MICROSOFT is still commented out; enabling it must be "
        "accompanied by a migration that recreates ck_user_created_via"
    )
