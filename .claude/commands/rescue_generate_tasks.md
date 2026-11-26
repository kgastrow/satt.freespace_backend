# Generate Task Graph

Generate the complete task graph for the rescue execution phase.

## Arguments
- `$1` - ADW ID

## Input Files (read all)
- `discovery/discovery_summary.md`
- `discovery/structure_report.json`
- `discovery/feature_map.json`
- `discovery/ui_catalog.json`
- `discovery/schema_analysis.json`
- `triage/backend_classification.json`
- `triage/component_scores.json`
- `triage/ui_rescue_plan.md`

## Context Files to Read
- `ai_docs/backend/context/models.md`
- `ai_docs/backend/context/crud.md`
- `ai_docs/backend/context/api.md`
- `ai_docs/frontend/context/components.md`

## Instructions

Generate a task graph that follows this execution order:

### Phase 1: Backend Foundation

For each domain in `backend_classification.json` with verdict REPLACE or ADAPT:

1. **Model tasks** (no dependencies):
   - Create SQLAlchemy model following template patterns
   - Include `organization_id` for multi-tenancy
   - Include soft delete (`deleted_time`)

2. **CRUD tasks** (depends on model):
   - Create CRUD service following template patterns
   - Always filter by `organization_id`
   - Include pagination support

3. **API tasks** (depends on CRUD):
   - Create router following template patterns
   - Include auth dependencies
   - Register in v1 router

### Phase 2: Frontend Rescue

For each component in `ui_catalog.json` by migration tier:

1. **AUTO tier** (parallel, depends on backend if needed):
   - Direct extraction with styling preservation
   - Add i18n for all strings

2. **ASSISTED tier** (depends on related AUTO components):
   - Extraction with state mapping
   - Review flags for manual attention

3. **MANUAL tier** (last, depends on ASSISTED):
   - Create skeleton from source
   - Mark TODOs for completion

### Phase 3: Integration

After backend + frontend:

1. **Wire tasks** (depends on component + API):
   - Connect components to new backend APIs
   - Replace fetch/axios with RTK Query

2. **Test tasks** (depends on wire):
   - Generate tests for each feature
   - Include tenant isolation tests

### Task ID Format

```
task-{NNN}-{type}-{domain_or_component}
```

Examples:
- `task-001-model-user`
- `task-002-crud-user`
- `task-003-api-user`
- `task-010-component-UserCard`
- `task-020-wire-UserCard`
- `task-030-test-user`

### Dependency Rules

1. Model tasks have no dependencies
2. CRUD tasks depend on their model
3. API tasks depend on their CRUD
4. Component tasks depend on their API (if they call it)
5. Wire tasks depend on component + API
6. Test tasks depend on wire

## Output

Create `triage/task_graph.json`:

```json
{
  "version": 1,
  "generated_at": "2024-01-15T10:30:00Z",
  "adw_id": "{adw_id}",
  "phases": [
    {
      "id": "backend-foundation",
      "name": "Backend Foundation",
      "description": "Create models, CRUD, and API endpoints",
      "tasks": ["task-001-model-user", "task-002-crud-user", "task-003-api-user"]
    },
    {
      "id": "frontend-rescue",
      "name": "Frontend Rescue",
      "description": "Extract and adapt UI components",
      "tasks": ["task-010-component-Button", "task-011-component-UserCard"]
    },
    {
      "id": "integration",
      "name": "Integration",
      "description": "Wire components to APIs and test",
      "tasks": ["task-020-wire-UserCard", "task-030-test-user"]
    }
  ],
  "tasks": [
    {
      "id": "task-001-model-user",
      "type": "model",
      "phase": "backend-foundation",
      "description": "Create User model with tenant isolation",
      "inputs": [],
      "outputs": ["app/backend/src/models/user.py"],
      "slash_command": "/rescue_execute_model",
      "args": ["user", "discovery/schema_analysis.json"],
      "status": "pending",
      "retry_count": 0,
      "max_retries": 3
    },
    {
      "id": "task-002-crud-user",
      "type": "crud",
      "phase": "backend-foundation",
      "description": "Create User CRUD service",
      "inputs": ["task-001-model-user"],
      "outputs": ["app/backend/src/crud/user.py"],
      "slash_command": "/rescue_execute_crud",
      "args": ["user"],
      "status": "pending",
      "retry_count": 0,
      "max_retries": 3
    },
    {
      "id": "task-003-api-user",
      "type": "api",
      "phase": "backend-foundation",
      "description": "Create User API router",
      "inputs": ["task-002-crud-user"],
      "outputs": ["app/backend/src/api/v1/users.py"],
      "slash_command": "/rescue_execute_api",
      "args": ["user"],
      "status": "pending",
      "retry_count": 0,
      "max_retries": 3
    },
    {
      "id": "task-010-component-Button",
      "type": "component",
      "phase": "frontend-rescue",
      "description": "Extract Button component",
      "inputs": [],
      "outputs": ["app/frontend/src/components/ui/Button.tsx"],
      "slash_command": "/rescue_execute_component",
      "args": ["source/src/components/Button.tsx", "auto", "app/frontend/src/components/ui/Button.tsx"],
      "status": "pending",
      "retry_count": 0,
      "max_retries": 3
    }
  ],
  "summary": {
    "total_tasks": 34,
    "by_type": {
      "model": 4,
      "crud": 4,
      "api": 4,
      "component": 18,
      "wire": 4,
      "test": 0
    },
    "by_phase": {
      "backend-foundation": 12,
      "frontend-rescue": 18,
      "integration": 4
    },
    "estimated_hours_min": 20,
    "estimated_hours_max": 35
  }
}
```

## Validation

- File exists and is valid JSON
- All tasks have unique IDs
- Dependencies form a valid DAG (no cycles)
- Every domain from backend_classification has corresponding tasks
- Every component from ui_catalog has a corresponding task
- All tasks have valid slash_command values

$ARGUMENTS
