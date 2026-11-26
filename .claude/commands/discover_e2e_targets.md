# Discover E2E Targets

Scan a project to discover testable features and produce a standardized manifest JSON for E2E test generation. Works generically on React + FastAPI projects.

## Variables

output_path: $1
spec_dir: $2

## CRITICAL CONSTRAINTS

- You are a **discovery agent**. Your job is to scan the project and produce a manifest JSON.
- **DO NOT** modify any source code.
- **DO NOT** generate tests — the caller handles that.
- **DO NOT** install packages.
- The ONLY tools you should use are: Read, Glob, Grep, Bash (for listing directories only)

## Instructions

### 1. Scan Frontend Routes

Find the route configuration. Look for files matching these patterns (in order of likelihood):
- `app/frontend/src/config/routes.ts` or `routes.tsx`
- `app/frontend/src/**/router.{ts,tsx}`
- `app/frontend/src/App.tsx` (may contain inline routes)

Extract all route definitions: `path`, component name, any permissions/guards, layout information.

### 2. Scan Navigation Configuration

Find navigation config files to determine target audience mapping:
- `app/frontend/src/config/navigation.ts` — main sidebar items → `end_user`
- `app/frontend/src/config/adminNav.ts` — admin hub items → `admin`
- `app/frontend/src/config/platformAdminNav.ts` — platform admin items → `platform_admin`
- `app/frontend/src/config/settingsNav.ts` — settings items → `end_user`

For each nav item, extract: `id`, `path`, `title`, `icon`, `permissions`.

If these specific files don't exist, look for navigation-related exports in `src/config/**/*.ts`.

### 3. Scan API Endpoints

Find backend route registrations:
- `app/backend/src/api/v1/__init__.py` — main router includes
- `app/backend/src/api/**/*.py` — individual route files

For each router, extract: prefix, endpoint methods (GET/POST/PUT/DELETE), path patterns.

### 4. Scan Page Components

For each route discovered in step 1, read the corresponding page component to identify:
- Whether it renders a table (list view)
- Whether it has forms (create/edit)
- Whether it has dialogs
- Whether it has delete/action buttons
- Key text content (headings, labels)

This determines what kind of tests to generate (smoke, CRUD, navigation, etc.).

### 5. Incorporate Existing Spec Files (optional)

If `{spec_dir}` is provided and non-empty, scan it for `test_*.md` files. For each spec:
- Read the `# E2E Test:` heading for the feature name
- Read the `## Test Steps` section for route paths (look for "Navigate to `/path`")
- Read the `## API Endpoints Tested` table for endpoint paths
- Read the `## User Story` section

Match specs to discovered routes/features by URL path overlap.

### 6. Group Into Modules

Cluster related routes, endpoints, and specs into modules. A module represents a coherent feature area. Guidelines:
- Group by top-level route prefix (e.g., all `/codebases*` routes = one module)
- Each module should have 1-8 acceptance criteria
- If a route has both a list view and a detail view, they belong to the same module
- Admin CRUD for a resource is a separate module from end-user views if they're in different nav sections

### 7. Assign Target Audience

Map each module to an audience based on where its routes appear:
- Routes in main navigation config → `end_user`
- Routes in admin navigation config → `admin`
- Routes in platform admin config → `platform_admin`
- Routes not in any nav (e.g., `/login`, `/register`) → `end_user`

### 8. Build Acceptance Criteria

For each module, derive acceptance criteria from what you discovered:
- **List page**: "Page loads with table", "Table has expected column headers"
- **Create form**: "Create dialog opens", "Form submission creates resource", "New resource appears in list"
- **Detail page**: "Detail page loads with expected sections"
- **Delete action**: "Resource can be deleted", "Deleted resource removed from list"
- **API verification**: "API returns created/updated/deleted resource"

If a spec file is attached to the module, also include criteria derived from the spec's test steps.

### 9. Write Manifest

Write the manifest JSON to `{output_path}` with this structure:

```json
{
  "project_summary": "Brief description derived from README or package.json",
  "source": "discover",
  "modules": [
    {
      "id": "kebab-case-id",
      "name": "Human Readable Name",
      "description": "What this feature does",
      "target_audience": "end_user|admin|platform_admin",
      "priority": "high|medium|low",
      "dependencies": [],
      "user_stories": ["As a user I want to..."],
      "acceptance_criteria": ["Page loads with heading", "CRUD operations work"],
      "estimated_complexity": "small|medium|large",
      "spec_path": ".claude/commands/e2e/test_feature.md",
      "routes": ["/feature", "/feature/:id"],
      "api_endpoints": ["GET /api/v1/feature", "POST /api/v1/feature"],
      "component_paths": ["src/pages/FeaturePage.tsx"]
    }
  ]
}
```

Fields:
- `spec_path`: Only set if an existing spec was matched to this module. Empty string if none.
- `routes`, `api_endpoints`, `component_paths`: Discovered from codebase scan. These help the test writer know what to test.
- `acceptance_criteria`: Derived from codebase analysis and/or spec files.
- `priority`: "high" for core features (auth, main CRUD), "medium" for secondary, "low" for admin/settings.

## Report

Return a JSON object (no markdown, raw JSON only):

```json
{
  "manifest_path": "{output_path}",
  "modules_count": 12,
  "specs_matched": 8,
  "success": true
}
```
