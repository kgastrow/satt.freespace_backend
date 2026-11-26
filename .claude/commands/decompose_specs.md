# Specification Decomposition for Greenfield Implementation

Decompose functional specifications and user stories into implementable modules for a greenfield project. This command analyzes spec documents and produces a structured JSON response defining modules, dependencies, and execution order.

## Variables
spec_content_file: $1
output_file: $2

## Instructions

### Overview

You are analyzing specification documents (functional specs, user stories, etc.) to decompose them into discrete, implementable **functional modules**. Each module should represent a coherent feature area that can be implemented through the SDLC workflow.

### Module Sizing Guidelines

Each module should:
- Represent a **cohesive functional area** (e.g., "User Authentication", "Invoice Management", "Banking Integration")
- Be implementable in **1-5 SDLC cycles** (could be single or multi-phase depending on complexity)
- Have **clear boundaries** - minimal overlap with other modules
- Be **independently testable** with its own acceptance criteria
- Produce **working functionality** after implementation

### Target Audience Classification

Every module MUST include a `target_audience` field. This determines where UI pages are placed in the application's navigation:

- **end_user** — Pages for the product's primary users (their core daily workflow). These belong in the **main sidebar**, visible immediately after login. Examples: a task dashboard, a message inbox, a field capture interface, a reporting view.
- **admin** — Pages for organization administrators managing configuration, reference data, users, and settings. These belong in the **admin hub** (`/admin`). Examples: user management, lookup table CRUD, org settings, audit logs.
- **platform_admin** — Pages for platform super-administrators. These belong in the **platform admin hub** (`/platform-admin`). Examples: tenant management, system configuration.
- **backend_only** — No UI pages (API-only, background workers, data models). No navigation placement needed.

**Key distinction:** Having permissions does NOT make something an admin page. If the spec describes a workflow used by the product's primary users as part of their daily job, it's `end_user` even if it requires permissions. Think about who opens this page multiple times per day vs who configures it once and forgets about it.

**Bias check:** In a typical greenfield project, the **majority** of modules should be `end_user` — these are the pages the product is built around. Only a small number should be `admin` (configuration, reference data, org settings). If your decomposition has more `admin` modules than `end_user` modules, re-examine each `admin` classification and ask: "Is this really a page an admin configures once, or is it a page primary users interact with daily?" Common misclassifications:
- A list/detail page for domain entities (customers, orders, inspections) → almost always `end_user`, not `admin`
- A dashboard or reporting view → `end_user`
- CRUD for reference/lookup data that changes infrequently (account types, templates, categories) → `admin`
- User/role management → `admin`

### Module Granularity

Strike a balance between:
- **Too Large**: "Build the whole accounting system" → Should be multiple modules
- **Too Small**: "Add email field validation" → Should be part of a larger module
- **Just Right**: "Customer Management" with CRUD, search, statements, payment terms

Target **5-15 modules** for a typical greenfield project. Adjust based on spec complexity.

### User Persona Identification

Before decomposing into modules, identify **distinct user personas** from the spec. A persona represents a category of user with a unique workflow, permission set, or onboarding path.

**When to define a persona:**
- The spec describes **two or more distinct user workflows** (e.g., field workers vs back-office staff, patients vs practitioners, buyers vs sellers)
- A user type requires **specialized onboarding** (e.g., credential verification, license upload, profile setup with domain-specific fields)
- A user type needs **different default permissions** than the standard member role
- A user type should see a **different primary interface** after login (e.g., a companion app, a simplified mobile view, a specialized dashboard)

**When NOT to define a persona:**
- The distinction is purely about **permission levels** within the same workflow (e.g., viewer vs editor of the same data) — use roles instead
- The spec only describes **one type of end user** — the default "member" role is sufficient
- The distinction is **admin vs non-admin** — that's handled by the existing role hierarchy

**Persona vs Role:**
- **Persona (UserType)**: Fundamentally different user category with distinct workflows, onboarding, and UI. Think "doctor vs patient" or "driver vs dispatcher".
- **Role**: Permission level within the same workflow. Think "viewer vs editor" or "member vs manager". Roles control what you CAN do; personas control what you ARE.

Each persona produces:
- A **UserType** record (global, with onboarding configuration)
- A **Role** with appropriate default permissions (or reuse existing roles)
- **Permission definitions** for the persona's feature areas (`resource:action` format)
- **Onboarding steps** if required (field definitions, approval workflow)

### Analysis Process

1. **Read All Specs**: Thoroughly analyze all provided specification content
2. **Detect Design Handoff**: Check whether the spec content includes a design handoff (see "Design Handoff Detection" below)
3. **Identify User Personas**: Extract distinct user types from the spec (see criteria above)
4. **Identify Feature Areas**: Group related functionality into cohesive modules
5. **Map User Stories**: Associate user stories with their respective modules
6. **Assign Target Audiences**: Determine which persona each module serves
7. **Extract Acceptance Criteria**: Pull testable criteria from specs for each module
8. **Determine Dependencies**: Identify which modules depend on others
9. **Estimate Complexity**: Assess implementation effort for each module
10. **Plan Execution Order**: Sequence modules respecting dependencies and priorities
11. **Attach Design References (if handoff detected)**: For every UI-bearing module, attach `design_references` and `design_screens` pulled from the handoff (see "Design Reference Attachment" below)
12. **Auto-emit Design Polish Module (if handoff detected)**: Append a final cross-cutting `design-polish` module that runs after every UI module to enforce visual consistency across the app (see "Design Polish Module" below). Skip this step entirely when no handoff is detected — the app has no brand baseline to enforce against.

### Design Handoff Detection

A design handoff is present when the spec content includes a section that:
- Defines design tokens (color palette, typography, spacing, radii, shadows) AND
- Describes one or more named screens with layout specifications, OR
- Includes file paths to prototype JSX/HTML files (typically under `specs/design_handoff*/src/`)

Conventionally the handoff is rooted at a `specs/design_handoff*/README.md` file and ships with a `src/` subdirectory of prototypes. The spec content's `# FILE:` headers will identify which input files belong to the handoff.

If no design handoff is detected, **`design_references` and `design_screens` MUST be omitted (or set to empty arrays) on every module** — they are no-ops when no handoff is provided. The rest of the decomposition is unchanged.

### Design Reference Attachment

When a design handoff IS detected:

**For every module with `target_audience ∈ {end_user, admin, platform_admin}`** that delivers user-facing screens, attach:

1. **`design_references`** — array of objects, one per screen this module owns:
   ```json
   {
     "screen_id": "screen-store-entry",
     "screen_name": "Store entry",
     "surface": "client-pwa-instore",
     "theme": "dark",
     "readme_section": "Client PWA — In-store self-scan flow > Screen 1 — Store entry",
     "prototype_file": "specs/design_handoff_legacy_sports/src/screens-instore.jsx",
     "prototype_component": "ScreenStoreEntry"
   }
   ```
   - `screen_id`: kebab-case slug derived from the screen name
   - `surface`: which app surface (e.g. `client-pwa-instore`, `client-pwa-online`, `management-centre`, `public-web`)
   - `theme`: `dark`, `light`, or `auto`
   - `readme_section`: human-readable path through the handoff README headings, used by the implementor to locate the spec block
   - `prototype_file`: path (workspace-relative) to the prototype JSX/HTML file containing the reference implementation
   - `prototype_component`: name of the exported React component or HTML id for the screen, if identifiable

2. **`design_screens`** — array of strings, one per screen, containing the **verbatim layout spec block** copied from the handoff README. This is what the implementor reads inline without having to navigate. Include:
   - The screen heading line
   - The "Layout (top → bottom)" / "Layers (stacked)" block in full
   - Any interaction notes, animation specs, and copy specs
   - 50–400 lines per screen is typical — do not summarize, copy verbatim

**Backend-only modules** (auth core, data models, API endpoints with no UI) get neither field — leave them omitted.

**Mapping modules to screens:** A single module typically owns 1–5 related screens. For example, a "Self-scan checkout" module owns the store-entry screen, scan-loop screen, item-confirm modal, and exit-QR screen. Use the handoff README's section structure as the primary signal — screens grouped together in the README usually belong to the same module.

If a screen is referenced by multiple modules (e.g. a shared component), attach it to the module that owns its primary route and add a `"shared_with": ["other-module-id"]` field on that screen's design_reference entry.

### Design Polish Module (auto-injected when handoff detected)

When a design handoff IS detected, append exactly one additional module to the end of the modules array — a cross-cutting consistency pass that runs after every UI-bearing module has been built and merged. The rationale:

- A typical handoff prototypes 5–20 representative screens but the implementation produces 30–80+ screens. Unmocked screens get brand-correct fundamentals from `ai_docs/frontend/baseline_context.md` (tokens, type, shape language) but no specific layout to mimic.
- Earlier modules can't anticipate every cross-screen consistency concern (button variants, modal patterns, toast styling, empty-state language) that emerges only once multiple modules ship.
- A retroactive polish pass is the only mechanism in this workflow that can audit and unify the whole UI surface.

**Module shape — emit exactly this structure** (substitute the real list of UI module ids and update complexity/description to fit the actual project):

```json
{
  "id": "design-polish",
  "name": "Design Polish & Consistency Pass",
  "description": "Cross-cutting audit and polish pass across every UI module. Verifies token discipline, typography scale, shape-language utilities, reserved-token usage, and cross-screen pattern consistency against ai_docs/frontend/context/design_system.md. Fixes divergences in place; does not add new features or routes.",
  "priority": "low",
  "dependencies": ["<every UI-bearing module id>"],
  "target_audience": "backend_only",
  "user_stories": [
    "As a user, every screen of the application uses the same brand palette, type scale, spacing rhythm, and shape language so the product feels like a single coherent surface."
  ],
  "acceptance_criteria": [
    "Every hardcoded color, font-size, radius, and shadow outside the token system in app/frontend/src/ is replaced with a token reference from ai_docs/frontend/context/design_system.md, or justified inline with a comment when intentionally bespoke.",
    "Reserved tokens called out in the design system (e.g. accent-only tokens, rewards-only tokens) appear only in their reserved contexts.",
    "Shape-language utilities (CTA clip-paths, chip shapes, drop-corner badges) are applied consistently across all UI modules — same utility class / variant on equivalent elements.",
    "Typography scale is honored — no off-scale font-size values; all type uses the tokens or utility classes defined in baseline_context.md.",
    "Cross-screen patterns are unified: buttons, dialogs, modals, toasts, form fields, and empty states look identical across modules. Variants are intentional, not accidental.",
    "Dark/light theme handling is consistent — every screen that supports both themes renders correctly in both."
  ],
  "estimated_complexity": "medium",
  "spec_references": [
    "ai_docs/frontend/baseline_context.md (Brand Design System section)",
    "ai_docs/frontend/context/design_system.md (full token reference and screen catalog)"
  ]
}
```

**Rules for the polish module:**

- `dependencies` MUST list **every UI-bearing module** in the decomposition (every module with `target_audience ∈ {end_user, admin, platform_admin}`). The polish pass cannot start until every UI surface has shipped.
- `target_audience` MUST be `backend_only`. This is intentionally a misnomer — the module operates on frontend code, but treating it as backend_only correctly tells the orchestrator that it (a) needs no navigation placement, (b) should be skipped by the E2E validation pass (no new features to test), and (c) should not be assigned `design_references` (it spans every screen, not specific ones).
- `priority` MUST be `low`. The app is functional without polish; this is the last value-add layer.
- `estimated_complexity` SHOULD scale with the UI module count: `small` for 1–3 UI modules, `medium` for 4–10, `large` for 11+. The polish module's work scales with how many screens it has to audit.
- DO NOT attach `design_references` or `design_screens` to the polish module — leave both fields omitted. The module's reference is the consolidated `design_system.md`, not a specific prototype.
- Append the module to `execution_order` as the **final** entry, after every UI-bearing module.

**Skip this entire section when no design handoff is detected** — the polish module is meaningless without a brand baseline to enforce against. The decomposition should emit no `design-polish` module in that case.

### Dependency Rules

- **Foundation modules first**: Auth, data models, core infrastructure
- **Feature modules next**: Build on foundation
- **Integration modules later**: Depend on multiple feature modules
- **Polish modules last**: UI/UX refinements, optimizations

### Priority Levels

- **critical**: Must be implemented first, blocks most other work (e.g., auth, data models)
- **high**: Important features, may have dependents (e.g., core CRUD operations)  
- **medium**: Standard features (e.g., reports, integrations)
- **low**: Nice-to-have, can be deferred (e.g., advanced analytics, optimizations)

### Complexity Estimation

- **small**: 1-2 files, straightforward implementation, < 1 day
- **medium**: 3-8 files, some complexity, 1-3 days
- **large**: 8-15 files, significant complexity, 3-7 days
- **xl**: 15+ files, high complexity, will require multi-phase SDLC

## Output Format

Return a JSON object (no markdown code blocks, raw JSON only) with this structure.

> **Note on the example below:** the `design_references` / `design_screens` fields on the `customer-management` module AND the entire `design-polish` module (including its slot in `execution_order`) are shown here for completeness — they are emitted **ONLY when a design handoff was detected** per the "Design Handoff Detection" rules above. **If no handoff is present, omit all three of these from your output entirely** — do not emit empty arrays, do not emit a stub polish module. The decomposition for a no-handoff project ends at the last UI/backend module.

```json
{
  "project_summary": "Brief description of the overall project from specs",
  "total_user_stories": 42,
  "user_personas": [
    {
      "id": "field-worker",
      "name": "Field Worker",
      "description": "Primary end users who perform inspections, capture data, and submit reports in the field",
      "is_default": false,
      "requires_onboarding": true,
      "requires_manual_review": false,
      "onboarding_fields": ["certification_number", "region", "specialization"],
      "suggested_role": "field-worker",
      "permissions": ["inspections:read", "inspections:write", "reports:submit", "locations:read"],
      "navigation_zone": "end_user",
      "notes": "Gets a simplified mobile-first dashboard after onboarding approval"
    },
    {
      "id": "reviewer",
      "name": "Reviewer",
      "description": "Back-office staff who review submitted reports, approve/reject inspections, and manage field worker assignments",
      "is_default": false,
      "requires_onboarding": false,
      "requires_manual_review": false,
      "onboarding_fields": [],
      "suggested_role": "reviewer",
      "permissions": ["inspections:read", "inspections:review", "reports:read", "reports:approve", "field_workers:read", "field_workers:assign"],
      "navigation_zone": "end_user",
      "notes": "Uses the main dashboard with review queues and assignment tools"
    }
  ],
  "modules": [
    {
      "id": "auth-core",
      "name": "Authentication & Authorization",
      "description": "User authentication, session management, role-based access control, and permission system",
      "priority": "critical",
      "dependencies": [],
      "target_audience": "backend_only",
      "user_stories": [
        "US-001: As a user, I want to log in with email and password",
        "US-002: As an admin, I want to manage user roles"
      ],
      "acceptance_criteria": [
        "Users can register with email/password",
        "Users can log in and receive JWT token",
        "Role-based permissions enforced on all endpoints",
        "Session timeout after 24 hours of inactivity"
      ],
      "estimated_complexity": "large",
      "spec_references": [
        "Functional Spec Section 11: User Management & Permissions",
        "User Stories: US-001 through US-012"
      ]
    },
    {
      "id": "customer-management",
      "name": "Customer Management UI",
      "description": "Customer list, detail views, search, and CRUD forms used daily by bookkeepers",
      "priority": "high",
      "dependencies": ["data-models"],
      "target_audience": "end_user",
      "user_stories": ["US-013: As a bookkeeper, I want to search and manage customer records"],
      "acceptance_criteria": [
        "Customer list with search and filtering in main sidebar",
        "CRUD forms with validation",
        "Permission-gated but accessible to all bookkeepers"
      ],
      "estimated_complexity": "large",
      "spec_references": ["Functional Spec Section 5: Customer Management"],
      "design_references": [
        {
          "screen_id": "customer-list",
          "screen_name": "Customer list",
          "surface": "management-centre",
          "theme": "light",
          "readme_section": "Management Centre > Customers > List view",
          "prototype_file": "specs/design_handoff_<project>/src/screens-admin.jsx",
          "prototype_component": "ScreenCustomerList"
        }
      ],
      "design_screens": [
        "### Screen — Customer list\n\n**Layout (top → bottom):**\n\n1. ... [verbatim screen spec block copied from the handoff README] ..."
      ]
    },
    {
      "id": "chart-of-accounts",
      "name": "Chart of Accounts Configuration",
      "description": "Admin CRUD for managing the chart of accounts, account types, and tax categories",
      "priority": "high",
      "dependencies": ["data-models"],
      "target_audience": "admin",
      "user_stories": ["US-014: As an admin, I want to configure the chart of accounts"],
      "acceptance_criteria": [
        "Account CRUD in admin hub",
        "Account type and tax category management",
        "Only accessible to users with accounting:admin permission"
      ],
      "estimated_complexity": "medium",
      "spec_references": ["Functional Spec Section 13: Data Requirements"]
    },
    {
      "id": "design-polish",
      "name": "Design Polish & Consistency Pass",
      "description": "Cross-cutting audit and polish pass across every UI module. Verifies token discipline, typography scale, shape-language utilities, reserved-token usage, and cross-screen pattern consistency against ai_docs/frontend/context/design_system.md. Fixes divergences in place; does not add new features or routes.",
      "priority": "low",
      "dependencies": ["customer-management", "chart-of-accounts", "transaction-management", "invoicing", "banking-integration", "reports", "dashboard"],
      "target_audience": "backend_only",
      "user_stories": [
        "As a user, every screen of the application uses the same brand palette, type scale, spacing rhythm, and shape language so the product feels like a single coherent surface."
      ],
      "acceptance_criteria": [
        "Every hardcoded color, font-size, radius, and shadow outside the token system in app/frontend/src/ is replaced with a token reference from ai_docs/frontend/context/design_system.md, or justified inline with a comment when intentionally bespoke.",
        "Reserved tokens called out in the design system appear only in their reserved contexts.",
        "Shape-language utilities are applied consistently across all UI modules.",
        "Typography scale is honored — no off-scale font-size values.",
        "Cross-screen patterns (buttons, dialogs, modals, toasts, form fields, empty states) look identical across modules.",
        "Dark/light theme handling is consistent across every theme-aware screen."
      ],
      "estimated_complexity": "medium",
      "spec_references": [
        "ai_docs/frontend/baseline_context.md (Brand Design System section)",
        "ai_docs/frontend/context/design_system.md (full token reference and screen catalog)"
      ]
    }
  ],
  "execution_order": [
    "auth-core",
    "chart-of-accounts",
    "customer-management",
    "transaction-management",
    "invoicing",
    "banking-integration",
    "reports",
    "dashboard",
    "design-polish"
  ],
  "notes": [
    "Banking integration requires FNB API credentials",
    "SARS compliance features should be validated by accountant"
  ]
}
```

### User Persona Schema

Each persona in `user_personas` must include:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Kebab-case identifier (e.g., `field-worker`, `reviewer`) |
| `name` | string | Human-readable name |
| `description` | string | What this persona does, their primary workflow |
| `is_default` | boolean | `true` if every new user starts as this type (only one default allowed) |
| `requires_onboarding` | boolean | `true` if the user must complete onboarding steps before accessing features |
| `requires_manual_review` | boolean | `true` if an admin must approve the user after onboarding |
| `onboarding_fields` | string[] | Fields collected during onboarding (e.g., `["license_number", "region"]`) |
| `suggested_role` | string | Role to create with this persona's default permissions |
| `permissions` | string[] | Permission codes in `resource:action` format |
| `navigation_zone` | string | Where this persona's pages live: `end_user`, `admin`, `platform_admin` |
| `notes` | string | Implementation notes (e.g., "Sees simplified dashboard") |

**Rules:**
- If the spec describes only one type of user, return an **empty array** `[]` — the default "member" role is sufficient
- The `permissions` list should only include permissions for **new feature areas** introduced by this project — don't re-list standard permissions (users, roles, etc.)
- `suggested_role` should be a new role name if the persona needs different permissions than existing roles
- If two personas share the same role, they can reference the same `suggested_role`

### Module ID Conventions

Use lowercase kebab-case IDs that clearly describe the module:
- `auth-core` - Authentication core
- `customer-mgmt` - Customer management
- `invoice-crud` - Invoice create/read/update/delete
- `banking-fnb` - FNB banking integration
- `reports-financial` - Financial reports
- `tax-sars` - SARS tax compliance

### User Story Mapping

For each module, include:
- The most relevant user stories (up to 10)
- Format: "US-XXX: Brief description"
- If there are more than 10, include the most important and note "... and X more"

### Acceptance Criteria Extraction

For each module, extract:
- 3-8 high-level acceptance criteria
- Derived from spec requirements and user story acceptance criteria
- Should be testable/verifiable

## Specification Content

**IMPORTANT**: Read the specification content from the file at `{spec_content_file}` using the Read tool before proceeding. This file contains all the specification documents to analyze.

## Output

Write the JSON response to the file: `{output_file}`

Use the Write tool to create this file. The file must contain valid JSON matching the schema above — no markdown, no code blocks, no surrounding text. Raw JSON only.
