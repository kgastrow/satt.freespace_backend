# Conditional Context Guide

Read relevant `ai_docs/` files based on your task. Only read what applies—don't over-read.

**Baseline first:** Backend tasks → `ai_docs/backend/baseline_context.md` | Frontend tasks → `ai_docs/frontend/baseline_context.md`

## Backend Context

| Trigger | Context File |
|---------|--------------|
| API endpoints, routers, pagination | `backend/context/api.md` |
| Login, JWT, `get_current_user`, RBAC | `backend/context/auth.md` |
| CRUD functions, `app/crud/` | `backend/context/crud.md` |
| DB models, relationships, `app/models/` | `backend/context/models.md` |
| Pydantic schemas, `app/serialisers/` | `backend/context/serializers.md` |
| **Tenant-scoped data (`organization_id`)** | `backend/context/multitenancy.md` |
| Tests, fixtures, `tests/` | `backend/context/testing.md` |
| End-to-end feature workflow | `backend/context/common_tasks.md` |
| Redis, cache invalidation | `backend/context/caching.md` |
| ARQ tasks, `app/workers/` | `backend/context/background_jobs.md` |
| Async sessions, SQLAlchemy queries, PgBouncer | `backend/context/async_database.md` |
| Scheduled/cron jobs | `backend/context/cron_scheduler.md` |
| Email/SMS/WhatsApp, `app/services/notifications/` | `backend/context/notifications.md` |
| File uploads, S3, `app/services/files/` | `backend/context/files.md` |
| Prometheus metrics | `backend/context/metrics.md` |
| Performance testing, Locust, pytest-benchmark | `backend/context/performance_testing.md` |
| Docker, docker-compose | `backend/context/docker.md` |
| Audit logging | `backend/context/audit_logging.md` |
| Permissions, `require_permission()` | `backend/context/permissions.md` |
| User types, onboarding, `UserType`, `OnboardingStep` | `backend/context/user_types.md` |
| OAuth/SSO providers | `backend/context/sso.md` |
| Super admin impersonation | `backend/context/impersonation.md` |

## Frontend Context

| Trigger | Context File |
|---------|--------------|
| **Any user-facing text (MANDATORY)** | `frontend/context/i18n.md` |
| UI components, shadcn/ui | `frontend/context/components.md` |
| Redux, RTK Query, `src/store/` | `frontend/context/state.md` |
| Forms, React Hook Form, Zod | `frontend/context/forms.md` |
| Routes, pages, lazy loading | `frontend/context/routing.md` |
| New pages, sidebar items, navigation placement | `frontend/context/navigation.md` |
| Auth flows, JWT in browser | `frontend/context/auth.md` |
| Frontend tests, Vitest | `frontend/context/testing.md` |
| Tailwind, theming | `frontend/context/styling.md` |
| XSS prevention, token storage | `frontend/context/security.md` |
| Lighthouse CI, Core Web Vitals, bundle size | `frontend/context/performance_testing.md` |
| SSO buttons, OAuth callbacks | `frontend/context/sso.md` |
| Permission gates, `usePermission` | `frontend/context/permissions.md` |
| Impersonation UI | `frontend/context/impersonation.md` |

## Security-Critical (Always Read)

- **Tenant-scoped operations** → `multitenancy.md`
- **Auth/permission changes** → `auth.md` + `permissions.md`
- **SSO/OAuth** → `sso.md` + `auth.md`
- **Frontend text** → `i18n.md` (all strings must be translated)
- **Token/credential handling** → `security.md` + `auth.md`

---

## Auto-Detection Rules

Use these patterns to automatically determine which context to load based on file paths you're modifying:

| File Pattern | Auto-Load Context | Critical Rules |
|--------------|-------------------|----------------|
| `app/backend/src/crud/*.py` | `backend/context/crud.md`, `backend/context/multitenancy.md`, `backend/context/async_database.md` | Always filter by `organization_id` |
| `app/backend/src/api/*.py` | `backend/context/api.md`, `backend/context/auth.md` | Use auth dependencies on protected endpoints |
| `app/backend/src/models/*.py` | `backend/context/models.md`, `backend/context/multitenancy.md` | Add `organization_id` FK for tenant-scoped models |
| `app/backend/src/models/user_type*.py`, `app/backend/src/models/onboarding*.py` | `backend/context/user_types.md`, `backend/context/permissions.md` | Follow user type + onboarding patterns |
| `app/backend/src/crud/user_type*.py`, `app/backend/src/crud/onboarding*.py` | `backend/context/user_types.md`, `backend/context/crud.md` | Follow user type CRUD patterns |
| `scripts/seed_data/user_types.yaml`, `scripts/seed_data/onboarding_steps.yaml` | `backend/context/user_types.md` | Follow seed data format |
| `app/backend/src/workers/*.py` | `backend/context/background_jobs.md`, `backend/context/async_database.md` | Use ARQ task patterns, manual session commits |
| `app/backend/src/services/notifications/*.py` | `backend/context/notifications.md` | Follow notification patterns |
| `app/backend/tests/*.py` | `backend/context/testing.md` | Include tenant isolation tests |
| `app/frontend/src/**/*.tsx` | `frontend/context/i18n.md`, `frontend/context/components.md` | All strings use `t()` |
| `app/frontend/src/pages/*.tsx` | `frontend/context/routing.md`, `frontend/context/navigation.md`, `frontend/context/i18n.md` | Follow route patterns, place in correct navigation zone |
| `app/frontend/src/config/navigation.ts`, `app/frontend/src/config/adminNav.ts` | `frontend/context/navigation.md` | Correct navigation zone placement |
| `app/frontend/src/store/*.ts` | `frontend/context/state.md` | Use RTK Query patterns |
| `app/frontend/src/components/forms/*.tsx` | `frontend/context/forms.md` | Use React Hook Form + Zod |
| `app/frontend/src/__tests__/*.tsx` | `frontend/context/testing.md` | Use MSW for API mocking |

### Pattern Matching Instructions

1. **Before implementing**, list the files you plan to create or modify
2. Match each file against the patterns above
3. Read ALL matching context files before writing any code
4. When in doubt, read more context rather than less

### Critical Patterns Summary

| Pattern | Severity | Validation |
|---------|----------|------------|
| CRUD without `organization_id` filter | BLOCKER | Automated check in review |
| Frontend strings without `t()` | BLOCKER | Automated check in review |
| Hard deletes instead of soft deletes | BLOCKER | Automated check in review |
| Sync I/O in async context | TECH_DEBT | Manual review |
| Missing type hints | TECH_DEBT | Manual review |

---

## Rescue Workflow Context

When working on Vibe Code Rescue tasks, load these context files based on the task type:

| Rescue Task Type | Context Files | Critical Rules |
|------------------|---------------|----------------|
| `/rescue_execute_model` | `backend/context/models.md`, `backend/context/multitenancy.md` | Add `organization_id` FK, use soft deletes |
| `/rescue_execute_crud` | `backend/context/crud.md`, `backend/context/multitenancy.md` | Always filter by `organization_id` |
| `/rescue_execute_api` | `backend/context/api.md`, `backend/context/auth.md` | Use auth dependencies, proper error codes |
| `/rescue_execute_component` | `frontend/context/components.md`, `frontend/context/i18n.md` | All strings use `t()`, use Tailwind |
| `/rescue_execute_wire` | `frontend/context/state.md`, `backend/context/api.md` | Use RTK Query patterns |
| `/rescue_execute_test` | `backend/context/testing.md`, `frontend/context/testing.md` | Include tenant isolation tests |
| `/rescue_catalog_ui` | `frontend/context/components.md` | For template pattern reference |
| `/rescue_classify_backend` | `backend/context/models.md`, `backend/context/crud.md`, `backend/context/api.md` | For template pattern reference |
| `/rescue_plan_ui` | `frontend/context/components.md`, `frontend/context/i18n.md`, `frontend/context/styling.md` | For migration planning |

### Rescue-Specific Critical Patterns

| Pattern | Severity | Description |
|---------|----------|-------------|
| Component without i18n | BLOCKER | All user-facing strings must use `t()` |
| Model without `organization_id` | BLOCKER | All tenant-scoped models need FK |
| CRUD without org filter | BLOCKER | All queries must filter by tenant |
| Hard delete in CRUD | BLOCKER | Use soft deletes (`deleted_time`) |
| Non-Tailwind styling | WARNING | Convert to Tailwind CSS |
| Redux without RTK Query | WARNING | Prefer RTK Query for server state |
