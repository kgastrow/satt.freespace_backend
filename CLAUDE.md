# AYZER Webapp Template

## Context
ayzer-webapp-template multi-tenant backend with React frontend. Row-level multi-tenancy with PostgreSQL. All tenant-scoped data requires `organization_id` filtering.

## Tooling

- Backend:
  - Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2
  - PostgreSQL + PgBouncer, Redis, ARQ (background jobs)
  - pytest, ruff, black, mypy
- Frontend:
  - React 19, TypeScript, Vite, Tailwind CSS
  - Redux Toolkit, React Hook Form, Zod, shadcn/ui
  - Vitest, ESLint

## Key Commands

Backend (from `app/backend/`):
- `make test-fast` - Run tests in parallel
- `make lint` - Run ruff and mypy
- `make format` - Format with black and ruff
- `make migrate` - Run database migrations
- `make migrate-new msg="description"` - Autogenerate a new migration from model changes (e.g., `make migrate-new msg="add_user_roles_table"`)
- `make dev` - Start development server

Frontend (from `app/frontend/`):
- `npm run test` - Run tests
- `npm run lint` - Run ESLint
- `npm run build` - Production build (regenerates types from backend, requires backend running)
- `npm run build:only` - Production build without type regeneration
- `npm run dev` - Start dev server
- `npm run generate:types` - Generate TypeScript types from OpenAPI schema (requires backend running)

## Project Structure
- `app/backend/` - FastAPI backend
- `app/frontend/` - React frontend
- `ai_docs/` - Agent context documentation
- `adws/` - Agentic development workflows

## Development Guidelines
1. Always filter tenant-scoped queries by `organization_id`
2. Use soft deletes (`deleted_time`) - never hard delete
3. Use async/await for all I/O operations
4. Use Pydantic models for all request/response validation
5. Write tests for new features (include tenant isolation tests)
6. Once dependencies are installed, python venv is at app/backend/.venv
7. Never manually write migrations - always autogenerate them with `make migrate-new` after completing model changes in source code
8. **i18n is mandatory** - All frontend user-facing text must use i18n. Add translations to ALL locale files (en, etc)
9. **API Router Registration** - New API routers must be registered in `app/backend/src/api/v1/__init__.py` (not `src/api/__init__.py`). Import the module and call `v1_router.include_router(module.router)`
10. **NEVER hard delete** - Always use soft deletes by setting `deleted_time`
11. **Always include tenant isolation tests** for any CRUD operation
12. **All exception handling** must use `create_http_exception` with `detail_code`
13. **API router order matters** - More specific routes before generic ones
14. **Reference data goes in the SHARED seeder** - New code-owned reference data (a permission, a role, a role->permission grant, a rate limit, a user type or onboarding step, a notification template or category, a cron definition, a system config key) MUST be added to `app/backend/src/services/organization_seeding.py` (a `seed_reference_*` function or the YAML file it reads, registered in `REFERENCE_SEED_STEPS`) - never to `scripts/seed_first_tenant.py` alone. `seed_first_tenant.py` is the bootstrap (fresh DB: reference data + identities + demo content) and `scripts/seed_maintenance.py` is the additive, re-runnable maintenance seeder for live deployments; both call the same shared functions. Reference data added only to the bootstrap script can never reach an already-deployed environment. `seed_first_tenant.py` keeps only deployment identity (super admin, org settings) and demo content.
