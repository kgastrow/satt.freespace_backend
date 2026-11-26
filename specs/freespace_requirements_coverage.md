# Freespace backend: requirement coverage

Derived on 2026-11-26 from the code and the tests (not from earlier reports), against
`specs/BACKEND_FUNCTIONAL_DESCRIPTION.md`. Paths are relative to `app/backend/` unless they start
with `frontend/`. Tests are `file::test` (class names are written as `Class.test`). Every named test
was checked to exist, and it passes in the final run (backend `pytest tests/ -n 8`; PostgreSQL-only
tests with `TEST_DATABASE_URL_DIRECT` set; frontend `npx vitest run`).

Status values:
- **covered**: a named test fails if the requirement is broken.
- **partial**: some of the requirement is tested and the rest is not (see the note).
- **not covered**: no test.
- **deployment-only**: can only be checked on the deployed host.
- **process-only**: an organisational rule, not software.

`PG` marks a test that runs only against real PostgreSQL (`TEST_DATABASE_URL_DIRECT`). It is skipped
otherwise, so CI must provide PostgreSQL or these are not run.

Abbreviations: `sf/` = `src/services/freespace/`, `tf/` = `tests/freespace/`.

## Data (§4)

| id | requirement | implementing file(s) | test(s) | status | note |
|---|---|---|---|---|---|
| BF-1 | Site: slug, name, customer, tz, topic, managed, listed, settings, templates | `src/models/site.py`, `sf/site_bootstrap.py`, `src/api/freespace_sites.py` | `tf/test_foundation_loaders.py::TestSiteBootstrap.test_site_defaults`, `tf/test_m1_sites_api.py::TestSitesCrud.test_create_uses_bootstrap`, `tf/test_foundation_loaders.py::TestSchemaConstraints.test_site_slug_unique_among_live_rows` | covered | |
| BF-2 | Zone: slug, name, order, enabled, recommendable, preferred, priority, settings, discovered | `src/models/zone.py`, `src/api/freespace_zones.py` | `tf/test_m1_zones_api.py::TestCrud.test_create_defaults`, `tf/test_m1_zones_api.py::TestDiscoveredReview.test_review_clears_flag`, `tf/test_foundation_loaders.py::TestSchemaConstraints.test_zone_slug_unique_per_site` | covered | Capacity is not editable: no field in `CreateZoneRequest`. |
| BF-3 | Latest snapshot per site and zone, overwritten, measuredAt + receivedAt | `src/models/site_snapshot.py`, `sf/intake.py` | `tf/test_m3_intake.py::test_snapshot_rows_written_and_overwritten` | covered | |
| BF-4 | Occupancy history, at most one point per minute | `src/models/occupancy_history.py`, `sf/intake.py` | `tf/test_m3_history.py::test_history_one_point_per_minute_last_wins`, `tf/test_m3_history.py::test_postgres_history_upsert_partial_indexes` (PG) | covered | |
| BF-5 | Engine state persisted; restart neither re-sends nor forgets | `src/models/site_engine_state.py`, `sf/evaluator.py`, `sf/loaders.py` | `tf/test_foundation_loaders.py::TestEngineStateRoundtrip.test_all_fields_survive`, `tf/test_m6_evaluator.py::TestEvaluateSite.test_restart_safety` | covered | |
| BF-6 | Device fields | `src/models/device.py`, `sf/devices.py` | `tf/test_m5_devices.py::test_put_creates_and_returns_registration` | covered | The raw `deviceId` is never stored (hash + 6-character suffix, D5). |
| BF-7 | Send history per device (time, site, type, fingerprint, event) | `src/models/push_send.py`, `src/crud/freespace_push_send.py` | `tf/test_m7_fanout.py::test_fanout_sends_once_per_device_and_writes_counts`, `tf/test_m7_fanout.py::test_reasons_and_their_order` | covered | |
| BF-8 | Event log | `src/models/site_event.py`, `sf/events.py` | `tf/test_foundation_events.py::test_insert_maps_all_fields` | covered | See BF-62. |
| BF-9 | Ingest keys: several per site, rotate, revoke, expiry, hashed, shown once; ≥2 app keys | `sf/keys.py`, `src/api/freespace_keys.py`, `src/api/freespace_deps.py` | `tf/test_m2_keys.py::TestCreateIngestKey.test_format_and_shown_once`, `tf/test_m2_keys.py::TestCreateIngestKey.test_expiry`, `tf/test_foundation_deps.py::TestIngestKey.test_expired_key`, `tf/test_foundation_deps.py::TestAppKey.test_two_keys_valid_at_once`, `tf/test_foundation_keys.py::TestIngestKeys.test_hash_is_sha256_hex_and_deterministic` | covered | |

## Intake (§5)

| id | requirement | implementing file(s) | test(s) | status | note |
|---|---|---|---|---|---|
| BF-10 | Bearer ingest key bound to one site; other siteId → 403 + `INGEST_REJECTED/SITE_MISMATCH` | `src/api/freespace_deps.py`, `src/api/freespace_public/ingest.py` | `tf/test_m3_intake.py::test_bt03_site_mismatch_403_event_nothing_stored`, `tf/test_foundation_deps.py::TestIngestKey.test_key_is_bound_to_its_own_site` | covered | |
| BF-10a | Key format `^[\x21-\x7e]{1,512}$`, ≥256 bits | `sf/keys.py` | `tf/test_foundation_keys.py::TestIngestKeys.test_format`, `tf/test_foundation_keys.py::TestKeyFormat.test_accepts_printable_ascii`, `tf/test_foundation_keys.py::TestKeyFormat.test_rejects_space_control_empty_and_long` | covered | `fsk_` + 43 base64url characters. |
| BF-10b | Rotation overlaps: two valid keys per site | `src/api/freespace_keys.py` | `tf/test_m2_keys.py::TestKeyLifecycleOnIngestAuth.test_two_keys_and_revocation_effect`, `tf/test_foundation_deps.py::TestIngestKey.test_two_valid_keys_for_one_site` | covered | |
| BF-11 | `GET /v1/ingest/ping` shape | `src/api/freespace_public/ingest.py` | `tf/test_m3_intake.py::test_ping_shape` | covered | |
| BF-12 | Validation, sum check → accepted + `INGEST_INCONSISTENT` + PARTIAL; malformed → 422 with path | `sf/intake.py`, `src/serialisers/freespace_ingest.py` | `tf/test_m3_intake.py::test_bt11_sum_mismatch_accepted_inconsistent_partial`, `tf/test_m3_intake.py::test_site_block_mismatch_marks_site_partial_offline_kept`, `tf/test_m3_intake.py::test_malformed_body_422_with_field_path` | covered | |
| BF-13 | Staleness on receivedAt; +120 s skew → 422 `CLOCK_SKEW`; out-of-order ignored | `sf/intake.py` | `tf/test_m3_intake.py::test_bt04_clock_skew_422`, `tf/test_m3_intake.py::test_skew_within_limit_accepted`, `tf/test_m3_intake.py::test_out_of_order_ignored_without_overwrite`, `tf/test_m3_intake.py::test_staleness_uses_received_at` | covered | |
| BF-14 | Unknown zone → discovered (disabled); missing zone keeps last values | `sf/intake.py` | `tf/test_m3_intake.py::test_unknown_zone_discovered`, `tf/test_m3_intake.py::test_missing_zone_keeps_last_values` | covered | |
| BF-15 | Response shape | `src/serialisers/freespace_ingest.py` | `tf/test_m3_intake.py::test_accepted_response_shape_exactly_bf15`, `tf/test_m3_intake.py::test_response_reports_evaluator_view_and_enqueues_after_commit` | covered | |
| BF-16 | Each submission evaluates; response does not wait for fan-out | `sf/intake.py`, `sf/evaluator.py` | `tf/test_m3_intake.py::test_response_reports_evaluator_view_and_enqueues_after_commit`, `tf/test_m3_intake.py::test_evaluator_failure_keeps_snapshot` | covered | |
| BF-17 | No backlog expected or requested | `sf/intake.py` | `tf/test_m3_intake.py::test_out_of_order_ignored_without_overwrite` | partial | This rule says what the backend must not do. There is no backlog endpoint, so nothing more can be tested. |
| BF-18 | 12/min per key; 429 with integer Retry-After 1–600 | `sf/ingest_rate_limit.py` | `tf/test_m2_ingest_rate_limit.py::TestLimiter.test_13th_request_429`, `tf/test_m2_ingest_rate_limit.py::TestHelpers.test_clamp`, `tf/test_m3_intake.py::test_rate_limit_429_retry_after` | covered | |
| BF-19 | Responses small (< 64 KB); short warnings list | `sf/intake.py` | `tf/test_m3_intake.py::test_warnings_capped_and_response_small` | covered | |

## Availability and app endpoints (§6)

| id | requirement | implementing file(s) | test(s) | status | note |
|---|---|---|---|---|---|
| BF-20 | Exact ratio for rules; app shows floor | `sf/availability.py` | `tf/test_m4_availability_core.py::test_floor_never_shows_90_before_rule_fires`, `tf/test_m4_app_endpoints.py::test_availability_floor_89_9_shows_89`, `tf/test_m6_engine_core.py::TestStateMachine.test_exact_ratio_below_trigger` | covered | |
| BF-21 | Zone staleness rules | `sf/availability.py` | `tf/test_m4_availability_core.py::test_is_zone_stale`, `tf/test_m4_availability_core.py::test_zone_unknown_limit_is_per_zone` | covered | |
| BF-22 | Site staleness rules | `sf/availability.py` | `tf/test_m4_availability_core.py::test_is_site_stale`, `tf/test_m4_availability_core.py::test_compute_site_offline_is_stale_even_with_fresh_zones` | covered | |
| BF-23 | Zone status UNKNOWN/FULL/LIMITED/AVAILABLE | `sf/availability.py` | `tf/test_m4_availability_core.py::test_zone_status` | covered | |
| BF-24 | Recommended zone: candidates, ranking, stickiness, null when stale; app = engine | `sf/availability.py` | `tf/test_m4_availability_core.py::test_rank_order_free_desc_priority_asc_slug_asc`, `tf/test_m4_availability_core.py::test_sticky_recommendation`, `tf/test_m4_availability_core.py::test_compute_site_stale_nulls_recommendation_but_keeps_zone_rows`, `tf/test_m4_app_endpoints.py::test_stored_recommendation_is_stickiness_input`, `tf/test_m8_admin_ops.py::TestLive.test_live_equals_app_endpoint` | covered | |
| BF-25 | Top two zones = first two candidates | `sf/availability.py`, `sf/templates.py` | `tf/test_m4_availability_core.py::test_top_two`, `tf/test_m1_templates.py::TestRender.test_format_top_zones` | covered | |
| BF-30 | `GET /v1/sites`: listed sites, fields, ordered by name; app key 401 | `src/api/freespace_public/app_sites.py`, `src/api/freespace_deps.py` | `tf/test_m4_app_endpoints.py::test_site_list_only_listed_live_sites_ordered_by_name`, `tf/test_m4_app_endpoints.py::test_missing_app_key_is_401`, `tf/test_m4_app_endpoints.py::test_revoked_app_key_is_401` | covered | Wrapped as `{"sites": [...]}` (see decisions). |
| BF-31 | Availability shape; never-received; unknown/unlisted 404; UNKNOWN zones listed in order | `src/api/freespace_public/app_sites.py`, `src/serialisers/freespace_app.py` | `tf/test_m4_app_endpoints.py::test_availability_full_shape`, `tf/test_m4_app_endpoints.py::test_never_received_site`, `tf/test_m4_app_endpoints.py::test_unlisted_site_is_404`, `tf/test_m4_app_endpoints.py::test_disabled_and_deleted_zones_hidden_unreported_shown_unknown`, `tf/test_m4_app_endpoints.py::test_display_order_respected` | covered | |
| BF-32 | Reads never evaluate or push; cache ≤5 s, `Cache-Control: max-age=5` | `sf/availability_cache.py`, `src/api/freespace_public/app_sites.py` | `tf/test_m4_app_endpoints.py::test_read_writes_nothing`, `tf/test_m4_app_endpoints.py::test_cache_serves_within_5s_and_recomputes_after`, `tf/test_m4_app_endpoints.py::test_cache_stale_flag_never_more_than_5s_late` | covered | |
| BF-33 | Device PUT: idempotent, id pattern, unknown sites 422, token moves, lastSeen | `sf/devices.py`, `src/api/freespace_public/devices.py` | `tf/test_m5_devices.py::test_put_is_idempotent_and_updates_last_seen`, `tf/test_m5_devices.py::test_invalid_device_id_is_422`, `tf/test_m5_devices.py::test_unknown_site_is_422_and_nothing_stored`, `tf/test_m5_devices.py::test_unlisted_site_is_422`, `tf/test_m5_devices.py::test_token_moves_to_new_device` | covered | |
| BF-34 | Device DELETE erases token and selections; tombstone; 204 always | `src/crud/freespace_devices.py`, `src/api/freespace_public/devices.py` | `tf/test_m5_devices.py::test_delete_erases_everything_but_a_tombstone`, `tf/test_m5_devices.py::test_delete_unknown_malformed_and_repeat_are_204` | covered | |
| BF-35 | deviceId never in logs, event log, back office, other responses | `src/middleware/request_response_logging.py`, `src/middleware/metrics.py`, `deploy/nginx.conf`, `src/database.py` | `tf/test_m5_log_privacy.py::test_put_and_delete_leave_no_trace`, `tf/test_m5_log_privacy.py::test_unmatched_device_path_is_not_logged_raw`, `tf/test_m5_log_privacy.py::test_rate_limit_metrics_do_not_expose_the_id`, `tf/test_m4_review_fixes.py::test_uvicorn_access_log_is_off_everywhere`, `tf/test_m8_admin_ops.py::TestDeviceStats.test_counts_and_privacy`, `tf/test_m9_alerts.py::test_alerts_contain_no_device_data` | partial | Application paths are covered. The nginx `freespace_masked` log format is not tested (no `nginx -t`). `make dev` (`uvicorn --reload`) still prints access-log lines with the raw id (seen in the smoke test). Deployed units use `--no-access-log`. |
| BF-36 | Per-IP limits: availability 60, sites 30, device 10/deviceId + 30/IP | `src/api/freespace_public/*.py`, `src/core/config.py` | `tf/test_m4_app_endpoints.py::test_availability_rate_limited_per_ip`, `tf/test_m4_app_endpoints.py::test_sites_rate_limited_per_ip`, `tf/test_m5_devices.py::test_per_device_limit_is_10_a_minute`, `tf/test_m5_devices.py::test_per_device_limit_applies_to_delete`, `tf/test_m5_devices.py::test_per_ip_limit_is_30_a_minute` | covered | The real client IP needs `server.trusted_client_ip_header` in production (deployment). |
| BF-37 | Device ceiling (50 000) → 503 + alert | `sf/devices.py`, `sf/alerts.py` | `tf/test_m5_devices.py::test_ceiling_blocks_new_but_not_existing`, `tf/test_m9_alerts.py::test_device_ceiling_alert_once_per_window` | covered | |

## Topics (§7)

| id | requirement | implementing file(s) | test(s) | status | note |
|---|---|---|---|---|---|
| BF-40 | App subscribes itself; backend never manages subscriptions | none (nothing to build) | none | partial | A rule about what the backend must not do. No subscription API is called anywhere in `src/` (checked by grep), but no test enforces it. |
| BF-41 | Topic sends only for announcement / test push; advisories to tokens | `sf/fcm.py`, `sf/admin_push.py`, `sf/fanout.py` | `tf/test_m7_fanout.py::test_fanout_sends_once_per_device_and_writes_counts`, `tf/test_m7_fcm.py::test_send_to_topic_helper`, `tf/test_m8_admin_ops.py::TestAnnouncement.test_admin_sends_one_topic_call`, `tf/test_m8_admin_ops.py::TestTestPush.test_topic_confirmation` | covered | |

## Rules engine (§8)

| id | requirement | implementing file(s) | test(s) | status | note |
|---|---|---|---|---|---|
| BF-50 | Evaluate on every submission and once a minute | `sf/evaluator.py`, `src/workers/freespace_tasks.py`, `src/workers/worker.py` | `tf/test_m6_evaluator.py::TestTick.test_tick_evaluates_all_isolates_failures_and_records`, `tf/test_foundation_mounts.py::TestWorkerWrappers.test_registered_in_worker`, `tf/test_m3_intake.py::test_response_reports_evaluator_view_and_enqueues_after_commit` | covered | The tick also covers unmanaged sites (decision). |
| BF-51 | One evaluator per site (row lock) | `sf/evaluator.py` | `tf/test_m6_postgres.py::test_bt01_concurrent_evaluations_one_advisory` (PG) | covered | PG only. |
| BF-52 | Record before send; resume never re-sends | `sf/evaluator.py`, `sf/fanout.py`, `src/crud/freespace_push_send.py` | `tf/test_m7_fanout.py::test_crash_between_commit_and_send_never_resends`, `tf/test_m7_fanout.py::test_crash_between_send_and_outcome_update_never_resends`, `tf/test_m7_fanout_review.py::test_crashed_pending_rows_finish_as_unknown_and_still_count`, `tf/test_m7_unknown_acceptance.py::test_client_exception_counts_for_cooldown_and_is_not_retried`, `tf/test_m7_fanout_postgres.py::test_bt02_killed_mid_fanout_then_restarted` (PG) | covered | |
| BF-53 | Stale timers do not advance | `sf/engine.py` | `tf/test_m6_engine_core.py::TestStateMachine.test_bf53_stale_during_pending_restarts_stabilisation`, `tf/test_m6_engine_core.py::TestStateMachine.test_stale_pending_below_trigger_on_return_is_not_stable` | covered | |
| BF-54 | Last-notified advances only when sent to ≥1 | `sf/engine.py`, `sf/fanout.py` | `tf/test_m6_engine_core.py::TestLastNotified.test_suppressed_candidate_does_not_advance`, `tf/test_m6_engine_core.py::TestLastNotified.test_sent_advances_everything`, `tf/test_m6_engine_core.py::TestLastNotified.test_zero_sent_keeps_transition_values` | covered | |
| BF-55 | Only rises count; `BOTH` option | `sf/engine.py` | `tf/test_m6_engine_core.py::TestStateMachine.test_bf55_rising_ignores_falls`, `tf/test_m6_engine_core.py::TestStateMachine.test_bf55_both_counts_falls_above_reset` | covered | |
| BF-56 | Zone advisory: preferred + advisoryPct, held S, once per cycle, reset gap, IDLE/PENDING only | `sf/engine.py` | `tf/test_m6_engine_core.py::TestZoneAdvisory.test_once_per_cycle_and_reset_gap`, `tf/test_m6_engine_core.py::TestZoneAdvisory.test_requires_hold_for_s`, `tf/test_m6_engine_core.py::TestZoneAdvisory.test_not_while_site_active`, `tf/test_m6_engine_core.py::TestZoneAdvisory.test_full_by_free_bays_counts` | covered | Per-phone limits apply to it through the same fan-out (BF-58). |
| BF-57 | Fingerprint; NO_MATERIAL_CHANGE; NO_RECOMMENDATION | `sf/templates.py`, `sf/engine.py` | `tf/test_m6_engine_core.py::TestUsefulness.test_fingerprint_equal_to_last_sent`, `tf/test_m6_engine_core.py::TestUsefulness.test_site_change_unchanged_recommendation_and_top_two`, `tf/test_m6_engine_core.py::TestUsefulness.test_no_recommendation`, `tf/test_m1_templates.py::TestFingerprint.test_top_zone_set_is_order_insensitive_for_initial` | covered | |
| BF-58 | Per-device checks in order; SENT/SEND_FAILED | `sf/limits.py`, `src/crud/freespace_push_send.py`, `sf/fanout.py`, `src/constants/freespace.py` (`send_counts_towards_limits`) | `tf/test_m7_limits.py::test_first_failure_wins_in_spec_order`, `tf/test_m7_fanout.py::test_reasons_and_their_order`, `tf/test_m7_fanout.py::test_duplicate_is_bounded_to_the_cycle`, `tf/test_m7_unknown_acceptance.py::test_counting_rule`, `tf/test_m7_unknown_acceptance.py::test_definite_failure_does_not_count` | covered | |
| BF-59 | Suppressed advisories never queued for later | `sf/fanout.py` | `tf/test_m7_fanout.py::test_expired_advisory_is_never_sent_late`, `tf/test_m7_fanout.py::test_reasons_and_their_order` | covered | A suppressed device gets a final `push_send` row, so it is never claimed again. |
| BF-60 | TEST bypasses and is not counted; RECOVERY counted | `src/constants/freespace.py`, `sf/fanout.py`, `sf/admin_push.py` | `tf/test_m7_fanout.py::test_test_push_bypasses_checks_and_is_not_counted`, `tf/test_m7_fanout.py::test_recovery_counts_towards_limits` | covered | |
| BF-61 | Unmanaged: nothing sent, candidates `UNMANAGED` | `sf/engine.py`, `sf/fanout.py` | `tf/test_m6_engine_core.py::TestShadowMode.test_bt09_unmanaged_logged_nothing_sent`, `tf/test_m7_fanout.py::test_unmanaged_site_sends_nothing`, `tf/test_m6_evaluator.py::TestEvaluateSite.test_unmanaged_shadow_mode` | covered | Also confirmed in the smoke test. |
| BF-62 | Event types, figures, counts, rendered text, latency, start/finish | `sf/events.py`, `sf/fanout.py`, `src/api/freespace_events.py` | `tf/test_m6_engine_core.py::TestEventFigures.test_shape_and_every_decision_has_figures`, `tf/test_m7_fanout.py::test_fanout_sends_once_per_device_and_writes_counts`, `tf/test_m6_evaluator.py::TestEvaluateSite.test_persists_state_and_events`, `tf/test_m8_admin_ops.py::TestEvents.test_list_filters_and_pagination` | covered | |
| BF-63 | limitScope DEVICE / DEVICE_PER_SITE; "today" in the right zone | `sf/limits.py`, `sf/deployment_settings.py` | `tf/test_m7_fanout.py::test_bt08_device_scope_two_sites_one_push`, `tf/test_m7_fanout.py::test_device_per_site_scope`, `tf/test_m7_fanout.py::test_daily_cap_day_boundary_in_time_zone`, `tf/test_m7_limits.py::test_resolve_limit_policy` | covered | |

## Push delivery (§9)

| id | requirement | implementing file(s) | test(s) | status | note |
|---|---|---|---|---|---|
| BF-64 | One `messages:send` per token, HTTP/2, at most 20 in flight | `sf/fcm.py`, `sf/fanout.py` | `tf/test_m7_fcm.py::test_http_client_sends_one_v1_request_per_token`, `tf/test_m7_fanout_review.py::test_fcm_concurrency_is_bounded_to_max_in_flight` | partial | `http2=True` on the production client is not asserted (the tests inject a transport). |
| BF-65 | Message content, Android + APNs fields, TTL/expiry | `sf/fcm.py`, `sf/fanout.py` | `tf/test_m7_fcm.py::test_payload_snapshot_both_platforms`, `tf/test_m7_fcm.py::test_data_payload_empty_values_are_empty_strings`, `tf/test_m7_fanout_review.py::test_ttl_from_decision_and_sent_at_is_send_time`, `tf/test_m7_fanout.py::test_late_start_shortens_ttl` | covered | |
| BF-66 | Token errors invalidate; 429/5xx retried with Retry-After ≤5 min; 401/403 stop + FCM_ERROR + alert | `sf/fcm.py`, `sf/fanout.py`, `sf/alerts.py` | `tf/test_m7_fcm.py::test_classify_response`, `tf/test_m7_fanout.py::test_retry_honours_retry_after_then_succeeds`, `tf/test_m7_fanout.py::test_retry_window_exhausted_then_send_failed`, `tf/test_m7_fanout.py::test_auth_failure_stops_fanout_and_alerts`, `tf/test_m7_fanout_review.py::test_full_chunk_retryable_honours_retry_after` | covered | |
| BF-67 | Invalid token excluded until next PUT | `src/crud/freespace_push_send.py`, `sf/devices.py` | `tf/test_m7_fanout.py::test_bt06_unregistered_token_invalidated_and_skipped_next_time`, `tf/test_m5_devices.py::test_new_token_clears_invalidation` | covered | |
| BF-68 | Service-account JSON outside repo; path is config; grep test | `sf/fcm_auth.py`, `src/core/config.py` | `tf/test_m7_secrets.py::test_no_key_material_in_source_control`, `tf/test_m7_secrets.py::test_configured_credentials_path_is_outside_the_repository` | covered | Placing the file on the VPS outside any web root is a deployment step. |
| BF-69 | Say "accepted by FCM", never "delivered" | `sf/admin_push.py`, `frontend/src/features/sites/components/EventDetail.tsx`, `frontend/src/locales/en/sites.json` | `frontend/src/pages/admin/sites/SitesOperations.test.tsx::"sends a device test push and words the result as accepted by FCM"` | partial | The test-push result wording is tested. The event-log `SENT` label is not. |
| BF-70 | Templates per type, placeholders, invalid refused, locale-ready | `sf/templates.py`, `src/models/site_message_template.py`, `src/api/freespace_sites.py` | `tf/test_m1_templates.py::TestValidation.test_unknown_placeholder_rejected_in_title_and_body`, `tf/test_m1_templates.py::TestDefaults.test_reference_wording`, `tf/test_m1_sites_api.py::TestTemplates.test_invalid_template_rejected`, `tf/test_m1_sites_api.py::TestTemplates.test_reset_to_default` | covered | `locale` column exists, only `en` is used. |

## Settings (§10)

| id | requirement | implementing file(s) | test(s) | status | note |
|---|---|---|---|---|---|
| BF-71 | Site settings validated, refused not clamped; defaults | `sf/site_config.py`, `src/api/freespace_sites.py` | `tf/test_m1_site_config_validation.py::test_invalid_is_refused_never_clamped`, `tf/test_m1_site_config_validation.py::test_defaults_valid_and_complete`, `tf/test_m1_sites_api.py::TestConfig.test_invalid_refused_with_code_and_nothing_written`, `tf/test_integration_wiring.py::test_stale_limit_minimum_is_120`, `tf/test_foundation_loaders.py::TestNotificationWindow.test_default_window_on_new_site` | covered | |
| BF-72 | Change applies at the next evaluation; managed off→on restarts cycle | `sf/evaluator.py`, `sf/site_bootstrap.py`, `src/api/freespace_sites.py` | `tf/test_m6_evaluator.py::TestEvaluateSite.test_settings_change_without_restart`, `tf/test_m1_sites_api.py::TestManaged.test_off_then_on_resets_cycle`, `tf/test_m1_sites_api.py::TestConfig.test_other_changes_do_not_reset_engine_state` | covered | |

## Retention and privacy (§11)

| id | requirement | implementing file(s) | test(s) | status | note |
|---|---|---|---|---|---|
| BF-73 | Daily purge with configurable retention | `sf/purge.py`, `src/services/cron/freespace_purge.py`, `scripts/seed_data/system_config.yaml` | `tf/test_m9_purge.py::test_devices_retention_cutoff_and_erasure`, `tf/test_m9_purge.py::test_send_history_cutoff`, `tf/test_m9_purge.py::test_event_log_cutoff_uses_last_activity`, `tf/test_m9_purge.py::test_occupancy_history_cutoff`, `tf/test_m9_purge.py::test_request_log_retention_honours_system_config`, `tf/test_m9_purge.py::test_retention_read_from_system_config`, `tf/test_m9_purge_postgres.py::test_purge_skip_locked_and_batched_deletes_on_postgres` (PG) | covered | The "no deviceId/token in request logs" part is BF-35. |
| BF-73a | POPIA requests: SATT contact, self-service erasure | `src/api/freespace_public/devices.py` (DELETE) | `tf/test_m5_devices.py::test_delete_erases_everything_but_a_tombstone` | process-only | The software part is BF-34. The rest is an organisational procedure. |

## Back office (§12)

| id | requirement | implementing file(s) | test(s) | status | note |
|---|---|---|---|---|---|
| BF-74 | Test push to device by suffix or topic (confirmed); works unmanaged; `TEST_PUSH`; not counted | `sf/admin_push.py`, `src/api/freespace_push.py` | `tf/test_m8_admin_ops.py::TestTestPush.test_by_suffix_one_match`, `tf/test_m8_admin_ops.py::TestTestPush.test_suffix_zero_two_and_other_site`, `tf/test_m8_admin_ops.py::TestTestPush.test_topic_confirmation`, `tf/test_m8_admin_ops.py::TestTestPush.test_unmanaged_site_works`, `tf/test_m7_fanout.py::test_test_push_bypasses_checks_and_is_not_counted` | covered | |
| BF-75 | Announcement: topic, Administrator only, confirmation, logged | `sf/admin_push.py`, `src/api/freespace_push.py` | `tf/test_m8_admin_ops.py::TestAnnouncement.test_admin_sends_one_topic_call`, `tf/test_m8_admin_ops.py::TestAnnouncement.test_role_matrix_confirmation_tenant`, `tf/test_m8_push_errors.py::test_announcement_refused_for_unmanaged_site` | covered | Refused for unmanaged sites (decision). |
| BF-76 | Screens: list, live view, settings, events + CSV, keys, device stats, history chart | `frontend/src/pages/admin/sites/*`, `src/api/freespace_stats.py`, `src/api/freespace_events.py` | `frontend/src/pages/admin/sites/SitesOperations.test.tsx::"shows data age, stale flag, engine state, occupancy, recommendation and devices from the summary"`, `SitesOperations.test.tsx::"shows the zone table as the app sees it, with recommended and not-enabled markers"`, `SitesOperations.test.tsx::"states the engine timers in words in the site time zone and the in-flight advisory"`, `SitesOperations.test.tsx::"exports the current filter as a CSV download through the API layer"`, `SitesOperations.test.tsx::"draws the chart with legend, reference lines and an accessible table view"`, `SitesOperations.test.tsx::"site tab shows counts by platform and version"`, `SitesPages.test.tsx::"lists keys with hint, status and last source IP, and the rotation explanation"`, `SitesPages.test.tsx::"renders every setting with the loaded values and the notification window"`, `tf/test_m8_admin_ops.py::TestEvents.test_csv_export_content_and_privacy`, `tf/test_m8_admin_ops.py::TestSummary.test_summary_row`, `tf/test_m8_admin_ops.py::TestHistory.test_day_in_site_time_zone` | covered | Component tests with mocked API. The e2e skills `e2e:test_freespace_*` exist but were not run here. |
| BF-77 | Config changes audited: who, when, before/after | `src/api/freespace_sites.py`, `src/api/freespace_zones.py` | `tf/test_m1_sites_api.py::TestConfig.test_partial_put_merges_and_audits`, `tf/test_m1_zones_api.py::TestCrud.test_update_audits_and_events`, `tf/test_m1_sites_api.py::TestTemplates.test_put_one_audits_and_events` | covered | |
| BF-78 | Admin API endpoints | `src/api/freespace_*.py`, `src/api/v1/__init__.py` | `tf/test_foundation_mounts.py::test_router_prefixes_and_admin_order`, `tf/test_m1_sites_api.py::TestRoleMatrix.test_matrix`, `tf/test_m1_zones_api.py::TestRoleMatrix.test_matrix`, `tf/test_m8_admin_ops.py::TestEvents.test_tenant_isolation_and_roles` | covered | Served at `/api/v1/admin/...`, not `/v1/admin/...` (decision D1). |

## Operations (§13)

| id | requirement | implementing file(s) | test(s) | status | note |
|---|---|---|---|---|---|
| BF-80 | `GET /health` unauthenticated, status only (DB, tick age) | `sf/health.py`, `main.py` | `tf/test_m9_health.py::test_report_keys_are_status_only`, `tf/test_m9_health.py::test_database_down_is_unhealthy_and_leaks_nothing`, `tf/test_m9_health.py::test_no_tick_after_grace_is_unhealthy`, `tf/test_integration_wiring.py::test_health_reports_engine_tick`, `tests/api_tests/test_health_endpoints.py::test_service_health_within_grace_is_200`, `tests/api_tests/test_health_endpoints.py::test_service_health_after_grace_without_tick_is_503` | covered | |
| BF-81 | Tick and purge as scheduled jobs, single-evaluator rule | `src/workers/worker.py`, `src/services/cron_handlers.py`, `scripts/seed_data/cron_jobs.yaml` | `tf/test_integration_wiring.py::test_cron_handlers_registered`, `tf/test_integration_wiring.py::test_purge_cron_job_seeded`, `tf/test_foundation_mounts.py::TestWorkerWrappers.test_registered_in_worker`, `tf/test_m6_postgres.py::test_bt01_concurrent_evaluations_one_advisory` (PG) | covered | |
| BF-82 | Operator alerts: silent site (and recovery), FCM credential, ceiling, rejection rate | `sf/alerts.py`, `scripts/seed_data/notification_templates.yaml` | `tf/test_m9_alerts.py::test_silent_site_fires_once_then_recovers_once`, `tf/test_m9_alerts.py::test_fcm_credential_failure_alert`, `tf/test_m9_alerts.py::test_device_ceiling_alert_once_per_window`, `tf/test_m9_alerts.py::test_rejection_rate_alert_from_events`, `tf/test_m9_alerts.py::test_recipients_are_permission_holders_and_super_admins` | covered | Real email delivery needs SMTP settings (deployment). |
| BF-83 | Nightly pg_dump, 14 days, copied off the VPS | `scripts/backup/freespace_backup.sh`, `deploy/freespace-backup.timer`, `scripts/backup/freespace_restore.md` | `tf/test_m9_backup_script.py::test_requires_an_off_host_destination`, `tf/test_m9_backup_script.py::test_local_only_run_writes_a_dump_and_prunes_old_ones`, `tf/test_m9_backup_script.py::test_refuses_pgbouncer_port` | partial | The script's checks are tested. The timer, the off-host copy and a restore are deployment-only. |
| BF-84 | mockMode off by default; routes absent (404) when off; refuse prod start without ack | `sf/mock_mode.py`, `src/api/freespace_public/mock.py`, `frontend/src/pages/admin/sites/SimulatorPage.tsx` | `tf/test_m10_mock_mode.py::test_mock_off_returns_404_not_403`, `tf/test_foundation_mounts.py::TestMockGuard.test_refuses_production_mock_mode`, `tf/test_foundation_mounts.py::TestMockGuard.test_create_application_refuses_to_start`, `tf/test_foundation_mounts.py::TestMockGuard.test_settings_default_off`, `frontend/src/features/sites/simulatorPresets.test.ts::"builds every acceptance scenario AT-01 to AT-08"` | covered | |
| BF-85 | Injectable clock only | `sf/clock.py` | `tf/test_foundation_clock.py::test_no_wall_clock_calls_in_freespace_code`, `tf/test_foundation_clock.py::TestGetClock.test_mock_mode_uses_redis_offset` | covered | |
| BN-1 | HTTPS 443 behind proxy with public cert; stable hostname | `deploy/nginx.conf`, `apache_site_config/freespace.conf` | `tests/unit_tests/test_deployment_client_ip_config.py::test_compose_api_trusts_the_proxy_network_not_localhost` | deployment-only | Certificate, port exposure and hostname can only be checked on the host. |
| BN-2 | ISO-8601 UTC `Z` on the wire; site IANA tz default Johannesburg | `src/serialisers/freespace_ingest.py` (`to_wire_timestamp`), `sf/site_config.py` | `tf/test_m3_intake.py::test_timestamps_iso_utc_z`, `tf/test_foundation_loaders.py::TestSiteBootstrap.test_site_defaults`, `tf/test_m1_sites_api.py::TestSitesCrud.test_invalid_time_zone_and_topic` | covered | Admin API responses use `+00:00` offsets, not `Z`. The admin API is not the "wire" for ParkIT or the app. |
| BN-3 | Sizing: 20 sites / 50 000 devices; availability p95 < 300 ms; 5 000-device fan-out < 2 min | `sf/fanout.py`, `sf/availability_cache.py` | `tf/test_m7_fanout.py::test_throughput_5000_devices`, `tf/test_m7_concurrency_postgres.py::test_throughput_5000_devices_with_device_lock` (PG) | partial | Fan-out is measured against a fake FCM (no network latency). Availability p95 and 50 000 devices are not load-tested. `perf/` has a generic locust setup only. |
| BN-4 | Redeploy keeps engine state, no re-send | `sf/evaluator.py`, `sf/fanout.py` | `tf/test_m6_evaluator.py::TestEvaluateSite.test_restart_safety`, `tf/test_m7_fanout_postgres.py::test_bt02_killed_mid_fanout_then_restarted` (PG) | covered | |

## Acceptance (§14)

| id | requirement | implementing file(s) | test(s) | status | note |
|---|---|---|---|---|---|
| AT-01 | 75 %: availability served, no candidate | `sf/availability.py`, `sf/engine.py` | `tf/test_m6_engine_core.py::TestAcceptance.test_at01_75_percent_no_candidate`, `tf/test_m4_app_endpoints.py::test_availability_at01_site_at_75` | covered | |
| AT-02 | 90 % for 4 min then 88 %: IDLE, NOT_STABLE | `sf/engine.py` | `tf/test_m6_engine_core.py::TestAcceptance.test_at02_not_stable` | covered | |
| AT-03 | 90 % for 5 min: SITE_INITIAL sent, ACTIVE | `sf/engine.py`, `sf/fanout.py` | `tf/test_m6_engine_core.py::TestAcceptance.test_at03_stabilised_sends_site_initial`, `tf/test_m6_evaluator.py::TestEndToEndWithFanout.test_at03_and_at05_through_fanout`, `tf/test_m10_mock_mode.py::test_scenario_trigger_then_advance_five_minutes` | covered | |
| AT-04 | Notified at 90 %, now 92 %: no candidate | `sf/engine.py` | `tf/test_m6_engine_core.py::TestAcceptance.test_at04_small_rise_no_candidate` | covered | |
| AT-05 | 95 % same rec: NO_MATERIAL_CHANGE; new rec: sent / COOLDOWN / DAILY_CAP | `sf/engine.py`, `sf/fanout.py` | `tf/test_m6_engine_core.py::TestAcceptance.test_at05_rise_same_recommendation_dropped`, `tf/test_m6_engine_core.py::TestAcceptance.test_at05_rise_with_new_recommendation_sent`, `tf/test_m7_fanout.py::test_at05_per_phone_part` | covered | |
| AT-06 | Falls to 79 %: IDLE, RECOVERY only if enabled, new cycle | `sf/engine.py` | `tf/test_m6_engine_core.py::TestAcceptance.test_at06_reset_and_new_cycle` | covered | |
| AT-07 | 85 %, B1 98 %, B4 55 %: recommends B4, no site push, ZONE_ADVISORY only if enabled + preferred | `sf/availability.py`, `sf/engine.py` | `tf/test_m6_engine_core.py::TestAcceptance.test_at07_zone_full_site_below_trigger`, `tf/test_m4_availability_core.py::test_at07_recommends_b4_when_b1_full` | covered | |
| AT-08 | No ingest 3 min or zone OFFLINE: stale/UNKNOWN, never recommend UNKNOWN, STALE_DATA | `sf/availability.py`, `sf/engine.py` | `tf/test_m6_engine_core.py::TestAcceptance.test_at08_stale_candidates_suppressed`, `tf/test_m6_engine_core.py::TestAcceptance.test_at08_offline_zone_never_recommended`, `tf/test_m4_app_endpoints.py::test_at08_no_ingest_for_three_minutes`, `tf/test_m4_availability_core.py::test_at08_recommendation_never_unknown_exhaustive` | covered | Also seen in the smoke test (a single 5-minute clock jump → `STALE_DATA`). |
| BT-01 | Two evaluations at once: one advisory per device | `sf/evaluator.py` | `tf/test_m6_postgres.py::test_bt01_concurrent_evaluations_one_advisory` (PG) | covered | PG only. |
| BT-02 | Killed mid fan-out, restarted: no double send | `sf/fanout.py` | `tf/test_m7_fanout_postgres.py::test_bt02_killed_mid_fanout_then_restarted` (PG), `tf/test_m7_fanout.py::test_crash_between_send_and_outcome_update_never_resends` | covered | |
| BT-03 | Key for A posts B: 403, event, nothing stored | `src/api/freespace_deps.py`, `sf/intake.py` | `tf/test_m3_intake.py::test_bt03_site_mismatch_403_event_nothing_stored`, `tf/test_m3_intake.py::test_bt03_second_site_key_cannot_write_first_site` | covered | |
| BT-04 | measuredAt +5 min: 422 CLOCK_SKEW | `sf/intake.py` | `tf/test_m3_intake.py::test_bt04_clock_skew_422` | covered | |
| BT-05 | 100/104 alternating: recommendation stable | `sf/availability.py` | `tf/test_m4_availability_core.py::test_bt05_alternating_100_104_never_flips`, `tf/test_m4_availability_core.py::test_bt05_large_swing_does_flip` | covered | |
| BT-06 | UNREGISTERED: token invalidated, skipped next time, others fine | `sf/fanout.py` | `tf/test_m7_fanout.py::test_bt06_unregistered_token_invalidated_and_skipped_next_time` | covered | |
| BT-07 | DELETE: token gone at once, next advisory skips | `src/crud/freespace_devices.py`, `sf/fanout.py` | `tf/test_m5_devices.py::test_delete_erases_everything_but_a_tombstone`, `tf/test_m7_fanout.py::test_target_set_excludes_invalid_tombstoned_unselected` | covered | |
| BT-08 | DEVICE scope, two sites ACTIVE within 30 min: one push, second COOLDOWN | `sf/limits.py`, `src/crud/freespace_push_send.py` | `tf/test_m7_fanout.py::test_bt08_device_scope_two_sites_one_push`, `tf/test_m7_concurrency_postgres.py::test_bt08_two_sites_same_tick_one_push` (PG) | covered | |
| BT-09 | Unmanaged at 90 % for 5 min: UNMANAGED, nothing sent | `sf/engine.py` | `tf/test_m6_engine_core.py::TestShadowMode.test_bt09_unmanaged_logged_nothing_sent` | covered | |
| BT-10 | mockMode off: `/mock/*` 404 | `src/api/freespace_public/__init__.py` | `tf/test_m10_mock_mode.py::test_mock_off_returns_404_not_403`, `tf/test_foundation_mounts.py::TestMountsOnRealApp.test_mock_routes_absent_when_off` | covered | |
| BT-11 | Counts do not sum: accepted, INGEST_INCONSISTENT, PARTIAL | `sf/intake.py` | `tf/test_m3_intake.py::test_bt11_sum_mismatch_accepted_inconsistent_partial` | covered | |

## Totals

96 ids: **87 covered**, **7 partial**, **0 not covered**, **1 deployment-only** (BN-1), **1 process-only**
(BF-73a). BF-83 counts as partial, although its remaining part is deployment-only.

## Requirements not, or only partly, covered

- **BF-17** (partial): a rule about what the backend must not do (no backlog). Only out-of-order handling is testable.
- **BF-35** (partial): nginx masking is not tested. `make dev` prints raw device ids in uvicorn access-log lines; deployed units use `--no-access-log`.
- **BF-40** (partial): "never manages subscriptions". No code does, but no test enforces it.
- **BF-64** (partial): `http2=True` on the production client is not asserted. One send per token and the 20-in-flight bound are tested.
- **BF-69** (partial): the "accepted by FCM" wording is tested for test-push results only, not for the event-log label.
- **BF-83** (partial): backup script validation is tested. The nightly timer, the off-host copy and a restore are not.
- **BN-3** (partial): no load test for availability p95 < 300 ms or for 50 000 devices. The 5 000-device fan-out is measured against a fake FCM.
- **BN-1** (deployment-only): TLS on 443, certificate, stable hostname.
- **BF-73a** (process-only): the POPIA procedure. Its software part (self-service DELETE) is covered by BF-34.
- **PG-only coverage**: BF-51, BT-01 and the PG halves of BT-02, BT-08 and BF-73 run only with `TEST_DATABASE_URL_DIRECT`. CI must set it.

## Decisions taken where the spec was silent or ambiguous

Visible on the wire to ParkIT or the mobile app:
1. `GET /v1/sites` returns an object `{"sites": [...]}`, not a bare array (lets fields be added later). Each item is `{id, name, topic, managed, timeZone}`.
2. A never-received site's availability is `{"siteId", "asOf": null, "ageSeconds": null, "stale": true, "site": null, "recommendedZoneId": null, "zones": []}`. `site` and `ageSeconds` are `null`, not omitted.
3. `discoveredZones` in the intake response lists **every submitted zone that is still discovered and not yet reviewed**, not only the zones created by this submission. ParkIT keeps seeing them until staff review them.
4. A deactivated or soft-deleted organisation: ingest answers **401** (the same as an unknown or revoked key). `GET /v1/sites` omits its sites, availability answers 404, and a device PUT naming its sites gets 422 `device.unknown_site`.
5. Out-of-order submissions answer `200 {"ignored": "OUT_OF_ORDER", ...}`. An equal `measuredAt` is not out of order.
6. A 429 under `/v1/` returns `{"detail", "detail_code"}` (`ingest.rate_limited` / `device.rate_limited` / `common.rate_limited`) with an integer `Retry-After` of 1–600.
7. Ingest bodies use `extra="ignore"`, so new ParkIT fields are accepted. Malformed bodies keep FastAPI's 422 shape, which includes the field path.
8. A device PUT for a `deviceId` that was DELETEd creates a fresh device: the tombstone is not revived.
9. FCM `data.recommendedZoneId` is `""` when there is none. All data values are strings.
10. `/mock/*` is unauthenticated (the spec gives no auth). It is protected by the startup guard and the per-IP limit.

Back office and behaviour:
11. Announcements are **refused (409 `site_push.site_unmanaged`) for unmanaged sites**. Test pushes still work there (BF-74).
12. Announcements are for the Administrator only (BF-75 over §12's "Operator"; D16/Q7).
13. Admin API lives at `/api/v1/admin/...`, not `/v1/admin/...` (D1).
14. A new site has `listed = false` (contracts §10.6) and `managed = false`.
15. The engine tick also evaluates unmanaged sites, so shadow-mode timers run (D7; BF-50 says "managed").
16. Repeated identical suppressions collapse into one event with `repeat_count` (D11).
17. A send whose acceptance by FCM is unknown (`CLIENT_ERROR`, `NO_RESPONSE_*`, `UNKNOWN_AFTER_CRASH`) counts towards cooldown, cap and duplicate checks and is never retried. Definite failures do not count. A retry-pending row (`PENDING`/`RETRY:*`) counts while pending. The rule is in `src/constants/freespace.py` (`send_counts_towards_limits`).
18. FCM not configured: the advisory's fan-out ends `FAILED` with an `FCM_ERROR / CREDENTIALS_MISSING` event, and the site's in-flight guard is released (not stuck).
19. `/health` has a 300 s start-up grace ("no_tick_yet") before a missing tick turns it 503. `/health/live` is a constant liveness probe.
20. Request-log retention reuses `request_logs.retention_days` (contracts §10.4).
21. Purge and `device_site` erasure are sanctioned hard deletes (D12, an exception to CLAUDE.md rules 2/10).

## Before go-live (human)

1. **FCM credential:** create the service account. Place the JSON outside the repo and any web root, readable only by the service user. Set `freespace.fcm_credentials_path` and `freespace.fcm_project_id`. Send one test push to a real phone.
2. **Proxy:** install `deploy/nginx.conf` (or the Apache file) and run `nginx -t`. Check that `/v1/devices/<id>` appears masked in the access and error logs. Obtain a Let's Encrypt certificate for the stable hostname. Set `server.trusted_client_ip_header`, or uvicorn `--forwarded-allow-ips`, to match the proxy.
3. **Mock mode** off in the production `config.json`, with no acknowledgement flag.
4. **Backups:** configure the off-host destination for `scripts/backup/freespace_backup.sh` and enable `freespace-backup.timer`. Run a **restore drill** following `scripts/backup/freespace_restore.md`.
5. **Seeding:** `make migrate`, then `scripts/seed_first_tenant.py` on a fresh DB (change the default super-admin password), or `scripts/seed_maintenance.py` on an existing one. Confirm the Freespace permissions, the operator role, cron jobs, system-config keys and alert templates.
6. **First site and keys:** create the customer organisation and the site (`managed = false`, `listed` as wanted), zones and an ingest key. Enter the key in ParkIT and use "test connection" (ping). Create two app keys for the app release.
7. **Operator alerts:** SMTP settings, plus at least one user holding `site_alerts:receive`.
8. **CI:** provide PostgreSQL and `TEST_DATABASE_URL_DIRECT` so the PG-only tests run.
9. Shadow-run the site (`managed = false`) and tune it before `managed = true` (§15.1).
