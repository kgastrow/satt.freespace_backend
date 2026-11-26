# Feature Planning

Create a new plan to implement the `Feature` using the exact specified markdown `Plan Format`. Follow the `Instructions` to create the plan use the `Relevant Files` to focus on the right files.

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

## Instructions

- You're writing a plan to implement a net new feature based on the `Feature` that will add value to the application.
- The `Feature` describes the feature that will be implemented but remember we're not implementing a new feature, we're creating the plan that will be used to implement the feature based on the `Plan Format` below.
- The plan filename will be: `issue-{issue_number}-adw-{adw_id}-sdlc_planner-{descriptive-name}.md` — the caller writes this to disk.
  - Replace `{descriptive-name}` with a short, descriptive name based on the feature (e.g., "add-auth-system", "implement-search", "create-dashboard")
- Use the `Plan Format` below to create the plan. 
- Research the codebase to understand existing patterns, architecture, and conventions before planning the feature.
- IMPORTANT: Replace every <placeholder> in the `Plan Format` with the requested value. Add as much detail as needed to implement the feature successfully.
- Use your reasoning model: THINK HARD about the feature requirements, design, and implementation approach.
- Follow existing patterns and conventions in the codebase. Don't reinvent the wheel.
- Design for extensibility and maintainability.
- If you need a new library, use `uv add` and be sure to report it in the `Notes` section of the `Plan Format`.
- Don't use decorators. Keep it simple.
- IMPORTANT: If the feature includes UI components or user interactions:
  - Add a task in the `Step by Step Tasks` section to create a separate E2E test file in `.claude/commands/e2e/test_<descriptive_name>.md` based on examples in that directory
  - Add E2E test validation to your Validation Commands section
  - IMPORTANT: When you fill out the `Plan Format: Relevant Files` section, add an instruction to read `.claude/commands/test_e2e.md`, and `.claude/commands/e2e/test_login_success.md` to understand how to create an E2E test file. List your new E2E test file to the `Plan Format: New Files` section.
  - To be clear, we're not creating a new E2E test file, we're creating a task to create a new E2E test file in the `Plan Format` below
- Respect requested files in the `Relevant Files` section.
- Start your research by reading the `README.md` file.

## Relevant Files

Focus on the following files:
- `README.md` - Contains the project overview and instructions.
- `app/backend/src/` - Contains the backend source code (models, crud, api, services).
- `app/backend/tests/` - Contains backend tests.
- `app/backend/alembic/` - Contains database migrations.
- `app/frontend/src/` - Contains the frontend source code.
- `scripts/**` - Contains the scripts to start and stop the server + client.
- `adws/**` - Contains the AI Developer Workflow (ADW) scripts.

- Read `.claude/commands/conditional_docs.md` to check if your task requires additional documentation
- If your task matches any of the conditions listed, include those documentation files in the `Plan Format: Relevant Files` section of your plan

- Read `.claude/commands/conditional_context.md` to check if your task requires additional specialised context
- If your task matches any of the conditions listed, include those context files in the `Plan Format: Relevant Context` section of your plan

Ignore all other files in the codebase.

## Multi-Tenancy Check (CRITICAL)

This codebase uses row-level multi-tenancy. Before creating your plan:

1. **Determine if the feature involves tenant-scoped data** (models with `organization_id` field)
2. **If yes, you MUST**:
   - Include `ai_docs/backend/context/multitenancy.md` in Relevant Context
   - Add isolation tests to your Testing Strategy
   - Ensure all CRUD operations filter by `organization_id`
   - Pass `organization_id` from `CurrentUser` dependency to CRUD functions
3. **Tenant-scoped models include**: User, UserRole, RefreshToken, UserOTP, and any model with `organization_id` field
4. **Global models** (no tenant filtering needed): Organization, Role, Permission
5. **For new models**: Decide if tenant-scoped or global. If tenant-scoped, add `organization_id` FK.

## Database Migration Guidance

If the feature adds or modifies database models:
1. Create migration: `cd app/backend && make migrate-new` (enter description when prompted)
2. Review generated migration in `app/backend/alembic/versions/`
3. Apply migration: `cd app/backend && make migrate`
4. Include migration steps in your plan's Step by Step Tasks

## Plan Format

```md
# Feature: <feature name>

## Metadata
issue_number: `{issue_number}`
adw_id: `{adw_id}`
issue_json: `{issue_json}`

## Feature Description
<describe the feature in detail, including its purpose and value to users>

## User Story
As a <type of user>
I want to <action/goal>
So that <benefit/value>

## Problem Statement
<clearly define the specific problem or opportunity this feature addresses>

## Solution Statement
<describe the proposed solution approach and how it solves the problem>

## Navigation Placement (REQUIRED for UI features)
**Target Audience:** <extract from the issue body — one of: `end_user`, `admin`, `platform_admin`, `backend_only`>
**Navigation Zone:** <based on target audience, specify exactly where pages go>

Rules — read `ai_docs/frontend/context/navigation.md` before filling this out:
- `end_user` → **Main Sidebar** — add to `config/navigation.ts` `mainNavigation`, pages in `pages/`, routes under `DashboardLayout`
- `admin` → **Admin Hub** (`/admin/*`) — add to `config/adminNav.ts`, pages in `pages/admin/`, routes via `generateRoutes(adminRoutes)`
- `platform_admin` → **Platform Admin Hub** (`/platform-admin/*`) — add to `config/platformAdminNav.ts`, pages in `pages/platform-admin/`
- `backend_only` → No UI pages, skip this section

**Common mistake:** Do NOT put end-user workflow pages in the admin hub just because they require permissions. If primary users open this page daily as part of their core workflow, it belongs in the main sidebar.

## Relevant Files
Use these files to implement the feature:

<find and list the files that are relevant to the feature describe why they are relevant in bullet points. If there are new files that need to be created to implement the feature, list them in an h3 'New Files' section.>

## Relevant Context (REQUIRED)
**This section is MANDATORY.** Implementers WILL read these files before writing code.

Use `.claude/commands/conditional_context.md` to determine which `ai_docs/` files apply to this feature.

| Context File | Reason for Inclusion |
|--------------|---------------------|
| <ai_docs path> | <why this context is needed> |

**Common triggers:**
- CRUD operations → `ai_docs/backend/context/multitenancy.md`
- API endpoints → `ai_docs/backend/context/api.md`
- Frontend UI → `ai_docs/frontend/context/i18n.md`
- Forms → `ai_docs/frontend/context/forms.md`
- New pages or nav items → `ai_docs/frontend/context/navigation.md` **(MANDATORY when adding pages)**

## Implementation Plan
### Phase 1: Foundation
<describe the foundational work needed before implementing the main feature>

### Phase 2: Core Implementation
<describe the main implementation work for the feature>

### Phase 3: Integration
<describe how the feature will integrate with existing functionality>

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

<list step by step tasks as h3 headers plus bullet points. use as many h3 headers as needed to implement the feature. Order matters, start with the foundational shared changes required then move on to the specific implementation. Include creating tests throughout the implementation process.>

<If the feature affects UI, include a task to create a E2E test file (like `.claude/commands/e2e/test_login_success.md` and `.claude/commands/e2e/test_create_user.md`) as one of your early tasks. That e2e test should validate the feature works as expected, be specific with the steps to demonstrate the new functionality. We want the minimal set of steps to validate the feature works as expected and screen shots to prove it if possible.>

<Your last step should be running the `Validation Commands` to validate the feature works correctly with zero regressions.>

## Testing Strategy
### Unit Tests
<describe unit tests needed for the feature>

### Edge Cases
<list edge cases that need to be tested>

## Acceptance Criteria
<list specific, measurable criteria that must be met for the feature to be considered complete>

## Validation Commands
Execute every command to validate the feature works correctly with zero regressions.

<list commands you'll use to validate with 100% confidence the feature is implemented correctly with zero regressions. every command must execute without errors so be specific about what you want to run to validate the feature works as expected. Include commands to test the feature end-to-end.>

<If you created an E2E test, include the following validation step: `Read .claude/commands/test_e2e.md`, then read and execute your new E2E `.claude/commands/e2e/test_<descriptive_name>.md` test file to validate this functionality works.>

### Backend Validation
- `cd app/backend && uv run python -m py_compile main.py src/**/*.py` - Validate Python syntax
- `cd app/backend && uv run ruff check .` - Run linting checks
- `cd app/backend && uv run pytest tests/ -v --tb=short` - Run all backend tests

### Frontend Validation
- `cd app/frontend && npx tsc --noEmit` - Validate TypeScript types
- `cd app/frontend && npm run build` - Validate production build

## Notes
<optionally list any additional notes, future considerations, or context that are relevant to the feature that will be helpful to the developer>
```

## Feature
Extract the feature details from the `issue_json` variable (parse the JSON and use the title and body fields).

## Report

- Your response must be the **complete plan content** in the markdown format specified above.
- Start directly with `# Feature:` — no preamble.
- Do NOT wrap the entire plan in a code block.
- Do NOT add commentary before or after the plan.
- Do NOT write any files — the caller handles file persistence.