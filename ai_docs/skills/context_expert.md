# Context Expert Skill

Context Documentation Expert responsible for maintaining AI context documentation accuracy for AYZER Webapp.

## Responsibilities

1. Audit context files against actual implementation
2. Ensure baseline_context.md is concise and references specialized files correctly
3. Identify gaps, inconsistencies, and improvements

## Context File Inventory

### Root & Backend

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Master instructions, quick reference |
| `ai_docs/backend/baseline_context.md` | Architecture overview, entry point |
| `ai_docs/backend/context/api.md` | FastAPI router patterns |
| `ai_docs/backend/context/auth.md` | Authentication/authorization |
| `ai_docs/backend/context/crud.md` | Async CRUD patterns |
| `ai_docs/backend/context/models.md` | SQLAlchemy model conventions |
| `ai_docs/backend/context/serializers.md` | Pydantic v2 schemas |
| `ai_docs/backend/context/multitenancy.md` | Multi-tenancy (CRITICAL) |
| `ai_docs/backend/context/testing.md` | Async pytest patterns |
| `ai_docs/backend/context/caching.md` | Redis caching |
| `ai_docs/backend/context/background_jobs.md` | ARQ worker patterns |

### Frontend

| File | Purpose |
|------|---------|
| `ai_docs/frontend/baseline_context.md` | Frontend architecture |
| `ai_docs/frontend/context/components.md` | shadcn/ui patterns |
| `ai_docs/frontend/context/state.md` | Redux/RTK Query |
| `ai_docs/frontend/context/forms.md` | React Hook Form/Zod |
| `ai_docs/frontend/context/routing.md` | React Router |
| `ai_docs/frontend/context/testing.md` | Vitest patterns |

## Audit Workflow

**Use subagents (Task tool with `subagent_type: Explore`) for each specialized context file.** This ensures focused analysis and parallel processing.

### Subagent Prompt Template

```
Review [context file] against source code in [directories]. Report:
1. Documented patterns not matching implementation
2. Implementation patterns missing from docs
3. Outdated examples
4. Missing gotchas/edge cases
5. Specific update recommendations
```

### Context File → Source Directory Mapping

| Context File | Source Directories |
|--------------|-------------------|
| `backend/context/crud.md` | `app/backend/src/crud/` |
| `backend/context/models.md` | `app/backend/src/models/` |
| `backend/context/api.md` | `app/backend/src/api/` |
| `backend/context/serializers.md` | `app/backend/src/serialisers/` |
| `backend/context/auth.md` | `app/backend/src/core/auth/`, `app/backend/src/api/` |
| `backend/context/multitenancy.md` | `app/backend/src/crud/`, `app/backend/tests/` |
| `backend/context/testing.md` | `app/backend/tests/` |
| `backend/context/caching.md` | `app/backend/src/services/cache/` |
| `backend/context/background_jobs.md` | `app/backend/src/workers/` |
| `frontend/context/components.md` | `app/frontend/src/components/ui/` |
| `frontend/context/state.md` | `app/frontend/src/features/`, `app/frontend/src/store/` |
| `frontend/context/routing.md` | `app/frontend/src/pages/`, `app/frontend/src/layouts/` |

### Audit Phases

1. **Orientation**: Read CLAUDE.md and baseline_context.md, identify files to audit
2. **Specialized Reviews**: Spawn subagents for each context file (batches of 3-5)
3. **Gap Discovery**: Find undocumented patterns in source code
4. **Cross-Reference**: Verify quick references, check for contradictions
5. **Report**: Consolidate findings into structured report

## Quality Standards

| Aspect | Requirement |
|--------|-------------|
| Structure | Clear headers, code examples that compile, consistent formatting |
| Content | Accurate to codebase, includes "why" not just "how", documents gotchas |
| Maintainability | No hardcoded stale values, relative paths, version-specific content marked |

## Common Issues

- **Multi-tenancy**: ALL examples must include `organization_id` filtering
- **API patterns**: Verify dependency injection and route prefixes match implementation
- **CRUD patterns**: Ensure async patterns and soft delete filters documented
- **Testing**: Verify fixture patterns match actual test utilities

## When to Update vs Create

| Action | Trigger |
|--------|---------|
| Update existing file | Adding missing info, correcting examples, adding gotchas |
| Create new file | New architectural layer, topic deserves focused coverage |
| Update CLAUDE.md | New specialized files, workflow changes, security requirements |
| Update baseline_context.md | Core architecture changes, new technology |

## Report Template

```markdown
# Context Documentation Audit Report

## Summary
[Brief overview]

## Findings
### Critical Issues
[Could cause incorrect/insecure code]

### Documentation Gaps
[Missing documentation for existing patterns]

### Inconsistencies
[Contradictions between files or with codebase]

## Action Items
1. [Specific update]
2. [New file to create]
```

## Key Principles

1. **Accuracy over completeness** - Less correct documentation beats more incorrect
2. **Security paramount** - Multi-tenancy isolation must be thorough
3. **Examples must work** - All code syntactically correct
4. **Document the "why"** - Help agents understand reasoning
5. **Keep it DRY** - Reference other files, don't duplicate

## Related

For structured audit process: `ai_docs/workflows/context_audit.md`
- Covers all code with discovery commands
- Quick (15 min) and full (1-2 hr) options
- Includes self-maintenance phase
