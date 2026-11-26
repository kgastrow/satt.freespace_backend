# Execute Model Task

Create a SQLAlchemy model for the rescued project.

## Arguments
- `$1` - ADW ID
- `$2` - Domain name (e.g., "user", "post", "category")
- `$3` - Path to schema analysis (optional)

## Context Files to Read (MANDATORY)
- `ai_docs/backend/context/models.md`
- `ai_docs/backend/context/multitenancy.md`

## Instructions

### 1. Read Source Schema

If schema path provided in `$3`, read the extracted schema to understand:
- Field names and types
- Relationships to other tables
- Constraints (unique, not null)
- Default values

Also check `discovery/schema_analysis.json` for the domain.

### 2. Create Model Following Template Patterns

Create `app/backend/src/models/{domain}.py`

**CRITICAL Requirements** (from multitenancy.md):
- Add `organization_id` FK for tenant isolation
- Use `deleted_time` for soft deletes (NEVER hard delete)
- Follow async patterns
- Use proper type hints with `Mapped[]`

**Standard Fields (include in ALL models):**

```python
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class {DomainName}(Base):
    __tablename__ = "{domain_plural}"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # Tenant isolation (REQUIRED)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Domain-specific fields
    # ... add fields from source schema ...

    # Audit timestamps
    created_time: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_time: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now()
    )

    # Soft delete (REQUIRED - never hard delete)
    deleted_time: Mapped[Optional[datetime]] = mapped_column(default=None)

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="{domain_plural}")
```

### 3. Type Mapping

Map source types to SQLAlchemy/PostgreSQL:

| Source Type | SQLAlchemy Type |
|-------------|-----------------|
| string/varchar | String(length) |
| text | Text |
| int/integer | Integer |
| bigint | BigInteger |
| float/double | Float |
| decimal | Numeric(precision, scale) |
| boolean | Boolean |
| date | Date |
| datetime/timestamp | DateTime(timezone=True) |
| uuid | UUID (use uuid.UUID) |
| json/jsonb | JSON |
| array | ARRAY(type) |

### 4. Register Model

Add import to `app/backend/src/models/__init__.py`:

```python
from src.models.{domain} import {DomainName}
```

### 5. Generate Migration

Run:
```bash
cd app/backend && make migrate-new msg="add_{domain}_model"
```

## Output

Report:
1. Model file path created
2. Key fields added
3. Relationships defined
4. Migration generated

Example output:
```
Created model: app/backend/src/models/post.py
Fields: id, organization_id, title, content, author_id, published, created_time, updated_time, deleted_time
Relationships: organization, author (User)
Migration: alembic/versions/xxxx_add_post_model.py
```

## Validation

- Model file exists at expected path
- Has `organization_id` field with FK
- Has `deleted_time` field for soft deletes
- Has proper type hints (Mapped[])
- Registered in `__init__.py`
- Migration generated successfully

$ARGUMENTS
