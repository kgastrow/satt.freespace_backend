"""
API-test fixtures.

WHY main.async_engine IS REPOINTED HERE
---------------------------------------
The suite runs against an in-memory SQLite database injected through the
``get_async_session`` dependency override (see tests/conftest.py). Nothing
provisions the Postgres that ``src.database.async_engine`` was built from, so
inside the test process that engine is a dangling handle: connecting to it
fails with an authentication error against a database the suite never uses.

That did not matter while ``/health/detailed`` answered HTTP 200 no matter what
it found - which was the bug this endpoint was fixed for. Now that a hard
dependency failure returns 503, an unrepointed engine would make every request
to that endpoint report a database outage that is an artefact of the test
environment rather than of the code under test.

So the endpoint is pointed at the database this suite actually has. Tests that
want to see a failing database patch ``main.async_engine`` themselves.
"""

import pytest
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture(scope="session")
def _health_check_engine():
    """One SQLite engine for the whole session; the health probe only pings it."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    yield engine


@pytest.fixture(autouse=True)
def _point_health_check_at_test_database(_health_check_engine, monkeypatch):
    import main

    monkeypatch.setattr(main, "async_engine", _health_check_engine)
    yield
