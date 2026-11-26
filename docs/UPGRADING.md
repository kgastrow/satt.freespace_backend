# Upgrading a live deployment

Read this before running `app/backend/deploy/deploy.sh`.

`deploy.sh` is not a dry run. Under `set -e` (line 5) it, in order:

1. rsyncs the new code to `/opt/ayzer-webapp/backend`,
2. installs dependencies,
3. runs **`alembic upgrade head`** (line 61),
4. copies `app/backend/deploy/ayzer-webapp-api.service` and `app/backend/deploy/ayzer-webapp-worker.service`
   into `/etc/systemd/system/`, `daemon-reload`s and **restarts both services**
   (lines 71-78).

So several of the changes below apply themselves whether or not anyone read
about them. One of them (§1) changes security-relevant behaviour with no error
of any kind, and one of them (§2) will abort the deploy half-way — after the new
code is on disk but before the services restart, leaving the old process running
against new files.

Items are ordered by how quickly and how badly they bite.

---

## 1. `--forwarded-allow-ips` is narrowed, and `trusted_client_ip_header` now matters

**Silent. No error, no log line at the point of failure, and it collapses your
rate limiting and your account lockouts into a single global bucket.**

### What changed

`app/backend/deploy/ayzer-webapp-api.service` line 44 now pins:

```
--forwarded-allow-ips='127.0.0.1'
```

It used to be `'*'`. With `'*'`, uvicorn 0.34's `_TrustedHosts.always_trust`
short-circuits and takes the **leftmost, client-supplied** `X-Forwarded-For`
entry for *every* connection — a client could simply name its own IP. That is
why `'*'` is gone and must not come back.

Separately, `TRUSTED_CLIENT_IP_HEADER` (config.json: `server.trusted_client_ip_header`)
defaults to **empty** (`app/backend/src/core/config.py:144`).

### What breaks

deploy.sh installs the unit file automatically, so this applies on your next
deploy without being asked.

If your reverse proxy does **not** run on `127.0.0.1`, uvicorn stops believing
its `X-Forwarded-For` and `request.client.host` becomes the proxy's own address.
Every visitor then shares one identity, which means they share:

- the slowapi rate-limit bucket — `client_ip_key()` is the limiter's `key_func`
  (`src/core/rate_limit.py:205`);
- the brute-force failure and block keys `brute_force:failures:{ip}` and
  `brute_force:blocked:{ip}` (`src/services/brute_force_detector.py:109,113`).

Consequence: five failed logins anywhere on your platform block *everyone* for
15 minutes (`DEFAULT_BLOCK_DURATION_SECONDS = 900`), and one busy tenant
exhausts the rate limit for all of them. Audit records also attribute every
action to the proxy.

### How it is signalled

Barely. There is a good explanatory comment inside the unit file
(`app/backend/deploy/ayzer-webapp-api.service`, lines 14-36) — which deploy.sh copies over the top
of your edited copy — and a one-shot startup `WARNING` from
`src/core/client_ip.py:83-91`:

> TRUSTED_CLIENT_IP_HEADER is not configured. Client IPs used for audit records
> and for the login/2FA lockout fall back to the connection peer address...

It is a warning, **not** a refusal. The only hard refusal at boot
(`_validate_trusted_client_ip_header`, `main.py:39`, called at `main.py:122`) is
for an append-only header — `x-forwarded-for`, `forwarded`, `x-forwarded`
(`client_ip.py:70`) — which the app will not start with.

### Action required

Pick the case that matches you, **before** deploying.

**Proxy on the same host (nginx on localhost):** nothing to do. `'127.0.0.1'` is
correct.

**Proxy or load balancer on another host:** edit `app/backend/deploy/ayzer-webapp-api.service`
in your fork (deploy.sh copies your repo's copy, so keep the edit in the repo,
not on the server) and name that host or CIDR:

```
--forwarded-allow-ips='10.0.0.5,10.0.1.0/24'
```

**Behind a CDN (Cloudflare, CloudFront, Fastly):** do **not** widen to `'*'`.
Set the header your edge overwrites, in `config.json`:

```json
{ "server": { "trusted_client_ip_header": "CF-Connecting-IP" } }
```

or the `TRUSTED_CLIENT_IP_HEADER` env var. Then lock the origin so only the edge
can reach it. Any header you name here must be one your edge *overwrites*; an
append-only header is refused at boot.

**Verify after deploying:** confirm a request's recorded IP is the visitor's, not
the proxy's, in the audit log or request log for a known client.

Also note the legacy unit at `app/backend/initscripts/ayzer_backend.service`
(gunicorn, `127.0.0.1:8085`, no `--forwarded-allow-ips`). deploy.sh does not
install it. Do not use it.

---

## 2. New enum CHECK constraints can abort `alembic upgrade head`

**This stops the deploy dead, part-way.**

### What changed

Migration `bc0c12077ba3_widen_and_constrain_non_native_enum_.py` widens five
non-native enum columns to `VARCHAR(50)` and adds a CHECK constraint to each:

| Table.column | Constraint | Allowed values |
| --- | --- | --- |
| `user.created_via` | `ck_user_created_via` | `EMAIL`, `GOOGLE` |
| `user.suspension_status` | `ck_user_suspension_status` | `ACTIVE`, `SUSPENDED` |
| `data_deletion_request.status` | `ck_data_deletion_request_status` | `PENDING`, `SCHEDULED`, `COMPLETED`, `CANCELLED` |
| `data_export_request.status` | `ck_data_export_request_status` | `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`, `EXPIRED` |
| `file.media_use` | `ck_file_media_use` | `AVATAR`, `ANNOUNCEMENT`, `HELP_ARTICLE`, `OTHER` |

Stored values are the **uppercase Python member names**, not the lowercase enum
values.

### What breaks

`user.created_via` is the trap. `src/models/user.py:36-43` literally invites you
to add providers:

```python
class CreatedVia(str, enum.Enum):
    EMAIL = "email"
    GOOGLE = "google"
    # Future providers can be added here
    # MICROSOFT = "microsoft"
    # GITHUB = "github"
```

If a fork uncommented those and has `MICROSOFT` or `GITHUB` rows, PostgreSQL
validates the new CHECK against every existing row and fails with SQLSTATE
**23514**:

```
check constraint "ck_user_created_via" of relation "user" is violated by some row
```

The migration runs inside Alembic's transaction, so it rolls back whole:
`alembic_version` is not advanced and `alembic upgrade head` exits non-zero.
Under `set -e`, deploy.sh aborts at line 61 — after the new code is on disk,
before the units are copied and the services restarted.

### Action required

**Extend the allowed set FIRST, then deploy.** In your fork, before deploying:

1. Uncomment the members you actually use in `src/models/user.py`.
2. Edit the enum list in the migration (`bc0c12077ba3`, `user.created_via` block
   at lines 119-133) so the CHECK it creates includes them.

Pre-flight query to see whether you are affected:

```sql
SELECT created_via, count(*) FROM "user" GROUP BY 1;
SELECT suspension_status, count(*) FROM "user" GROUP BY 1;
SELECT status, count(*) FROM data_export_request GROUP BY 1;
SELECT status, count(*) FROM data_deletion_request GROUP BY 1;
SELECT media_use, count(*) FROM file GROUP BY 1;
```

Anything outside the tables above must be corrected or added to the constraint
before you run the migration.

**Downgrade hazard:** `downgrade()` restores the exact old widths
(`created_via` → `VARCHAR(6)`). Once a longer member such as `MICROSOFT` has been
written, downgrading past this revision fails on the `ALTER COLUMN ... TYPE`.
This is intentional; plan forward, not back.

---

## 3. SSO and account linking now hard-require Redis

### What changed

The single-use nonce guards used to fail **open**: with Redis absent the check
was skipped inside a `try/except` that only logged a warning, so an OAuth
`state` and an SSO link token stayed replayable for their whole TTL — precisely
during an incident or a failover, when replay protection matters most.

They now fail **closed**:

| Path | Status | `detail_code` |
| --- | --- | --- |
| `GET /sso/{provider}/callback` (`src/api/sso.py:74-90`) | 503 | `sso.state_verification_unavailable` |
| `POST /auth/sso/link` (`src/api/account_linking.py`) | 503 | `sso.link_verification_unavailable` |

Both fire when `cache_service._redis is None` *and* on a Redis transport error.

### What breaks

**Nobody can sign in via SSO, and nobody can complete an account link.** Password
login still works.

### The non-obvious trigger

It is not only "Redis is down". Setting **`cache.enabled: false`** in
`config.json` (env `CACHE_ENABLED=false`, `settings.CACHE_ENABLED`,
`src/core/config.py:211`) does it too: `CacheService.set_redis()` returns early
when disabled (`src/services/cache.py:46-61`), so `_redis` stays `None`
permanently even though Redis itself is running and reachable.

If you have ever switched caching off to debug something, SSO is off with it.

### Action required

- Ensure Redis is reachable from the API host and is part of your health checks.
- Confirm `cache.enabled` is `true` (or absent — it defaults to `true`).
- If you run SSO, treat Redis as a **hard** dependency, not a cache. Losing it is
  now a sign-in outage, not a slowdown.

---

## 4. `POST /auth/sso/link` requires a password or a bearer session — ship both halves together

### What changed

The link token used to be the entire proof. It only ever proved that *somebody*
completed an OAuth flow for an address matching an existing account, so anyone
able to create a provider account on a victim's email address got a full session
on the victim's account. The endpoint now additionally requires one of:

1. an `Authorization: Bearer` session for the **same** user in the **same**
   organization, or
2. the existing account's `password`, re-entered.

`ConfirmLinkRequest` (`src/serialisers/auth.py:128-152`) gained the optional
`password` field and keeps `model_config = ConfigDict(extra="forbid")`.

A rejected password now answers **403 `auth.invalid_password`** (it was 401), so
it is distinguishable from **401 `sso.link_proof_required`** ("you sent no
proof") by status alone. Password guesses are also brute-force limited per link
token, per target account and per IP; over the cap the endpoint answers **429**
`sso.link_attempts_exceeded` (or `auth.ip_blocked`). Hitting the cap refuses
further attempts — it does not burn the link token and does not lock the account
out of `/auth/login`.

### What breaks — in both directions

**New backend + old frontend:** the old client posts `{"link_token": "..."}` with
no password and no `Authorization` header → **401**, `detail_code`
`sso.link_proof_required`. (An old client that *is* signed in and sends a bearer
token still works.)

**New frontend + old backend:** the new SPA posts `{link_token, password}` on the
signed-out path. The old serialiser has no `password` field and `extra="forbid"`,
so Pydantic rejects the body before the handler runs → **422**, with
`detail[].type == "extra_forbidden"` and `loc == ["body", "password"]`.

### Action required

Deploy backend and frontend **together**. There is no compatible intermediate
state for the signed-out linking flow. If you must stage them, stage backend
first and accept that signed-out linking returns 401 until the SPA ships; a
frontend-first deploy produces a 422 that reads like a client bug.

Fork clients keying on status must now treat 403 (`auth.invalid_password`) and
429 (`sso.link_attempts_exceeded`, `auth.ip_blocked`) as expected outcomes of
this endpoint.

---

## 5. `scripts/seed_maintenance.py` is a new required step that nothing runs for you

### What changed

Reference data (roles, permissions, rate limits, user types, **notification
categories**, notification templates, cron jobs, system config) is now seeded by
a dedicated maintenance script rather than piggybacking on first-tenant seeding.

### What breaks

Nothing errors. Every reference-data fix in this release simply **stays dormant**
— including the notification categories in §9, without which the entire
notification preference layer is inert.

It is invoked by **nothing**: not `deploy.sh`, not the `Makefile`, not a cron
job. Only prose mentions it.

### Action required

Run it by hand after the deploy, from `app/backend` with the venv active:

```bash
python scripts/seed_maintenance.py --list      # see the steps first
python scripts/seed_maintenance.py --dry-run   # write, report, roll back
python scripts/seed_maintenance.py             # all steps
```

It connects with `settings.DATABASE_URL_DIRECT` (the direct URL, not PgBouncer).

**The `role_permissions` step is not purely additive.** Revoking a permission is
a soft delete, and the seeder's existence check matches only live rows — so a
grant an admin *deliberately* removed from a system role is silently restored.
The script prints a warning about this, but if you have hand-tuned system roles:

```bash
python scripts/seed_maintenance.py --skip role_permissions
```

`--only <steps>` and `--skip <steps>` both take comma-separated step names. An
unknown name exits 2 without writing anything.

---

## 6. ~68 newly registered `detail_code`s flip ~94 call sites from 500 to their intended 4xx/2xx

### What changed

`create_http_exception()` and `create_success_response()` call
`get_response_code()` **before** building their result, and `get_response_code()`
raises `KeyError` on an unregistered key. An unregistered `detail_code=`
therefore never produced the intended status: the `KeyError` escaped into the
surrounding `except Exception` handler and the caller got **500
`common.internal_error`** instead.

68 previously-missing codes are now registered in `src/core/response_codes.py`
(373 entries total), across 18-20 API modules — `auth`, `cron_job`,
`data_export`, `feedback`, `file`, `help_article`, `help_category`,
`help_center`, `help_faq`, `impersonation`, `notification_preferences`,
`onboarding_step`, `payments`, `request_logs`, `server`, `session`, `sso`,
`two_factor`, `user`, `user_type`.

A CI guard (`tests/unit_tests/test_response_code_registry.py`) now AST-scans
`src/` and fails if any `detail_code=` / `message_code=` literal is unregistered,
so this class of bug cannot come back.

### What breaks

Endpoints that reliably returned **500** now return 400 / 401 / 403 / 404 / 409 /
422 / 200 as intended. Any fork that keyed error handling, retries, alerting or
frontend copy on those 500s will stop matching. Error-rate dashboards will show
5xx dropping and 4xx rising — that is the fix landing, not a regression.

### Action required

Audit any client-side or monitoring logic that treats a 500 from these modules as
a known state. Move it onto `detail_code`, which is the actual contract. This is
coordinated work: budget for it rather than discovering it in an alert.

---

## 7. `PUBLIC_URL` is deprecated in favour of two keys

Well signalled already — see **[docs/public-url-split.md](./public-url-split.md)**
for the full mapping and recipes.

Summary:

| Setting | config.json key | Default | Meaning |
| --- | --- | --- | --- |
| `PUBLIC_URL_FRONTEND` | `public_url_frontend` | `http://localhost:5173` | Origin serving the SPA bundle |
| `PUBLIC_URL_BACKEND` | `public_url_backend` | `http://localhost:8000` | Origin serving this API under `/api/v1` |

The rule of thumb from that document: the **frontend** origin is used by
everything a person clicks (password reset, invitation, unsubscribe pages, the
SSO `redirect_uri` fallback); the **backend** origin by everything a machine
calls or signs (Twilio `sms-status` webhook signature reconstruction, the RFC
8058 one-click unsubscribe POST target, file serve/upload URLs). Unsubscribe uses
both.

`public_url` still works: if it is set and neither new key is, it back-fills both
and logs a startup warning. deploy.sh greps your `config.json` and prints the
same deprecation notice (lines 48-56). `PUBLIC_URL` always resolves to
`PUBLIC_URL_BACKEND` — do not read it in new code.

**Action required:** set both keys explicitly. When the two origins differ, the
frontend origin must also appear in `cors.allowed_origins`. Note that
`.ports.env`'s `BACKEND_PORT` rewrites the port in `public_url_backend` and
`public_url` only, never `public_url_frontend`.

---

## 8. Email no longer silently downgrades to platform SMTP

### What changed

Three doors used to quietly substitute the platform's SMTP provider and sender
for the provider an organization had actually configured — and record the result
as `status="sent"`:

1. Org selected SendGrid but the API key is missing or undecryptable
   (`src/services/notifications/dispatcher.py:515-527`) — now logs
   *"Refusing to downgrade to SMTP."* and returns `None`.
2. No organization email configuration at all
   (`src/services/notifications/email_provider.py:88-101`) — now returns a
   failed `NotificationResult` rather than falling through to the process-global
   `config.json` SMTP singleton.
3. The error path (`dispatcher.py:543-555`) — used to build a platform-SMTP
   provider from global config and return it, reaching the same substitution the
   SendGrid branch already refused.

### What breaks

A bad SendGrid key, or a missing org email config, now records a
`Notification` row with **`status = "failed"`** (`src/models/notification.py:82`;
plain string, no enum — the set is `pending`, `sent`, `failed`, `skipped`) and an
`error_message`, and increments the `failed` delivery metric. Previously the mail
went out from the *platform's* sender and was recorded as `sent` with
`provider="smtp"`.

So: mail that appeared to work may stop. Loudly, in the notification table — but
it is a behaviour change, not an outage of the sending path.

### Action required

Before deploying, verify every organization that sends email has a valid provider
configuration and a decryptable SendGrid key. After deploying, query for
`status = 'failed'` notifications and fix the configs they name.

---

## 9. Notification categories are now seeded — this both suppresses and bypasses

### What changed

Four system categories (`organization_id IS NULL`) are seeded by the
`notification_categories` step of `seed_maintenance.py` (§5):

| code | name | `user_configurable` |
| --- | --- | --- |
| `account` | Account & Security | **false** (mandatory) |
| `phone_verification` | Phone Verification | **false** (mandatory) |
| `onboarding` | Onboarding | true |
| `marketing` | Marketing & Updates | true — this is the unsubscribe target |

`PreferenceChecker.check_can_send()`
(`src/services/notifications/preference_checker.py:54`) evaluates strictly in
this order:

1. **mandatory short-circuit** — a category with `user_configurable = false`
   returns `allowed=True` immediately;
2. organization channel enabled?
3. user's global channel preference;
4. user's per-category opt-out;
5. quiet hours (skipped when `is_urgent=True`).

Before seeding, `_get_category()` found no row, `_get_user_category_preference()`
returned `None`, and **no opt-out was enforceable at all**.

### What breaks — in two opposite directions

**Suppression.** User opt-outs that have been accumulating in
`UserCategoryPreference` and doing nothing now take effect. Send volume for
`marketing` and `onboarding` can drop sharply the moment the seeder runs. That is
correct behaviour finally working; it will still look like a regression on a
delivery graph.

**Bypass.** `account` and `phone_verification` are mandatory, so they
short-circuit **before** quiet hours as well as before opt-outs. Security and
verification messages will now arrive at 3am. That is deliberate — a
password-reset or OTP message must not be held by a quiet-hours window — but say
so in your release notes if your users expect otherwise.

`is_urgent=True` bypasses quiet hours only, never opt-outs.

### Action required

Run `seed_maintenance.py` (§5) knowingly, ideally outside a send window, and
expect both effects on the same day.

---

## 10. Bulk sends now honour recipient filters and verify per channel

### What changed

`BulkProcessor.get_recipients()` and `count_recipients()` now share a single
`_build_recipient_conditions(org_id, filters, channel)`, so the count and the
actual send can no longer diverge, and the recipient filters are genuinely
applied.

Verification is per channel rather than always-email
(`src/services/notifications/bulk_processor.py:36-50`):

```python
CHANNEL_VERIFICATION_COLUMN = {
    "email":    User.email_verified,
    "sms":      User.phone_verified,
    "whatsapp": User.phone_verified,
}
CHANNELS_WITHOUT_VERIFIABLE_CONTACT = frozenset({"in_app"})
```

The filter field is now **`verified_contact_only`** (`RecipientFilter`,
`src/serialisers/notification.py:115-127`, default `true`).
**`email_verified_only`** is accepted as a deprecated alias: because
`RecipientFilter` sets `extra="forbid"`, rejecting it outright would 422 payloads
that worked yesterday, so a `model_validator(mode="before")` translates it and
logs a warning. The new key wins when both are present.

Other legacy aliases still translated: `specific_user_ids` → `user_ids`; `role`
filters by a single role **name**. `exclude_user_ids` is applied last and always
wins. `all_users: false` with no positive selector selects **nobody**.

### What breaks

Audiences shrink. A bulk that previously reached everyone because the filters
were not applied now reaches only the filtered, channel-verified set. An SMS
bulk is now gated on `phone_verified` rather than `email_verified`, which for
most tenants is a much smaller set.

An unknown channel applies no verification filter at all and logs a warning
(deliberately permissive).

### Action required

Re-check saved bulk definitions and any integration that posts recipient filters.
Migrate `email_verified_only` → `verified_contact_only`; the alias works but logs
a deprecation warning on every call. Use the recipient **count** endpoint before
a large send — it is now truthful.

---

## 11. `BulkProcessor.get_recipients()` / `count_recipients()` gained a required `channel` argument

Purely a fork-code break, but an immediate one.

```python
async def get_recipients(self, session, org_id, filters, channel,
                         limit=100, offset=0) -> list[User]: ...

async def count_recipients(self, session, org_id, filters, channel) -> int: ...
```

`channel` is required and deliberately **not** defaulted — the audience genuinely
depends on it, and a forgotten argument must be a type error rather than a silent
fallback to email semantics. It is also positioned before the defaulted
parameters, so positional callers break too.

**What breaks:** any fork script or service calling these raises

```
TypeError: get_recipients() missing 1 required positional argument: 'channel'
```

**Action required:** grep your fork for `get_recipients(` and `count_recipients(`
and pass the bulk's channel (`bulk_notification.channel` / `request.channel`).

---

## 12. Public Help Center routes serve platform-wide content only

### What changed

The unauthenticated Help Center endpoints passed `organization_id=None` with a
comment claiming "platform-wide content only" — but in the CRUD layer
`organization_id=None` meant **no filter at all**, so anonymous callers received
every tenant's published articles and FAQs.

A third explicit scope, `platform_only: bool`, now exists
(`src/crud/help_center.py:31-76`):

- `platform_only=True` → `organization_id IS NULL` only — the public endpoints;
- `organization_id=<uuid>` → that org's rows **plus** platform-wide;
- both `None`/`False` → unfiltered, the super-admin cross-org view.

Combining `platform_only=True` with an `organization_id` raises `ValueError`.

Public routes now passing `platform_only=True`: `GET /articles`,
`GET /articles/{slug}`, `GET /faqs`, `GET /search` (articles and FAQs).
`GET /admin/articles` and `GET /admin/faqs` are explicitly pinned to
`platform_only=False`.

### What breaks

**"Platform-wide" means the row's `organization_id` column is NULL. Nothing
else.** A fork whose public help content was authored inside an organization now
returns nothing on the public routes — and there is **no backfill migration**.

The previous behaviour was a cross-tenant disclosure, so this is not optional.

### Action required

Decide per article. To make content genuinely public:

```sql
UPDATE help_article SET organization_id = NULL WHERE id = '...';
UPDATE help_faq     SET organization_id = NULL WHERE id = '...';
```

Content that should stay tenant-scoped needs no change — it remains visible to
authenticated members of that organization.

---

## 13. `make seed` is now additive, not a reset

### What changed

`scripts/seed_first_tenant.py` no longer offers to clear the database. The
destructive branch is not merely defaulted off, it is **unreachable** without the
new `--force-clear` flag — the confirmation prompt is never even shown, so a
plain run cannot destroy anything no matter what is typed or piped at it.

With `--force-clear` there are three gates: the flag itself, an interactive TTY
(a piped/non-TTY run exits 2), and typing the target database name back
(a mismatch exits 2). Only then does it `TRUNCATE ... CASCADE` every table except
`alembic_version`.

`make seed` runs `python scripts/seed_first_tenant.py` with no flags, so it is
now purely additive.

### What breaks

Any workflow — a Makefile target, a CI job, a developer habit — that relied on
`make seed` giving a clean database. It will now seed on top of whatever is
already there.

### Action required

For a deliberate local reset:

```bash
python scripts/seed_first_tenant.py --force-clear   # interactive terminal required
```

There is no `make seed-maintenance` target; `seed_maintenance.py` (§5) must be
invoked directly.

---

## Suggested order of operations

1. **Before deploying:** run the §2 pre-flight queries; extend the `created_via`
   enum and its CHECK if you use extra providers.
2. **Before deploying:** set `--forwarded-allow-ips` and/or
   `trusted_client_ip_header` for your topology (§1); set
   `public_url_frontend` / `public_url_backend` (§7); confirm `cache.enabled` is
   true and Redis is healthy (§3); verify per-org email configs (§8).
3. **Deploy backend and frontend together** (§4).
4. **After deploying:** run `python scripts/seed_maintenance.py --dry-run`, then
   for real, with `--skip role_permissions` if you have hand-tuned system roles
   (§5, §9).
5. **Verify:** a request's recorded client IP is the visitor's (§1); SSO sign-in
   and account linking work (§3, §4); a notification send records `sent` not
   `failed` (§8); public Help Center routes still return the content you expect
   (§12).
6. **Then:** work through the 500 → 4xx migration in your clients and monitoring
   (§6), the bulk recipient filter changes (§10, §11).
