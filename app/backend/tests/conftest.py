"""
Pytest configuration and fixtures for async FastAPI testing.

PERFORMANCE OPTIMIZATIONS:
1. In-memory SQLite - no disk I/O
2. Fresh database per test with fast schema creation
3. Supports pytest-xdist parallel execution (each worker isolated)

Uses fakeredis to simulate Redis for rate limiting tests.
"""

from collections.abc import AsyncGenerator
import os
import sys

# ============================================================================
# IMPORTANT: Patch Redis with fakeredis BEFORE any app imports
# This ensures all Redis connections (including rate limiter) use fakeredis
# ============================================================================
import fakeredis


# Create a shared fakeredis server for all tests in this worker
_fake_redis_server = fakeredis.FakeServer()

# Patch redis.from_url which is used by the limits library (slowapi's backend)
import redis  # noqa: E402


_original_from_url = redis.from_url


def _fake_from_url(url, **kwargs):
    """Replace redis.from_url with fakeredis connection."""
    return fakeredis.FakeRedis(
        server=_fake_redis_server,
        decode_responses=kwargs.get("decode_responses", False),
    )


redis.from_url = _fake_from_url

# ============================================================================
# IMPORTANT: Reset Prometheus registry to avoid duplicate metric errors
# This must happen BEFORE any app imports that register metrics
# ============================================================================
from prometheus_client import REGISTRY  # noqa: E402


# Unregister default collectors that conflict with our custom metrics
# and that cause issues during test re-imports
for collector in list(REGISTRY._names_to_collectors.values()):
    try:
        REGISTRY.unregister(collector)
    except Exception:
        pass

# ============================================================================

from httpx import ASGITransport, AsyncClient  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402


# Add the parent directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.security import create_access_token, hash_password  # noqa: E402
from src.database import Base, get_async_session  # noqa: E402

# API Key models (imported for SQLAlchemy model registration)
from src.models.api_key import ApiKey  # noqa: E402, F401
from src.models.api_key_permission import ApiKeyPermission  # noqa: E402, F401
from src.models.api_key_rate_limit import ApiKeyRateLimit  # noqa: E402, F401
from src.models.bulk_notification import BulkNotification  # noqa: E402, F401

# File models
# Feedback models
from src.models.feedback import Feedback, FeedbackAttachment  # noqa: E402, F401

# Notification models
from src.models.notification import Notification  # noqa: E402, F401
from src.models.notification_category import NotificationCategory  # noqa: E402, F401
from src.models.notification_template import NotificationTemplate  # noqa: E402, F401

# Import all models to register them with Base.metadata
from src.models.organization import Organization  # noqa: E402
from src.models.organization_notification_settings import (  # noqa: E402, F401
    OrganizationNotificationSettings,
)
from src.models.organization_payment_settings import (  # noqa: E402
    OrganizationPaymentSettings,  # noqa: F401
)

# Payment models
# fmt: off
from src.models.payment import Payment  # noqa: E402, F401
from src.models.payment_customer import (  # noqa: E402, F401
    PaymentCustomer,
    SavedPaymentMethod,
)

# fmt: on
# Permission models
from src.models.permission import Permission  # noqa: E402
from src.models.role import Role  # noqa: E402
from src.models.role_permission import RolePermission  # noqa: E402
from src.models.user import User  # noqa: E402
from src.models.user_invitation import UserInvitation  # noqa: E402, F401
from src.models.user_notification_preference import (  # noqa: E402, F401
    UserCategoryPreference,
    UserNotificationPreference,
)
from src.models.user_role import UserRole  # noqa: E402


# SSO and 2FA models


# ============================================================================
# DATABASE FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Create async database session for testing.

    Uses in-memory SQLite with StaticPool for fast, isolated tests.
    Each test gets a fresh database with schema created.
    StaticPool ensures the same connection is reused within a test.
    """
    # Create a new in-memory database for each test
    # StaticPool keeps the connection alive for the duration of the test
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    async_session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:
        yield session

    # Dispose of the engine after the test
    await engine.dispose()


# Reset rate limiter storage before each test
@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset rate limiter storage before each test to prevent cross-test interference."""
    fake_redis = fakeredis.FakeRedis(server=_fake_redis_server)
    fake_redis.flushall()
    yield


# ============================================================================
# ORGANIZATION FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def test_organization(async_session: AsyncSession):
    """Create a test organization."""
    org = Organization(name="Test Organization", slug="test-org", is_active=True)
    async_session.add(org)
    await async_session.commit()
    await async_session.refresh(org)
    return org


@pytest_asyncio.fixture(scope="function")
async def second_organization(async_session: AsyncSession):
    """Create a second test organization for isolation testing."""
    org = Organization(name="Second Organization", slug="second-org", is_active=True)
    async_session.add(org)
    await async_session.commit()
    await async_session.refresh(org)
    return org


# ============================================================================
# USER FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def test_user(async_session: AsyncSession, test_organization):
    """Create a test user."""
    user = User(
        email="test@test.com",
        password=hash_password("Password123!"),  # Valid complex password
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def test_admin_user(async_session: AsyncSession, test_organization):
    """Create a test admin user."""
    user = User(
        email="admin@test.com",
        password=hash_password("AdminPass123!"),  # Valid complex password
        email_verified=True,
        phone="+27737442554",
        phone_verified=True,
        first_name="Admin",
        last_name="User",
        is_admin=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def test_role(async_session: AsyncSession):
    """Create a test role (global - no organization_id)."""
    import uuid

    role = Role(
        name=f"test_role_{uuid.uuid4().hex[:8]}", description="Test role for testing"
    )
    async_session.add(role)
    await async_session.commit()
    await async_session.refresh(role)
    return role


@pytest_asyncio.fixture(scope="function")
async def admin_role(async_session: AsyncSession):
    """Create an admin role (global - no organization_id).

    Uses the standard 'admin' name which is checked by has_role() in endpoints.
    Each test gets a fresh database so name conflicts are not an issue.
    """
    role = Role(
        name="admin", description="Can manage users, roles, and organization settings."
    )
    async_session.add(role)
    await async_session.commit()
    await async_session.refresh(role)
    return role


@pytest_asyncio.fixture(scope="function")
async def owner_role(async_session: AsyncSession):
    """Create an owner role (global - no organization_id).

    Uses the standard 'owner' name which is checked by has_role() in endpoints.
    """
    role = Role(name="owner", description="Organization owner with full access.")
    async_session.add(role)
    await async_session.commit()
    await async_session.refresh(role)
    return role


@pytest_asyncio.fixture(scope="function")
async def member_role(async_session: AsyncSession):
    """Create a member role (global - no organization_id).

    Uses the standard 'member' name which is checked by has_role() in endpoints.
    """
    role = Role(name="member", description="Standard team member.")
    async_session.add(role)
    await async_session.commit()
    await async_session.refresh(role)
    return role


@pytest_asyncio.fixture(scope="function")
async def admin_user(async_session: AsyncSession, test_organization, admin_role):
    """Create a user with admin role."""
    user = User(
        email="orgadmin@test.com",
        password=hash_password("OrgAdmin123!"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    # Assign admin role
    user_role = UserRole(
        user_id=user.id, role_id=admin_role.id, organization_id=test_organization.id
    )
    async_session.add(user_role)
    await async_session.commit()

    return user


# ============================================================================
# TOKEN FIXTURES
# ============================================================================


@pytest.fixture
def test_jwt_token(test_user, test_organization) -> str:
    """Create a test JWT token for regular user."""
    token = create_access_token(
        user_id=str(test_user.id), organization_id=str(test_organization.id)
    )
    return f"Bearer {token}"


@pytest.fixture
def test_admin_token(test_admin_user, test_organization) -> str:
    """Create a test JWT token for admin user."""
    token = create_access_token(
        user_id=str(test_admin_user.id), organization_id=str(test_organization.id)
    )
    return f"Bearer {token}"


@pytest.fixture
def admin_token(admin_user, test_organization) -> str:
    """Create a test JWT token for admin role user."""
    token = create_access_token(
        user_id=str(admin_user.id), organization_id=str(test_organization.id)
    )
    return f"Bearer {token}"


@pytest.fixture
def test_super_admin_token(test_admin_user, test_organization) -> str:
    """Create a test JWT token for super admin user (is_admin=True).

    Super admins have access to system-wide admin endpoints like
    /api/admin/config, /api/admin/notifications/providers, etc.
    """
    token = create_access_token(
        user_id=str(test_admin_user.id), organization_id=str(test_organization.id)
    )
    return f"Bearer {token}"


@pytest.fixture
def second_org_user_token(test_user, second_organization) -> str:
    """Create a token for a user in a different organization (for isolation tests)."""
    token = create_access_token(
        user_id=str(test_user.id), organization_id=str(second_organization.id)
    )
    return f"Bearer {token}"


# ============================================================================
# HTTP CLIENT FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def client(async_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for testing FastAPI endpoints."""
    from main import app

    # Override the database session dependency
    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_async_session] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    # Clear overrides after test
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def authenticated_client(client: AsyncClient, test_jwt_token: str) -> AsyncClient:
    """Create authenticated HTTP client."""
    client.headers["Authorization"] = test_jwt_token
    return client


@pytest_asyncio.fixture(scope="function")
async def admin_client(client: AsyncClient, test_admin_token: str) -> AsyncClient:
    """Create authenticated HTTP client with admin privileges."""
    client.headers["Authorization"] = test_admin_token
    return client


# ============================================================================
# HELPER FIXTURES
# ============================================================================


@pytest.fixture
def test_user_id(test_user) -> str:
    """Return test user ID as string."""
    return str(test_user.id)


@pytest.fixture
def test_organization_id(test_organization) -> str:
    """Return test organization ID as string."""
    return str(test_organization.id)


@pytest.fixture
def test_role_id(test_role) -> str:
    """Return test role ID as string."""
    return str(test_role.id)


# ============================================================================
# MULTI-TENANCY ISOLATION TEST HELPERS
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def second_org_user(async_session: AsyncSession, second_organization):
    """Create a user in the second organization."""
    user = User(
        email="other@test.com",
        password=hash_password("OtherUser123!"),  # Valid complex password
        email_verified=True,
        organization_id=second_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def second_org_role(async_session: AsyncSession):
    """Create a second global role for testing."""
    import uuid

    role = Role(
        name=f"other_role_{uuid.uuid4().hex[:8]}",
        description="Another global role for testing",
    )
    async_session.add(role)
    await async_session.commit()
    await async_session.refresh(role)
    return role


# ============================================================================
# PERMISSION FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def test_permission(async_session: AsyncSession):
    """Create a test permission."""
    permission = Permission(
        code="test:read",
        name="Test Read",
        description="Test read permission",
        resource="test",
        action="read",
        display_order=0,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)
    return permission


@pytest_asyncio.fixture(scope="function")
async def users_read_permission(async_session: AsyncSession):
    """Create users:read permission."""
    permission = Permission(
        code="users:read",
        name="Read Users",
        description="View users in the organization",
        resource="users",
        action="read",
        display_order=0,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)
    return permission


@pytest_asyncio.fixture(scope="function")
async def users_write_permission(async_session: AsyncSession):
    """Create users:write permission."""
    permission = Permission(
        code="users:write",
        name="Write Users",
        description="Create and update users",
        resource="users",
        action="write",
        display_order=1,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)
    return permission


@pytest_asyncio.fixture(scope="function")
async def test_role_permission(
    async_session: AsyncSession, test_role, test_permission, test_user
):
    """Create a role permission linking test_role to test_permission."""
    role_permission = RolePermission(
        role_id=test_role.id, permission_id=test_permission.id, granted_by=test_user.id
    )
    async_session.add(role_permission)
    await async_session.commit()
    await async_session.refresh(role_permission)
    return role_permission


@pytest_asyncio.fixture(scope="function")
async def user_with_permission(
    async_session: AsyncSession,
    test_organization,
    test_role,
    users_read_permission,
    test_user,
):
    """Create a user with users:read permission through a role."""
    from src.core.security import hash_password

    # Grant permission to the role
    role_permission = RolePermission(
        role_id=test_role.id,
        permission_id=users_read_permission.id,
        granted_by=test_user.id,
    )
    async_session.add(role_permission)
    await async_session.commit()

    # Create user with the role
    user = User(
        email="permuser@test.com",
        password=hash_password("PermUser123!"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    # Assign role to user
    user_role = UserRole(
        user_id=user.id, role_id=test_role.id, organization_id=test_organization.id
    )
    async_session.add(user_role)
    await async_session.commit()

    return user


@pytest.fixture
def user_with_permission_token(user_with_permission, test_organization) -> str:
    """Create a JWT token for user with permission."""
    from src.core.security import create_access_token

    token = create_access_token(
        user_id=str(user_with_permission.id), organization_id=str(test_organization.id)
    )
    return f"Bearer {token}"


# ============================================================================
# API KEY PERMISSION FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def files_read_permission(async_session: AsyncSession):
    """Create files:read permission."""
    permission = Permission(
        code="files:read",
        name="Read Files",
        description="View files in the organization",
        resource="files",
        action="read",
        display_order=0,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)
    return permission


@pytest_asyncio.fixture(scope="function")
async def test_permission_code(async_session: AsyncSession):
    """Create test:permission permission for auth tests."""
    permission = Permission(
        code="test:permission",
        name="Test Permission",
        description="Test permission for auth tests",
        resource="test",
        action="permission",
        display_order=0,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)
    return permission


@pytest_asyncio.fixture(scope="function")
async def api_key_permissions(async_session: AsyncSession):
    """Create all standard API key management permissions."""
    permissions = []
    for action in ["read", "write", "delete"]:
        perm = Permission(
            code=f"api_keys:{action}",
            name=f"API Keys {action.title()}",
            description=f"API key {action} permission",
            resource="api_keys",
            action=action,
            display_order=0,
        )
        async_session.add(perm)
        permissions.append(perm)
    await async_session.commit()
    for perm in permissions:
        await async_session.refresh(perm)
    return {p.code: p for p in permissions}


@pytest_asyncio.fixture(scope="function")
async def standard_permissions(async_session: AsyncSession):
    """Create standard permissions used in API key tests.

    Returns a dict mapping permission codes to Permission objects.
    """
    permission_defs = [
        ("users:read", "Read Users", "users", "read"),
        ("users:write", "Write Users", "users", "write"),
        ("files:read", "Read Files", "files", "read"),
        ("test:permission", "Test Permission", "test", "permission"),
        ("api_keys:read", "API Keys Read", "api_keys", "read"),
        ("api_keys:write", "API Keys Write", "api_keys", "write"),
        ("api_keys:delete", "API Keys Delete", "api_keys", "delete"),
    ]

    permissions = {}
    for code, name, resource, action in permission_defs:
        perm = Permission(
            code=code,
            name=name,
            description=f"{name} permission",
            resource=resource,
            action=action,
            display_order=0,
        )
        async_session.add(perm)
        permissions[code] = perm

    await async_session.commit()
    for perm in permissions.values():
        await async_session.refresh(perm)

    return permissions


# ============================================================================
# PAYMENT FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def payment_settings(async_session: AsyncSession, test_organization):
    """Create payment settings for the test organization."""
    settings = OrganizationPaymentSettings(
        organization_id=test_organization.id,
        payments_allowed=True,
        default_provider="stripe",
        default_currency="USD",
        supported_currencies=["USD", "EUR", "GBP"],
        stripe_enabled=True,
        stripe_publishable_key="pk_test_123",
        stripe_secret_key="sk_test_123",
        stripe_webhook_secret="whsec_test_123",
        payfast_enabled=False,
        paypal_enabled=False,
    )
    async_session.add(settings)
    await async_session.commit()
    await async_session.refresh(settings)
    return settings


@pytest_asyncio.fixture(scope="function")
async def payment_customer(async_session: AsyncSession, test_organization, test_user):
    """Create a payment customer record."""
    customer = PaymentCustomer(
        organization_id=test_organization.id,
        user_id=test_user.id,
        provider="stripe",
        provider_customer_id="cus_test_123",
        email=test_user.email,
        name="Test User",
    )
    async_session.add(customer)
    await async_session.commit()
    await async_session.refresh(customer)
    return customer


@pytest_asyncio.fixture(scope="function")
async def saved_payment_method(
    async_session: AsyncSession, test_organization, payment_customer
):
    """Create a saved payment method for the test customer."""
    method = SavedPaymentMethod(
        organization_id=test_organization.id,
        customer_id=payment_customer.id,
        provider="stripe",
        provider_payment_method_id="pm_test_123",
        type="card",
        last_four="4242",
        brand="visa",
        exp_month=12,
        exp_year=2030,
        is_default=True,
        is_expired=False,
    )
    async_session.add(method)
    await async_session.commit()
    await async_session.refresh(method)
    return method


@pytest_asyncio.fixture(scope="function")
async def test_payment(
    async_session: AsyncSession, test_organization, test_user, payment_customer
):
    """Create a test payment record."""
    payment = Payment(
        organization_id=test_organization.id,
        user_id=test_user.id,
        provider="stripe",
        provider_reference="pi_test_123",
        customer_id=payment_customer.id,
        amount_cents=10000,
        currency="USD",
        status="succeeded",
        payment_method="card",
        description="Test payment",
        extra_data={"test": True},
    )
    async_session.add(payment)
    await async_session.commit()
    await async_session.refresh(payment)
    return payment


@pytest_asyncio.fixture(scope="function")
async def payment_permissions(async_session: AsyncSession):
    """Create payment-related permissions."""
    permission_defs = [
        ("payments:read", "Read Payments", "payments", "read"),
        ("payments:write", "Write Payments", "payments", "write"),
        ("payment-settings:read", "Read Payment Settings", "payment-settings", "read"),
        (
            "payment-settings:write",
            "Write Payment Settings",
            "payment-settings",
            "write",
        ),
        ("payment-methods:read", "Read Payment Methods", "payment-methods", "read"),
        ("payment-methods:write", "Write Payment Methods", "payment-methods", "write"),
    ]

    permissions = {}
    for code, name, resource, action in permission_defs:
        perm = Permission(
            code=code,
            name=name,
            description=f"{name} permission",
            resource=resource,
            action=action,
            display_order=0,
        )
        async_session.add(perm)
        permissions[code] = perm

    await async_session.commit()
    for perm in permissions.values():
        await async_session.refresh(perm)

    return permissions


@pytest_asyncio.fixture(scope="function")
async def organization_write_permission(async_session: AsyncSession):
    """Create organization:write permission."""
    permission = Permission(
        code="organization:write",
        name="Write Organization",
        description="Manage organization settings",
        resource="organization",
        action="write",
        display_order=0,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)
    return permission


@pytest_asyncio.fixture(scope="function")
async def sso_read_permission(async_session: AsyncSession):
    """Create sso:read permission."""
    permission = Permission(
        code="sso:read",
        name="View SSO Settings",
        description="View SSO configuration for the organization",
        resource="sso",
        action="read",
        display_order=0,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)
    return permission


@pytest_asyncio.fixture(scope="function")
async def sso_write_permission(async_session: AsyncSession):
    """Create sso:write permission."""
    permission = Permission(
        code="sso:write",
        name="Manage SSO Settings",
        description="Configure SSO providers and settings",
        resource="sso",
        action="write",
        display_order=1,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)
    return permission


@pytest_asyncio.fixture(scope="function")
async def user_with_sso_read(
    async_session: AsyncSession,
    test_organization,
    test_role,
    sso_read_permission,
    test_user,
):
    """Create a user with sso:read permission through a role."""
    # Grant permission to the role
    role_permission = RolePermission(
        role_id=test_role.id,
        permission_id=sso_read_permission.id,
        granted_by=test_user.id,
    )
    async_session.add(role_permission)
    await async_session.commit()

    # Create user with the role
    user = User(
        email="ssouser@test.com",
        password=hash_password("SSOUser123!"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    # Assign role to user
    user_role = UserRole(
        user_id=user.id, role_id=test_role.id, organization_id=test_organization.id
    )
    async_session.add(user_role)
    await async_session.commit()

    return user


@pytest.fixture
def user_with_sso_read_token(user_with_sso_read, test_organization) -> str:
    """Create a JWT token for user with sso:read permission."""
    token = create_access_token(
        user_id=str(user_with_sso_read.id), organization_id=str(test_organization.id)
    )
    return f"Bearer {token}"


@pytest_asyncio.fixture(scope="function")
async def admin_with_org_permission(
    async_session: AsyncSession,
    admin_user,
    admin_role,
    organization_write_permission,
):
    """Grant organization:write permission to admin_role and return admin_user."""
    role_permission = RolePermission(
        role_id=admin_role.id,
        permission_id=organization_write_permission.id,
        granted_by=admin_user.id,
    )
    async_session.add(role_permission)
    await async_session.commit()
    return admin_user


# ============================================================================
# FEATURE FLAG FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def api_keys_feature_flag(async_session: AsyncSession):
    """Create the api_keys feature flag (enabled by default)."""
    from src.models.feature_flag import FeatureFlag

    flag = FeatureFlag(
        key="api_keys",
        name="API Keys",
        description="Enable API key management",
        default_enabled=True,
    )
    async_session.add(flag)
    await async_session.commit()
    await async_session.refresh(flag)
    return flag


# ============================================================================
# TASK QUEUE MOCK FIXTURE
# ============================================================================


@pytest.fixture(autouse=True)
def mock_task_queue_enqueue_job(monkeypatch):
    """
    Mock task_queue.enqueue_job for all tests.

    This prevents tests from trying to connect to a real Redis instance
    when enqueuing background jobs via enqueue_job(). The mock returns a fake job ID.

    Note: Only enqueue_job is mocked here. Other methods like enqueue_password_reset_email
    are left for individual tests to mock when they need to make assertions on them.
    """

    async def mock_enqueue_job(*args, **kwargs):
        """Mock enqueue_job that returns a fake job ID."""
        return "mock-job-id-12345"

    # Import the task_queue instance and patch enqueue_job
    from src.services.tasks import task_queue

    monkeypatch.setattr(task_queue, "enqueue_job", mock_enqueue_job)

    yield


# ============================================================================
# ASYNC REDIS MOCK FOR RATE LIMITER
# ============================================================================


@pytest_asyncio.fixture(autouse=True)
async def mock_async_redis_for_rate_limiter(monkeypatch):
    """
    Patch the API key rate limiter to use fakeredis for async Redis connections.

    This ensures the rate limiter uses fakeredis instead of trying to
    connect to a real Redis instance in CI.
    """
    import fakeredis.aioredis

    # Create a fake async redis server shared across the test
    fake_server = fakeredis.FakeServer()

    # Get the rate limiter instance
    from src.core.api_key_rate_limit import api_key_rate_limiter

    async def mock_connect() -> None:
        """Mock connect that uses fakeredis."""
        if not api_key_rate_limiter._enabled:
            return

        # Use fakeredis instead of real Redis
        api_key_rate_limiter._redis = fakeredis.aioredis.FakeRedis(
            server=fake_server,
            decode_responses=False,
        )

        # Create a mock pool with disconnect method
        class MockPool:
            async def disconnect(self):
                pass

        api_key_rate_limiter._pool = MockPool()

    monkeypatch.setattr(api_key_rate_limiter, "connect", mock_connect)

    yield

    # Reset the rate limiter state after the test
    api_key_rate_limiter._redis = None
    api_key_rate_limiter._pool = None


# ============================================================================
# CHANGELOG FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def test_changelog(
    async_session: AsyncSession, test_organization, test_admin_user
):
    """Create a test changelog entry."""
    from datetime import datetime, timezone

    from src.models.changelog import Changelog

    changelog = Changelog(
        organization_id=test_organization.id,
        version="1.0.0",
        title="Test Changelog",
        body="Test changelog body content",
        category="feature",
        release_date=datetime.now(timezone.utc),
        is_published=True,
        created_by_id=test_admin_user.id,
    )
    async_session.add(changelog)
    await async_session.commit()
    await async_session.refresh(changelog)
    return changelog


@pytest_asyncio.fixture(scope="function")
async def second_org_changelog(
    async_session: AsyncSession, second_organization, test_admin_user
):
    """Changelog in second org for isolation tests."""
    from datetime import datetime, timezone

    from src.models.changelog import Changelog

    changelog = Changelog(
        organization_id=second_organization.id,
        version="2.0.0",
        title="Second Org Changelog",
        body="Second org changelog body",
        category="bugfix",
        release_date=datetime.now(timezone.utc),
        is_published=True,
        created_by_id=test_admin_user.id,
    )
    async_session.add(changelog)
    await async_session.commit()
    await async_session.refresh(changelog)
    return changelog


@pytest_asyncio.fixture(scope="function")
async def platform_changelog(async_session: AsyncSession, test_admin_user):
    """Platform-wide changelog entry (no organization)."""
    from datetime import datetime, timezone

    from src.models.changelog import Changelog

    changelog = Changelog(
        organization_id=None,
        version="0.1.0",
        title="Platform Changelog",
        body="Platform-wide changelog body",
        category="improvement",
        release_date=datetime.now(timezone.utc),
        is_published=True,
        created_by_id=test_admin_user.id,
    )
    async_session.add(changelog)
    await async_session.commit()
    await async_session.refresh(changelog)
    return changelog


# ============================================================================
# FEATURE FLAG FIXTURES (additional)
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def test_feature_flag(async_session: AsyncSession):
    """Create a test feature flag."""
    from src.models.feature_flag import FeatureFlag

    flag = FeatureFlag(
        key="test_flag",
        name="Test Feature Flag",
        description="A test feature flag",
        default_enabled=False,
    )
    async_session.add(flag)
    await async_session.commit()
    await async_session.refresh(flag)
    return flag


@pytest_asyncio.fixture(scope="function")
async def test_feature_flag_override(
    async_session: AsyncSession, test_organization, test_feature_flag
):
    """Create org-specific feature flag override."""
    from src.models.feature_flag_override import FeatureFlagOverride

    override = FeatureFlagOverride(
        feature_flag_id=test_feature_flag.id,
        organization_id=test_organization.id,
        enabled=True,
    )
    async_session.add(override)
    await async_session.commit()
    await async_session.refresh(override)
    return override


# ============================================================================
# ONBOARDING FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def test_user_type(async_session: AsyncSession):
    """Create a test user type with onboarding."""
    from src.models.user_type import UserType

    user_type = UserType(
        name="Test User Type",
        code="test_user_type",
        description="A test user type",
        is_active=True,
        requires_onboarding=True,
        requires_manual_review=True,
    )
    async_session.add(user_type)
    await async_session.commit()
    await async_session.refresh(user_type)
    return user_type


@pytest_asyncio.fixture(scope="function")
async def test_onboarding_step(async_session: AsyncSession, test_user_type):
    """Create an onboarding step."""
    from src.models.onboarding_step import OnboardingStep

    step = OnboardingStep(
        user_type_id=test_user_type.id,
        name="Test Step",
        code="test_step",
        description="A test onboarding step",
        step_order=1,
        required_fields={"name": {"type": "string", "required": True}},
        validation_rules={},
        requires_verification=False,
        is_active=True,
    )
    async_session.add(step)
    await async_session.commit()
    await async_session.refresh(step)
    return step


@pytest_asyncio.fixture(scope="function")
async def test_user_user_type(
    async_session: AsyncSession, test_organization, test_user, test_user_type
):
    """Create a user-user_type association for onboarding."""
    from src.models.user_user_type import OnboardingStatus, UserUserType

    uut = UserUserType(
        user_id=test_user.id,
        user_type_id=test_user_type.id,
        organization_id=test_organization.id,
        onboarding_status=OnboardingStatus.IN_PROGRESS,
    )
    async_session.add(uut)
    await async_session.commit()
    await async_session.refresh(uut)
    return uut


@pytest_asyncio.fixture(scope="function")
async def second_org_user_user_type(
    async_session: AsyncSession, second_organization, second_org_user, test_user_type
):
    """Create a user-user_type association in second org."""
    from src.models.user_user_type import OnboardingStatus, UserUserType

    uut = UserUserType(
        user_id=second_org_user.id,
        user_type_id=test_user_type.id,
        organization_id=second_organization.id,
        onboarding_status=OnboardingStatus.IN_PROGRESS,
    )
    async_session.add(uut)
    await async_session.commit()
    await async_session.refresh(uut)
    return uut


# ============================================================================
# ORGANIZATION EMAIL SETTINGS FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def test_email_settings(async_session: AsyncSession, test_organization):
    """Create email settings for test organization."""
    from src.models.organization_email_settings import OrganizationEmailSettings

    settings = OrganizationEmailSettings(
        organization_id=test_organization.id,
        provider="smtp",
        sender_email="test@testorg.com",
        sender_name="Test Organization",
    )
    async_session.add(settings)
    await async_session.commit()
    await async_session.refresh(settings)
    return settings


@pytest_asyncio.fixture(scope="function")
async def second_org_email_settings(async_session: AsyncSession, second_organization):
    """Create email settings for second organization."""
    from src.models.organization_email_settings import OrganizationEmailSettings

    settings = OrganizationEmailSettings(
        organization_id=second_organization.id,
        provider="smtp",
        sender_email="test@secondorg.com",
        sender_name="Second Organization",
    )
    async_session.add(settings)
    await async_session.commit()
    await async_session.refresh(settings)
    return settings


# ============================================================================
# ORGANIZATION SSO SETTINGS FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def test_sso_settings(async_session: AsyncSession, test_organization):
    """Create SSO settings for test organization."""
    from src.models.organization_sso_settings import OrganizationSSOSettings

    settings = OrganizationSSOSettings(
        organization_id=test_organization.id,
        sso_allowed=True,
        google_enabled=True,
        google_client_id="test-google-client-id",
    )
    async_session.add(settings)
    await async_session.commit()
    await async_session.refresh(settings)
    return settings


@pytest_asyncio.fixture(scope="function")
async def second_org_sso_settings(async_session: AsyncSession, second_organization):
    """Create SSO settings for second organization."""
    from src.models.organization_sso_settings import OrganizationSSOSettings

    settings = OrganizationSSOSettings(
        organization_id=second_organization.id,
        sso_allowed=True,
        google_enabled=False,
    )
    async_session.add(settings)
    await async_session.commit()
    await async_session.refresh(settings)
    return settings


# ============================================================================
# ORGANIZATION DELETION REQUEST FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def test_deletion_request(
    async_session: AsyncSession, test_organization, test_admin_user
):
    """Create a deletion request for test organization."""
    from src.models.organization_deletion_request import OrganizationDeletionRequest

    request = OrganizationDeletionRequest(
        organization_id=test_organization.id,
        requested_by_id=test_admin_user.id,
    )
    async_session.add(request)
    await async_session.commit()
    await async_session.refresh(request)
    return request


@pytest_asyncio.fixture(scope="function")
async def second_org_deletion_request(
    async_session: AsyncSession, second_organization, test_admin_user
):
    """Create a deletion request for second organization."""
    from src.models.organization_deletion_request import OrganizationDeletionRequest

    request = OrganizationDeletionRequest(
        organization_id=second_organization.id,
        requested_by_id=test_admin_user.id,
    )
    async_session.add(request)
    await async_session.commit()
    await async_session.refresh(request)
    return request


# ============================================================================
# ONBOARDING REVIEW COMMENT FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def test_review_comment(
    async_session: AsyncSession, test_organization, test_admin_user, test_user_user_type
):
    """Create a review comment for test organization."""
    from src.models.onboarding_review_comment import (
        CommentAuthorType,
        OnboardingReviewComment,
    )

    comment = OnboardingReviewComment(
        organization_id=test_organization.id,
        user_user_type_id=test_user_user_type.id,
        author_id=test_admin_user.id,
        author_type=CommentAuthorType.ADMIN,
        comment="Test admin comment",
    )
    async_session.add(comment)
    await async_session.commit()
    await async_session.refresh(comment)
    return comment


@pytest_asyncio.fixture(scope="function")
async def second_org_review_comment(
    async_session: AsyncSession,
    second_organization,
    test_admin_user,
    second_org_user_user_type,
):
    """Create a review comment in second organization."""
    from src.models.onboarding_review_comment import (
        CommentAuthorType,
        OnboardingReviewComment,
    )

    comment = OnboardingReviewComment(
        organization_id=second_organization.id,
        user_user_type_id=second_org_user_user_type.id,
        author_id=test_admin_user.id,
        author_type=CommentAuthorType.ADMIN,
        comment="Second org admin comment",
    )
    async_session.add(comment)
    await async_session.commit()
    await async_session.refresh(comment)
    return comment


# ============================================================================
# CHANGELOG PERMISSION FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def changelog_write_permission(async_session: AsyncSession):
    """Create changelog:write permission."""
    permission = Permission(
        code="changelog:write",
        name="Write Changelog",
        description="Create, update, and delete changelog entries",
        resource="changelog",
        action="write",
        display_order=0,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)
    return permission


@pytest_asyncio.fixture(scope="function")
async def user_with_changelog_permission(
    async_session: AsyncSession,
    test_organization,
    test_role,
    changelog_write_permission,
    test_user,
):
    """Create a user with changelog:write permission through a role."""
    # Grant permission to the role
    role_permission = RolePermission(
        role_id=test_role.id,
        permission_id=changelog_write_permission.id,
        granted_by=test_user.id,
    )
    async_session.add(role_permission)
    await async_session.commit()

    # Create user with the role
    user = User(
        email="changeloguser@test.com",
        password=hash_password("ChangelogUser123!"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    # Assign role to user
    user_role = UserRole(
        user_id=user.id, role_id=test_role.id, organization_id=test_organization.id
    )
    async_session.add(user_role)
    await async_session.commit()

    return user


@pytest.fixture
def user_with_changelog_token(user_with_changelog_permission, test_organization) -> str:
    """Create a JWT token for user with changelog permission."""
    token = create_access_token(
        user_id=str(user_with_changelog_permission.id),
        organization_id=str(test_organization.id),
    )
    return f"Bearer {token}"
