# Execute API Task

Create an API router for the rescued project.

## Arguments
- `$1` - ADW ID
- `$2` - Domain name (e.g., "user", "post", "category")

## Context Files to Read (MANDATORY)
- `ai_docs/backend/context/api.md`
- `ai_docs/backend/context/auth.md`

## Instructions

### 1. Read CRUD and Schema

Read the CRUD service and schemas:
- `app/backend/src/crud/{domain}.py`
- `app/backend/src/schemas/{domain}.py`

### 2. Create API Router

Create `app/backend/src/api/v1/{domain}s.py` (note plural)

**CRITICAL Requirements:**
- Use dependency injection for auth and session
- Get `organization_id` from authenticated user context
- Use `create_http_exception` with `detail_code` for errors
- Follow RESTful conventions

**Standard Router Pattern:**

```python
import uuid
from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_session
from src.crud.{domain} import {domain}_crud
from src.models.user import User
from src.schemas.{domain} import (
    {DomainName}Create,
    {DomainName}Update,
    {DomainName}Response,
)
from src.schemas.common import PaginatedResponse
from src.core.exceptions import create_http_exception

router = APIRouter(prefix="/{domain}s", tags=["{DomainName}s"])


@router.post("", response_model={DomainName}Response, status_code=201)
async def create_{domain}(
    data: {DomainName}Create,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> {DomainName}Response:
    """Create a new {domain}."""
    result = await {domain}_crud.create(
        session=session,
        organization_id=current_user.organization_id,
        data=data,
    )
    await session.commit()
    return {DomainName}Response.model_validate(result)


@router.get("", response_model=PaginatedResponse[{DomainName}Response])
async def list_{domain}s(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[{DomainName}Response]:
    """List {domain}s with pagination."""
    items = await {domain}_crud.get_multi(
        session=session,
        organization_id=current_user.organization_id,
        skip=skip,
        limit=limit,
    )
    total = await {domain}_crud.count(
        session=session,
        organization_id=current_user.organization_id,
    )
    return PaginatedResponse(
        items=[{DomainName}Response.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{{id}}", response_model={DomainName}Response)
async def get_{domain}(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> {DomainName}Response:
    """Get a {domain} by ID."""
    result = await {domain}_crud.get(
        session=session,
        organization_id=current_user.organization_id,
        id=id,
    )
    if not result:
        raise create_http_exception(
            status_code=404,
            detail="{DomainName} not found",
            detail_code="{DOMAIN}_NOT_FOUND",
        )
    return {DomainName}Response.model_validate(result)


@router.put("/{{id}}", response_model={DomainName}Response)
async def update_{domain}(
    id: uuid.UUID,
    data: {DomainName}Update,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> {DomainName}Response:
    """Update a {domain}."""
    result = await {domain}_crud.update(
        session=session,
        organization_id=current_user.organization_id,
        id=id,
        data=data,
    )
    if not result:
        raise create_http_exception(
            status_code=404,
            detail="{DomainName} not found",
            detail_code="{DOMAIN}_NOT_FOUND",
        )
    await session.commit()
    return {DomainName}Response.model_validate(result)


@router.delete("/{{id}}", status_code=204)
async def delete_{domain}(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a {domain} (soft delete)."""
    success = await {domain}_crud.delete(
        session=session,
        organization_id=current_user.organization_id,
        id=id,
    )
    if not success:
        raise create_http_exception(
            status_code=404,
            detail="{DomainName} not found",
            detail_code="{DOMAIN}_NOT_FOUND",
        )
    await session.commit()
```

### 3. Register Router

**IMPORTANT:** Register in `app/backend/src/api/v1/__init__.py` (NOT `src/api/__init__.py`):

```python
from src.api.v1.{domain}s import router as {domain}s_router

v1_router.include_router({domain}s_router)
```

## Output

Report:
1. Router file path created
2. Endpoints implemented
3. Router registered

Example:
```
Created router: app/backend/src/api/v1/posts.py
Endpoints:
  POST /api/v1/posts - Create post
  GET /api/v1/posts - List posts
  GET /api/v1/posts/{id} - Get post
  PUT /api/v1/posts/{id} - Update post
  DELETE /api/v1/posts/{id} - Delete post
Registered in: app/backend/src/api/v1/__init__.py
```

## Validation

- Router file exists
- All endpoints use auth dependency
- Organization ID comes from current_user
- Errors use create_http_exception with detail_code
- Router registered in v1/__init__.py

$ARGUMENTS
