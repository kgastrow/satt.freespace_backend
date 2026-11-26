# Implement the following plan
Follow the `Instructions` to implement the `Plan` then `Report` the completed work.

## Instructions

### 1. Load Context (REQUIRED)
- Read `.claude/commands/conditional_context.md` - this is your lookup table for determining which `ai_docs/` files to read
- Based on your task and the files you'll modify, load the applicable context files BEFORE implementing
- If the plan has a `Relevant Context` section, also read those files
- **Context Assertion**: After loading, confirm which context files you read

### 2. Multi-Tenancy Awareness (CRITICAL)
This codebase uses row-level multi-tenancy. When implementing:
- **Tenant-scoped models** have `organization_id` field - ALL CRUD must filter by it
- Pass `organization_id` from `CurrentUser` dependency (never from request body)
- Reference `ai_docs/backend/context/multitenancy.md` if working with tenant-scoped data

### 3. Implementation
- Read the plan thoroughly and understand the requirements
- Follow existing patterns in the codebase
- Implement step by step as outlined in the plan (EXCEPT tests - see below)
- Run validation commands after each significant change
- Use async/await for all I/O operations
- Use soft deletes (`deleted_time`) - never hard delete

### 3a. Design Fidelity (REQUIRED when the plan has design references)

If the plan, issue body, or linked spec contains **"Design References"**, **"Design Screen Specs"**, or any reference to a `design_handoff*` directory:

1. **Read brand context first.** Before writing any component, read:
   - `ai_docs/frontend/baseline_context.md` — the "Brand Design System" section near the top names the palette, type system, and shape language. These are non-negotiable.
   - `ai_docs/frontend/context/design_system.md` — full token reference, type scale, shape-language utilities, and screen catalog.

2. **Read every linked prototype file.** The plan lists prototype JSX/HTML files under `specs/design_handoff*/src/`. Open each one and read the relevant component(s) before deciding component structure. They show the intended DOM tree, class structure, and interaction model. **Do not copy the code verbatim** — re-implement using the project's component library (shadcn/ui), router, state management, and i18n.

3. **Match the screen spec verbatim.** The plan's "Design Screen Specs" blocks are copied directly from the handoff README. Reproduce them as specified:
   - Exact color tokens (use the CSS variables — never hardcode hex values)
   - Exact typography (use the `display-*`, `eyebrow`, `body-*`, `mono-*` utilities as defined in `design_system.md`)
   - Exact spacing, radii, and shadows
   - Brand shape language: slashed/hex-clipped CTAs, parallelogram chips, sharp diagonals — these are signature elements, not optional polish

4. **Token seeding (first UI module only).** Check whether `app/frontend/src/index.css` already contains a `Brand Design System` block:
   - **If yes:** the `/assimilate_design` phase already seeded tokens directly into `index.css`. Skip this step and move on.
   - **If no, AND `ai_docs/frontend/context/design_system_seed.md` exists:** this module is the first UI module. Its implementation MUST start by pasting the CSS-variable block, font imports, and shape-language utility classes from `design_system_seed.md` into `index.css`. After seeding, delete `design_system_seed.md`.
   - **If no, AND no seed file exists:** investigate before continuing — `/assimilate_design` should have written one or the other. Don't invent tokens; surface the inconsistency.

5. **Reserved tokens.** Any token marked "reserved" in `design_system.md` (e.g. accent colors reserved for rewards moments) must not be used as a general accent. Read the reservations carefully.

If the plan has **no design references**, skip this section — implement using whatever component library and theming the project already has.

### 3b. Frontend Standards (REQUIRED for any UI work)

- **i18n (mandatory)**: ALL user-facing strings must use the i18n `t()` function with translation keys. NEVER hardcode display text. Add every new key to ALL locale files under `app/frontend/src/locales/` (e.g. `en`, and any other locales present) — never leave a locale missing a key.
- **Responsive (mandatory)**: ALL UI must render correctly on BOTH mobile (390x844) and desktop (1440x900). No desktop-only layouts — use responsive Tailwind utilities so the layout adapts to small and large viewports.

### 4. Database Migrations
If the plan involves model changes:
- Create migration: `cd app/backend && make migrate-new`
- Review migration in `app/backend/alembic/versions/`
- Apply migration: `cd app/backend && make migrate`

### 5. Test Writing - DO NOT WRITE TESTS
**IMPORTANT**: Do NOT create test files during implementation.
- Skip any "Testing" sections in the plan's Step by Step Tasks
- Skip creating files in `tests/` directories
- The Test phase will handle all test creation via `/write_tests`

This separation ensures:
- Clear ownership: Test phase owns all test writing
- No duplicate work between Build and Test phases
- Tests are always created from the spec's Testing Strategy

## Plan
$ARGUMENTS

## Report
- Summarize the work you've just done in a concise bullet point list.
- Confirm: "Tests deferred to Test phase as per workflow"
- Report the files and total lines changed with `git diff --stat`