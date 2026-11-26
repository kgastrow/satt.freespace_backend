"""
Unit tests pinning the exact Redis keys the queue health service reads.

The pre-fix service read arq's default queue key, scanned `arq:health:*` and
`arq:job-result:*`, and parsed the heartbeat value as a timestamp - none of
which arq writes in that shape. These tests fail loudly if the key contract
regresses.
"""

from unittest.mock import AsyncMock, patch

from src.constants.queues import (
    ARQ_HEALTH_CHECK_KEY,
    ARQ_IN_PROGRESS_KEY_PREFIX,
    ARQ_IN_PROGRESS_TIMEOUT_SECONDS,
    ARQ_JOB_KEY_PREFIX,
    ARQ_QUEUE_NAME,
)
from src.services.queue_health import QueueHealthService


class _FakeRedis:
    """Minimal stub of the decoding Redis client used by the health service."""

    def __init__(self, *, strings=None, ttls=None, in_progress=None, zsets=None):
        self.strings = strings or {}
        self.ttls = ttls or {}
        self.in_progress = in_progress or []
        self.zsets = zsets or {}
        self.zcard_calls: list[str] = []
        self.scan_patterns: list[str] = []

    async def ping(self):
        return True

    async def zcard(self, key):
        self.zcard_calls.append(key)
        return self.zsets.get(key, 0)

    async def get(self, key):
        return self.strings.get(key)

    async def pttl(self, key):
        return self.ttls.get(key, -2)

    async def exists(self, key):
        return 1 if key in self.strings else 0

    async def scan_iter(self, match=None, count=None):
        self.scan_patterns.append(match)
        for key in self.in_progress:
            yield key


def _service(fake: _FakeRedis) -> QueueHealthService:
    service = QueueHealthService()
    service.set_redis(fake)  # type: ignore[arg-type]
    return service


class TestQueueDepthKey:
    async def test_reads_app_specific_queue_name(self):
        fake = _FakeRedis(zsets={ARQ_QUEUE_NAME: 7, "arq:queue": 999})
        depth = await _service(fake).get_queue_depth()

        assert depth == 7
        assert fake.zcard_calls == [ARQ_QUEUE_NAME]


class TestWorkerHeartbeat:
    async def test_key_existence_is_the_liveness_signal(self):
        # arq's value is a human-readable info string, not a timestamp.
        fake = _FakeRedis(
            strings={ARQ_HEALTH_CHECK_KEY: "Sep-03 21:10:00 j_complete=4 j_failed=0"},
            ttls={ARQ_HEALTH_CHECK_KEY: 25_000},
        )

        workers = await _service(fake).get_worker_status()

        assert len(workers) == 1
        assert workers[0]["is_online"] is True
        assert workers[0]["worker_id"] == ARQ_HEALTH_CHECK_KEY
        assert workers[0]["seconds_to_heartbeat_expiry"] == 25

    async def test_absent_key_reports_no_workers(self):
        workers = await _service(_FakeRedis()).get_worker_status()

        assert workers == []

    async def test_health_is_unhealthy_when_no_worker_is_online(self):
        service = _service(_FakeRedis())
        health = await service.check_health()

        assert health["workers_online"] == 0
        assert health["is_healthy"] is False
        assert any("worker" in issue.lower() for issue in health["issues"])


class TestStuckJobs:
    async def test_elapsed_time_derived_from_in_progress_pttl(self):
        job_id = "abc123"
        elapsed = 250
        fake = _FakeRedis(
            in_progress=[f"{ARQ_IN_PROGRESS_KEY_PREFIX}{job_id}"],
            ttls={
                f"{ARQ_IN_PROGRESS_KEY_PREFIX}{job_id}": (
                    ARQ_IN_PROGRESS_TIMEOUT_SECONDS - elapsed
                )
                * 1000
            },
            # Job key still present => genuinely running.
            strings={f"{ARQ_JOB_KEY_PREFIX}{job_id}": "payload"},
        )
        service = _service(fake)

        with patch.object(service, "_get_job_function", AsyncMock(return_value=None)):
            stuck = await service.get_stuck_jobs(stuck_threshold_minutes=1)

        assert fake.scan_patterns == [f"{ARQ_IN_PROGRESS_KEY_PREFIX}*"]
        assert len(stuck) == 1
        assert stuck[0]["job_id"] == job_id
        assert stuck[0]["duration_minutes"] == elapsed // 60
        # A stuck job with no resolvable name is still a stuck job.
        assert stuck[0]["function"] == "unknown"

    async def test_finished_cron_is_not_reported_stuck(self):
        # arq re-expires a finished cron's in-progress key to 60s and deletes
        # the job key. The shortened TTL alone looks like a long-running job.
        job_id = "cronjob"
        fake = _FakeRedis(
            in_progress=[f"{ARQ_IN_PROGRESS_KEY_PREFIX}{job_id}"],
            ttls={f"{ARQ_IN_PROGRESS_KEY_PREFIX}{job_id}": 60_000},
            strings={},
        )
        service = _service(fake)

        stuck = await service.get_stuck_jobs(stuck_threshold_minutes=1)

        assert stuck == []

    async def test_job_below_threshold_is_not_stuck(self):
        job_id = "fresh"
        fake = _FakeRedis(
            in_progress=[f"{ARQ_IN_PROGRESS_KEY_PREFIX}{job_id}"],
            ttls={
                f"{ARQ_IN_PROGRESS_KEY_PREFIX}{job_id}": (
                    ARQ_IN_PROGRESS_TIMEOUT_SECONDS - 10
                )
                * 1000
            },
            strings={f"{ARQ_JOB_KEY_PREFIX}{job_id}": "payload"},
        )

        stuck = await _service(fake).get_stuck_jobs(stuck_threshold_minutes=4)

        assert stuck == []

    async def test_threshold_above_observability_ceiling_warns(self):
        fake = _FakeRedis()
        service = _service(fake)

        with patch("src.services.queue_health.logger") as mock_logger:
            await service.get_stuck_jobs(stuck_threshold_minutes=30)

        mock_logger.warning.assert_called_once()
        assert "always be 0" in mock_logger.warning.call_args.args[0]


class TestDefaults:
    def test_default_threshold_is_below_the_in_progress_ceiling(self):
        assert (
            QueueHealthService.STUCK_JOB_MINUTES * 60 < ARQ_IN_PROGRESS_TIMEOUT_SECONDS
        )
