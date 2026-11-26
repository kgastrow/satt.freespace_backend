"""
Tests that the DATABASE_POOL_* settings are actually read.

They used to be dead config: ``DATABASE_POOL_SIZE``, ``DATABASE_MAX_OVERFLOW``,
``DATABASE_POOL_TIMEOUT`` and ``DATABASE_POOL_PRE_PING`` were declared on
``Settings`` and loaded from config.json, and nothing anywhere read them. The
application engine was a hardcoded ``NullPool``. A config surface that accepts
values it silently ignores is worse than one that does not offer them at all -
it tells operators they have a knob when they have a decorative screw.

They are now opt-in behind ``DATABASE_POOL_ENABLED`` and every one of them is
read when it is on. These tests assert exactly that, so the settings cannot
quietly go dead again.
"""

import pytest
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from src import database as database_module
from src.core.config import settings


@pytest.fixture
def captured_engine_kwargs(monkeypatch) -> dict:
    """Capture what create_async_engine is actually handed."""
    captured: dict = {}

    def _fake_create_async_engine(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        database_module, "create_async_engine", _fake_create_async_engine
    )
    return captured


def test_pool_disabled_by_default_uses_nullpool(monkeypatch, captured_engine_kwargs):
    """The shipped default is unchanged: NullPool, PgBouncer does the pooling."""
    monkeypatch.setattr(settings, "DATABASE_POOL_ENABLED", False)

    database_module.create_async_engine_from_config(use_direct=False)

    assert captured_engine_kwargs["poolclass"] is NullPool
    # Nothing to size, so these must not be passed at all.
    for key in ("pool_size", "max_overflow", "pool_timeout", "pool_pre_ping"):
        assert key not in captured_engine_kwargs
    # The PgBouncer transaction-pooling requirement still holds.
    assert captured_engine_kwargs["connect_args"]["statement_cache_size"] == 0


def test_every_pool_setting_is_read_when_pooling_is_enabled(
    monkeypatch, captured_engine_kwargs
):
    """Each declared DATABASE_POOL_* value must reach the engine verbatim."""
    monkeypatch.setattr(settings, "DATABASE_POOL_ENABLED", True)
    monkeypatch.setattr(settings, "DATABASE_POOL_SIZE", 7)
    monkeypatch.setattr(settings, "DATABASE_MAX_OVERFLOW", 3)
    monkeypatch.setattr(settings, "DATABASE_POOL_TIMEOUT", 11)
    monkeypatch.setattr(settings, "DATABASE_POOL_RECYCLE", 123)
    monkeypatch.setattr(settings, "DATABASE_POOL_PRE_PING", False)

    database_module.create_async_engine_from_config(use_direct=False)

    assert captured_engine_kwargs["poolclass"] is AsyncAdaptedQueuePool
    assert captured_engine_kwargs["pool_size"] == 7
    assert captured_engine_kwargs["max_overflow"] == 3
    assert captured_engine_kwargs["pool_timeout"] == 11
    assert captured_engine_kwargs["pool_recycle"] == 123
    assert captured_engine_kwargs["pool_pre_ping"] is False


def test_pooling_disables_both_prepared_statement_caches_and_uniquifies_names(
    monkeypatch, captured_engine_kwargs
):
    """The PgBouncer transaction-pooling requirement, in full.

    Disabling only asyncpg's ``statement_cache_size`` is the trap: SQLAlchemy's
    asyncpg dialect keeps its OWN cache and still issues a server-side NAMED
    prepare on every execute, using a per-connection counter for the name. Those
    names repeat across pooled connections, so under transaction pooling a name
    prepared on one backend is referenced on another -> intermittent
    ``prepared statement "__asyncpg_stmt_N__" does not exist``.
    """
    monkeypatch.setattr(settings, "DATABASE_POOL_ENABLED", True)

    database_module.create_async_engine_from_config(use_direct=False)

    connect_args = captured_engine_kwargs["connect_args"]
    assert connect_args["statement_cache_size"] == 0
    assert connect_args["prepared_statement_cache_size"] == 0
    assert (
        connect_args["prepared_statement_name_func"]
        is database_module._unique_prepared_statement_name
    )


def test_prepared_statement_names_are_unique():
    """A per-connection counter would repeat across backends; these must not."""
    names = {database_module._unique_prepared_statement_name() for _ in range(1000)}
    assert len(names) == 1000


def test_real_engine_honours_the_configured_pool_size(monkeypatch):
    """End to end through SQLAlchemy, not just the kwargs we pass."""
    monkeypatch.setattr(settings, "DATABASE_POOL_ENABLED", True)
    monkeypatch.setattr(settings, "DATABASE_POOL_SIZE", 9)
    monkeypatch.setattr(settings, "DATABASE_MAX_OVERFLOW", 4)
    monkeypatch.setattr(settings, "DATABASE_POOL_TIMEOUT", 6)

    engine = database_module.create_async_engine_from_config(use_direct=False)
    try:
        pool = engine.pool
        assert isinstance(pool, AsyncAdaptedQueuePool)
        assert pool.size() == 9
        assert pool._max_overflow == 4
        assert pool._timeout == 6
    finally:
        engine.sync_engine.pool.dispose()


def test_direct_engine_still_reads_pool_recycle(monkeypatch, captured_engine_kwargs):
    """DATABASE_POOL_RECYCLE was the one setting already wired; keep it wired."""
    monkeypatch.setattr(settings, "DATABASE_POOL_RECYCLE", 4242)

    database_module.create_async_engine_from_config(use_direct=True)

    assert captured_engine_kwargs["pool_recycle"] == 4242
