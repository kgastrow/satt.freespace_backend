# Multi-Tenancy Architecture

**CRITICAL**: Row-level multi-tenancy with application-layer data isolation. **ALL tenant-scoped queries MUST filter by `organization_id`**.

## Core Principles

- Users belong to exactly one organization
- JWT tokens include `organization_id` for tenant context
- Super admins (`is_admin=True`) bypass organization restrictions

## Model Scoping

| Scope | Models |
|-------|--------|
| **Tenant-scoped** | User, UserRole, RefreshToken, UserOTP, File, FileUsage, AuditLog, UserNotification, UserNotificationPreference, ApiKey, ApiKeyPermission, OrganizationNotificationSettings, OrganizationFileSettings, OrganizationEmailSettings, OrganizationSSOSettings, OrganizationTwoFactorSettings, UserTwoFactor, UserIdentity, UserOnboardingProgress, UserUserType, Feedback, DataExportRequest, DataDeletionRequest, Report, ReportSchedule, PaymentCustomer, Payment |
| **Global** | Organization, Role, Permission, RolePermission, NotificationProvider, SystemConfig, FeatureFlag, UserType, OnboardingStep |
| **Mixed-scope** | NotificationTemplate, NotificationCategory, BulkNotification, Notification, Changelog, Announcement, HelpCenterArticle, HelpCenterCategory, CronJob, RequestLog |

Mixed-scope: `NULL organization_id` = system-wide, `UUID` = org-specific.

Note for Help Center content: although `HelpCenterArticle` / `HelpCenterCategory`
are mixed-scope models, the **anonymous** `/help/*` routes are hard-pinned to
platform-wide rows (`platform_only=True` -> `organization_id IS NULL`) regardless
of any org context. They previously passed `organization_id=None`, which the CRUD
layer read as "no filter", disclosing every tenant's published content to
unauthenticated callers.

## Data Isolation

| Rule | Implementation |
|------|----------------|
| Email uniqueness | Per-org partial unique index: `uq_user_org_email_active` (WHERE deleted_time IS NULL) |
| Role names | Globally unique (roles are system-wide) |
| User-role assignments | Tenant-scoped via UserRole table |

## Security Model

| User Type | Access |
|-----------|--------|
| Super admin (`is_admin=True`) | All organizations, bypass role checks |
| Regular user | Own organization only, role-based permissions |
| Inactive org users | Blocked (except super admins) |

---

## Standardized Query Patterns (HIGH-007)

### Recommended: tenant_query Helper Pattern

For consistency across all CRUD operations, use this standardized query builder pattern:

```python
from typing import Type, TypeVar
from uuid import UUID
from sqlalchemy import Select, select
from sqlalchemy.orm import DeclarativeBase

T = TypeVar("T", bound=DeclarativeBase)

def tenant_query(model: Type[T], org_id: UUID) -> Select:
    """
    Build a base query with standard tenant isolation.

    Always includes:
    - organization_id filter for tenant isolation
    - deleted_time IS NULL for soft delete support

    Usage:
        query = tenant_query(User, org_uuid)
        query = query.where(User.email == email)  # Add more conditions
        result = await session.execute(query)
    """
    return select(model).where(
        model.organization_id == org_id,
        model.deleted_time.is_(None)
    )
```

### When to Use Each Approach

| Approach | Use When | Example |
|----------|----------|---------|
| **Explicit Filter** | Simple single-table queries, custom joins, subqueries | `select(User).where(User.organization_id == org_uuid, User.deleted_time.is_(None))` |
| **tenant_query Helper** | Standard CRUD operations, consistent pattern needed | `tenant_query(User, org_uuid).where(User.email == email)` |
| **FilterSpec Abstraction** | API endpoints with DSL filtering (filter[field]=value) | `apply_filters(query, Model, filters, FIELD_MAPPING)` |

---

## Implementation Patterns

### Pattern 1: Explicit Filter (Simple Queries)

Use for straightforward CRUD operations:

```python
async def get_user_by_id(session: AsyncSession, user_id: str, organization_id: str):
    """Get user by ID within organization context. organization_id is required for tenant isolation."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(User).where(
            User.id == UUID(user_id),
            User.organization_id == org_uuid,  # REQUIRED: tenant isolation
            User.deleted_time.is_(None)         # REQUIRED: soft delete support
        )
    )
    return result.scalars().first()
```

### Pattern 2: Using FilterSpec with Query Builder (DSL Endpoints)

For API endpoints that support filter/sort DSL parameters:

```python
from src.core.query_params import parse_filters, parse_sort, get_pagination_params
from src.core.query_builder import apply_filters, apply_sort, apply_pagination, get_total_count

# Define allowed fields for the endpoint
FEEDBACK_FILTER_FIELDS = {"type", "status", "rating", "created_time"}
FEEDBACK_SORT_FIELDS = {"created_time", "type", "status", "rating"}
FEEDBACK_FIELD_MAPPING: Dict[str, str] = {}  # Map API names to model attributes if different

async def get_feedbacks_list(
    session: AsyncSession,
    organization_id: str,
    filters: Optional[List[FilterSpec]] = None,
    sorts: Optional[List[SortSpec]] = None,
    limit: int = 100,
    offset: int = 0,
) -> Tuple[List[Feedback], int]:
    """Get paginated list of feedback with DSL filtering and sorting."""
    org_uuid = UUID(organization_id)

    # Step 1: Build base query WITH tenant isolation FIRST
    base_query = (
        select(Feedback)
        .where(
            Feedback.organization_id == org_uuid,  # REQUIRED: tenant isolation
            Feedback.deleted_time.is_(None),        # REQUIRED: soft delete support
        )
    )

    # Step 2: Apply DSL filters (these are ADDITIONAL filters, not replacing org filter)
    if filters:
        base_query = apply_filters(base_query, Feedback, filters, FEEDBACK_FIELD_MAPPING)

    # Step 3: Get total count before pagination
    total_count = await get_total_count(session, base_query)

    # Step 4: Apply sorting and pagination
    if sorts:
        base_query = apply_sort(base_query, Feedback, sorts, FEEDBACK_FIELD_MAPPING)
    base_query = apply_pagination(base_query, limit, offset)

    result = await session.execute(base_query)
    return list(result.scalars().all()), total_count
```

### Pattern 3: API Endpoint with Tenant Context

Always use `current_user.organization_id` from JWT - never trust user input:

```python
@router.get("/{user_id}")
async def get_user(
    user_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)]
):
    # ALWAYS use current_user.organization_id from JWT - never trust user input
    user = await get_user_by_id(session, user_id, current_user.organization_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

### Pattern 4: Super Admin Cross-Org Access

For endpoints that allow super admins to query across organizations:

```python
@router.get("", response_model=FeedbackListResponse)
async def list_feedback_endpoint(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("feedback:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    organization_id: Optional[str] = Query(None, description="Filter by organization (super admin only)"),
):
    # Default to current user's organization
    filter_org_id = current_user.organization_id

    # Only system super admins (is_admin=True) can query across organizations
    if organization_id:
        if not current_user.is_admin:
            raise HTTPException(
                status_code=403,
                detail="Only super admins can view data from other organizations"
            )
        filter_org_id = organization_id

    return await get_feedbacks_list(session, organization_id=filter_org_id, ...)
```

### Pattern 5: Mixed-Scope Query Pattern

For models that can be org-specific or system-wide (NULL):

```python
async def get_template(session: AsyncSession, code: str, organization_id: str | None):
    """Try org-specific first, fall back to system-wide (NULL)."""
    if organization_id:
        result = await session.execute(
            select(NotificationTemplate).where(
                NotificationTemplate.code == code,
                NotificationTemplate.organization_id == UUID(organization_id),
                NotificationTemplate.deleted_time.is_(None)
            )
        )
        if template := result.scalar_one_or_none():
            return template

    # Fall back to system template (organization_id IS NULL)
    return (await session.execute(
        select(NotificationTemplate).where(
            NotificationTemplate.code == code,
            NotificationTemplate.organization_id.is_(None),
            NotificationTemplate.deleted_time.is_(None)
        )
    )).scalar_one_or_none()
```

### Pattern 6: Tenant-Scoped Model Definition

```python
class User(Base):
    __tablename__ = "user"
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )
    # Partial unique index for soft-delete support
    __table_args__ = (
        Index("uq_user_org_email_active", "organization_id", "email",
              unique=True, postgresql_where=text("deleted_time IS NULL")),
    )
```

---

## Common Mistakes to Avoid

### Mistake 1: Missing organization_id Filter

```python
# WRONG - No tenant isolation!
async def get_user_by_id(session: AsyncSession, user_id: str):
    result = await session.execute(
        select(User).where(User.id == UUID(user_id))  # Missing organization_id!
    )
    return result.scalars().first()

# CORRECT
async def get_user_by_id(session: AsyncSession, user_id: str, organization_id: str):
    result = await session.execute(
        select(User).where(
            User.id == UUID(user_id),
            User.organization_id == UUID(organization_id),  # REQUIRED
            User.deleted_time.is_(None)
        )
    )
    return result.scalars().first()
```

### Mistake 2: Trusting User Input for Organization ID

```python
# WRONG - Allows cross-tenant access!
@router.get("/{user_id}")
async def get_user(user_id: str, org_id: str = Query(...)):  # User controls org_id!
    return await get_user_by_id(session, user_id, org_id)

# CORRECT - Use organization_id from authenticated user's JWT
@router.get("/{user_id}")
async def get_user(
    user_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)]
):
    return await get_user_by_id(session, user_id, current_user.organization_id)
```

### Mistake 3: Forgetting deleted_time Filter

```python
# WRONG - Returns soft-deleted records!
result = await session.execute(
    select(User).where(User.organization_id == org_uuid)
)

# CORRECT
result = await session.execute(
    select(User).where(
        User.organization_id == org_uuid,
        User.deleted_time.is_(None)  # Exclude soft-deleted records
    )
)
```

### Mistake 4: Not Setting organization_id on Creation

```python
# WRONG - organization_id not set on new record!
new_user = User(email=email, password=hashed_password)

# CORRECT
new_user = User(
    email=email,
    password=hashed_password,
    organization_id=UUID(organization_id)  # REQUIRED on creation
)
```

### Mistake 5: Applying FilterSpec Before Tenant Filter

```python
# WRONG - FilterSpec might not include org filter, allowing cross-tenant access
base_query = select(Feedback)
base_query = apply_filters(base_query, Feedback, filters, FIELD_MAPPING)  # No org filter!

# CORRECT - Always apply tenant filter BEFORE FilterSpec
base_query = select(Feedback).where(
    Feedback.organization_id == org_uuid,
    Feedback.deleted_time.is_(None)
)
base_query = apply_filters(base_query, Feedback, filters, FIELD_MAPPING)  # Additional filters
```

### Mistake 6: Forgetting Tenant Filter in Subqueries

```python
# WRONG - Subquery missing organization_id filter!
user_type_subquery = (
    select(UserUserType.user_id)
    .where(UserUserType.user_type_id == user_type_uuid)
    .scalar_subquery()
)

# CORRECT
user_type_subquery = (
    select(UserUserType.user_id)
    .where(
        UserUserType.organization_id == org_uuid,  # REQUIRED in subquery too!
        UserUserType.user_type_id == user_type_uuid,
        UserUserType.deleted_time.is_(None),
    )
    .scalar_subquery()
)
```

---

## Background Worker Exception

Background workers processing ALL organizations are the **only exception** to org filtering:

| Valid | Invalid |
|-------|---------|
| Scheduled cleanup (tokens, files) | User-initiated API requests |
| System cron jobs (metrics, health) | Any user-triggered operation |
| Super admin operations | Operations returning data to users |

---

## Testing Requirements

Every tenant-scoped feature MUST include tests for:
- User in org A cannot access org B data
- Listings return only user's organization data
- Super admins can access all organizations
- Inactive orgs block regular user access

### Test Template for Tenant Isolation

See `app/backend/tests/api_tests/test_multitenancy_isolation.py` for comprehensive examples.

```python
@pytest.mark.asyncio
async def test_cannot_access_other_org_resource(
    async_session, test_organization, second_organization
):
    """Test that a user cannot access resources from another organization."""
    from src.crud.your_model import create_resource, get_resource_by_id

    # Create resource in second organization
    resource_in_org_b = await create_resource(
        session=async_session,
        data={"name": "Resource B"},
        organization_id=str(second_organization.id),
    )

    # Try to access from org A context - should return None
    fetched = await get_resource_by_id(
        async_session, str(resource_in_org_b.id), str(test_organization.id)
    )
    assert fetched is None  # Resource not visible to org A


@pytest.mark.asyncio
async def test_list_excludes_other_org_resources(
    async_session, test_organization, second_organization
):
    """Test that listing only returns resources from the specified organization."""
    from src.crud.your_model import create_resource, get_resources

    # Create resources in both orgs
    resource_a = await create_resource(async_session, {"name": "A"}, str(test_organization.id))
    resource_b = await create_resource(async_session, {"name": "B"}, str(second_organization.id))

    # List from org A - should only include org A resources
    resources_org_a, _ = await get_resources(async_session, str(test_organization.id))
    resource_ids = [str(r.id) for r in resources_org_a]

    assert str(resource_a.id) in resource_ids
    assert str(resource_b.id) not in resource_ids


@pytest.mark.asyncio
async def test_api_enforces_organization_isolation(
    client: AsyncClient,
    async_session,
    test_organization,
    second_organization,
    test_jwt_token,  # Token for user in test_organization
):
    """Test that API endpoint enforces organization isolation."""
    from src.crud.your_model import create_resource

    # Create resource in second organization
    resource_in_org_b = await create_resource(
        async_session,
        {"name": "Secret Resource"},
        str(second_organization.id),
    )

    # Try to access via API using token from org A
    response = await client.get(
        f"/api/v1/resources/{resource_in_org_b.id}",
        headers={"Authorization": test_jwt_token}
    )

    # Should return 404 (not 403, to avoid leaking existence)
    assert response.status_code == 404
```

---

## Critical Rules

| NEVER | ALWAYS |
|-------|--------|
| Write CRUD without `organization_id` filtering | Filter by `organization_id` in ALL tenant-scoped queries |
| Trust user input for `organization_id` | Use `current_user.organization_id` from JWT |
| Allow cross-organization data access | Set `organization_id` on record creation |
| Skip isolation tests for new features | Test tenant isolation for every new feature |
| Apply FilterSpec before tenant filter | Apply tenant filter FIRST, then FilterSpec |
| Forget tenant filter in subqueries | Include `organization_id` filter in ALL subqueries |
