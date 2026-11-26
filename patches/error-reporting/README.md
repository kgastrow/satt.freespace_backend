# Error reporting + support submission

Port guide for the in-app error page that lets users file a support item with
diagnostics captured automatically (page, failing component, recent actions,
environment). Built for the NextCase template stack: **React 19 + TypeScript +
Vite + Tailwind v4 + shadcn/ui + Redux Toolkit (RTK Query) + i18next**.

`error-reporting.patch` in this folder is a unified diff of the complete
feature. Apply it from the repo root:

```bash
git apply --3way patches/error-reporting/error-reporting.patch
# or, if not in a git repo / hunks reject:
patch -p1 < patches/error-reporting/error-reporting.patch
```

If context-line hunks reject (your template's `ErrorBoundary.tsx`,
`RootLayout.tsx`, `router.tsx`, or `FeedbackForm.tsx` have diverged), apply the
**new files** cleanly and make the four edits by hand using the per-file notes
below.

---

## What it does

- A rich, themed **"Something went wrong"** page replaces React's white-screen
  for any render error inside a route.
- Actions: **Try Again** (reset boundary), **Reload Page**, and — for
  authenticated users — **Report to support**.
- Report opens the existing feedback dialog **pre-filled** (type `bug`, a
  subject, and a human summary) with full diagnostics **attached as a file**.
- Diagnostics are gathered automatically: error name/message/stack, page
  URL + path, the React component that threw, a breadcrumb trail of recent
  navigations + clicks, and environment (UA, viewport, locale, build version).

---

## Prerequisites in the template

The feature reuses existing template infrastructure. Confirm these exist (they
do in the stock NextCase template) before applying:

| Dependency | Used for |
|---|---|
| Feedback widget + RTK API (`features/feedback`, `useSubmitFeedbackMutation`, `useUploadAttachmentMutation`) | Submitting the support item |
| Files API (`features/files`, `useUploadFileMutation`, `MediaUse`) | Uploading the diagnostics attachment |
| `useAppSelector` + `auth` slice (`state.auth.isAuthenticated`) | Gating the report button |
| shadcn `Button`, `Card`, `Dialog`, `ScrollArea` | Fallback UI + report dialog |
| Design-token Tailwind aliases (`bg-paper`, `text-ink/-2/-3`, `bg-surface-2`, `bg-danger-nc-soft`, `text-danger-nc`, `rounded-nc-md`, `font-display`, `font-mono-nc`) | Theming (light/dark safe) |
| `react-i18next` + `common` namespace | Copy |
| `react-router-dom` (`useLocation`) | Navigation breadcrumbs |

If your design tokens use different alias names, remap the classes in
`ErrorFallback.tsx` / `CrashTestPage.tsx` accordingly.

---

## Files

### New files (apply as-is)

| File | Purpose |
|---|---|
| `src/lib/errorBreadcrumbs.ts` | In-memory ring buffer (15 entries) of recent navigations + clicks. Captures only UI labels (button text / `aria-label` / `data-breadcrumb`) — never input values. |
| `src/lib/errorDiagnostics.ts` | Builds the structured diagnostics payload from a caught error + component stack + breadcrumbs + environment. |
| `src/components/ErrorFallback.tsx` | The themed error page + the pre-filled report dialog. |
| `src/pages/dev/CrashTestPage.tsx` | **Dev-only** page (`/dev/crash`) with a button that throws a render error, for testing the boundary. Excluded from prod builds. |
| `src/lib/errorBreadcrumbs.test.ts`, `src/lib/errorDiagnostics.test.ts`, `src/components/ErrorFallback.test.tsx` | Unit + component tests (27 cases). |

### Modified files (4 edits)

**`src/components/ErrorBoundary.tsx`** — capture the component stack and add a
`renderFallback` render-prop:
- Add `componentStack: string | null` to state; set it in `componentDidCatch`
  from `errorInfo.componentStack`.
- Add an optional `renderFallback?: ({ error, componentStack, reset }) => ReactNode`
  prop; in `render()`, when `hasError && error`, call it first (before the
  existing `fallback` / default UI).
- The existing top-level boundary (in `main.tsx`) is untouched and stays as the
  catastrophic last-resort fallback — it sits **above** the Redux/i18n
  providers and cannot use them.

**`src/layouts/RootLayout.tsx`** — mount the rich boundary **inside** the
providers and wire breadcrumbs:
- Wrap `<Outlet />` in `<ErrorBoundary renderFallback={({error, componentStack, reset}) => <ErrorFallback ... />}>`.
- `useEffect(() => installBreadcrumbCollectors(), [])` once on mount.
- `useEffect(() => recordBreadcrumb('navigation', ...), [location.pathname])`.

**`src/router.tsx`** — register the dev-only crash route so it is
**dead-code-eliminated from production**. The lazy import must live *inside* the
`import.meta.env.DEV` branch (a top-level `lazyNamed(...)` const is NOT
tree-shaken — Rollup keeps it as potentially side-effecting and still emits the
chunk). See the `devRoutes` IIFE in the patch, then `...devRoutes` in the root
route's `children`.

**`src/features/feedback/components/FeedbackForm.tsx`** — accept pre-fill +
diagnostics (backward compatible; all new props optional):
- `defaultValues?: Partial<Pick<FeedbackFormData,'type'|'subject'|'message'|'rating'>>`
  → seed `useForm` defaults; call `form.trigger()` on mount when provided so the
  submit button is enabled without editing a field.
- `diagnostics?: unknown` + `diagnosticsFilename` → after the feedback is
  created, upload the payload as a file attachment (inside the existing
  non-blocking attachment `try/catch`).

---

## ⚠️ Backend caveat — diagnostics attach as `.txt`, not `.json`

There are **two** `DEFAULT_ALLOWED_EXTENSIONS` lists in the backend:

- `src/services/files/validators.py` (fallback when an org has no settings row) —
  includes `json`.
- `src/models/organization_file_settings.py` and `src/crud/file_settings.py`
  (the per-org default that every org's settings row actually uses) —
  **does not include `json`** (it has `txt`, `csv`).

So uploading `error-diagnostics.json` is rejected by `validate_extension`, and
`FeedbackForm` silently swallows the attachment error. The feature therefore
uploads **`error-diagnostics.txt`** (`text/plain`); the content is still
pretty-printed JSON, readable and downloadable. The inline summary in the
message body is a safety net even if the attachment fails.

If you'd rather attach real `.json`, add `"json"` (and `"xml"`) to the per-org
`DEFAULT_ALLOWED_EXTENSIONS` in **both** `models/organization_file_settings.py`
and `crud/file_settings.py`, then change `diagnosticsFilename` back to
`error-diagnostics.json` / `application/json` in `FeedbackForm.tsx`.

---

## i18n

The patch adds an `errorBoundary` block to `locales/en/common.json` and
`locales/af/common.json`. **Add the same keys to every locale file in your
template** (the template's locale set may differ from this app's). Keys:

`eyebrow, title, description, tryAgain, reloadPage, reportButton,
reportDialogTitle, reportDialogDescription, pageLabel, componentLabel,
errorLabel, recentActionsLabel, noRecentActions, unknownComponent,
prefillSubject ("Error: {{message}}"), prefillIntro, diagnosticsAttachedNote`.

`title / description / tryAgain / reloadPage` already exist in the stock
template — the patch only **adds** the rest, so a locale-parity test stays green.

---

## Verify

1. `npm run dev`, log in, click around (seeds click breadcrumbs).
2. Visit **`/dev/crash`** → **Trigger render error**. (Dev only; in dev, dismiss
   the Vite error overlay with `Esc` to see the fallback underneath.)
3. The page shows **Page: `/dev/crash`** and **Component: `Boom`**. Toggle dark
   mode — it should flip cleanly.
4. **Report to support** → dialog is pre-filled → submit → open the feedback
   **detail** page (attachments render there, not in the list) → confirm
   `error-diagnostics.txt` is attached.
5. `npm run test` — the 3 new test files (27 cases) should pass.
6. `npm run build:only` → confirm no `CrashTestPage` chunk and no `dev/crash`
   string in `dist/` (dev route excluded from prod).
