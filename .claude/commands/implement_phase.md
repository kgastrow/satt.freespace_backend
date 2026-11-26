# Implement Phase

Implement a single phase from a multi-phase plan. This command focuses on implementing ONLY the files listed in the phase's scope, ensuring atomic, testable commits.

## Variables
phase_id: $1
plan_file: $2

## Instructions

### 1. Load and Parse Plan
- Read the multi-phase plan at `{plan_file}`
- Find the phase section with id `{phase_id}`
- Extract: Description, Scope (files), Relevant Context, Acceptance Criteria, Test Scope

### 2. Load Context
- Read the phase's `Relevant Context` section from the plan
- Load all listed context files from `ai_docs/` before implementing
- If the section says "None required", proceed directly to implementation
- If no `Relevant Context` section exists, read `.claude/commands/conditional_context.md` and load context based on the phase's scope

### 3. Understand Phase Boundaries (CRITICAL)

**You MUST only modify files listed in this phase's Scope section.**

- Files marked `(new)` should be created
- Files marked `(modify)` should be updated
- **DO NOT** touch any files outside the scope
- **DO NOT** "fix" or "improve" code in other files
- **DO NOT** add dependencies or imports to files outside scope
- If you discover something needs to change outside scope, note it but do not implement it

This boundary enforcement is critical because:
1. Other phases may modify those files
2. We need atomic, testable commits per phase
3. Context overflow prevention requires strict scope

### Forward Reference Prevention (CRITICAL)

**NEVER add an import, lazy import, or reference to a file/component that does not yet exist.** This includes:
- `import Foo from '@/pages/admin/FooPage'` — where `FooPage.tsx` hasn't been created yet
- `lazy(() => import('@/components/SomeWidget'))` — where `SomeWidget.tsx` is in a LATER phase
- Route config entries pointing to non-existent page components
- API router includes for non-existent modules

If the plan's scope includes a coordination file (e.g., `routes.ts`, `store/index.ts`, `__init__.py`), ONLY add registrations for components/modules that:
1. Already exist in the codebase, OR
2. Are being created as `(new)` files in THIS SAME phase

If you notice the plan expects you to reference a file from a later phase, **do not add that reference**. Note it in your output and proceed without it.

### 4. Implementation

For each file in the phase scope:

1. **New files**: Create with proper structure following codebase patterns
2. **Modified files**: Read first, make minimal necessary changes

Implementation guidelines:
- Follow existing patterns in the codebase
- Use async/await for all I/O operations (backend)
- Use soft deletes (`deleted_time`) - never hard delete
- For tenant-scoped models, always filter by `organization_id`
- Write clean, well-structured code without excessive comments
- **i18n (mandatory for UI work)**: ALL user-facing frontend strings must use the i18n `t()` function with keys added to ALL locale files under `app/frontend/src/locales/`. Never hardcode display text and never leave a locale missing a key.
- **Responsive (mandatory for UI work)**: ALL UI must work on BOTH mobile (390x844) and desktop (1440x900). No desktop-only layouts.

### 5. Database Migrations (if applicable)

If the phase involves model changes:
```bash
cd app/backend && make migrate-new  # Create migration
cd app/backend && make migrate      # Apply migration
```

### 6. Validation

After implementing, run the phase's scoped tests:
- For backend phases: `cd app/backend && pytest {test_scope} -v`
- For frontend phases: `cd app/frontend && npm run test -- {test_scope}`
- Always run: type checking / linting for the modified directories

### 7. Verify Acceptance Criteria

Before completing, verify each acceptance criterion from the phase is met.

## Output Format

After implementation, provide:

```
## Phase Implementation Summary

**Phase:** {phase_id}
**Status:** Completed / Partially Completed / Blocked

### Files Changed
- `path/to/file1.py` - Created: <brief description>
- `path/to/file2.ts` - Modified: <brief description>

### Acceptance Criteria
- [x] Criterion 1 - <how it was met>
- [x] Criterion 2 - <how it was met>
- [ ] Criterion 3 - <why not met, if applicable>

### Test Results
<output of scoped tests>

### Notes
<any issues encountered or things to note for subsequent phases>
```

## Example

If the phase is:
```
### Phase 1: backend-websocket-infrastructure
**Scope:**
- `app/backend/src/api/websocket.py` (new)
- `app/backend/src/services/connection_manager.py` (new)

**Acceptance Criteria:**
- WebSocket endpoint at /ws/connect
- Connection manager handles lifecycle
```

You would:
1. Create `app/backend/src/api/websocket.py` with the WebSocket endpoint
2. Create `app/backend/src/services/connection_manager.py` with the manager class
3. NOT modify any other files (like routers, __init__.py outside scope)
4. Run scoped tests
5. Report completion status

## Report
Provide the implementation summary in the format above.
