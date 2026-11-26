"""
Database query micro-benchmarks using pytest-benchmark.

Tests measure query performance for paginated user listing, audit log queries,
and tenant isolation overhead.
"""

import asyncio

import pytest

from src.crud.audit_log import get_audit_logs
from src.crud.user import get_users


def _run(coro):
    """Helper to run an async coroutine synchronously for benchmark."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.mark.benchmark(group="db-queries")
def test_list_users_performance(
    benchmark, async_session, test_organization, seeded_users
):
    """List users query should complete quickly with 1000 rows (paginated to 50)."""

    def run():
        return _run(
            get_users(
                async_session,
                organization_id=str(test_organization.id),
                limit=50,
                offset=0,
            )
        )

    result = benchmark.pedantic(run, rounds=50, warmup_rounds=5)
    assert result is not None
    users, total = result
    assert total == 1000
    assert len(users) == 50


@pytest.mark.benchmark(group="db-queries")
def test_list_users_deep_pagination(
    benchmark, async_session, test_organization, seeded_users
):
    """Paginated query at a deep offset should still perform well."""

    def run():
        return _run(
            get_users(
                async_session,
                organization_id=str(test_organization.id),
                limit=50,
                offset=900,
            )
        )

    result = benchmark.pedantic(run, rounds=50, warmup_rounds=5)
    users, total = result
    assert total == 1000
    assert len(users) == 50  # 900..950 out of 1000


@pytest.mark.benchmark(group="db-queries")
def test_audit_log_query_performance(
    benchmark, async_session, test_organization, seeded_audit_logs
):
    """Audit log query with 10k rows, paginated to 100."""

    def run():
        return _run(
            get_audit_logs(
                async_session,
                organization_id=str(test_organization.id),
                limit=100,
                offset=0,
            )
        )

    result = benchmark.pedantic(run, rounds=30, warmup_rounds=3)
    assert result is not None
    logs, total = result
    assert total == 10000
    assert len(logs) == 100


@pytest.mark.benchmark(group="db-queries")
def test_tenant_isolation_no_cross_leak(
    benchmark, async_session, test_organization, seeded_users, other_organization
):
    """Verify tenant filter doesn't degrade with multiple tenants seeded."""

    def run():
        return _run(
            get_users(
                async_session,
                organization_id=str(test_organization.id),
                limit=50,
                offset=0,
            )
        )

    result = benchmark.pedantic(run, rounds=50, warmup_rounds=5)
    users, total = result
    # Should only see users from test_organization, not other_organization
    assert total == 1000


@pytest.mark.benchmark(group="db-queries")
def test_other_tenant_isolation(
    benchmark, async_session, test_organization, seeded_users, other_organization
):
    """Query the other tenant to confirm isolation from both directions."""

    def run():
        return _run(
            get_users(
                async_session,
                organization_id=str(other_organization.id),
                limit=50,
                offset=0,
            )
        )

    result = benchmark.pedantic(run, rounds=50, warmup_rounds=5)
    users, total = result
    assert total == 500
