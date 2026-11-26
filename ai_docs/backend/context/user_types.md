# User Types, Roles & Onboarding

## Overview

This application supports **two complementary systems** for access control:

- **Roles** — Permission levels within the same workflow (viewer, member, manager, admin, owner). Control what a user *can do*.
- **User Types** — Fundamentally different user categories with distinct workflows, onboarding, and UI. Define what a user *is*.

**When to create a new Role:** The user does the same job but needs more/fewer permissions (e.g., a "manager" who can approve things a "member" cannot).

**When to create a new User Type:** The user has a fundamentally different workflow, may need specialized onboarding (credential verification, license upload), and sees different primary interfaces (e.g., a field worker vs a back-office coordinator).

## Data Models

### UserType (Global)

Defines a category of user across the entire platform.

| Field | Type | Purpose |
|-------|------|---------|
| `name` | String(100) | Display name |
| `code` | String(50) | Unique identifier (e.g., `field_worker`) |
| `is_active` | Boolean | Soft-enable/disable |
| `requires_onboarding` | Boolean | Must complete onboarding steps before gaining permissions |
| `requires_manual_review` | Boolean | Admin must approve after onboarding submission |
| `is_default` | Boolean | Auto-assigned to new users on registration (only one) |
| `display_order` | Integer | UI ordering |

### OnboardingStep (Global, per UserType)

Defines a step in the onboarding wizard for a user type.

| Field | Type | Purpose |
|-------|------|---------|
| `user_type_id` | FK(UserType) | Parent user type |
| `name` | String(100) | Step display name |
| `code` | String(50) | Unique within user type |
| `step_order` | Integer | Display/execution order |
| `required_fields` | JSON | Field definitions (see schema below) |
| `validation_rules` | JSON | Optional validation logic |
| `requires_verification` | Boolean | Step needs admin verification |
| `is_active` | Boolean | Soft-enable/disable |

**`required_fields` JSON schema:**
```json
[
  {
    "name": "license_number",
    "type": "string",
    "label": "License Number",
    "required": true
  },
  {
    "name": "region",
    "type": "select",
    "label": "Operating Region",
    "required": true,
    "options": ["North", "South", "East", "West"]
  }
]
```

Supported field types: `string`, `number`, `date`, `select`, `boolean`, `file`

### UserUserType (Org-scoped junction)

Links a user to a user type within an organization. **Always filter by `organization_id`.**

| Field | Type | Purpose |
|-------|------|---------|
| `organization_id` | FK | Tenant scope |
| `user_id` | FK | The user |
| `user_type_id` | FK | The user type |
| `onboarding_status` | Enum | Current status (see below) |
| `onboarded_at` | DateTime | When onboarding completed |
| `expires_at` | DateTime | Optional expiration |
| `requires_admin_attention` | Boolean | Flagged for admin review |

**Onboarding Status Flow:**
```
PENDING → IN_PROGRESS → PENDING_REVIEW → APPROVED
                                       → CHANGE_REQUESTED → IN_PROGRESS (resubmit)
                                       → REJECTED
                       → APPROVED (if no manual review needed)
APPROVED → EXPIRED (if expires_at passes)
```

### UserOnboardingProgress (Org-scoped)

Tracks per-step completion. **Always filter by `organization_id`.**

| Field | Type | Purpose |
|-------|------|---------|
| `organization_id` | FK | Tenant scope |
| `user_id` | FK | The user |
| `user_user_type_id` | FK | The junction record |
| `onboarding_step_id` | FK | The step |
| `submitted_data` | JSON | User's input for this step |
| `completed_time` | DateTime | When step was completed |

### UserTypePermission (Global)

Grants permissions to a user type. **Permissions are only active when the user's `UserUserType.onboarding_status` is `APPROVED` and not expired.**

## Permission Resolution

The permission check follows this order:

1. **Super admin** (`is_admin=True`) — bypasses all checks
2. **Redis cache** — returns cached permissions if available
3. **Role permissions** — from user's assigned roles via `UserRole`
4. **User type permissions** — from user's approved, non-expired `UserUserType` records via `UserTypePermission`

User type permissions are **additive** — they grant additional permissions on top of role permissions.

## Seed Data Pattern

New user types, roles, onboarding steps, and permissions should be added to seed data files:

| What | File | Format |
|------|------|--------|
| User types | `scripts/seed_data/user_types.yaml` | YAML list |
| Onboarding steps | `scripts/seed_data/onboarding_steps.yaml` | YAML list (references user type by code) |
| Permissions | `scripts/seed_data/permissions.yaml` | YAML list |
| Role-permission mappings | `scripts/seed_data/role_permissions.yaml` | YAML (role → permission codes) |

The seeding script (`scripts/seed_first_tenant.py`) handles idempotent upserts — it creates records if they don't exist and updates them if they do.

## Implementation Checklist

When adding a new user type:

1. **Define the UserType** in `user_types.yaml` — set `requires_onboarding` and `requires_manual_review`
2. **Define OnboardingSteps** in `onboarding_steps.yaml` — each step with `required_fields` JSON
3. **Define new Permissions** in `permissions.yaml` — `resource:action` format for the persona's feature areas
4. **Create a Role** for the persona (or reuse existing) — map permissions in `role_permissions.yaml`
5. **Optionally assign UserTypePermissions** if the persona needs permissions gated behind onboarding approval (beyond what their role grants)
6. **Run seed migration** — `python scripts/seed_first_tenant.py`
7. **Frontend: Gate features** — Use `PermissionGate` or `usePermissions` hook to show/hide UI based on the persona's permissions
8. **Frontend: Navigation placement** — Persona's daily-use pages go in main sidebar, admin config goes in admin hub (see `navigation.md`)

## API Endpoints

### User Types (`/api/v1/user-types`)

| Method | Endpoint | Access |
|--------|----------|--------|
| GET | `/` | `user_types:read` |
| GET | `/{id}` | `user_types:read` |
| POST | `/` | Super admin |
| PUT | `/{id}` | Super admin |
| DELETE | `/{id}` | Super admin |

### Onboarding (`/api/v1/onboarding`)

| Method | Endpoint | Access |
|--------|----------|--------|
| GET | `/status` | Authenticated user (own status) |
| GET | `/steps` | Authenticated user (own steps) |
| POST | `/steps/{step_id}/submit` | Authenticated user (own submission) |
| GET | `/admin/pending` | `onboarding:review` |
| POST | `/admin/{user_user_type_id}/approve` | `onboarding:review` |
| POST | `/admin/{user_user_type_id}/reject` | `onboarding:review` |
| POST | `/admin/{user_user_type_id}/request-changes` | `onboarding:review` |

## Related Files

- **Models**: `src/models/{user_type,onboarding_step,user_user_type,user_onboarding_progress,user_type_permission}.py`
- **CRUD**: `src/crud/{user_type,onboarding,user_user_type}.py`
- **API**: `src/api/{user_type,onboarding}.py`
- **Seed Data**: `scripts/seed_data/{user_types,onboarding_steps,permissions,role_permissions}.yaml`
- **Seeding Script**: `scripts/seed_first_tenant.py`
