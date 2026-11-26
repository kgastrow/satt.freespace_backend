# Execute CRUD Task

Create a CRUD service for the rescued project.

## Arguments
- `$1` - ADW ID
- `$2` - Domain name (e.g., "user", "post", "category")

## Context Files to Read (MANDATORY)
- `ai_docs/backend/context/crud.md`
- `ai_docs/backend/context/multitenancy.md`

## Instructions

### 1. Read Model Definition

Read `app/backend/src/models/{domain}.py` to understand:
- Field names and types
- Relationships
- Any special constraints

### 2. Create CRUD Service

Create `app/backend/src/crud/{domain}.py`

**CRITICAL Requirements:**
- ALL queries MUST filter by `organization_id`
- Use soft deletes (set `deleted_time`, never DELETE)
- All methods must be async
- Return Pydantic schemas, not ORM objects

**Standard CRUD Pattern:**

```python
import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.{domain} import {DomainName}
from src.schemas.{domain} import (
    {DomainName}Create,
    {DomainName}Update,
    {DomainName}Response,
)


class {DomainName}CRUD:
    """CRUD operations for {DomainName}.

    All operations are scoped to organization_id for tenant isolation.
    """

    async def create(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID,
        data: {DomainName}Create,
    ) -> {DomainName}:
        """Create a new {domain}."""
        db_obj = {DomainName}(
            organization_id=organization_id,
            **data.model_dump(),
        )
        session.add(db_obj)
        await session.flush()
        await session.refresh(db_obj)
        return db_obj

    async def get(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID,
        id: uuid.UUID,
    ) -> Optional[{DomainName}]:
        """Get a {domain} by ID (tenant-scoped)."""
        query = select({DomainName}).where(
            {DomainName}.id == id,
            {DomainName}.organization_id == organization_id,
            {DomainName}.deleted_time.is_(None),  # Exclude soft-deleted
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[{DomainName}]:
        """Get multiple {domain}s with pagination (tenant-scoped)."""
        query = (
            select({DomainName})
            .where(
                {DomainName}.organization_id == organization_id,
                {DomainName}.deleted_time.is_(None),
            )
            .offset(skip)
            .limit(limit)
            .order_by({DomainName}.created_time.desc())
        )
        result = await session.execute(query)
        return result.scalars().all()

    async def count(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID,
    ) -> int:
        """Count {domain}s (tenant-scoped)."""
        query = (
            select(func.count())
            .select_from({DomainName})
            .where(
                {DomainName}.organization_id == organization_id,
                {DomainName}.deleted_time.is_(None),
            )
        )
        result = await session.execute(query)
        return result.scalar_one()

    async def update(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID,
        id: uuid.UUID,
        data: {DomainName}Update,
    ) -> Optional[{DomainName}]:
        """Update a {domain} (tenant-scoped)."""
        db_obj = await self.get(session, organization_id, id)
        if not db_obj:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        await session.flush()
        await session.refresh(db_obj)
        return db_obj

    async def delete(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID,
        id: uuid.UUID,
    ) -> bool:
        """Soft delete a {domain} (tenant-scoped).

        NEVER hard delete - always set deleted_time.
        """
        db_obj = await self.get(session, organization_id, id)
        if not db_obj:
            return False

        db_obj.deleted_time = datetime.now(timezone.utc)
        await session.flush()
        return True


# Singleton instance
{domain}_crud = {DomainName}CRUD()
```

### 3. Create Pydantic Schemas

Create `app/backend/src/schemas/{domain}.py` if not exists:

```python
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class {DomainName}Base(BaseModel):
    # Common fields (exclude id, org_id, timestamps)
    pass


class {DomainName}Create({DomainName}Base):
    pass


class {DomainName}Update(BaseModel):
    # All fields optional for partial updates
    pass


class {DomainName}Response({DomainName}Base):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    created_time: datetime
    updated_time: datetime
```

## Output

Report:
1. CRUD file path created
2. Schema file path created
3. Methods implemented

Example:
```
Created CRUD: app/backend/src/crud/post.py
Created schemas: app/backend/src/schemas/post.py
Methods: create, get, get_multi, count, update, delete
All methods include organization_id filtering
```

## Validation

- CRUD file exists
- All methods filter by `organization_id`
- Delete method uses soft delete (sets deleted_time)
- All methods are async
- Schemas exist and match CRUD

$ARGUMENTS
