"""Shared test setup: every test gets its own machine-wide resource registry (ADW_SHARED_DIR in tmp), so tests
never touch ~/.adw/resources.json or each other's leases."""

import pytest


@pytest.fixture(autouse=True)
def _private_resource_registry(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("ADW_SHARED_DIR", str(tmp_path_factory.mktemp("adw_shared")))
    for name in ("ADW_RESOURCES", "ADW_MAX_WORKFLOWS", "ADW_MAX_FULL_SUITES", "ADW_BACKEND_PORTS",
                 "ADW_FRONTEND_PORTS", "ADW_REDIS_DBS", "ADW_LEASE_TTL_HOURS", "ORE_MAX_PARALLEL"):
        monkeypatch.delenv(name, raising=False)
