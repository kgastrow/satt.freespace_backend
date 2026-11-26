# Multi-Phase Feature Planning

Create a phased implementation plan for a large feature that exceeds single-agent context limits. This command produces a structured plan where each phase represents a logical unit of work that can run through build -> test -> review -> commit independently.

## Variables
issue_number: $1
adw_id: $2
issue_json: $3

## CRITICAL CONSTRAINTS — DO NOT VIOLATE

- You are a **PLANNER**, not an implementer. Your ONLY job is to produce plan content.
- **DO NOT** write any files. Not the plan file, not source code, nothing. The caller writes the plan to disk.
- **DO NOT** write any source code files (`.py`, `.ts`, `.tsx`, `.js`, `.css`, etc.)
- **DO NOT** run tests, linting, formatting, or any validation commands
- **DO NOT** install packages or run `uv add`, `npm install`, or similar
- **DO NOT** run `make`, `pytest`, `ruff`, `npm`, or any build/test commands
- **DO NOT** enter plan mode. Do not use the EnterPlanMode tool.
- The ONLY tools you should use are: Read, Glob, Grep (for codebase research)

### OUTPUT FORMAT (MANDATORY)
- Your final response must be the **complete plan content in markdown**, starting with `# Multi-Phase Feature:` and using the exact format specified in the Plan Format section below.
- **DO NOT** wrap the plan in a markdown code block (no triple backticks around the whole plan).
- **DO NOT** add any preamble, summary, or commentary before or after the plan content.
- Your response IS the plan — output it directly as markdown text.

## Instructions

### 1. Planning Overview

You are planning a LARGE feature that requires multiple implementation phases. Each phase must be:
- **Self-contained**: Implementable by a single agent without exceeding context limits
- **Bounded scope**: Touches 3-8 files maximum
- **Testable independently**: Has clear validation criteria
- **Committable atomically**: Produces a working, tested commit

### Planning Process

1. **Analyze Scope**: Read the feature requirements thoroughly from the issue
2. **Research Codebase**: Understand existing patterns, architecture, and conventions
3. **Identify Domains**: Separate backend, frontend, shared types, and integration concerns
4. **Define Phases**: Break into 3-8 phases, each targeting specific files
5. **Order Dependencies**: Determine which phases depend on others completing first
6. **Define Acceptance**: Each phase needs clear, testable criteria

### Phase Sizing Guidelines

Each phase should:
- Touch **3-8 files maximum** (new + modified)
- Be implementable in a **single agent session** (~15-30 minutes of work)
- Have **non-overlapping file scope** with other phases where possible
- Be **independently testable** with its own validation commands
- Produce a **working codebase** after completion (no broken imports/builds)

### Dependency Rules

- Phases with **no dependencies** should be listed first (can potentially run in parallel)
- Dependent phases must **explicitly list their dependencies** by phase ID
- Execution order must **respect all dependencies**
- A phase cannot start until all its dependencies are completed

### File Scope Boundaries

When defining phase scope, be explicit about which files are:
- **(new)**: Files that will be created
- **(modify)**: Existing files that will be modified

Avoid having multiple phases modify the same file when possible. If unavoidable, ensure later phases depend on earlier ones.

**Exception - backend test files**: All backend phases must use `backend_test_file` from metadata. First phase creates it, subsequent phases append to it.

### Shared File Coordination (CRITICAL)

Certain files are "coordination points" that multiple phases may need to modify (e.g., route configs, store registration, API router `__init__.py`). These require special handling:

**Common coordination point files:**
- `app/frontend/src/config/routes.ts` — route registration
- `app/frontend/src/store/index.ts` — reducer registration
- `app/backend/src/api/v1/__init__.py` — API router registration
- Any `__init__.py` that exports/registers from multiple phases
- Any `index.ts` barrel file that re-exports from multiple phases

**Rules for coordination points:**
1. **Only the phase that creates a component/module should register it** in coordination files. Include the coordination file in that phase's scope.
2. **NEVER add imports or references to components/modules that don't exist yet.** If Phase 3 creates `DeviceDetailPage`, only Phase 3's scope should include `routes.ts` to add that route — not an earlier phase.
3. **If a coordination file must appear in multiple phases**, each later phase MUST explicitly depend on all earlier phases that modify it.
4. **Validate no forward references**: For every import added in a phase, the imported file must either already exist OR be created within that same phase's scope. An import referencing a file created by a LATER phase is a planning error.

### Forward Reference Prevention (CRITICAL)

Before finalizing the plan, mentally validate each phase:
- For every `import` or `lazy(() => import(...))` that a phase will add, confirm the target file exists or is `(new)` in the SAME phase.
- If Phase N needs to import from a file created in Phase M (where M > N), that is a **planning error**. Restructure: either move the registration to Phase M, or merge the phases.

### API Completeness Validation (CRITICAL)

Before finalizing frontend phases, validate that every frontend page's data requirements have a matching backend endpoint from an earlier phase:
- For each frontend page, list the API calls it will need to make (list, get, create, update, delete).
- Verify that each required endpoint exists in a backend phase that the frontend phase depends on.
- If a frontend page needs an endpoint that no backend phase provides, you MUST either:
  1. Add the missing endpoint to an existing backend phase's scope, OR
  2. Create a new backend phase for it and add it as a dependency
- **Do NOT plan a frontend page that relies on an API endpoint that doesn't exist.** This is a planning error equivalent to a forward reference.

### Acceptance Criteria Achievability (CRITICAL)

Every acceptance criterion for a phase MUST be achievable using ONLY the files listed in that phase's scope:
- If a criterion requires creating a new file (e.g., a page component, a service), that file MUST be listed in the phase's scope.
- If a criterion cannot be fulfilled within the phase's scope, either:
  1. Add the required files to the phase's scope, OR
  2. Move the criterion to a phase that has the required files in scope, OR
  3. Remove the criterion and defer it to a future phase/feature
- **Do NOT add acceptance criteria that require out-of-scope work.** The reviewer will flag unachievable criteria as blockers, and the patch system cannot create out-of-scope files to fix them.

## Relevant Files

Focus on the following files to understand the codebase:
- `README.md` - Project overview and instructions
- `app/backend/src/` - Backend source code (models, crud, api, services)
- `app/frontend/src/` - Frontend source code
- `adws/README.md` - ADW system documentation

Read `.claude/commands/conditional_context.md` to check if the task requires additional context files.

## Multi-Tenancy Check (CRITICAL)

This codebase uses row-level multi-tenancy. For each phase involving tenant-scoped data:
1. Include `ai_docs/backend/context/multitenancy.md` in relevant context
2. Ensure CRUD operations filter by `organization_id`
3. Add isolation tests to the phase's acceptance criteria

## Plan Format

Output the plan using exactly this format:

```md
# Multi-Phase Feature: <feature name>

## Metadata
issue_number: `{issue_number}`
issue_title: `<title from issue_json>`
adw_id: `{adw_id}`
total_phases: `<number of phases>`
backend_test_file: `<single test file for backend, e.g. tests/unit_tests/test_websocket.py>`

## Feature Description
<2-4 sentences describing the feature, its purpose, and value to users>

## Phases

### Phase 1: <phase-id>
**Name:** <Human readable phase name>
**Description:** <1-2 sentences describing what this phase accomplishes>
**Dependencies:** none
**Scope:**
- `path/to/file1.py` (new)
- `path/to/file2.py` (modify)
- `path/to/file3.ts` (new)

**Relevant Context:**
<List context files from ai_docs/ that the implementer should read before implementing this phase. Evaluate conditional_context.md against this phase's scope. If none needed, write "None required">

**Acceptance Criteria:**
- <Specific, testable criterion 1>
- <Specific, testable criterion 2>
- <Specific, testable criterion 3>
- Codebase builds successfully after this phase (no broken imports or forward references)

**Test Scope:** `<directory or file pattern for scoped testing>`

---

### Phase 2: <phase-id>
**Name:** <Human readable phase name>
**Description:** <1-2 sentences describing what this phase accomplishes>
**Dependencies:** Phase 1
**Scope:**
- `path/to/file4.ts` (new)
- `path/to/file5.ts` (modify)

**Relevant Context:**
<List context files from ai_docs/ for this phase. If none needed, write "None required">

**Acceptance Criteria:**
- <Specific, testable criterion 1>
- <Specific, testable criterion 2>
- Codebase builds successfully after this phase (no broken imports or forward references)

**Test Scope:** `<directory or file pattern for scoped testing>`

---

<Continue for all phases...>

---

## Execution Order
1. Phase 1: <phase-id>
2. Phase 2: <phase-id>
3. Phase 3: <phase-id>
<etc>

## Integration Validation
After all phases complete, run these validation commands:
- `cd app/backend && make test` - Full backend test suite
- `cd app/backend && make lint` - Backend linting
- `cd app/frontend && npm run build` - Full frontend build
- `cd app/frontend && npm run test` - Frontend tests
<Add any feature-specific E2E tests>

## Notes
<Any additional context, considerations, or future enhancements>
```

## Example Phase Structure

Here's an example of a well-structured multi-phase plan for "Add WebSocket Support":

```
## Metadata
...
backend_test_file: `app/backend/tests/unit_tests/test_websocket.py`

### Phase 1: backend-websocket-infrastructure
**Name:** Backend WebSocket Infrastructure
**Description:** Add WebSocket endpoint and connection manager to FastAPI backend
**Dependencies:** none
**Scope:**
- `app/backend/src/api/websocket.py` (new)
- `app/backend/src/services/connection_manager.py` (new)
- `app/backend/src/api/__init__.py` (modify)
- `app/backend/tests/unit_tests/test_websocket.py` (new) ← uses backend_test_file from metadata

**Relevant Context:**
- ai_docs/backend/context/api.md
- ai_docs/backend/context/testing.md

**Acceptance Criteria:**
- WebSocket endpoint available at `/ws/connect`
- Connection manager handles connect/disconnect lifecycle
- Broadcast method available for sending to all clients
- Unit tests pass with pytest

**Test Scope:** `app/backend/tests/unit_tests/test_websocket.py`

---

### Phase 2: frontend-websocket-types
**Name:** Shared WebSocket TypeScript Types
**Description:** Define TypeScript types for all WebSocket message formats
**Dependencies:** none
**Scope:**
- `app/frontend/src/types/websocket.ts` (new)
- `app/frontend/src/types/index.ts` (modify)

**Relevant Context:**
None required

**Acceptance Criteria:**
- Message types defined for connect, disconnect, broadcast events
- Types exported from index.ts
- TypeScript compilation passes

**Test Scope:** `app/frontend/src/types/`
```

## Feature
Extract the feature details from the `issue_json` variable (parse the JSON and use the title and body fields).

## Report

- Your response must be the **complete plan content** in the markdown format specified above.
- Start directly with `# Multi-Phase Feature:` — no preamble.
- Do NOT wrap the entire plan in a code block.
- Do NOT add commentary before or after the plan.
- Do NOT write any files — the caller handles file persistence.
