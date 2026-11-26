# Super Admin User Impersonation (Backend)

Super admins (`is_admin=True`) can impersonate non-admin users with verified email in active organizations. Cannot impersonate self or other admins.

## Key Files

| File | Purpose |
|------|---------|
| `src/api/impersonation.py` | API endpoints (admin + user routers) |
| `src/services/impersonation.py` | Business logic |
| `src/models/impersonation_session.py` | Session model |
| `src/crud/impersonation_session.py` | CRUD operations |
| `src/core/security.py` | `create_impersonation_token()` |

## API Endpoints

**GOTCHA**: Static routes (`/end`, `/session`, `/history`, `/resume`) MUST be defined before `/{user_id}` to prevent FastAPI matching "end" as user_id.

Admin routes (`/api/v1/admin/impersonate/`):
| Endpoint | Auth | Purpose |
|----------|------|---------|
| `POST /{user_id}` | Super admin | Start impersonation (auto-ends existing session first) |
| `POST /end` | Impersonation token | End session, returns admin token |
| `GET /session` | Any auth | Returns `{active: false}` or session details |
| `GET /history` | Super admin | Paginated session history with filters |
| `POST /resume` | Super admin (not impersonating) | Re-issue token for active session after page refresh |

User routes (`/api/v1/impersonate/`):
| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /my-history` | User (not impersonating) | User sees when they were impersonated (completed sessions only) |

### Endpoint Behaviors

**Auto-end on start**: When starting a new impersonation, any existing active session for that admin is automatically ended. Handles orphaned sessions from logout/browser close.

**/my-history restrictions**: Blocked during active impersonation (403) to prevent admins from viewing other admins' impersonation history of the target user. Only returns completed sessions (where `ended_time` is set).

**/resume flow**: After page refresh, `/auth/refresh` returns admin token (from cookie). Frontend calls `/resume` to get fresh impersonation token if session still active.

## Token Claims

```json
{
  "user_id": "target-uuid",
  "organization_id": "target-org-uuid",
  "impersonator_id": "admin-uuid",
  "impersonation_session_id": "session-uuid",
  "type": "impersonation",
  "exp": 1234567890
}
```

`get_current_user` sets `is_impersonating`, `impersonator_id`, `impersonation_session_id` on CurrentUser.

## Validations

`start_impersonation()` checks:
1. Impersonator is super admin
2. Target exists and not soft-deleted
3. Not impersonating self or another admin
4. Target has verified email
5. Target's organization is active

## Security

| Rule | Detail |
|------|--------|
| Token isolation | Impersonation tokens separate from admin tokens |
| Short expiry | 1 hour default (`IMPERSONATION_TOKEN_EXPIRE_SECONDS`) |
| No refresh | Impersonation tokens cannot be refreshed via `/auth/refresh` |
| Session validation | Server validates session not ended on each request (see below) |
| Audit trail | `IMPERSONATE_START`/`IMPERSONATE_END` logged with impersonator as actor |
| Session recovery | Admin cookie persists; `/resume` re-issues impersonation token |

### Session Validation (deps.py)

On every authenticated request with an impersonation token, `get_current_user` validates the session is still active in the database. If the session has been ended (by another tab, admin action, or auto-end), returns **401 Unauthorized** with `"Impersonation session has ended"` even though the JWT itself is still valid.

This prevents continued access after:
- Admin manually ends session via `/end`
- Auto-end triggered by starting a new impersonation
- Admin-initiated session termination

## Audit Logging

Both `IMPERSONATE_START` and `IMPERSONATE_END` log to audit with:
- **actor_id**: Impersonator's user ID (not target)
- **organization_id**: Target user's organization
- **resource_type**: `ImpersonationSession`
- **resource_id**: Session UUID
- **ip_address**: Request IP
- **user_agent**: Browser/client info
- **changes**: Start logs `target_user_id` and `target_organization_id`; End logs `duration_seconds` and `ended_time`

## Caching

- JWT claims cached in Redis with token as key (target user's claims)
- User permissions cached at `user_perms:{org_id}:{user_id}` (target user's key)
