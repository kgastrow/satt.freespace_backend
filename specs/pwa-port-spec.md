# PWA Port Spec

How to bring another repository forked from the same template up to OneFan's PWA
behaviour: build identity, the update lifecycle, post-deploy chunk recovery,
install surface, Web Push, and the serving rules the client code depends on.

- **Audience:** an engineer (or agent) working in the target repo.
- **Source of truth:** the OneFan repo at commit `1f1fdf9`. Every path below is
  relative to that repo root unless stated otherwise.
- **Assumption:** the target is another app forked from the same template, so it
  already has the template's PWA — `vite-plugin-pwa` at defaults, a
  `useVersionCheck` poller, `useInstallPrompt`, `InstallBanner`. If the target is
  the template itself, the same tracks apply but everything marked *adapt* has to
  be genericised rather than rebranded.

---

## 0. Scope

**In scope.** Nine tracks, T1–T9 below. T1–T5 and T7–T9 are the PWA shell and the
update model. T6 (Web Push) is separable and roughly half the total effort,
because it carries backend models, an API, a migration and an operator runbook.

**Out of scope.** OneFan product surfaces that merely happen to use these
primitives — the gate scanner's IndexedDB offline queue
(`src/lib/scan/offline.ts`), the hoisted stream player, the splash gate. They are
named where they explain a design choice, not because they should be ported.

---

## 1. Why the template's PWA is not enough

Each of the following is a defect that was observed in production and is now
fixed by a specific piece of this port. They are the reason the tracks are shaped
the way they are, and the reason several settings must not be "tidied up" on the
way across.

| # | Failure | Cause | Fixed by |
|---|---|---|---|
| P1 | Every client reported `commit_hash: "development"` forever; update detection was dead for weeks and nothing downstream could tell two releases apart | Build silently fell back to a placeholder when `git rev-parse` failed | T1 |
| P2 | A fan on a live match, a checkout, or a gate scanner mid-shift was force-reloaded with no prompt | `controllerchange` reloaded unconditionally | T3 |
| P3 | The new worker was promoted the moment it was detected, pruning the precache out from under the open page; its next lazy chunk missed cache, hit the network, and 404'd | `skipWaiting: true` | T2 |
| P4 | Only the first deploy a long-lived tab saw would ever prompt | `workbox-window` stops listening for `updatefound` >60s after registration | T3 |
| P5 | iPhones sat on weeks-old builds indefinitely | Backgrounded iOS suspends timers, and a bfcache restore fires `pageshow` without reliably firing `visibilitychange` | T3 |
| P6 | Clients were handed a stale `sw.js` | Cloudflare rewrote the origin's `no-cache` | T7 |
| P7 | A lazy route after a deploy failed with an opaque module parse error | `/assets/` fell through to `index.html` with a 200 instead of a real 404 | T4 + T7 |
| P8 | A genuinely missing chunk reloaded forever | Reload guard was a flag cleared on `load` — the very event it was meant to survive | T4 |
| P9 | Fans reported being "unable to enable push" with the toggle greyed out | On iOS, Web Push exists only for a home-screen install; the generic "unsupported" copy was true and useless | T6 |

---

## 2. Tracks

### T1 — Build identity

**Purpose.** The commit hash is the build's identity: it is what `version.json`
advertises, what the update check compares, and what `X-App-Commit` reports on
every API call. Nothing else in this spec works without it.

**Files.**

| File | Action |
|---|---|
| `app/frontend/vite.config.ts` | Copy `getGitCommitHash`, `getBuildMetadata`, `assertBuildIsIdentifiable`, `generateVersionJson`, the `generate-version-json` plugin, and the three `define` entries |
| `app/frontend/src/store/api.ts` | Set the `X-App-Commit` request header (`:34`) |
| `app/frontend/src/types/version.ts` | `VersionInfo` type |
| `app/backend/src/core/config.py` | Add `X-App-Commit` to `CORS_ALLOWED_HEADERS` — both the field default (`:384`) and the runtime default (`:1002`) |

**Copy verbatim.** All of it. Nothing here is OneFan-specific.

**Gotchas.**

- `getBuildMetadata()` **must** stay memoised. Before it was, each caller re-ran
  git and took a fresh timestamp, so the bundle's `VITE_BUILD_TIME` and
  `version.json`'s `build_time` disagreed.
- `assertBuildIsIdentifiable()` **fails the production build** when git cannot
  name the commit (P1). The escape hatch is `ALLOW_UNVERSIONED_BUILD=true`.
  Failing a build is recoverable in a minute; shipping an unidentifiable one is
  not noticed for weeks. Only `config.command === 'build'` is held to this — dev
  and the test runner legitimately have no commit.
- `version.json` is written to **both** `public/` (dev server) and `dist/`
  (`writeBundle`).

---

### T2 — Service worker configuration

**Purpose.** Produce a worker that precaches the whole build in the background
and then waits, rather than one that takes over the moment it lands.

**File.** `app/frontend/vite.config.ts`, the `VitePWA({...})` block.

**Copy verbatim.**

```
disable: process.env.VITE_ENABLE_PWA !== 'true'
registerType: 'prompt'
workbox: {
  globIgnores: ['**/version.json'],
  navigateFallback: '/index.html',
  navigateFallbackDenylist: [/^\/api\//],
  skipWaiting: false,
  clientsClaim: true,
  cleanupOutdatedCaches: true,
}
```

Plus the `version.json` `NetworkFirst` rule, the `/api/` `NetworkFirst` rule, and
the `.(js|css|woff2?)$` `CacheFirst` rule.

**Adapt.**

- `manifest` — name, description, `theme_color`, `background_color`, `icons`.
- `importScripts: ['/sw-push.js']` — only with T6.
- The `\/api\/v1\/scan\/cache\/` runtime rule is the OneFan gate scanner. Drop it
  unless the target has an equivalent offline snapshot.

**Gotchas.**

- `skipWaiting: false` and `clientsClaim: true` look contradictory and are not.
  Waiting is what stops P3; `clientsClaim` only matters once a worker *does*
  activate, and without it a first-ever visitor is never controlled at all — no
  offline shell, and no runtime cache ever populates.
- Stay on `generateSW`. `importScripts` is what makes that possible with push
  handlers; switching to `injectManifest` to get them is a much heavier change.
- `globIgnores` on `version.json` — precaching the version file defeats the
  version check.

---

### T3 — Update lifecycle

**Purpose.** A new build installs quietly, waits, and is applied either while the
user is demonstrably elsewhere or because they asked. Never underneath them.

**Files, in dependency order.**

| File | Role |
|---|---|
| `src/lib/swUpdate.ts` | The one place that knows a build is staged, and the only place that reloads |
| `src/registerSW.ts` | Registration + update detection |
| `src/hooks/useVersionCheck.ts` | `/version.json` poller — advisory and watchdog only |
| `src/hooks/useAppUpdate.ts` | Combines the two signals; dismissal and staleness policy |
| `src/lib/deferUpdate.ts` | Deferral claims: reasons not to swap the build right now |
| `src/hooks/useDeferUpdate.ts` | React wrapper for claiming/releasing |
| `src/hooks/useAutoApplyUpdate.ts` | The quiet-swap policy |
| `src/components/UpdateBanner.tsx` | The prompt, for devices that could not be updated quietly |
| `src/components/splash/SplashUpdater.tsx` | Silent updater for pages outside the app shell |
| `src/pwa.d.ts` | `vite-plugin-pwa/client` types |
| `src/main.tsx` | `import './registerSW'`; mount `<UpdateBanner />`, `<InstallBanner />` |

**Copy verbatim.** `swUpdate.ts`, `registerSW.ts`, `useVersionCheck.ts`,
`useAppUpdate.ts`, `deferUpdate.ts`, `useDeferUpdate.ts`, `pwa.d.ts`. The one
value worth reviewing per product is `STALE_BUILD_MS` (7 days) in `useAppUpdate`.

**Adapt.**

- `useAutoApplyUpdate.ts` → `PROTECTED_PATHS`. OneFan protects `/scan`,
  `/scorekeeping`, `/live-scoring`, `/checkout`, `/return`, `/success`,
  `/signup`, `/apply`. The target needs its own list: routes where a reload
  destroys in-memory work or costs money.
- Deferral claim points. In OneFan the claimants are
  `StreamPlaybackContext.tsx`, `MerchCheckoutPage.tsx` and `LiveNow.tsx`. The
  target picks its own.
- `UpdateBanner.tsx` — restyle entirely. Its fixed positioning exists to dodge
  OneFan's stream mini player.
- `SplashUpdater.tsx` — only if the target renders anything outside the app
  shell. Auto-applying without asking is correct **only** where there is no user
  state to lose.

**Design rules that must survive the port.**

1. **Two signals, deliberately not equivalent.** A `waiting` service worker means
   the build is fully precached on *this device* and applying it fetches nothing.
   A `/version.json` delta only means the origin is serving a different commit.
   Only the first should drive a prompt. The second is the sole signal when the
   PWA is disabled, and otherwise a watchdog: if a precached asset 404s mid-deploy
   the new worker's install aborts, no `waiting` ever appears, and the SW path
   goes silent with no other recovery. After a 10-minute grace, fall back to a
   plain reload.
2. **Own the `updatefound` listener.** Do not rely on `onNeedRefresh` alone (P4).
3. **Listen to `visibilitychange` *and* `pageshow`.** Both, in both
   `registerSW.ts` and `useVersionCheck.ts`, throttled to 30s. On iOS the
   foreground check is the only one that ever runs (P5).
4. **`controllerchange` raises the badge, it does not reload** — unless this page
   is the one that called `applyUpdate()`. Another tab promoting the worker must
   not reload a page that is mid-task (P2).
5. **A first-ever visit is not an update.** Capture
   `navigator.serviceWorker.controller` at startup; the initial `clientsClaim`
   handover must neither reload nor raise the badge.
6. **Exactly one `useAppUpdate` in the tree.** A second instance is a second
   version-check poller. This is why `useAutoApplyUpdate` is mounted inside
   `UpdateBanner` rather than in its own component.
7. **Dismissal is per deployed commit**, persisted in `localStorage`. "Not now"
   means not until the next deploy, not again in five minutes.
8. **Jitter the auto-apply** (30s hidden + up to 45s random). A deploy lands on
   every device at once and `visibilitychange` fires for all of them together; a
   cold boot is ~10 requests against a 100/min per-IP limiter, so a venue behind
   one NAT can rate-limit itself simply by being updated simultaneously.
9. **Never auto-apply on navigation.** It destroys anything the app shell hoists
   above the router.

---

### T4 — Post-deploy chunk recovery

**Purpose.** A long-lived tab keeps running the `index.html` it booted with,
which references chunk hashes the origin may no longer have. Recover silently
where possible, and say something useful where not.

**Files.**

| File | Role |
|---|---|
| `src/lib/retryImport.ts` | Retry once, then reload, guarded |
| `src/lib/lazyRoute.tsx` | `lazyNamed` / `LazyPage` — the only way to lazy-load a route |
| `src/components/StaleBuildNotice.tsx` | The "this tab is stale" screen |
| `src/components/ErrorFallback.tsx` (`:78`) | Route chunk errors to the notice |
| `src/pages/RouteErrorPage.tsx` (`:18`) | Same, for router errors |

**Copy verbatim.** `retryImport.ts` and `lazyRoute.tsx`. Restyle
`StaleBuildNotice.tsx`.

**Gotchas.**

- The reload guard is a **timestamp** in `sessionStorage` with a 30s window, not
  a flag (P8). When storage is denied it fails closed — declines to reload and
  lets the error reach the boundary, because a visible error beats an
  unbreakable refresh cycle.
- `retryImport` returns a never-settling promise after triggering the reload.
  Resolving would let a Suspense boundary render against a module that never
  loaded.
- Chunk-load errors surface as a `TypeError` in Chrome/Safari and as a message
  match elsewhere. Accept both; neither is a stable contract.
- Route **every** lazy route through `lazyNamed`. In OneFan, per-fragment copies
  of the lazy helper meant only `router.tsx`'s version retried, leaving the whole
  consumer surface with no recovery at all.
- `StaleBuildNotice` calls `applyUpdate()`, not `location.reload()`, so the
  reload lands on the build that actually has the missing chunk.

**This track is only meaningful with T7.** It exists because `/assets/` returns a
real 404 rather than the SPA shell.

---

### T5 — Install surface

**Purpose.** Installability and the home-screen identity.

**Files.**

| File | Action |
|---|---|
| `src/hooks/useInstallPrompt.ts` | Copy; near template-standard |
| `src/components/InstallBanner.tsx` | Copy and restyle |
| `src/features/preferences/` | `pwaInstallDismissed` flag |
| `index.html` head | `theme-color`, `apple-mobile-web-app-*`, `application-name`, `viewport-fit=cover`, icon links |
| `public/app-icons/` | `icon-192`, `icon-512`, `icon-maskable-192`, `icon-maskable-512`, favicons |
| `public/apple-touch-icon.png` | 180×180 |
| `public/offline.html` | Offline shell |

The code is small; the work is asset generation and branding. Maskable icons are
separate files from the `any`-purpose ones — a single icon declared as both is
cropped wrong on Android.

---

### T6 — Web Push *(separable)*

**Purpose.** Browser push notifications. Dormant until a VAPID keypair is
configured; nothing crashes and no prompt appears without one.

**Frontend.**

| File | Role |
|---|---|
| `public/sw-push.js` | `push` / `notificationclick` handlers, pulled in by `workbox.importScripts` |
| `src/lib/webPush.ts` | Feature detection, VAPID key conversion, (un)subscribe, iOS/standalone detection, `pushBlockReason` |
| `src/hooks/useWebPush.ts` | Orchestration |
| `src/store/api/pushApi.ts` | RTK Query endpoints |
| `src/components/notifications/WebPushCard.tsx` | Settings toggle |
| `src/components/onefan/PushOptInPrompt.tsx` | The fan-facing nudge |
| `src/locales/*/push.json` | `push` namespace, registered in `src/i18n/config.ts` |

**Backend.**

| File | Role |
|---|---|
| `src/models/web_push_subscription.py` | Per-device subscription; partial unique index on `(user_id, endpoint)` where `deleted_time IS NULL` |
| `alembic/versions/…` | **Autogenerate** with `make migrate-new` — never hand-write |
| `src/api/push.py` | `/notifications/push/vapid-key`, `/subscriptions`, super-admin provider management |
| `src/api/v1/__init__.py` | Register the router (`:81`, `:302`) |
| `src/serialisers/foundations.py` | `PushSubscription*`, `VapidKeyResponse` |
| `src/serialisers/web_push.py` | Provider status / set-provider schemas |
| `src/services/notifications/web_push_config.py` | DB-backed VAPID config with settings fallback; private key Fernet-encrypted at rest |
| `src/services/notifications/web_push_provider.py` | Signs and sends; payload is `{ title, body, url }` |
| `src/services/notifications/web_push_dispatch.py` | Fan-out; prunes on 404/410 |
| `src/core/config.py` | `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` |
| `scripts/seed_data/permissions.yaml` | The provider-management permission |
| `docs/deploy-web-push.md` | Operator runbook — port and adapt |

**Design rules that must survive the port.**

- **The VAPID key fetch is the "is push configured?" probe.** Unconfigured
  returns `503 push.not_configured`; the opt-in prompt then stays silent. No dead
  prompt, no error toast. Every other channel is unaffected.
- **iOS gets its own copy** (P9). `pushBlockReason` returns `ios-needs-install`
  when the browser is iOS and not in standalone display; the UI must say "add to
  Home Screen", not "unsupported".
- **Allowing opens both gates.** Subscribing the device *and* setting
  `web_push_enabled` on the account. One without the other delivers nothing and
  reads as a broken toggle.
- **The prompt is triggered deliberately**, never on first load — pass `trigger`
  at a moment that earns it, and persist dismissal in `localStorage`.
- The payload shape is a contract between `web_push_provider.py` and
  `sw-push.js`. Port both or neither.

**If the target repo has its own seeding conventions**, add the new permission to
its maintenance seeder, not only its bootstrap seeder.

---

### T7 — Serving rules

**Purpose.** The client-side update model assumes specific cache behaviour. Ship
this **before** T3/T4, or the new model runs onto old headers and P6 returns.

**File.** `app/backend/apache_site_config/onefan.conf` (`:140`–`:174`), plus the
QA vhost. Three tiers:

| Tier | Match | Header | Extra |
|---|---|---|---|
| 3 | `\.(png\|jpe?g\|gif\|svg\|webp\|avif\|ico\|woff2?\|ttf\|otf\|mp4)$` | `public, max-age=86400` | Un-hashed names, so a day — long enough for bandwidth, short enough to correct |
| 2 | `/assets/` | `public, max-age=31536000, immutable` | **`FallbackResource disabled`** |
| 1 | `^/(index\.html\|sw\.js\|sw-push\.js\|registerSW\.js\|manifest\.webmanifest\|version\.json\|offline\.html)$` | `no-store, no-cache, must-revalidate, max-age=0` + `Pragma: no-cache` | **`FallbackResource disabled`** |

**Gotchas.**

- **`no-store`, not `no-cache`.** Cloudflare enforces a minimum browser cache TTL
  on anything it caches and has overridden the origin's `no-cache` before,
  handing clients a stale `sw.js`. Cloudflare does not cache `no-store`.
- **`FallbackResource disabled` on `/assets/`** — a deleted chunk must 404. With
  the fallback active the browser gets `index.html` with a 200 and fails on an
  opaque module parse error (P7).
- **`FallbackResource disabled` on tier 1** — a missing service worker must 404
  too. `importScripts()` on an HTML body throws, which aborts installation of the
  new worker and leaves every client stuck on the previous one. That failure mode
  has no client-side recovery.
- `Header always unset Expires` on every tier; a fixed `Expires` rewrites what
  these rules just set.
- The frontend also fetches `version.json` with `cache: 'no-store'` and a
  cache-busting query param. Belt and braces, deliberately.

---

### T8 — Tests

Port these. Several encode the exact regressions in §1 and will catch a
half-applied port.

| Test | Covers |
|---|---|
| `src/__tests__/integration/pwa-config.integration.test.ts` | Manifest declares standalone + theme colour; every declared icon file **exists on disk**; no placeholder icons; the build-identity rules |
| `src/lib/swUpdate.test.ts` | Staging state machine, apply path, timeout fallback |
| `src/lib/retryImport.test.ts` | Retry, reload guard window, storage-denied fail-closed |
| `src/lib/deferUpdate.test.ts` | Claim/release semantics |
| `src/hooks/useAutoApplyUpdate.test.tsx` | Protected paths, hidden settle, deferral respect |
| `src/hooks/useVersionCheck.test.tsx` | Polling, foreground re-check, throttle |
| `src/components/UpdateBanner.test.tsx` | Prompt gating and dismissal |
| `src/registerSW.test.ts` | Detection wiring |
| `src/store/api.appCommit.test.ts` | `X-App-Commit` on every request |

---

### T9 — Environment

```
VITE_ENABLE_PWA=false
VITE_PWA_APP_NAME=<APP NAME>
```

Both belong in `.env.example`. `VITE_ENABLE_PWA` is a **build-time** Vite
variable, not a runtime one — setting it after a deploy does nothing until the
frontend is rebuilt. It gates three things at once: the `VitePWA` plugin, the
registration in `registerSW.ts`, and `useInstallPrompt`. This is the single most
common reason a correct port appears to do nothing.

Backend `VAPID_*` keys come with T6 and are documented in
`docs/deploy-web-push.md`.

---

## 3. Sequencing

```
T1 ──▶ T2 ──▶ T7 ──▶ T3 ──▶ T4 ──▶ T5 ──▶ T8
                │
                └──▶ T6   (any point after T2)
```

- **T1 first.** Every later track compares or reports the commit hash.
- **T7 before T3/T4.** Deploying the new update model onto old cache headers
  reintroduces P6, and T4 is meaningless until `/assets/` 404s properly.
- **T8 last**, or alongside each track if the target has the harness for it.
- **T6 independent** after T2 (it needs `importScripts`).

---

## 4. Per-repo adaptation checklist

Everything on this list is wrong by default in the target repo and must be
changed, not merely copied.

- [ ] Manifest: `name`, `short_name`, `description`, `theme_color`,
      `background_color`
- [ ] Icons: 192/512 `any`, 192/512 `maskable`, 180×180 apple-touch, favicons
- [ ] `index.html`: title, meta description, Open Graph / Twitter tags, CSP
- [ ] `useAutoApplyUpdate.PROTECTED_PATHS`
- [ ] Deferral claim sites (player, checkout, dirty forms)
- [ ] `UpdateBanner` styling and placement — must clear any persistent overlay
- [ ] `SplashUpdater` — keep only if a surface exists outside the app shell
- [ ] The `scan/cache` runtime-caching rule — drop unless there is an equivalent
- [ ] i18n: `updatePrompt.*`, `installBanner.*`, `staleBuild.*` (in `errors`),
      and the `push` namespace — **in every locale file**, not just `en`
- [ ] Apache/vhost `ServerName`, paths, and both prod and QA vhosts
- [ ] `VITE_PWA_APP_NAME`, `VAPID_SUBJECT`

---

## 5. Verification

A port is done when all of the following hold in a real deployed environment, not
just locally.

**T1.** `curl https://<host>/version.json` returns a real commit hash. A build
from a tree with no git history fails with the `Refusing to build` message.
Backend request logs show `X-App-Commit` on API calls.

**T2/T3.** Deploy build A, open the app, deploy build B, return to the tab: a new
worker installs and parks in `waiting`; the page does **not** reload; the badge or
banner appears. Background the tab for a minute on an unprotected route and it
swaps quietly. Repeat on a protected route and it does not.

**T3 (iOS).** Install to the Home Screen on an iPhone, background it, deploy,
reopen: the update is detected. This is the path with no other coverage.

**T4.** After a deploy, a long-lived tab navigating to a lazy route it has not
visited recovers silently. Force the second failure and `StaleBuildNotice`
appears rather than a generic crash screen.

**T5.** Chrome desktop and Android offer install; the home-screen icon is the
maskable one, not a cropped square. `display-mode: standalone` suppresses the
install banner.

**T6.** With no VAPID configured: no prompt, no toast, `503
push.not_configured`, in-app notifications unaffected. With a keypair configured:
subscribe on Android/desktop, receive a push, tap it, land on the payload's
`url`. On iOS in a Safari tab the card says "add to Home Screen"; installed, the
toggle works.

**T7.** `curl -I` each tier-1 path and confirm `no-store` survives the edge.
`curl -I https://<host>/assets/does-not-exist.js` returns **404**, not 200.

**T8.** The ported suite passes.

---

## 6. Open questions

- **Q1.** Does the target need T6? It is about half the total effort and carries
  a database migration and an operator procedure.
- **Q2.** Is the target served by the same Apache + Cloudflare topology? If it
  sits behind a different edge, T7 needs re-deriving — the rules are correct for
  this stack, but the *reasons* (edge TTL rewriting, SPA fallback) generalise and
  the directives do not.
- **Q3.** Should any of this be pushed back up to the template rather than copied
  sideways into one more fork?
