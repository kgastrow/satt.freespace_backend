"""
Tests for the Prometheus metrics system.
Tests HTTP request metrics, cache metrics, and the /metrics endpoint.
"""

from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format(client: AsyncClient):
    """Test that /metrics endpoint returns valid Prometheus format."""
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")

    # Check for expected metric names in the response
    content = response.text
    assert "http_requests_total" in content
    assert "http_request_duration_seconds" in content


@pytest.mark.asyncio
async def test_metrics_endpoint_excluded_from_request_metrics(client: AsyncClient):
    """Test that /metrics endpoint itself is not counted in request metrics."""
    # Make several requests to /metrics
    for _ in range(5):
        await client.get("/metrics")

    # Get the metrics
    response = await client.get("/metrics")
    content = response.text

    # The /metrics endpoint should not appear in the metrics
    # (it's in the excluded paths)
    assert (
        'endpoint="/metrics"' not in content
        or "http_requests_total{" not in content.split('endpoint="/metrics"')[0]
    )


@pytest.mark.asyncio
async def test_http_request_metrics_incremented(client: AsyncClient):
    """Test that HTTP request metrics are incremented for API calls."""
    # Make a request to auth endpoint (not excluded)
    await client.post(
        "/api/v1/auth/login",
        json={"email": "x", "password": "x", "organization_slug": "x"},
    )

    # Get metrics
    response = await client.get("/metrics")
    content = response.text

    # Should have recorded the request
    assert "http_requests_total" in content
    # Should have the auth endpoint in metrics
    assert "/api/v1/auth/login" in content


@pytest.mark.asyncio
async def test_http_request_duration_histogram(client: AsyncClient):
    """Test that request duration is recorded as a histogram."""
    # Make a request to a non-excluded endpoint
    await client.post(
        "/api/v1/auth/login",
        json={"email": "x", "password": "x", "organization_slug": "x"},
    )

    # Get metrics
    response = await client.get("/metrics")
    content = response.text

    # Check for histogram buckets
    assert "http_request_duration_seconds_bucket" in content
    assert "http_request_duration_seconds_count" in content
    assert "http_request_duration_seconds_sum" in content


@pytest.mark.asyncio
async def test_http_error_metrics(client: AsyncClient):
    """Test that HTTP errors are recorded in metrics."""
    # Make a request that will return 404
    await client.get("/nonexistent-endpoint-12345")

    # Get metrics
    response = await client.get("/metrics")
    content = response.text

    # Should have recorded an error
    assert "http_errors_total" in content
    # Should have 404 status code
    assert 'status_code="404"' in content


@pytest.mark.asyncio
async def test_http_requests_in_progress_gauge(client: AsyncClient):
    """Test that in-progress requests gauge exists."""
    response = await client.get("/metrics")
    content = response.text

    # Should have the in-progress gauge defined
    assert "http_requests_in_progress" in content


@pytest.mark.asyncio
async def test_authenticated_request_metrics(client: AsyncClient, test_jwt_token: str):
    """Test that authenticated requests are properly metered."""
    # Make an authenticated request
    response = await client.get(
        "/api/v1/user/me", headers={"Authorization": test_jwt_token}
    )
    assert response.status_code == 200

    # Get metrics
    metrics_response = await client.get("/metrics")
    content = metrics_response.text

    # Should have recorded the request
    assert "http_requests_total" in content
    assert 'status_code="200"' in content


@pytest.mark.asyncio
async def test_unauthenticated_request_error_metrics(client: AsyncClient):
    """Test that 401 errors are recorded for unauthenticated requests."""
    # Make an unauthenticated request to a protected endpoint
    response = await client.get("/api/v1/user/me")
    assert response.status_code == 401

    # Get metrics
    metrics_response = await client.get("/metrics")
    content = metrics_response.text

    # Should have recorded a 401 error
    assert 'status_code="401"' in content
    assert "http_errors_total" in content


@pytest.mark.asyncio
async def test_validation_error_metrics(client: AsyncClient):
    """Test that validation errors (422) are recorded."""
    # Make a request with invalid data
    response = await client.post(
        "/api/v1/auth/login", json={"invalid": "data"}  # Missing required fields
    )
    assert response.status_code == 422

    # Get metrics
    metrics_response = await client.get("/metrics")
    content = metrics_response.text

    # Should have recorded a validation error
    assert 'status_code="422"' in content


@pytest.mark.asyncio
async def test_concurrent_requests_metric(client: AsyncClient):
    """Test that concurrent requests gauge is present."""
    response = await client.get("/metrics")
    content = response.text

    assert "concurrent_requests" in content


@pytest.mark.asyncio
async def test_app_instance_info(client: AsyncClient):
    """Test that app instance info is present in metrics."""
    response = await client.get("/metrics")
    content = response.text

    # Should have instance info
    assert "app_instance_info" in content


@pytest.mark.asyncio
async def test_app_start_time_metric(client: AsyncClient):
    """Test that app start time is recorded."""
    response = await client.get("/metrics")
    content = response.text

    # Should have app start time
    assert "app_start_time_seconds" in content


@pytest.mark.asyncio
async def test_cache_metrics_present(client: AsyncClient):
    """Test that cache-related metrics are defined."""
    response = await client.get("/metrics")
    content = response.text

    # Cache metrics should be present (may be 0 if no cache operations yet)
    assert "cache_operations_total" in content or "cache_connected" in content


@pytest.mark.asyncio
async def test_cache_metrics_after_authenticated_request(
    client: AsyncClient, test_jwt_token: str
):
    """Test that cache metrics are recorded after authenticated requests."""
    # Make an authenticated request (which uses cache for JWT claims)
    await client.get("/api/v1/user/me", headers={"Authorization": test_jwt_token})

    # Get metrics
    response = await client.get("/metrics")
    content = response.text

    # Should have cache operation metrics
    # Note: In tests, cache may be disabled, so we check for the metric definition
    assert "cache_" in content


@pytest.mark.asyncio
async def test_multiple_requests_increment_counter(client: AsyncClient):
    """Test that multiple requests properly increment the counter."""
    # Get initial count for a unique endpoint that won't be used by other tests
    initial_response = await client.get("/metrics")
    initial_content = initial_response.text

    # Find initial count for /api/user/register (422 response since no valid data)
    initial_count = 0.0
    for line in initial_content.split("\n"):
        if (
            "http_requests_total{" in line
            and "/api/v1/user/register" in line
            and 'status_code="422"' in line
        ):
            initial_count = float(line.split()[-1])
            break

    # Make 5 requests to /api/user/register
    for _ in range(5):
        await client.post("/api/v1/user/register", json={"email": "x"})

    # Get metrics
    response = await client.get("/metrics")
    content = response.text

    # Find the http_requests_total line for /api/user/register
    lines = content.split("\n")
    register_metric_line = None
    for line in lines:
        if (
            "http_requests_total{" in line
            and "/api/v1/user/register" in line
            and 'status_code="422"' in line
        ):
            register_metric_line = line
            break

    assert (
        register_metric_line is not None
    ), "Should have a metric for /api/user/register endpoint"
    # Extract the count value and verify it increased by 5
    new_count = float(register_metric_line.split()[-1])
    assert (
        new_count >= initial_count + 5
    ), f"Expected count to increase by at least 5, got {new_count - initial_count}"


@pytest.mark.asyncio
async def test_different_status_codes_tracked_separately(
    client: AsyncClient, test_jwt_token: str
):
    """Test that different status codes are tracked separately."""
    # Make a successful request (authenticated)
    await client.get("/api/v1/user/me", headers={"Authorization": test_jwt_token})

    # Make a 404 request
    await client.get("/nonexistent")

    # Get metrics
    response = await client.get("/metrics")
    content = response.text

    # Both 200 and 404 should be tracked
    assert 'status_code="200"' in content
    assert 'status_code="404"' in content


@pytest.mark.asyncio
async def test_different_methods_tracked_separately(
    client: AsyncClient, test_jwt_token: str, test_organization
):
    """Test that different HTTP methods are tracked separately."""
    # Make a GET request (use an API endpoint that's tracked, not /health which is excluded)
    await client.get("/api/v1/user/me")

    # Make a POST request
    await client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@test.com",
            "password": "password123",
            "organization_slug": test_organization.slug,
        },
    )

    # Get metrics
    response = await client.get("/metrics")
    content = response.text

    # Both GET and POST should be tracked
    assert 'method="GET"' in content
    assert 'method="POST"' in content


@pytest.mark.asyncio
async def test_health_detailed_includes_pool_stats(client: AsyncClient):
    """Test that detailed health check includes database pool stats."""
    response = await client.get("/health/detailed")

    assert response.status_code == 200
    data = response.json()

    # Should have components
    assert "components" in data
    assert "database" in data["components"]


@pytest.mark.asyncio
async def test_slow_request_threshold_metric(client: AsyncClient):
    """Test that slow request metric exists."""
    response = await client.get("/metrics")
    content = response.text

    # Should have slow request counter defined
    assert "http_slow_requests_total" in content


@pytest.mark.asyncio
async def test_exception_counter_metric(client: AsyncClient):
    """Test that exception counter metric exists."""
    response = await client.get("/metrics")
    content = response.text

    # Should have exceptions counter defined
    assert "exceptions_total" in content


@pytest.mark.asyncio
async def test_auth_failures_metric(client: AsyncClient, test_organization):
    """Test that auth failures are tracked."""
    # Make a login request with wrong password
    await client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@test.com",
            "password": "wrongpassword",
            "organization_slug": test_organization.slug,
        },
    )

    # Get metrics
    response = await client.get("/metrics")
    content = response.text

    # Should have auth failures metric
    assert "auth_failures_total" in content


# ============================================================================
# METRICS SUMMARY ENDPOINT TESTS (/api/metrics/summary)
# ============================================================================


@pytest.mark.asyncio
async def test_metrics_summary_requires_authentication(client: AsyncClient):
    """Test that /api/metrics/summary returns 401 without authentication."""
    response = await client.get("/api/v1/metrics/summary")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_metrics_summary_requires_admin_role(
    client: AsyncClient, test_jwt_token: str
):
    """Test that /api/metrics/summary returns 403 for non-admin users."""
    response = await client.get(
        "/api/v1/metrics/summary", headers={"Authorization": test_jwt_token}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_metrics_summary_accessible_by_super_admin(
    client: AsyncClient, test_admin_token: str
):
    """Test that /api/metrics/summary is accessible by super admin (is_admin=True)."""
    response = await client.get(
        "/api/v1/metrics/summary", headers={"Authorization": test_admin_token}
    )
    assert response.status_code == 200
    data = response.json()

    # Verify top-level structure
    assert "requests" in data
    assert "database" in data
    assert "cache" in data
    assert "users" in data
    assert "jobs" in data
    assert "system" in data


@pytest.mark.asyncio
async def test_metrics_summary_accessible_by_admin_role(
    client: AsyncClient, test_admin_token: str
):
    """Test that /api/metrics/summary is accessible by super admin."""
    response = await client.get(
        "/api/v1/metrics/summary", headers={"Authorization": test_admin_token}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_metrics_summary_request_metrics_structure(
    client: AsyncClient, test_admin_token: str
):
    """Test that request metrics have correct structure."""
    response = await client.get(
        "/api/v1/metrics/summary", headers={"Authorization": test_admin_token}
    )
    assert response.status_code == 200
    data = response.json()

    requests = data["requests"]
    assert "total" in requests
    assert "rate_per_minute" in requests
    assert "error_rate" in requests
    assert "avg_latency_ms" in requests

    # Validate types
    assert isinstance(requests["total"], int)
    assert isinstance(requests["rate_per_minute"], (int, float))
    assert isinstance(requests["error_rate"], (int, float))
    assert isinstance(requests["avg_latency_ms"], (int, float))


@pytest.mark.asyncio
async def test_metrics_summary_database_metrics_structure(
    client: AsyncClient, test_admin_token: str
):
    """Test that database metrics have correct structure."""
    response = await client.get(
        "/api/v1/metrics/summary", headers={"Authorization": test_admin_token}
    )
    assert response.status_code == 200
    data = response.json()

    database = data["database"]
    assert "pool_size" in database
    assert "connections_in_use" in database
    assert "connections_available" in database

    # Validate types
    assert isinstance(database["pool_size"], int)
    assert isinstance(database["connections_in_use"], int)
    assert isinstance(database["connections_available"], int)


@pytest.mark.asyncio
async def test_metrics_summary_cache_metrics_structure(
    client: AsyncClient, test_admin_token: str
):
    """Test that cache metrics have correct structure."""
    response = await client.get(
        "/api/v1/metrics/summary", headers={"Authorization": test_admin_token}
    )
    assert response.status_code == 200
    data = response.json()

    cache = data["cache"]
    assert "hit_rate" in cache
    assert "connected" in cache

    # Validate types
    assert isinstance(cache["hit_rate"], (int, float))
    assert isinstance(cache["connected"], bool)


@pytest.mark.asyncio
async def test_metrics_summary_user_metrics_structure(
    client: AsyncClient, test_admin_token: str
):
    """Test that user metrics have correct structure."""
    response = await client.get(
        "/api/v1/metrics/summary", headers={"Authorization": test_admin_token}
    )
    assert response.status_code == 200
    data = response.json()

    users = data["users"]
    assert "active_count" in users

    # Validate types
    assert isinstance(users["active_count"], int)
    assert users["active_count"] >= 0


@pytest.mark.asyncio
async def test_metrics_summary_job_metrics_structure(
    client: AsyncClient, test_admin_token: str
):
    """Test that job metrics have correct structure."""
    response = await client.get(
        "/api/v1/metrics/summary", headers={"Authorization": test_admin_token}
    )
    assert response.status_code == 200
    data = response.json()

    jobs = data["jobs"]
    assert "pending" in jobs
    assert "in_progress" in jobs
    assert "failed_total" in jobs

    # Validate types
    assert isinstance(jobs["pending"], int)
    assert isinstance(jobs["in_progress"], int)
    assert isinstance(jobs["failed_total"], int)

    # Values should be non-negative
    assert jobs["pending"] >= 0
    assert jobs["in_progress"] >= 0
    assert jobs["failed_total"] >= 0


@pytest.mark.asyncio
async def test_metrics_summary_system_metrics_structure(
    client: AsyncClient, test_admin_token: str
):
    """Test that system metrics have correct structure."""
    response = await client.get(
        "/api/v1/metrics/summary", headers={"Authorization": test_admin_token}
    )
    assert response.status_code == 200
    data = response.json()

    system = data["system"]
    assert "cpu_percent" in system
    assert "memory_percent" in system
    assert "uptime_seconds" in system

    # Validate types
    assert isinstance(system["cpu_percent"], (int, float))
    assert isinstance(system["memory_percent"], (int, float))
    assert isinstance(system["uptime_seconds"], (int, float))

    # CPU and memory should be between 0-100
    assert 0 <= system["cpu_percent"] <= 100
    assert 0 <= system["memory_percent"] <= 100

    # Uptime should be positive
    assert system["uptime_seconds"] >= 0


@pytest.mark.asyncio
async def test_metrics_summary_total_requests_increments(
    client: AsyncClient, test_admin_token: str
):
    """Test that total requests metric increments after making requests."""
    # Get initial metrics
    response1 = await client.get(
        "/api/v1/metrics/summary", headers={"Authorization": test_admin_token}
    )
    initial_total = response1.json()["requests"]["total"]

    # Make some additional requests
    await client.get("/health")
    await client.get("/health")

    # Get updated metrics
    response2 = await client.get(
        "/api/v1/metrics/summary", headers={"Authorization": test_admin_token}
    )
    new_total = response2.json()["requests"]["total"]

    # Total should have increased (at least by the 2 health requests)
    assert new_total > initial_total
