# Freespace Reference Extracts

Verbatim extracts from `specs/Freespace.pdf` (spec, rev 0.1, 21 Oct 2026, 5 pp.) and `specs/Freespace-Backend-Proposal.pdf` (proposal, rev 0.1, 24 Nov 2026, 4 pp.). Reference only. `BACKEND_FUNCTIONAL_DESCRIPTION.md` ("FD") is authoritative and overrides these where they differ. Section 6 lists the differences without resolving them.

Neither PDF contains a notification title. Only body wording is given.

---

## 1. Push messages (spec §9, proposal §6)

### 1.1 Default wording per type

Proposal §6 table (column "Wording (spec section 9)"). Curly-brace tokens are the PDF's own.

| Type | When (proposal) | Body wording |
|---|---|---|
| `SITE_INITIAL` | Above trigger and stable for 5 minutes | "ABSA parking is filling up. {top two zones} currently have the most available bays. Open Freespace for current availability." |
| `SITE_CHANGE` | Up 5 points or a new recommended zone, and still useful | "Parking availability has changed. {zone} is now the recommended parking area. Open Freespace for the latest information." |
| `ZONE_ADVISORY` | Optional: a preferred zone is full while the site is below trigger | "{zone} is full. {recommended zone} has available bays." |
| `RECOVERY` | Optional: site falls below reset level | "Parking availability has improved at {site}. Open Freespace to check available areas." |
| `TEST` | Back-office test | Free text. |

Spec §9, "Sample push-message wording", is the origin of three of these. Its text differs from the proposal's for RECOVERY and SITE_CHANGE:

- Initial high-occupancy advisory: "ABSA parking is filling up. Basement 3 and Basement 4 currently have the most available bays. Open Freespace for current availability."
- Material change advisory: "Parking availability has changed. Basement 4 is now the recommended parking area. Open Freespace for the latest information."
- Optional recovery advisory: "Parking availability has improved at Alice Lane. Open Freespace to check available areas."

Notes:
- `ZONE_ADVISORY` wording is not in spec §9. It appears only in proposal §6.
- `SITE_INITIAL` hard-codes "ABSA" rather than using `{site}`.
- In the `ZONE_ADVISORY` wording `{zone}` is the full zone and `{recommended zone}` is the recommendation.

### 1.2 Data payload (proposal §6)

"Each push carries a visible notification plus a data payload the app acts on:"

```json
{ "type": "SITE_CHANGE", "siteId": "absa-alice-lane",
  "recommendedZoneId": "b4", "occupancyPct": 95,
  "eventId": "evt_01J...", "sentAt": "2026-11-24T08:20:00Z" }
```

### 1.3 Delivery settings (proposal §6, verbatim)

| Delivery setting | Value and reason |
|---|---|
| Sending method | FCM sends to device tokens in batches. Per-phone limits cannot be applied to a topic broadcast. |
| Replacement | Collapse key per site, so a newer advisory replaces an older one in the notification tray. |
| Expiry | 30 minutes, so a phone that was offline does not receive outdated guidance later. |
| Android channel | `freespace_default` |
| On tap | The app opens the availability screen for siteId and refreshes it. |
| Token clean-up | Tokens reported as unregistered by FCM are removed automatically. |

No other FCM or APNs field details (priority, tag, apns headers) appear in either PDF.

---

## 2. App API (proposal §3.1)

"No user sign-in. Requests carry an app key header and are rate-limited." The header name is not given.

| Endpoint | Purpose (verbatim) |
|---|---|
| `GET /v1/sites` | Lists the sites available for selection on first launch and in Settings: id, name, topic, managed. |
| `GET /v1/sites/{siteId}/availability` | Live availability for one site (FR-01 to FR-04). Example below. |
| `PUT /v1/devices/{deviceId}` | Registers or updates {fcmToken, platform, siteIds[], notificationsEnabled, appVersion}. Called on launch, on token refresh and when settings change. Safe to repeat. |
| `DELETE /v1/devices/{deviceId}` | Removes the phone completely (full opt-out). |

The sites list response shape is NOT given beyond the field names "id, name, topic, managed". Types are not stated.

Example availability response (verbatim):

```json
{
  "siteId": "absa-alice-lane",
  "asOf": "2026-11-24T07:45:12Z",
  "stale": false,
  "site": { "capacity": 1200, "occupied": 1081, "occupancyPct": 90 },
  "recommendedZoneId": "b4",
  "zones": [
    { "id": "b1", "name": "Basement 1", "capacity": 450, "free": 18,
      "occupancyPct": 96, "status": "FULL", "asOf": "2026-11-24T07:45:10Z" },
    { "id": "b4", "name": "Basement 4", "capacity": 400, "free": 185,
      "occupancyPct": 54, "status": "AVAILABLE", "asOf": "2026-11-24T07:45:11Z" }
  ]
}
```

Types are implied only by the example: strings for ids, names, `asOf` (ISO-8601 UTC `Z`) and `status`. Integers for counts and `occupancyPct`. Boolean for `stale`. `recommendedZoneId` is a string or null.

Zone status table (proposal §3.1):

| Zone status | Rule (configurable) |
|---|---|
| AVAILABLE | Below 80% occupied. |
| LIMITED | From 80% to below 95% occupied. |
| FULL | 95% or more occupied, or fewer free bays than a configured minimum. |
| UNKNOWN | Zone data is stale or unavailable (AT-08). |

"Recommended zone (FR-03): the zone with the most usable free bays, excluding zones that are stale or full. A per-zone priority breaks ties and lets ABSA add proximity or entitlement rules later. The value is null when the data cannot be trusted. The recommendation is calculated by the backend, so the rules can change without releasing a new version of the app."

Spec illustrative example (spec §3): "Basement 1: 18 bays free (96% occupied); Basement 2: 42 free (89%); Basement 3: 116 free (71%); Basement 4: 185 free (54%). Freespace would recommend Basement 4 in this simplified scenario. These are not actual ABSA occupancy figures."

Spec FR-01..FR-05 (spec §3):
- FR-01: On launch or refresh, display the latest ParkIT availability for each configured parking floor/zone.
- FR-02: For each zone, display available-bay count and/or occupancy percentage, with an understandable availability status.
- FR-03: Identify a recommended parking area, initially based on the greatest usable availability; ABSA may later define proximity, entitlement or other priorities.
- FR-04: Display the age of the availability data or an appropriate stale-data indication if ParkIT updates are delayed.
- FR-05: Allow the user to refresh or revisit the availability screen without generating a push notification.

---

## 3. Admin endpoints (proposal §3.3)

The proposal gives ONLY a purpose per endpoint. No request or response shapes exist in either PDF.

| Endpoint | Purpose (verbatim) |
|---|---|
| `GET / PUT /v1/admin/sites/{id}/config` | Read or change the site settings in section 4. |
| `GET /v1/admin/sites/{id}/events` | Event log: threshold changes, pushes sent and suppressed, reason codes. |
| `POST /v1/admin/sites/{id}/test-push` | Send a test push to the site. |

Shapes must be designed from FD §10 (settings), §8.6 (events) and BF-74 (test push).

Proposal §4 "Settings per site (spec section 10)", initial values:

| Setting | Initial value |
|---|---|
| Site-wide trigger | 90% occupancy |
| Subsequent change threshold | 5 percentage points since the last notification |
| Reset level | Below 80% occupancy |
| Stabilisation time | 5 minutes |
| Minimum interval per phone | 30 minutes |
| Daily cap per phone | 2 pushes |
| Recovery push | Off |
| Zone advisory (optional) | Off; threshold configurable per zone |
| Notification window | None |
| Stale-data limit | 120 seconds |
| Timezone (for daily cap) | Africa/Johannesburg |

Spec §10 (configurability), verbatim bullets:
- Provide site-level configuration of initial trigger, subsequent change threshold, reset level, stabilisation time, cooldown and daily notification cap.
- Provide optional zone-specific thresholds and recommendation priorities.
- Maintain a log of occupancy threshold events, notifications sent/suppressed, reason codes and delivery requests for support and tuning.
- Prevent duplicate or contradictory pushes caused by occupancy fluctuations around a threshold (hysteresis plus stabilisation).
- Ensure alerts are based on recent, reliable occupancy data; suppress guidance when the relevant data is stale or unavailable.
- Respect mobile operating-system notification permissions and employee opt-in/preferences where applicable.

---

## 4. Mock / simulator (proposal §3.4) and acceptance scenarios (spec §11)

### 4.1 Mock-only endpoints (proposal §3.4, "local development and demonstration")

| Endpoint | Purpose (verbatim) |
|---|---|
| `POST /mock/sites/{id}/occupancy` | Set zone occupancy manually. |
| `POST /mock/clock` | Fast-forward time so the stabilisation and cooldown periods can be tested. |
| Simulator web page | Browser page for driving acceptance scenarios AT-01 to AT-08 during demonstrations. |

No request bodies are specified. Proposal §1 adds: "Until then, a local mock server will implement this same interface for app development and demonstration." and "The local mock and the eventual production backend expose the same API. Moving to production only changes the base URL configured in the app."

### 4.2 Acceptance scenarios (spec §11, as written)

| Test | Expected outcome |
|---|---|
| AT-01 | At 75% site occupancy, app shows live zone availability; no routine push. |
| AT-02 | At 90% for less than five minutes, no immediate push. |
| AT-03 | At 90% for five minutes, first useful advisory may be sent. |
| AT-04 | Change from 90% to 92% produces no occupancy-change push. |
| AT-05 | Change from 90% to 95% is eligible, but blocked if cooldown/cap applies or advice is unchanged. |
| AT-06 | Crossing below 80% resets alert state; recovery push follows ABSA configuration. |
| AT-07 | A full preferred zone can change the in-app recommendation below 90% site occupancy. |
| AT-08 | Unavailable or stale ParkIT zone data is flagged and does not generate misleading guidance. |

### 4.3 Related spec text

Spec §4 notification policy:

| Parameter | Initial proposed setting |
|---|---|
| Site-wide notification trigger | 90% occupancy |
| Additional occupancy-change threshold | 5 percentage points since the last relevant notification |
| Minimum interval per employee | 30 minutes between pushes |
| Maximum push volume | 2 per employee per day |
| Threshold stabilisation | Threshold must remain crossed for 5 minutes |
| Notification-cycle reset | When site occupancy drops below 80% |
| Below-trigger behaviour | No routine push; live availability remains visible in app |
| Zone recommendation change | May justify a push if material and useful, subject to cooldown and daily cap |

"A five-percentage-point change means, for example, an increase from 90% to 95% occupancy, not a relative 5% change in the current value. Meeting this change threshold makes a message eligible for consideration; it does not mandate a push when the employee would receive no new actionable guidance."

Spec §6 example sequence:

| Time | Occupancy | Expected behaviour |
|---|---|---|
| 07:00 | 75% | No push; employees may view live availability. |
| 07:45 | 90% | After stabilisation, send one advisory identifying zones with available parking. |
| 08:00 | 92% | No push; update the app display only. |
| 08:20 | 95% | Potential second advisory if cooldown has elapsed and guidance materially changes. |
| 09:00 | 97% | No push if previous advice remains valid or user cap reached. |
| Later | Below 80% | Reset notification cycle; optional recovery push only if configured. |

Spec §5 clarification: "For a large site, an important zone may become effectively full even while total site occupancy is below 90%. The system should therefore support a separately configurable optional zone-level advisory (for example, when preferred areas are full and employees should use another floor). This exception must still respect cooldown and daily limits."

Spec §7 example: "Basement 1 is 98% occupied, Basement 2 is 95%, and Basement 4 is 55%. Freespace should recommend Basement 4 on screen even when the site-wide occupancy is below 90%. ABSA may optionally activate a one-time morning advisory when preferred zones reach a configured threshold." Spec §7 also says recommendations "must reflect usable bays, not merely the site-wide average".

---

## 5. Proposal §1, §2, §4, §5, §7 details beyond the FD

Proposal §1 design assumptions:
- "No sign-in. Each phone registers anonymously using an ID generated by the app, its Firebase Cloud Messaging (FCM) push token and the sites the employee has selected."
- "Multiple sites. On first launch the employee selects one or more sites. The selection can be changed later under Settings."
- "Existing site unchanged. The external back-office system continues to send pushes for the existing site (topic ABSA-270RR). The new backend only sends pushes for sites it is configured to manage (initially Alice Lane), so no site receives pushes from both systems."
- "Topics retained. The app subscribes to one FCM topic per selected site. This keeps the existing system working and provides a channel for announcements to all users of a site."
- Topic name for the existing site: `ABSA-270RR`. No topic naming convention for new sites is given (e.g. no pattern for Alice Lane).

Proposal §2 components (names only): Occupancy intake, Availability service, Device registry, Notification rules engine ("using one state per site"), Push sender ("Applies per-phone limits, then delivers via FCM"), Event log ("Records every push sent or suppressed, with a reason code (spec section 10)").

Proposal §5, wording that adds detail beyond the FD:
- "The engine keeps one state per managed site. It is evaluated on every occupancy submission and once a minute, so stabilisation timers expire even when no new data arrives."
- State table: IDLE to PENDING (at or above trigger, record time of crossing); PENDING to IDLE if it drops below trigger before 5 minutes (no push, AT-02); PENDING to ACTIVE after 5 minutes (initial advisory, AT-03); ACTIVE "Rises 5 points above last notified level, or the recommended zone changes and stays changed for 5 minutes" gives a change advisory candidate (AT-04, AT-05); ACTIVE falling below reset level goes to IDLE ("recovery push only if enabled", AT-06); Any with "Data stale or unavailable" leaves state unchanged and suppresses all pushes (AT-08).
- "Usefulness check (before any push): a candidate message is dropped if it would not tell the employee anything new, for example the same recommendation in the same wording."
- "Per-phone checks: notifications enabled; site selected; 30 minutes since the last push; under the daily cap (reset at midnight site time); not a repeat of the last message; inside the notification window, if one is configured."
- "Reason codes logged: SENT, NOT_STABLE, NO_MATERIAL_CHANGE, COOLDOWN, DAILY_CAP, DUPLICATE, STALE_DATA, OPTED_OUT, OUTSIDE_WINDOW."

Proposal §3.2 (original intake, superseded by FD §5): "POST /v1/ingest/occupancy with {siteId, measuredAt, zones:[{zoneId, occupied}]}, authenticated with a machine API key. Each submission triggers a rules-engine evaluation."

Proposal §7 questions (answered by FD §15 and D1..D4):
- Are the daily cap and minimum interval counted per site, or per phone across all sites?
- Does ParkIT send occupancy to the backend, or does the backend fetch it? Is occupancy available per zone, or only from entry and exit ramp counts?
- Should the existing site eventually move to these rules, or remain with the external system?
- How long should push tokens and logs be kept? An anonymous push token can still be personal information under POPIA.
- Who will implement and host the production backend?

Spec §12 outstanding questions (answered by FD §15): Alice Lane sensing granularity; actual zones, floor names, capacities, bay entitlements and access restrictions; recommendation basis (most free, nearest entrance, assigned area, weighted); zone advisories before 90%; keep the recovery push or silent reset; daily cap of two and morning-only window; acceptable update latency and staleness limit; user preferences, message history and privacy.

Spec §8 architecture notes: the phone "need not continuously poll the server or use background GPS tracking to receive push notifications. ParkIT should make server-side decisions and publish only qualifying events. When the employee opens the app, it retrieves current availability through the agreed application interface." Spec §13: pilot the settings against actual Alice Lane occupancy patterns and tune with ABSA before full rollout.

---

## 6. Discrepancies

Each entry gives what the FD says and what the PDFs say. None is resolved here.

1. **Titles.** FD BF-65/BF-70 refers to `notification.title` and a template per type "default to the spec §9 / proposal §6 wording". The PDFs define no title for any type, only bodies. There is no default title text to copy.
2. **Placeholder names.** FD BF-70 defines `{site}`, `{zone}` (the recommended zone's name), `{topZones}`, `{occupancyPct}`, `{fullZone}`. The proposal uses `{top two zones}`, `{zone}`, `{recommended zone}`, `{site}`. In `ZONE_ADVISORY`, PDF `{zone}` means the FULL zone and `{recommended zone}` the recommendation. In FD, `{zone}` is always the recommendation and the full zone is `{fullZone}`. In `SITE_CHANGE`, PDF `{zone}` is the recommended zone. FD never defines `{recommended zone}`.
3. **Hard-coded "ABSA".** The PDF `SITE_INITIAL` wording says "ABSA parking is filling up." The PDF `RECOVERY` wording uses `{site}`. The FD does not say whether `SITE_INITIAL` uses `{site}`.
4. **Spec vs proposal wording.** Spec §9 recovery wording is "...at Alice Lane. Open Freespace to check available areas." The proposal templatises it as `{site}`. FD says defaults come from "spec §9 / proposal §6" without saying which wins. `ZONE_ADVISORY` wording exists only in the proposal.
5. **FCM batching.** The proposal says "FCM sends to device tokens in batches." FD BF-64 says one `messages:send` per token with bounded concurrency, because it believes the legacy batch API was shut down.
6. **Token clean-up.** The proposal says unregistered tokens "are removed automatically". FD BF-66/67 invalidates the token (`tokenInvalidatedAt`), excludes the device until its next `PUT`, and does not say it deletes it.
7. **FCM details cited from the proposal.** FD BF-65 attributes expiry and collapse to proposal §6. The PDF states only "30 minutes", "Collapse key per site" and channel `freespace_default`. `priority: HIGH`, `notification.tag`, the APNs headers and "all data values are strings" are not in either PDF. The proposal's example payload shows `occupancyPct` as the number 95 (not a string).
8. **Availability shape.** FD BF-31 adds `ageSeconds` and `site.freeUsable`, and defines `asOf` as the backend's `receivedAt`. The proposal example has neither added field. Its zone `asOf` values (07:45:10, 07:45:11) differ from the top-level `asOf` (07:45:12). The proposal does not say what `asOf` is.
9. **Sites list.** FD BF-30 returns `id`, `name`, `topic`, `managed`, `timeZone`. The proposal lists `id`, `name`, `topic`, `managed`, with no `timeZone` and no shapes or types.
10. **Admin endpoint shapes.** FD BF-78 and the task point at proposal §3.3 for the config/events/test-push endpoints. The proposal has only one-line purposes. The FD says test-push targets one device (last 6 characters of id) or the topic. The proposal says "Send a test push to the site." Request/response schemas are absent from the PDFs.
11. **Mock endpoints.** FD BF-84 describes `POST /mock/sites/{id}/occupancy` as "sets a snapshot as if ParkIT had sent it". The proposal says "Set zone occupancy manually", and its intake carried only `occupied` per zone. FD adds the `mockMode` flag, the 404 behaviour and the production guard, none of which appear in the PDFs.
12. **Intake payload.** The proposal §3.2 payload is `{siteId, measuredAt, zones:[{zoneId, occupied}]}` with a "machine API key". FD §5 replaces it (D3). FD also adds `Authorization: Bearer`, `/v1/ingest/ping`, rate limits and key formats, none of which are in the PDFs. The proposal's hosting statement "Who implements and hosts the backend is still to be decided" is superseded by D1.
13. **Per-phone check order and set.** The proposal lists: notifications enabled; site selected; 30 min since last push; daily cap; not a repeat; inside window. FD BF-58 orders: opted out, window, duplicate, cooldown, daily cap. FD has no check named for "site selected". It is handled by device selection.
14. **Limit scope and time zone.** The proposal makes the daily cap reset at "midnight site time", with one `Timezone (for daily cap)` per site and the cooldown/cap as per-site settings. FD D4/BF-63 defaults to per-phone across all sites with a deployment time zone, and uses site time only for `DEVICE_PER_SITE`.
15. **Notification window default.** The proposal §4 default is "None". FD §10.1 / Q4 defaults to Mon-Fri 06:00-10:00. The FD notes this as a ruling, but it contradicts the PDF default.
16. **Reason codes.** The proposal lists nine (SENT, NOT_STABLE, NO_MATERIAL_CHANGE, COOLDOWN, DAILY_CAP, DUPLICATE, STALE_DATA, OPTED_OUT, OUTSIDE_WINDOW). FD adds `UNMANAGED`, `NO_RECOMMENDATION`, `SEND_FAILED`, `TOKEN_INVALID`. The proposal does not provide an event-type list (`STATE_CHANGE`, etc.).
17. **Zone advisory trigger.** The proposal says "a preferred zone is full while the site is below trigger". Spec §7 says "one-time morning advisory when preferred zones reach a configured threshold". FD BF-56 uses `advisoryPct` or FULL held for S, once per zone cycle, evaluated only while the site is IDLE or PENDING.
18. **AT-02, AT-07 wording.** FD AT-02 adds a drop to 88% (spec: only "at 90% for less than five minutes, no immediate push"). FD AT-07 gives "site at 85%, B1 98%, B4 55%" (spec has no site %, and spec §7 uses B1 98%, B2 95%, B4 55%). FD AT-04/AT-05 are stated as "No candidate" / "dropped as NO_MATERIAL_CHANGE" rather than the spec's "no push".
19. **Stickiness and `ageSeconds`.** FD BF-24 adds a recommendation margin (stickiness) and `null` when the site is stale. The proposal says only "null when the data cannot be trusted", with ties broken by priority and no margin. FD acknowledges these as additions.
20. **FD content not found in the PDFs.** App key header name `X-Freespace-App-Key`, the legacy Android channel `msg-channel`, the "last 6 characters of id as shown in the settings screen", the "erase my data" action and privacy notice, `deviceId` format, `limitScope`, and the retention periods. FD sources these to decisions D1..D6, not the PDFs. The spec §13 citation in BF-4/BF-61 is valid (it refers to piloting and tuning).
21. **Spec dates and states.** FD cites "spec §12" and "proposal §7" for the open questions, which exist and match. Note that spec §12 contains an eighth question (preferences, history, privacy) which FD §15 does not list separately (covered by Q2).
