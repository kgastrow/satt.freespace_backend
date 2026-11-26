"""
Benchmark fixtures for seeding realistic data volumes.

Reuses the existing test infrastructure (async_session, test_organization, etc.)
from the root conftest.py and adds bulk data seeding on top.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.models.audit_log import AuditAction, AuditLog
from src.models.organization import Organization
from src.models.user import User


# A pre-hashed password to avoid hashing 1000 times during seed
_HASHED_PASSWORD = hash_password("BenchmarkPass123!")


@pytest_asyncio.fixture(scope="function")
async def seeded_users(async_session: AsyncSession, test_organization):
    """Seed 1000 users into the test organization for query benchmarks."""
    users = []
    for i in range(1000):
        user = User(
            email=f"bench-user-{i}@test.com",
            password=_HASHED_PASSWORD,
            email_verified=True,
            first_name=f"Bench{i}",
            last_name=f"User{i}",
            organization_id=test_organization.id,
        )
        users.append(user)
    async_session.add_all(users)
    await async_session.commit()
    return users


@pytest_asyncio.fixture(scope="function")
async def seeded_audit_logs(async_session: AsyncSession, test_organization):
    """Seed 10000 audit log entries for the test organization."""
    actor_id = uuid.uuid4()
    logs = []
    for i in range(10000):
        log = AuditLog(
            organization_id=test_organization.id,
            actor_id=actor_id,
            action=AuditAction.UPDATE.value,
            resource_type="User",
            resource_id=uuid.uuid4(),
            resource_name=f"user-{i}@test.com",
            changes={"field": {"old": "a", "new": "b"}},
            ip_address="127.0.0.1",
        )
        logs.append(log)
    async_session.add_all(logs)
    await async_session.commit()
    return logs


@pytest_asyncio.fixture(scope="function")
async def other_organization(async_session: AsyncSession):
    """Create a second organization with its own users for isolation benchmarks."""
    org = Organization(
        name="Other Benchmark Org", slug="other-bench-org", is_active=True
    )
    async_session.add(org)
    await async_session.commit()
    await async_session.refresh(org)

    users = []
    for i in range(500):
        user = User(
            email=f"other-bench-{i}@test.com",
            password=_HASHED_PASSWORD,
            email_verified=True,
            organization_id=org.id,
        )
        users.append(user)
    async_session.add_all(users)
    await async_session.commit()

    return org


@pytest.fixture
def sample_user_dict():
    """Return a dictionary matching User column values for Pydantic serialization."""
    user_id = str(uuid.uuid4())
    return {
        "id": user_id,
        "email": "sample@test.com",
        "email_deliverable": True,
    }
