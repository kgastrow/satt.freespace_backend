# CRUD Patterns

CRUD functions are async data access functions in `src/crud/`.

## Core Principles

- All functions are `async def` with `AsyncSession` as first parameter
- **CRITICAL**: Tenant-scoped CRUD MUST accept and filter by `organization_id`
- Handle soft deletes: `where(Model.deleted_time.is_(None))`
- Return model instances or raise `ValueError`

## Function Signatures

### Tenant-Scoped (Standard)

```python
async def get_by_id(session: AsyncSession, id: str, organization_id: str) -> Model | None
async def get_all(session: AsyncSession, organization_id: str, limit=10, offset=0) -> tuple[list[Model], int]
async def create(session: AsyncSession, data: dict, organization_id: str) -> Model
async def delete(session: AsyncSession, id: str, organization_id: str) -> Model
```

### Global (No org filter)

```python
async def get_organization_by_id(session: AsyncSession, id: str) -> Organization | None
async def get_organizations(session: AsyncSession, limit=10, offset=0) -> tuple[list[Organization], int]
```

## Query Patterns

### Read with Offset Pagination

```python
async def get_items(session: AsyncSession, organization_id: str, limit=10, offset=0):
    org_uuid = UUID(organization_id)
    conditions = [Model.organization_id == org_uuid, Model.deleted_time.is_(None)]

    count_result = await session.execute(
        select(func.count()).select_from(Model).where(*conditions)
    )
    total = count_result.scalar() or 0

    result = await session.execute(
        select(Model).where(*conditions).limit(limit).offset(offset)
    )
    return result.scalars().all(), total
```

**Count Query - IMPORTANT:**
```python
# CORRECT - Efficient, counts all rows
select(func.count()).select_from(Model).where(*conditions)

# WRONG - Less efficient
select(func.count(Model.id)).where(*conditions)
```

### Cursor-Based Pagination (High-Volume Tables)

For high-volume tables, use keyset pagination on `(created_time, id)` for O(1) performance regardless of page depth (offset pagination degrades linearly).

**Cursor encoding/decoding:**
```python
def encode_cursor(created_time: datetime, id: UUID) -> str:
    data = {"t": created_time.isoformat(), "i": str(id)}
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()

def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    data = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    return datetime.fromisoformat(data["t"]), UUID(data["i"])
```

**Query pattern:**
```python
async def get_items_cursor(
    session: AsyncSession,
    organization_id: str,
    limit: int = 50,
    cursor: str | None = None,
) -> tuple[list[Model], str | None, bool]:
    conditions = [Model.organization_id == UUID(organization_id), Model.deleted_time.is_(None)]

    # Apply cursor condition for keyset pagination
    if cursor:
        cursor_time, cursor_id = decode_cursor(cursor)
        # For DESC order: (created_time, id) < (cursor_time, cursor_id)
        conditions.append(or_(
            Model.created_time < cursor_time,
            and_(Model.created_time == cursor_time, Model.id < cursor_id),
        ))

    # Fetch limit+1 to determine has_more
    result = await session.execute(
        select(Model)
        .where(*conditions)
        .order_by(desc(Model.created_time), desc(Model.id))
        .limit(limit + 1)
    )
    items = list(result.scalars().all())

    has_more = len(items) > limit
    if has_more:
        items = items[:limit]

    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(last.created_time, last.id)

    return items, next_cursor, has_more
```

**Reference:** `src/crud/request_log.py`, `src/crud/user.py` (`get_users_cursor`)

### Enhanced CRUD with Metadata Flags

For list endpoints requiring optional additional data (storage, last login, etc.), return `needs_*` flags so the API layer can decide whether to batch fetch.

```python
async def get_users_enhanced(
    session: AsyncSession,
    organization_id: str,
    limit: int = 10,
    offset: int = 0,
    fields: list[str] | None = None,  # Sparse fieldset
    # ... filters
) -> tuple[list[User], int, bool, bool, bool]:
    """Returns (users, total, needs_storage, needs_user_types, needs_last_login)"""

    # Determine what additional data is needed based on requested fields
    needs_storage = fields is None or "total_storage_bytes" in fields
    needs_user_types = fields is None or "user_types" in fields
    needs_last_login = fields is None or "last_login" in fields

    # Conditionally add eager loading
    if needs_user_types:
        data_query = data_query.options(
            selectinload(User.user_user_types).selectinload(UserUserType.user_type)
        )

    # ... execute query
    return users, total_count, needs_storage, needs_user_types, needs_last_login
```

**API layer usage:**
```python
users, total, needs_storage, needs_user_types, needs_last_login = await get_users_enhanced(...)

# Batch fetch only what's needed
if needs_storage and user_ids:
    storage_map = await get_users_storage_batch(session, user_ids, organization_id)
if needs_last_login and user_ids:
    last_login_map = await get_users_last_login_batch(session, user_ids, organization_id)
```

**Reference:** `src/crud/user.py` (`get_users_enhanced`), `src/api/users.py`

### Batch Query Patterns (Avoiding N+1)

When displaying lists with additional data per item, use batch queries:

```python
# CORRECT - Batch fetch all related data upfront
async def get_users_storage_batch(
    session: AsyncSession, user_ids: list[str], organization_id: str
) -> dict[str, int | None]:
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(FileUsage.user_id, FileUsage.total_size_bytes)
        .where(
            FileUsage.user_id.in_([UUID(uid) for uid in user_ids]),
            FileUsage.organization_id == org_uuid,
        )
    )
    return {str(row.user_id): row.total_size_bytes for row in result}

# WRONG - N+1 queries
for user in users:
    storage = await get_user_storage(session, user.id, org_id)  # Query per user
```

**Reference:** `src/crud/user.py` (`get_users_storage_batch`, `get_users_last_login_batch`)

### Complex Data Aggregation

For detail views requiring multiple related data sources, aggregate in a single CRUD function:

```python
async def get_user_full_detail(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
    current_session_id: str | None = None,
) -> dict | None:
    """Get complete user details with all related data."""
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    # Get user with eager loading of always-needed relationships
    user_result = await session.execute(
        select(User)
        .options(
            selectinload(User.user_roles).selectinload(UserRole.role),
            selectinload(User.user_user_types).selectinload(UserUserType.user_type),
            selectinload(User.avatar),
        )
        .where(User.id == user_uuid, User.organization_id == org_uuid, User.deleted_time.is_(None))
    )
    user = user_result.scalars().first()
    if not user:
        return None

    # Fetch additional data in parallel-friendly separate queries
    sessions = await _get_user_sessions(session, user_uuid, org_uuid)
    two_factor = await _get_user_two_factor(session, user_uuid, org_uuid)
    # ... etc

    return {
        "user": user,
        "sessions": sessions,
        "two_factor": two_factor,
        "current_session_id": current_session_id,
        # ...
    }
```

**Reference:** `src/crud/user.py` (`get_user_full_detail`)

### Create

```python
async def create_item(session: AsyncSession, data: dict, organization_id: str):
    org_uuid = UUID(organization_id)

    # Check uniqueness WITHIN organization
    existing = await session.execute(
        select(Model).where(
            Model.name == data["name"],
            Model.organization_id == org_uuid,
            Model.deleted_time.is_(None)
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"Item already exists")

    item = Model(**data, organization_id=org_uuid)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item
```

### Soft Delete

```python
async def delete_item(session: AsyncSession, id: str, organization_id: str):
    item = await get_by_id(session, id, organization_id)
    if not item:
        raise ValueError(f"Item {id} not found")
    item.deleted_time = datetime.now(timezone.utc)
    await session.commit()
    return item
```

## Type Safety

### Dynamic Conditions

```python
# CORRECT - ColumnElement supports .is_(None)
conditions: list[ColumnElement[bool]] = [Model.organization_id == org_uuid, Model.deleted_time.is_(None)]

# WRONG - BinaryExpression doesn't work with .is_(None)
conditions: list[BinaryExpression[bool]] = []
```

### Boolean/NULL Comparisons

```python
# CORRECT
Model.is_active.is_(True)
Model.deleted_time.is_(None)

# WRONG - Type errors with mypy
Model.is_active == True
Model.deleted_time == None
```

### Pagination Return

```python
# CORRECT - Returns int
total = count_result.scalar() or 0

# WRONG - Returns int | None
total = count_result.scalar()
```

## Relationship Loading

Async SQLAlchemy does not support lazy loading. Accessing unloaded relationships raises `MissingGreenlet`.

```python
# WRONG - Lazy load fails in async context
config = await get_config(session, key)
email = config.updated_by.email  # MissingGreenlet error

# CORRECT - Eager load with selectinload
from sqlalchemy.orm import selectinload

query = select(SystemConfig).options(selectinload(SystemConfig.updated_by))
result = await session.execute(query)
config = result.scalars().first()
email = config.updated_by.email  # Works
```

### Nested Selectinload

For relationships that themselves have relationships, chain `selectinload`:

```python
# Load User -> user_roles -> role (two levels deep)
select(User).options(
    selectinload(User.user_roles).selectinload(UserRole.role)
)

# Load User -> user_user_types -> user_type
select(User).options(
    selectinload(User.user_user_types).selectinload(UserUserType.user_type)
)
```

Use `selectinload` for one-to-many, `joinedload` for many-to-one when the relationship is always needed.

## Soft Delete State Fields

| Field | Used By | Meaning |
|-------|---------|---------|
| `deleted_time` | Most models | Standard soft delete / revocation |
| `deletion_requested_time` | Organization | Pending deletion |

```python
# UserRole uses deleted_time for revocation (revoked roles are soft-deleted)
select(UserRole).where(UserRole.deleted_time.is_(None))
```

## Background Worker Exception

Worker/cron functions may skip `organization_id` filter when processing all orgs:

```python
async def get_expired_tokens(session: AsyncSession):
    """Background cleanup - processes ALL organizations"""
    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.created_time < cutoff,
            RefreshToken.deleted_time.is_(None)
        )
        # No organization_id filter - worker processes all
    )
    return result.scalars().all()
```

## Security Rules

**NEVER:**
- Write tenant-scoped CRUD without `organization_id` parameter
- Query tenant-scoped models without filtering by `organization_id`
- Use `== None` for NULL checks (use `.is_(None)`)
- Use `== True/False` for booleans (use `.is_(True/False)`)
- Use `select(func.count(Model.id))` for counts (use `select(func.count()).select_from(Model)`)
- Omit `or 0` fallback on `scalar()` count results

**ALWAYS:**
- Filter by `organization_id` in ALL tenant-scoped queries
- Set `organization_id` when creating tenant-scoped models
- Filter out soft-deleted records
- Check model-specific state fields (deletion_requested_time for Organization, etc.)
- Use `scalar() or 0` for count operations (ensures `int` return type)
