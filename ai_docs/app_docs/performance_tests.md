# Performance Test Suite

Comprehensive performance testing across three layers: backend load testing, backend micro-benchmarks, and frontend performance auditing.

## Overview

| Layer | Tool | Location | Command |
|-------|------|----------|---------|
| HTTP Load Testing | Locust | `app/backend/perf/` | `make perf` |
| Micro-Benchmarks | pytest-benchmark | `app/backend/tests/benchmarks/` | `make benchmark` |
| Frontend Perf | Lighthouse CI | `app/frontend/lighthouserc.json` | `npm run perf` |

## Backend Load Testing (Locust)

Simulates realistic multi-tenant traffic against the API with weighted scenarios:

| Scenario | Weight | Endpoints |
|----------|--------|-----------|
| Auth | 30 | Login, token refresh, check-email |
| Users | 15 | List users, search |
| Organizations | 10 | List/get orgs, member count |
| Files | 15 | Upload, list, usage, settings |
| Notifications | 20 | In-app list, unread count, mark read, preferences |
| Audit Logs | 10 | List with filters, sort, search |

### Usage

```bash
cd app/backend

# Headless (CI)
make perf

# With web UI (interactive)
make perf-ui

# Custom parameters
PERF_USERS=100 PERF_SPAWN_RATE=10 PERF_RUN_TIME=10m make perf
```

### Configuration

All settings via environment variables — see `app/backend/perf/config.py`. Requires a pre-seeded test tenant with credentials set in `PERF_ADMIN_EMAIL` / `PERF_ADMIN_PASSWORD`.

### CI Thresholds

| Metric | Threshold |
|--------|-----------|
| p95 latency | < 500ms |
| p99 latency | < 1000ms |
| Error rate | < 1% |
| Throughput | > 100 req/s @ 50 users |

Results are parsed by `app/backend/perf/check_thresholds.py` in CI.

## Backend Micro-Benchmarks (pytest-benchmark)

Isolated benchmarks for critical code paths:

### Database Queries (`test_query_perf.py`)
- List users with 1,000 rows (paginated) — target < 50ms
- Audit log query with 10,000 rows — target < 100ms
- Deep pagination performance
- Tenant isolation (no cross-tenant data leakage, no performance degradation with multiple tenants)

### Auth (`test_auth_perf.py`)
- Password hashing — target 100-300ms (security floor)
- Password verification
- JWT encode/decode round-trip — target < 5ms

### Serialization (`test_serialization.py`)
- `UserResponse.model_validate()` — target < 1ms
- `UserDetailResponse`, `UserListItemResponse`
- Batch serialization (50 items)
- JSON output (`model_dump_json()`)

### Usage

```bash
cd app/backend
make benchmark

# Results saved to tests/benchmarks/results/benchmark.json
# Automatically compared against baseline on subsequent runs
```

## Frontend Performance (Lighthouse CI)

Core Web Vitals audited against `localhost:5173`:

| Metric | Target |
|--------|--------|
| Performance Score | >= 90 |
| LCP | < 2.5s |
| TTI | < 3.5s |
| CLS | < 0.1 |
| Bundle Size | < 500KB (warning) |

```bash
cd app/frontend
npm run perf          # Run audit
npm run perf:report   # View results
```

## CI Integration

`.github/workflows/perf.yml` runs on PRs to main and weekly (Monday 2am):

1. **backend-benchmarks** — pytest-benchmark with PostgreSQL + Redis services
2. **backend-load-test** — Locust against running app (depends on benchmarks)
3. **frontend-lighthouse** — Lighthouse CI audit

All results uploaded as GitHub Actions artifacts.

## Metrics Reference

| Category | Metric | Tool |
|----------|--------|------|
| Throughput | Requests/second | Locust |
| Latency | p50, p95, p99 response time | Locust |
| Error Rate | % non-2xx under load | Locust |
| Concurrency | Saturation point | Locust |
| DB Queries | Execution time (paginated) | pytest-benchmark |
| Auth | JWT round-trip, hash time | pytest-benchmark |
| Serialization | Pydantic model_validate | pytest-benchmark |
| Tenant Isolation | Query time vs tenant count | pytest-benchmark |
| Frontend | Performance Score, LCP, TTI, CLS | Lighthouse |
| Bundle | Total JS payload | Lighthouse |
| DB Pool | Connection utilization | Prometheus (existing) |
| Cache | Redis hit/miss ratio | Prometheus (existing) |
| Queue | ARQ job queue depth | Prometheus (existing) |
