# React Frontend Architecture Guide

## Tech Stack

| Category | Tools |
|----------|-------|
| Build | Vite, React 19, TypeScript |
| Styling | Tailwind CSS v4, shadcn/ui (Radix UI) |
| State | Redux Toolkit + RTK Query |
| Forms | React Hook Form + Zod |
| Routing | React Router |
| i18n | react-i18next |
| Testing | Vitest + React Testing Library |

## Multi-Tenant Architecture

**CRITICAL**: JWT tokens include `organization_id`. All API requests include Bearer token - backend enforces tenant isolation automatically.

## Directory Structure

```
frontend/src/
├── components/           # UI components
│   ├── ui/               # shadcn/ui components (can modify)
│   ├── AuthGuard.tsx     # Route protection
│   ├── AuthProvider.tsx  # Auth init + WebSocket connections
│   └── ErrorBoundary.tsx # Global error boundary
├── config/               # Route configs, navigation configs
├── features/             # Feature modules (auth/, permissions/)
├── hooks/                # Custom hooks (useAuth.ts, etc.)
├── layouts/              # Layout components
├── lib/utils.ts          # cn() helper for Tailwind
├── locales/              # i18n translations (en/)
├── pages/                # Route page components
├── store/                # Redux store
│   ├── index.ts          # Store setup
│   ├── api.ts            # RTK Query base API + token refresh
│   └── hooks.ts          # Typed useAppSelector, useAppDispatch
├── types/                # Shared types (auth.ts, api.ts)
├── test/                 # Test utilities (render wrapper)
└── router.tsx            # React Router config
```

## Core Patterns

| Pattern | Convention |
|---------|------------|
| Components | shadcn/ui with `cn()` for conditional classes. Add: `npx shadcn@latest add [name]` |
| State | RTK Query for server state. Use `useAppSelector`/`useAppDispatch` from `@/store/hooks` |
| Auth | `useAuth` hook for operations. Wrap protected routes with `<AuthGuard>` |
| Forms | Zod schemas + `zodResolver` + shadcn Form components |
| Routing | Define in `router.tsx`. Use `Link` for navigation |
| Styling | Tailwind utilities + theme variables in `index.css`. Dark mode via `.dark` class |
| i18n | `useTranslation` hook. Keys use namespace prefix (e.g., `settings:nav.account.title`). Translations in `src/locales/en/` |
| Testing | Colocate tests (`Component.test.tsx`). Use custom `render` from `@/test/utils` |

## Token Storage

- **Access token**: In-memory only (Redux state, 15-min TTL). Not persisted to storage.
- **Refresh token**: httpOnly cookie set by backend (invisible to JavaScript, 30-day TTL)
- On page load, `AuthProvider` bootstraps the session via a silent `POST /auth/refresh` call
- Automatic token refresh on 401 responses via `baseQueryWithReauth`
- All fetch requests use `credentials: 'include'` to send cookies

## Configuration

```
VITE_API_URL=http://localhost:8000/api/v1
```

Defaults to `http://localhost:8000/api/v1` if not set.

## Build Optimization

The Vite configuration (`vite.config.ts`) includes production optimizations:

### Code Splitting

All page components use `React.lazy()` for route-based code splitting. See `routing.md` for the lazy loading pattern.

### Manual Chunks

Vendor bundles are split for optimal caching:

| Chunk | Contents |
|-------|----------|
| `react-vendor` | react, react-dom |
| `router` | react-router-dom |
| `redux` | @reduxjs/toolkit, react-redux |
| `ui-vendor` | Radix UI components |
| `forms` | react-hook-form, zod, resolvers |
| `i18n` | i18next, react-i18next, i18next-browser-languagedetector |
| `date` | date-fns |
| `icons` | lucide-react |

### Compression

Production builds generate gzip (`.gz`) and brotli (`.br`) compressed files via `vite-plugin-compression2`.

### TypeScript Incremental Builds

`tsconfig.app.json` has `"incremental": true` for faster subsequent builds.

## Best Practices

1. Use `@/` path aliases for imports
2. Use RTK Query for all server state (not useState/useEffect)
3. Feature folders: `src/features/[feature]/`
4. Handle errors with `getErrorMessage()` from `@/types/api`
5. Never log credentials or tokens to console
6. **i18n is mandatory** - Never hardcode user-facing strings. Use `t()` from `useTranslation`. Add translations to en locale.
7. **Navigation placement depends on target audience** - See `navigation.md` for the full decision guide. In short: pages for **end-users** (the people who use the product daily) belong in the **main sidebar**. Pages for **administrators** (configuration, settings, user management) belong in the **admin hub** (`/admin`). Pages for **platform super-admins** belong in `/platform-admin`. Never dump all new pages into the admin hub by default — always consider who the primary user of each page is.
8. **AdvancedDataTable is mandatory** - Use `AdvancedDataTable` for ALL tables displaying list endpoint data. Never use raw `<Table>` for paginated API data. See `components.md` for usage.

## Specialized Context Files

- `auth.md` - Authentication patterns
- `security.md` - Security requirements
- `components.md` - shadcn/ui patterns
- `state.md` - Redux/RTK Query patterns
- `forms.md` - Form handling
- `routing.md` - React Router patterns
- `navigation.md` - Navigation zones, sidebar vs admin hub placement
- `testing.md` - Testing patterns
- `styling.md` - Tailwind patterns
- `i18n.md` - Internationalization patterns
