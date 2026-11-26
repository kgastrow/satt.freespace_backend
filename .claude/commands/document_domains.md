# Document Domains

Follow the `Instructions` below to **generate or update domain context documentation** in `ai_docs/domain/` using a parallelized subagent approach. Domain docs are *vertical* business + full-stack maps of a functional area (e.g. "Customer Management", "Inspections") — they complement the *horizontal* technical context docs in `ai_docs/backend/context/` and `ai_docs/frontend/context/`.

This command fills the gap left after greenfield builds and other ADWs: downstream domain knowledge (what a domain is, its entities, business rules, API/UI surface, and workflows) is otherwise never captured for future ADWs to load.

**IMPORTANT:**
1. Domain docs describe *business domains*, NOT infrastructure. Do NOT create domain docs for cross-cutting technical concerns already covered by the technical context docs (auth, permissions, multitenancy, files, notifications, audit logging, metrics, caching, cron/scheduler, sso, two-factor, impersonation, i18n). Those are horizontal.
2. Create-or-update: if a domain doc already exists, read it first and refresh stale parts while preserving still-accurate prose. Do NOT blindly overwrite.
3. After generating docs, you MUST register them (index + conditional context) so future ADWs load them.

## Variables

target: $1 if provided, otherwise empty

`target` selects the mode:
- **empty** OR **a path ending in `decomposition.json`** → FAN-OUT mode: document ALL domains.
- **`--changed`** → SINGLE mode: document only the domain(s) touched by the current branch's diff.
- **anything else** → SINGLE mode: treat `target` as a domain id or name and document just that one.

## Instructions

### Phase 0: Orient

- Read `ai_docs/backend/baseline_context.md` and `ai_docs/frontend/baseline_context.md` to understand the stack and conventions.
- List existing domain docs: `ls ai_docs/domain/*.md` (the directory may not exist yet — that is fine).
- Read `.claude/commands/conditional_context.md` so you know the registration format and which concerns are already covered by horizontal technical docs (to exclude from domains).

### Phase 1: Enumerate Target Domains

Determine the list of domains to document based on `target`:

#### Mode A — Single explicit domain (`target` is a domain id/name)
- The list is just that one domain. If a matching `ai_docs/domain/<id>.md` exists, this is an update; otherwise a create.
- Resolve a stable `id` (kebab-case, e.g. `customer-management`) and a display `name`.

#### Mode B — `--changed` (incremental, used by other ADWs)
- Run `git diff origin/main --name-only` to get changed files.
- Map changed files to domain(s):
  - Match against existing `ai_docs/domain/*.md` docs (each doc references its code paths — a changed file under those paths means that domain is affected).
  - Match changed backend models/crud/api routers and frontend pages/feature folders to a domain by name.
- The list is the affected domain(s) only (usually 1–3). If a change introduces a brand-new domain, include it as a create. If no business-domain files changed (only infra/tests/config), report "no domain docs needed" and stop.

#### Mode C — Fan-out (empty target, or a decomposition.json path)
1. **Authoritative source — greenfield decomposition:**
   - If `target` is a path ending in `decomposition.json`, use it. Otherwise locate the newest `specs/greenfields/*/decomposition.json` (fall back to any `agents/*/greenfield_state.json` and read its `modules` map).
   - Parse `modules[]`. For each module capture: `id`, `name`, `description`, `target_audience`, `user_stories`, `acceptance_criteria`, `dependencies`, `spec_references`. Treat each module as a domain candidate.
2. **Supplement — codebase scan** (also the only source if no greenfield state exists):
   - Group `app/backend/src/models/*.py`, `app/backend/src/api/v1/*.py` routers, and `app/backend/src/crud/*.py` by feature; group `app/frontend/src/pages/*` and frontend feature folders. Each cohesive feature area not already in the module list is an additional domain candidate.
3. **Filter & dedupe:**
   - Drop candidates that are horizontal infrastructure (see the exclusion list in the IMPORTANT note above).
   - Deduplicate by `id`. Merge greenfield metadata into scan-derived candidates where they refer to the same area.

Print the final enumerated domain list before proceeding.

### Phase 2: Spawn Subagents in Parallel

For EACH enumerated domain, spawn a subagent using the Task tool with `subagent_type: "general-purpose"`.

**CRITICAL: Spawn ALL subagents in a SINGLE message so they run in parallel** (skip this only when there is exactly one domain).

Give each subagent this prompt template (fill in the variables):

```
You are generating/updating the domain context document for the "{name}" domain (id: {id}) in this codebase.

## Known domain metadata (from greenfield decomposition, may be empty)
- Description: {description}
- Audience: {target_audience}
- User stories: {user_stories}
- Acceptance criteria: {acceptance_criteria}
- Dependencies: {dependencies}
- Spec references: {spec_references}

## Your task

1. If `ai_docs/domain/{id}.md` already exists, READ it first. You are updating it: keep still-accurate prose, refresh anything stale, fill gaps. Otherwise you are creating it.
2. Investigate the actual implementation of this domain across the stack:
   - Backend: models (`app/backend/src/models/`), CRUD (`app/backend/src/crud/`), API routers (`app/backend/src/api/v1/`), serializers/schemas (`app/backend/src/serialisers/`), migrations, workers/services if relevant.
   - Frontend: pages (`app/frontend/src/pages/`), components, routes, Redux/RTK state (`app/frontend/src/store/`), navigation placement.
   - Tests: backend tests and any e2e covering this domain.
   Use Glob/Grep/Read. Ground EVERY claim in real code — cite concrete file paths. Do not invent behaviour.
3. Note tenant-scoping: which entities carry `organization_id`, and confirm CRUD filters by it (flag if not).
4. Write `ai_docs/domain/{id}.md` using EXACTLY this template (omit a section only if genuinely not applicable, and say so):

# Domain: {name}

**Domain ID:** {id}
**Audience:** end_user | admin | platform_admin | backend_only
**Status:** generated {today} by /document_domains

## Purpose
What this domain does and who uses it.

## Entities & Data Model
Models, key fields, relationships, tenant-scoping. Reference `app/backend/src/models/...`.

## Business Rules & Invariants
Domain rules, validation, state transitions, constraints that must always hold.

## API Surface
| Method | Path | Permission | Purpose |
Reference routers in `app/backend/src/api/v1/...` and crud in `app/backend/src/crud/...`.

## UI Surface
Pages, routes, key components, navigation placement. Reference `app/frontend/src/...`.

## Key Workflows
Step-by-step primary user/business flows end-to-end (UI -> API -> data).

## Dependencies
Other domains / shared services this relies on, and who relies on it. Link related `domain/*.md`.

## Tests
Where domain behaviour is covered (backend tests, e2e).

5. Keep it concise and high-signal — match the tone of existing `ai_docs/backend/context/*.md` docs (tables over prose, cite paths, no filler).

## Return (your final message, raw — no preamble)
Return a single JSON object:
{
  "id": "{id}",
  "name": "{name}",
  "doc_path": "ai_docs/domain/{id}.md",
  "action": "created" | "updated",
  "audience": "<resolved audience>",
  "trigger_keywords": ["<3-6 short keywords/phrases a future ADW task would mention when working in this domain — entity names, route nouns, page names>"],
  "summary": "<one-line description of the domain for the index>"
}
```

After spawning, wait for ALL subagents to complete. Verify a `ai_docs/domain/<id>.md` file exists for every domain and collect each subagent's returned JSON.

### Phase 3: Consolidate & Register

Using the collected subagent results:

1. **Domain index** — create/update `ai_docs/domain/README.md`:

```md
# Domain Context Documentation

Vertical, per-domain context maps (business purpose, entities, business rules, API & UI surface, workflows). These complement the horizontal technical docs in `ai_docs/backend/context/` and `ai_docs/frontend/context/`. Generated and kept current by `/document_domains`.

| Domain | Doc | Audience | Purpose |
|--------|-----|----------|---------|
| <name> | `<id>.md` | <audience> | <summary> |
```
Update existing rows in place; append new domains. Keep rows sorted by name. Do not remove rows for domains you did not touch this run.

2. **Conditional context registration** — edit `.claude/commands/conditional_context.md`:
   - Ensure a `## Domain Context` section exists (add it after the `## Frontend Context` section if missing) with this intro line and table header:
     ```md
     ## Domain Context

     Per-domain business + full-stack maps in `ai_docs/domain/`. Load the matching doc when working within that business domain.

     | Trigger | Context File |
     |---------|--------------|
     ```
   - For each documented domain, add/maintain a row: `| <trigger_keywords joined by ", "> | `domain/<id>.md` |`.
   - **Idempotent:** if a row for `domain/<id>.md` already exists, update its triggers in place; do not duplicate rows.

### Phase 4: Report

Report concisely:
- The mode used and domains enumerated.
- For each domain: created vs updated, and the doc path.
- The index and `conditional_context.md` changes made.

If invoked in `--changed` mode and no business-domain files changed, report exactly: `No domain docs needed` and make no edits.
