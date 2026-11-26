"""
Unit tests for background jobs monitoring.
Tests job types constants and job stats service.
"""

from unittest.mock import AsyncMock

import pytest


class TestJobTypesConstants:
    """Tests for job types constants."""

    def test_get_all_job_types(self):
        """Test getting all job types."""
        from src.constants.job_types import JOB_TYPES, get_all_job_types

        job_types = get_all_job_types()

        assert len(job_types) > 0
        assert job_types == JOB_TYPES

    def test_get_job_type_existing(self):
        """Test getting an existing job type."""
        from src.constants.job_types import get_job_type

        job_type = get_job_type("send_email_task")

        assert job_type is not None
        assert job_type.code == "send_email_task"
        assert job_type.name == "Send Email"
        assert job_type.category == "email"
        assert job_type.is_cron is False

    def test_get_job_type_not_found(self):
        """Test getting a non-existent job type."""
        from src.constants.job_types import get_job_type

        job_type = get_job_type("nonexistent_job")

        assert job_type is None

    def test_get_job_types_by_category(self):
        """Test getting job types by category."""
        from src.constants.job_types import get_job_types_by_category

        email_jobs = get_job_types_by_category("email")

        assert len(email_jobs) >= 1
        for job in email_jobs:
            assert job.category == "email"

    def test_job_types_by_code_lookup(self):
        """Test JOB_TYPES_BY_CODE lookup dictionary."""
        from src.constants.job_types import JOB_TYPE_CODES, JOB_TYPES_BY_CODE

        # All codes should be in the lookup
        for code in JOB_TYPE_CODES:
            assert code in JOB_TYPES_BY_CODE
            assert JOB_TYPES_BY_CODE[code].code == code

    def test_all_job_types_have_required_fields(self):
        """Test all job types have required fields."""
        from src.constants.job_types import get_all_job_types

        for job_type in get_all_job_types():
            assert job_type.code, "Job type missing code"
            assert job_type.name, f"Job type {job_type.code} missing name"
            assert job_type.description, f"Job type {job_type.code} missing description"
            assert job_type.category, f"Job type {job_type.code} missing category"

    def test_cron_jobs_marked_correctly(self):
        """Test that cron jobs are marked with is_cron=True."""
        from src.constants.job_types import get_all_job_types

        cron_codes = [
            "cleanup_expired_otps_task",
            "cleanup_expired_refresh_tokens_task",
            "collect_metrics_task",
            "system_cron_scheduler_task",
        ]

        for job_type in get_all_job_types():
            if job_type.code in cron_codes:
                assert (
                    job_type.is_cron is True
                ), f"Job {job_type.code} should be marked as cron"


class TestJobStatsService:
    """Tests for job stats service."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = AsyncMock()
        mock.ping = AsyncMock()
        mock.zadd = AsyncMock()
        mock.zcard = AsyncMock(return_value=5)
        mock.zrange = AsyncMock(return_value=[])
        mock.expire = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock()
        return mock

    @pytest.mark.asyncio
    async def test_record_job_execution_success(self, mock_redis):
        """Test recording a successful job execution."""
        from src.services.job_stats import JobStatsService

        service = JobStatsService()
        service._redis = mock_redis
        service._enabled = True

        await service.record_job_execution(
            job_type="send_email_task",
            status="success",
            duration_ms=150.5,
        )

        # Verify zadd was called for executions and durations
        assert mock_redis.zadd.call_count >= 2
        assert mock_redis.expire.call_count >= 2

    @pytest.mark.asyncio
    async def test_record_job_execution_failure(self, mock_redis):
        """Test recording a failed job execution."""
        from src.services.job_stats import JobStatsService

        service = JobStatsService()
        service._redis = mock_redis
        service._enabled = True

        await service.record_job_execution(
            job_type="send_email_task",
            status="failure",
            duration_ms=50.0,
        )

        # Verify zadd was called for executions, failures, and durations
        assert mock_redis.zadd.call_count >= 3

    @pytest.mark.asyncio
    async def test_record_job_execution_redis_unavailable(self):
        """Test recording when Redis is unavailable."""
        from src.services.job_stats import JobStatsService

        service = JobStatsService()
        service._redis = None
        service._enabled = False

        # Should not raise an error
        await service.record_job_execution(
            job_type="send_email_task",
            status="success",
            duration_ms=100.0,
        )

    @pytest.mark.asyncio
    async def test_get_job_stats_empty(self, mock_redis):
        """Test getting stats when no executions exist."""
        from src.services.job_stats import JobStatsService

        mock_redis.zcard = AsyncMock(return_value=0)
        mock_redis.zrange = AsyncMock(return_value=[])

        service = JobStatsService()
        service._redis = mock_redis
        service._enabled = True

        stats = await service.get_job_stats("send_email_task")

        assert stats["job_type"] == "send_email_task"
        assert stats["executions_24h"] == 0
        assert stats["failures_24h"] == 0
        assert stats["failure_rate"] == 0.0
        assert stats["avg_duration_ms"] == 0.0
        assert stats["last_execution"] is None

    @pytest.mark.asyncio
    async def test_get_job_stats_with_data(self, mock_redis):
        """Test getting stats with execution data."""
        import time

        from src.services.job_stats import JobStatsService

        now = time.time()
        mock_redis.zcard = AsyncMock(side_effect=[10, 2])  # executions, failures
        mock_redis.zrange = AsyncMock(
            side_effect=[
                # Durations
                [(f"{now}:100", now), (f"{now}:200", now)],
                # Last execution
                [(str(now), now)],
            ]
            * 24
        )

        service = JobStatsService()
        service._redis = mock_redis
        service._enabled = True

        stats = await service.get_job_stats("send_email_task", window_hours=1)

        assert stats["job_type"] == "send_email_task"
        assert stats["executions_24h"] == 10
        assert stats["failures_24h"] == 2
        assert stats["failure_rate"] == 20.0

    @pytest.mark.asyncio
    async def test_get_job_stats_redis_unavailable(self):
        """Test getting stats when Redis is unavailable."""
        from src.services.job_stats import JobStatsService

        service = JobStatsService()
        service._redis = None
        service._enabled = False

        stats = await service.get_job_stats("send_email_task")

        assert stats["job_type"] == "send_email_task"
        assert stats["executions_24h"] == 0
        assert stats["failures_24h"] == 0

    @pytest.mark.asyncio
    async def test_get_all_job_stats(self, mock_redis):
        """Test getting stats for multiple job types."""
        from src.services.job_stats import JobStatsService

        mock_redis.zcard = AsyncMock(return_value=5)
        mock_redis.zrange = AsyncMock(return_value=[])

        service = JobStatsService()
        service._redis = mock_redis
        service._enabled = True

        stats = await service.get_all_job_stats(
            ["send_email_task", "cleanup_expired_otps_task"]
        )

        assert len(stats) == 2
        assert stats[0]["job_type"] == "send_email_task"
        assert stats[1]["job_type"] == "cleanup_expired_otps_task"

    @pytest.mark.asyncio
    async def test_is_job_disabled_not_cached(self, mock_redis):
        """Test checking if job is disabled when not cached."""
        from src.services.job_stats import JobStatsService

        mock_redis.get = AsyncMock(return_value=None)

        service = JobStatsService()
        service._redis = mock_redis
        service._enabled = True

        is_disabled = await service.is_job_disabled("send_email_task")

        # Default to not disabled when not cached
        assert is_disabled is False

    @pytest.mark.asyncio
    async def test_is_job_disabled_cached_disabled(self, mock_redis):
        """Test checking if job is disabled when cached as disabled."""
        from src.services.job_stats import JobStatsService

        mock_redis.get = AsyncMock(return_value="0")

        service = JobStatsService()
        service._redis = mock_redis
        service._enabled = True

        is_disabled = await service.is_job_disabled("send_email_task")

        assert is_disabled is True

    @pytest.mark.asyncio
    async def test_is_job_disabled_cached_enabled(self, mock_redis):
        """Test checking if job is disabled when cached as enabled."""
        from src.services.job_stats import JobStatsService

        mock_redis.get = AsyncMock(return_value="1")

        service = JobStatsService()
        service._redis = mock_redis
        service._enabled = True

        is_disabled = await service.is_job_disabled("send_email_task")

        assert is_disabled is False

    @pytest.mark.asyncio
    async def test_set_job_enabled_cache(self, mock_redis):
        """Test setting job enabled cache."""
        from src.services.job_stats import JobStatsService

        service = JobStatsService()
        service._redis = mock_redis
        service._enabled = True

        await service.set_job_enabled_cache("send_email_task", True)

        mock_redis.set.assert_called_once()
        mock_redis.expire.assert_called()

    @pytest.mark.asyncio
    async def test_empty_stats_structure(self):
        """Test empty stats structure."""
        from src.services.job_stats import JobStatsService

        service = JobStatsService()
        stats = service._empty_stats("test_job")

        assert stats == {
            "job_type": "test_job",
            "executions_24h": 0,
            "failures_24h": 0,
            "failure_rate": 0.0,
            "avg_duration_ms": 0.0,
            "last_execution": None,
        }

    def test_get_hour_bucket(self):
        """Test hour bucket generation."""
        from datetime import datetime, timezone

        from src.services.job_stats import JobStatsService

        service = JobStatsService()

        # Test with specific timestamp
        dt = datetime(2025, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
        bucket = service._get_hour_bucket(dt)

        assert bucket == "2025061514"

    def test_get_redis_keys(self):
        """Test Redis key generation."""
        from src.services.job_stats import JobStatsService

        service = JobStatsService()

        exec_key = service._get_executions_key("test_job", "2025061514")
        fail_key = service._get_failures_key("test_job", "2025061514")
        dur_key = service._get_durations_key("test_job", "2025061514")

        assert exec_key == "job_stats:test_job:executions:2025061514"
        assert fail_key == "job_stats:test_job:failures:2025061514"
        assert dur_key == "job_stats:test_job:durations:2025061514"


class TestBackgroundJobsSerializers:
    """Tests for background jobs serializers."""

    def test_job_type_info_schema(self):
        """Test JobTypeInfo schema."""
        from src.serialisers.background_jobs import JobTypeInfo

        info = JobTypeInfo(
            code="test_job",
            name="Test Job",
            description="A test job",
            category="test",
            is_cron=False,
            enabled=True,
        )

        assert info.code == "test_job"
        assert info.name == "Test Job"
        assert info.enabled is True

    def test_job_type_stats_schema(self):
        """Test JobTypeStats schema."""
        from src.serialisers.background_jobs import JobTypeStats

        stats = JobTypeStats(
            job_type="test_job",
            name="Test Job",
            description="A test job",
            category="test",
            is_cron=False,
            enabled=True,
            executions_24h=100,
            failures_24h=5,
            failure_rate=5.0,
            avg_duration_ms=150.5,
            last_execution="2025-06-15T14:30:00Z",
        )

        assert stats.job_type == "test_job"
        assert stats.executions_24h == 100
        assert stats.failures_24h == 5
        assert stats.failure_rate == 5.0

    def test_queue_health_response_schema(self):
        """Test QueueHealthResponse schema."""
        from src.serialisers.background_jobs import QueueHealthResponse

        response = QueueHealthResponse(
            is_healthy=True,
            issues=[],
            queue_depth=10,
            depth_threshold=100,
            stuck_jobs_count=0,
            stuck_jobs=[],
            workers_online=3,
            workers_offline=0,
            total_workers=3,
            checked_at="2025-06-15T14:30:00Z",
        )

        assert response.is_healthy is True
        assert response.queue_depth == 10
        assert response.workers_online == 3

    def test_toggle_job_type_request_schema(self):
        """Test ToggleJobTypeRequest schema."""
        from src.serialisers.background_jobs import ToggleJobTypeRequest

        request = ToggleJobTypeRequest(enabled=False)

        assert request.enabled is False

    def test_toggle_job_type_response_schema(self):
        """Test ToggleJobTypeResponse schema."""
        from src.serialisers.background_jobs import ToggleJobTypeResponse

        response = ToggleJobTypeResponse(
            job_type="test_job",
            enabled=False,
            message="Job type disabled",
        )

        assert response.job_type == "test_job"
        assert response.enabled is False
        assert response.message == "Job type disabled"
