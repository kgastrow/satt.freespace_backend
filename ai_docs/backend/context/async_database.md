# Async PostgreSQL Patterns

## Session Management

**API Routes** - Use `get_session` dependency (alias for `get_async_session`):
```python
from src.api.deps import get_session

async def endpoint(session: Annotated[AsyncSession, Depends(get_session)]):
    result = await session.execute(query)
    # Auto-commit on success, rollback on exception
```

**Worker Tasks** - Get session_factory from ARQ context:
```python
session_factory = ctx.get("session_factory")
if not session_factory:
    raise RuntimeError("Database session factory not available")

async with session_factory() as session:
    result = await session.execute(query)
    await session.commit()  # Explicit commit required
```

## Relationship Loading

Lazy loading fails in async - raises `MissingGreenlet`. Always use eager loading:
```python
query = select(User).options(selectinload(User.user_roles))
```

## PgBouncer Constraints

Transaction pooling mode (via NullPool) means:
- No `LISTEN/NOTIFY` (use Redis pub/sub instead)
- No advisory locks or temp tables
- No session-level settings (reset between transactions)
- Prepared statements disabled (`statement_cache_size=0`)

## Common Patterns

**Count queries**:
```python
select(func.count()).select_from(Model).where(...)
```

**Dynamic conditions**:
```python
conditions: list[ColumnElement[bool]] = [Model.deleted_time.is_(None)]
if org_id:
    conditions.append(Model.organization_id == org_id)
query = select(Model).where(*conditions)
```

**Batch operations** (worker tasks):
```python
BATCH_SIZE = 1000
while True:
    result = await session.execute(select(Model.id).where(...).limit(BATCH_SIZE))
    ids = [row[0] for row in result.all()]
    if not ids:
        break
    await session.execute(update(Model).where(Model.id.in_(ids)).values(...))
    await session.commit()
    if len(ids) < BATCH_SIZE:
        break
```
