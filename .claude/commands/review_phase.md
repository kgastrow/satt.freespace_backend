# Review Phase

Review a single phase implementation against its acceptance criteria. This is a lightweight review focused on verifying the phase meets its defined criteria without requiring the full application to be running.

## Variables
phase_id: $1
plan_file: $2

## Instructions

### 1. Load Phase Definition
- Read the multi-phase plan at `{plan_file}`
- Find the phase section with id `{phase_id}`
- Extract: Description, Scope (files), Acceptance Criteria

### 2. Review Implementation

For each file in the phase's Scope:

1. **Verify file exists** (for new files) or **was modified** (for modify files)
2. **Read the implementation** and assess quality
3. **Check against acceptance criteria**

### 3. Acceptance Criteria Verification

For each acceptance criterion listed in the phase:
- Determine if it is **met**, **partially met**, or **not met**
- Provide evidence for your assessment
- Note any issues that need to be addressed

### 4. Code Quality Checks

Review the implementation for:
- **Correctness**: Does the code do what it's supposed to?
- **Patterns**: Does it follow existing codebase patterns?
- **Security**: Any obvious security issues? (SQL injection, XSS, etc.)
- **Multi-tenancy**: If tenant-scoped, is `organization_id` filtering in place?
- **Error handling**: Are errors handled appropriately?
- **Types**: Are TypeScript/Python types properly defined?
- **i18n**: For any UI work, are ALL user-facing strings using the `t()` function (no hardcoded display text), with keys present in ALL locale files under `app/frontend/src/locales/`? Flag hardcoded strings or missing locale keys as a **blocker**.
- **Responsive**: For any UI work, is the implementation responsive for BOTH mobile (390x844) and desktop (1440x900)? Flag desktop-only layouts as a **blocker**.
- **Test existence**: Do the tests required by this phase's plan (Test Scope / Testing Strategy) actually exist in the diff — especially tenant-isolation tests for any new CRUD? If a required test is silently missing (not explicitly deferred to a later phase of the plan), flag it as a **blocker**. If the plan explicitly defers the test to a later phase, that is acceptable.

### 5. Scope Compliance

Verify that:
- Only files in the phase scope were modified for NEW functionality
- No unexpected changes to other files
- Changes are minimal and focused

**Infrastructure Backfill Exception:**

If files outside the phase scope were modified, determine whether each change is:

1. **Infrastructure backfill (ACCEPTABLE):** Completing setup/registration that a PREVIOUS COMPLETED phase should have done. Examples:
   - Registering a reducer in `store/index.ts` that was created in an earlier phase
   - Exporting a model from `__init__.py` that was created in an earlier phase
   - Adding imports/configuration needed to use something from a previous phase
   - Enabling plugins (e.g., `enableMapSet()`) required by earlier phase code

2. **Forward reference (BLOCKER):** Adding imports, lazy imports, route registrations, or references to files/components that do NOT yet exist in the codebase and are NOT created in this phase's scope. Examples:
   - `lazy(() => import('@/pages/admin/SomePage'))` where `SomePage.tsx` is in a later phase
   - Route config entries for pages that haven't been created yet
   - API router includes for modules that don't exist yet
   - Any `import` statement where the target file does not exist on disk

3. **Scope violation (BLOCKER):** Adding new functionality outside this phase's responsibility. Examples:
   - Creating new components not in the phase scope
   - Adding new features unrelated to the phase
   - Modifying business logic in unrelated files

**Key questions for each out-of-scope change:**
1. "Does the imported/referenced file already exist on disk?" — If NO, it's a **forward reference (BLOCKER)**.
2. "Is this change completing work from a PREVIOUS completed phase, or setting up for a FUTURE phase?" — Only PREVIOUS phase completions are acceptable.
3. "Is this change adding new work?" — If YES, it's a **scope violation (BLOCKER)**.

If ALL out-of-scope changes are infrastructure backfills (not forward references), set `scope_compliance.compliant: true` and list them in `infrastructure_backfills` (not `unexpected_changes`).

## Output Format

```json
{
  "phase_id": "{phase_id}",
  "review_passed": true|false,
  "summary": "<2-3 sentence summary of the review>",
  "criteria_results": [
    {
      "criterion": "<acceptance criterion text>",
      "status": "met|partially_met|not_met",
      "evidence": "<how this was verified>"
    }
  ],
  "issues": [
    {
      "severity": "blocker|warning|suggestion",
      "description": "<description of the issue>",
      "file": "<file path if applicable>",
      "resolution": "<suggested fix>"
    }
  ],
  "scope_compliance": {
    "compliant": true|false,
    "unexpected_changes": ["<list of files with TRUE scope violations>"],
    "infrastructure_backfills": ["<list of files with acceptable backfill changes>"]
  }
}
```

### Review Decision Rules

**PASS** (review_passed: true) if:
- All acceptance criteria are met or partially met with minor issues
- No blocker-severity issues
- Scope compliance is maintained (infrastructure backfills are acceptable)

**FAIL** (review_passed: false) if:
- Any acceptance criterion is not met
- Any blocker-severity issue exists
- TRUE scope violations occurred (not infrastructure backfills)
- Forward references detected (imports/references to non-existent files)

**Note:** Infrastructure backfills do NOT cause failure. They are a normal part of multi-phase development where earlier phases may have incomplete setup. However, forward references (imports of files that don't exist yet) ALWAYS cause failure.

### Severity Guidelines

- **blocker**: Must be fixed before phase can complete
  - Missing core functionality
  - Security vulnerabilities
  - Build/test failures
  - Forward references (imports, lazy imports, or route configs pointing to files that don't exist on disk)
  - Major scope violations (adding NEW functionality outside scope - NOT infrastructure backfills)

- **warning**: Should be addressed but doesn't block
  - Minor deviations from patterns
  - Missing edge case handling
  - Suboptimal implementation

- **suggestion**: Nice to have improvements
  - Code style improvements
  - Additional test coverage
  - Documentation additions

## Example Output

### Example 1: Clean pass (no out-of-scope changes)
```json
{
  "phase_id": "backend-websocket-infrastructure",
  "review_passed": true,
  "summary": "WebSocket infrastructure implemented correctly with connection manager and endpoint. All acceptance criteria met.",
  "criteria_results": [
    {
      "criterion": "WebSocket endpoint at /ws/connect",
      "status": "met",
      "evidence": "Endpoint defined in websocket.py at line 15, correctly mounted in router"
    }
  ],
  "issues": [],
  "scope_compliance": {
    "compliant": true,
    "unexpected_changes": [],
    "infrastructure_backfills": []
  }
}
```

### Example 2: Pass with infrastructure backfills
```json
{
  "phase_id": "frontend-announcement-integration",
  "review_passed": true,
  "summary": "AnnouncementBanner integrated into layout with tests. Infrastructure backfills applied to register reducer from Phase 5.",
  "criteria_results": [
    {
      "criterion": "AnnouncementBanner integrated into RootLayout",
      "status": "met",
      "evidence": "AnnouncementBanner imported and rendered in RootLayout.tsx"
    }
  ],
  "issues": [],
  "scope_compliance": {
    "compliant": true,
    "unexpected_changes": [],
    "infrastructure_backfills": [
      "app/frontend/src/store/index.ts - registered announcementsReducer from Phase 5",
      "app/frontend/src/test/utils.tsx - added announcements reducer to test store"
    ]
  }
}
```

### Example 3: Fail with true scope violation
```json
{
  "phase_id": "backend-api-endpoint",
  "review_passed": false,
  "summary": "API endpoint implemented but added unrelated UI component outside scope.",
  "criteria_results": [
    {
      "criterion": "GET /api/items endpoint",
      "status": "met",
      "evidence": "Endpoint implemented in items.py"
    }
  ],
  "issues": [
    {
      "severity": "blocker",
      "description": "Created new ItemCard.tsx component which is not in phase scope",
      "file": "app/frontend/src/components/ItemCard.tsx",
      "resolution": "Remove this file - frontend components belong in a later phase"
    }
  ],
  "scope_compliance": {
    "compliant": false,
    "unexpected_changes": ["app/frontend/src/components/ItemCard.tsx"],
    "infrastructure_backfills": []
  }
}
```

### Example 4: Fail with forward reference
```json
{
  "phase_id": "frontend-device-list-page",
  "review_passed": false,
  "summary": "Device list page implemented well, but routes.ts imports DeviceDetailPage which doesn't exist yet — it's scheduled for a later phase.",
  "criteria_results": [
    {
      "criterion": "DevicesPage with data table and search",
      "status": "met",
      "evidence": "DevicesPage.tsx created with AdvancedDataTable, search, and filters"
    }
  ],
  "issues": [
    {
      "severity": "blocker",
      "description": "Forward reference: routes.ts adds lazy(() => import('@/pages/admin/DeviceDetailPage')) but DeviceDetailPage.tsx does not exist on disk and is not created in this phase's scope",
      "file": "app/frontend/src/config/routes.ts",
      "resolution": "Remove the DeviceDetailPage import and route config entry. The phase that creates DeviceDetailPage should add its own route registration."
    }
  ],
  "scope_compliance": {
    "compliant": false,
    "unexpected_changes": ["app/frontend/src/config/routes.ts - forward reference to non-existent DeviceDetailPage"],
    "infrastructure_backfills": []
  }
}
```

## Report
Output the JSON review result only, no additional text.
