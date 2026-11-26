"""
Unit tests pinning the recording behaviour of the ARQ job metrics decorators.

Both decorators must write rolling stats to Redis AND a persistent execution
row to the database regardless of METRICS_ENABLED - that setting is a
Prometheus-only switch. instrument_cron_task must do so on both the success
and the failure path.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.workers.job_metrics import instrument_cron_task, instrument_task


class _StubSession:
    """Async context manager standing in for an AsyncSession."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _stub_ctx():
    return {"session_factory": lambda: _StubSession()}


class _StubJobStats:
    """Stand-in for job_stats_service that records every call."""

    def __init__(self):
        self.executions: list[dict] = []

    async def is_job_disabled(self, job_type: str) -> bool:
        return False

    async def record_job_execution(
        self, job_type: str, status: str, duration_ms: float
    ):
        self.executions.append(
            {"job_type": job_type, "status": status, "duration_ms": duration_ms}
        )


@pytest.fixture
def recorded():
    """Patch the Redis stats service and the DB writer, metrics disabled."""
    stats = _StubJobStats()
    db_calls = AsyncMock()

    with (
        patch("src.services.job_stats.job_stats_service", stats),
        patch("src.workers.job_metrics._record_to_db", db_calls),
        patch("src.workers.job_metrics.settings.METRICS_ENABLED", False),
    ):
        yield stats, db_calls


class TestInstrumentTaskRecording:
    """METRICS_ENABLED=False must not disable Redis/DB recording."""

    async def test_success_records_to_redis_and_db(self, recorded):
        stats, db_calls = recorded

        @instrument_task
        async def send_email_task(ctx):
            return "sent"

        result = await send_email_task(_stub_ctx())

        assert result == "sent"
        assert [e["status"] for e in stats.executions] == ["success"]
        assert stats.executions[0]["job_type"] == "send_email_task"

        db_calls.assert_awaited_once()
        args = db_calls.await_args.args
        assert args[1] == "send_email_task"
        assert args[2] == "success"

    async def test_failure_records_to_redis_and_db(self, recorded):
        stats, db_calls = recorded

        @instrument_task
        async def failing_task(ctx):
            raise ValueError("boom")

        with pytest.raises(ValueError):
            await failing_task(_stub_ctx())

        assert [e["status"] for e in stats.executions] == ["failure"]

        db_calls.assert_awaited_once()
        kwargs = db_calls.await_args.kwargs
        assert db_calls.await_args.args[2] == "failure"
        assert kwargs["error_type"] == "ValueError"
        assert kwargs["error_message"] == "boom"


class TestInstrumentCronTaskRecording:
    """The cron decorator must write to the database on both paths."""

    async def test_success_records_to_redis_and_db(self, recorded):
        stats, db_calls = recorded

        @instrument_cron_task
        async def collect_metrics_task(ctx):
            return "ok"

        result = await collect_metrics_task(_stub_ctx())

        assert result == "ok"
        assert [e["status"] for e in stats.executions] == ["success"]

        db_calls.assert_awaited_once()
        args = db_calls.await_args.args
        assert args[1] == "collect_metrics_task"
        assert args[2] == "success"

    async def test_failure_records_to_redis_and_db(self, recorded):
        stats, db_calls = recorded

        @instrument_cron_task
        async def failing_cron_task(ctx):
            raise RuntimeError("cron boom")

        with pytest.raises(RuntimeError):
            await failing_cron_task(_stub_ctx())

        assert [e["status"] for e in stats.executions] == ["failure"]

        db_calls.assert_awaited_once()
        kwargs = db_calls.await_args.kwargs
        assert db_calls.await_args.args[2] == "failure"
        assert kwargs["error_type"] == "RuntimeError"
        assert kwargs["error_message"] == "cron boom"


class TestDisabledJobStillShortCircuits:
    """A disabled job must skip execution without recording."""

    async def test_disabled_job_is_skipped(self):
        stats = _StubJobStats()
        stats.is_job_disabled = AsyncMock(return_value=True)
        db_calls = AsyncMock()
        ran = False

        @instrument_task
        async def some_task(ctx):
            nonlocal ran
            ran = True

        with (
            patch("src.services.job_stats.job_stats_service", stats),
            patch("src.workers.job_metrics._record_to_db", db_calls),
        ):
            result = await some_task(_stub_ctx())

        assert ran is False
        assert result == {"status": "skipped", "reason": "job_disabled"}
        db_calls.assert_not_awaited()
