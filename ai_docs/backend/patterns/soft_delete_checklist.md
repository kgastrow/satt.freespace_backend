# Soft Delete Checklist

## What are Soft Deletes?

Soft deletes are a data management pattern where records are never physically removed from the database. Instead, they are marked as "deleted" by setting a `deleted_time` timestamp. This approach provides:

- **Data Recovery**: Accidentally deleted records can be restored
- **Audit Trail**: Complete history of all data, including deletions
- **Referential Integrity**: Foreign key references remain valid
- **Compliance**: Supports data retention requirements

**CRITICAL: This codebase uses soft deletes exclusively. Never use hard deletes (SQL DELETE) on business data.**

## How to Implement Soft Deletes

### 1. Model Definition

All models must include the `deleted_time` field:

```python
from datetime import datetime
from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

class MyModel(Base):
    # ... other fields ...

    # Soft delete field - NULL means not deleted
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

### 2. Performing a Soft Delete

Set `deleted_time` to the current UTC timestamp:

```python
from datetime import datetime, timezone

async def delete_item(session: AsyncSession, id: str, organization_id: str):
    item = await get_by_id(session, id, organization_id)
    if not item:
        raise ValueError(f"Item {id} not found")

    # Soft delete - set timestamp
    item.deleted_time = datetime.now(timezone.utc)

    await session.commit()
    return item
```

**Reference:** `src/crud/user.py` (delete_user function)

### 3. Querying Non-Deleted Records

Always filter for `deleted_time.is_(None)` in queries:

```python
from sqlalchemy import select

# CORRECT - Filter out soft-deleted records
result = await session.execute(
    select(Model).where(
        Model.organization_id == org_uuid,
        Model.deleted_time.is_(None)  # Only non-deleted records
    )
)
```

**Reference:** All CRUD functions in `src/crud/`

## Checklist for New Features

### When Writing Queries

- [ ] **Read operations**: Include `Model.deleted_time.is_(None)` in WHERE clause
- [ ] **Count operations**: Include `Model.deleted_time.is_(None)` in WHERE clause
- [ ] **Existence checks**: Include `Model.deleted_time.is_(None)` in WHERE clause
- [ ] **Uniqueness checks**: Include `Model.deleted_time.is_(None)` to allow recreating soft-deleted records

### When Writing Delete Operations

- [ ] **Use soft delete**: Set `deleted_time = datetime.now(timezone.utc)`
- [ ] **Never use SQL DELETE**: No `session.delete(obj)` or raw DELETE statements
- [ ] **Cascade considerations**: Soft delete related records if needed

### When Writing Create Operations

- [ ] **Uniqueness validation**: Check for existing non-deleted records only
- [ ] **Allows recreation**: Users can recreate previously soft-deleted records

### When Writing Unique Constraints

- [ ] **Use partial unique indexes**: Allow recreating soft-deleted records
- [ ] **PostgreSQL syntax**: Use `postgresql_where=text("deleted_time IS NULL")`

## Common Mistakes to Avoid

### Mistake 1: Forgetting to Filter Deleted Records

```python
# WRONG - Returns deleted records
result = await session.execute(
    select(User).where(User.organization_id == org_uuid)
)

# CORRECT - Excludes deleted records
result = await session.execute(
    select(User).where(
        User.organization_id == org_uuid,
        User.deleted_time.is_(None)
    )
)
```

### Mistake 2: Using == None Instead of .is_(None)

```python
# WRONG - Type error with mypy, may not work correctly
Model.deleted_time == None

# CORRECT - Proper NULL comparison in SQLAlchemy
Model.deleted_time.is_(None)
```

### Mistake 3: Using Hard Delete

```python
# WRONG - Hard delete destroys data permanently
await session.delete(item)
# or
await session.execute(delete(Model).where(Model.id == item_id))

# CORRECT - Soft delete preserves data
item.deleted_time = datetime.now(timezone.utc)
await session.commit()
```

### Mistake 4: Using UniqueConstraint Instead of Partial Index

```python
# WRONG - Prevents recreating soft-deleted records
__table_args__ = (
    UniqueConstraint("organization_id", "email", name="uq_user_org_email"),
)

# CORRECT - Allows recreating soft-deleted records
from sqlalchemy import Index, text

__table_args__ = (
    Index(
        "uq_user_org_email_active",
        "organization_id",
        "email",
        unique=True,
        postgresql_where=text("deleted_time IS NULL"),
    ),
)
```

**Reference:** `src/models/user.py`, migration `a2d8539b7e70_fix_partial_unique_indexes_for_soft_.py`

### Mistake 5: Not Checking Soft Delete in Uniqueness Validation

```python
# WRONG - Blocks creation if soft-deleted record exists
existing = await session.execute(
    select(Model).where(Model.email == email, Model.organization_id == org_uuid)
)
if existing.scalar_one_or_none():
    raise ValueError("Email already exists")

# CORRECT - Only check non-deleted records
existing = await session.execute(
    select(Model).where(
        Model.email == email,
        Model.organization_id == org_uuid,
        Model.deleted_time.is_(None)
    )
)
if existing.scalar_one_or_none():
    raise ValueError("Email already exists")
```

**Reference:** `src/crud/user.py` (create_user function)

## Code Examples from Codebase

### Example: User Deletion (src/crud/user.py)

```python
async def delete_user(session: AsyncSession, request: dict, organization_id: str):
    org_uuid = UUID(organization_id)
    delete_user_request = DeleteUserRequest(**request)

    result = await session.execute(
        select(User).where(
            User.id == delete_user_request.id,
            User.organization_id == org_uuid,
            User.deleted_time.is_(None),  # Only find non-deleted users
        )
    )
    user = result.scalars().first()

    if not user:
        raise ValueError(f"User with id {delete_user_request.id} not found.")

    # Soft delete
    user.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(user)
    except IntegrityError:
        await session.rollback()
        raise
    return user
```

### Example: Session Revocation (src/crud/user.py)

```python
async def revoke_user_session(
    session: AsyncSession,
    user_id: str,
    session_id: str,
    organization_id: str,
) -> bool:
    """Revoke a specific user session (soft delete the refresh token)."""
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.id == session_id,
            RefreshToken.user_id == user_uuid,
            RefreshToken.organization_id == org_uuid,
            RefreshToken.deleted_time.is_(None),
        )
    )
    token = result.scalars().first()

    if not token:
        return False

    # Soft delete the token
    token.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        return True
    except IntegrityError:
        await session.rollback()
        return False
```

### Example: Paginated Query with Soft Delete Filter (src/crud/organization.py)

```python
async def get_organizations(
    session: AsyncSession, limit: int = 10, offset: int = 0
) -> Tuple[List[Organization], int]:
    # Count query - includes soft delete filter
    count_result = await session.execute(
        select(func.count())
        .select_from(Organization)
        .where(Organization.deleted_time.is_(None))
    )
    total_count = count_result.scalar() or 0

    # Data query - includes soft delete filter
    result = await session.execute(
        select(Organization)
        .where(Organization.deleted_time.is_(None))
        .limit(limit)
        .offset(offset)
    )
    organizations = result.scalars().all()

    return list(organizations), total_count
```

## Special Cases

### Organization Deletion Request

Organizations use a two-phase deletion with `deletion_requested_time`:

```python
# Phase 1: Mark deletion requested
org.deletion_requested_time = datetime.now(timezone.utc)

# Phase 2: Actual soft delete (after retention period)
org.deleted_time = datetime.now(timezone.utc)
```

**Reference:** `src/crud/organization.py`, `src/models/organization.py`

### Background Workers

Background workers processing all organizations may intentionally skip `organization_id` filter but must still filter `deleted_time`:

```python
async def get_expired_tokens(session: AsyncSession):
    """Background cleanup - processes ALL organizations"""
    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.created_time < cutoff,
            RefreshToken.deleted_time.is_(None)  # Still filter soft deletes!
        )
        # No organization_id filter - worker processes all
    )
    return result.scalars().all()
```

## Testing Soft Deletes

When writing tests, verify:

1. **Deleted records are excluded from queries**
2. **Soft delete sets deleted_time correctly**
3. **Soft-deleted records can be "recreated"**
4. **Related data handling is correct**

```python
async def test_soft_delete_excludes_from_query(async_session, test_org):
    # Create and soft delete a user
    user = User(email="test@example.com", organization_id=test_org.id)
    async_session.add(user)
    await async_session.commit()

    user.deleted_time = datetime.now(timezone.utc)
    await async_session.commit()

    # Verify user is excluded from normal queries
    result = await async_session.execute(
        select(User).where(
            User.organization_id == test_org.id,
            User.deleted_time.is_(None)
        )
    )
    users = result.scalars().all()
    assert user not in users
```

## Related Documentation

- [Models Pattern](../context/models.md) - Model field definitions and partial unique indexes
- [CRUD Patterns](../context/crud.md) - Query patterns with soft delete filtering
- [Multitenancy](../context/multitenancy.md) - Tenant isolation with organization_id
