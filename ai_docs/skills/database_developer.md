# Database Developer Skill

Expert role for optimizing database performance: reviewing SQLAlchemy models, query patterns, indexes, and Redis caching.

## Tech Stack

| Technology | Purpose |
|------------|---------|
| PostgreSQL | Primary database |
| SQLAlchemy 2.0 | Async ORM with `AsyncSession` |
| PgBouncer | Connection pooling (transaction mode, port 6432) |
| Redis | Caching layer |
| Alembic | Migrations |

## Database Configuration

Key settings in `app/backend/src/core/config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `DATABASE_URL` | - | PostgreSQL connection string |
| `DB_STATEMENT_TIMEOUT_MS` | 30000 | Query timeout in ms (via `config.json` → `database.statement_timeout_ms`) |

### PgBouncer Transaction Mode

When using PgBouncer in transaction pooling mode, SQLAlchemy must use `NullPool` to avoid connection state issues. The application automatically detects PgBouncer via port 6432 or explicit configuration.

```python
# src/database.py
if using_pgbouncer:
    engine = create_async_engine(url, poolclass=NullPool, ...)
else:
    engine = create_async_engine(url, pool_size=5, max_overflow=10, ...)
```

The `statement_timeout` is set via asyncpg's `server_settings` parameter rather than SQLAlchemy's `connect_args` for proper async support.

## Required Context

Read before starting: `ai_docs/backend/context/models.md`, `ai_docs/backend/context/caching.md`, `ai_docs/backend/context/multitenancy.md`

## Model/CRUD Inventory

All models in `app/backend/src/models/`, CRUD in `app/backend/src/crud/`:

| Model | Tenant-Scoped | Key Indexes |
|-------|---------------|-------------|
| Organization | No (root) | `slug` (unique), `is_active` |
| User | Yes | `organization_id`, `email`, `phone` |
| Role | Yes | `organization_id` |
| UserRole | Yes | `organization_id` |
| RefreshToken | Yes | `organization_id`, `token` (unique) |
| UserOTP | Yes | `organization_id`, `otp_type` |
| AuditLog | Yes | Composite: `(org_id, actor_id, created_time)` |
| FileUsage | Yes | Composite: `(org_id, user_id, deleted_time)` |

## Index Analysis Workflow

### Model Index Review

For each model, verify:
1. Foreign keys have `index=True`
2. `organization_id` has `index=True`
3. Unique constraints scoped to organization
4. Timestamp columns indexed if sorted/filtered

### Query Pattern Analysis

Common patterns to check:

```python
# Org-scoped (most common) - needs: (organization_id, deleted_time)
select(User).where(User.organization_id == org_id, User.deleted_time.is_(None))

# Lookup within org - needs: (organization_id, email)
select(User).where(User.email == email, User.organization_id == org_id)

# Time-range - needs: (organization_id, created_time)
select(AuditLog).where(AuditLog.organization_id == org_id, AuditLog.created_time >= start).order_by(...)
```

### Relationship Review

| Check | Pattern |
|-------|---------|
| Eager loading | `lazy='selectin'` for one-to-many |
| Joined loading | `lazy='joined'` for small related data |
| Explicit loading | `selectinload(User.user_roles)` in queries |

## Redis Cache Review

### Current Cache Keys

| Type | Pattern | TTL |
|------|---------|-----|
| JWT Claims | `jwt:{token_hash}` | Min(expiry, 1hr) |
| Organization | `org:{org_id}` | 5 min |
| User | `user:{user_id}` | 5 min |
| User Roles | `user_roles:{org_id}:{user_id}` | 1 min |

### TTL Guidelines

| Data Type | TTL | Reason |
|-----------|-----|--------|
| Static config | 1 hr+ | Rarely changes |
| User profiles | 5 min | Moderate changes |
| Roles | 1 min | Security-sensitive |
| Session data | Match token | Security |

## Index Best Practices

**DO index:**
- Foreign keys (SQLAlchemy doesn't auto-index)
- Columns in frequent WHERE/ORDER BY/JOIN
- High cardinality filtered columns

**DON'T index:**
- Boolean 50/50 distribution
- Low cardinality columns
- Rarely queried columns
- Small tables (< 1000 rows)

### Composite Index Rules

1. Equality conditions first, range last
2. Include `deleted_time` for soft-delete queries
3. Match query column order

```python
# Good - matches: WHERE organization_id = ? AND email = ?
Index('idx_user_org_email', 'organization_id', 'email')

# Partial index (PostgreSQL) - only active rows
Index('idx_user_active', 'organization_id', 'email',
      postgresql_where=text("deleted_time IS NULL"))
```

## Analysis Commands

```bash
grep -r "index=True" app/backend/src/models/     # Find indexes
grep -r "ForeignKey" app/backend/src/models/     # Find FKs
grep -r "relationship" app/backend/src/models/   # Find relationships
grep -r "select(" app/backend/src/crud/          # Query patterns
grep -r "selectinload\|joinedload" app/backend/src/  # Eager loading
```

## Output Report Format

```markdown
# Database Audit Report

## Summary
[Priority findings]

## Model Review
### [ModelName]
- Current indexes: [list]
- Issues: [list]
- Recommendations: [list with code]

## Query Patterns
### [CRUD File]
- N+1 issues: [none/description]
- Missing index support: [queries]

## Redis Recommendations
| Data | Action | TTL | Reason |
|------|--------|-----|--------|

## Priority Actions
### High (Performance)
1. [Action] - [Expected improvement]

### Medium (Optimization)
1. [Action]

## Migrations Needed
[Alembic migration requirements]
```

## Migration Template

```python
# alembic/versions/xxx_add_indexes.py
def upgrade():
    op.create_index('idx_user_org_email', 'user', ['organization_id', 'email'])
    # Partial index (PostgreSQL)
    op.execute("""CREATE INDEX idx_user_active ON "user" (organization_id, email) WHERE deleted_time IS NULL""")

def downgrade():
    op.drop_index('idx_user_org_email', 'user')
    op.drop_index('idx_user_active', 'user')
```

## Key Reminders

| Rule | Reason |
|------|--------|
| Test with EXPLAIN ANALYZE | Measure before/after |
| Consider write overhead | Indexes slow INSERT/UPDATE |
| Monitor cache hit rates | Track effectiveness |
| Multi-tenancy always | Every optimization maintains isolation |
| PgBouncer compatibility | Avoid server-side prepared statements |
| Async-first | All ops use `AsyncSession` |
| Migrations required | All schema changes via Alembic |
