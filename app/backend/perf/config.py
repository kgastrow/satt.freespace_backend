"""Environment-specific settings for performance tests."""

import os

BASE_URL = os.getenv("PERF_BASE_URL", "http://localhost:8000")
USERS_COUNT = int(os.getenv("PERF_USERS", "50"))
SPAWN_RATE = int(os.getenv("PERF_SPAWN_RATE", "5"))
RUN_TIME = os.getenv("PERF_RUN_TIME", "5m")

# Pre-seeded test tenant credentials
TEST_TENANT_ADMIN_EMAIL = os.getenv("PERF_ADMIN_EMAIL", "performance_test@test.com")
TEST_TENANT_ADMIN_PASSWORD = os.getenv("PERF_ADMIN_PASSWORD", "Admin@123")
TEST_ORG_SLUG = os.getenv("PERF_ORG_SLUG", "default-org")
TEST_ORG_ID = os.getenv("PERF_ORG_ID", "")
