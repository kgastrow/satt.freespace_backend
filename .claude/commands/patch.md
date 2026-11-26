# Patch Plan

Create a **focused patch plan** to resolve a specific issue based on the `review_change_request`. Follow the `Instructions` to create a concise plan that addresses the issue with minimal, targeted changes.

## Variables

adw_id: $1
review_change_request: $2
spec_path: $3 if provided, otherwise leave it blank
agent_name: $4 if provided, otherwise use 'patch_agent'
issue_screenshots: $5 (optional) - comma-separated list of screenshot paths if provided

## CRITICAL CONSTRAINTS — DO NOT VIOLATE

- You are a **PLANNER**, not an implementer. Your ONLY job is to create a patch plan markdown file.
- **DO NOT** write any source code files (`.py`, `.ts`, `.tsx`, `.js`, `.css`, etc.)
- **DO NOT** run tests, linting, formatting, or any validation commands
- **DO NOT** install packages or run `uv add`, `npm install`, or similar
- **DO NOT** create or modify any file other than the single patch plan markdown file in `specs/patch/`
- **DO NOT** run `make`, `pytest`, `ruff`, `npm`, or any build/test commands
- The ONLY file you create is: `specs/patch/patch-adw-{adw_id}-{descriptive-name}.md`
- The ONLY tools you should use are: Read, Glob, Grep, Bash (for `git diff` only) and Write (for the plan file)

## Instructions

### 1. Create Patch Plan

- You're creating a patch plan to fix a specific review issue. Keep changes small, focused, and targeted
- Read the original specification (spec) file at `spec_path` if provided to understand the context and requirements
- IMPORTANT Use the `review_change_request` to understand exactly what needs and use it as the basis for your patch plan
- If `issue_screenshots` are provided, examine them to better understand the visual context of the issue
- Create the patch plan in `specs/patch/` directory with filename: `patch-adw-{adw_id}-{descriptive-name}.md`
  - Replace `{descriptive-name}` with a short name based on the issue (e.g., "fix-button-color", "update-validation", "correct-layout")
- IMPORTANT: This is a PATCH - keep the scope minimal. Only fix what's described in the `review_change_request` and nothing more. Address only the `review_change_request`.
- Run `git diff --stat`. If changes are available, use them to understand what's been done in the codebase and so you can understand the exact changes you should detail in the patch plan.
- Ultra think about the most efficient way to implement the solution with minimal code changes
- Base your `Plan Format: Validation` on the validation steps from `spec_path` if provided
  - If any tests fail in the validation steps, you must fix them.
  - If not provided, READ `.claude/commands/test.md: ## Test Execution Sequence` and execute the tests to understand the tests that need to be run to validate the patch.
- Replace every <placeholder> in the `Plan Format` with specific implementation details
- IMPORTANT: When you finish writing the patch plan, return exclusively the path to the patch plan file created and nothing else.

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
- If your task matches any of the conditions listed, reference those documentation files to understand the context better when creating your patch plan

- Read `.claude/commands/conditional_context.md` to check if your task requires additional specialised context
- If your task matches any of the conditions listed, include those context files in the `Plan Format: Relevant Context` section of your plan

Ignore all other files in the codebase.

## Multi-Tenancy Check (CRITICAL)

This codebase uses row-level multi-tenancy. Before creating your patch plan:

1. **Determine if the patch involves tenant-scoped data** (models with `organization_id` field)
2. **If yes, you MUST**:
   - Reference `ai_docs/backend/context/multitenancy.md` for context
   - Ensure patch maintains `organization_id` filtering in CRUD operations
3. **Tenant-scoped models include**: User, UserRole, RefreshToken, UserOTP, and any model with `organization_id` field
4. **Global models** (no tenant filtering needed): Organization, Role, Permission


## Plan Format

```md
# Patch: <concise patch title>

## Metadata
adw_id: `{adw_id}`
review_change_request: `{review_change_request}`

## Issue Summary
**Original Spec:** <spec_path>
**Issue:** <brief description of the review issue based on the `review_change_request`>
**Solution:** <brief description of the solution approach based on the `review_change_request`>

## Files to Modify
Use these files to implement the patch:

<list only the files that need changes - be specific and minimal>

## Implementation Steps
IMPORTANT: Execute every step in order, top to bottom.

<list 2-5 focused steps to implement the patch. Each step should be a concrete action.>

### Step 1: <specific action>
- <implementation detail>
- <implementation detail>

### Step 2: <specific action>
- <implementation detail>
- <implementation detail>

<continue as needed, but keep it minimal>

## Validation
Execute every command to validate the patch is complete with zero regressions.

<list 1-5 specific commands or checks to verify the patch works correctly>

## Patch Scope
**Lines of code to change:** <estimate>
**Risk level:** <low|medium|high>
**Testing required:** <brief description>
```

## Report

- CRITICAL: Your response must be ONLY the relative file path to the patch plan file you created. Nothing else.
- The path MUST start with `specs/` and end with `.md`
- Example valid response: `specs/patch/patch-adw-12345-fix-button-color.md`
- DO NOT include any explanation, summary, commentary, or markdown formatting
- DO NOT describe what you found — you should not have fixed anything
- A single line. The file path. Nothing else.