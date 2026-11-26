# Freespace Backend — Shared Contracts (M0 foundation)

Written 2026-11-26 by the M0 foundation step. This is the **single reference** for the agents implementing M1–M10 in parallel in the same working tree. Read it fully before you start. Requirement ids (BF-x, BT-x, AT-x) refer to `specs/BACKEND_FUNCTIONAL_DESCRIPTION.md` (authoritative); design ids (Dx, Qx) to `specs/freespace_backend_implementation_plan.md`. Default message wording (spec §9 / proposal §6) is in `specs/freespace_reference_extracts.md`.

All paths below are relative to `app/backend/` unless they start with `specs/` or `app/`.

---

## 0. Rules (binding)

1. **Edit only files you own** (§1). Everything else is read-only for you. Foundation files listed as "shared, read-only" may not be changed by anyone; if a signature there is wrong, **report it** in your final report instead of changing it.
2. **Do not create or edit migrations.** The schema for every table in plan §3 already exists (migration `alembic/versions/3bbd1397e1c2_freespace_core_tables.py`). If you need a schema change, describe it in your report (table, column, type, nullable, default, index, reason).
3. **Do not edit** `main.py`, `src/api/v1/__init__.py`, `src/api/freespace_public/__init__.py`, `src/models/*`, `src/core/response_codes.py`, `src/core/config.py`, `config.json*`, seed YAML, `src/services/organization_seeding.py`, `src/workers/worker.py`, `tests/conftest.py`, `tests/freespace/conftest.py`, `pytest.ini`, `requirements.txt`. All routers, codes, settings, permissions, roles, SystemConfig keys and fixtures you should need are already there. Missing response code / setting / fixture → report it; as a stop-gap you may define a **local** fixture in your own test file.
4. **Do not `git commit`**, do not create branches.
5. **Do not change signatures** in the stub files you own unless unavoidable; if you must, report old and new signature and every caller.
6. CLAUDE.md applies (tenant filtering, soft deletes, `create_http_exception` with `detail_code`, async, Pydantic, tenant-isolation tests, i18n for the frontend). Exceptions agreed in the plan: `/v1` mount outside `v1_router` (D1), hard deletes only for retention purges and device erasure (D12/Q3).
7. **Never** log, store in `site_event`, return (except to its own `PUT`), or export a raw `deviceId` or FCM token (BF-35). Never log a plaintext key.
8. Run your tests scoped: `cd app/backend && .venv/bin/pytest tests/freespace -q -n 4` (your files: `tests/freespace/test_<module>_*.py`), then `make lint` (`ruff check src/ tests/` and `mypy src/ --ignore-missing-imports`; the template has 25 pre-existing mypy errors and 16 pre-existing ruff UP007 errors in `src/services/email.py` / `src/services/notifications/email_provider.py` — do not add new ones). Before finishing run the whole suite once: `.venv/bin/pytest tests/ -q -n 8` (baseline: 1 pre-existing failure `tests/unit_tests/test_deployment_client_ip_config.py::test_compose_network_subnet_is_pinned_and_matches_the_allow_list`).

---

## 1. File ownership

"Owns" = may edit. "New files" = naming pattern for files the module may create. Every module may also create `tests/freespace/test_<prefix>_*.py`.

| Module | Owns (existing skeleton/stub files) | New files it may create | Test file prefix |
|---|---|---|---|
| **M1** sites, zones, templates admin API | `src/api/freespace_sites.py`, `src/api/freespace_zones.py`, `src/services/freespace/templates.py` (fill bodies + `DEFAULT_TEMPLATES` wording) | `src/crud/freespace_sites.py`, `src/crud/freespace_zones.py`, `src/crud/freespace_templates.py`, `src/serialisers/freespace_sites.py`, `src/serialisers/freespace_zones.py`, `src/serialisers/freespace_templates.py`, `src/services/freespace/site_config.py` (BF-71 validation model shared with the engine loader if needed) | `test_m1_` |
| **M2** keys admin API + ingest limiter | `src/api/freespace_keys.py` (`router`, `app_keys_router`), `src/crud/freespace_keys.py` (ADD write-side functions; keep existing read-side ones unchanged) | `src/serialisers/freespace_keys.py`, `src/services/freespace/ingest_rate_limit.py` | `test_m2_` |
| **M3** intake | `src/api/freespace_public/ingest.py` | `src/crud/freespace_snapshots.py`, `src/crud/freespace_history.py`, `src/serialisers/freespace_ingest.py`, `src/services/freespace/intake.py` | `test_m3_` |
| **M4** availability core + app endpoints | `src/services/freespace/availability.py` (fill stubs), `src/api/freespace_public/app_sites.py` | `src/serialisers/freespace_app.py`, `src/services/freespace/availability_cache.py` | `test_m4_` |
| **M5** devices + log privacy | `src/api/freespace_public/devices.py`, `src/middleware/request_response_logging.py` (D5 route-template logging and full mask of `fcmToken`), `src/middleware/metrics.py` (only if labels use raw paths) | `src/crud/freespace_devices.py`, `src/serialisers/freespace_devices.py`, `src/services/freespace/devices.py` | `test_m5_` |
| **M6** engine core + evaluator + tick | `src/services/freespace/engine.py`, `src/services/freespace/evaluator.py` (replace the TEMPORARY body of `evaluate_site`, implement `run_engine_tick`) | `src/services/freespace/engine_*.py` (helpers) | `test_m6_` |
| **M7** FCM client + fan-out | `src/services/freespace/fcm.py` (`build_data_payload`, `build_message`, `HttpFcmClient`; keep `FakeFcmClient`/protocol/result types unchanged), `src/services/freespace/fanout.py` | `src/crud/freespace_push_send.py`, `src/services/freespace/fcm_auth.py`, `src/services/freespace/limits.py` | `test_m7_` |
| **M8** admin ops API | `src/api/freespace_events.py`, `src/api/freespace_push.py`, `src/api/freespace_stats.py` | `src/crud/freespace_events.py`, `src/crud/freespace_stats.py`, `src/serialisers/freespace_events.py`, `src/serialisers/freespace_push.py`, `src/serialisers/freespace_stats.py`, `src/services/freespace/admin_push.py` | `test_m8_` |
| **M9** ops (purge, alerts, health, backup) | the `/health` part of `main.py` is **not** editable — put the BF-80 check in a function and report the one-line `main.py` change needed; `scripts/backup/` | `src/services/freespace/purge.py`, `src/services/freespace/alerts.py`, `src/services/freespace/health.py`, cron handler in a new file `src/services/cron/freespace_purge.py` (registration lines in the existing cron handler registry and YAML: **report** them, do not edit shared YAML) | `test_m9_` |
| **M10** mock mode | `src/api/freespace_public/mock.py` | `src/serialisers/freespace_mock.py` | `test_m10_` |

**Integration (after M1–M10, 2026-11-26):** the shared files above (`main.py`, `src/core/*`, seed YAML, `organization_seeding.py`, `cron_scheduler.py` / `src/services/cron/__init__.py`, deploy files) were wired by the integration step; see §11 for what changed.

Shared, read-only for every module (foundation): `src/constants/freespace.py`, `src/services/freespace/{types,loaders,clock,redis_client,keys,events,deployment_settings,site_bootstrap,mock_mode,__init__}.py`, `src/api/freespace_deps.py`, `src/workers/freespace_tasks.py`, all `src/models/*` Freespace models.

Cross-module calls (allowed, by signature only): M3 → `evaluator.evaluate_site/enqueue_fanouts`, M4 `availability`, M1 none; M6 → `availability`, `templates`, `fanout.recover_stuck_fanouts`; M7 → `engine.on_fanout_completed`, `fcm`; M8 → `availability`, `fcm`, `templates`; M10 → M3's intake service (`src/services/freespace/intake.py`, agree the function name via reports; until it exists, write the snapshot rows directly) and `clock.advance_mock_offset`.

---

## 2. Data model (all tables exist)

Conventions: UUID pk `id`; config entities have `created_time` / `updated_time` / `deleted_time` (soft delete); every timestamp is `DateTime(timezone=True)` UTC. **Write engine-relevant timestamps from the Freespace clock, never from column defaults.** In SQLite tests datetimes come back naive — use `clock.ensure_utc()` (the loaders already do).

**Slugs vs ids (deviation from plan naming, see §9):** the wire `siteId` is `site.slug`; the wire `zoneId` is `zone.slug`. Every FK column named `site_id` / `zone_id` is a row UUID. Engine state and events reference zones by slug in `*_zone_slug` columns.

| Model (file) | Table | Tenant | Key columns / notes |
|---|---|---|---|
| `Site` (`src/models/site.py`) | `site` | `organization_id` | `slug` (globally unique among live rows, partial index), `name`, `time_zone`, `fcm_topic`, `managed` (False), `listed` (False), settings: `trigger_pct` 90, `reset_pct` 80, `change_points` 5, `change_direction` RISING, `stabilisation_s` 300, `recommendation_margin` 10, `stale_limit_s` 120, `partial_is_stale` True, `recovery_push` False, `zone_advisory` False, `zone_reset_gap` 10, `notification_window` JSON (default Mon–Fri 06:00–10:00), `cooldown_s` 1800, `daily_cap` 2, `push_expiry_s` 1800. Relationship `zones` (`lazy="raise"`: use `selectinload`). |
| `Zone` (`zone.py`) | `zone` | `organization_id` | `site_id` FK, `slug` (unique per site among live rows), `name`, `display_order` 0, `enabled` (False = discovered default; admin-created zones set True), `recommendable` True, `preferred` False, `priority` 100, `limited_pct` 80, `full_pct` 95, `full_min_free` 5, `unknown_limit_pct` 25, `advisory_pct` NULL, `note` "", `discovered` False. |
| `SiteSnapshot` / `ZoneSnapshot` (`site_snapshot.py`) | `site_snapshot`, `zone_snapshot` | `organization_id` | one row per site (unique `site_id`) / per zone (unique `zone_id`); `capacity, occupied, free_usable, free_reserved, free_disabled, unknown`, `health` (EFFECTIVE, after BF-12 downgrade), `reported_health` (as received), `measured_at`, `received_at`; site row also `publisher` JSON. No soft delete. |
| `OccupancyHistory` (`occupancy_history.py`) | `occupancy_history` | `organization_id` | BIGINT pk; `site_id`, `zone_id` NULL = site row, `bucket_minute` (minute start), `occupied, capacity, free_usable, health`. Two partial unique indexes: `(site_id, bucket_minute) WHERE zone_id IS NULL` and `(zone_id, bucket_minute) WHERE zone_id IS NOT NULL` — upsert with `postgresql.insert(...).on_conflict_do_update(index_elements=[...], index_where=...)`; SQLite tests: select-then-update. |
| `SiteEngineState` (`site_engine_state.py`) | `site_engine_state` | `organization_id` | unique `site_id`; `state`, `state_entered_at`, `pending_since`, `cycle_id`, `last_notified_pct` (float exact %), `last_notified_zone_slug`, `last_notified_top_zones` JSON list, `last_sent_fingerprint`, `last_sent_at`, `current_zone_slug`, `current_zone_since`, `zone_advisory_state` JSON `{slug: {"above_since": iso\|null, "advised": bool}}`, `stale` (True), `stale_since`, `inflight_event_id`, `inflight_fingerprint`, `last_evaluated_at`, `ops_alert_state` JSON (**M9 only**). Created with the site. Convert only via `loaders.engine_state_from_row` / `apply_engine_state`. |
| `SiteMessageTemplate` (`site_message_template.py`) | `site_message_template` | `organization_id` | `site_id`, `advisory_type`, `locale` ('en'), `title` (≤255), `body`; unique `(site_id, advisory_type, locale)` among live rows. |
| `SiteEvent` (`site_event.py`) | `site_event` | `organization_id` | `occurred_at`, `last_seen_at`, `repeat_count`, `type`, `reason`, `advisory_type`, `zone_slug`, `cycle_id`, `figures` JSON, `recommended_zone_slug`, `rendered_title`, `rendered_body`, `fingerprint`, `counts` JSON `{DeviceOutcome: int}`, `fanout_status` (NULL = never fans out), `fanout_started_at`, `fanout_finished_at`, `fcm_latency_ms`, `details` JSON. No soft delete (purged). **Insert only through `events.write_event`.** |
| `Device`, `DeviceSite` (`device.py`) | `device`, `device_site` | **none** (D2) | `device_key_hash` (SHA-256 of deviceId, UNIQUE, NULL on tombstone), `id_suffix` (last 6), `fcm_token` (UNIQUE, ≤512), `platform`, `app_version`, `notifications_enabled`, `first_seen`, `last_seen`, `token_invalidated_at`, soft-delete `deleted_time`. `device_site(device_id, site_id)` unique, hard-deleted on opt-out. |
| `PushSend` (`push_send.py`) | `push_send` | `organization_id` (denormalised from site) | `event_id`, `device_id`, `site_id`, `advisory_type`, `fingerprint`, `outcome` (`DeviceOutcome`), `queued_at` (clock), `sent_at`, `error_code`; **UNIQUE (event_id, device_id)** = at-most-once. No soft delete (purged). |
| `IngestKey` (`ingest_key.py`) | `ingest_key` | `organization_id` | `site_id`, `name`, `key_hash` (SHA-256, UNIQUE), `key_hint` (last 4), `expires_at`, `revoked_at`, `last_used_at`, `last_used_ip`, `created_by`, soft delete. |
| `AppKey` (`app_key.py`) | `app_key` | **none** | `name`, `key_hash` (UNIQUE), `key_hint`, `revoked_at`, `created_by`, soft delete. |

---

## 3. Shared code (signatures and meaning)

### 3.1 Constants — `src/constants/freespace.py`
StrEnums (compare equal to stored strings): `EngineState`, `AdvisoryType` (+ `TEMPLATED_ADVISORY_TYPES`, `LIMIT_COUNTED_ADVISORY_TYPES` = all but TEST), `EventType` (BF-62 list), `SuppressionReason` (STALE_DATA, NO_MATERIAL_CHANGE, NO_RECOMMENDATION, UNMANAGED, IN_FLIGHT), `DeviceOutcome` (PENDING, OPTED_OUT, OUTSIDE_WINDOW, DUPLICATE, COOLDOWN, DAILY_CAP, SENT, SEND_FAILED, TOKEN_INVALID) + `DEVICE_CHECK_ORDER`, `StateChangeReason` (TRIGGER_CROSSED, NOT_STABLE, STABILISED, RESET, CYCLE_RESTARTED), `IngestRejectReason` (SITE_MISMATCH, CLOCK_SKEW, RATE_LIMITED, OUT_OF_ORDER), `IngestInconsistencyReason` (SUM_MISMATCH), `FcmErrorReason` (AUTH_FAILURE, CREDENTIALS_MISSING, QUOTA_EXHAUSTED), `ConfigChangeReason`, `Health`, `ZoneStatus`, `Platform`, `LimitScope`, `ChangeDirection`, `FanoutStatus` (PENDING, RUNNING, COMPLETED, FAILED).
Defaults: `SITE_DEFAULTS`, `ZONE_DEFAULTS`, `SITE_SETTING_BOUNDS` (single source of the integer site-setting bounds used by `site_config.validate_site_settings`; `stale_limit_s` min 120), `DEPLOYMENT_DEFAULTS`, `DEFAULT_NOTIFICATION_WINDOW` / `default_notification_window()`, `DEFAULT_TIME_ZONE`, `DEFAULT_LOCALE`.
Wire: `MAX_FUTURE_SKEW_S`=120, `MAX_INGEST_WARNINGS`, `MAX_INGEST_WARNING_LENGTH`, `RETRY_AFTER_MIN_S/MAX_S`=1/600, `AVAILABILITY_CACHE_MAX_AGE_S`=5, `SLUG_PATTERN`, `FCM_TOPIC_PATTERN`, `DEVICE_ID_PATTERN`, `DEVICE_ID_SUFFIX_LENGTH`, `INGEST_KEY_PREFIX` "fsk_", `APP_KEY_PREFIX` "fsa_", `APP_KEY_HEADER`, `ANDROID_CHANNEL_ID`, `FCM_MAX_IN_FLIGHT`=20, `FCM_RETRY_WINDOW_S`=300, `FANOUT_CHUNK_SIZE`=500, `FANOUT_STUCK_AFTER_S`.
Redis keys: `REDIS_MOCK_CLOCK_OFFSET_KEY`, `REDIS_APP_KEYS_KEY`, `REDIS_DEPLOYMENT_SETTINGS_KEY`, `REDIS_ENGINE_TICK_KEY` = `freespace:engine_tick:last` (M6 writes ISO time, M9 `/health` reads), `REDIS_AVAILABILITY_KEY_FMT` (M4), `REDIS_INGEST_RATE_KEY_FMT` (M2). Permission constants `PERM_*`, `FREESPACE_PERMISSION_CODES`, `OPERATOR_ROLE_NAME`, job names `JOB_FANOUT_ADVISORY`, `JOB_ENGINE_TICK`.

### 3.2 Pure types — `src/services/freespace/types.py`
Frozen dataclasses; zones by slug; datetimes aware UTC; pct settings are whole points.
- `NotificationWindowRule(weekdays: frozenset[int] ISO 1–7, start: time, end: time)` + `.contains(local_dt)`; `is_within_notification_window(rules, local_dt) -> bool` (empty = always).
- `SiteSettings(site_id, organization_id, slug, name, time_zone, fcm_topic, managed, listed, trigger_pct…push_expiry_s, notification_window: tuple[NotificationWindowRule,...])`.
- `ZoneConfig(zone_id, slug, name, display_order, enabled, recommendable, preferred, priority, limited_pct, full_pct, full_min_free, unknown_limit_pct, advisory_pct, discovered)`.
- `MessageTemplate(advisory_type, title, body, locale)`, `RenderedMessage(title, body)`.
- `Figures(capacity, occupied, free_usable, free_reserved, free_disabled, unknown, health, measured_at, received_at)`; `SiteFigures(Figures)`; `ZoneFigures(Figures, zone_slug)`.
- `SnapshotView(site: SiteFigures | None, zones: Mapping[slug, ZoneFigures])`.
- `ZoneAdvisoryState(above_since, advised)`; `EngineStateData(...)` mirrors the row; `initial_engine_state(now)`.
- `RankedZone(slug, name, free_usable, priority)`; `ZoneAvailability(slug, name, display_order, enabled, recommendable, status, stale, capacity, occupied, free, occupancy_pct, health, as_of)`; `SiteAvailability(site_slug, stale, as_of, age_seconds, capacity, occupied, free_usable, occupancy_pct, health, recommended_zone_slug, top_zones, ranked, zones)`.
- `Candidate(advisory_type, recommended_zone_slug, top_zones, occupancy_pct, occupancy_exact, title, body, fingerprint, suppressed, zone_slug)`.
- `EventDraft(type, occurred_at, reason, advisory_type, zone_slug, cycle_id, figures, recommended_zone_slug, rendered_title, rendered_body, fingerprint, counts, fanout_status, details, id=uuid4())`.
- `EvaluationResult(new_state, events, candidates, availability)` + `.fanout_event_ids`.

### 3.3 Loaders — `src/services/freespace/loaders.py` (implemented)
Converters: `site_settings_from_row(Site)`, `zone_config_from_row(Zone)`, `site_figures_from_row(SiteSnapshot)`, `zone_figures_from_row(ZoneSnapshot, slug)`, `message_template_from_row(row)`, `engine_state_from_row(row)`, `apply_engine_state(row, data)`, `parse_notification_window(json)` / `notification_window_to_json(rules)`, `zones_by_slug(zones)`.
Queries (no tenant filter — resolve/authorise the site first in admin code): `load_site_row(session, site_id)`, `load_site_row_by_slug(session, slug)`, `load_zone_rows(session, site_id)` (live, display order), `load_zone_configs`, `load_snapshot(session, site_id) -> SnapshotView`, `load_templates(session, site_id, locale="en") -> dict[AdvisoryType, MessageTemplate]`, `load_engine_state_row(session, site_id, *, for_update=False)`, `load_site_context(session, site_id, *, with_templates=True) -> SiteContext(site, settings, zones, snapshot, templates) | None`.

### 3.4 Clock — `src/services/freespace/clock.py` (implemented)
`Clock` protocol (`now() -> aware UTC`), `SystemClock(offset)`, `FixedClock(start).advance(seconds=0, *, delta=None)/.set(dt)`, `ensure_utc(dt)`, `async get_clock() -> Clock` (FastAPI dependency **and** accessor: override > mock-mode Redis offset > system), `set_clock_override(clock|None)`, `get_mock_offset_seconds()`, `set_mock_offset_seconds(s)`, `advance_mock_offset(s) -> new offset` (M10), `reset_mock_offset()`.

### 3.5 Redis — `src/services/freespace/redis_client.py`
`get_redis() -> async client | None` (override > API pool > cache client); `set_redis_override(client)` (tests). Always fail open on `None` / errors.

### 3.6 Deployment settings — `src/services/freespace/deployment_settings.py` (implemented)
`DeploymentSettings(limit_scope, cooldown_s, daily_cap, time_zone, device_ceiling, retention_devices_days=90, retention_send_history_days=35, retention_events_days=365, retention_occupancy_history_days=180, retention_request_logs_days=30)`; `async get_deployment_settings(session=None)` (60 s Redis cache, safe defaults); `invalidate_deployment_settings_cache()`; `SYSTEM_CONFIG_KEYS` (field → key: `freespace.limit_scope`, `freespace.cooldown_s`, `freespace.daily_cap`, `freespace.time_zone`, `freespace.device_ceiling`, `freespace.retention.{devices_days,send_history_days,events_days,occupancy_history_days}`, and the template's existing `request_logs.retention_days`).

### 3.7 Keys — `src/services/freespace/keys.py` (implemented)
`generate_ingest_key()` (`fsk_` + 43 base64url), `generate_app_key()` (`fsa_…`), `hash_key(plaintext) -> sha256 hex`, `key_hint(plaintext)` (last 4), `is_valid_key_format(s)` (BF-10a), `keys_equal(a, b)`, `is_valid_device_id(s)`, `hash_device_id(device_id)` (also the per-device rate-limit key), `device_id_suffix(device_id)` (last 6).

### 3.8 Event writer — `src/services/freespace/events.py` (implemented)
`async write_event(session, *, site_id, organization_id, draft: EventDraft, collapse=True) -> SiteEvent` and `write_events(..., drafts)`. Flush only. D11 collapse for `COLLAPSIBLE_EVENT_TYPES` = {CANDIDATE, INGEST_REJECTED, INGEST_INCONSISTENT}: same type+reason+advisory_type+zone_slug+fingerprint as the site's latest event of that type (with no non-collapsible event after it) → `repeat_count += 1`, `last_seen_at = occurred_at`, the EXISTING row is returned (its id ≠ `draft.id`). ADVISORY etc. never collapse. **Write events inside the transaction you commit; raising `HTTPException` afterwards rolls them back unless you commit first** (M3: commit the `INGEST_REJECTED` event before raising 403/422). `to_json_value()` converts mappings/tuples/enums/datetimes/UUIDs for JSON columns.

### 3.9 Site bootstrap — `src/services/freespace/site_bootstrap.py` (implemented)
`async create_site_dependents(session, site, now) -> (SiteEngineState, [SiteMessageTemplate])` — M1 MUST call it right after inserting a site (engine-state lock target + one default template per `TEMPLATED_ADVISORY_TYPES` from `templates.DEFAULT_TEMPLATES`). `async reset_engine_cycle(session, site_id, now) -> EngineStateData` — BF-72, M1 calls it when `managed` goes false→true (then writes a `STATE_CHANGE / CYCLE_RESTARTED` and a `CONFIG_CHANGED / MANAGED_ON` event).

### 3.10 Availability (M4) — `src/services/freespace/availability.py`
Implemented primitives: `occupancy_ratio(occupied, capacity) -> Fraction|None`, `occupancy_pct_floor(...) -> int|None`, `meets_pct(occupied, capacity, pct: float) -> bool` (exact), `occupancy_exact_pct(...) -> float|None`, `age_seconds(figures, now)`.
Stubs: `is_zone_stale(settings, zone, figures, now)`, `is_site_stale(settings, figures, now)`, `zone_status(settings, zone, figures, now) -> ZoneStatus`, `rank_candidates([(ZoneConfig, ZoneFigures, ZoneStatus)]) -> tuple[RankedZone,...]`, `sticky_recommendation(ranked, current, margin, *, site_stale) -> slug|None`, `top_two(ranked)`, **`compute_site_availability(settings, zones, snapshot, current_recommendation, now) -> SiteAvailability`** — the one computation used by app (M4), live view (M8) and engine (M6). App passes `site_engine_state.current_zone_slug` as `current_recommendation` and persists nothing.

### 3.11 Templates (M1) — `src/services/freespace/templates.py`
Implemented: `PLACEHOLDER_*`, `PLACEHOLDER_RE`, `ALLOWED_PLACEHOLDERS` (SITE_INITIAL/SITE_CHANGE/RECOVERY: site, zone, topZones, occupancyPct; ZONE_ADVISORY: + fullZone; TEST: site), `DEFAULT_TEMPLATES` (**TODO wording — M1 fills from `specs/freespace_reference_extracts.md`**), `TemplateValidationError(message, unknown)`.
Stubs: `extract_placeholders(text)`, `validate_template(advisory_type, title, body)`, `format_top_zones(names)`, `build_context(*, site_name, zone_name, top_zone_names, occupancy_pct, full_zone_name=None) -> dict[str,str]`, `render(template, context) -> RenderedMessage`, `fingerprint(advisory_type, recommended_zone_slug, top_zones, body) -> sha256 hex`.

### 3.12 Engine (M6) — `src/services/freespace/engine.py`
Stubs: `evaluate(settings, zones, snapshot, state, templates, now) -> EvaluationResult`; `on_fanout_completed(state, *, event_id, cycle_id, advisory_type, fingerprint, recommended_zone_slug, top_zones, occupancy_exact, sent_count, now) -> EngineStateData` (called by M7 under the row lock; BF-54); `event_figures(availability) -> dict` (BF-62 `figures` JSON).

### 3.13 Evaluator (M6) — `src/services/freespace/evaluator.py`
`EvaluatedSiteView(state, recommended_zone_slug, stale, fanout_event_ids)`. `async evaluate_site(session, site_id, clock) -> EvaluatedSiteView` — locks `site_engine_state FOR UPDATE`, evaluates, persists, **does not commit**; raises `LookupError` without a state row. **TEMPORARY body now:** returns stored state, `recommended_zone_slug=None`, stored `stale`, no fan-outs. Caller pattern: `view = await evaluate_site(...); await session.commit(); await enqueue_fanouts(view.fanout_event_ids)`. `async enqueue_fanouts(event_ids)` (implemented). `async run_engine_tick(session_factory, clock) -> TickResult` (stub; all live sites incl. unmanaged; recover stuck fan-outs; write `REDIS_ENGINE_TICK_KEY`). `SessionFactory = Callable[[], AsyncContextManager[AsyncSession]]`.

### 3.14 FCM (M7) — `src/services/freespace/fcm.py`
`FcmResultKind` (ACCEPTED, TOKEN_INVALID, RETRYABLE, AUTH_FAILURE, FAILED), `FcmMessage(payload, token=None, topic=None).to_request_body()`, `FcmSendResult(kind, message_id, retry_after_s, error_code, http_status, latency_ms)`, `FcmClient` protocol (`async send(message) -> FcmSendResult`, `async aclose()`), `FakeFcmClient` (implemented: `sent`, `sent_tokens`, `sent_topics`, `results_by_token` / `results_by_topic` scripts, `default_result`), `get_fcm_client()` (dependency/accessor; override > lazily built `HttpFcmClient`; `RuntimeError` if not configured), `set_fcm_client_override()`. Stubs: `build_data_payload(*, message_type, site_slug, recommended_zone_slug, occupancy_pct, event_id, sent_at) -> dict[str,str]`, `build_message(*, title, body, data, site_slug, sent_at, ttl_s, token=None, topic=None) -> FcmMessage`, `HttpFcmClient(credentials_path, project_id).send`.

### 3.15 Fan-out (M7) — `src/services/freespace/fanout.py`
`FanoutResult(event_id, status, reenqueue_in_s=None, processed=0, counts={})`; stubs `async run_fanout(session_factory, event_id, *, clock, fcm, chunk_size=FANOUT_CHUNK_SIZE) -> FanoutResult` (one chunk, idempotent, at-most-once via `push_send` unique row committed before the FCM call) and `async recover_stuck_fanouts(session, now) -> list[UUID]`.

### 3.16 ARQ tasks — `src/workers/freespace_tasks.py` (foundation, registered in `worker.py` and `job_types.py`)
`fanout_advisory_task(ctx, event_id: str)` → `run_fanout(ctx["session_factory"], UUID, clock=await get_clock(), fcm=get_fcm_client())`; re-enqueues itself with `_defer_by=reenqueue_in_s` when set. `engine_tick(ctx)` (ARQ cron every minute at second 30) → `run_engine_tick(ctx["session_factory"], await get_clock())`. Both catch `NotImplementedError` and return `{"status": "not_implemented"}`.

### 3.17 Auth dependencies — `src/api/freespace_deps.py` (implemented)
- `IngestAuth(site: Site, key: IngestKey)`; `get_ingest_site(request, session, clock, authorization header) -> IngestAuth`: 401 `ingest.unauthorized` (missing / not Bearer / bad format / unknown / deleted key or site), `ingest.key_revoked`, `ingest.key_expired`, with `WWW-Authenticate: Bearer`; sets `last_used_at` (clock) / `last_used_ip` and **commits**. The site mismatch check (BF-10 403) is M3's.
- `require_app_key(session, X-Freespace-App-Key)` → 401 `app_key.invalid`; valid hash set cached 60 s (`REDIS_APP_KEYS_KEY`). `invalidate_app_key_cache()` — M2 calls after create/revoke. `get_valid_app_key_hash_set(session)`.
- Read-side crud (`src/crud/freespace_keys.py`): `ingest_key_is_valid(key, now)`, `get_ingest_key_with_site_by_hash(session, hash) -> (IngestKey, Site) | None`, `touch_ingest_key(session, key, now, ip)`, `get_valid_app_key_hashes(session) -> set[str]`.

### 3.18 Mock mode — `src/services/freespace/mock_mode.py` (implemented)
`validate_mock_mode(settings)` raises `MockModeConfigurationError` when mock on, DEBUG off and not acknowledged — called first thing in `main.create_application()`. `mock_routes_enabled(settings)`. `src/api/freespace_public/__init__.py: include_freespace_public_routers(app, settings)` mounts `public_router` at `/v1` and `mock_router` at root only in mock mode.

---

## 4. Routes (all routers already registered)

Public (no `/api` prefix), mounted by `main.py` via `include_freespace_public_routers`:

| File | Router prefix | Full paths to implement |
|---|---|---|
| `src/api/freespace_public/ingest.py` (M3) | `/ingest` | `GET /v1/ingest/ping`, `POST /v1/ingest/occupancy` |
| `src/api/freespace_public/app_sites.py` (M4) | `/sites` | `GET /v1/sites`, `GET /v1/sites/{site_slug}/availability` |
| `src/api/freespace_public/devices.py` (M5) | `/devices` | `PUT/DELETE /v1/devices/{device_id}` |
| `src/api/freespace_public/mock.py` (M10) | `/mock` (root, mock mode only) | `POST /mock/sites/{site_slug}/occupancy`, `POST /mock/clock` |

Admin (under `/api/v1` via `v1_router`; sites addressed by row **UUID** `{site_id}`), include order in `src/api/v1/__init__.py`: stats → events → push → keys → app keys → zones → **sites last** (rule 13):

| File | Router prefix | Paths (suggested) | Permission |
|---|---|---|---|
| `freespace_stats.py` (M8) | `/admin/sites` | `GET /summary`, `GET /device-stats`, `GET /{site_id}/live`, `GET /{site_id}/device-stats`, `GET /{site_id}/history` | `sites:read` |
| `freespace_events.py` (M8) | `/admin/sites/{site_id}/events` | `GET ""`, `GET /export.csv` | `site_events:read` |
| `freespace_push.py` (M8) | `/admin/sites/{site_id}` | `POST /test-push`, `POST /announcements` | `site_push:test`, `site_push:announce` |
| `freespace_keys.py` `router` (M2) | `/admin/sites/{site_id}/ingest-keys` | `GET ""`, `POST ""`, `POST /{key_id}/revoke` | `sites:read` (list), `site_keys:write` |
| `freespace_keys.py` `app_keys_router` (M2) | `/admin/app-keys` | `GET ""`, `POST ""`, `POST /{key_id}/revoke` | super admin (`get_current_super_admin`) |
| `freespace_zones.py` (M1) | `/admin/sites/{site_id}/zones` | `GET ""`, `POST ""`, `GET/PUT/DELETE /{zone_id}` | `sites:read` / `sites:write` |
| `freespace_sites.py` (M1) | `/admin/sites` | `GET ""`, `POST ""`, `GET/PUT/DELETE /{site_id}`, `GET/PUT /{site_id}/config`, `GET/PUT /{site_id}/templates` | `sites:read` / `sites:write` |

A NEW literal single-segment path under `/admin/sites/` must live in `freespace_stats.py` (or be reported), never in a router included after `freespace_sites`.

---

## 5. Conventions

- **Wire format (`/v1`)**: Pydantic models with camelCase aliases — `model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)` (`from pydantic.alias_generators import to_camel`), return with `response_model_by_alias=True` (FastAPI default). Timestamps ISO-8601 UTC with `Z` (`dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")`). **Ingest request models use `extra="ignore"`** (not `forbid`, D15); app/device request models may use `forbid`. Malformed bodies keep FastAPI's default 422 shape (field path, BF-12). Keep intake/ping responses tiny (BF-19).
- **Admin wire format**: template convention (snake_case, `{Operation}{Entity}Request/Response`, `extra="forbid"`, mutation responses with `message` + `message_code`), serialisers in `src/serialisers/freespace_*.py`.
- **Errors**: always `create_http_exception(status_code, detail, detail_code)` with a code from §6. 3-tier handling (ValueError → 400, re-raise HTTPException, Exception → log + `request.state.error_traceback` + 500 `common.internal_error`). Codes not in `RESPONSE_CODES` become 500s.
- **Clock rule (D8)**: no `datetime.now(`, `.utcnow(`, `date.today(`, `datetime.today(` in `src/services/freespace/**`, `src/api/freespace_*.py`, `src/api/freespace_public/**`, `src/crud/freespace_*.py`, `src/serialisers/freespace_*.py`, `src/workers/freespace_*.py` (enforced by `tests/freespace/test_foundation_clock.py`). Endpoints: `clock: Annotated[Clock, Depends(get_clock)]`. Pure functions take `now`.
- **Events**: build an `EventDraft`, call `events.write_event` inside your transaction; include `figures` and the recommendation for engine decisions; `details` must stay small and contain no device data.
- **Tenant scoping for admin endpoints (D2, Q2)**: resolve the site with `site.id == site_id AND deleted_time IS NULL` and, unless `current_user.is_admin` (super admin, sees every customer), `site.organization_id == UUID(current_user.organization_id)`; otherwise **404** `site.not_found` (never 403 across tenants). Every child row (zones, keys, events, templates, push_send) is then filtered by that `site_id` (and its `organization_id`). Site creation: non-super-admins create in their own org; super admins may pass a target `organization_id` (validate it exists → `site.organization_not_found`). Each CRUD endpoint needs a tenant-isolation test using `fs_second_org_admin_token` / `fs_second_site`.
- **Public endpoints** resolve the site only by key (ingest) or slug (app) — the only unscoped reads (D2). App: unknown OR unlisted slug → 404 `site.not_found`.
- **Rate limits**: app endpoints use slowapi (`from src.core.rate_limit import limiter`, `@limiter.limit(settings.RATE_LIMIT_FREESPACE_…)`; the endpoint needs a `request: Request` param). Device per-id limit: `key_func` returning `"fsdev:" + hash_device_id(device_id)`. Ingest (BF-18): M2's Redis limiter keyed by ingest key id (`REDIS_INGEST_RATE_KEY_FMT`), 429 with integer `Retry-After` 1–600, `settings.RATE_LIMIT_FREESPACE_INGEST` ("12/minute").
- **Hard deletes** only: `device_site` rows on opt-out (M5), retention purges (M9), test cleanup.
- **Audit (BF-77)**: config changes use `audit_service.log_update(...)` AND a `CONFIG_CHANGED` event.
- **Push wording**: "accepted by FCM", never "delivered" (BF-69).

---

## 6. Response codes (registered in `src/core/response_codes.py`, English copy in `app/frontend/src/locales/en/backend.json`)

- `ingest.`: `unauthorized`, `key_revoked`, `key_expired`, `site_mismatch`, `clock_skew`, `rate_limited`, `invalid_payload`, `site_not_found`
- `app_key.`: `invalid`, `created`, `revoked`, `deleted`, `not_found`, `already_revoked`, `name_conflict`
- `ingest_key.`: `created`, `updated`, `revoked`, `deleted`, `not_found`, `already_revoked`, `name_conflict`, `invalid_expiry`
- `site.`: `not_found`, `created`, `updated`, `deleted`, `config_updated`, `slug_conflict`, `invalid_slug`, `invalid_settings`, `invalid_time_zone`, `invalid_notification_window`, `invalid_topic`, `organization_not_found`
- `zone.`: `not_found`, `created`, `updated`, `deleted`, `reviewed`, `slug_conflict`, `invalid_slug`, `invalid_settings`
- `site_template.`: `not_found`, `updated`, `reset`, `invalid`, `invalid_placeholder`, `unknown_type`
- `device.`: `invalid_id`, `unknown_site`, `invalid_token`, `ceiling_reached`, `rate_limited`, `registered`, `deleted`
- `site_push.`: `test_sent`, `test_failed`, `device_not_found`, `device_ambiguous`, `device_no_token`, `confirmation_required`, `confirmation_mismatch`, `invalid_target`, `announcement_sent`, `announcement_failed`, `fcm_not_configured`, `fcm_auth_failure`
- `site_event.`: `not_found`, `invalid_filter`, `invalid_period`, `export_too_large`
- `site_stats.`: `invalid_period`, `invalid_date`
- `mock.`: `clock_advanced`, `clock_reset`, `invalid_clock_request`, `occupancy_set`, `redis_unavailable`
- Generic: use `common.*` (`common.internal_error`, `common.validation_error`, `common.service_unavailable`, …).

The BF-12/BF-13 wire bodies that are not errors (`{"ignored": "OUT_OF_ORDER"}`) are plain responses, not codes.

## 7. Permissions and roles (seeded by the shared seeder)

Permissions (`scripts/seed_data/permissions.yaml`): `sites:read`, `sites:write`, `site_keys:write`, `site_push:test`, `site_push:announce`, `site_events:read`, `site_alerts:receive`.
Grants (`scripts/seed_data/role_permissions.yaml`): `owner`, `admin` → all seven; `operator` (new role in `DEFAULT_ROLES`, hierarchy level 2) → `sites:read`, `site_events:read`, `site_push:test`; `viewer` → `sites:read`, `site_events:read`. Announcements are Administrator only (BF-75, Q7). Super admins bypass all checks. Alerts (M9) go to users holding `site_alerts:receive`.

## 8. Configuration

`config.json` (`Settings` field ← JSON key): `FREESPACE_MOCK_MODE` ← `freespace.mock_mode`, `FREESPACE_MOCK_MODE_ACKNOWLEDGED` ← `freespace.mock_mode_acknowledged`, `FREESPACE_FCM_CREDENTIALS_PATH` ← `freespace.fcm_credentials_path`, `FREESPACE_FCM_PROJECT_ID` ← `freespace.fcm_project_id`; `RATE_LIMIT_FREESPACE_AVAILABILITY` (60/minute) ← `rate_limit.freespace_availability`, `RATE_LIMIT_FREESPACE_SITES` (30/minute) ← `rate_limit.freespace_sites`, `RATE_LIMIT_FREESPACE_DEVICE_PER_ID` (10/minute) ← `rate_limit.freespace_device_per_id`, `RATE_LIMIT_FREESPACE_DEVICE_PER_IP` (30/minute) ← `rate_limit.freespace_device_per_ip`, `RATE_LIMIT_FREESPACE_INGEST` (12/minute) ← `rate_limit.freespace_ingest`. Under pytest `settings` is the in-code default (mock mode off); patch with `monkeypatch.setattr(settings, ...)`.
SystemConfig: see §3.6. Dependencies installed: `httpx[http2]==0.28.1`, `google-auth==2.38.0`.

## 9. Test fixtures — `tests/freespace/conftest.py`

Autouse in every Freespace test: `fs_redis` (fresh fakeredis async client wired into `redis_client`), `fixed_clock` (`FixedClock` at **2026-11-24T05:45:00Z** = Tue 07:45 SAST, installed as the clock override, so API requests through the root `client` fixture and worker helpers use it), `fake_fcm` (`FakeFcmClient` installed as FCM override).
Opt-in:
- Roles/users: `fs_roles` (`FsRoles.roles` / `.permissions`; grants mirror the seed YAML), `fs_admin_user` / `fs_admin_token`, `fs_operator_user` / `fs_operator_token`, `fs_viewer_user` / `fs_viewer_token`, `fs_no_role_user` / `fs_no_role_token`, `fs_second_org_admin_user` / `fs_second_org_admin_token`; super admin = root `test_admin_user` / `test_admin_token`. Tokens include `Bearer `.
- Sites: `fs_site` (managed, listed `absa-alice-lane` in `test_organization`, engine-state row + default templates), `fs_second_site` (`other-customer-site` in `second_organization`), `fs_zones` (`{"b1".."b4": Zone}` enabled, names "Basement N", display order 1–4).
- `fs_snapshot` builder: `await fs_snapshot(site, capacity=…, occupied=…, [free_usable, free_reserved, free_disabled, unknown, health, reported_health], received_at=None, measured_at=None, zones={"b1": {"capacity": …, "occupied": …, [same keys, received_at]}})` — overwrites the latest snapshot rows; defaults keep the BF-12 sum consistent and use `fixed_clock.now()`.
- Keys: `fs_ingest_key` → `(plaintext, IngestKey)`, `fs_ingest_headers` → `{"Authorization": "Bearer …"}`, `fs_app_key` → `(plaintext, AppKey)`, `fs_app_headers` → `{"X-Freespace-App-Key": …}`.
- Helpers (import from `tests.freespace.conftest`): `make_site(session, org, *, slug, name, managed, listed, now, **site_columns)`, `make_zone(session, site, slug, *, name, display_order, enabled, **zone_columns)`, `make_ingest_key(session, site, *, name, **columns)`, `make_app_key(session, *, name, **columns)`, `unique_slug(prefix)`, constants `FIXED_START`, `SITE_SLUG`, `SECOND_SITE_SLUG`.
- PostgreSQL (BT-01/BT-02): `fs_pg_engine` (skips unless `TEST_DATABASE_URL_DIRECT` points at a migrated DB, e.g. `postgresql+asyncpg://freespace:freespace@localhost:5432/freespace`); mark tests `@pytest.mark.postgres`; they commit for real and must delete what they create.
- Root fixtures still available: `async_session`, `client` (real `main.app`, session overridden), `test_organization`, `second_organization`, `test_user`, `test_admin_user`, `test_admin_token`, `mock_task_queue_enqueue_job` (autouse; patch `task_queue.enqueue_job` with `monkeypatch` to assert enqueues).
- Tips: after `rollback()` or `expire_all()` re-read attributes with `await session.refresh(obj)` before touching them (async lazy load → `MissingGreenlet`). SQLite ignores `FOR UPDATE` and returns naive datetimes.

Scoped command: `cd app/backend && .venv/bin/pytest tests/freespace -q -n 4`.

## 10. Deviations from the plan made by M0

1. Slug columns are named `slug` (`site.slug`, `zone.slug`) and zone references in engine state/events are `*_zone_slug`; the plan's `site.site_id` / `zone.zone_id` / `current_zone_id` naming would collide with the FK columns `site_id`/`zone_id`.
2. Extra columns: `site_engine_state.{last_notified_top_zones, last_sent_at, stale, stale_since, inflight_event_id, inflight_fingerprint, last_evaluated_at, ops_alert_state}`, `site_event.{last_seen_at, advisory_type, zone_slug, cycle_id, details}`, snapshots `reported_health`, `push_send.{organization_id, queued_at, error_code}`, keys `key_hint` on app keys. Needed for BF-57 (top-two), D10 in-flight guard, D11 collapse, BF-82 alert state.
3. `occupancy_history` uses two partial unique indexes instead of one UNIQUE with nullable `zone_id` (NULLs are distinct in PostgreSQL), and a BIGINT pk.
4. Request-log retention reuses the existing SystemConfig key `request_logs.retention_days` instead of a new `freespace.retention.request_logs_days`.
5. `engine.evaluate` additionally takes `templates`; `on_fanout_completed` and `event_figures` added to the engine contract.
6. `site.listed` defaults to False (spec gives no default; a new site stays hidden until configured).
7. The mock-mode guard runs at the top of `create_application()` (when `main` is imported), not in the lifespan, so no route of an unsafe app is ever built. It is not skipped under TESTING; under pytest mock mode is off by default.

## 11. Integration step (what now differs from §1–§4)

- **Shared functions added by modules:** `intake.ingest_snapshot(session, site, payload, clock) -> IntakeResult` (M3; also used by `/mock`), `fcm.send_to_topic(fcm, *, topic, title, body, message_type, ...)` (M7, announcements/test push), `fanout.record_fcm_auth_failure` / `register_fcm_auth_failure_hook` (Redis `freespace:fcm:auth_failure`), `fanout.fail_fanout_credentials_missing(session_factory, event_id, *, clock)` (FCM not configured: event FAILED through the normal finish path, `FCM_ERROR / CREDENTIALS_MISSING`, engine in-flight released; called by `fanout_advisory_task` when `get_fcm_client()` raises), `devices.record_device_ceiling_alert`.
- **Alert hooks (BF-82):** `evaluator.run_engine_tick` calls `alerts.run_alert_checks(session, clock)` last, on its own session, failures logged into `TickResult.errors` only. `alerts.record_ingest_rejection(key_id | None, now)` is called for every ingest 401 in `freespace_deps.get_ingest_site` (unknown/malformed key: `None`) and before the 429 in `ingest_rate_limit`. Category `site_operations`, five `freespace_*` email templates in `notification_templates.yaml`.
- **Cron:** `freespace_daily_purge` (03:30 daily) registered; `cleanup_old_request_logs` now runs `cleanup_old_request_logs_configured_handler` (honours `request_logs.retention_days`).
- **Health:** `GET /health` = BF-80 verdict (`health.check_health`, 200/503, `no-store`, status only, uptime monitoring); `GET /health/live` = constant liveness (container/deploy probes). Both exempt from the global per-IP limit; `/health/live` excluded from request logs.
- **`main.py`:** rate-limit metrics and the unhandled-exception log use the route template, never the raw path; 429s under `/v1/` return `{"detail", "detail_code"}` (`device.rate_limited`, `ingest.rate_limited`, else `common.rate_limited`) with an integer `Retry-After` 1–600.
- **Events:** D11 collapse breaks ties between events with equal timestamps in write order (ingest, state events, then CANDIDATE/ADVISORY, site before zone, then id).
- **Templates:** length limits only in `templates.validate_template` (title 255, body 2000); `TemplateInput` no longer caps length.
- **Mock:** `/mock/clock` runs the tick over the request session through a factory that rolls the session back when a site's evaluation fails.
