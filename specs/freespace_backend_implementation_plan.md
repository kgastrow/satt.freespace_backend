# Freespace Backend — Implementation Plan

Plan for implementing `specs/BACKEND_FUNCTIONAL_DESCRIPTION.md` (rev 0.2) on this template.
Written 2026-11-26. Requirement ids (BF-x, BN-x, AT-x, BT-x) refer to that document.

Each module in §4 is sized to become one ADW issue (`/feature` or `/plan_multi_phase`). This document fixes the design decisions those issues share, so the per-module plans do not each re-decide them.

---

## 1. What the template gives us, and what it does not

| Need | Template state | Consequence |
|---|---|---|
| Customer → organization, users, roles, permissions, audit log | Present | Reuse. |
| Back-office web app | Present (React admin area, `config/adminNav.ts`, `config/routes.ts`) | Add a "Sites" section. No charting library is installed. |
| Machine API keys | `ApiKey` exists but is bound to org + user, uses `X-API-Key`, bcrypt per request, looks up by 8-char prefix with `.first()`, has no revoke timestamp or last IP, and no endpoint uses it | Do not reuse. New `ingest_key` table (D3). |
| Rate limits | slowapi per IP, default 100/min on every route, 429 body `{"error": ...}` with no `Retry-After` | Fine for app endpoints. Ingest needs its own limiter (D4). |
| URL prefix | Everything is mounted at `/api/v1` (`main.py:670`) | The wire contract is `/v1/...`. Needs a second mount (D1). |
| Scheduled jobs | ARQ worker (single process), DB-driven cron with 1-minute tick, jobs run sequentially, no locking | Daily purge fits. The engine tick must be a hardcoded ARQ cron (D7). |
| Locks | None anywhere. PgBouncer runs in transaction mode, so session-level advisory locks do not work | Per-site lock must be transaction-scoped (D6). |
| Clock | None. `datetime.now(timezone.utc)` inline in ~358 places, no freezegun | New injectable clock for all Freespace code (D8). |
| FCM | Nothing. Web push is VAPID browser push only. `httpx` present without HTTP/2 | New FCM HTTP v1 client; add `google-auth`, `httpx[http2]` (D10). |
| Request logs | Raw `request.url.path` is logged to file and DB; exclusion is exact-match only; `fcmToken` is masked but keeps its first 4 characters | `deviceId` would leak. Middleware change required (D5). |
| Request-log retention | Handler reads `parameters.retention_days`, not the SystemConfig key (needs verification) | Fix while wiring BF-73. |
| Health | `/health` checks nothing | Extend (BF-80). |
| Backups | None | New script (BF-83). |
| Tests | In-memory SQLite, fakeredis, ARQ enqueue mocked | Postgres-only behaviour (row locks, BT-01, BT-02) needs Postgres-marked tests (D15). |
| Deployment settings | SystemConfig (global key/value, seeded from `scripts/seed_data/system_config.yaml`) and `config.json` | Runtime-tunable settings → SystemConfig. Startup flags and secrets paths → `config.json`. |

---

## 2. Design decisions

### D1. Two URL mounts
- Ingest and app endpoints are served at `/v1/...` exactly as the spec writes them. ParkIT's publisher is already built against `/v1/ingest/...`.
- A new aggregator `src/api/freespace_public/__init__.py` exposes `public_router`, mounted in `main.py` with `prefix="/v1"`.
- Admin endpoints are served at `/api/v1/admin/sites/...` through `v1_router`, because the frontend's base URL is `/api/v1` and all template auth/CSRF/cookie handling assumes it. This differs from the spec's `/v1/admin/...` (Q1).
- `deploy/nginx.conf` and `apache_site_config/freespace.conf` must proxy `/v1`.
- CLAUDE.md rule 9 (register routers in `src/api/v1/__init__.py`) applies to the admin routers. The `/v1` mount is a stated exception; add a line to CLAUDE.md when M0 lands.

### D2. Tenancy
- `site.organization_id` is the customer. Zones, snapshots, engine state, keys, templates, events and history all carry `organization_id` (denormalised from the site) so admin queries follow rule 1.
- `site.site_id` (slug) is **globally** unique, because ingest and app endpoints address a site by slug with no tenant context.
- Devices are not tenant data. One phone can select sites of several customers. `device` and `device_site` have no `organization_id`. Device statistics are computed per site and so remain tenant-scoped.
- Ingest and app endpoints resolve the site by key or slug, never by user. They are the only code paths that read tenant data without an `organization_id` filter; each is covered by a test that a key for site A cannot touch site B (BT-03).
- Back office: super admins see all customers. Other users see only their own organization's sites (Q2).

### D3. Keys
- `ingest_key`: `site_id`, `name`, `key_hash` (SHA-256, unique), `key_hint` (last 4), `expires_at`, `revoked_at`, `last_used_at`, `last_used_ip`, `created_by`. Key = `fsk_` + 43 base64url chars (256 bits). SHA-256 is sufficient because the key is high-entropy; bcrypt per request at 2 req/min/site is unnecessary and the lookup must be exact, not by prefix.
- Several valid keys per site is the normal state (BF-10b). "Rotate" in the UI = create new, then revoke old as a separate action.
- `app_key`: `name`, `key_hash`, `revoked_at`. Not tenant-scoped (deployment-wide, BF-9). Valid set cached in Redis for 60 s.
- Dependencies: `get_ingest_site` (reads `Authorization: Bearer`, returns site + key) and `require_app_key` (reads `X-Freespace-App-Key`).

### D4. Rate limits
- Ingest (BF-18): a dedicated Redis sliding-window limiter keyed by ingest key id, 12/min. The 429 carries `Retry-After` as an integer string clamped to 1–600. slowapi cannot produce that header today.
- App endpoints (BF-36): slowapi decorators per IP. Device `PUT`/`DELETE` add a second limit with a `key_func` on a hash of `deviceId`.
- Limits are `config.json` `rate_limit.*` values, as the template does.
- Client IP comes from `server.trusted_client_ip_header`. That setting must be configured for production, or every phone shares the proxy's IP.
- The template limiter fails open when Redis is down. Accepted.

### D5. Device privacy (BF-35, BF-73)
- The database never stores a raw `deviceId`. `device.device_key_hash` (SHA-256, unique) is the lookup key and `device.id_suffix` (last 6 characters) supports BF-74.
- `DELETE` nulls `fcm_token`, `device_key_hash` and `id_suffix`, removes the `device_site` rows and sets `deleted_time`. The remaining tombstone holds platform, app version and dates only.
- `RequestResponseLoggingMiddleware` logs the matched route template (`request.scope["route"].path`) instead of the raw path, and `sanitize_data` gets a full-mask list containing `fcmToken`.
- The reverse proxy access log must not record `/v1/devices/<id>`. Add a log format or `map` in nginx/Apache that rewrites that path segment.
- Verify the Prometheus middleware labels by route template, not raw path.
- A test greps log output and the `request_log` table for a known `deviceId` and token after a PUT.

### D6. One evaluator per site (BF-51)
- Evaluation runs in one transaction that begins with `SELECT ... FROM site_engine_state WHERE site_id = :id FOR UPDATE`. A row lock is transaction-scoped, so it works through PgBouncer in transaction mode. `pg_advisory_xact_lock` is the fallback if a lock is ever needed before the row exists.
- The engine-state row is created with the site, so the lock target always exists.
- All engine reads and writes happen inside that transaction.

### D7. Where evaluation and fan-out run
- **Evaluation is DB-only and runs inline.** The ingest handler stores the snapshot, evaluates under the site lock, writes events and the new engine state, and commits. The response (BF-15) then carries the real `state` and `recommendedZoneId`. Cost: one site, a handful of zones.
- **Fan-out is asynchronous.** An advisory event is committed with `fanout_status = PENDING`, then an ARQ job `fanout_advisory_task(event_id)` is enqueued. The response does not wait for it (BF-16).
- **Tick.** A hardcoded ARQ cron `engine_tick` (every minute, registered in `workers/worker.py` like `collect_metrics`) evaluates every site and re-enqueues any advisory whose fan-out is `PENDING` or `RUNNING` past a deadline. `TaskQueue.enqueue_job` swallows errors, so this recovery path is required, and it is also what satisfies BT-02.
- The tick is not a DB-driven cron job: those run sequentially inside one scheduler task, so a slow unrelated job would delay the engine.
- The tick covers unmanaged sites too. BF-50 says "every managed site", but BF-61 shadow mode needs timers to expire on unmanaged sites.
- The tick writes its timestamp to Redis for `/health` (BF-80).

### D8. Clock
- `src/services/freespace/clock.py`: a `Clock` with `now()`, a `SystemClock`, and a `FixedClock` for tests. Every Freespace service takes the clock or an explicit `now`. No `datetime.now()` in Freespace code; a test greps for it.
- Mock mode (BF-84) stores a clock offset in Redis so all API workers and the ARQ worker agree.

### D9. Engine shape
- A pure core with no I/O:
  - `availability.py`: staleness, zone status, ranking, sticky recommendation (BF-20 – BF-25).
  - `engine.py`: `evaluate(settings, zones, snapshot, state, now) -> (new_state, events, candidates)` (BF-52 – BF-57).
  - `templates.py`: placeholder validation, rendering, fingerprint (BF-57, BF-70).
- A thin shell loads rows, calls the core, persists. AT-01 – AT-08 run against the core with a `FixedClock`, then once more through the API.
- **Recommendation consistency (BF-24).** The engine persists the current recommendation. The availability endpoint calls the same function with the stored recommendation as its stickiness input and does not persist. A read can therefore null a recommendation that has gone stale since the last evaluation, but can never pick a different sticky winner than the engine would.

### D10. Push delivery
- `FcmClient`: `httpx.AsyncClient(http2=True)`, OAuth token from `google-auth` service-account credentials, cached until near expiry. One `messages:send` per token, semaphore of 20 (BF-64). Confirm during build that HTTP v1 has no multi-token endpoint.
- Fan-out works in chunks of 500 devices per ARQ job and re-enqueues itself, because the worker's `job_timeout` is 300 s and BF-66 allows 5 minutes of retries. Retries of 429/5xx are re-enqueued with `_defer_by`, not slept in-process.
- **At-most-once (BF-52).** For each device the job inserts a `push_send` row (unique on `event_id, device_id`) with outcome `PENDING` and commits *before* calling FCM. A resumed fan-out skips every device that already has a row. A crash between insert and send costs that device the advisory; it cannot cause a second send.
- Per-phone checks (BF-58) are evaluated at fan-out time in SQL per chunk, in spec order. Suppressed devices get a `push_send` row with the reason and no FCM call. `TEST` rows are excluded from cooldown and cap counts; `RECOVERY` rows are included (BF-60).
- When fan-out finishes, the event's per-reason counts, latency and start/finish times are written, and under the site lock the "last-notified" values advance if `SENT ≥ 1` (BF-54).
- **In-flight guard.** While a site has an advisory in `PENDING`/`RUNNING`, the engine compares new candidates against the in-flight fingerprint as well as the last sent one. Without this, the next 30 s snapshot would raise the same candidate again before BF-54 has advanced.
- 401/403 from FCM aborts the fan-out, marks the event failed, logs `FCM_ERROR` and alerts (BF-66).

### D11. Event log and audit
- New `site_event` table (BF-62). The template `AuditLog` is not used for engine events: it requires a UUID resource and has a different shape.
- Config changes (BF-77) use `audit_service.log_update` for before/after and also write a `CONFIG_CHANGED` event so they appear in the site's timeline.
- Repeated identical suppressions (same type, reason and fingerprint as the site's previous event) are not re-logged on every 30 s evaluation; the existing row gets a `repeat_count` and `last_seen`. Otherwise a site sitting above T+Δ writes 2 880 `NO_MATERIAL_CHANGE` rows a day (Q5).
- The template's `Announcement` model is an in-app banner and is unrelated. A Freespace announcement (BF-75) is an event of type `ANNOUNCEMENT` plus one topic send; it has no table of its own.

### D12. Deletes
- Config entities (site, zone, keys, templates) use soft delete as the template requires.
- Retention purges (BF-73) and the erasure of `device_site` rows (BF-34) are hard deletes. The spec requires erasure, and the template's own purge jobs already hard-delete. This needs an explicit exception to CLAUDE.md rules 2 and 10 (Q3).

### D13. Settings storage
- Site settings: typed columns on `site` (one per row of §10.1), `notification_window` as JSON. Validation in one Pydantic model used by the API and by the engine loader, refusing invalid combinations (BF-71).
- Zone settings: typed columns on `zone`.
- Templates: `site_message_template(site_id, advisory_type, locale, title, body)`, `locale = 'en'` only (BF-70). Defaults are created with the site.
- Deployment settings: SystemConfig keys `freespace.limit_scope`, `freespace.cooldown_s`, `freespace.daily_cap`, `freespace.time_zone`, `freespace.device_ceiling`, `freespace.retention.*`, seeded in `scripts/seed_data/system_config.yaml` (rule 14), read through a 60 s Redis cache.
- `config.json`: `freespace.mock_mode`, `freespace.mock_mode_acknowledged`, `freespace.fcm_credentials_path`, `freespace.fcm_project_id`, rate-limit strings.
- The template has no environment name, only `DEBUG` and `TESTING`. The BF-84 guard is: `mock_mode` on, `DEBUG` off and no acknowledgement flag → refuse to start.

### D14. Occupancy history
- `occupancy_history(site_id, zone_id NULL, bucket_minute, occupied, capacity, free_usable, health)`, unique on `(site_id, zone_id, bucket_minute)`, written by upsert at intake. Last value in the minute wins.
- At BN-3 sizing this is about 320 000 rows a day and 57 M rows at 180 days. Index on `(site_id, bucket_minute)`. The purge deletes in batches by `bucket_minute`. Partitioning by month is the fallback if the purge or the chart query is slow; decide after load data exists.

### D15. Wire format and tests
- `/v1` serialisers use camelCase aliases (`siteId`, `measuredAt`). Ingest request models use `extra="ignore"`, not the template's `extra="forbid"`, so a later ParkIT that adds a field is not rejected.
- 422 for malformed bodies keeps FastAPI's default shape (it already contains the field path, BF-12). `CLOCK_SKEW`, `SITE_MISMATCH` and the others go through `create_http_exception` with new codes in `RESPONSE_CODES`.
- BT-01 and BT-02 need real row locks. They are written against Postgres using the existing `TEST_DATABASE_URL_DIRECT` pattern and skip without it. CI must provide Postgres or these two are not actually run (Q6).

### D16. Roles and permissions
- Permissions (seeded in the shared seeder, rule 14): `sites:read`, `sites:write`, `site_keys:write`, `site_push:test`, `site_push:announce`, `site_events:read`, `site_alerts:receive`.
- Roles: Administrator → template `admin`/`owner` (all of the above). Operator → new role `operator` (read, events, test push, announce). Viewer → template `viewer` (read, events).
- Spec §12 gives Operators announcements while BF-75 says "Administrator only". Plan follows BF-75: `site_push:announce` is granted to Administrator only. Confirm (Q7).

---

## 3. Data model

| Table | Key columns | Notes |
|---|---|---|
| `site` | `id`, `organization_id`, `site_id` (slug, unique), `name`, `time_zone`, `fcm_topic`, `managed`, `listed`, settings columns | BF-1, §10.1 |
| `zone` | `site_id`, `zone_id` (slug, unique per site), `name`, `display_order`, `enabled`, `recommendable`, `preferred`, `priority`, thresholds, `advisory_pct`, `note`, `discovered` | BF-2, §10.2 |
| `site_snapshot` | one row per site: counts, `health`, `measured_at`, `received_at`, `publisher` JSON | BF-3 |
| `zone_snapshot` | one row per zone: counts, `health`, `measured_at`, `received_at` | BF-3 |
| `occupancy_history` | see D14 | BF-4 |
| `site_engine_state` | `state`, `state_entered_at`, `pending_since`, `last_notified_pct`, `last_notified_zone_id`, `last_sent_fingerprint`, `current_zone_id`, `current_zone_since`, `zone_advisory_state` JSON, `cycle_id` | BF-5 |
| `device` | `device_key_hash`, `id_suffix`, `fcm_token` (unique where not null), `platform`, `app_version`, `notifications_enabled`, `first_seen`, `last_seen`, `token_invalidated_at` | BF-6, D5 |
| `device_site` | `device_id`, `site_id` | BF-6 |
| `push_send` | `event_id`, `device_id`, `site_id`, `advisory_type`, `fingerprint`, `outcome`, `sent_at` | BF-7, D10 |
| `site_event` | `site_id`, `occurred_at`, `type`, `reason`, `figures` JSON, `recommended_zone_id`, `rendered_title/body`, `fingerprint`, `counts` JSON, `fanout_status`, `fanout_started_at/finished_at`, `fcm_latency_ms`, `repeat_count` | BF-8, BF-62 |
| `ingest_key`, `app_key` | see D3 | BF-9 |
| `site_message_template` | see D13 | BF-70 |

All migrations are autogenerated with `make migrate-new` (rule 7), one per module that adds tables.

---

## 4. Modules

Backend code follows the template's flat layout (`src/models/`, `src/crud/`, `src/serialisers/`, `src/api/`), with engine logic in a new package `src/services/freespace/`.

### M0. Foundations
- `/v1` router mount; `Clock`; Freespace response codes; `config.json` keys; SystemConfig keys; permissions, `operator` role and grants in the shared seeder; dependencies `google-auth`, `httpx[http2]`.
- Done when: app starts, `/v1` mount serves a placeholder 404, seeders are idempotent, no-`datetime.now` grep test exists.

### M1. Sites, zones, templates (model + admin API)
- Tables: `site`, `zone`, `site_engine_state`, `site_message_template`, `site_event`.
- Admin API: sites CRUD, zones CRUD, `GET`/`PUT .../config`, templates get/put. Settings validation (BF-71), template placeholder validation (BF-70), audit + `CONFIG_CHANGED` (BF-77), `managed` off→on resets the cycle (BF-72).
- Covers BF-1, BF-2, BF-5 (storage), BF-8 (storage), BF-70 – BF-72, BF-77, part of BF-78.
- Tests: validation table of §10.1, tenant isolation on every endpoint, role matrix.

### M2. Keys
- Tables: `ingest_key`, `app_key`. Admin endpoints: create (shown once), revoke, list with last used and last IP. Auth dependencies.
- Covers BF-9, BF-10, BF-10a, BF-10b.
- Tests: key regex of BF-10a, expiry, revocation, two keys valid at once, plaintext never stored or logged.

### M3. Intake
- `GET /v1/ingest/ping`, `POST /v1/ingest/occupancy`. Tables: `site_snapshot`, `zone_snapshot`, `occupancy_history`.
- Sum check and `PARTIAL` downgrade (BF-12), clock skew and out-of-order (BF-13), zone discovery (BF-14), response (BF-15) under 64 KB with capped `warnings` (BF-19), ingest limiter (BF-18), `last_used_*` on the key, events `INGEST_REJECTED`, `INGEST_INCONSISTENT`, `ZONE_DISCOVERED`.
- Until M6 exists the response returns `state: "IDLE"` from the stored engine row and the recommendation from M4. M3 and M4 ship together.
- Covers BF-3, BF-4, BF-10 – BF-19. Tests: BT-03, BT-04, BT-11, 429 `Retry-After` format.
- Depends on M1, M2.

### M4. Availability
- Pure `availability.py` (BF-20 – BF-25) and `GET /v1/sites`, `GET /v1/sites/{siteId}/availability` (BF-30 – BF-32) with a 5 s Redis cache and `Cache-Control: max-age=5`. Per-IP limits (BF-36).
- Covers BF-20 – BF-25, BF-30 – BF-32, BF-36 (read part). Tests: AT-01, AT-07 (recommendation part), AT-08 (availability part), BT-05, floor rounding at 89.9 %, never-received site, unlisted site 404.
- Depends on M1, M2.

**Milestone A (M0–M4):** ParkIT can publish to a real site and the app can show availability. First integration test with ParkIT and the app.

### M5. Devices
- Tables: `device`, `device_site`. `PUT`/`DELETE /v1/devices/{deviceId}` (BF-33, BF-34), token move between devices, device ceiling with 503 (BF-37), per-device and per-IP limits (BF-36), logging changes of D5.
- Covers BF-6, BF-33 – BF-37. Tests: BT-07 (storage part), idempotent PUT, unknown site 422, DELETE of unknown id is 204, the log-leak test of D5.
- Depends on M1, M2.

### M6. Rules engine
- Pure `engine.py` and `templates.py`; persistence shell with the site lock (D6); inline evaluation from intake; `engine_tick` cron; `DATA_STALE` / `DATA_RECOVERED` events; shadow mode (BF-61).
- Advisory candidates that pass usefulness are committed as events with `fanout_status = PENDING`. Until M7 lands, a stub fan-out marks them complete with zero devices.
- Covers BF-5, BF-50 – BF-57, BF-61, BF-62, BF-72, BF-85. Tests: AT-02 – AT-08 with `FixedClock`, BF-53 (timers frozen while stale), BT-01 (Postgres), BT-09.
- Depends on M3, M4.

### M7. Push delivery
- `FcmClient`, message builder (BF-65: Android and APNs blocks both set), `push_send`, fan-out task with per-phone checks (BF-58 – BF-60), limit scope (BF-63), error handling and token invalidation (BF-66, BF-67), credential loading (BF-68), in-flight guard and BF-54 advance (D10). Wording says "accepted by FCM" everywhere (BF-69).
- FCM is faked in tests behind the client interface.
- Covers BF-7, BF-41, BF-58 – BF-60, BF-63 – BF-69. Tests: AT-03, AT-05 (per-phone part), BT-02 (Postgres), BT-06, BT-07, BT-08, the BF-68 secret-grep test, message payload snapshot for both platforms.
- Depends on M5, M6.

**Milestone B (M5–M7):** pilot site runs in shadow mode, then goes live.

### M8. Admin operations API
- Events list with filters and CSV export (streamed, no device data), site live view (same computation as the app plus engine timers), sites list summary, test push to device suffix or topic with typed confirmation (BF-74), announcement (BF-75), device statistics (BF-76), occupancy history series.
- Covers BF-74 – BF-76 (API side), BF-78. Depends on M6, M7.

### M9. Operations
- Daily purge as a DB-driven cron job seeded in `cron_jobs.yaml`, retention read from SystemConfig (BF-73); fix request-log retention wiring; operator alerts through the notification dispatcher with new templates and a `site_operations` category in the shared seeder, sent to users holding `site_alerts:receive` (BF-82); `/health` with DB check and tick age (BF-80); `pg_dump` script with 14-day rotation and off-host copy (BF-83).
- Alert state (site silent, recovered) is tracked so each alert fires once per transition.
- Covers BF-73, BF-80 – BF-83. Depends on M5, M6, M7.

### M10. Mock mode
- `/mock/sites/{id}/occupancy`, `/mock/clock`, registered only when `mock_mode` is on; startup guard (D13).
- Covers BF-84. Tests: BT-10, startup refusal. Depends on M6.

### M11. Back-office frontend
One ADW issue per group; all text through i18n (`locales/en/admin.json`, rule 8).
1. Sites list and site live view.
2. Site settings, notification window editor, zone settings (with discovered-zone review), message templates.
3. Ingest keys (create with shown-once dialog, revoke) and app keys.
4. Event log with filters and CSV export.
5. Test push and announcement dialogs with typed confirmation.
6. Device statistics and occupancy history chart. Adds `recharts`; draws trigger and reset lines.
7. Simulator page for AT-01 – AT-08, visible only when the backend reports mock mode.

Each group needs: RTK Query slice in `features/sites/`, tags in `store/api.ts`, routes in `config/routes.ts`, nav entries in `config/adminNav.ts`, hub permissions in `config/navigation.ts`, and an E2E spec. Depends on M1, M2, M8, M10 as relevant; groups 1–3 can start after Milestone A.

### M12. Deployment
- Proxy `/v1`, access-log masking for `/v1/devices/`, `trusted_client_ip_header`, Let's Encrypt on the stable hostname (BN-1), FCM service-account file outside the repo, backup timer, load check for BN-3 (availability p95, 5 000-device fan-out against a fake FCM).
- Covers BN-1, BN-3, BN-4, BF-68, BF-83.

### Order

```
M0 → M1 → M2 → M3+M4 ──→ M6 → M7 → M8 → M9
                    └→ M5 ───┘         └→ M10
M11.1–3 after M4; M11.4–7 after M8/M10; M12 alongside M9
```

---

## 5. Risks

| # | Risk | Handling |
|---|---|---|
| R1 | `deviceId` leaks through a log nobody listed (proxy access log, metrics labels, exception traces) | D5 changes plus the leak test; review proxy config in M12. |
| R2 | Duplicate pushes from concurrent evaluation or a resumed fan-out | D6, D10; BT-01 and BT-02 on real Postgres. |
| R3 | SQLite test database hides Postgres-only behaviour | Postgres-marked tests; CI Postgres (Q6). |
| R4 | Single ARQ worker: a long fan-out delays the tick | Chunked fan-out, `max_jobs = 10`; measure in M12 and add a second queue if needed. |
| R5 | `occupancy_history` size | D14. |
| R6 | Spec and proposal wording for default templates is not in this repo | Q8. |
| R7 | Template features irrelevant to Freespace (self-registration, payments, onboarding) stay reachable on a public host | Not in the spec. Decide separately whether to disable them before go-live. |

---

## 6. Open questions

| # | Question | Default used in this plan |
|---|---|---|
| Q1 | Admin API path: spec says `/v1/admin/...`; template and frontend use `/api/v1/...`. | `/api/v1/admin/sites/...` |
| Q2 | Do SATT Operators and Viewers need to see all customers, or is super admin enough for cross-customer access? | Super admin sees all; other users see their own organization. |
| Q3 | Approve hard deletes for retention purges and device erasure, as an exception to CLAUDE.md rules 2 and 10? | Yes. |
| Q4 | Where do nightly backups go off the VPS? | Undecided; script takes a target as configuration. |
| Q5 | Two interpretations: (a) collapse repeated identical suppression events into one row with a count; (b) in shadow mode advance "last-notified" as if the advisory had been sent, so shadow events match live behaviour. | Both yes. |
| Q6 | Does CI have Postgres for BT-01 and BT-02? | Assumed yes. |
| Q7 | Announcements: Administrator only (BF-75) or also Operator (§12 intro)? | Administrator only. |
| Q8 | Need *Freespace Functional Specification* §9 and *Backend Proposal* §3.1, §3.3, §6 for default message wording and the exact admin shapes. | Blocked for M1 template defaults; placeholders until supplied. |
