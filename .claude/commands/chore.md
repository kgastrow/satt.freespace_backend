# Chore Planning

Create a new plan to resolve the `Chore` using the exact specified markdown `Plan Format`. Follow the `Instructions` to create the plan use the `Relevant Files` to focus on the right files. Follow the `Report` section to properly report the results of your work.

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

- You're writing a plan to resolve a chore based on the `Chore` that will add value to the application.
- The `Chore` describes the chore that will be resolved but remember we're not resolving the chore, we're creating the plan that will be used to resolve the chore based on the `Plan Format` below.
- You're writing a plan to resolve a chore, it should be simple but we need to be thorough and precise so we don't miss anything or waste time with any second round of changes.
- The plan filename will be: `issue-{issue_number}-adw-{adw_id}-sdlc_planner-{descriptive-name}.md` — the caller writes this to disk.
  - Replace `{descriptive-name}` with a short, descriptive name based on the chore (e.g., "update-readme", "fix-tests", "refactor-auth")
- Use the plan format below to create the plan. 
- Research the codebase and put together a plan to accomplish the chore.
- IMPORTANT: Replace every <placeholder> in the `Plan Format` with the requested value. Add as much detail as needed to accomplish the chore.
- Use your reasoning model: THINK HARD about the plan and the steps to accomplish the chore.
- Respect requested files in the `Relevant Files` section.
- Start your research by reading the `README.md` file.
- `adws/*.py` contain astral uv single file python scripts. So if you want to run them use `uv run <script_name>`.
- When you finish creating the plan for the chore, follow the `Report` section to properly report the results of your work.

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

1. **Determine if the chore involves tenant-scoped data** (models with `organization_id` field)
2. **If yes, you MUST**:
   - Include `ai_docs/backend/context/multitenancy.md` in Relevant Context
   - Ensure any refactoring maintains `organization_id` filtering
   - Add isolation tests if modifying CRUD operations
3. **Tenant-scoped models include**: User, UserRole, RefreshToken, UserOTP, and any model with `organization_id` field
4. **Global models** (no tenant filtering needed): Organization, Role, Permission

## Plan Format

```md
# Chore: <chore name>

## Metadata
issue_number: `{issue_number}`
adw_id: `{adw_id}`
issue_json: `{issue_json}`

## Chore Description
<describe the chore in detail>

## Relevant Files
Use these files to resolve the chore:

<find and list the files that are relevant to the chore describe why they are relevant in bullet points. If there are new files that need to be created to accomplish the chore, list them in an h3 'New Files' section.>

## Relevant Context (REQUIRED)
**This section is MANDATORY.** Implementers WILL read these files before writing code.

Use `.claude/commands/conditional_context.md` to determine which `ai_docs/` files apply to this chore.

| Context File | Reason for Inclusion |
|--------------|---------------------|
| <ai_docs path> | <why this context is needed> |

**Common triggers:**
- CRUD operations → `ai_docs/backend/context/multitenancy.md`
- API endpoints → `ai_docs/backend/context/api.md`
- Frontend UI → `ai_docs/frontend/context/i18n.md`

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

<list step by step tasks as h3 headers plus bullet points. use as many h3 headers as needed to accomplish the chore. Order matters, start with the foundational shared changes required to fix the chore then move on to the specific changes required to fix the chore. Your last step should be running the `Validation Commands` to validate the chore is complete with zero regressions.>

## Validation Commands
Execute every command to validate the chore is complete with zero regressions.

<list commands you'll use to validate with 100% confidence the chore is complete with zero regressions. every command must execute without errors so be specific about what you want to run to validate the chore is complete with zero regressions. Don't validate with curl commands.>

### Backend Validation (if backend changes)
- `cd app/backend && uv run python -m py_compile main.py app/**/*.py` - Validate Python syntax
- `cd app/backend && uv run ruff check .` - Run linting checks
- `cd app/backend && uv run pytest tests/ -v --tb=short` - Run all backend tests

### Frontend Validation (if frontend changes)
- `cd app/frontend && npx tsc --noEmit` - Validate TypeScript types
- `cd app/frontend && npm run build` - Validate production build

## Notes
<optionally list any additional notes or context that are relevant to the chore that will be helpful to the developer>
```

## Chore
Extract the chore details from the `issue_json` variable (parse the JSON and use the title and body fields).

## Report

- Your response must be the **complete plan content** in the markdown format specified above.
- Start directly with `# Chore:` — no preamble.
- Do NOT wrap the entire plan in a code block.
- Do NOT add commentary before or after the plan.
- Do NOT write any files — the caller handles file persistence.