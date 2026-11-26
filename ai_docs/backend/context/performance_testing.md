# Backend Performance Testing

Database query benchmarks and HTTP load testing infrastructure.

## Running (from `app/backend/`)

```bash
make benchmark              # pytest-benchmark micro-benchmarks
make perf                   # Locust headless (50 users, 5m)
make perf-ui                # Locust with web UI
PERF_USERS=100 make perf    # Override user count
```

## Data Seeding (Required Before Load Tests)

Locust tests require a seeded database with test credentials. Run once before testing:

```bash
make seed   # Creates default-org, test users, permissions, sample data
```

This creates:
- Organization: `default-org`
- Admin: `super@test.com` / `Admin@123`
- Test users with various roles

Override test credentials via environment variables if using custom seed data.

## Locust Load Tests (`app/backend/perf/`)

Structure: `locustfile.py` (entry point), `config.py`, `utils.py`, `check_thresholds.py`, `scenarios/`

### Writing a Scenario

Create `perf/scenarios/your_scenario.py`:

```python
from locust import task, tag

class YourScenario:
    """Describe scenario purpose. Weight: total task weights."""

    @task(5)  # Weight: higher = more frequent
    @tag("your-feature")
    def list_items(self):
        """List items with pagination."""
        headers = {k: v for k, v in self.auth_headers.items() if not k.startswith("_")}
        self.client.get(
            "/api/v1/items?limit=10&offset=0",
            headers=headers,
            name="/api/v1/items [list]",  # Grouping name for reports
        )

    @task(2)
    @tag("your-feature")
    def create_item(self):
        """Create a new item."""
        headers = {k: v for k, v in self.auth_headers.items() if not k.startswith("_")}
        self.client.post(
            "/api/v1/items",
            headers=headers,
            json={"name": "Test Item"},
            name="/api/v1/items [create]",
        )
```

Key points:
- `@task(weight)`: Higher weight = more frequent execution
- `@tag("name")`: Filter tests with `--tags` flag
- `self.auth_headers`: Set during `on_start()` via login helper
- `name` parameter: Groups requests in reports (use `[action]` suffix)
- Filter `_refresh_token` from headers (prefixed with `_`)

### Integrating Into WebAppUser

Edit `perf/locustfile.py`:

```python
from perf.scenarios.your_scenario import YourScenario

class WebAppUser(
    AuthScenario,
    UserScenario,
    YourScenario,  # Add your mixin
    HttpUser,
):
    """Update docstring with new scenario weights."""
    wait_time = between(1, 3)
    host = "http://localhost:8000"

    def on_start(self):
        self.auth_headers = login(self.client)
```

### Authentication

Authentication is handled automatically in `on_start()`. The `login()` helper in `utils.py`:

```python
def login(client) -> dict:
    """Authenticate and return headers with Bearer token."""
    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": TEST_TENANT_ADMIN_EMAIL,
            "password": TEST_TENANT_ADMIN_PASSWORD,
            "organization_slug": TEST_ORG_SLUG,
        },
    )
    data = resp.json()
    return {
        "Authorization": f"Bearer {data['access_token']}",
        "_refresh_token": data.get("refresh_token", ""),  # Prefixed to exclude from requests
    }
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PERF_BASE_URL` | `http://localhost:8000` | Target server |
| `PERF_USERS` | `50` | Concurrent users |
| `PERF_SPAWN_RATE` | `5` | Users spawned/sec |
| `PERF_RUN_TIME` | `5m` | Test duration |
| `PERF_ADMIN_EMAIL` | `performance_test@test.com` | Test account |
| `PERF_ADMIN_PASSWORD` | `Admin@123` | Test account |
| `PERF_ORG_SLUG` | `default-org` | Target org slug |
| `PERF_ORG_ID` | `` | Target org UUID |

### CI Threshold Checking

After running load tests, check results against thresholds:

```bash
python perf/check_thresholds.py perf/results/run_stats.csv
```

Thresholds:
| Metric | Threshold |
|--------|-----------|
| p95 latency | < 500ms |
| p99 latency | < 1000ms |
| Error rate | < 1% |

The script reads the Locust CSV output, finds the "Aggregated" row, and fails if any threshold is exceeded. Use in CI pipelines to gate deployments.

## pytest-benchmark (`app/backend/tests/benchmarks/`)

Files: `conftest.py` (fixtures), `test_query_perf.py` (DB queries), `test_auth_perf.py` (auth), `test_serialization.py` (Pydantic)

### Key Fixtures

- `seeded_users` - 1000 users for query benchmarks
- `seeded_audit_logs` - 10000 audit log entries
- `other_organization` - Second org (500 users) for tenant isolation tests

### Adding a Benchmark

1. Add test to appropriate file in `tests/benchmarks/`
2. For async functions: use `benchmark.pedantic(fn, rounds=N, warmup_rounds=M)` with event loop bridge pattern:
   ```python
   def _run(coro):
       loop = asyncio.get_event_loop_policy().new_event_loop()
       try:
           return loop.run_until_complete(coro)
       finally:
           loop.close()
   ```
3. Group with `@pytest.mark.benchmark(group="group-name")`

### Baseline Comparison

```bash
make benchmark  # outputs results/benchmark.json
# To compare: copy benchmark.json to results/baseline.json, then run again
```
