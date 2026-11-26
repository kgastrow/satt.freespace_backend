# Freespace Backend — Functional Description

Revision 0.2 · 26 November 2026 · For the backend build. The open questions are settled (§15); ParkIT's publisher is built against §5.

This is what the Freespace backend must do. It does not say how to structure the code. The sources are:

- *Freespace Functional Specification* rev 0.1 (21 Oct 2026), cited as **spec §n**
- *Freespace Backend Proposal* rev 0.1 (24 Nov 2026), cited as **proposal §n**
- the decisions listed in §1.3

Where this document differs from the proposal, it says so and gives the reason. Requirements are numbered **BF-x** (functional) and **BN-x** (non-functional) so the build and the tests can refer to them.

---

## 1. Purpose and scope

### 1.1 Purpose

The backend sits between on-site ParkIT installations and the Freespace mobile app. It does four jobs:

- receives zone occupancy pushed out from each site
- serves live availability and a recommended parking zone to the app
- decides, server-side, when an employee's phone should get a push, and sends it through FCM
- gives SATT staff a back office to configure sites and see why each push was sent or suppressed

### 1.2 Out of scope

- **Employee accounts and sign-in.** Phones are anonymous (proposal §1).
- **Pushes for sites that ParkIT's legacy notifier still serves.** The existing ABSA site keeps topic `ABSA-270RR` and ParkIT's own FCM notifier. The backend must never push to a site whose `managed` flag is off (BF-61).
- **Images, maps and media.** Not in this revision.
- **Pulling data from a site.** The backend never connects to a site. Sites connect out to it.

### 1.3 Decisions this document rests on

| # | Decision | Owner, date |
|---|---|---|
| D1 | SATT builds and hosts the backend on its own Ubuntu VPS, with PostgreSQL. Firebase Firestore and Storage were considered and rejected. | SATT, 2026-11-24 |
| D2 | ParkIT **pushes** to the backend over outbound HTTPS. The backend never reaches into a site. | SATT, 2026-11-24 |
| D3 | The intake carries capacity, the free-bay breakdown and data health per zone, not just `occupied` (§5). This differs from proposal §3.2. | SATT, 2026-11-24 |
| D4 | The per-phone cooldown and daily cap count **per phone across all sites** by default, and the scope is configurable (§8.7). | SATT, 2026-11-24 |
| D5 | Phones are addressed by FCM device token for advisories. Each site keeps a topic for announcements and for the legacy system. | proposal §1, §6 |
| D6 | The rulings in §15 (recovery counts towards limits, retention, POPIA contact, zone advisories off, morning window, mixed sensing, legacy site later). | SATT, 2026-11-26 |

---

## 2. Actors and network

| Actor | Talks to the backend by | Trust |
|---|---|---|
| **ParkIT publisher** (one per site, on-premises Windows) | `POST /v1/ingest/...` every 30 s, outbound HTTPS, possibly through a corporate proxy | Machine API key bound to one site |
| **Freespace app** (Android, iOS) | `GET /v1/sites`, `GET /v1/sites/{id}/availability`, `PUT`/`DELETE /v1/devices/{id}` | App key, which can be extracted from the APK and so is not a secret, plus rate limits |
| **Back-office user** (SATT staff, perhaps a client administrator later) | Web UI and `/v1/admin/...` | Named user with a role |
| **FCM** | The backend calls FCM HTTP v1 | Google service account held on the VPS |

**BN-1.** Only HTTPS on 443 is exposed, behind a reverse proxy holding a publicly trusted certificate (Let's Encrypt). The hostname is stable: site firewalls and proxies will allow-list it by name, so changing it means a change request at every customer.

**BN-2.** Every timestamp on the wire is ISO-8601 UTC with a `Z` suffix. Each site has an IANA time zone, default `Africa/Johannesburg`, used for daily caps, notification windows and message wording.

---

## 3. Concepts

| Term | Meaning |
|---|---|
| **Customer** | The client organisation (e.g. ABSA). It owns sites. It maps onto the template's `organization`. |
| **Site** | One car park / one ParkIT installation. It has a stable `siteId` slug (e.g. `absa-alice-lane`), a display name, a time zone, an FCM topic and a `managed` flag. |
| **Zone** | A floor or area within a site, shown in the app. It has a stable `zoneId` slug (e.g. `b4`) that is unique within the site. |
| **Snapshot** | The latest figures for a site and its zones, as received from ParkIT. |
| **Publisher** | The ParkIT instance posting for a site. It is identified by its ingest key. |
| **Device** | One installed copy of the app: an app-generated `deviceId`, an FCM token, a platform and the sites it has selected. |
| **Cycle** | A site's alerting episode, from the first advisory (state ACTIVE) to the reset below the reset level. |
| **Advisory** | A push message of type `SITE_INITIAL`, `SITE_CHANGE`, `ZONE_ADVISORY`, `RECOVERY` or `TEST`. An `ANNOUNCEMENT` (BF-75) is a topic message, not an advisory: no limits apply and the engine never generates one. |
| **Event** | A log record of something the engine decided: a state change, an advisory candidate, a send or a suppression. |

---

## 4. Data the backend keeps

These are the entities and what each must hold. Names are indicative.

**BF-1. Site:**
- `siteId`, name, customer, time zone, FCM topic
- `managed` (whether the backend may push for this site)
- `listed` (whether it appears in `GET /v1/sites`)
- the site settings (§10.1) and message templates (§9.5)

**BF-2. Zone:**
- `siteId`, `zoneId`, display name, display order
- `enabled` (whether it is shown in the app)
- `recommendable` (a zone may be shown but never recommended, e.g. a visitor floor)
- `preferred`, `priority` (an integer; lower wins ties)
- the zone settings (§10.2)
- `discovered` (true when the zone was created automatically by intake and has not yet been reviewed)

Capacity is **not** edited in the backend; it comes from ParkIT on every snapshot.

**BF-3. Latest snapshot:** one row per site and one per zone, overwritten on each accepted submission. It holds the values received, plus `measuredAt` (ParkIT's clock) and `receivedAt` (the backend's clock).

**BF-4. Occupancy history**, used to tune thresholds against real patterns (spec §13). Store per site and per zone, at most one point per minute: occupied, capacity, usable free, health. Retention is in §11.

**BF-5. Engine state per site:**
- state (`IDLE` / `PENDING` / `ACTIVE`) and when it was entered
- the occupancy level last notified
- the recommendation last notified
- the current recommendation and when it became current
- per-zone advisory state

It must be persisted, so that a restart neither re-sends nor forgets an advisory.

**BF-6. Device:** `deviceId`, FCM token, platform (`ANDROID`/`IOS`), app version, selected sites, `notificationsEnabled`, `firstSeen`, `lastSeen`, `tokenInvalidatedAt`.

**BF-7. Send history per device:** when it was sent, the site, the advisory type, the message fingerprint and the event id. This is enough to evaluate the cooldown, the daily cap and duplicates.

**BF-8. Event log** (§8.6).

**BF-9. Keys:**
- ingest keys: one or more per site; each can be rotated, revoked and given an expiry; stored hashed; shown once at creation. The key format is fixed by BF-10a.
- app keys: one or more per deployment, with at least two valid at once so an app release can rotate them

---

## 5. Intake from ParkIT

### 5.1 Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /v1/ingest/occupancy` | Submit a snapshot for one site. |
| `GET /v1/ingest/ping` | Check the key and connectivity, store nothing. ParkIT's "test connection" button calls it. |

**BF-10.** Both require the header `Authorization: Bearer <ingest key>`. A key is bound to exactly one site. A submission whose `siteId` is not that key's site gets **403** and an event `INGEST_REJECTED / SITE_MISMATCH`.

**BF-10a. Key format.** ParkIT refuses to store a key that is not 1–512 characters of printable ASCII with no space (`^[\x21-\x7e]{1,512}$`), because it travels in an HTTP header. Generate keys well inside that: at least 256 bits of randomness, encoded as base64url or hex, optionally with a short readable prefix (e.g. `fsk_`).

**BF-10b. Rotation.** After a 401, ParkIT stops posting for 300 s before it tries again, and raises a fault on its own screen. Rotation must therefore overlap: create the new key, let the site engineer enter it in ParkIT, then revoke the old one. Two keys valid at once for a site is normal (BF-9).

**BF-11.** `GET /v1/ingest/ping` answers `200 {"siteId": ..., "siteName": ..., "serverTime": ...}`. ParkIT shows the name, so the installer can see the key points at the right site, and compares `serverTime` with its own clock to warn about skew.

### 5.2 Payload (replaces proposal §3.2)

```json
{
  "siteId": "absa-alice-lane",
  "measuredAt": "2026-11-24T07:45:10Z",
  "publisher": { "product": "ParkIT", "version": "2.4.0", "instance": "PARKIT-ALICE-01" },
  "site": {
    "capacity": 1200, "occupied": 1081,
    "freeUsable": 101, "freeReserved": 6, "freeDisabled": 4, "unknown": 8,
    "health": "OK"
  },
  "zones": [
    { "zoneId": "b1", "name": "Basement 1",
      "capacity": 450, "occupied": 432,
      "freeUsable": 16, "freeReserved": 0, "freeDisabled": 2, "unknown": 0,
      "health": "OK", "measuredAt": "2026-11-24T07:45:10Z" }
  ]
}
```

| Field | Meaning |
|---|---|
| `capacity` | Bays in service in the zone, including reserved and disabled bays, excluding bays closed by the operator. |
| `occupied` | Bays occupied. |
| `freeUsable` | Vacant bays any employee may use. ParkIT computes this; the backend does not second-guess it. |
| `freeReserved`, `freeDisabled` | Vacant bays an ordinary employee may not use. |
| `unknown` | Bays with no current reading (failed sensor or comms). Zero for ramp-counted zones. |
| `health` | `OK`: all of the zone's sources are reporting. `PARTIAL`: some are. `OFFLINE`: none are, so the counts are meaningless. |
| `name` | ParkIT's name for the zone. Used only to label a discovered zone. |
| `site` | Site totals. ParkIT computes them because ParkIT knows which zones overlap (nested zones); the backend must **not** sum the `zones` array to get site totals. |

**Mixed sensing.** Alice Lane has both kinds of zone (§15 Q5). A zone sensed per bay can carry non-zero `unknown`, `freeReserved` and `freeDisabled`; a ramp-counted zone always sends them as 0, and its `occupied` can drift between counter resets. The backend treats every zone the same way and must not infer the sensing type from the figures. The back office shows a free-text zone note (e.g. "ramp-counted") so staff tuning thresholds know which figures to trust.

**BF-12. Validation.** Every count is an integer ≥ 0. The backend checks `occupied + freeUsable + freeReserved + freeDisabled + unknown == capacity` for the site and for each zone.
- A mismatch is still accepted. It logs an event `INGEST_INCONSISTENT` with the figures, and marks that zone or site `PARTIAL` for this snapshot. A miscounting site should be visible without going dark.
- A malformed body gets 422 with the field path.

**BF-13. Clocks.** Staleness is judged on `receivedAt`, never `measuredAt`.
- A submission with `measuredAt` more than 120 s in the future gets **422** `CLOCK_SKEW`.
- A submission older than the stored snapshot for the same site is ignored, with `200 {"ignored": "OUT_OF_ORDER"}`. It does not overwrite.

**BF-14. Zone matching.**
- A `zoneId` the site does not have is created as a **discovered** zone: `enabled = false`, labelled with `name`. It appears in the back office for review and is reported in the response.
- A known zone missing from a submission keeps its last values and ages normally, so it goes stale (BF-21).

**BF-15. Response:**

```json
{ "accepted": true, "receivedAt": "2026-11-24T07:45:11Z",
  "site": { "stale": false, "state": "ACTIVE", "recommendedZoneId": "b4" },
  "discoveredZones": ["b5"], "warnings": [] }
```

ParkIT shows this to its operator, so a site engineer can see the backend's view without a back-office login.

**BF-16. Evaluation.** Each accepted submission triggers a rules-engine evaluation for that site (§8). Evaluation must not delay the response: the response may return before any push fan-out finishes.

**BF-17. Cadence and backlog.** ParkIT posts every 30 s by default, whether or not anything has changed; the post doubles as the heartbeat. The backend must not expect a backlog after an outage, and must not ask for one: ParkIT sends only the current snapshot.

**BF-18. Rate limit.** 12 submissions a minute per ingest key; beyond that, 429 with `Retry-After` as a **whole number of seconds** (1–600). ParkIT reads only a number: an HTTP date, a missing header, `nan` or `inf` is treated as 60 s, and any value is clamped to 1–600 s. A site rate-limited for 120 s raises a fault in ParkIT, so a 429 is for a misbehaving publisher, not normal flow control.

**BF-19. Response size.** ParkIT reads at most the first 64 KB of an intake or ping response; a longer body is cut there, no longer parses as JSON, and its fields (`site`, `warnings`, `siteName`) are lost. Keep responses small; `warnings` is a short list of short strings.

---

## 6. Availability

### 6.1 Computation

**BF-20. Occupancy percentage** = `occupied / capacity`. It is undefined when `capacity = 0`.
- Rules compare the exact ratio against thresholds. 89.9 % is below a 90 % trigger.
- The app is shown `floor(ratio × 100)`, so it never shows "90 %" before the 90 % rule has fired.

**BF-21. Zone staleness.** A zone is **stale** when any of these holds:
- `now − receivedAt > staleLimit` (site setting, default 120 s)
- `health = OFFLINE`
- `capacity = 0`
- `unknown / capacity > unknownLimit` (zone setting, default 25 %)
- `health = PARTIAL` and the site setting `partialIsStale` is true (the default)

**BF-22. Site staleness.** The site is stale when `now − receivedAt > staleLimit`, or the `site` block's health is `OFFLINE`, or (with `partialIsStale`) `PARTIAL`, or its `capacity = 0`.

**BF-23. Zone status** (proposal §3.1), with thresholds from the zone settings:

| Status | Rule |
|---|---|
| `UNKNOWN` | The zone is stale (BF-21). |
| `FULL` | occupancy ≥ `fullPct` (default 95 %) **or** `freeUsable < fullMinFree` (default 5) |
| `LIMITED` | occupancy ≥ `limitedPct` (default 80 %) |
| `AVAILABLE` | otherwise |

**BF-24. Recommended zone** (spec FR-03, §7):
1. Candidates are zones that are enabled, `recommendable`, not `UNKNOWN` and not `FULL`.
2. Rank them by `freeUsable` descending, then `priority` ascending, then `zoneId`.
3. **Stickiness.** The current recommendation is kept unless the top candidate's `freeUsable` beats it by more than `recommendationMargin` (site setting, default 10 bays), or the current one is no longer a candidate. Without this, two floors with similar counts flip back and forth on every snapshot.
4. The result is `null` when there are no candidates or the site is stale.

The same recommendation is used by the app response and the rules engine. They must never disagree.

**BF-25.** "Top two zones" for message wording is the first two candidates in the BF-24 ranking.

### 6.2 App endpoints

All app endpoints require the header `X-Freespace-App-Key`. A missing or unknown key gets 401. The key is a speed bump, not authentication; the limits in §6.3 are the real defence.

**BF-30. `GET /v1/sites`** lists sites with `listed = true`: `id`, `name`, `topic`, `managed`, `timeZone`. Ordered by name.

**BF-31. `GET /v1/sites/{siteId}/availability`** returns proposal §3.1's shape, with these additions:

```json
{
  "siteId": "absa-alice-lane",
  "asOf": "2026-11-24T07:45:11Z",
  "ageSeconds": 14,
  "stale": false,
  "site": { "capacity": 1200, "occupied": 1081, "occupancyPct": 90, "freeUsable": 101 },
  "recommendedZoneId": "b4",
  "zones": [
    { "id": "b1", "name": "Basement 1", "capacity": 450, "free": 16,
      "occupancyPct": 96, "status": "FULL", "asOf": "2026-11-24T07:45:11Z" }
  ]
}
```

- `asOf` is the backend's `receivedAt`.
- `ageSeconds` is computed by the server, so the app shows data age correctly even when the phone's clock is wrong (spec FR-04).
- `free` is `freeUsable`.
- Zones are listed in display order and include `UNKNOWN` ones, so the app can show "no data" rather than silently dropping a floor.
- A site that has never received data answers 200 with `stale: true`, `asOf: null` and `zones: []`.
- An unknown or unlisted site gets 404.

**BF-32.** Availability reads never trigger an evaluation or a push (spec FR-05). Responses may be cached for up to 5 s and carry `Cache-Control: max-age=5`.

**BF-33. `PUT /v1/devices/{deviceId}`.** Body: `{fcmToken, platform, siteIds[], notificationsEnabled, appVersion}`.
- **Idempotent.** It creates or replaces, and returns the stored registration.
- `deviceId` must match `^[A-Za-z0-9_-]{22,64}$` and should carry ≥ 128 bits of randomness (e.g. a UUIDv4 or 22 base64url characters).
- Unknown or unlisted `siteIds` get 422.
- A token already held by another `deviceId` is moved to this one (reinstalls), and the old device loses it.
- Updates `lastSeen`.

**BF-34. `DELETE /v1/devices/{deviceId}`** is a full opt-out.
- It **erases** the FCM token and the site selections immediately. Keeping the token after an opt-out is not acceptable under POPIA.
- If the template's soft-delete convention is kept, the row may survive only as a tombstone with no token, used for counts.
- Answers 204, including for an unknown id. It must not reveal whether an id exists.

**BF-35. `deviceId` is a bearer secret.** It never appears in logs, the event log, the back office or any response other than to its own `PUT`.

### 6.3 Abuse limits

**BF-36.** Per client IP:
- availability: 60 requests a minute
- `GET /v1/sites`: 30 a minute
- device `PUT`/`DELETE`: 10 a minute per `deviceId`, and 30 a minute per IP

**BF-37.** A deployment-wide ceiling on registered devices (default 50 000). Beyond it, registration gets 503 and an operator alert fires (BF-82). This stops a script from filling the table.

---

## 7. Topics

**BF-40.** The app subscribes itself to each selected site's `topic` (proposal §1). The backend never manages subscriptions.

**BF-41.** The backend sends to a topic only for:
- a back-office **announcement** (BF-75)
- a **test push** to a topic (BF-74)

Advisories always go to device tokens, because per-phone limits cannot be applied to a topic.

---

## 8. Notification rules engine

### 8.1 When it runs

**BF-50.** The engine evaluates a site on every accepted submission, and once a minute for every managed site, so stabilisation timers expire and stale data is detected even when no submissions arrive.

**BF-51. Exactly one evaluator per site at a time.** The template can run several API workers and background workers. Two evaluations running in parallel would send duplicate pushes. Evaluation must hold an exclusive per-site lock (e.g. a PostgreSQL advisory lock), and read and write the engine state inside it.

**BF-52. An advisory is recorded before it is sent.**
- The advisory event (with its `eventId`) and the engine-state change are committed first; fan-out follows.
- A fan-out interrupted by a crash resumes for the devices not yet recorded in send history, and never re-sends to one that is.
- Phones may miss an advisory in a crash. They must never get it twice.

### 8.2 Site state machine (proposal §5, refined)

`T` = trigger (default 90 %), `R` = reset level (default 80 %), `S` = stabilisation (default 5 min), `Δ` = change threshold (default 5 points).

| From | Condition | To / action | Spec |
|---|---|---|---|
| IDLE | site occupancy ≥ T | PENDING; record the crossing time | |
| PENDING | occupancy < T before S has elapsed | IDLE; log `NOT_STABLE` | AT-02 |
| PENDING | occupancy ≥ T continuously for S | ACTIVE; candidate `SITE_INITIAL`; set last-notified level = current, last-notified recommendation = current | AT-03 |
| ACTIVE | occupancy ≥ last-notified level + Δ | candidate `SITE_CHANGE` | AT-04, AT-05 |
| ACTIVE | recommendation ≠ last-notified recommendation, and the new one has held for S | candidate `SITE_CHANGE` | spec §5 |
| ACTIVE | occupancy < R | IDLE; candidate `RECOVERY` only if `recoveryPush` is on; clear the last-notified values | AT-06 |
| any | site stale | state, timers and last-notified values unchanged; every candidate suppressed with `STALE_DATA` | AT-08 |

**BF-53. While stale, timers do not advance.** A PENDING site that goes stale for 3 minutes and comes back has not been stable for those 3 minutes. Its stabilisation restarts from the first fresh snapshot at or above T.

**BF-54. "Last-notified level"** advances only when a `SITE_INITIAL` or `SITE_CHANGE` is actually sent to at least one device. A candidate suppressed by usefulness or by every phone's limits leaves it unchanged.

**BF-55. Only rises count against Δ** (spec §4: "an increase from 90 % to 95 %"). Improvement is announced through a recommendation change or the optional `RECOVERY`. A `changeDirection` setting (`RISING`, default; or `BOTH`) is kept for later; with `BOTH`, a fall of Δ while still ≥ R is also a candidate.

### 8.3 Zone advisory (spec §5 design clarification; optional)

**BF-56.** Applies when the site setting `zoneAdvisory` is on, to zones with `preferred = true` and a zone `advisoryPct` set. It is evaluated only while the site is IDLE or PENDING; once the site is ACTIVE, site advisories cover it.
- A preferred zone that holds at or above `advisoryPct` (or reaches FULL) for S, while a recommendation exists, produces candidate `ZONE_ADVISORY`.
- Each zone advises at most once per zone cycle. The cycle resets when that zone falls below `advisoryPct − zoneResetGap` (default 10 points).
- Zone advisories respect every per-phone limit.

### 8.4 Usefulness (proposal §5)

**BF-57.** Each candidate gets a **fingerprint**: its type, the recommended zone, the top-two zone set (for `SITE_INITIAL`) and the full rendered body text.
- A candidate whose fingerprint equals the last advisory actually sent for the site in this cycle is dropped as `NO_MATERIAL_CHANGE`.
- A `SITE_CHANGE` whose recommendation and top-two set are unchanged is also dropped as `NO_MATERIAL_CHANGE`, even if Δ was crossed. The 90 → 95 % case is "eligible but not mandated" (spec §4).
- A candidate with no recommendation (`null`) is dropped as `NO_RECOMMENDATION`; an advisory that tells you to park nowhere is not useful.

### 8.5 Per-phone checks (proposal §5)

**BF-58.** A candidate that passes BF-57 goes to every device that has the site selected and a valid token. Each device is checked **in this order**, and the first failure is its reason:

| # | Check | Reason code |
|---|---|---|
| 1 | `notificationsEnabled` | `OPTED_OUT` |
| 2 | inside the site's notification window, if one is set (§10.1) | `OUTSIDE_WINDOW` |
| 3 | the device's last advisory fingerprint ≠ this one | `DUPLICATE` |
| 4 | at least `cooldown` since the device's last advisory, in the limit scope (BF-63) | `COOLDOWN` |
| 5 | fewer than `dailyCap` advisories today, in the limit scope | `DAILY_CAP` |
| — | passed | `SENT` (after FCM accepts) or `SEND_FAILED` |

**BF-59.** Suppressed advisories are not queued or retried later. A phone that was in cooldown at 08:20 does not receive the 08:20 message at 08:50. Stale guidance is worse than none (proposal §6, expiry).

**BF-60.** `TEST` pushes bypass every check (BF-74) and are not counted towards cooldown or caps. `RECOVERY` **is** counted towards both (§15 Q1): without that, a site hovering at the trigger could send "full", "space again", "full" to the same phone.

**BF-61.** Nothing is sent for a site with `managed = false`. Its candidates are logged with reason `UNMANAGED`, so its settings can be tuned in shadow mode before it goes live. This is also how a new site should be piloted (spec §13).

### 8.6 Event log (spec §10)

**BF-62.** Every engine decision is an event:
- `siteId` and `occurredAt`
- type: `STATE_CHANGE`, `CANDIDATE`, `ADVISORY`, `DATA_STALE`, `DATA_RECOVERED`, `INGEST_REJECTED`, `INGEST_INCONSISTENT`, `ZONE_DISCOVERED`, `FCM_ERROR`, `CONFIG_CHANGED`, `TEST_PUSH`, `ANNOUNCEMENT`
- the site and zone figures at that moment, and the recommendation
- for advisories:
  - `eventId`, type and rendered text
  - **per-reason device counts**, e.g. `{SENT: 812, COOLDOWN: 40, DAILY_CAP: 3, OPTED_OUT: 120, SEND_FAILED: 2, TOKEN_INVALID: 5}`
  - FCM latency, and when fan-out started and finished

Per-device outcomes live in send history (BF-7), not in the event log. One row per device per evaluation would grow with phones × minutes.

### 8.7 Limit scope

**BF-63.** A deployment setting `limitScope`:
- `DEVICE` (default, D4): the cooldown and daily cap come from the deployment settings and count every advisory to the device from any site. "Today" is midnight to midnight in the deployment time zone (default `Africa/Johannesburg`).
- `DEVICE_PER_SITE`: each site's own `cooldown` / `dailyCap`, counted per (device, site), with "today" in the site's time zone.

---

## 9. Push delivery

### 9.1 Message

**BF-64.** Each advisory is one FCM HTTP v1 `messages:send` per device token. As far as we know FCM no longer has a multi-token batch endpoint (the legacy batch API was shut down in 2024); check this during the build. Use HTTP/2 with bounded concurrency (default 20 in flight).

**BF-65.** Message content:

| Part | Value |
|---|---|
| `notification.title` / `body` | From the site's templates (§9.5). |
| `data` | `type`, `siteId`, `recommendedZoneId` (or empty), `occupancyPct`, `eventId`, `sentAt`. All values are strings, as FCM requires. |
| Android | `priority: HIGH`, `ttl: "1800s"`, `collapse_key: <siteId>`, `notification.channel_id: "freespace_default"`, `notification.tag: <siteId>` (replaces the tray entry) |
| APNs | Headers `apns-priority: 10`, `apns-push-type: alert`, `apns-expiration: <sentAt + 1800 s as epoch>`, `apns-collapse-id: <siteId>` |

The expiry (default 30 min, site setting) and the collapse/replace behaviour come from proposal §6. **Both platforms must be set explicitly**: Android's `collapse_key`/`ttl` do not reach iOS.

### 9.2 Errors

**BF-66.**
- `UNREGISTERED`, a 404 on the token, or `INVALID_ARGUMENT` naming the token: the token is invalidated (`tokenInvalidatedAt`) and the device's outcome is `TOKEN_INVALID`.
- `SENDER_ID_MISMATCH`: the same.
- 429, 500 or 503: retried with exponential backoff that honours `Retry-After`, until 5 minutes have passed or the message has expired, whichever is sooner. Then `SEND_FAILED`.
- 401 / 403 from FCM: the credential is broken. Stop the fan-out, raise `FCM_ERROR`, and alert operators (BF-82).

**BF-67.** A device whose token is invalid is excluded from fan-out until its next `PUT` brings a new token.

### 9.3 Credentials

**BF-68.** The FCM service-account JSON lives on the VPS outside the repository and outside any web-served path. Its path is configuration. Nothing in source control contains key material; add a test that greps for it, as ParkIT does.

### 9.4 Delivery is best-effort

**BF-69.** "Sent" means FCM accepted the message. The backend cannot know whether a phone displayed it. The event log and the back office must say "accepted by FCM", never "delivered".

### 9.5 Message templates

**BF-70.** Each site has a template per advisory type, editable in the back office. They default to the spec §9 / proposal §6 wording.
- Placeholders: `{site}`, `{zone}` (the recommended zone's name), `{topZones}` ("Basement 3 and Basement 4"), `{occupancyPct}`, `{fullZone}` (for `ZONE_ADVISORY`).
- A template referencing a placeholder that the type does not provide is rejected when saved.
- English only in this revision; the model must allow a locale to be added later.

---

## 10. Settings

### 10.1 Site settings (spec §10, proposal §4)

**BF-71.** Validated on save. An invalid combination is refused, not clamped.

| Setting | Default | Validation |
|---|---|---|
| `managed` | false | Turning it on is logged as `CONFIG_CHANGED`. |
| `triggerPct` (T) | 90 | 1–100 |
| `resetPct` (R) | 80 | < `triggerPct` |
| `changePoints` (Δ) | 5 | 1–50 |
| `changeDirection` | `RISING` | `RISING` / `BOTH` |
| `stabilisationS` (S) | 300 | 0–3600 |
| `recommendationMargin` | 10 bays | ≥ 0 |
| `staleLimitS` | 120 | ≥ 2 × ParkIT's post interval (60) |
| `partialIsStale` | true | |
| `recoveryPush` | false | |
| `zoneAdvisory` | false | |
| `zoneResetGap` | 10 points | 1–50 |
| `notificationWindow` | Mon–Fri 06:00–10:00 (§15 Q4) | A list of {weekdays, start, end} in site local time; `start < end`; no overnight span in this revision. An empty list means no window (any time). |
| `cooldownS` / `dailyCap` | 1800 / 2 | Used only when `limitScope = DEVICE_PER_SITE`. |
| `pushExpiryS` | 1800 | 60–86400 |
| `timeZone` | `Africa/Johannesburg` | A valid IANA name. |

Deployment-level settings: `limitScope`, plus `cooldownS`, `dailyCap` and `timeZone` for `DEVICE` scope, and the device ceiling (BF-37).

### 10.2 Zone settings

| Setting | Default |
|---|---|
| `enabled`, `recommendable`, `preferred` | false (discovered zones), true, false |
| `priority` | 100 |
| `limitedPct` / `fullPct` / `fullMinFree` | 80 / 95 / 5 |
| `unknownLimitPct` | 25 |
| `advisoryPct` | unset (no zone advisory) |
| `note` | empty. Free text for staff, e.g. how the zone is sensed (§5.2). Never sent to the app. |

**BF-72.** A settings change takes effect at the next evaluation, without a restart. It does not reset engine state, except that switching `managed` off and back on starts a fresh cycle.

---

## 11. Retention and privacy

**BF-73.** Daily purge:

| Data | Kept for |
|---|---|
| Devices with no `PUT` for 90 days | Erased (token and selections). |
| Send history | 35 days. |
| Event log | 365 days. |
| Occupancy history (BF-4) | 180 days. |
| Request logs that include app traffic | 30 days, with no `deviceId` and no token in them. |

These defaults are settled (§15 Q2). They are deployment settings, not constants.

FCM tokens and device ids are personal information under POPIA. They appear in no log and no back-office view, and no export includes them.

**BF-73a. Data requests.** SATT is the contact for POPIA requests from phone users and is named as such in the app's privacy notice; ABSA's information officer is copied on each request. Because phones are anonymous, the backend cannot match a person to a device, so erasure is self-service: the app's "erase my data" action calls `DELETE /v1/devices/{deviceId}` (BF-34). A request that arrives by email is answered by pointing to that action; SATT staff cannot and must not search for a device by any personal detail.

---

## 12. Back office

The template's admin web app, with users and roles. Roles: **Administrator** (everything), **Operator** (view everything, test push, announcements), **Viewer** (read only).

**BF-74. Test push** (proposal §3.3, `POST /v1/admin/sites/{id}/test-push`). The target is either:
- one device, found by the last 6 characters of its id as shown in the app's settings screen, or
- the site's topic. This needs a confirmation that names the topic, because it reaches every subscriber.

A test push works even for an unmanaged site, is logged as `TEST_PUSH`, and is not counted against limits.

**BF-75. Announcement.** Free text to a site's topic, Administrator only, with a confirmation, logged.

**BF-76. Screens:**
- **Sites list:** each site's name, managed / shadow, data age, stale flag, engine state, site occupancy, recommendation, and devices opted in.
- **Site live view:** the zone table exactly as the app sees it (same computation, BF-24), plus the engine state with its timers ("pending since 07:41, fires at 07:46").
- **Site settings, zone settings, message templates, notification window.**
- **Event log:** filter by site, type, reason and period; export to CSV.
- **Ingest keys:** create (shown once), rotate, revoke, last used, last source IP.
- **Device statistics:** counts by platform, app version, opted-in and site. Never ids or tokens.
- **Occupancy history chart:** site and zones over a chosen day, with the trigger and reset levels drawn. This is what the pilot tuning in spec §13 needs.

**BF-77. Config changes are audited:** who, when, and before and after.

**BF-78. Admin API endpoints:**
- proposal §3.3: `GET`/`PUT /v1/admin/sites/{id}/config`, `GET /v1/admin/sites/{id}/events`, `POST /v1/admin/sites/{id}/test-push`
- plus: sites CRUD, zones CRUD, templates, keys, device stats, history

---

## 13. Operations

**BF-80.** `GET /health` is unauthenticated, for the uptime check. It returns status only: database reachable, and the age of the last engine tick.

**BF-81.** The once-a-minute evaluation (BF-50) and the daily purge (BF-73) run as scheduled jobs, with the same single-evaluator rule (BF-51).

**BF-82. Operator alerts** (email, using the template's notification system):
- a managed site has had no accepted ingest for 10 minutes, and again when it recovers
- FCM credential failure
- the device ceiling is reached
- the ingest rejection rate exceeds 10 a minute for a key

**BF-83.** Nightly `pg_dump`, kept 14 days, copied off the VPS.

**BN-3. Sizing:**
- up to 20 sites, 50 000 devices, one ingest every 30 s per site
- availability p95 under 300 ms at the server
- fan-out to 5 000 devices completes within 2 minutes

**BN-4.** The backend can be redeployed without losing engine state (BF-5) and without re-sending advisories (BF-52).

### 13.1 Mock and demonstration mode (proposal §3.4)

**BF-84.** A deployment flag `mockMode`, **off by default**, read once at startup. When on, these exist:
- `POST /mock/sites/{id}/occupancy` (sets a snapshot as if ParkIT had sent it)
- `POST /mock/clock` (advances an injected clock)
- the simulator page for AT-01 to AT-08

When off, those routes are not registered at all: 404, not 403. The production configuration must refuse to start with `mockMode` on unless an explicit second flag acknowledges it.

**BF-85.** The engine reads time only from an injectable clock, so the acceptance scenarios run as automated tests with simulated time and need no mock server.

---

## 14. Acceptance

Spec §11, restated against this design, plus backend-specific cases. Each should be an automated test with an injected clock.

| ID | Given / when | Then |
|---|---|---|
| AT-01 | Site at 75 % | Availability served; no candidate. |
| AT-02 | 90 % for 4 min, then 88 % | IDLE; `NOT_STABLE` logged; no push. |
| AT-03 | 90 % held for 5 min | `SITE_INITIAL` sent to eligible devices; state ACTIVE. |
| AT-04 | ACTIVE, notified at 90 %, now 92 % | No candidate. |
| AT-05 | ACTIVE, notified at 90 %, now 95 %, same recommendation and top-two | Dropped as `NO_MATERIAL_CHANGE`. With a new recommendation: sent to devices out of cooldown and under the cap; the rest logged `COOLDOWN` / `DAILY_CAP`. |
| AT-06 | ACTIVE, falls to 79 % | IDLE; `RECOVERY` only if enabled; a later rise to 90 % starts a new cycle. |
| AT-07 | Site at 85 %, B1 98 %, B4 55 % | The app recommends B4; no site push; a `ZONE_ADVISORY` only if enabled and B1 is preferred. |
| AT-08 | No ingest for 3 min, or a zone `OFFLINE` | `stale: true` / `UNKNOWN`; recommendation never points at an UNKNOWN zone; candidates `STALE_DATA`. |
| BT-01 | Two evaluations of one site start at once | Exactly one advisory per device. |
| BT-02 | Process killed mid fan-out, then restarted | No device receives the advisory twice. |
| BT-03 | Ingest key for site A posts `siteId` B | 403, event logged, nothing stored. |
| BT-04 | `measuredAt` 5 min ahead of the server | 422 `CLOCK_SKEW`. |
| BT-05 | Two zones' free counts alternate 100/104 and 104/100 | The recommendation does not change (margin 10). |
| BT-06 | FCM answers `UNREGISTERED` for one token | Token invalidated; that device is skipped in the next fan-out; the others are unaffected. |
| BT-07 | `DELETE` a device | Token gone from the database immediately; the next advisory skips it. |
| BT-08 | `limitScope = DEVICE`, a phone follows two sites that both go ACTIVE within 30 min | One push; the second is `COOLDOWN`. |
| BT-09 | Site `managed = false` reaches 90 % for 5 min | Candidate logged `UNMANAGED`; nothing sent. |
| BT-10 | `mockMode` off | `/mock/*` returns 404. |
| BT-11 | Counts do not sum to capacity | Accepted, `INGEST_INCONSISTENT`, zone `PARTIAL`. |

---

## 15. Settled questions

The questions carried from spec §12 and proposal §7, as ruled by SATT on 2026-11-26. Each ruling is written into the requirement it names.

| # | Question | Ruling | Where |
|---|---|---|---|
| Q1 | Does a `RECOVERY` push count towards the cooldown and daily cap? | **Yes**, both. | BF-60 |
| Q2 | Retention periods, and who answers POPIA data requests for devices | **The BF-73 defaults stand.** SATT is the contact, ABSA's information officer copied; erasure is self-service in the app. | BF-73, BF-73a |
| Q3 | Zone advisories before the site trigger? | **Build them, off by default** (`zoneAdvisory = false`). They take a phone's daily slots, so they are turned on only when ABSA asks. | BF-56 |
| Q4 | A morning-only notification window? | **Yes:** a new site defaults to Mon–Fri 06:00–10:00 in site time; editable per site. | §10.1 |
| Q5 | Alice Lane's sensing | **Mixed:** some zones per bay, some ramp-counted. The backend treats them the same; a zone note records which is which. | §5.2, §10.2 |
| Q6 | Should the existing ABSA site move to the backend? | **Later, not in this build.** The procedure is in §15.1. | §15.1 |

### 15.1 Moving the existing ABSA site later

The existing site keeps ParkIT's legacy notifier and topic `ABSA-270RR` until this is done. Nothing in this build may depend on it.

1. Create the site in the backend with `managed = false`, its `topic` set to `ABSA-270RR`, and an ingest key.
2. Add a FREESPACE device in that site's ParkIT and let it publish. The backend runs the engine in shadow mode (BF-61): every candidate is logged as `UNMANAGED`, nothing is sent.
3. Tune the site settings against the shadow events and the occupancy history until the candidates match what the site should receive.
4. In one change window: switch the legacy notifier off in ParkIT, then set `managed = true` in the backend. Never have both on, or phones get two pushes.
5. The app keeps subscribing to `ABSA-270RR` for announcements (D5) and keeps declaring the legacy `msg-channel` Android channel until every phone runs a release that no longer needs it.
