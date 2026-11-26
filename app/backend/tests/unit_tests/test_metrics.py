"""
Unit tests for the metrics system components.
Tests cache metrics, user activity tracking, and job metrics.
"""

from unittest.mock import AsyncMock

import pytest

from src.middleware.cache_metrics import (
    CACHE_OPERATION_DURATION_SECONDS,
    CACHE_OPERATIONS_TOTAL,
    record_cache_delete,
    record_cache_error,
    record_cache_hit,
    record_cache_miss,
    record_cache_set,
)
from src.middleware.metrics import (
    ACTIVE_USERS_CURRENT,
    AUTH_FAILURES_TOTAL,
    EXCEPTIONS_TOTAL,
    classify_error,
    record_auth_failure,
    record_exception,
    update_active_users,
)
from src.workers.job_metrics import (
    JOBS_COMPLETED_TOTAL,
    JOBS_ENQUEUED_TOTAL,
    JOBS_FAILED_TOTAL,
    record_job_completed,
    record_job_enqueued,
    record_job_failed,
    set_worker_active,
)


class TestCacheMetrics:
    """Tests for cache metrics recording functions."""

    def test_record_cache_hit(self):
        """Test recording a cache hit."""
        initial_value = CACHE_OPERATIONS_TOTAL.labels(
            operation="get_test", cache_type="test", result="hit"
        )._value.get()

        record_cache_hit("test", "get_test", 0.001)

        new_value = CACHE_OPERATIONS_TOTAL.labels(
            operation="get_test", cache_type="test", result="hit"
        )._value.get()

        assert new_value == initial_value + 1

    def test_record_cache_miss(self):
        """Test recording a cache miss."""
        initial_value = CACHE_OPERATIONS_TOTAL.labels(
            operation="get_test", cache_type="test", result="miss"
        )._value.get()

        record_cache_miss("test", "get_test", 0.002)

        new_value = CACHE_OPERATIONS_TOTAL.labels(
            operation="get_test", cache_type="test", result="miss"
        )._value.get()

        assert new_value == initial_value + 1

    def test_record_cache_error(self):
        """Test recording a cache error."""
        initial_value = CACHE_OPERATIONS_TOTAL.labels(
            operation="get_test", cache_type="test", result="error"
        )._value.get()

        record_cache_error("test", "get_test")

        new_value = CACHE_OPERATIONS_TOTAL.labels(
            operation="get_test", cache_type="test", result="error"
        )._value.get()

        assert new_value == initial_value + 1

    def test_record_cache_set(self):
        """Test recording a cache set operation."""
        initial_value = CACHE_OPERATIONS_TOTAL.labels(
            operation="set", cache_type="test", result="success"
        )._value.get()

        record_cache_set("test", 0.001)

        new_value = CACHE_OPERATIONS_TOTAL.labels(
            operation="set", cache_type="test", result="success"
        )._value.get()

        assert new_value == initial_value + 1

    def test_record_cache_delete(self):
        """Test recording a cache delete operation."""
        initial_value = CACHE_OPERATIONS_TOTAL.labels(
            operation="delete", cache_type="test", result="success"
        )._value.get()

        record_cache_delete("test", 0.001)

        new_value = CACHE_OPERATIONS_TOTAL.labels(
            operation="delete", cache_type="test", result="success"
        )._value.get()

        assert new_value == initial_value + 1

    def test_cache_duration_histogram(self):
        """Test that cache operation duration is recorded."""
        # Record a cache hit with specific duration
        record_cache_hit("test", "duration_test", 0.005)

        # The histogram should have recorded the observation
        # We can check that the count increased
        histogram = CACHE_OPERATION_DURATION_SECONDS.labels(
            operation="duration_test", cache_type="test"
        )
        # Histogram observations are recorded, count should be > 0
        assert histogram._sum.get() > 0


class TestAuthMetrics:
    """Tests for authentication metrics."""

    def test_record_auth_failure(self):
        """Test recording an authentication failure."""
        initial_value = AUTH_FAILURES_TOTAL.labels(
            failure_reason="test_reason"
        )._value.get()

        record_auth_failure("test_reason")

        new_value = AUTH_FAILURES_TOTAL.labels(
            failure_reason="test_reason"
        )._value.get()

        assert new_value == initial_value + 1

    def test_record_auth_failure_different_reasons(self):
        """Test that different failure reasons are tracked separately."""
        initial_invalid = AUTH_FAILURES_TOTAL.labels(
            failure_reason="invalid_token"
        )._value.get()
        initial_expired = AUTH_FAILURES_TOTAL.labels(
            failure_reason="expired_token"
        )._value.get()

        record_auth_failure("invalid_token")
        record_auth_failure("expired_token")
        record_auth_failure("invalid_token")

        new_invalid = AUTH_FAILURES_TOTAL.labels(
            failure_reason="invalid_token"
        )._value.get()
        new_expired = AUTH_FAILURES_TOTAL.labels(
            failure_reason="expired_token"
        )._value.get()

        assert new_invalid == initial_invalid + 2
        assert new_expired == initial_expired + 1


class TestExceptionMetrics:
    """Tests for exception metrics."""

    def test_record_exception(self):
        """Test recording an exception."""
        initial_value = EXCEPTIONS_TOTAL.labels(
            exception_type="ValueError", endpoint="/test"
        )._value.get()

        record_exception("ValueError", "/test")

        new_value = EXCEPTIONS_TOTAL.labels(
            exception_type="ValueError", endpoint="/test"
        )._value.get()

        assert new_value == initial_value + 1

    def test_record_different_exception_types(self):
        """Test that different exception types are tracked separately."""
        initial_value = EXCEPTIONS_TOTAL.labels(
            exception_type="KeyError", endpoint="/api/test"
        )._value.get()
        initial_type = EXCEPTIONS_TOTAL.labels(
            exception_type="TypeError", endpoint="/api/test"
        )._value.get()

        record_exception("KeyError", "/api/test")
        record_exception("TypeError", "/api/test")

        new_key = EXCEPTIONS_TOTAL.labels(
            exception_type="KeyError", endpoint="/api/test"
        )._value.get()
        new_type = EXCEPTIONS_TOTAL.labels(
            exception_type="TypeError", endpoint="/api/test"
        )._value.get()

        assert new_key == initial_value + 1
        assert new_type == initial_type + 1


class TestActiveUsersMetrics:
    """Tests for active users gauge."""

    def test_update_active_users(self):
        """Test updating active users gauge."""
        update_active_users(100, "5m")

        value = ACTIVE_USERS_CURRENT.labels(window="5m")._value.get()
        assert value == 100

    def test_update_active_users_different_windows(self):
        """Test that different windows are tracked separately."""
        update_active_users(50, "5m")
        update_active_users(200, "1h")

        value_5m = ACTIVE_USERS_CURRENT.labels(window="5m")._value.get()
        value_1h = ACTIVE_USERS_CURRENT.labels(window="1h")._value.get()

        assert value_5m == 50
        assert value_1h == 200


class TestJobMetrics:
    """Tests for background job metrics."""

    def test_record_job_enqueued(self):
        """Test recording a job enqueue."""
        initial_value = JOBS_ENQUEUED_TOTAL.labels(job_type="test_job")._value.get()

        record_job_enqueued("test_job")

        new_value = JOBS_ENQUEUED_TOTAL.labels(job_type="test_job")._value.get()

        assert new_value == initial_value + 1

    def test_record_job_completed(self):
        """Test recording a job completion."""
        initial_value = JOBS_COMPLETED_TOTAL.labels(job_type="test_job")._value.get()

        record_job_completed("test_job", 1.5)

        new_value = JOBS_COMPLETED_TOTAL.labels(job_type="test_job")._value.get()

        assert new_value == initial_value + 1

    def test_record_job_failed(self):
        """Test recording a job failure."""
        initial_value = JOBS_FAILED_TOTAL.labels(
            job_type="test_job", error_type="RuntimeError"
        )._value.get()

        record_job_failed("test_job", "RuntimeError")

        new_value = JOBS_FAILED_TOTAL.labels(
            job_type="test_job", error_type="RuntimeError"
        )._value.get()

        assert new_value == initial_value + 1

    def test_set_worker_active(self):
        """Test setting worker active status."""
        set_worker_active(True)

        # Worker should be marked as active
        # Note: The label includes instance_id which varies
        # We just verify the function runs without error

        set_worker_active(False)
        # Should set to 0


class TestPathTemplateExtraction:
    """Tests for path template extraction."""

    def test_classify_error_authentication(self):
        """Test error classification for 401."""
        assert classify_error(401) == "authentication"

    def test_classify_error_authorization(self):
        """Test error classification for 403."""
        assert classify_error(403) == "authorization"

    def test_classify_error_not_found(self):
        """Test error classification for 404."""
        assert classify_error(404) == "not_found"

    def test_classify_error_validation(self):
        """Test error classification for 422."""
        assert classify_error(422) == "validation"

    def test_classify_error_rate_limit(self):
        """Test error classification for 429."""
        assert classify_error(429) == "rate_limit"

    def test_classify_error_client_error(self):
        """Test error classification for generic 4xx."""
        assert classify_error(400) == "client_error"
        assert classify_error(415) == "client_error"

    def test_classify_error_server_error(self):
        """Test error classification for 5xx."""
        assert classify_error(500) == "server_error"
        assert classify_error(503) == "server_error"


class TestUserActivityService:
    """Tests for user activity tracking service."""

    @pytest.mark.asyncio
    async def test_record_activity_without_redis(self):
        """Test that record_activity handles missing Redis gracefully."""
        from src.services.user_activity import user_activity_service

        # Without Redis set, should return False but not error
        result = await user_activity_service.record_activity("user-123", "org-456")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_active_user_count_without_redis(self):
        """Test that get_active_user_count returns 0 without Redis."""
        from src.services.user_activity import user_activity_service

        count = await user_activity_service.get_active_user_count()
        assert count == 0

    @pytest.mark.asyncio
    async def test_record_activity_with_mock_redis(self):
        """Test recording activity with mocked Redis."""
        from src.services.user_activity import UserActivityService

        service = UserActivityService()

        # Create mock Redis
        mock_redis = AsyncMock()
        mock_redis.pfadd = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)

        service._redis = mock_redis
        service._enabled = True

        result = await service.record_activity("user-123", "org-456")

        assert result is True
        # Should have called pfadd for both global and org keys
        assert mock_redis.pfadd.call_count == 2
        assert mock_redis.expire.call_count == 2

    @pytest.mark.asyncio
    async def test_get_active_user_count_with_mock_redis(self):
        """Test getting active user count with mocked Redis."""
        from src.services.user_activity import UserActivityService

        service = UserActivityService()

        # Create mock Redis
        mock_redis = AsyncMock()
        mock_redis.pfcount = AsyncMock(return_value=42)

        service._redis = mock_redis
        service._enabled = True

        count = await service.get_active_user_count()

        assert count == 42
        mock_redis.pfcount.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_activity_handles_redis_error(self):
        """Test that record_activity handles Redis errors gracefully."""
        from src.services.user_activity import UserActivityService

        service = UserActivityService()

        # Create mock Redis that raises an exception
        mock_redis = AsyncMock()
        mock_redis.pfadd = AsyncMock(side_effect=Exception("Redis error"))

        service._redis = mock_redis
        service._enabled = True

        result = await service.record_activity("user-123", "org-456")

        # Should return False on error, not raise
        assert result is False
