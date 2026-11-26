# Common Development Tasks

Step-by-step guides for common FastAPI development tasks.

## Adding a Tenant-Scoped Model

### Files to Create/Modify

| Step | File | Action |
|------|------|--------|
| 1 | `src/models/<entity>.py` | Create model class |
| 2 | `src/models/organization.py` | Add relationship (if needed) |
| 3 | `src/serialisers/<entity>.py` | Create Pydantic schemas |
| 4 | `src/crud/<entity>.py` | Create async CRUD functions |
| 5 | `src/api/<entity>.py` | Create router endpoints |
| 6 | `src/api/v1/__init__.py` | Register router |
| 7 | `tests/api_tests/test_<entity>_isolation.py` | Add isolation tests |

### Model Template

Uses SQLAlchemy 2.0 `Mapped` syntax with type annotations:

```python
# src/models/project.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.models.organization import Organization

class Project(Base):
    __tablename__ = "project"

    # Standard fields (REQUIRED)
    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
    )
    deleted_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Multi-tenancy (REQUIRED for tenant-scoped models)
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )

    # Business fields
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")

    # Composite indexes for common queries
    __table_args__ = (
        Index("idx_project_org_name", "organization_id", "name"),
    )
```

### CRUD Pattern (Critical)

**Every query MUST filter by `organization_id`:**

```python
# src/crud/project.py
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.project import Project

async def get_by_id(session: AsyncSession, id: str, organization_id: str) -> Project | None:
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(Project).where(
            Project.id == UUID(id),
            Project.organization_id == org_uuid,
            Project.deleted_time.is_(None)
        )
    )
    return result.scalar_one_or_none()
```

### Router Pattern

```python
# src/api/project.py
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import CurrentUser, get_current_user, get_session

router = APIRouter(prefix="/projects", tags=["projects"])

@router.get("/{id}")
async def get_project(
    id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)]
):
    organization_id = current_user.organization_id
    project = await get_by_id(session, id, organization_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return project
```

---

## Authentication & Authorization

### Dependencies (from `src/api/deps`)

| Dependency | Use Case |
|------------|----------|
| `get_current_user` | Require login |
| `require_permission("resource:action")` | Require specific permission (preferred) |
| `require_any_permission("perm1", "perm2")` | Require any of permissions |
| `get_current_super_admin` | Require super admin |
| `get_current_user_admin` | Require owner or admin role |
| `require_role("role_name")` | Require specific role |

### Example

```python
from src.api.deps import get_current_user, require_permission, CurrentUser

# Require login only
@router.get("/data")
async def get_data(current_user: Annotated[CurrentUser, Depends(get_current_user)]):
    organization_id = current_user.organization_id
    # ...

# Require specific permission (PREFERRED)
@router.delete("/{id}")
async def delete_entity(
    current_user: Annotated[CurrentUser, Depends(require_permission("entities:delete"))]
):
    # Only users with entities:delete permission (or super admins)
```

**Note:** Prefer `require_permission()` over role checks for fine-grained access control.

---

## Audit Logging

### When to Audit

- CREATE, UPDATE, DELETE operations
- Permission/role changes
- Authentication events

### Pattern (using audit_service)

```python
from fastapi import Request
from src.services.audit import audit_service, get_client_ip, get_user_agent

@router.post("")
async def create_entity(
    request_body: CreateRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)]
):
    # ... create entity ...

    await audit_service.log_create(
        session=session,
        organization_id=current_user.organization_id,
        resource_type="Entity",
        resource_id=str(entity.id),
        actor_id=current_user.id,
        ip_address=get_client_ip(http_request),
        user_agent=get_user_agent(http_request),
        resource_data={"name": entity.name},
    )
```

Available methods: `log_create()`, `log_update()`, `log_delete()`

---

## Background Jobs (ARQ)

### 1. Define Task

```python
# src/workers/tasks.py
async def process_report_task(ctx, report_id: str, user_email: str) -> dict:
    session_factory = ctx.get("session_factory")
    async with session_factory() as session:
        # Process...
        return {"status": "completed"}
```

### 2. Register Task

```python
# src/workers/worker.py
from src.workers.job_metrics import instrument_task

class WorkerSettings(BaseWorkerSettings):
    functions = [
        instrument_task(process_report_task),
        # ...
    ]
```

### 3. Enqueue

```python
from src.services.tasks import task_queue

job_id = await task_queue.enqueue_job("process_report_task", report_id=id, user_email=email)
```

---

## Database Migrations

Use `make` commands from `app/backend/`:

```bash
# Generate migration from model changes
make migrate-new msg="add_project_model"

# Apply migrations
make migrate

# Rollback one step
alembic downgrade -1
```

**Never manually write migrations** - always autogenerate with `make migrate-new`.

---

## Quick Reference Commands

From `app/backend/`:

| Command | Purpose |
|---------|---------|
| `make test` | Run tests |
| `make lint` | Run ruff and mypy |
| `make format` | Format with black and ruff |
| `make dev` | Start development server |
| `curl localhost:8000/health` | Health check |
| `open localhost:8000/docs` | API docs |

---

## Checklist: New Feature

- [ ] Model with `organization_id` and standard fields (id, created_time, updated_time, deleted_time)
- [ ] Relationship in Organization model (if bidirectional navigation needed)
- [ ] Serializers in `src/serialisers/` (Create, Update, Get, List)
- [ ] CRUD functions in `src/crud/` (all filter by `organization_id`)
- [ ] Router with auth dependencies in `src/api/`
- [ ] Register router in `src/api/v1/__init__.py`
- [ ] Isolation tests for tenant boundary
- [ ] Audit logging for mutations
