# Models Pattern and Conventions

Models use SQLAlchemy 2.0 declarative style in `app/backend/src/models/`.

## Standard Fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `id` | `UUID(as_uuid=True)` | All | Primary key, `default=uuid.uuid4` |
| `created_time` | `DateTime(timezone=True)` | All | Creation timestamp |
| `updated_time` | `DateTime(timezone=True)` | All | Last modified timestamp |
| `deleted_time` | `DateTime(timezone=True)` | All | Soft delete (NULL if not deleted) |
| `organization_id` | `UUID FK` | Tenant-scoped | Must include `index=True` |

### Timestamp Field Patterns

```python
from datetime import datetime, timezone

# created_time: Use default=
created_time: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
)

# updated_time: Use onupdate=, optionally add default= for initial value
updated_time: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
)

# deleted_time: No default (NULL means not deleted)
deleted_time: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True
)
```

**Note:** Some models use `Mapped[datetime]` (non-nullable) for timestamps on core entities like Organization. Either pattern is acceptable.

## Scope Types

| Scope | `organization_id` | Examples |
|-------|-------------------|----------|
| Tenant-scoped | `nullable=False` | User, UserRole, RefreshToken, FileUsage, ApiKey |
| Global | Not present | Organization, Role, Permission |
| Mixed | `nullable=True` | NotificationTemplate, NotificationCategory (NULL=system, UUID=org-specific) |

**Mixed-scope query pattern**: Try org-specific first, fall back to `organization_id.is_(None)`.

## Type Safety Rules

| Pattern | Correct | Why |
|---------|---------|-----|
| Column with default | `Mapped[bool] = mapped_column(..., nullable=False, default=True)` | `Mapped[Type]` requires non-nullable |
| Nullable column | `Mapped[str \| None] = mapped_column(..., nullable=True)` | `Mapped[Type \| None]` for nullable |
| Wrong | `Mapped[bool] = mapped_column(..., default=True)` | Missing `nullable=False` causes mypy error |

## Relationships

```python
# One-to-many
organization: Mapped["Organization"] = relationship("Organization", back_populates="users")

# Multiple FKs to same table - MUST specify foreign_keys
# Example from ImpersonationSession:
impersonator: Mapped["User"] = relationship("User", foreign_keys=[impersonator_id])
target_user: Mapped["User"] = relationship("User", foreign_keys=[target_user_id])

# Self-referential with remote_side
suspended_by_user: Mapped["User | None"] = relationship(
    "User", foreign_keys=[suspended_by], remote_side=[id], uselist=False
)
```

## Indexes and Unique Constraints

### Partial Unique Indexes (REQUIRED for Soft Delete)

**CRITICAL: Use partial unique indexes, NOT UniqueConstraint, for business keys.**

UniqueConstraint prevents recreating soft-deleted records. Use partial indexes with `postgresql_where`:

```python
from sqlalchemy import Index, text

__table_args__ = (
    # Partial unique index allows recreating soft-deleted records
    Index(
        "uq_user_org_email_active",
        "organization_id",
        "email",
        unique=True,
        postgresql_where=text("deleted_time IS NULL"),
    ),
)
```

**Security Exception**: Security keys (like API key hashes) that should never be reused MUST use UniqueConstraint:

```python
# From ApiKey model - key_hash must be globally unique (security requirement)
UniqueConstraint("key_hash", name="uq_api_key_hash"),
```

### Composite Index Guidelines

Use composite indexes when queries filter/sort on multiple columns:

```python
# For queries: WHERE organization_id = X AND deleted_time IS NULL ORDER BY created_time DESC
Index("ix_user_org_active_created", "organization_id", "deleted_time", desc("created_time"))
```

## Best Practices

1. **Never hard delete** - Use `deleted_time` for soft deletes
2. **Always timezone-aware** - `DateTime(timezone=True)`
3. **Index foreign keys** - Especially `organization_id`
4. **Scope unique constraints** - Include `organization_id` for tenant-scoped
5. **Multiple FKs to same table** - Use `foreign_keys` parameter
6. **Table names** - Singular, lowercase
