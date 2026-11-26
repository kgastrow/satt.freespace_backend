# Testing Patterns

## Quick Reference

**Key points:**
- Tests use in-memory SQLite (not PostgreSQL)
- Each test gets a fresh, isolated database
- Use existing fixtures from `tests/conftest.py`
- Run tests: `make test` (parallel with `-n 8`) or `make test-fast` (auto-detect workers)

## Test Structure

```
tests/
├── conftest.py        # ALL fixtures - DO NOT duplicate
├── unit_tests/        # CRUD/model tests (no HTTP)
├── service_tests/     # Business logic with mocks
├── api_tests/         # HTTP endpoint tests
├── crud_tests/        # Complex CRUD operations (e.g., payments)
└── benchmarks/        # Performance benchmarks (pytest-benchmark)
```

| Type | Directory | Naming |
|------|-----------|--------|
| Unit | `unit_tests/` | `test_<entity>.py` |
| Service | `service_tests/` | `test_<name>_service.py` |
| API | `api_tests/` | `test_<entity>_api.py` |
| CRUD | `crud_tests/` | `test_<entity>_crud.py` |
| Benchmark | `benchmarks/` | `test_<name>_perf.py` |

## Available Fixtures

### Database & HTTP

| Fixture | Description |
|---------|-------------|
| `async_session` | Database session for all DB operations |
| `client` | AsyncClient for API tests |
| `authenticated_client` | Client with auth headers |
| `admin_client` | Client with admin auth |

### Entities

| Fixture | Description |
|---------|-------------|
| `test_organization` | "Test Organization" (slug: "test-org") |
| `second_organization` | For isolation tests |
| `test_user` | Regular user (test@test.com) |
| `test_admin_user` | Super admin (admin@test.com) |
| `test_role`, `admin_role`, `owner_role`, `member_role` | Various roles |
| `second_org_user` | User in second org |
| `user_with_permission` | User with specific permission via RolePermission |
| `admin_with_org_permission` | Admin with organization permission |

### Tokens

| Fixture | Description |
|---------|-------------|
| `test_jwt_token` | Regular user token (includes "Bearer " prefix) |
| `test_admin_token` | Super admin token (includes "Bearer " prefix) |
| `admin_token` | Org admin token (includes "Bearer " prefix) |
| `test_super_admin_token` | Super admin token (includes "Bearer " prefix) |
| `user_with_permission_token` | Token for user_with_permission |
| `second_org_user_token` | Token for different org (multi-tenancy isolation tests) |

**Token format note:** All token fixtures return the complete `"Bearer {token}"` string. Use directly in headers:
```python
headers={"Authorization": test_jwt_token}  # Correct - already includes "Bearer "
```

### Payments

| Fixture | Description |
|---------|-------------|
| `payment_settings` | OrganizationPaymentSettings with Stripe config |
| `payment_customer` | PaymentCustomer record |
| `saved_payment_method` | SavedPaymentMethod (Visa ending 4242) |
| `test_payment` | Payment record (succeeded, $100) |

### Permission Dicts

| Fixture | Description |
|---------|-------------|
| `api_key_permissions` | Dict of API key permissions (create, read, etc.) |
| `standard_permissions` | Dict of common permissions (users:read, etc.) |
| `payment_permissions` | Dict of payment-related permissions |

### Feature Flags

| Fixture | Description |
|---------|-------------|
| `api_keys_feature_flag` | Enables API keys feature (required for API key tests) |
| `test_feature_flag` | Generic test flag (disabled by default) |
| `test_feature_flag_override` | Org-specific override for test_feature_flag |

### ID Helpers

| Fixture | Description |
|---------|-------------|
| `test_user_id` | String version of test_user.id |
| `test_organization_id` | String version of test_organization.id |
| `test_role_id` | String version of test_role.id |

## Writing Tests

### Unit Test (CRUD)

```python
@pytest.mark.asyncio
async def test_create_project(async_session, test_organization):
    project = await create_project(
        session=async_session,
        data={"name": "Test"},
        organization_id=str(test_organization.id)
    )
    assert project.name == "Test"
```

### API Test

```python
@pytest.mark.asyncio
async def test_create_project_api(client: AsyncClient, test_jwt_token: str):
    response = await client.post(
        "/api/v1/projects",
        headers={"Authorization": test_jwt_token},
        json={"name": "New Project"}
    )
    assert response.status_code == 201
```

### Multi-Tenancy Isolation (CRITICAL)

Every tenant-scoped feature MUST include:

```python
@pytest.mark.asyncio
async def test_cannot_access_other_org_data(
    client, async_session, test_organization, second_organization, test_jwt_token
):
    # Create in other org
    other_item = await create_item(async_session, {...}, str(second_organization.id))

    # Access with test_org token
    response = await client.get(
        f"/api/v1/items/{other_item.id}",
        headers={"Authorization": test_jwt_token}
    )
    assert response.status_code == 404  # Not 403 (don't reveal existence)
```

**404 vs 403 Guidance:**
- **Use 404**: When accessing data that belongs to a different organization. This avoids revealing the existence of data across tenants (security best practice).
- **Use 403**: When the user explicitly lacks permission within their own organization (e.g., missing role permission).

### Soft Delete Verification

Always verify soft deletes check `deleted_time`:

```python
deleted_user = await delete_user(session=async_session, user_id=str(user.id), ...)
assert deleted_user.deleted_time is not None
```

### Service Test (with mocks)

Use class-based organization for related tests:

```python
class TestPaymentService:
    @pytest.fixture
    def mock_provider(self):
        """Create a mock payment provider."""
        provider = MagicMock()
        provider.provider_name = "stripe"
        return provider

    @pytest.mark.asyncio
    async def test_create_checkout_success(
        self, async_session, test_organization, test_user, payment_settings, mock_provider
    ):
        mock_provider.create_checkout_session = AsyncMock(return_value=mock_checkout_session)

        with patch(
            "src.services.payments.service.PaymentProviderFactory.get_provider_for_org",
            new_callable=AsyncMock,
            return_value=mock_provider,
        ):
            result = await PaymentService.create_checkout(
                session=async_session,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
                amount_cents=10000,
                currency="USD",
                description="Test checkout",
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )

        assert result["checkout_url"] == "https://checkout.stripe.com/pay/cs_test_123"
```

### Mock Call Verification

```python
mock_email.send_email.assert_called_once_with(
    to="user@example.com",
    subject="Test Subject",
    body="Test body content",
)

# For inspecting call arguments:
call_kwargs = mock_enqueue.call_args.kwargs
assert call_kwargs["to"] == test_user.email
```

### Class-Based Test Organization

Use classes to group related tests:

```python
class TestPasswordResetRequest:
    """Tests for POST /api/v1/auth/password-reset/request"""

    @pytest.mark.asyncio
    async def test_password_reset_request_success(self, client, test_user):
        ...

    @pytest.mark.asyncio
    async def test_password_reset_invalid_email(self, client):
        ...
```

## Running Tests

```bash
make test                               # Parallel (recommended, -n 8)
make test-fast                          # Parallel (auto-detect workers)
make test-cov                           # With coverage
pytest tests/unit_tests/test_user.py::test_create_user  # Specific test
pytest tests/ -k "multitenancy"         # Pattern matching
make benchmark                          # Run performance benchmarks
```

## Adding Fixtures

```python
# tests/conftest.py
@pytest_asyncio.fixture(scope="function")
async def test_project(async_session: AsyncSession, test_organization):
    project = Project(name="Test", organization_id=test_organization.id)
    async_session.add(project)
    await async_session.commit()
    await async_session.refresh(project)  # Load generated fields
    return project
```

## Redis Testing (fakeredis)

Redis is patched globally in conftest.py before imports. Rate limiting tests work automatically.

### How It Works

1. **Shared fake server**: A single `_fake_redis_server` is used across all tests for consistent state
2. **Monkey-patching**: `redis.from_url` is patched before any app imports
3. **Autouse reset**: The `reset_rate_limiter` fixture flushes Redis before each test

### Async Redis for Rate Limiters

The `mock_async_redis_for_rate_limiter` autouse fixture provides a fake async Redis client with `incr`, `expire`, and `ttl` methods for testing API key rate limiting.

### When to Use

- **Use fakeredis** (default): For testing actual Redis logic (rate limiting, pub/sub)
- **Use mocking**: When you need to simulate Redis failures or specific return values

## WebSocket Testing

WebSocket infrastructure is tested by directly testing the component classes (`ConnectionManager`, `MessageBroadcaster`, `RedisPubSub`, `RedisRegistry`) rather than creating actual WebSocket connections.

### ConnectionManager Test

```python
class TestConnectionManager:
    @pytest.fixture
    def manager(self):
        """Create a fresh ConnectionManager for each test."""
        return ConnectionManager()

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket."""
        ws = MagicMock()
        ws.send_json = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_connect_stores_connection(self, manager, mock_websocket):
        user_id = uuid4()
        org_id = uuid4()
        await manager.connect(mock_websocket, "conn-1", user_id, org_id)
        assert manager.connection_count == 1
```

### MessageBroadcaster Test

```python
@pytest.mark.asyncio
async def test_broadcast_to_user_sends_to_all_user_connections(
    self, manager, mock_websocket_1, mock_websocket_2
):
    user_id = uuid4()
    org_id = uuid4()
    await manager.connect(mock_websocket_1, "conn-1", user_id, org_id)
    await manager.connect(mock_websocket_2, "conn-2", user_id, org_id)

    await MessageBroadcaster.broadcast_to_user(
        manager, str(user_id), {"type": "notification", "data": "test"}
    )

    mock_websocket_1.send_json.assert_called_once()
    mock_websocket_2.send_json.assert_called_once()
```

## ARQ Task Testing

```python
@pytest.fixture
def mock_ctx_with_session(async_session: AsyncSession):
    @asynccontextmanager
    async def session_factory():
        yield async_session
    return {"session_factory": session_factory}

@pytest.mark.asyncio
async def test_cleanup_task(mock_ctx_with_session, async_session):
    result = await cleanup_expired_otps_task(mock_ctx_with_session)
    assert result["deleted_count"] == 1
```

**Email tasks**: Patch at `src.services.email.email_service`.

### Testing Task Enqueueing

To test that a task was enqueued (without actually running it):

```python
with patch(
    "src.services.tasks.TaskQueue.enqueue_password_reset_email",
    new_callable=AsyncMock,
) as mock_enqueue:
    # Trigger the action that enqueues the task
    response = await client.post("/api/v1/auth/password-reset/request", ...)

    # Verify task was enqueued with correct args
    mock_enqueue.assert_called_once()
    call_kwargs = mock_enqueue.call_args.kwargs
    assert call_kwargs["to"] == test_user.email
```

## Global Autouse Mocks

The following fixtures run automatically for all tests (via `autouse=True`):

| Fixture | Purpose |
|---------|---------|
| `reset_rate_limiter` | Flushes fakeredis before each test |
| `mock_task_queue_enqueue_job` | Prevents actual task enqueueing, returns mock job ID |
| `mock_async_redis_for_rate_limiter` | Provides fake async Redis for API key rate limiting |

These prevent side effects and make tests hermetic. **You do NOT need to include them in test function signatures** - they run automatically even without being listed as parameters.

## Best Practices

**DO:**
- Use existing fixtures
- Test success AND error cases
- Include isolation tests for tenant-scoped features
- Use `pytest.mark.asyncio`
- Run parallel with `make test` or `make test-fast`

**DON'T:**
- Create own database engine/session
- Use `app/database.py` for tests
- Share state between tests
- Skip isolation tests
- Use sync fixtures with async tests

**Common Pitfalls:**
- **Permission validation**: When testing features that assign permissions (e.g., API keys), the test user must have those permissions granted via `RolePermission`. Creating the `Permission` entity alone is not enough.
- **Response structures**: Endpoints returning permissions return `PermissionResponse` objects (with `code`, `name`, etc.), not string arrays. Check `p["code"]` not `"perm:code" in data["permissions"]`.
- **Refresh after commit**: After `await async_session.commit()`, call `await async_session.refresh(obj)` to reload generated fields (id, created_time, etc.). Without refresh, these fields may be stale or None.
- **Feature flags**: Some features require feature flags to be enabled. Use fixtures like `api_keys_feature_flag` to enable them in tests.

## Granting Permissions to Test Users

Permissions flow through a chain: **Permission -> RolePermission -> UserRole -> User**

To grant a permission to a test user:
```python
# 1. Create the Permission (or use existing fixture)
permission = Permission(code="files:read", name="Read Files", ...)
async_session.add(permission)
await async_session.commit()

# 2. Create RolePermission linking role to permission
role_permission = RolePermission(
    role_id=test_role.id,
    permission_id=permission.id,
    granted_by=test_user.id  # Who granted this
)
async_session.add(role_permission)
await async_session.commit()

# 3. Create UserRole linking user to role in organization
user_role = UserRole(
    user_id=user.id,
    role_id=test_role.id,
    organization_id=test_organization.id
)
async_session.add(user_role)
await async_session.commit()
```

Use existing fixtures when possible: `user_with_permission` and `user_with_permission_token` already have `users:read` permission set up.

## Test Checklist

- [ ] Place test in correct directory (`unit_tests/`, `api_tests/`, `service_tests/`, `crud_tests/`, or `benchmarks/`)
- [ ] Use existing fixtures from `conftest.py` (don't create own session)
- [ ] Add `@pytest.mark.asyncio` decorator for async tests
- [ ] Test both success AND error cases (401, 403, 404, validation)
- [ ] Include multi-tenancy isolation test if feature is tenant-scoped
- [ ] Return 404 (not 403) for cross-tenant access attempts
- [ ] Use `AsyncMock` for async methods, `MagicMock` for sync objects
- [ ] Verify soft deletes (check `deleted_time is not None`)
- [ ] For permissions, create `RolePermission` link (not just `Permission`)
- [ ] Use class-based organization for related tests
- [ ] Verify mock calls with `assert_called_once_with()` when needed
- [ ] Run tests with `make test` to verify parallel execution works
- [ ] Document new fixtures in `conftest.py` with docstrings
