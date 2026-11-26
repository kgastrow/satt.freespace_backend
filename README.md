# Freespace Webapp

A production-ready, full-stack SaaS application template with **row-level multi-tenancy**, **FastAPI backend**, **React frontend**, and **AI-assisted development workflows**. Built for teams building scalable multi-tenant applications with complete data isolation.

## Features

### Multi-Tenancy
- **Row-level isolation** - Complete data separation between organizations
- **Organization-scoped** users, roles, permissions, and data
- **JWT tokens** carry organization context for automatic filtering
- **Super admin** access across all organizations
- **Soft deletes** - Never lose data, maintain complete audit trails

### Authentication & Security
- **JWT authentication** - Access tokens (15 min) + refresh tokens (30 days via httpOnly cookies)
- **Two-factor authentication (2FA)** - TOTP-based with setup and enforcement flows
- **SSO/OAuth** - External identity provider support with account linking
- **Session management** - Device tracking, session revocation, brute force detection
- **API keys** - Per-key rate limiting for programmatic access
- **Impersonation** - Admin can impersonate users with time-limited tokens
- **Security headers** - X-Frame-Options, HSTS, CSP, and more

### Backend (FastAPI)
- **Async throughout** - FastAPI + SQLAlchemy 2.0 async + asyncpg
- **High performance** - Uvicorn with uvloop, PgBouncer connection pooling
- **Redis caching** - JWT claims, user/org data with configurable TTLs
- **Background jobs** - ARQ (async Redis queue) for email, file processing, and scheduled tasks
- **RBAC** - Role-based access control with granular permissions and role hierarchy
- **Rate limiting** - SlowAPI with endpoint-specific limits (auth: 5/min, OTP: 3/min)
- **Prometheus metrics** - Request/response times, cache stats, DB pool stats
- **Notifications** - Multi-provider (email, SMS, WhatsApp) with templates and i18n
- **File management** - S3 storage with local fallback, thumbnails, type validation
- **Payments** - Pluggable providers (Stripe, PayFast, PayPal) with webhook handling
- **Feature flags** - System-wide and per-organization toggles
- **Audit logging** - All modifications tracked with user and timestamp
- **Cron jobs** - Configurable scheduled tasks via ARQ
- **Help center** - Knowledge base with articles and categories
- **Onboarding** - Multi-step flows with progress tracking and admin review
- **Maintenance mode** - Graceful service degradation with announcements
- **Data export** - User data export and deletion for compliance

### Frontend (React)
- **React 19** with TypeScript and Vite
- **Tailwind CSS 4** with shadcn/ui + Radix UI components
- **Redux Toolkit** for state management
- **React Hook Form + Zod** for form validation
- **Feature-based** architecture with modular organization
- **i18n** - Full internationalization with i18next (English included, extensible)
- **PWA support** - Service workers, offline fallback, caching strategies
- **WebSocket** - Real-time notifications and announcements
- **OpenAPI type generation** - Auto-generated TypeScript types from backend schema
- **Optimized builds** - Code splitting, Brotli/Gzip compression, lazy loading

### Production Ready
- **Docker Compose** for local development and production
- **Systemd services** for API and worker deployment
- **Nginx** reverse proxy configuration
- **Alembic** async-compatible database migrations (62+ migrations)
- **Comprehensive test suite** - Backend (pytest + xdist) and frontend (Vitest + Testing Library)
- **CI/CD** - GitHub Actions for automated testing and performance checks
- **Non-root containers** - Application runs as unprivileged user

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Node.js 18+ (for frontend development)
- Python 3.12+ (for backend development outside Docker)

### Rename the Project

After cloning, rename the template to your own project name:

```bash
./scripts/rename_ayzer.sh "my project"
```

This derives all naming variants from your input and updates the entire codebase:

| Variant | Example | Used in |
|---------|---------|---------|
| snake_case | `my_project` | Directories, services, queues, config |
| kebab-case | `my-project` | Docker, packages, S3, deploy |
| Title Case | `My Project` | Descriptions, UI text |
| UPPER CASE | `MY PROJECT` | HTML title, PWA name, TOTP issuer |

The script will prompt for optional customizations (press Enter to keep defaults):
- **Website URL** - Sidebar link target
- **Logo filenames** - Symbol and wordmark SVG assets
- **Apache ServerName** - Domain for the Apache virtual host

After completion, review the changes with `git diff` and remove the script:

```bash
git rm scripts/rename_ayzer.sh
```

### Local Development with Claude Code

The easiest way to set up local development is using Claude Code:

```bash
# In Claude Code, run:
/install
```

#### Claude Code Aliases

For convenience, set up these shell aliases:

```bash
# Source the aliases (one-time for current session)
source scripts/claude-aliases.sh

# Or add to your ~/.bashrc or ~/.zshrc for persistence
echo "source $(pwd)/scripts/claude-aliases.sh" >> ~/.bashrc
```

| Alias | Command | Description |
|-------|---------|-------------|
| `cld` | `claude` | Run Claude Code |
| `cldyo` | `claude --dangerously-skip-permissions` | Run Claude Code without permission prompts |
| `cyolo` | `claude --dangerously-skip-permissions` | Alias for `cldyo` |

This will:
- Check for required system dependencies (PostgreSQL, PgBouncer, Redis)
- Guide you through installing any missing dependencies via `./scripts/setup-system-deps.sh`
- Install backend and frontend dependencies
- Run database migrations

After installation, start the servers with:
```bash
./scripts/start.sh
```

### Development with Docker

```bash
# Clone the repository
git clone <your-repo-url>
cd freespace

# Start all services (PostgreSQL, PgBouncer, Redis, API, Worker)
cd app/backend
make dev

# In another terminal, start the frontend
cd app/frontend
npm install
npm run dev
```

The services will be available at:
- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### Seed Initial Data

```bash
cd app/backend
make seed  # Creates first organization and admin user
```

## Project Structure

```
freespace/
├── app/
│   ├── backend/                 # FastAPI backend
│   │   ├── src/
│   │   │   ├── api/             # Route handlers
│   │   │   ├── crud/            # Data access layer
│   │   │   ├── models/          # SQLAlchemy models
│   │   │   ├── serialisers/     # Pydantic v2 DTOs
│   │   │   ├── services/        # Business logic
│   │   │   ├── workers/         # ARQ background jobs
│   │   │   ├── core/            # Config, security, rate limiting
│   │   │   └── middleware/      # Metrics, instrumentation
│   │   ├── tests/               # pytest test suite
│   │   ├── alembic/             # Database migrations
│   │   ├── deploy/              # Systemd, Nginx configs
│   │   ├── docker-compose.yml   # Development services
│   │   └── Makefile             # Development commands
│   │
│   └── frontend/                # React frontend
│       ├── src/
│       │   ├── features/        # Feature modules
│       │   ├── components/      # UI components
│       │   ├── pages/           # Page components
│       │   ├── store/           # Redux state
│       │   ├── hooks/           # Custom hooks
│       │   ├── layouts/         # Root and dashboard layouts
│       │   ├── routes/          # Route configuration
│       │   ├── i18n/            # i18n setup
│       │   └── locales/         # Translation files
│       ├── package.json
│       └── vite.config.ts
│
├── ai_docs/                     # AI-friendly documentation
│   ├── backend/                 # Backend context guides
│   ├── frontend/                # Frontend context guides
│   └── specs/                   # Technical specifications
│
├── adws/                        # Agentic Development Workflows
│   ├── adw_*.py                 # Workflow scripts (26+)
│   ├── adw_modules/             # Shared workflow modules
│   └── README.md                # ADW documentation
│
├── scripts/                     # Utility scripts
├── .github/workflows/           # CI/CD pipelines
├── CLAUDE.md                    # Project context for AI assistants
└── README.md
```

## Development Commands

### Backend (from `app/backend/`)

| Command | Description |
|---------|-------------|
| `make dev` | Start development environment with Docker |
| `make test` | Run pytest test suite (8 workers) |
| `make test-fast` | Run tests in parallel with auto worker count |
| `make test-cov` | Run tests with coverage report |
| `make lint` | Run ruff and mypy |
| `make format` | Format with black and ruff |
| `make migrate` | Run database migrations |
| `make migrate-new msg="description"` | Auto-generate migration from model changes |
| `make seed` | Seed first tenant data |
| `make perf` | Run Locust load tests |
| `make benchmark` | Run pytest-benchmark micro-benchmarks |

### Frontend (from `app/frontend/`)

| Command | Description |
|---------|-------------|
| `npm run dev` | Start Vite dev server with HMR |
| `npm run build` | Production build (regenerates types, requires backend) |
| `npm run build:only` | Production build without type regeneration |
| `npm run test` | Run Vitest |
| `npm run lint` | Run ESLint |
| `npm run generate:types` | Generate TypeScript types from backend OpenAPI schema |

## Technology Stack

### Backend
| Component | Technology |
|-----------|------------|
| Framework | FastAPI 0.115 |
| Language | Python 3.12 |
| Server | Uvicorn + uvloop, Gunicorn |
| Database | PostgreSQL 15 |
| ORM | SQLAlchemy 2.0 (async + asyncpg) |
| Connection Pool | PgBouncer 1.21 |
| Cache | Redis 7 (hiredis) |
| Background Jobs | ARQ |
| Validation | Pydantic v2 |
| Migrations | Alembic |
| Authentication | JWT (PyJWT) + bcrypt |
| 2FA | pyotp (TOTP) |
| Rate Limiting | SlowAPI |
| Metrics | prometheus-client |
| Payments | Stripe, PayFast, PayPal |
| File Storage | S3 (boto3) + local fallback |
| Email | aiosmtplib (async) |
| Linting | ruff, black, mypy |
| Testing | pytest, pytest-xdist, pytest-asyncio |

### Frontend
| Component | Technology |
|-----------|------------|
| Framework | React 19 |
| Build Tool | Vite 7 |
| Language | TypeScript 5.9 |
| Styling | Tailwind CSS 4 |
| Components | shadcn/ui + Radix UI |
| State | Redux Toolkit |
| Forms | React Hook Form + Zod |
| Routing | React Router 7 |
| i18n | i18next |
| Icons | Lucide React |
| Dates | date-fns |
| PWA | vite-plugin-pwa |
| Testing | Vitest, Testing Library, MSW |

## Testing

### Backend Tests

```bash
cd app/backend

# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
pytest tests/api_tests/test_auth.py -v
```

Tests use:
- **In-memory SQLite** for fast execution (aiosqlite)
- **Fake Redis** for cache and rate limiting tests (fakeredis)
- **pytest-asyncio** for async test support
- **pytest-xdist** for parallel execution (up to 8 workers)
- **pytest-benchmark** for performance micro-benchmarks
- **Multi-tenancy isolation tests** to verify data separation

### Frontend Tests

```bash
cd app/frontend

# Run tests
npm run test

# Run with coverage
npm run test:coverage
```

Tests use:
- **Vitest** for fast test execution
- **React Testing Library** for component testing
- **MSW (Mock Service Worker)** for API mocking
- **@testing-library/user-event** for realistic user interaction simulation

### CI/CD

GitHub Actions pipelines run automatically on pull requests:
- **test.yml** - Backend pytest (8 parallel workers) + frontend Vitest
- **perf.yml** - Performance and load testing

## OpenAPI Type Generation

The project automatically generates TypeScript types from the backend's OpenAPI schema, ensuring type safety between frontend and backend.

### Generating Types

```bash
# Ensure backend is running first
./scripts/start.sh

# Then generate types (in another terminal)
cd app/frontend
npm run generate:types

# Or run the script directly
BACKEND_URL=http://localhost:9112 ./scripts/generate-api-types.sh
```

The generated types will be placed in `app/frontend/src/types/api-generated.ts` and are automatically git-ignored.

### Using Generated Types

```typescript
import type { paths, components } from '@/types/api-generated'

// Use path types for API requests
type LoginRequest = paths['/api/v1/auth/login']['post']['requestBody']['content']['application/json']
type LoginResponse = paths['/api/v1/auth/login']['post']['responses']['200']['content']['application/json']

// Use component schemas
type User = components['schemas']['UserRead']
type Organization = components['schemas']['OrganizationRead']
```

### When to Regenerate

Run the type generation script whenever:
- You add, modify, or remove backend API endpoints
- You change Pydantic models used in request/response schemas
- You update API documentation or descriptions

The generated types provide:
- **Type safety** - Catch API contract mismatches at compile time
- **Autocomplete** - Full IntelliSense for all API endpoints
- **Documentation** - API descriptions and field documentation in your IDE
- **Refactoring safety** - TypeScript will flag breaking changes

### Authentication

The OpenAPI schema endpoint is protected by HTTP basic auth. Default credentials:
- **Username**: `ayzer`
- **Password**: `ayzer`

To use custom credentials:
```bash
export API_DOCS_USERNAME=your_username
export API_DOCS_PASSWORD=your_password
npm run generate:types
```

## Production Deployment

### Docker Production

```bash
# Build production images
docker-compose -f docker-compose.prod.yml build

# Start services
docker-compose -f docker-compose.prod.yml up -d
```

### Systemd Services

```bash
# Deploy with provided script
sudo ./app/backend/deploy/deploy.sh

# Manage services
sudo systemctl status freespace-api
sudo systemctl status freespace-worker

# View logs
journalctl -u freespace-api -f
```

### Manual Start

```bash
# API server (production)
cd app/backend
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4 --loop uvloop

# Background worker
arq src.workers.worker.WorkerSettings
```

## AI-Assisted Development

This project includes comprehensive AI documentation in `ai_docs/`:

- **Baseline context** - Architecture overviews for backend and frontend
- **Context guides** - Detailed guides for auth, CRUD, caching, testing, etc.
- **Technical specs** - Multi-tenancy, RBAC, PgBouncer specifications
- **Skills** - Agent specialization definitions

### Agentic Development Workflows (ADWs)

The `adws/` directory contains automated workflows for AI-assisted development:

- **Isolated execution** - Each workflow runs in a separate git worktree
- **Dedicated ports** - Backend (9100-9114) and frontend (9200-9214)
- **Workflow phases** - Plan → Build → Test → Review → Document → Ship
- **State tracking** - Persistent JSON state across workflow phases

#### Available ADW Workflows

| Workflow | Type | Description | Typical Use Cases |
|----------|------|-------------|-------------------|
| `adw_plan_iso` | Planning Phase | Creates isolated worktree and generates implementation plan | Initial planning for features/bugs, spec generation before implementation |
| `adw_patch_iso` | Planning Phase | Quick patch workflow in isolated environment (triggered by 'adw_patch' keyword) | Small fixes, hotfixes, targeted changes without full planning phase |
| `adw_build_iso` | Implementation Phase | Implements solution in existing isolated worktree | Execute implementation after planning phase completes |
| `adw_test_iso` | Testing Phase | Runs tests in isolated environment with auto-resolution | Validate implementation, catch regressions, auto-fix test failures |
| `adw_review_iso` | Review Phase | Reviews implementation with screenshots and validation | Quality checks, visual verification, ensure spec compliance |
| `adw_document_iso` | Documentation Phase | Generates comprehensive documentation in isolated worktree | Create user guides, technical docs, API documentation |
| `adw_ship_iso` | Shipping Phase | Approves and merges PR to main branch | Final deployment step, merge approved changes |
| `adw_plan_build_iso` | Orchestrated Pipeline | Plan + Build phases in isolation | Quick feature implementation without tests |
| `adw_plan_build_test_iso` | Orchestrated Pipeline | Plan + Build + Test phases in isolation | Feature implementation with automated testing |
| `adw_plan_build_test_review_iso` | Orchestrated Pipeline | Plan + Build + Test + Review phases in isolation | Complete feature pipeline with quality assurance |
| `adw_plan_build_review_iso` | Orchestrated Pipeline | Plan + Build + Review phases in isolation (skips tests) | Features where visual review is more important than automated tests |
| `adw_plan_build_document_iso` | Orchestrated Pipeline | Plan + Build + Document phases in isolation | Features requiring immediate documentation |
| `adw_sdlc_iso` | Orchestrated Pipeline | Complete SDLC: Plan → Build → Test → Review → Document | Full development lifecycle without auto-merge, requires manual PR approval |
| `adw_multi_phase_sdlc_iso` | Multi-Phase Pipeline | Breaks large features into phases, each running build → test → review → commit | Large features exceeding single-agent context, multi-domain implementations |
| `adw_sdlc_ZTE_iso` | Zero Touch Execution | Complete SDLC with automatic PR approval and merge | Fully automated deployment pipeline - ⚠️ merges to main automatically! |

**Entry Point Workflows** (create worktrees): `adw_plan_iso`, `adw_patch_iso`, and all orchestrated pipelines

**Dependent Workflows** (require existing worktree): `adw_build_iso`, `adw_test_iso`, `adw_review_iso`, `adw_document_iso`, `adw_ship_iso`

See `adws/README.md` for detailed ADW documentation.

## Development Guidelines

1. **Multi-tenancy** - Always filter by `organization_id` for tenant-scoped queries
2. **Soft deletes** - Use `deleted_time` field, never hard delete
3. **Async I/O** - Use async/await for all I/O operations
4. **Validation** - Use Pydantic models for all request/response validation
5. **Testing** - Write tests including tenant isolation tests for new features

## Security

- **Row-level isolation** - Organization context enforced on all queries
- **JWT authentication** - Short-lived access tokens + httpOnly refresh cookies
- **Two-factor authentication** - TOTP-based 2FA with optional enforcement
- **Password hashing** - bcrypt with salting
- **Rate limiting** - Strict limits on auth (5/min), OTP (3/min), and general endpoints (100/min)
- **Brute force detection** - Automatic lockout on repeated failed attempts
- **Session management** - Device tracking, session listing, and remote revocation
- **Security headers** - X-Frame-Options, HSTS, CSP, X-Content-Type-Options
- **Audit logging** - All modifications logged with user, timestamp, and context
- **Non-root Docker** - Application runs as unprivileged user
- **Statement timeout** - 30-second database query timeout to prevent runaway queries

## License

[Choose your license - MIT, Apache 2.0, etc.]

## Contributing

This project uses **Agentic Development Workflows (ADWs)** for contributions:

- Each feature/bug runs in an isolated git worktree with dedicated ports, enabling parallel development
- Automated workflow phases handle planning, building, testing, review, and PR creation

### Example ADW Usage

```bash
cd adws/

# Process a GitHub issue (plan + build)
uv run adw_plan_build_iso.py 123

# Full SDLC with testing and review
uv run adw_sdlc_iso.py 456

# Run multiple issues in parallel
uv run adw_plan_build_iso.py 101 &
uv run adw_plan_build_iso.py 102 &
uv run adw_plan_build_iso.py 103 &
```

### GitHub Webhook Setup

For automatic issue processing, set up the webhook server:

```bash
# Set required environment variables
export GITHUB_WEBHOOK_SECRET="your-webhook-secret"
export GITHUB_REPO_URL="https://github.com/owner/repo"
export ANTHROPIC_API_KEY="sk-ant-..."

# Start the webhook server
cd adws/
uv run adw_triggers/trigger_webhook.py
```

Configure in GitHub repository settings:
- **Payload URL**: `https://your-domain.com/gh-webhook`
- **Content type**: `application/json`
- **Secret**: Your `GITHUB_WEBHOOK_SECRET` value
- **Events**: Select "Issues" and "Issue comments"

### Triggering Workflows via GitHub Issues

Include a workflow name in your issue body to trigger automatic processing:

```markdown
Add a button to export user data as CSV.

adw_plan_build_iso
```

**Available workflows:**
| Workflow | Description |
|----------|-------------|
| `adw_plan_iso` | Planning only |
| `adw_plan_build_iso` | Plan + build |
| `adw_plan_build_test_iso` | Plan + build + test |
| `adw_plan_build_review_iso` | Plan + build + review (skip tests) |
| `adw_sdlc_iso` | Full SDLC (plan + build + test + review + document) |
| `adw_multi_phase_sdlc_iso` | Multi-phase SDLC for large features (phases: build → test → review → commit) |
| `adw_sdlc_zte_iso` | Zero Touch Execution - auto-merges to main |

**Options:**
- Add `model_set heavy` for complex tasks (uses Opus model)
- Dependent workflows (`adw_build_iso`, `adw_test_iso`, etc.) require an existing ADW ID: `adw_test_iso adw-a1b2c3d4`

See [`adws/README.md`](adws/README.md) for complete documentation.
