# OpenAPI TypeScript Client Generation

**ADW ID:** 20260110130509-5c10d056
**Date:** 2026-01-10

## Overview

Automatic TypeScript type generation from FastAPI backend's OpenAPI schema for compile-time type safety in API interactions.

## Files Modified

- `scripts/generate-api-types.sh`: Downloads OpenAPI schema (with basic auth) and generates TypeScript types
- `app/frontend/package.json`: Added `openapi-typescript` v7.4.4 and `generate:types` script
- `app/frontend/.openapi-generator-ignore`: Preserves patterns during generation
- `.gitignore`: Excludes `api-generated.ts` and `openapi.json`
- `CLAUDE.md`: Added `npm run generate:types` to frontend commands

## Key Features

- **Smart Backend URL Detection**: Sources `.ports.env` for dynamic port (ADW worktree), falls back to localhost:8000
- **Health Check Validation**: Verifies backend is running before schema download
- **Basic Auth Support**: Uses `API_DOCS_USERNAME`/`API_DOCS_PASSWORD` (defaults: `ayzer`/`ayzer`)
- **Error Handling**: Clear messages for common issues (backend down, auth failure, generation errors)
- **Colorized Output**: Green/yellow/red console feedback

## Usage

### Generate Types

```bash
cd app/frontend
npm run generate:types
```

Or from project root:
```bash
./scripts/generate-api-types.sh
```

Backend must be running: `cd app/backend && make dev`

### Type Imports

```typescript
import type { paths, components } from '@/types/api-generated'

type LoginRequest = paths['/api/v1/auth/login']['post']['requestBody']['content']['application/json']
type User = components['schemas']['UserRead']
```

### Configuration

- **Backend URL**: Override with `BACKEND_URL=http://localhost:9112 ./scripts/generate-api-types.sh`
- **Credentials**: Override with `API_DOCS_USERNAME` and `API_DOCS_PASSWORD`
- **Output**: `app/frontend/src/types/api-generated.ts` (auto-generated, git-ignored, not manually edited)

### When to Regenerate

- API endpoints added/modified/removed
- Pydantic models in request/response schemas change
- API documentation updated

## Type Structure

Generated file exports two namespaces:
- `paths`: Types by API path and HTTP method
- `components`: Direct schema access (models)

## Tool Selection

**openapi-typescript v7.4.4** selected for:
- Type-only generation (no runtime code)
- Excellent OpenAPI 3.x support
- Clean TypeScript output
- Active maintenance

Alternatives considered:
- `openapi-generator-cli`: Too heavyweight
- `orval`: Generates RTK hooks; project uses manual API slice config

## Integration Notes

- **RTK Query**: Generated types used to type manual endpoint definitions in `app/frontend/src/store/api.ts`
- **Multi-Tenancy**: Organization_id fields in tenant-scoped models enforce tenant isolation at compile-time
- **CI/CD**: Backend must run during build to download schema; type generation precedes frontend build
